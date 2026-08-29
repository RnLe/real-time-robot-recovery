# Bench tools

Small single-file utilities I used during SO-ARM101 SE bring-up. They are not
part of the `real_time_recovery` package. Run them directly against the locked
hardware environment:

```bash
uv run --frozen --extra hardware python hardware/tools/<script>.py <args>
```

`PORT` is always a `/dev/serial/by-id/...` alias. The two Bus Servo Adapter (A)
boards are physically identical, so the CH343 serial in that path is the only
reliable way to address one specific arm. The serial-to-arm mapping is in
`hardware/private/bench_notes.md`.

## Read-only

| script | what it does |
| --- | --- |
| `scan_bus.py PORT` | Probes every baud rate and lists responding motor IDs. A healthy arm answers with ids 1-6 at 1000000 baud. |
| `arm_status.py PORT` | Per-joint position, torque state, bus voltage, temperature. |
| `read_torque_cfg.py PORT` | Dumps torque limits, P/I/D gains, protection thresholds, present load and current. |

None of these write EEPROM, enable torque or command motion.

## Motion (the arm moves, supervise these)

| script | what it does |
| --- | --- |
| `choreography.py PORT CALIB OUT.json` | ~60 s keyframed sequence, recording measured positions for later rendering. |
| `gain_experiment.py PORT CALIB OUT.json` | Holds one loaded pose and sweeps P/I gains, measuring sag, load, current and temperature. Restores LeRobot's defaults on exit. |

Both seed `Goal_Position` from the present pose *before* enabling torque, so the
arm cannot snap to a stale register value, and both ramp back to the starting
pose before releasing torque. `CALIB` is the follower's calibration JSON, e.g.
`~/.cache/huggingface/lerobot/calibration/robots/so_follower/rir_follower_v1.json`.

The arm goes limp when these exit. Do not leave it raised.

## 3D visualization

Fetch the URDF and meshes once per machine (~15 MB, gitignored):

```bash
bash hardware/tools/fetch_so101_meshes.sh
```

| script | what it does |
| --- | --- |
| `so101_viz.py` | Library: parses the URDF and logs forward kinematics to rerun. Not run directly. |
| `capture_calibrated.py PORT URDF OUT.rrd [secs] [arm_id]` | Records the calibrated leader while you move it by hand, then renders it. |
| `render_from_json.py IN.json URDF OUT.rrd [signs]` | Re-renders a saved capture with no hardware attached. |

Forward kinematics is computed straight from the URDF with numpy. LeRobot's own
`RobotKinematics` would need `placo`, which is not in the locked environment.

`signs` is an optional JSON object mapping joint names to `1` or `-1`, for
flipping a joint that renders mirrored, e.g. `'{"wrist_roll": -1}'`.

### Viewing under WSL

The native rerun viewer does not work under WSLg: the default adapter cannot
draw to `R32Float`, and forcing software Vulkan (lavapipe) then hits a
`max_color_attachments` limit. Use the web viewer and open it from Windows
instead:

```bash
uv run --frozen --extra hardware rerun --web-viewer --web-viewer-port 9090 --port 9877 OUT.rrd
```

Then browse to
`http://localhost:9090?url=rerun%2Bhttp%3A%2F%2Flocalhost%3A9877%2Fproxy`. The
`?url=` parameter is not optional; without it the viewer loads empty.
