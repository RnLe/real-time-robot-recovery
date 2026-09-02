# Recover in Real Time

A small physical robot-learning study on a Waveshare SO-ARM101 leader-follower
kit. The task I am building toward: push a passive puck through a gate while a
controlled lateral disturbance and a controlled inference delay produce failures
that are still recoverable.

> **Status:** hardware bring-up is finished. Both arms are assembled, calibrated
> and running stable leader-follower teleoperation with tuned position gains.
> The camera and the physical task are not set up yet. There are no trained
> policies, no results and no experimental claims here.

## What the study is meant to answer

Two practical bottlenecks in imitation learning, both of which are cheap to
assert and awkward to measure:

- Given a fixed amount of demonstration time, is it better spent collecting
  deliberately disturbed recovery states than more nominal behavior?
- Does timestamp-aware asynchronous action-chunk execution stay useful and
  smooth once policy inference starts finishing late?

The plan is to cross these two choices on one tabletop task, with the same
physical disturbance, the same delay traces and the same task-level outcomes on
both sides of each comparison. Matched data budgets and visible failure analysis
matter more here than a new learning algorithm. There isn't one.

## Repository layout

```text
src/real_time_recovery/   rrt CLI: read-only environment and manifest diagnostics
configs/                  hardware manifest, teleoperation defaults
hardware/                 bring-up log and bench tools
tests/                    unit tests for the manifest schema and diagnostics
environment/              provenance of the pinned LeRobot build
```

## Environment

Software is pinned to [LeRobot v0.6.1](https://github.com/huggingface/lerobot/releases/tag/v0.6.1)
at commit `7e241bd630a3719a56157a497ce5d08f244784f1`, installed from the
[published PyPI wheel](https://pypi.org/project/lerobot/0.6.1/); the hash is
recorded in [environment/lerobot_commit.txt](environment/lerobot_commit.txt).
Python is 3.12 and the environment is managed with uv; I developed against
0.12.6, and `uv.lock` is what actually pins the dependency set.

```bash
curl -LsSf https://astral.sh/uv/0.12.6/install.sh | sh
uv sync --frozen --extra hardware
uv run --frozen --extra hardware rrt doctor
```

If the installer asks for a new shell, reopen the terminal first. `rrt doctor`
checks the software versions, serial-device visibility, the hardware manifest
and CUDA availability; `--json` gives the same report as JSON. It never writes
servo memory and never commands motion.

Tests and lint need only the default environment:

```bash
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen pytest
```

## Bring-up

The procedure I followed is in the
[SO-ARM101 SE bring-up log](hardware/so101_se_bringup.md): usbipd attachment
under WSL, the six persistent bus IDs per arm, assembly and daisy-chaining,
calibration under permanent LeRobot names, and a conservative first
teleoperation test. Read the power checks at the top before connecting a servo
supply; the Bus Servo Adapter (A) passes its input voltage straight through to
the servo bus.

## Teleoperation

With both adapters attached, both arms run from one checked-in config:

```bash
uv run --frozen --extra hardware lerobot-teleoperate \
  --config_path=configs/teleop_rir.yaml
```

That file pins both `/dev/serial/by-id` ports, both calibration ids, a
conservative `max_relative_target`, and position gains of `P=32, I=8`. LeRobot's
defaults of `P=16, I=0` leave the arm noticeably compliant under leverage; the
values here come from a measured sag sweep, tabulated in the
[bring-up log](hardware/so101_se_bringup.md#position-loop-gains). Clamp both
bases and match the two arms' poses by hand before starting.

Read-only diagnostics, supervised motion demos and a rerun-based 3D
visualization live in [hardware/tools/](hardware/tools/).

The laptop/WSL install was the bring-up host. The RTX desktop is meant to own
the robot buses, the camera and the inference process during the experiments.
Servo IDs survive that move because they sit in each servo's EEPROM; USB device
paths and LeRobot calibration files do not, and have to be moved deliberately
with checksums recorded.

## Where this is going

- [x] Labels, supplies, controller settings and servo IDs verified. Both buses
      report IDs 1-6 at 1 Mbaud.
- [x] Assembled, clamped, calibrated as `rir_follower_v1` and `rir_leader_v1`,
      backed up with checksums. Slow teleoperation is stable.
- [ ] Camera, then characterize the physical task. No camera is visible under
      WSL, so this is the natural point to move to the desktop host.
- [ ] Nominal demonstrations, then the recovery-data and delayed-execution
      experiments.

Datasets, calibration backups, label photographs, checkpoints and run artifacts
stay out of version control. Source and analysis get added as the corresponding
hardware gates are passed, not before.
