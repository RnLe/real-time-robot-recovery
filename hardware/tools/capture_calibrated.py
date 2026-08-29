"""Capture the CALIBRATED leader arm and render it in 3D.

Uses LeRobot's own SO101Leader class so joint angles come back already
normalized to degrees through the saved calibration - no hand-rolled offsets.
Read-only: the leader is passive and torque is never enabled.
"""
import json
import pathlib
import sys
import time

import numpy as np
import rerun as rr

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from so101_viz import URDF, log_pose, log_static

PORT, URDF_PATH, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
DURATION = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
ARM_ID = sys.argv[5] if len(sys.argv) > 5 else "rir_leader_v1"
SIGNS = json.loads(sys.argv[6]) if len(sys.argv) > 6 else {}
TRIG_DEG, WAIT, LOG_HZ = 3.0, 90.0, 50.0

leader = SO101Leader(SO101LeaderConfig(port=PORT, id=ARM_ID))
leader.connect(calibrate=False)
if not leader.calibration:
    sys.exit(f"No calibration loaded for id '{ARM_ID}'.")
print(f"Connected. Calibration '{ARM_ID}' loaded, is_calibrated={leader.is_calibrated}")

names = list(leader.bus.motors)
def read():
    return {k.removesuffix(".pos"): v for k, v in leader.get_action().items()}


base = read()
print(f"Armed. Move any joint to start (waiting up to {WAIT:.0f}s)...", flush=True)
t0 = time.perf_counter()
while max(abs(read()[n] - base[n]) for n in names) < TRIG_DEG:
    if time.perf_counter() - t0 > WAIT:
        print("No movement detected."); leader.disconnect(); sys.exit(2)
print(f"Recording {DURATION:.0f}s - move every joint.", flush=True)

samples, ts = {n: [] for n in names}, []
t0 = time.perf_counter()
while (t := time.perf_counter() - t0) < DURATION:
    c = read()
    for n in names: samples[n].append(c[n])
    ts.append(t)
leader.disconnect()

ts = np.array(ts)
deg = {n: np.array(v, float) for n, v in samples.items()}
with open(OUT + ".json", "w") as fh:
    json.dump({"t": ts.tolist(), "deg": {n: v.tolist() for n, v in deg.items()}}, fh)

u = URDF(URDF_PATH)
rr.init("so101_leader_calibrated"); rr.save(OUT)
paths = log_static(u)
step = max(1, int(round(len(ts) / (LOG_HZ * DURATION))))
for k in range(0, len(ts), step):
    rr.set_time("t", duration=float(ts[k]))
    log_pose(u, paths, {n: np.radians(deg[n][k]) * SIGNS.get(n, 1.0) for n in names})
    for n in names:
        rr.log(f"joint/{n}", rr.Scalars(float(deg[n][k])))

print(f"\n{len(ts)} samples, {len(ts)/(ts[-1]-ts[0]):.0f} Hz\n")
print(f"{'joint':<15}{'min deg':>9}{'max deg':>9}{'span':>8}")
for n in names:
    print(f"{n:<15}{deg[n].min():>9.1f}{deg[n].max():>9.1f}{np.ptp(deg[n]):>8.1f}")
print(f"\nSaved: {OUT}")
