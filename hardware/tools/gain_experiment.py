"""Measure gravity sag, load and current at a demanding pose across P/I gains.

Holds one loaded pose for the whole run (which also exercises the servos'
overload protection), stepping through gain settings and measuring steady-state
tracking error at each. EEPROM is unlocked in place so torque is never dropped
while the arm is raised.
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
TEMP_ABORT, ERR_ABORT = 55, 45.0
SETTLE, MEASURE = 3.0, 5.0
CONFIGS = [(16, 0), (32, 0), (32, 8), (48, 8), (32, 16)]
POSE = dict(shoulder_pan=0, shoulder_lift=30, elbow_flex=-50, wrist_flex=10, wrist_roll=0, gripper=50)
LOADED = ["shoulder_lift", "elbow_flex", "wrist_flex"]

raw = json.loads(CAL.read_text())
motors = {n: Motor(v["id"], "sts3215",
                   MotorNormMode.RANGE_0_100 if n == "gripper" else MotorNormMode.DEGREES)
          for n, v in raw.items()}
bus = FeetechMotorsBus(port=PORT, motors=motors,
                       calibration={n: MotorCalibration(**v) for n, v in raw.items()})
bus.connect(handshake=True)
lim = {n: ((5.0, 95.0) if n == "gripper" else
           ((v["range_min"] - 2048) * CTS2DEG + MARGIN, (v["range_max"] - 2048) * CTS2DEG - MARGIN))
       for n, v in raw.items()}
pose = {n: float(np.clip(v, *lim[n])) for n, v in POSE.items()}

def set_gains(p, i):
    for n in motors:
        bus.write("Lock", n, 0)
        bus.write("P_Coefficient", n, p)
        bus.write("I_Coefficient", n, i)
        bus.write("Lock", n, 1)
    got_p = bus.sync_read("P_Coefficient", normalize=False)
    got_i = bus.sync_read("I_Coefficient", normalize=False)
    ok = all(got_p[n] == p and got_i[n] == i for n in motors)
    print(f"    gains P={p} I={i} -> written {'OK' if ok else 'MISMATCH ' + str((got_p, got_i))}")
    return ok

bus.disable_torque()
for n in motors:
    bus.write("Operating_Mode", n, 0); bus.write("D_Coefficient", n, 32)
q0 = bus.sync_read("Present_Position", num_retry=2)
print("rest pose:", {n: round(v, 1) for n, v in q0.items()})
bus.sync_write("Goal_Position", q0); time.sleep(0.2)
bus.enable_torque()

series = []
t_start = time.perf_counter()
prev = dict(q0)

def ramp(src, dst, secs):
    global prev
    n_steps = max(1, int(secs * FPS))
    for k in range(n_steps):
        a = (lambda x: x * x * (3 - 2 * x))((k + 1) / n_steps)
        w = {n: src[n] + a * (dst[n] - src[n]) for n in motors}
        w = {n: float(np.clip(w[n], prev[n] - STEP_CAP, prev[n] + STEP_CAP)) for n in motors}
        bus.sync_write("Goal_Position", w); prev = w
        time.sleep(1 / FPS)

def sample(tag, p, i):
    now = bus.sync_read("Present_Position", num_retry=2)
    load = bus.sync_read("Present_Load", normalize=False, num_retry=2)
    cur = bus.sync_read("Present_Current", normalize=False, num_retry=2)
    tmp = bus.sync_read("Present_Temperature", normalize=False, num_retry=2)
    row = dict(t=time.perf_counter() - t_start, tag=tag, P=p, I=i,
               pos={n: now[n] for n in motors}, load={n: load[n] for n in motors},
               cur={n: cur[n] for n in motors}, temp={n: tmp[n] for n in motors})
    series.append(row)
    return now, tmp

results = []
try:
    print("\napproaching test pose...", flush=True)
    ramp(q0, {**q0, **pose}, 6.0)
    for (p, i) in CONFIGS:
        print(f"\n  P={p} I={i}", flush=True)
        set_gains(p, i)
        t_cfg = time.perf_counter()
        while time.perf_counter() - t_cfg < SETTLE:
            bus.sync_write("Goal_Position", pose); sample("settle", p, i); time.sleep(1 / FPS)
        errs = {n: [] for n in motors}; loads = {n: [] for n in motors}; curs = {n: [] for n in motors}
        t_m = time.perf_counter()
        while time.perf_counter() - t_m < MEASURE:
            bus.sync_write("Goal_Position", pose)
            now, tmp = sample("measure", p, i)
            for n in motors:
                errs[n].append(pose[n] - now[n])
                loads[n].append(series[-1]["load"][n]); curs[n].append(series[-1]["cur"][n])
            if max(tmp.values()) >= TEMP_ABORT:
                raise RuntimeError(f"temperature abort: {tmp}")
            if max(abs(errs[n][-1]) for n in LOADED) > ERR_ABORT:
                raise RuntimeError(f"tracking error abort at P={p} I={i}")
            time.sleep(1 / FPS)
        results.append(dict(P=p, I=i,
                            err={n: float(np.mean(errs[n])) for n in motors},
                            load={n: float(np.mean(loads[n])) for n in motors},
                            cur={n: float(np.mean(curs[n])) for n in motors},
                            temp=dict(tmp)))
        print("    sag: " + "  ".join(f"{n}={np.mean(errs[n]):+.1f}" for n in LOADED)
              + f"   maxtemp={max(tmp.values())}C")
finally:
    print("\nreturning to rest and restoring LeRobot defaults...", flush=True)
    try:
        ramp(prev, q0, 6.0); time.sleep(0.3)
    except Exception as e:
        print("  ramp-back failed:", e)
    try:
        set_gains(16, 0)
    except Exception as e:
        print("  gain restore failed:", e)
    bus.disable_torque(); bus.disconnect()
    print("torque OFF")

with open(OUT, "w") as fh:
    json.dump(dict(results=results, series=series), fh)
print(f"\n{'P':>4}{'I':>4} | " + "".join(f"{n[:12]:>14}" for n in LOADED) + f"{'max temp':>10}")
for r in results:
    print(f"{r['P']:>4}{r['I']:>4} | "
          + "".join(f"{r['err'][n]:>+14.1f}" for n in LOADED)
          + f"{max(r['temp'].values()):>10}")
print(f"\nsaved {OUT}")
