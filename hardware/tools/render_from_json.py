"""Re-render a saved capture. No hardware needed."""
import json
import pathlib
import sys

import numpy as np
import rerun as rr

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from so101_viz import URDF, log_pose, log_static

JSON_PATH, URDF_PATH, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SIGNS = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
LOG_HZ = 50.0

with open(JSON_PATH) as fh:
    d = json.load(fh)
ts = np.array(d["t"]); deg = {n: np.array(v, float) for n, v in d["deg"].items()}
u = URDF(URDF_PATH)

# gripper comes back normalized 0-100, not degrees. Map it onto the URDF
# gripper joint limits (-10 deg .. 100 deg, in radians).
lo, hi = -0.174533, 1.74533


def angles(k):
    out = {}
    for n, v in deg.items():
        if n == "gripper":
            out[n] = lo + (np.clip(v[k], 0, 100) / 100.0) * (hi - lo)
        else:
            out[n] = np.radians(v[k])
        out[n] *= SIGNS.get(n, 1.0)
    return out


rr.init("so101_leader_calibrated"); rr.save(OUT)
paths = log_static(u)
step = max(1, int(round(len(ts) / (LOG_HZ * (ts[-1] - ts[0])))))
for k in range(0, len(ts), step):
    rr.set_time("t", duration=float(ts[k]))
    log_pose(u, paths, angles(k))
    for n in deg:
        rr.log(f"joint/{n}", rr.Scalars(float(deg[n][k])))
print(f"rendered {len(range(0,len(ts),step))} frames -> {OUT}")
