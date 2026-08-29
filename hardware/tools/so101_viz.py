"""SO-101 forward kinematics from the real URDF, logged to rerun. numpy only."""
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import rerun as rr


def _rpy(rpy):
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ])


def _vec(node, attr, default=(0.0, 0.0, 0.0)):
    if node is None or node.get(attr) is None:
        return np.array(default, float)
    return np.array([float(v) for v in node.get(attr).split()], float)


class URDF:
    def __init__(self, path):
        self.dir = Path(path).parent
        root = ET.parse(path).getroot()
        self.joints, self.children, self.visuals = {}, {}, {}
        child_links = set()
        for j in root.findall("joint"):
            o = j.find("origin")
            self.joints[j.get("name")] = dict(
                type=j.get("type"),
                parent=j.find("parent").get("link"),
                child=j.find("child").get("link"),
                xyz=_vec(o, "xyz"), rpy=_vec(o, "rpy"), axis=_vec(j.find("axis"), "xyz"),
            )
            self.children.setdefault(j.find("parent").get("link"), []).append(j.get("name"))
            child_links.add(j.find("child").get("link"))
        self.root = next(lk.get("name") for lk in root.findall("link")
                         if lk.get("name") not in child_links)
        for lk in root.findall("link"):
            vs = []
            for v in lk.findall("visual"):
                mesh = v.find("geometry/mesh")
                if mesh is None:
                    continue
                o = v.find("origin")
                vs.append((self.dir / mesh.get("filename"), _vec(o, "xyz"), _vec(o, "rpy")))
            self.visuals[lk.get("name")] = vs

    def paths(self):
        out, stack = {self.root: self.root}, [self.root]
        while stack:
            link = stack.pop()
            for jn in self.children.get(link, []):
                c = self.joints[jn]["child"]
                out[c] = f"{out[link]}/{c}"
                stack.append(c)
        return out


def log_static(urdf, prefix="robot"):
    paths = urdf.paths()
    for link, epath in paths.items():
        for i, (mesh, xyz, rpy) in enumerate(urdf.visuals.get(link, [])):
            if not mesh.exists():
                continue
            ent = f"{prefix}/{epath}/visual_{i}"
            rr.log(ent, rr.Transform3D(translation=xyz, mat3x3=_rpy(rpy)), static=True)
            rr.log(ent, rr.Asset3D(path=mesh), static=True)
    return paths


def log_pose(urdf, paths, angles_rad, prefix="robot"):
    for jn, j in urdf.joints.items():
        R = _rpy(j["rpy"])
        if j["type"] == "revolute":
            q = angles_rad.get(jn, 0.0)
            ax = j["axis"] / np.linalg.norm(j["axis"])
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = R @ (np.eye(3) + np.sin(q) * K + (1 - np.cos(q)) * K @ K)
        rr.log(f"{prefix}/{paths[j['child']]}",
               rr.Transform3D(translation=j["xyz"], mat3x3=R))
