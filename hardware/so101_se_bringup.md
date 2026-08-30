# Waveshare SO-ARM101 SE bring-up

My bench log for getting the two arms identified, assembled, calibrated and
teleoperating. It sits alongside the vendor instructions, not instead of them.
If a photo or a label here disagrees with the documentation for the SKU I
actually bought, the documentation wins and I stop.

References I kept open:

- [Waveshare servo-ID procedure](https://www.waveshare.com/wiki/SO-ARM100/101_Set_Servo_ID)
- [Waveshare SO-ARM100/101 assembly guide](https://www.waveshare.com/wiki/SO-ARM100/101_Kit_Aassembly)
- [LeRobot SO-101 guide, v0.6.1](https://github.com/huggingface/lerobot/blob/v0.6.1/docs/source/so101.mdx)
- Waveshare Bus Servo Adapter (A):
  [wiring](https://docs.waveshare.com/Bus_Servo_Adapter_A/Product-Wiring-Example),
  [FAQ](https://docs.waveshare.com/Bus_Servo_Adapter_A/FAQ)
- [USB devices in WSL](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)

## Rules I set for myself

No servo power until I have written down all four of these:

- the exact kit SKU, including the `(SE)` marking, from the package or invoice
- output voltage, current rating, polarity symbol and intended arm, read off
  *both* power-supply labels
- controller and a representative follower/leader servo label, photographed and
  transcribed into `configs/hardware_manifest.yaml`
- a physical follower/leader label on each supply, so I cannot swap them by
  accident

The reason for being this careful: the Bus Servo Adapter (A) has no voltage
regulator. Whatever goes in comes out on the servo bus. A connector that fits is
not evidence that the supply is safe. The supply has to match the label on the
servo that is plugged in at that moment. Wire color means nothing.

Then, throughout:

- Servo supply off and verified off before touching any three-pin cable, jumper
  or daisy-chain link.
- Both adapter jumpers at `B` before power-up, for USB control.
- Exactly one loose servo on the bus during ID assignment. No chain.
- Both bases clamped before calibration or teleoperation, an unobstructed power
  cutoff within reach, and the follower supported against a torque-loss fall.
- Never force a powered joint, and never push an unpowered high-ratio follower
  joint through resistance.
- No firmware utilities, no flashing. That only starts if I have verified a
  model/firmware mismatch against authoritative documentation, which I have not.

One more, which cost me some anxiety before I understood it: if the kit turns up
already assembled, do **not** reach for `lerobot-setup-motors` first. It writes
IDs and baud rate to EEPROM. Work through the matching Waveshare instructions
and find out whether the bus is already configured. Everything below assumes
what I actually got: loose, new motors with no IDs yet.

## 1. Getting the adapter into WSL

Keep a WSL terminal open so the VM stays alive. Install `usbipd-win` from an
elevated PowerShell:

```powershell
winget install --interactive --exact dorssel.usbipd-win
```

Accept the driver prompt, restart Windows if it asks. Then, with an adapter
plugged in, share it (still elevated):

```powershell
usbipd list
usbipd bind --busid <BUSID>
usbipd list
```

`<BUSID>` is whatever `usbipd list` shows for the CH343 adapter. `bind` needs
admin and is normally a one-time thing per Windows device. Attaching does not
need elevation:

```powershell
usbipd attach --wsl --busid <BUSID>
```

Plain `attach` turned out to be fragile. The attachment drops on any
re-enumeration; `dmesg` shows `vhci_hcd: connection reset by peer`, the
`/dev/ttyACM*` node disappears, and whatever LeRobot command was running dies
with it. The self-healing form re-attaches on its own:

```powershell
usbipd attach --wsl --busid <BUSID> --auto-attach
```

That blocks, so the window stays open for the whole session, and running both
adapters at once means two PowerShell windows.

Two things I got wrong at first:

- A USB hub does not merge the adapters into one device. `usbipd` shares
  devices individually, so `usbipd list` still shows two `1a86:55d3` entries and
  each needs its own `bind` and `attach`.
- `bind` is persistent per device *and per port*. Moving an adapter to a
  different physical port can mean binding it again from an elevated prompt.

While a device is attached, Windows cannot use it. On the WSL side, check the
USB and serial nodes without opening the motor bus:

```bash
lsusb
find /dev -maxdepth 1 -name 'ttyACM*' -ls
find /dev/serial/by-id -maxdepth 1 -type l -ls 2>/dev/null
```

Waveshare calls the USB-to-serial chip a CH343. If no `/dev/ttyACM*` shows up,
re-check `usbipd list` and run `wsl --update` from Windows before blaming
LeRobot.

If permissions are the only problem, open up the one port I just identified,
not every serial device:

```bash
sudo chmod a+rw /dev/ttyACM0
```

That is lost on reconnect. A udev rule can come later, once the USB identity is
recorded. Prefer the `/dev/serial/by-id/...` alias where there is one, because
`/dev/ttyACM0` ordering moves around.

To hand the device back to Windows:

```powershell
usbipd detach --busid <BUSID>
```

Repeat for the second adapter, and do not assume the two identical boards keep
the same Linux path. Attached alone, both come up as `/dev/ttyACM0`; the
numbering only reflects attachment order. The CH343 serial baked into the
`/dev/serial/by-id/...` alias is the only durable identifier, so mark each board
physically and write down which serial belongs to which arm.

## 2. Finding the adapter port

Install the locked hardware environment, if it isn't there yet:

```bash
uv sync --frozen --extra hardware
uv run --frozen --extra hardware rrt doctor
```

With the intended adapter visible in WSL, run LeRobot's port finder and follow
its disconnect/reconnect prompt:

```bash
uv run --frozen --extra hardware lerobot-find-port
```

Note which physical controller it picks out as follower or leader. Use the
`/dev/serial/by-id/...` path if WSL exposes one, otherwise the current
`/dev/ttyACM*` for this session. Finding a port says nothing about the supply
being correct; the label check still applies.

`lerobot-find-port` is only needed once, to work out which board is which. After
that each arm is addressed directly by its alias:

| Arm | CH343 serial | Stable alias |
| --- | --- | --- |
| leader | `5B79017659` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B79017659-if00` |
| follower | `5B79015017` | `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B79015017-if00` |

These survive reboots and work on any Linux host, so they carry over to the
desktop unchanged.

## 3. Assigning the servo IDs

Each arm is its own bus and uses IDs 1 to 6 independently, so a follower ID
does not collide with the same ID on the leader. LeRobot runs the bus at
1,000,000 baud and stores the ID and baud rate in the servo's EEPROM.

The setup tool works from the end effector back toward the base:

| Servo ID | Joint / LeRobot name | Prompt order |
| ---: | --- | ---: |
| 1 | shoulder pan / base (`shoulder_pan`) | 6th |
| 2 | shoulder lift (`shoulder_lift`) | 5th |
| 3 | elbow flex (`elbow_flex`) | 4th |
| 4 | wrist flex (`wrist_flex`) | 3rd |
| 5 | wrist roll (`wrist_roll`) | 2nd |
| 6 | follower gripper or SE-leader trigger (`gripper`) | 1st |

Twelve labels written out before starting anything: `F1`-`F6` for the follower,
`L1`-`L6` for the leader. Two sets of motors, two verified supplies, kept apart.

### Follower

Follower controller on USB, both jumpers at `B`, verified follower supply only:

```bash
uv run --frozen --extra hardware lerobot-setup-motors \
  --robot.type=so101_follower \
  --robot.port=<FOLLOWER_PORT>
```

(`<FOLLOWER_PORT>` is the real port or alias. No angle brackets.)

At **every** prompt:

1. Switch off or unplug the servo DC supply, and leave it off while touching
   the cable.
2. Connect only the motor the prompt names, straight to the controller. Check
   both motor sockets: it must not run on to another motor.
3. Confirm connector orientation, `B` jumpers, follower supply label.
4. Restore DC power, *then* press Enter once.
5. Wait for the success message and write the ID into the bench notes.
6. Cut DC power before unplugging the motor, then put its `F<n>` label on
   immediately.

Expected order is `gripper` -> 6, `wrist_roll` -> 5, `wrist_flex` -> 4,
`elbow_flex` -> 3, `shoulder_lift` -> 2, `shoulder_pan` -> 1. If a name or ID
comes back different, stop. Do not paper over it with a different physical
label.

Step 4 is the one that is easy to get backwards. The servo **must be powered
when Enter is pressed**: LeRobot broadcast-pings across every baud rate, and an
unpowered servo cannot answer, which gives

```text
RuntimeError: Motor '<joint>' (model 'sts3215') was not found
```

Power comes off only while a three-pin cable is being seated or pulled, never
during the scan and write.

Reassuringly, `setup_motor` checks the model number before it writes anything.
A servo that answers with an unexpected model aborts the run, names both
numbers, and leaves EEPROM alone. The `(SE)` leader servos pass this as
`sts3215`, so the SE marking does not mean a different motor model as far as
LeRobot is concerned.

If a run dies partway it restarts at `gripper`. Reassigning an ID a servo
already holds is harmless, so I just walk the chain again.

### SE leader

Same again, with the leader controller, the verified leader supply and the
`L1`-`L6` labels:

```bash
uv run --frozen --extra hardware lerobot-setup-motors \
  --teleop.type=so101_leader \
  --teleop.port=<LEADER_PORT>
```

Same power-off swap sequence, same 1-6 mapping. Never a follower motor on the
leader controller or the other way round. Finishing one arm does nothing for the
other.

These bus IDs are not the LeRobot names `rir_follower_v1` and `rir_leader_v1`
that show up later. Numeric IDs address servos on a serial bus; the names
address calibration records.

## 4. Assembly and daisy-chain

Both servo supplies stay disconnected for this. Screw and horn orientations come
from the photographs in the Waveshare assembly guide; I am not going to
reconstruct those from text. Each labeled motor goes to its matching joint:

```text
controller -> F1/L1 base -> F2/L2 shoulder -> F3/L3 elbow
           -> F4/L4 wrist flex -> F5/L5 wrist roll -> F6/L6 gripper/trigger
```

Before closing each printed part: check it for cracks and clear the support
material, compare motor and horn orientation against the vendor image, route the
three-pin cable so it is not trapped, twisted or loaded, leave slack for the
joint's full range without leaving a loop that can catch on a horn or a
neighboring joint, and tighten evenly into the plastic without stripping it.

The controller connects to ID 1 at the base only; everything after that is
daisy-chained in ascending ID order. Check the whole chain and clamp the base
before restoring power. If communication comes back incomplete, kill power and
inspect cables, connector orientation and labels. Rerunning EEPROM setup is not
a diagnostic step.

## 5. Calibration, with the names I intend to keep

Bases clamped, workspace empty, follower supported. One arm at a time:

```bash
uv run --frozen --extra hardware lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=<FOLLOWER_PORT> \
  --robot.id=rir_follower_v1

uv run --frozen --extra hardware lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=<LEADER_PORT> \
  --teleop.id=rir_leader_v1
```

Follow the v0.6.1 prompts exactly: middle-of-range pose first, then every joint
through its full usable range. Do not force an obstruction and do not lever
against the mechanical hard stops. Unexpected motion, a bus timeout, a hot
servo or a snagged cable all mean stop.

Two files come out, named after the shared LeRobot classes rather than the
`so101_*` type strings, which confused me for a minute:

```text
~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/rir_leader_v1.json
~/.cache/huggingface/lerobot/calibration/robots/so_follower/rir_follower_v1.json
```

The prompts are less demanding than they read. Joints do not have to be moved in
isolation: `record_ranges_of_motion` tracks every joint's min and max at the
same time and independently, so moving several at once is fine as long as each
one reaches both ends. And `wrist_roll` is skipped entirely and hardcoded to a
full turn, so there is no point sweeping it.

Worth sanity-checking the result rather than trusting it. Each recorded range
should sit close to 2048 at its center, which is what `set_half_turn_homings`
having worked looks like. Calibrating both arms also cross-checks them: on this
pair the two independent calibrations agreed to within about 1% on every joint
except the gripper.

Those IDs stay fixed in every command from here on. Back the files up privately
before ever recalibrating, and record a checksum:

```bash
sha256sum <CALIBRATION_FILE>
```

Calibration belongs to a specific physical arm under a specific name. The files
do not follow the hardware to another machine on their own.

## 6. First teleoperation

First run with nothing else in the workspace: no puck, no camera rig, no
paddle. Both arms clamped, follower supported, hands clear of pinch points, and
ideally someone else near the motion-power cutoff. Leave the follower in a safe
pose from calibration and put the passive SE leader into roughly the same pose
before starting. Never force the follower to match the leader.

```bash
uv run --frozen --extra hardware lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=<FOLLOWER_PORT> \
  --robot.id=rir_follower_v1 \
  --teleop.type=so101_leader \
  --teleop.port=<LEADER_PORT> \
  --teleop.id=rir_leader_v1
```

Very small, slow movements, well above the table, one joint at a time: correct
sign, useful range, repeatability, cable clearance. Any jump, repeated timeout,
odd noise or heat, large offset or snagged cable and I stop.

`max_relative_target` defaults to `None`, which means **no per-step motion cap
at all**. Passing a value bounds how far the follower can move per control step:

```bash
  --robot.max_relative_target=5
```

It clamps the per-step delta in degrees, so a pose mismatch becomes a fast creep
instead of an instant snap. It is a backstop, not a replacement for matching the
two poses by hand first.

The same hazard applies to anything that enables follower torque: the servos go
back to holding whatever `Goal_Position` is still sitting in their registers,
which can be a long way from where the arm is now if it has been moved by hand
since. The scripts in `hardware/tools/` seed `Goal_Position` from
`Present_Position` before enabling torque. `lerobot-teleoperate` does not, which
is the practical reason to match poses first.

`disable_torque_on_disconnect` defaults to `True`, so the follower goes limp
when teleoperation exits. Bring it low and supported before stopping.

### Position-loop gains

LeRobot writes `P=16, I=0, D=32` to the follower on every connect. That is a
deliberately compliant tuning and it feels weak under leverage. I measured it
instead of guessing (`hardware/tools/gain_experiment.py`, one loaded pose held
throughout, gains swept in place):

| P | I | shoulder_lift sag | elbow_flex sag | wrist_flex sag |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 0 | -0.7 deg | -2.9 deg | -1.1 deg |
| 32 | 0 | -0.8 deg | -1.1 deg | -0.4 deg |
| 32 | 8 | +0.2 deg | -0.1 deg | -0.1 deg |
| 48 | 8 | -0.1 deg | -0.1 deg | -0.1 deg |

Peak load in that pose was 144 out of 1000 and temperature stayed between 33 and
43 C, so the servos were nowhere near torque-limited. The weakness is loop
stiffness, not available torque. `Max_Torque_Limit` is already 1000 on all five
body joints (only the gripper is deliberately capped at 500), so raising it
would have achieved nothing.

`P=32, I=8` removes the sag at unchanged load and temperature. That is the
project default now, in `configs/teleop_rir.yaml`:

```bash
uv run --frozen --extra hardware lerobot-teleoperate \
  --config_path=configs/teleop_rir.yaml
```

Higher `P` is worth trying, but only while watching for humming, oscillation or
heat.

One structural thing to keep in mind: the SE leader is a passive encoder device.
Ordinary teleoperation and demonstration recording work fine, but no code may
assume the leader can enable torque, drive itself to the follower pose, or do an
active handover. That only matters for the later recovery-data collection; it
changes nothing about the ID map above.

## 7. Moving from the laptop to the desktop

The laptop/WSL host is fine for ID assignment, assembly checks and slow
teleoperation. The live experiments should run as a single process on the RTX
desktop, with one operating system owning both robot adapters and the camera.
Splitting live USB ownership between Windows and WSL is not something I want to
debug mid-run.

When I move hosts: servo IDs stay as they are (they live in EEPROM); ports get
rediscovered rather than copied across as `/dev/ttyACM*` names; calibration
files get transferred privately and checksum-verified; `rir_follower_v1` and
`rir_leader_v1` stay; and the read-only diagnostics plus a conservative no-puck
teleoperation test get rerun before the task apparatus goes anywhere near it.

Bring-up counts as done when both assembled buses report IDs 1-6, both
calibration records are backed up, slow no-puck teleoperation is stable, and no
power, thermal, communication, motion-sign or cable-routing fault is left
outstanding.

## 8. What this particular pair does

Things that came out of bring-up and are not obvious from the vendor or LeRobot
documentation. Full measurements are in `hardware/private/bench_notes.md`.

- **The SE leader does not report temperature.** `Present_Temperature` reads `0`
  on all six leader servos, while the follower reports plausible values (31-43
  C). So the thermal stop condition cannot be checked in software on the
  leader; leader servo heat gets judged by hand.
- **The follower rests outside its own calibrated range.** Its natural slumped
  pose is around `shoulder_lift` -106 deg and `elbow_flex` +96 deg, at or past
  the calibrated limits. Any scripted "return to rest" therefore has to be
  allowed past the calibrated range, or the arm stops short and drops the rest
  of the way under gravity when torque is released.
- **Tracking lag dominates static sag.** Holding a loaded pose costs under 3 deg
  of error even at LeRobot's default gains, but following a moving target costs
  6-9 deg on the gravity-loaded joints. Motion-time error is not gravity droop.
- **The bus is not the bottleneck.** Reading six joints sustains 750-780 Hz with
  no read failures, so a control loop has plenty of headroom.
- **No camera under WSL.** `lerobot-find-cameras` reports zero devices. A webcam
  would need its own `usbipd` bind and attach, and capture through usbip adds
  latency I cannot easily characterize. Camera work belongs on the desktop.

## 9. Bench tools

`hardware/tools/` holds the read-only diagnostics, the motion demos and the 3D
visualization used above, with its own README for arguments, safety behavior and
the WSL rerun viewer workaround. The URDF and STL meshes those need are fetched
on demand and are not in version control:

```bash
bash hardware/tools/fetch_so101_meshes.sh
```
