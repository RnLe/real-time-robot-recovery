"""~60s choreography for the SO-101 follower, with smooth keyframe easing.

Absolute keyframe poses in calibrated degrees (gripper 0-100). Every keyframe is
clamped into the calibrated range with margin; motion between keyframes uses a
smoothstep ease so acceleration is continuous. Goal_Position is seeded to the
present pose before torque is enabled. Ends back at the starting pose.

Records measured joint positions to JSON for 3D rendering afterwards.
"""
import json
import pathlib
import sys
import time

import numpy as np
from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

PORT, CAL, OUT = sys.argv[1], pathlib.Path(sys.argv[2]).expanduser(), sys.argv[3]
FPS, STEP_CAP, MARGIN = 30.0, 3.0, 15.0
CTS2DEG = 360 / 4096
BODY = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]

# (seconds, {joint: target}) - unspecified joints hold their previous value
SCRIPT = [
    (6.0, dict(shoulder_pan=0, shoulder_lift=0, elbow_flex=0, wrist_flex=0, wrist_roll=0, gripper=50)),
    (3.5, dict(shoulder_lift=-30, elbow_flex=40, wrist_flex=-20)),          # bow
    (3.5, dict(shoulder_lift=0, elbow_flex=0, wrist_flex=0)),               # rise
    (5.0, dict(shoulder_pan=-70, wrist_roll=-40)),                          # look left
    (6.0, dict(shoulder_pan=70, wrist_roll=40)),                            # look right
    (3.5, dict(shoulder_pan=0, wrist_roll=0)),                              # center
    (5.0, dict(shoulder_lift=30, elbow_flex=-50, wrist_flex=10, gripper=90)),  # reach + open
    (2.5, dict(gripper=10)),                                                # grasp
    (4.0, dict(shoulder_lift=50, wrist_roll=90)),                           # lift + roll
    (4.0, dict(wrist_roll=-90)),                                            # roll back
    (2.5, dict(wrist_roll=0, gripper=90)),                                  # release
    (2.0, dict(wrist_flex=-35)),                                            # wave
    (1.5, dict(wrist_flex=35)),
    (1.5, dict(wrist_flex=-35)),
    (2.0, dict(wrist_flex=0, gripper=50)),
    (7.0, None),                                                            # None = return to start
]

raw = json.loads(CAL.read_text())
calib = {n: MotorCalibration(**v) for n, v in raw.items()}
motors = {n: Motor(v["id"], "sts3215",
                   MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.DEGREES)
          for n, v in raw.items()}
bus = FeetechMotorsBus(port=PORT, motors=motors, calibration=calib)
bus.connect(handshake=True)

lim = {}
for n, v in raw.items():
    lim[n] = (5.0, 95.0) if n == "gripper" else (
        (v["range_min"] - 2048) * CTS2DEG + MARGIN, (v["range_max"] - 2048) * CTS2DEG - MARGIN)

bus.disable_torque()
for n in motors:
    bus.write("Operating_Mode", n, 0)
    bus.write("P_Coefficient", n, 16); bus.write("I_Coefficient", n, 0); bus.write("D_Coefficient", n, 32)
bus.write("Max_Torque_Limit", "gripper", 500)
bus.write("Protection_Current", "gripper", 250)
bus.write("Overload_Torque", "gripper", 25)

q0 = bus.sync_read("Present_Position", num_retry=2)
print("start pose:", {n: round(v, 1) for n, v in q0.items()})
print("safe band :", {n: (round(a), round(b)) for n, (a, b) in lim.items()})
bus.sync_write("Goal_Position", q0)
time.sleep(0.2)
bus.enable_torque()
print(f"\ntorque ON. Choreography: {sum(d for d, _ in SCRIPT):.0f}s\n", flush=True)

def smooth(a):
    return a * a * (3 - 2 * a)

cur = dict(q0)
prev = dict(q0)
log = {n: [] for n in motors}; ts = []
t_start = time.perf_counter()
try:
    for idx, (dur, kf) in enumerate(SCRIPT):
        if kf is None:
            # Returning to the pose the arm was physically resting in. That pose
            # is safe by definition and may sit outside the padded safe band -
            # this follower rests past its own calibrated range on shoulder_lift
            # and elbow_flex - so it must NOT be clamped, or the arm stops short
            # of home and settles the remainder under gravity when torque drops.
            target = dict(q0)
        else:
            target = {**cur, **{k: float(v) for k, v in kf.items()}}
            target = {n: float(np.clip(v, *lim[n])) for n, v in target.items()}
        src = dict(cur)
        label = "return to start" if kf is None else ", ".join(f"{k}->{v:g}" for k, v in kf.items())
        print(f"  [{idx+1:2d}/{len(SCRIPT)}] {dur:4.1f}s  {label}", flush=True)
        n_steps = max(1, int(dur * FPS))
        for k in range(n_steps):
            a = smooth((k + 1) / n_steps)
            want = {n: src[n] + a * (target[n] - src[n]) for n in motors}
            want = {n: float(np.clip(want[n], prev[n] - STEP_CAP, prev[n] + STEP_CAP)) for n in motors}
            bus.sync_write("Goal_Position", want)
            prev = want
            now = bus.sync_read("Present_Position", num_retry=2)
            ts.append(time.perf_counter() - t_start)
            for n in motors: log[n].append(now[n])
            time.sleep(1 / FPS)
        cur = target
    time.sleep(0.5)
finally:
    end = bus.sync_read("Present_Position", num_retry=2)
    bus.disable_torque()
    bus.disconnect()
    print("\ntorque OFF - arm limp")

with open(OUT, "w") as fh:
    json.dump({"t": ts, "deg": log}, fh)
print(f"\nran {ts[-1]:.1f}s, {len(ts)} samples -> {OUT}")
print(f"\n{'joint':<15}{'start':>8}{'end':>8}{'min':>8}{'max':>8}")
for n in motors:
    a = np.array(log[n])
    print(f"{n:<15}{q0[n]:>8.1f}{end[n]:>8.1f}{a.min():>8.1f}{a.max():>8.1f}")
