#!/usr/bin/env python3
"""CBD Adapter -- Isaac Sim / GR00T, Unitree G1 embodiment.

`adapters/` role of the Common Behavior Data project. Target: the **Unitree G1**
as NVIDIA GR00T drives it -- a 43-DoF joint vector (29 body + two Dex3
three-finger hands) plus a USD stage that replays it in Isaac Sim.

This reads nothing but canonical Common Behavior Data -- `04_behavior_dataset/`,
unpacked or still inside the generator's `cbd_dataset.zip` -- and *retargets*
it. That is the difference from the notebook adapters, which measure the
subject and animate a figure built to those measurements: a G1 is a machine with
fixed link lengths and hard joint limits, so the human motion has to be solved
into the robot's joint space, clipped where the robot cannot follow, and the
shortfall reported.

What it writes, under <output>/06_groot_g1/:

    g1_robot.usda           the robot -- one Xform per G1 link, at the URDF origins
    scene.usda              the set   -- floor, backdrop, chair, table, lights, cameras
    motion.usda             the motion -- time samples only; sublayers the two above
    motion.npz              joint angles, root pose and link frames as arrays
    g1_joint_trajectory.csv the 43 joint angles per frame, with limit-clip flags
    groot_lerobot/          a GR00T-LeRobot v2.1 dataset (the Arena G1 modality)
    adapter_report.json     retarget residuals, clipping, and what it could not do
    README_GROOT_G1.md

Model, set and motion are three separate layers (rule 3). `motion.usda` is the
stage to open; nothing in it is Isaac-specific.

Coordinate conversion happens once, at this adapter's boundary (rule 2).
Canonical CBD is Y-up, right-handed, subject facing +Z. The G1's own frame is
URDF/ROS -- X forward, Y left, Z up -- so canonical maps to it by the cyclic
relabelling (x, y, z) -> (z, x, y), a proper rotation. The USD stage is Z-up
with the subject facing -Y, which the robot root carries as a single -90 deg
yaw.

What this adapter is *not*: it does not run a GR00T policy and does not claim
the motion came from one. It writes the two things a GR00T G1 stack consumes --
a joint-space trajectory and a GR00T-LeRobot dataset in the Isaac Lab Arena G1
layout -- from human behavior data. See README.md.

Usage:
    python cbd_adapter_groot_g1.py --dataset <dir containing 04_behavior_dataset>
    python cbd_adapter_groot_g1.py --dataset cbd_dataset.zip     # straight from the generator
    python cbd_adapter_groot_g1.py --dataset ... --output <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KINEMATICS = HERE / "g1_kinematics.json"

# --------------------------------------------------------------------------
# rotation helpers -- quaternions are wxyz, matrices are 3x3, both float64
# --------------------------------------------------------------------------


def q_mul(a, b):
    a = np.atleast_2d(a)
    b = np.atleast_2d(b)
    aw, ax, ay, az = a.T
    bw, bx, by, bz = b.T
    return np.column_stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw])


def q_normalize(q):
    q = np.atleast_2d(q)
    return q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)


def q_rot(q, v):
    q = np.atleast_2d(q)
    v = np.asarray(v, dtype=float)
    if v.ndim == 1:
        v = np.tile(v, (len(q), 1))
    u = q[:, 1:]
    t = 2.0 * np.cross(u, v)
    return v + q[:, :1] * t + np.cross(u, t)


def q_to_mat(q):
    """(N,4) wxyz -> (N,3,3)."""
    q = q_normalize(np.atleast_2d(q))
    w, x, y, z = q.T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1),
    ], axis=1)


def mat_to_q(m):
    """(3,3) -> (4,) wxyz. The branch-free trace form is not stable near 180 deg."""
    m = np.asarray(m, float)
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        return np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s,
                         (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(max(1e-12, 1.0 + m[i, i] - m[j, j] - m[k, k])) * 2.0
    q = np.zeros(4)
    q[0] = (m[k, j] - m[j, k]) / s
    q[1 + i] = 0.25 * s
    q[1 + j] = (m[j, i] + m[i, j]) / s
    q[1 + k] = (m[k, i] + m[i, k]) / s
    return q


def rpy_mat(rpy):
    """URDF fixed-axis roll-pitch-yaw: Rz(yaw) Ry(pitch) Rx(roll)."""
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = (math.cos(r), math.sin(r), math.cos(p),
                              math.sin(p), math.cos(y), math.sin(y))
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr]])


def axis_mat(axis, angle):
    """Rodrigues, for a URDF joint axis (always a unit basis vector on the G1)."""
    x, y, z = axis
    c, s, v = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return np.array([
        [c + x * x * v, x * y * v - z * s, x * z * v + y * s],
        [y * x * v + z * s, c + y * y * v, y * z * v - x * s],
        [z * x * v - y * s, z * y * v + x * s, c + z * z * v]])


def unit(v, axis=-1):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=axis, keepdims=True) + 1e-12)


def angle_between_deg(a, b):
    return np.degrees(np.arccos(np.clip(np.sum(unit(a) * unit(b), axis=-1), -1.0, 1.0)))


# --------------------------------------------------------------------------
# the adapter boundary -- three frames, two conversions
# --------------------------------------------------------------------------
# canonical CBD : Y up, X = subject's left, Z = subject's facing
# G1 / URDF     : Z up, Y = robot's left, X = robot's facing
# USD stage     : Z up, subject faces -Y (right-handed)
#
# canonical -> G1 is the cyclic relabelling (x, y, z) -> (z, x, y). It is a
# permutation with determinant +1, so it is a rotation and not a handedness
# flip: the same 120 deg turn about (1,1,1) that maps the canonical rest pose
# onto the G1's zero pose axes.
P_C2R = np.array([[0.0, 0.0, 1.0],
                  [1.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0]])
# G1 -> USD stage: -90 deg about Z, so the robot's +X faces the stage's -Y and
# the camera on the -Y side looks at its front.
Q_R2U = np.array([math.cos(-math.pi / 4), 0.0, 0.0, math.sin(-math.pi / 4)])


def vec_c_to_r(v):
    v = np.atleast_2d(np.asarray(v, float))
    return np.column_stack([v[:, 2], v[:, 0], v[:, 1]])


def mat_c_to_r(m):
    """A canonical rotation, expressed in G1 axes."""
    return P_C2R @ m @ P_C2R.T


def vec_r_to_usd(v):
    v = np.atleast_2d(np.asarray(v, float))
    return np.column_stack([v[:, 1], -v[:, 0], v[:, 2]])


# --------------------------------------------------------------------------
# the human rig -- the same canonical bone tree every CBD adapter reads
# --------------------------------------------------------------------------
BONE_TREE = [
    ("hips",            None,             lambda d: (0.0, 0.0, 0.0)),
    ("spine",           "hips",           lambda d: (0.0, d["spine1"], 0.0)),
    ("chest",           "spine",          lambda d: (0.0, d["spine2"], 0.0)),
    ("neck",            "chest",          lambda d: (0.0, d["neck"], 0.0)),
    ("head",            "neck",           lambda d: (0.0, d["head_off"], 0.0)),
    ("left_shoulder",   "chest",          lambda d: (d["sh_half"] * 0.45, 0.0, 0.0)),
    ("left_upper_arm",  "left_shoulder",  lambda d: (d["sh_half"] * 0.55, 0.0, 0.0)),
    ("left_lower_arm",  "left_upper_arm", lambda d: (d["upper_arm"], 0.0, 0.0)),
    ("left_hand",       "left_lower_arm", lambda d: (d["lower_arm"], 0.0, 0.0)),
    ("right_shoulder",  "chest",          lambda d: (-d["sh_half"] * 0.45, 0.0, 0.0)),
    ("right_upper_arm", "right_shoulder", lambda d: (-d["sh_half"] * 0.55, 0.0, 0.0)),
    ("right_lower_arm", "right_upper_arm", lambda d: (-d["upper_arm"], 0.0, 0.0)),
    ("right_hand",      "right_lower_arm", lambda d: (-d["lower_arm"], 0.0, 0.0)),
    ("left_upper_leg",  "hips",           lambda d: (d["hip_half"], 0.0, 0.0)),
    ("left_lower_leg",  "left_upper_leg", lambda d: (0.0, -d["upper_leg"], 0.0)),
    ("left_foot",       "left_lower_leg", lambda d: (0.0, -d["lower_leg"], 0.0)),
    ("right_upper_leg", "hips",           lambda d: (-d["hip_half"], 0.0, 0.0)),
    ("right_lower_leg", "right_upper_leg", lambda d: (0.0, -d["upper_leg"], 0.0)),
    ("right_foot",      "right_lower_leg", lambda d: (0.0, -d["lower_leg"], 0.0)),
]

FINGER_ORDER_DEFAULT = ["thumb", "index", "middle", "ring", "little"]

LM = {"nose": 0, "l_ear": 7, "r_ear": 8, "l_sh": 11, "r_sh": 12,
      "l_elb": 13, "r_elb": 14, "l_wri": 15, "r_wri": 16,
      "l_idx": 19, "r_idx": 20, "l_hip": 23, "r_hip": 24,
      "l_knee": 25, "r_knee": 26, "l_ank": 27, "r_ank": 28,
      "l_heel": 29, "r_heel": 30, "l_toe": 31, "r_toe": 32}


# --------------------------------------------------------------------------
# reading canonical CBD -- from a directory or straight from the generator zip
# --------------------------------------------------------------------------


def open_dataset(spec: str, workdir: str | None = None):
    """Resolve `spec` to a 04_behavior_dataset/ directory.

    `spec` may be that directory, any directory above it, or the generator's
    `cbd_dataset.zip`. The zip mirrors the generator's runtime layout
    (`config.json`, `source/`, `04_behavior_dataset/`), so unpacking it and
    then looking for the dataset is the whole of it -- no separate code path.
    """
    path = Path(spec).expanduser().resolve()
    unpacked_from = None
    if path.is_file() and zipfile.is_zipfile(path):
        target = Path(workdir).expanduser().resolve() if workdir \
            else path.parent / f"{path.stem}_unpacked"
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                # a zip entry may not escape the directory it unpacks into
                dest = (target / member).resolve()
                if not str(dest).startswith(str(target)):
                    raise SystemExit(f"refusing to unpack {member} outside {target}")
            archive.extractall(target)
        unpacked_from, path = path, target
        print(f"unpacked {unpacked_from.name} -> {target}")
    if (path / "manifest.json").exists() and path.name == "04_behavior_dataset":
        return path, unpacked_from
    direct = path / "04_behavior_dataset/manifest.json"
    if direct.exists():
        return direct.parent, unpacked_from
    hit = next(iter(sorted(path.glob("**/04_behavior_dataset/manifest.json"))), None)
    if hit is None:
        raise SystemExit(f"no 04_behavior_dataset/ found under {path}")
    return hit.parent, unpacked_from


class Cbd:
    """Everything this adapter reads, and nothing else."""

    def __init__(self, dataset_dir: Path):
        self.dir = Path(dataset_dir)
        self.manifest = json.loads((self.dir / "manifest.json").read_text("utf-8"))
        self.summary = json.loads(
            (self.dir / "behavior_summary.json").read_text("utf-8"))
        self.frames = [json.loads(l) for l
                       in (self.dir / "timeline/frames.jsonl").read_text("utf-8").splitlines()
                       if l.strip()]
        if not self.frames:
            raise SystemExit("timeline/frames.jsonl is empty")
        self.n = len(self.frames)
        self.fps = float(self.manifest["fps"])
        self.timestamps = np.array([f["timestamp_sec"] for f in self.frames], float)
        self.bone_order = (self.manifest.get("bone_order")
                           or list(self.frames[0]["human"]["bone_rotations_xyzw"]))
        self.finger_order = self.manifest.get("finger_order", FINGER_ORDER_DEFAULT)
        self.rot = {}
        for bone in self.bone_order:
            xyzw = np.array([f["human"]["bone_rotations_xyzw"][bone]
                             for f in self.frames], float)
            self.rot[bone] = q_normalize(np.column_stack(
                [xyzw[:, 3], xyzw[:, 0], xyzw[:, 1], xyzw[:, 2]]))
        self.hips_pos = np.array([f["human"]["hips_position"] for f in self.frames], float)
        self.pose = np.array([f["human"]["pose_canonical"] for f in self.frames], float)
        self.phase = [f.get("phase") or {} for f in self.frames]
        self.captions = [f.get("caption") or {} for f in self.frames]
        self.notes = []          # rule 5: filled / interpolated / approximated
        self.unrepresented = []  # rule 5: could not be represented at all

        self.curls, self.curls_filled = {}, {}
        for side in ("left", "right"):
            raw = [f["human"].get("finger_curls_rad", {}).get(side)
                   for f in self.frames]
            present = np.array([r is not None for r in raw])
            values = np.zeros((self.n, len(self.finger_order)))
            if present.any():
                valid = np.where(present)[0]
                obs = np.array([raw[k] for k in valid], float)
                # Interpolate across a gap, hold at the ends. Nearest-neighbour
                # fill puts the whole of a gap's change at one frame in its
                # middle -- on the sample clip the right hand drops out for
                # frames 66-68 while the finger closes, and nearest fill turned
                # that into a 26.9 deg curl step between two adjacent frames,
                # 42.3 deg once distributed onto `middle_1`. A curl is a
                # continuous quantity: between two detections the honest fill is
                # the line joining them. Outside them there is nothing to
                # interpolate towards, so the nearest value is held.
                for c in range(values.shape[1]):
                    values[:, c] = np.interp(np.arange(self.n), valid, obs[:, c])
            self.curls[side] = values
            self.curls_filled[side] = int((~present).sum()) if present.any() else self.n
            if present.any() and self.curls_filled[side]:
                self.notes.append(
                    f"finger curls: {self.curls_filled[side]}/{self.n} {side} frames had "
                    "no hand detection and were interpolated between the detections "
                    "either side, held at the ends")
            elif not present.any():
                self.unrepresented.append(f"finger curls: no {side} hand was ever detected")

        self.primary_label = ((self.manifest.get("primary", {}) or {}).get("object_label")
                              or (self.summary.get("primary_object") or {}).get("label"))
        self.primary_hand = ((self.manifest.get("primary", {}) or {}).get("hand")
                             or self.summary.get("primary_hand") or "right")

    def task_text(self):
        """One natural-language instruction, for the GR00T dataset's task field."""
        for row in self.captions:
            text = (row or {}).get("en")
            if text:
                return text
        action = (self.phase[0] or {}).get("action")
        if action and self.primary_label:
            return f"{action.replace('_', ' ')} the {self.primary_label}"
        return self.summary.get("task") or "reproduce the recorded human behavior"

    def pose_landmarks_2d(self):
        path = self.dir / "human/pose_landmarks.csv"
        if not path.exists():
            return None
        u, v, x, y, vis = [], [], [], [], []
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                u.append(float(row["x"]));  v.append(float(row["y"]))
                x.append(float(row["world_x"]));  y.append(-float(row["world_y"]))
                vis.append(float(row.get("visibility") or 1.0))
        return (np.array(u), np.array(v), np.array(x), np.array(y), np.array(vis))

    def object_detections(self):
        path = self.dir / "objects/object_detections.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def interaction_events(self):
        path = self.dir / "interactions/interaction_events.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# the human, measured from canonical landmarks
# --------------------------------------------------------------------------


def measure_subject(cbd: Cbd):
    """Bone lengths in metres -- medians of canonical landmark distances.

    Rule 6: nothing here is authored. The G1 does not adopt these lengths --
    it cannot, they are its hardware -- but the retarget needs them to know
    what the subject's segments were pointing at, and the size ratio between
    subject and robot is derived from them.
    """
    p = cbd.pose

    def seg(a, b):
        return float(np.median(np.linalg.norm(p[:, LM[a]] - p[:, LM[b]], axis=1)))

    def pair(la, lb, ra, rb):
        return (seg(la, lb) + seg(ra, rb)) / 2.0

    mid_sh = (p[:, LM["l_sh"]] + p[:, LM["r_sh"]]) / 2.0
    mid_hip = (p[:, LM["l_hip"]] + p[:, LM["r_hip"]]) / 2.0
    hip_to_shoulder = float(np.median(np.linalg.norm(mid_sh - mid_hip, axis=1)))
    nose_above_sh = float(np.median(np.linalg.norm(p[:, LM["nose"]] - mid_sh, axis=1)))
    dims = {
        "sh_half": seg("l_sh", "r_sh") / 2.0,
        "hip_half": seg("l_hip", "r_hip") / 2.0,
        "hip_to_shoulder": hip_to_shoulder,
        "spine1": hip_to_shoulder * 0.42,
        "spine2": hip_to_shoulder * 0.58,
        "neck": 0.02,
        "head_off": max(0.05, nose_above_sh * 0.26),
        "upper_arm": pair("l_sh", "l_elb", "r_sh", "r_elb"),
        "lower_arm": pair("l_elb", "l_wri", "r_elb", "r_wri"),
        "hand": pair("l_wri", "l_idx", "r_wri", "r_idx"),
        "upper_leg": pair("l_hip", "l_knee", "r_hip", "r_knee"),
        "lower_leg": pair("l_knee", "l_ank", "r_knee", "r_ank"),
        "foot": pair("l_ank", "l_toe", "r_ank", "r_toe"),
    }
    dims["floor_y"] = float(p[:, [LM["l_heel"], LM["r_heel"],
                                  LM["l_toe"], LM["r_toe"]], 1].min())
    dims["pelvis_to_ankle"] = dims["upper_leg"] + dims["lower_leg"]
    return dims


def human_fk(cbd: Cbd, dims, root_pos):
    """Canonical world rotation and position of every human bone, per frame."""
    offsets = {name: np.array(fn(dims), float) for name, parent, fn in BONE_TREE}
    world_rot, world_pos = {}, {}
    for name, parent, _ in BONE_TREE:
        local = cbd.rot.get(name)
        if local is None:
            local = np.tile([1.0, 0.0, 0.0, 0.0], (cbd.n, 1))
        if parent is None:
            world_rot[name] = q_normalize(local)
            world_pos[name] = root_pos
        else:
            world_rot[name] = q_normalize(q_mul(world_rot[parent], local))
            world_pos[name] = world_pos[parent] + q_rot(world_rot[parent], offsets[name])
    return world_rot, world_pos, offsets


# --------------------------------------------------------------------------
# the robot -- a Unitree G1, read from the kinematic table beside this file
# --------------------------------------------------------------------------
# `g1_kinematics.json` carries joint origins, axes and limits taken from the
# official Unitree URDF, and nothing else. It is the target's hardware: unlike
# the human rig above, not one number in it is derived from the dataset, and
# none of it may be stretched to fit the subject.


class G1:
    def __init__(self, path=KINEMATICS):
        doc = json.loads(Path(path).read_text("utf-8"))
        self.doc = doc
        self.joints = doc["joints"]
        self.order = doc["state_action_order"]          # the 43-DoF GR00T layout
        self.groups = doc["groups"]
        self.index = {name: i for i, name in enumerate(self.order)}
        self.limit = np.array([self.joints[n]["limit"] for n in self.order])
        self.origin_t = {k: np.array(v["origin_xyz"], float) for k, v in self.joints.items()}
        self.origin_R = {k: rpy_mat(v["origin_rpy"]) for k, v in self.joints.items()}
        self.axis = {k: np.array(v.get("axis", [0.0, 0.0, 1.0]), float)
                     for k, v in self.joints.items()}
        self.child_joints = {}
        for name, j in self.joints.items():
            self.child_joints.setdefault(j["parent"], []).append(name)
        self.links = ["pelvis"] + [j["child"] for j in self.joints.values()]

    # -- chains the retarget solves, in URDF order -------------------------
    WAIST = ["waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint"]

    def arm(self, side):
        return [f"{side}_shoulder_pitch_joint", f"{side}_shoulder_roll_joint",
                f"{side}_shoulder_yaw_joint", f"{side}_elbow_joint",
                f"{side}_wrist_roll_joint", f"{side}_wrist_pitch_joint",
                f"{side}_wrist_yaw_joint", f"{side}_hand_palm_joint"]

    def leg(self, side):
        return [f"{side}_hip_pitch_joint", f"{side}_hip_roll_joint",
                f"{side}_hip_yaw_joint", f"{side}_knee_joint",
                f"{side}_ankle_pitch_joint", f"{side}_ankle_roll_joint"]

    def chain_limits(self, chain):
        rev = [n for n in chain if self.joints[n]["type"] == "revolute"]
        lim = np.array([self.joints[n]["limit"] for n in rev])
        return lim[:, 0], lim[:, 1]

    def chain_frames(self, chain, angles, R0=None, t0=None):
        """Link frames along one chain. `angles` covers its revolute joints only."""
        R = np.eye(3) if R0 is None else R0
        t = np.zeros(3) if t0 is None else np.asarray(t0, float)
        out = {}
        k = 0
        for name in chain:
            t = t + R @ self.origin_t[name]
            R = R @ self.origin_R[name]
            if self.joints[name]["type"] == "revolute":
                R = R @ axis_mat(self.axis[name], float(angles[k]))
                k += 1
            out[self.joints[name]["child"]] = (R, t)
        return out

    def full_frames(self, q, pelvis_R=None, pelvis_t=None):
        """Every link frame, walking the whole tree from the pelvis."""
        R0 = np.eye(3) if pelvis_R is None else pelvis_R
        t0 = np.zeros(3) if pelvis_t is None else np.asarray(pelvis_t, float)
        frames = {"pelvis": (R0, t0)}
        stack = ["pelvis"]
        while stack:
            link = stack.pop()
            R, t = frames[link]
            for name in self.child_joints.get(link, []):
                tc = t + R @ self.origin_t[name]
                Rc = R @ self.origin_R[name]
                if self.joints[name]["type"] == "revolute":
                    Rc = Rc @ axis_mat(self.axis[name], float(q[self.index[name]]))
                child = self.joints[name]["child"]
                frames[child] = (Rc, tc)
                stack.append(child)
        return frames

    def pelvis_to_ankle(self):
        """The robot's own leg length, at its zero pose. Hardware, not a fit."""
        frames = self.chain_frames(self.leg("left"), np.zeros(6))
        return float(np.linalg.norm(frames["left_ankle_roll_link"][1]))

    def shoulder_to_palm(self):
        frames = self.chain_frames(self.arm("left"), np.zeros(7))
        return float(np.linalg.norm(frames["left_hand_palm_link"][1]
                                    - frames["left_shoulder_pitch_link"][1]))


# --------------------------------------------------------------------------
# retargeting -- human segment directions into G1 joint angles
# --------------------------------------------------------------------------
# The G1 cannot borrow the subject's proportions, so nothing is matched in
# metres. What is matched is *direction*: where each segment points, in the
# frame of the joint that carries it. That is the quantity a fixed-length limb
# can actually reproduce, and the residual it leaves is reported in degrees.


def solve_ik(fk, residual, x0, lo, hi, iters=60, damp=0.02, step=1e-4, tol=1e-6):
    """Damped least squares on a direction residual, with box constraints.

    The Jacobian is finite-difference and taken *without* clamping, so a joint
    resting on its limit still reports the direction it would move in; only the
    step is projected back into the box. Damping keeps the solve stable through
    the singular configurations a straightened arm passes through.
    """
    x = np.clip(np.asarray(x0, float).copy(), lo, hi)
    r = residual(fk(x))
    cost = float(r @ r)
    eye = np.eye(len(x))
    for _ in range(iters):
        jac = np.empty((len(r), len(x)))
        for k in range(len(x)):
            xp = x.copy()
            xp[k] += step
            jac[:, k] = (residual(fk(xp)) - r) / step
        try:
            dx = np.linalg.solve(jac.T @ jac + damp * eye, -jac.T @ r)
        except np.linalg.LinAlgError:
            break
        improved = False
        for scale in (1.0, 0.5, 0.25, 0.1, 0.03):
            xn = np.clip(x + scale * dx, lo, hi)
            rn = residual(fk(xn))
            cn = float(rn @ rn)
            if cn < cost - tol:
                x, r, improved = xn, rn, True
                cost = cn
                break
        if not improved:
            break
    return x, r, cost


def decompose_zxy(m):
    """R = Rz(yaw) Rx(roll) Ry(pitch) -- the G1 waist chain's own order."""
    roll = math.asin(float(np.clip(m[2, 1], -1.0, 1.0)))
    pitch = math.atan2(-float(m[2, 0]), float(m[2, 2]))
    yaw = math.atan2(-float(m[0, 1]), float(m[1, 1]))
    return yaw, roll, pitch


def dir_in(frame_R, v_world_robot):
    """A robot-world direction, expressed in a link frame."""
    return unit(frame_R.T @ v_world_robot)


class Retargeter:
    """One frame at a time, warm-started from the last -- so the solution is a
    trajectory rather than 96 independent solves that flip between branches."""

    # The Dex3 has three fingers, so ring and little have nowhere to go, and
    # `thumb_0` is an abduction rather than a curl. Everything else is driven
    # by the measured CBD flexion, split across the joints that carry it in
    # proportion to their travel -- no "closed fist" constant to tune.
    FINGER_CHAIN = {"index": ["index_0", "index_1"],
                    "middle": ["middle_0", "middle_1"],
                    "thumb": ["thumb_1", "thumb_2"]}
    THUMB_OPPOSITION = 0.6      # rad at full thumb flexion; an adapter choice

    # `finger_curls_rad` is the **mean** flexion of a finger's joints, not the
    # finger's total bend -- the specification says so in as many words
    # ("mean flexion per finger", specification/README.md) and the sample
    # dataset agrees to two decimals: right index mean(J1,J2,J3) = 33.09 deg,
    # curl = 33.09, sum = 99.26. Treating the mean as the total is what v2
    # shipped, and it closed the hand to a third of the subject's grip: 16 deg
    # per Dex3 joint against a 190 deg travel, which reads as an open hand
    # holding nothing. CBD carries three flexions per finger, so the total is
    # three times the mean.
    CURL_JOINTS_PER_FINGER = 3.0

    def __init__(self, g1: G1, cbd: Cbd, world_rot, world_pos):
        self.g1 = g1
        self.cbd = cbd
        self.world_rot = world_rot
        self.world_pos = world_pos
        self.hips_mat = q_to_mat(world_rot["hips"])          # (N,3,3) canonical
        self.arm_targets = {s: self._arm_targets(s) for s in ("left", "right")}
        self.leg_targets = {s: self._leg_targets(s) for s in ("left", "right")}
        self.waist_mat = self._waist_matrices()

    # -- targets, all in the robot's world axes ---------------------------
    def _world_dir(self, a, b):
        return unit(vec_c_to_r(self.world_pos[b] - self.world_pos[a]))

    def _world_axis(self, bone, axis_c):
        return unit(vec_c_to_r(q_rot(self.world_rot[bone], axis_c)))

    def _arm_targets(self, side):
        s = "left" if side == "left" else "right"
        sign = 1.0 if side == "left" else -1.0
        return {
            "upper": self._world_dir(f"{s}_upper_arm", f"{s}_lower_arm"),
            "fore": self._world_dir(f"{s}_lower_arm", f"{s}_hand"),
            # the hand's long axis: +X for the left hand in the canonical T-pose
            "hand": self._world_axis(f"{s}_hand", (sign, 0.0, 0.0)),
            # the direction the palm faces: down in the canonical T-pose
            "palm": self._world_axis(f"{s}_hand", (0.0, -1.0, 0.0)),
        }

    def _leg_targets(self, side):
        return {
            "thigh": self._world_dir(f"{side}_upper_leg", f"{side}_lower_leg"),
            "shank": self._world_dir(f"{side}_lower_leg", f"{side}_foot"),
            "foot": self._world_axis(f"{side}_foot", (0.0, 0.0, 1.0)),
        }

    def _waist_matrices(self):
        chest = q_to_mat(self.world_rot["chest"])
        rel = np.einsum("nji,njk->nik", self.hips_mat, chest)      # hips^T * chest
        # the batched form of mat_c_to_r: the same P M P^T, per frame
        return np.einsum("ij,njk,lk->nil", P_C2R, rel, P_C2R)

    # -- one frame ---------------------------------------------------------
    def waist(self, i, clip_log):
        yaw, roll, pitch = decompose_zxy(self.waist_mat[i])
        out = []
        for name, value in zip(G1.WAIST, (yaw, roll, pitch)):
            lo, hi = self.g1.joints[name]["limit"]
            clipped = float(np.clip(value, lo, hi))
            if abs(clipped - value) > 1e-9:
                clip_log[name] = clip_log.get(name, 0) + 1
            out.append(clipped)
        return np.array(out)

    def _pelvis_R(self, i):
        return mat_c_to_r(self.hips_mat[i])

    def arm(self, i, side, torso_R, x0):
        chain = self.g1.arm(side)
        lo, hi = self.g1.chain_limits(chain)
        tgt = self.arm_targets[side]
        palm_axis = np.array([0.0, -1.0, 0.0]) if side == "left" else np.array([0.0, 1.0, 0.0])
        sh, el = f"{side}_shoulder_pitch_link", f"{side}_elbow_link"
        wr, pl = f"{side}_wrist_roll_link", f"{side}_hand_palm_link"
        # targets carried into the torso frame the arm actually hangs from, so
        # a clipped waist shows up as arm error rather than being hidden
        t_up = dir_in(torso_R, tgt["upper"][i])
        t_fo = dir_in(torso_R, tgt["fore"][i])
        t_ha = dir_in(torso_R, tgt["hand"][i])
        t_pa = dir_in(torso_R, tgt["palm"][i])

        def fk(x):
            return self.g1.chain_frames(chain, x)

        def residual(f):
            d_up = unit(f[el][1] - f[sh][1])
            d_fo = unit(f[wr][1] - f[el][1])
            d_ha = unit(f[pl][1] - f[wr][1])
            n_pa = f[pl][0] @ palm_axis
            return np.concatenate([1.0 * (d_up - t_up), 1.0 * (d_fo - t_fo),
                                   0.6 * (d_ha - t_ha), 0.4 * (n_pa - t_pa)])

        return solve_ik(fk, residual, x0, lo, hi)

    def leg(self, i, side, x0):
        chain = self.g1.leg(side)
        lo, hi = self.g1.chain_limits(chain)
        tgt = self.leg_targets[side]
        hip, knee = f"{side}_hip_pitch_link", f"{side}_knee_link"
        ank, sole = f"{side}_ankle_pitch_link", f"{side}_ankle_roll_link"
        pelvis_R = self._pelvis_R(i)
        t_th = dir_in(pelvis_R, tgt["thigh"][i])
        t_sh = dir_in(pelvis_R, tgt["shank"][i])
        t_fo = dir_in(pelvis_R, tgt["foot"][i])
        forward = np.array([1.0, 0.0, 0.0])

        def fk(x):
            return self.g1.chain_frames(chain, x)

        def residual(f):
            d_th = unit(f[knee][1] - f[hip][1])
            d_sh = unit(f[ank][1] - f[knee][1])
            d_fo = f[sole][0] @ forward
            return np.concatenate([1.0 * (d_th - t_th), 1.0 * (d_sh - t_sh),
                                   0.6 * (d_fo - t_fo)])

        return solve_ik(fk, residual, x0, lo, hi)

    def hand(self, i, side, clip_log):
        """CBD finger curls onto the Dex3's seven joints.

        A curl is the *mean* flexion of the finger's joints, in radians, so the
        finger's total bend is `CURL_JOINTS_PER_FINGER` times it. That total is
        distributed over the two Dex3 joints in proportion to how far each one
        can travel toward closing, and anything past the finger's total travel
        is clipped and counted -- so the robot bends as far as the subject did,
        or as far as it can, and the report says which.
        """
        order = self.cbd.finger_order
        curls = self.cbd.curls[side][i]
        out = {}
        for finger, shorts in self.FINGER_CHAIN.items():
            mean_flex = float(curls[order.index(finger)]) if finger in order else 0.0
            flex = mean_flex * self.CURL_JOINTS_PER_FINGER
            travel = []
            for short in shorts:
                lo, hi = self.g1.joints[f"{side}_hand_{short}_joint"]["limit"]
                # the G1's zero is the open hand; closing runs toward one limit
                travel.append(hi if abs(hi) > abs(lo) else lo)
            total = sum(abs(t) for t in travel)
            for short, reach in zip(shorts, travel):
                name = f"{side}_hand_{short}_joint"
                share = abs(reach) / total if total else 0.0
                value = math.copysign(max(0.0, flex) * share, reach)
                lo, hi = self.g1.joints[name]["limit"]
                clipped = float(np.clip(value, lo, hi))
                if abs(clipped - value) > 1e-9:
                    clip_log[name] = clip_log.get(name, 0) + 1
                out[name] = clipped
            if finger == "thumb":
                name = f"{side}_hand_thumb_0_joint"
                lo, hi = self.g1.joints[name]["limit"]
                sign = 1.0 if side == "left" else -1.0
                u = min(1.0, max(0.0, flex) / total) if total else 0.0
                out[name] = float(np.clip(sign * self.THUMB_OPPOSITION * u, lo, hi))
        return out


# --------------------------------------------------------------------------
# the set -- derived from canonical data, then scaled to the robot
# --------------------------------------------------------------------------
# The G1 is 1.3 m of fixed hardware and the subject is not. Rather than stretch
# the robot, this adapter scales the *set*: one number, the ratio between the
# robot's own seated pelvis height and the subject's, applied to the floor, the
# chair, the table and the camera. The robot keeps its factory dimensions and
# the geometry stays consistent -- it sits on a chair built for it.


def fit_image_plane(cbd: Cbd):
    """Fit normalized image coordinates to canonical metres.

    The dataset carries both views of the same landmarks -- normalized image
    and canonical world -- so the mapping between them is measured, not
    assumed. Anything projected through it is `projected_to_plane`.
    """
    got = cbd.pose_landmarks_2d()
    if got is None:
        return None
    u, v, x, y, vis = got
    keep = vis > 0.5
    if keep.sum() < 50:
        return None
    ax = np.column_stack([u[keep], np.ones(keep.sum())])
    sx, cx = np.linalg.lstsq(ax, x[keep], rcond=None)[0]
    av = np.column_stack([v[keep], np.ones(keep.sum())])
    sy, cy = np.linalg.lstsq(av, y[keep], rcond=None)[0]
    return {"sx": float(sx), "cx": float(cx), "sy": float(sy), "cy": float(cy),
            "residual_x_m": round(float(np.std(x[keep] - (sx * u[keep] + cx))), 4),
            "residual_y_m": round(float(np.std(y[keep] - (sy * v[keep] + cy))), 4),
            "samples": int(keep.sum())}


def project(plane, u, v):
    return (plane["sx"] * u + plane["cx"], plane["sy"] * v + plane["cy"])


def median_bbox(detections, label):
    rows = [d for d in detections if d.get("label") == label]
    if not rows:
        return None
    bb = np.array([[float(d["bbox_x"]), float(d["bbox_y"]),
                    float(d["bbox_width"]), float(d["bbox_height"])] for d in rows])
    x, y, w, h = np.median(bb, axis=0)
    return {"u0": float(x), "v0": float(y), "u1": float(x + w), "v1": float(y + h),
            "count": len(rows)}


def derive_set(cbd: Cbd, dims, world_pos, plane, scale):
    """Floor, chair and table, in the robot's world frame (Z up, metres).

    No glass: the primary object is out of this adapter's scope, and the
    report says so rather than leaving a prop standing in the render with no
    provenance behind it.
    """
    det = cbd.object_detections()
    hips = world_pos["hips"]
    floor_y = dims["floor_y"]
    prov = {"scale": [
        f"the whole set is scaled by {scale:.4f} about the floor plane -- the "
        "ratio of the robot's own seated pelvis height (from its retargeted "
        "leg pose, with its factory link lengths) to the subject's. The robot "
        "is not resized; the room is"]}

    def to_robot(x_c, y_c, z_c):
        """canonical (x right, y up, z toward camera) -> robot (x fwd, y left, z up),
        with the floor at z = 0 and the set scaled about it."""
        return (scale * z_c, scale * x_c, scale * (y_c - floor_y))

    # ---- chair -----------------------------------------------------------
    chair_box = median_bbox(det, "chair")
    seat_y = float(np.median(hips[:, 1])) - 0.075
    half_width, back_top_y = 0.28, seat_y + 0.24
    prov["chair"] = ["seat height: derived from the canonical pelvis position "
                     "(the subject is sitting on it)"]
    if chair_box and plane:
        left_x, top_y = project(plane, chair_box["u0"], chair_box["v0"])
        half_width = max(0.22, abs(float(np.median(hips[:, 0])) - left_x))
        back_top_y = float(top_y)
        prov["chair"].append(
            f"width and back height: projected_to_plane from the median of "
            f"{chair_box['count']} `chair` detections")
    else:
        prov["chair"].append("width and back height: adapter defaults "
                             "(no `chair` detections in the dataset)")
    cx, cy, cz = to_robot(float(np.median(hips[:, 0])),
                          seat_y, float(np.median(hips[:, 2])) - 0.02)
    chair = {"x": cx, "y": cy, "seat_top_z": cz,
             "half_width": scale * half_width, "half_depth": scale * 0.24,
             "back_top_z": scale * (back_top_y - floor_y),
             "arm_top_z": scale * (seat_y + 0.20 - floor_y)}

    # ---- table -----------------------------------------------------------
    # Its top is the height the primary hand reached to, and its extent is the
    # detected box. Nothing stands on it: see `not_represented`.
    hand_bone = f"{cbd.primary_hand.lower()}_hand"
    hand = world_pos.get(hand_bone, world_pos["right_hand"])
    reach = int(np.argmax(np.abs(hand[:, 0] - np.median(hips[:, 0]))))
    grip = hand[reach]
    prov["table"] = [
        f"top height: the height the {cbd.primary_hand} hand reached at frame "
        f"{reach} (t={cbd.timestamps[reach]:.2f}s), its furthest reach"]
    radius, centre_x = 0.24, float(grip[0]) + 0.06
    table_box = median_bbox(det, "dining table")
    if table_box and plane:
        left_x, _ = project(plane, table_box["u0"], table_box["v0"])
        right_x, _ = project(plane, table_box["u1"], table_box["v0"])
        radius = max(0.16, float(right_x - left_x) / 2.0)
        centre_x = float(left_x) + radius
        prov["table"].append(
            f"radius and X: projected_to_plane from the median of "
            f"{table_box['count']} `dining table` detections")
    else:
        prov["table"].append("radius: adapter default "
                             "(no `dining table` detections in the dataset)")
    tx, ty, tz = to_robot(centre_x, float(grip[1]) - 0.05, float(grip[2]) - 0.06)
    table = {"x": tx, "y": ty, "top_z": tz, "radius": scale * radius}

    return {"chair": chair, "table": table, "reach_frame": reach,
            "scale": scale, "provenance": prov}


def derive_camera(cbd: Cbd, plane, scale, floor_y, width, height):
    """A camera that reproduces the source clip's framing, at set scale."""
    aspect = height / float(width)
    if plane is None:
        return {"axis_x": 0.0, "axis_z": 0.9 * scale, "world_width": 1.2 * scale,
                "world_height": 1.2 * scale * aspect, "distance": 3.0 * scale,
                "source": "adapter default (no paired landmarks in the dataset)"}
    axis_x, axis_y = project(plane, 0.5, 0.5)
    world_width = abs(plane["sx"]) * scale
    # canonical X becomes the stage's X and canonical Y its Z, with the floor
    # moved to zero and the whole set scaled about it
    return {"axis_x": float(axis_x) * scale,
            "axis_z": float(axis_y - floor_y) * scale,
            "world_width": float(world_width),
            "world_height": float(world_width * aspect),
            "distance": 3.0 * scale,
            "source": "fitted from the dataset's paired image/canonical landmarks"}


# --------------------------------------------------------------------------
# USD authoring
# --------------------------------------------------------------------------
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade   # noqa: E402

SHELL = (0.93, 0.93, 0.94)      # the G1's white shells
JOINT = (0.13, 0.13, 0.15)      # the exposed actuator housings
ACCENT = (0.24, 0.26, 0.30)
VISOR = (0.05, 0.05, 0.06)
SOLE_BELOW_ANKLE = 0.030        # adapter constant: no collision geometry is read

# Shell radius and colour per link, by the joint group it belongs to. The G1
# wears white covers over dark actuator clusters; the split below follows that
# rather than inventing a livery.
LINK_RADIUS = {"hip_pitch": 0.050, "hip_roll": 0.048, "hip_yaw": 0.046,
               "knee": 0.040, "ankle_pitch": 0.032, "ankle_roll": 0.032,
               "shoulder_pitch": 0.042, "shoulder_roll": 0.040,
               "shoulder_yaw": 0.034, "elbow": 0.030,
               "wrist_roll": 0.026, "wrist_pitch": 0.024, "wrist_yaw": 0.024,
               "hand_palm": 0.012, "hand_index": 0.009, "hand_middle": 0.009,
               "hand_thumb": 0.009, "waist_yaw": 0.055, "waist_roll": 0.055}
LINK_MATERIAL = {"shoulder_pitch": "accent", "shoulder_roll": "accent",
                 "hip_pitch": "accent", "hip_roll": "accent",
                 "wrist": "joint", "ankle": "joint", "hand": "joint"}


def link_material(link):
    for key, value in LINK_MATERIAL.items():
        if key in link:
            return value
    return "shell"


def link_radius(link):
    for key, value in LINK_RADIUS.items():
        if key in link:
            return value
    return 0.04


def make_material(stage, path, color, roughness=0.6, metallic=0.0,
                  opacity=1.0, ior=1.5):
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    if opacity < 1.0:
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(ior)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def bind(prim, material):
    UsdShade.MaterialBindingAPI.Apply(prim.GetPrim()).Bind(material)


def add_sphere(stage, path, radius, material, offset=(0, 0, 0), scale=None):
    sph = UsdGeom.Sphere.Define(stage, path)
    sph.GetRadiusAttr().Set(float(radius))
    api = UsdGeom.XformCommonAPI(sph)
    api.SetTranslate(Gf.Vec3d(*[float(c) for c in offset]))
    if scale:
        api.SetScale(Gf.Vec3f(*[float(c) for c in scale]))
    bind(sph, material)
    return sph


def add_box(stage, path, size, material, offset=(0, 0, 0), rotate=None):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.GetSizeAttr().Set(2.0)
    api = UsdGeom.XformCommonAPI(cube)
    api.SetTranslate(Gf.Vec3d(*[float(c) for c in offset]))
    if rotate:
        api.SetRotate(Gf.Vec3f(*[float(c) for c in rotate]))
    api.SetScale(Gf.Vec3f(*[float(c) / 2.0 for c in size]))
    bind(cube, material)
    return cube


def add_cylinder(stage, path, axis, height, radius, material, offset=(0, 0, 0)):
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.GetAxisAttr().Set(axis)
    cyl.GetHeightAttr().Set(float(height))
    cyl.GetRadiusAttr().Set(float(radius))
    UsdGeom.XformCommonAPI(cyl).SetTranslate(Gf.Vec3d(*[float(c) for c in offset]))
    bind(cyl, material)
    return cyl


def add_capsule_between(stage, path, a, b, radius, material):
    """A capsule spanning two points in the parent link's frame.

    The link shells are generated from the URDF's own joint origins, so the
    robot in the render has the G1's proportions and not an artist's.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    span = b - a
    length = float(np.linalg.norm(span))
    if length < 1e-4:
        return None
    cap = UsdGeom.Capsule.Define(stage, path)
    cap.GetAxisAttr().Set("Z")
    cap.GetRadiusAttr().Set(float(radius))
    cap.GetHeightAttr().Set(float(max(length - 2 * radius, 1e-3)))
    axis = np.cross([0.0, 0.0, 1.0], span / length)
    dot = float(span[2] / length)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-9:
        quat = Gf.Quatf(1.0 if dot > 0 else 0.0,
                        Gf.Vec3f(1.0, 0.0, 0.0) if dot < 0 else Gf.Vec3f(0.0, 0.0, 0.0))
    else:
        angle = math.atan2(norm, dot)
        axis = axis / norm
        quat = Gf.Quatf(float(math.cos(angle / 2)),
                        Gf.Vec3f(*[float(c * math.sin(angle / 2)) for c in axis]))
    xf = UsdGeom.Xformable(cap)
    xf.AddTranslateOp().Set(Gf.Vec3d(*[float(c) for c in (a + b) / 2.0]))
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(quat)
    bind(cap, material)
    return cap


def new_stage(path, fps=None, frames=None):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    if fps:
        stage.SetTimeCodesPerSecond(fps)
        stage.SetFramesPerSecond(fps)
        stage.SetStartTimeCode(0)
        stage.SetEndTimeCode(frames - 1)
    return stage


# -- the robot -------------------------------------------------------------
# Terminal links carry no joint to point a shell at, so their tips are the one
# place a length is authored rather than read from the URDF.
TIP = {"left_hand_index_1_link": (0.045, 0.0, 0.0),
       "left_hand_middle_1_link": (0.045, 0.0, 0.0),
       "left_hand_thumb_2_link": (0.0, -0.040, 0.0),
       "right_hand_index_1_link": (0.045, 0.0, 0.0),
       "right_hand_middle_1_link": (0.045, 0.0, 0.0),
       "right_hand_thumb_2_link": (0.0, 0.040, 0.0)}
SKIP_SHELL_PARENT = {"pelvis", "torso_link", "waist_yaw_link", "waist_roll_link"}


def write_robot_usd(path, g1: G1, ego_width, ego_height):
    """`g1_robot.usda` -- the robot alone, at its zero pose. No motion.

    One Xform per G1 link, each at the URDF's own origin and fixed rotation, so
    a joint angle drops straight onto `xformOp:orient` in the motion layer. The
    shells are capsules spanning the URDF's joint origins: the proportions are
    the robot's, the surfaces are this adapter's, and no vendor mesh is
    redistributed here.
    """
    stage = new_stage(path)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    root = UsdGeom.Xform.Define(stage, "/World/G1")
    # the one conversion between the robot's frame and the stage's
    UsdGeom.Xformable(root).AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
        Gf.Quatf(float(Q_R2U[0]), Gf.Vec3f(*[float(c) for c in Q_R2U[1:]])))
    looks = "/World/G1/Looks"
    UsdGeom.Scope.Define(stage, looks)
    mats = {
        "shell": make_material(stage, looks + "/Shell", SHELL, roughness=0.35),
        "joint": make_material(stage, looks + "/Joint", JOINT, roughness=0.45, metallic=0.4),
        "accent": make_material(stage, looks + "/Accent", ACCENT, roughness=0.5, metallic=0.2),
        "visor": make_material(stage, looks + "/Visor", VISOR, roughness=0.12, metallic=0.1),
    }

    link_path = {"pelvis": "/World/G1/pelvis"}
    pelvis = UsdGeom.Xform.Define(stage, link_path["pelvis"])
    UsdGeom.Xformable(pelvis).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
    UsdGeom.Xformable(pelvis).AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
        Gf.Quatf(1.0, Gf.Vec3f(0.0, 0.0, 0.0)))

    # walk the joint tree so a parent's path always exists before its child's
    pending = ["pelvis"]
    while pending:
        parent = pending.pop(0)
        for name in g1.child_joints.get(parent, []):
            child = g1.joints[name]["child"]
            link_path[child] = link_path[parent] + "/" + child
            xf = UsdGeom.Xform.Define(stage, link_path[child])
            xf.AddTranslateOp().Set(Gf.Vec3d(*[float(c) for c in g1.origin_t[name]]))
            q = mat_to_q(g1.origin_R[name])
            xf.AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
                Gf.Quatf(float(q[0]), Gf.Vec3f(*[float(c) for c in q[1:]])))
            pending.append(child)

    # ---- shells generated from the URDF's own joint origins ---------------
    for name, joint in g1.joints.items():
        parent = joint["parent"]
        if parent in SKIP_SHELL_PARENT or parent not in link_path:
            continue
        span = g1.origin_t[name]
        if float(np.linalg.norm(span)) < 0.045:
            continue
        add_capsule_between(stage, link_path[parent] + f"/shell_{joint['child']}",
                            (0.0, 0.0, 0.0), span, link_radius(parent),
                            mats[link_material(parent)])
    for link, tip in TIP.items():
        add_capsule_between(stage, link_path[link] + "/tip", (0.0, 0.0, 0.0), tip,
                            0.009, mats["joint"])
    # the actuator housings the shells run between
    for side in ("left", "right"):
        add_sphere(stage, link_path[f"{side}_shoulder_roll_link"] + "/hub", 0.046,
                   mats["accent"])
        add_sphere(stage, link_path[f"{side}_elbow_link"] + "/hub", 0.036, mats["accent"])
        add_sphere(stage, link_path[f"{side}_knee_link"] + "/hub", 0.046, mats["accent"])
        add_sphere(stage, link_path[f"{side}_hip_yaw_link"] + "/hub", 0.052, mats["accent"])

    # ---- pelvis, torso and head ------------------------------------------
    p = link_path["pelvis"]
    add_box(stage, p + "/block", (0.145, 0.210, 0.140), mats["shell"],
            offset=(0.0, 0.0, -0.040))
    add_box(stage, p + "/waistband", (0.125, 0.185, 0.050), mats["accent"],
            offset=(0.0, 0.0, 0.030))
    t = link_path["torso_link"]
    # the shoulder pitch joints sit at y = +/-0.100, so a torso wider than
    # that would swallow the arms: 0.195 is what the URDF leaves room for
    add_box(stage, t + "/chest", (0.150, 0.195, 0.245), mats["shell"],
            offset=(0.008, 0.0, 0.108))
    add_box(stage, t + "/chest_plate", (0.018, 0.118, 0.128), mats["accent"],
            offset=(0.085, 0.0, 0.118))
    add_box(stage, t + "/spine", (0.110, 0.185, 0.085), mats["accent"],
            offset=(0.0, 0.0, -0.045))
    add_box(stage, t + "/yoke", (0.120, 0.235, 0.062), mats["accent"],
            offset=(0.004, 0.0, 0.240))
    add_cylinder(stage, t + "/neck", "Z", 0.050, 0.033, mats["joint"],
                 offset=(0.0, 0.0, 0.305))
    # the head pod stops short of `d435_link`, so the robot's own camera is not
    # looking at the inside of its own shell
    add_sphere(stage, t + "/head", 0.066, mats["shell"], offset=(-0.008, 0.0, 0.380),
               scale=(0.86, 0.95, 1.02))
    add_box(stage, t + "/visor", (0.016, 0.105, 0.036), mats["visor"],
            offset=(0.040, 0.0, 0.368))
    for sign in (-1, 1):
        add_cylinder(stage, t + f"/ear_{'l' if sign > 0 else 'r'}", "Y", 0.016, 0.022,
                     mats["joint"], offset=(-0.010, sign * 0.062, 0.388))

    # ---- feet and palms ---------------------------------------------------
    for side in ("left", "right"):
        add_box(stage, link_path[f"{side}_ankle_roll_link"] + "/sole",
                (0.195, 0.095, 0.028), mats["joint"],
                offset=(0.022, 0.0, -SOLE_BELOW_ANKLE))
        add_box(stage, link_path[f"{side}_hand_palm_link"] + "/palm",
                (0.078, 0.028, 0.072), mats["shell"], offset=(0.038, 0.0, 0.0))

    # ---- the robot's own camera ------------------------------------------
    # Parented to `d435_link`, the frame the G1's head camera actually sits in,
    # so the ego view the GR00T dataset carries is the robot's, not a guess.
    cam = UsdGeom.Camera.Define(stage, link_path["d435_link"] + "/ego_cam")
    # the camera looks down its own -Z; the sensor frame looks down +X
    q = mat_to_q(np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]))
    UsdGeom.Xformable(cam).AddOrientOp(UsdGeom.XformOp.PrecisionFloat).Set(
        Gf.Quatf(float(q[0]), Gf.Vec3f(*[float(c) for c in q[1:]])))
    aperture = 20.955
    cam.GetFocalLengthAttr().Set(float(aperture / (2 * math.tan(math.radians(69.4 / 2)))))
    cam.GetHorizontalApertureAttr().Set(float(aperture))
    cam.GetVerticalApertureAttr().Set(float(aperture * ego_height / ego_width))
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.02, 100.0))

    stage.GetRootLayer().Save()
    return link_path


# -- the set ---------------------------------------------------------------


def write_scene_usd(path, sett, camera, width, height):
    """`scene.usda` -- floor, backdrop, chair, table, lights and the film camera.

    Built from primitives so every dimension traces back to a number in
    `derive_set()`. There is no glass on the table: see `not_represented`.
    """
    stage = new_stage(path)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    env = "/World/Environment"
    UsdGeom.Xform.Define(stage, env)
    looks = env + "/Looks"
    UsdGeom.Scope.Define(stage, looks)
    m_floor = make_material(stage, looks + "/Floor", (0.90, 0.90, 0.91), roughness=0.5)
    m_wall = make_material(stage, looks + "/Wall", (0.95, 0.95, 0.96), roughness=0.95)
    m_furn = make_material(stage, looks + "/Furniture", (0.96, 0.96, 0.97), roughness=0.3)

    def stage_xy(x_r, y_r):
        """The adapter's other boundary, on the two axes the set uses."""
        x, y, _ = vec_r_to_usd((x_r, y_r, 0.0))[0]
        return float(x), float(y)

    add_box(stage, env + "/floor", (12.0, 12.0, 0.04), m_floor, offset=(0, 0, -0.02))
    add_box(stage, env + "/backdrop", (12.0, 0.06, 6.0), m_wall, offset=(0, 1.6, 3.0))
    add_box(stage, env + "/wall_left", (0.06, 12.0, 6.0), m_wall, offset=(-3.2, 0, 3.0))
    add_box(stage, env + "/wall_right", (0.06, 12.0, 6.0), m_wall, offset=(3.4, 0, 3.0))

    ch = sett["chair"]
    cx, cy = stage_xy(ch["x"], ch["y"])
    seat, hw, hd = ch["seat_top_z"], ch["half_width"], ch["half_depth"]
    chair = env + "/chair"
    UsdGeom.Xform.Define(stage, chair)
    add_box(stage, chair + "/seat", (hw * 2, hd * 2, 0.035), m_furn,
            offset=(cx, cy, seat - 0.018))
    add_box(stage, chair + "/back", (hw * 1.92, 0.04, ch["back_top_z"] - seat), m_furn,
            offset=(cx, cy + hd - 0.02, (seat + ch["back_top_z"]) / 2))
    for sx in (-1, 1):
        tag = "l" if sx < 0 else "r"
        add_box(stage, chair + f"/arm_{tag}", (0.05, hd * 1.75, 0.035), m_furn,
                offset=(cx + sx * (hw - 0.025), cy - 0.04, ch["arm_top_z"]))
        for sy in (-1, 1):
            add_cylinder(stage, chair + f"/leg_{tag}{'f' if sy < 0 else 'b'}", "Z",
                         max(0.05, seat), 0.018, m_furn,
                         offset=(cx + sx * (hw - 0.05), cy + sy * (hd - 0.05), seat / 2))

    tb = sett["table"]
    tx, ty = stage_xy(tb["x"], tb["y"])
    top = tb["top_z"]
    table = env + "/table"
    UsdGeom.Xform.Define(stage, table)
    add_cylinder(stage, table + "/top", "Z", 0.03, tb["radius"], m_furn,
                 offset=(tx, ty, top - 0.015))
    for angle in (35, 155, 275):
        rad = math.radians(angle)
        add_cylinder(stage, table + f"/leg_{angle}", "Z", max(0.05, top - 0.03), 0.014,
                     m_furn, offset=(tx + math.cos(rad) * (tb["radius"] - 0.05),
                                     ty + math.sin(rad) * (tb["radius"] - 0.05),
                                     (top - 0.03) / 2))

    dome = UsdLux.DomeLight.Define(stage, env + "/dome")
    dome.CreateIntensityAttr(1200.0)
    key = UsdLux.RectLight.Define(stage, env + "/key")
    key.CreateIntensityAttr(16000.0)
    key.CreateWidthAttr(2.6)
    key.CreateHeightAttr(2.6)
    UsdGeom.XformCommonAPI(key).SetTranslate(Gf.Vec3d(-1.8, -2.6, 3.1))
    UsdGeom.XformCommonAPI(key).SetRotate(Gf.Vec3f(-50.0, 0.0, -32.0))
    fill = UsdLux.RectLight.Define(stage, env + "/fill")
    fill.CreateIntensityAttr(6500.0)
    fill.CreateWidthAttr(3.2)
    fill.CreateHeightAttr(2.2)
    UsdGeom.XformCommonAPI(fill).SetTranslate(Gf.Vec3d(2.4, -2.2, 2.4))
    UsdGeom.XformCommonAPI(fill).SetRotate(Gf.Vec3f(-38.0, 0.0, 38.0))
    ceiling = UsdLux.RectLight.Define(stage, env + "/top")
    ceiling.CreateIntensityAttr(5000.0)
    ceiling.CreateWidthAttr(4.0)
    ceiling.CreateHeightAttr(3.0)
    UsdGeom.XformCommonAPI(ceiling).SetTranslate(Gf.Vec3d(0.0, -0.2, 3.4))
    UsdGeom.XformCommonAPI(ceiling).SetRotate(Gf.Vec3f(-90.0, 0.0, 0.0))

    dist = camera["distance"]
    cam = UsdGeom.Camera.Define(stage, "/World/Camera")
    UsdGeom.XformCommonAPI(cam).SetTranslate(
        Gf.Vec3d(float(camera["axis_x"]), float(-dist), float(camera["axis_z"])))
    UsdGeom.XformCommonAPI(cam).SetRotate(Gf.Vec3f(90.0, 0.0, 0.0))
    aperture = 20.955
    focal = (aperture / 2.0) / (camera["world_width"] / 2.0 / dist)
    cam.GetFocalLengthAttr().Set(float(focal))
    cam.GetHorizontalApertureAttr().Set(float(aperture))
    cam.GetVerticalApertureAttr().Set(float(aperture * height / width))
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 100.0))

    stage.GetRootLayer().Save()
    return {"focal_length_mm": round(float(focal), 3),
            "horizontal_aperture_mm": aperture,
            "position_stage": [round(float(camera["axis_x"]), 4), round(-dist, 4),
                               round(float(camera["axis_z"]), 4)],
            "rotate_xyz_deg": [90.0, 0.0, 0.0],
            "horizontal_fov_deg": round(
                math.degrees(2 * math.atan(camera["world_width"] / 2.0 / dist)), 3)}


# -- the motion ------------------------------------------------------------


def write_motion_usd(path, robot_rel, scene_rel, g1: G1, link_path, cbd: Cbd,
                     q_traj, pelvis_R, pelvis_t):
    """`motion.usda` -- the stage to open. Sublayers the set and the robot and
    adds nothing but time samples."""
    stage = new_stage(path, fps=cbd.fps, frames=cbd.n)
    root = stage.GetRootLayer()
    root.subLayerPaths = [scene_rel, robot_rel]
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))

    pelvis = stage.GetPrimAtPath(link_path["pelvis"])
    translate = pelvis.GetAttribute("xformOp:translate")
    orient = pelvis.GetAttribute("xformOp:orient")
    for i in range(cbd.n):
        translate.Set(Gf.Vec3d(*[float(c) for c in pelvis_t[i]]), i)
        q = mat_to_q(pelvis_R[i])
        orient.Set(Gf.Quatf(float(q[0]), Gf.Vec3f(*[float(c) for c in q[1:]])), i)

    for name in g1.order:
        child = g1.joints[name]["child"]
        attr = stage.GetPrimAtPath(link_path[child]).GetAttribute("xformOp:orient")
        rest = g1.origin_R[name]
        axis = g1.axis[name]
        col = g1.index[name]
        for i in range(cbd.n):
            q = mat_to_q(rest @ axis_mat(axis, float(q_traj[i, col])))
            attr.Set(Gf.Quatf(float(q[0]), Gf.Vec3f(*[float(c) for c in q[1:]])), i)

    root.Save()


# --------------------------------------------------------------------------
# the GR00T-LeRobot dataset
# --------------------------------------------------------------------------
# The layout GR00T reads for a Unitree G1: LeRobot v2.1 on disk, with a
# `modality.json` that slices a flat 43-wide state/action vector into the
# groups the policy expects. The grouping and the joint order below are the
# Isaac Lab Arena G1 embodiment's, so a dataset written here drops into the
# same loader the Arena pick-and-place demo uses.

EEF_HELP = ("[x, y, z, qw, qx, qy, qz] of each hand's palm link, **in the "
            "pelvis frame** (X forward, Y left, Z up), left then right")


def modality_json(g1: G1):
    state, action, start = {}, {}, 0
    for group, names in g1.groups.items():
        span = {"start": start, "end": start + len(names)}
        state[group] = dict(span, original_key="observation.state")
        action[group] = dict(span)
        start += len(names)
    for i, side in enumerate(("left", "right")):
        state[f"{side}_wrist_pose"] = {"start": i * 7, "end": i * 7 + 7,
                                       "original_key": "observation.eef_pose"}
        action[f"{side}_wrist_pose"] = {"start": i * 7, "end": i * 7 + 7,
                                        "original_key": "action.eef_pose"}
    action["base_height_command"] = {"start": 0, "end": 1,
                                     "original_key": "teleop.base_height_command"}
    action["navigate_command"] = {"start": 0, "end": 3,
                                  "original_key": "teleop.navigate_command"}
    action["torso_orientation_rpy_command"] = {
        "start": 0, "end": 3, "original_key": "teleop.torso_orientation_rpy_command"}
    return {"state": state, "action": action,
            "video": {"ego_view": {"original_key": "observation.images.ego_view"}},
            "annotation": {"human.task_description": {"original_key": "task_index"}}}


def feature_stats(values):
    a = np.asarray(values, float)
    if a.ndim == 1:
        a = a[:, None]
    return {"mean": [float(v) for v in a.mean(0)],
            "std": [float(v) for v in a.std(0)],
            "min": [float(v) for v in a.min(0)],
            "max": [float(v) for v in a.max(0)],
            "q01": [float(v) for v in np.quantile(a, 0.01, axis=0)],
            "q99": [float(v) for v in np.quantile(a, 0.99, axis=0)]}


def write_groot_lerobot(out: Path, g1: G1, cbd: Cbd, columns, task, task_index,
                        video_size):
    """Write the GR00T-LeRobot dataset. Everything but the ego-view video, which
    only exists once the render has run."""
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "meta"
    meta.mkdir(exist_ok=True)
    height, width = video_size
    n = cbd.n

    features = {
        "observation.images.ego_view": {
            "dtype": "video", "shape": [height, width, 3],
            "names": ["height", "width", "channel"],
            "video_info": {"video.width": width, "video.height": height,
                           "video.fps": float(cbd.fps), "video.codec": "h264",
                           "video.pix_fmt": "yuv420p", "video.channels": 3,
                           "video.is_depth_map": False, "has_audio": False}},
        "observation.state": {"dtype": "float32", "shape": [43], "names": g1.order},
        "action": {"dtype": "float32", "shape": [43], "names": g1.order},
        "timestamp": {"dtype": "float64", "shape": [1]},
        "observation.eef_pose": {"dtype": "float64", "shape": [14]},
        "action.eef_pose": {"dtype": "float64", "shape": [14]},
        "teleop.base_height_command": {"dtype": "float32", "shape": [1]},
        "teleop.navigate_command": {"dtype": "float32", "shape": [3]},
        "teleop.torso_orientation_rpy_command": {"dtype": "float32", "shape": [3]},
        "annotation.human.task_description": {"dtype": "int64", "shape": [1]},
        "episode_index": {"dtype": "int64", "shape": [1]},
        "task_index": {"dtype": "int64", "shape": [1]},
        "index": {"dtype": "int64", "shape": [1]},
        "frame_index": {"dtype": "int64", "shape": [1]},
        "next.reward": {"dtype": "float64", "shape": [1]},
        "next.done": {"dtype": "bool", "shape": [1]},
        "observation.img_state_delta": {"dtype": "float64", "shape": [1]},
    }
    info = {
        "codebase_version": "v2.1", "robot_type": "unitree_g1",
        "total_episodes": 1, "total_frames": n, "total_tasks": 1,
        "total_videos": 1, "total_chunks": 1, "chunks_size": 1000,
        "fps": float(cbd.fps), "splits": {"train": "0:1"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/"
                      "episode_{episode_index:06d}.mp4",
        "features": features,
    }
    (meta / "info.json").write_text(json.dumps(info, indent=4), encoding="utf-8")
    (meta / "modality.json").write_text(json.dumps(modality_json(g1), indent=4),
                                        encoding="utf-8")
    (meta / "tasks.jsonl").write_text(
        json.dumps({"task_index": task_index, "task": task}) + "\n", encoding="utf-8")
    (meta / "episodes.jsonl").write_text(
        json.dumps({"episode_index": 0, "tasks": [task], "length": n}) + "\n",
        encoding="utf-8")
    (meta / "stats.json").write_text(json.dumps(
        {key: feature_stats(np.asarray(value, float) if key == "next.done" else value)
         for key, value in columns.items()}, indent=2), encoding="utf-8")

    data_dir = out / "data/chunk-000"
    data_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out / "videos/chunk-000/observation.images.ego_view"
    video_dir.mkdir(parents=True, exist_ok=True)

    written = None
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        rows = []
        for i in range(n):
            row = {}
            for key, value in columns.items():
                cell = value[i]
                row[key] = ([float(c) for c in cell] if np.ndim(cell)
                            else (bool(cell) if key == "next.done" else float(cell)))
            rows.append(json.dumps(row))
        written = data_dir / "episode_000000.jsonl"
        written.write_text("\n".join(rows) + "\n", encoding="utf-8")
    else:
        arrays, fields = [], []
        dtype = {"observation.state": pa.float32(), "action": pa.float32(),
                 "observation.eef_pose": pa.float64(), "action.eef_pose": pa.float64(),
                 "teleop.base_height_command": pa.float32(),
                 "teleop.navigate_command": pa.float32(),
                 "teleop.torso_orientation_rpy_command": pa.float32()}
        scalar = {"timestamp": pa.float64(), "annotation.human.task_description": pa.int64(),
                  "episode_index": pa.int64(), "task_index": pa.int64(),
                  "index": pa.int64(), "frame_index": pa.int64(),
                  "next.reward": pa.float64(), "next.done": pa.bool_(),
                  "observation.img_state_delta": pa.float64()}
        for key, value in columns.items():
            if key in scalar:
                arrays.append(pa.array(list(np.asarray(value).ravel()), type=scalar[key]))
                fields.append(pa.field(key, scalar[key]))
            else:
                cell = pa.list_(dtype[key])
                arrays.append(pa.array([[float(c) for c in row] for row in value],
                                       type=cell))
                fields.append(pa.field(key, cell))
        written = data_dir / "episode_000000.parquet"
        pq.write_table(pa.Table.from_arrays(arrays, schema=pa.schema(fields)), written)
    return written, video_dir / "episode_000000.mp4"


# --------------------------------------------------------------------------
# report / docs
# --------------------------------------------------------------------------

README_TEMPLATE = """# GR00T / Unitree G1 Output

Common Behavior Data retargeted onto a **Unitree G1** -- the embodiment NVIDIA
GR00T drives -- as a joint-space trajectory, a USD stage and a GR00T-LeRobot
dataset.

- `g1_robot.usda` ......... the robot: one Xform per G1 link, at the URDF's own origins
- `scene.usda` ............ the set: floor, backdrop, chair, table, lights, film camera
- `motion.usda` ........... **open this one.** Sublayers the two above and adds
  nothing but time samples
- `motion.npz` ............ joint angles, root pose and link frames as arrays
- `g1_joint_trajectory.csv` the 43 joint angles per frame, in the GR00T order
- `groot_lerobot/` ........ a GR00T-LeRobot v2.1 dataset (the Isaac Lab Arena G1 modality)
- `adapter_report.json` ... retarget residuals, joints on their limits, and what
  could not be represented
- `groot_g1_simulation.mp4` rendered video (same trajectory as the stage)

## Open it

```bash
./isaac-sim.sh --/app/file/openPath=<abs path>/motion.usda
usdview motion.usda           # nothing in the stage is Isaac-specific
```

## The 43 numbers

`observation.state` and `action` are the Unitree G1's 43 joints in the order
the Isaac Lab Arena G1 embodiment uses -- left leg (6), right leg (6), waist
(3), left arm (7), left Dex3 hand (7), right arm (7), right Dex3 hand (7).
`meta/modality.json` carries that slicing, so a GR00T loader configured for the
Arena G1 embodiment reads this dataset without changes.

`action[t]` is `state[t+1]`, with the last frame repeated: this is a kinematic
replay, so the commanded next pose *is* the next pose. No policy produced these
numbers and none is implied.

## Mode: retarget, not replay

The other CBD adapters measure the subject and animate a figure with the
subject's proportions. This one cannot: a G1 has fixed link lengths and hard
joint limits, so the human motion is solved into the robot's joint space by
matching **segment directions** -- where the upper arm, forearm, hand, thigh,
shank and foot point, in the frame of the joint that carries each -- under the
URDF's limits. What is left over is in `adapter_report.json`, in degrees, per
segment. Nothing is scaled to hide it.

The set is scaled instead. The one number in `adapter_report.json` under
`scale` is the ratio between the robot's own seated pelvis height and the
subject's; the floor, chair, table and camera are scaled by it and the robot
keeps its factory dimensions.

## Coordinate frames

| | Frame |
|---|---|
| Canonical CBD | Y-up, right-handed, subject faces +Z |
| Unitree G1 / URDF | Z-up, X forward, Y left, origin at the pelvis |
| This stage | Z-up, metres, robot faces -Y, camera on the -Y side |

Canonical to G1 is the cyclic relabelling `(x, y, z) -> (z, x, y)`, a proper
rotation. G1 to stage is a single -90 deg yaw, carried by the `/World/G1` root
Xform, so every link below it is in the robot's own frame and matches the URDF.
"""


def write_report(path, cbd: Cbd, g1: G1, dims, scale, accuracy, at_limit,
                 sett, camera_usd, plane, clip_log, foot_clearance,
                 extra_unrepresented, dataset_files):
    report = {
        "adapter": "cbd_adapter_groot_g1",
        "target": "NVIDIA GR00T / Unitree G1 (29 body DoF + two Dex3 hands) in Isaac Sim",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": {
            "manifest": os.path.relpath(cbd.dir / "manifest.json", Path(path).parent),
            "dataset_version": cbd.manifest.get("dataset_version"),
            "frame_count": cbd.n,
            "fps": cbd.fps,
        },
        "reads": [
            "timeline/frames.jsonl (bone_rotations_xyzw, hips_position, "
            "pose_canonical, finger_curls_rad, phase, caption)",
            "human/pose_landmarks.csv (paired normalized-image and canonical "
            "landmarks, for the image-plane fit)",
            "objects/object_detections.csv (chair / dining table boxes)",
            "manifest.json, behavior_summary.json",
        ],
        "writes": ["g1_robot.usda", "scene.usda", "motion.usda", "motion.npz",
                   "g1_joint_trajectory.csv", "groot_lerobot/",
                   "groot_g1_simulation.mp4"],
        "robot": {
            "model": g1.doc["_provenance"]["urdf_robot_name"],
            "kinematics_source": g1.doc["_provenance"]["derived_from"],
            "degrees_of_freedom": len(g1.order),
            "total_mass_kg": g1.doc["total_mass_kg"],
            "pelvis_to_ankle_m": round(g1.pelvis_to_ankle(), 4),
            "shoulder_to_palm_m": round(g1.shoulder_to_palm(), 4),
            "note": "hardware. Not one number here is derived from the dataset, "
                    "and none of it was stretched to fit the subject",
        },
        "coordinate_conversion": {
            "canonical": "Y-up, right-handed, subject faces +Z",
            "robot": "URDF/ROS: Z-up, X forward, Y left, origin at the pelvis",
            "target_stage": "USD Z-up, metres, robot faces -Y",
            "canonical_to_robot": "(x, y, z) -> (z, x, y); a permutation with "
                                  "determinant +1, so a rotation and not a flip",
            "robot_to_stage": "-90 deg about Z, carried by the /World/G1 root Xform",
        },
        "retarget": {
            "method": "per-frame damped least squares on segment *direction* "
                      "residuals, warm-started from the previous frame, with the "
                      "URDF's joint limits as box constraints",
            "matched": "upper arm, forearm, hand axis and palm normal (arms); "
                       "thigh, shank and foot forward (legs); the torso's "
                       "rotation relative to the pelvis, decomposed in the "
                       "waist chain's own Z-X-Y order (waist)",
            "not_matched": "absolute positions in metres. The G1's segments are "
                           "shorter than the subject's, so matching a reach in "
                           "metres would need either a resized robot or a "
                           "fabricated pose",
            "subject_dimensions_m": {k: round(float(v), 4) for k, v in dims.items()},
            "direction_error_deg": accuracy,
            "joints_resting_on_a_limit": at_limit,
            "clipped_outside_the_solver": clip_log,
        },
        "scale": {
            "value": round(float(scale), 5),
            "definition": "robot seated pelvis height (from its retargeted leg "
                          "pose, with factory link lengths) divided by the "
                          "subject's pelvis height above the derived floor",
            "applied_to": "floor, chair, table and camera -- not to the robot",
            "foot_clearance_above_floor_m": foot_clearance,
        },
        "set_placement": sett["provenance"],
        "camera": dict(camera_usd, plane_fit=plane),
        "groot_dataset": {
            "layout": "LeRobot v2.1",
            "embodiment": "Isaac Lab Arena G1 (43-DoF joint space, "
                          "`modality.json` groups: " + ", ".join(g1.groups) + ")",
            "state_and_action": "the 43 joint angles in radians, in that order",
            "action_definition": "action[t] = state[t+1], last frame repeated -- "
                                 "a kinematic replay, not a policy rollout",
            "eef_pose": EEF_HELP,
            "files": dataset_files,
        },
        "filled_or_interpolated": list(cbd.notes),
        "not_represented": list(cbd.unrepresented) + extra_unrepresented,
        "promoted_candidates": False,
        "policy_was_run": False,
    }
    Path(path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def segment_error(frames, targets, i, root_R, side, kind):
    """Angle, in degrees, between what the robot does and what the human did."""
    if kind == "arm":
        palm = np.array([0.0, -1.0, 0.0]) if side == "left" else np.array([0.0, 1.0, 0.0])
        pairs = {
            "upper_arm": (frames[f"{side}_elbow_link"][1]
                          - frames[f"{side}_shoulder_pitch_link"][1], targets["upper"]),
            "forearm": (frames[f"{side}_wrist_roll_link"][1]
                        - frames[f"{side}_elbow_link"][1], targets["fore"]),
            "hand_axis": (frames[f"{side}_hand_palm_link"][1]
                          - frames[f"{side}_wrist_roll_link"][1], targets["hand"]),
            "palm_normal": (frames[f"{side}_hand_palm_link"][0] @ palm, targets["palm"]),
        }
    else:
        pairs = {
            "thigh": (frames[f"{side}_knee_link"][1]
                      - frames[f"{side}_hip_pitch_link"][1], targets["thigh"]),
            "shank": (frames[f"{side}_ankle_pitch_link"][1]
                      - frames[f"{side}_knee_link"][1], targets["shank"]),
            "foot_forward": (frames[f"{side}_ankle_roll_link"][0]
                             @ np.array([1.0, 0.0, 0.0]), targets["foot"]),
        }
    return {name: float(angle_between_deg(got, dir_in(root_R, want[i])))
            for name, (got, want) in pairs.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True,
                    help="directory containing 04_behavior_dataset/, the dataset "
                         "itself, or the generator's cbd_dataset.zip")
    ap.add_argument("--output", default=None,
                    help="output root; default: alongside 04_behavior_dataset/")
    ap.add_argument("--workdir", default=None,
                    help="where to unpack a zip; default: <zip>_unpacked beside it")
    ap.add_argument("--width", type=int, default=720, help="film render width")
    ap.add_argument("--height", type=int, default=1280, help="film render height")
    ap.add_argument("--ego-width", type=int, default=640, help="ego-view width")
    ap.add_argument("--ego-height", type=int, default=480, help="ego-view height")
    ap.add_argument("--task-index", type=int, default=0,
                    help="task_index recorded in the GR00T dataset")
    args = ap.parse_args()

    dataset_dir, unpacked_from = open_dataset(args.dataset, args.workdir)
    out_root = Path(args.output).expanduser().resolve() if args.output \
        else dataset_dir.parent
    out = out_root / "06_groot_g1"
    out.mkdir(parents=True, exist_ok=True)

    cbd = Cbd(dataset_dir)
    g1 = G1()
    print(f"Common Behavior Data: {dataset_dir}")
    print(f"frames={cbd.n}  fps={cbd.fps:.2f}  duration={cbd.timestamps[-1]:.2f}s")
    print(f"target: {g1.doc['_provenance']['urdf_robot_name']}, "
          f"{len(g1.order)} DoF, {g1.doc['total_mass_kg']} kg")

    # ---- the subject, in canonical space ---------------------------------
    dims = measure_subject(cbd)
    hip_centre = (cbd.pose[:, LM["l_hip"]] + cbd.pose[:, LM["r_hip"]]) / 2.0
    root_c = hip_centre + (cbd.hips_pos - np.median(cbd.hips_pos, axis=0))
    cbd.notes.append(
        "root translation: hips_position is a translation offset with an "
        "arbitrary origin, so it is de-meaned and added to the canonical hip "
        "centre; that keeps the root consistent with the same landmark set the "
        "floor height is measured from")
    world_rot, world_pos, _ = human_fk(cbd, dims, root_c)

    # Rule 5, before anything is solved: if a canonical limb landmark sits on
    # the wrong side of the body from the joint it hangs off, the retarget will
    # reproduce that faithfully and the robot will look cross-legged. Say so
    # here rather than let the render be blamed for it.
    for label, joint, anchor_lm, anchor_name in (("knee", "knee", "hip", "hip"),
                                                ("ankle", "ank", "hip", "hip"),
                                                ("wrist", "wri", "sh", "shoulder")):
        for side, sign in (("l", 1.0), ("r", -1.0)):
            base = float(np.median(cbd.pose[:, LM[f"{side}_{anchor_lm}"], 0]))
            tip = float(np.median(cbd.pose[:, LM[f"{side}_{joint}"], 0]))
            if sign * (tip - base) < -0.04:
                cbd.notes.append(
                    f"canonical landmarks: the {'left' if side == 'l' else 'right'} "
                    f"{label} sits {abs(tip - base) * 100:.0f} cm across the body "
                    f"midline from its {anchor_name}, which a monocular capture of a "
                    "seated subject does produce. The retarget reproduces it rather "
                    "than correcting it")

    # ---- retarget --------------------------------------------------------
    rt = Retargeter(g1, cbd, world_rot, world_pos)
    q = np.zeros((cbd.n, len(g1.order)))
    pelvis_R = np.zeros((cbd.n, 3, 3))
    clip_log, errors = {}, {}
    warm = {("arm", "left"): np.zeros(7), ("arm", "right"): np.zeros(7),
            ("leg", "left"): np.zeros(6), ("leg", "right"): np.zeros(6)}
    for i in range(cbd.n):
        waist = rt.waist(i, clip_log)
        for name, value in zip(G1.WAIST, waist):
            q[i, g1.index[name]] = value
        pelvis_R[i] = rt._pelvis_R(i)
        torso_R = pelvis_R[i] @ g1.chain_frames(G1.WAIST, waist)["torso_link"][0]
        for side in ("left", "right"):
            x, _, _ = rt.arm(i, side, torso_R, warm[("arm", side)])
            warm[("arm", side)] = x
            chain = [n for n in g1.arm(side) if g1.joints[n]["type"] == "revolute"]
            for name, value in zip(chain, x):
                q[i, g1.index[name]] = value
            for key, value in segment_error(g1.chain_frames(g1.arm(side), x),
                                            rt.arm_targets[side], i, torso_R,
                                            side, "arm").items():
                errors.setdefault(f"{side}_{key}", []).append(value)

            y, _, _ = rt.leg(i, side, warm[("leg", side)])
            warm[("leg", side)] = y
            for name, value in zip(g1.leg(side), y):
                q[i, g1.index[name]] = value
            for key, value in segment_error(g1.chain_frames(g1.leg(side), y),
                                            rt.leg_targets[side], i, pelvis_R[i],
                                            side, "leg").items():
                errors.setdefault(f"{side}_{key}", []).append(value)

            for name, value in rt.hand(i, side, clip_log).items():
                q[i, g1.index[name]] = value

    accuracy = {k: {"mean_deg": round(float(np.mean(v)), 2),
                    "max_deg": round(float(np.max(v)), 2)} for k, v in errors.items()}
    every = np.concatenate([np.array(v) for k, v in errors.items()])
    accuracy["all_segments"] = {"mean_deg": round(float(every.mean()), 2),
                                "max_deg": round(float(every.max()), 2)}
    print(f"retarget direction error: mean {accuracy['all_segments']['mean_deg']} deg, "
          f"max {accuracy['all_segments']['max_deg']} deg")

    # A joint pinned to its limit is where the robot ran out of travel. It is
    # not an error the solver can fix, and it is the honest way to say the G1
    # cannot do what the subject did.
    at_limit = {}
    for j, name in enumerate(g1.order):
        lo, hi = g1.limit[j]
        hits = int(((q[:, j] <= lo + 1e-6) | (q[:, j] >= hi - 1e-6)).sum())
        if hits:
            at_limit[name] = {"frames": hits, "of": cbd.n,
                              "limit_rad": [round(float(lo), 4), round(float(hi), 4)]}

    # ---- scale: the robot sets it, the room follows ----------------------
    local = [g1.full_frames(q[i]) for i in range(cbd.n)]
    # the lowest point of each sole, in the pelvis frame and then turned by the
    # pelvis's own orientation -- which is what decides how high the pelvis has
    # to be for the robot's feet to reach the floor
    sole_offset = np.array([
        [(pelvis_R[i] @ (local[i][f"{s}_ankle_roll_link"][0]
                         @ np.array([0.022, 0.0, -SOLE_BELOW_ANKLE])
                         + local[i][f"{s}_ankle_roll_link"][1]))[2]
         for s in ("left", "right")] for i in range(cbd.n)])
    h_robot = float(np.median(-sole_offset.min(axis=1)))
    h_human = float(np.median(root_c[:, 1] - dims["floor_y"]))
    scale = h_robot / h_human
    pelvis_t = scale * vec_c_to_r(root_c - np.array([0.0, dims["floor_y"], 0.0]))
    world_sole = pelvis_t[:, 2:3] + sole_offset
    foot_clearance = {"median_m": round(float(np.median(world_sole.min(axis=1))), 4),
                      "min_m": round(float(world_sole.min()), 4),
                      "max_m": round(float(world_sole.max()), 4)}
    print(f"scale: {scale:.4f}  (robot seated pelvis {h_robot:.3f} m / "
          f"subject {h_human:.3f} m); feet sit "
          f"{foot_clearance['median_m'] * 100:+.1f} cm off the floor")

    # ---- the set and the camera ------------------------------------------
    plane = fit_image_plane(cbd)
    if plane is None:
        cbd.notes.append("image-plane fit unavailable (human/pose_landmarks.csv "
                         "missing): set and camera fall back to adapter defaults")
    sett = derive_set(cbd, dims, world_pos, plane, scale)
    camera = derive_camera(cbd, plane, scale, dims["floor_y"], args.width, args.height)

    # ---- the three layers -------------------------------------------------
    link_path = write_robot_usd(out / "g1_robot.usda", g1,
                                args.ego_width, args.ego_height)
    camera_usd = write_scene_usd(out / "scene.usda", sett, camera,
                                 args.width, args.height)
    write_motion_usd(out / "motion.usda", "./g1_robot.usda", "./scene.usda",
                     g1, link_path, cbd, q, pelvis_R, pelvis_t)
    print(f"Wrote: {out/'g1_robot.usda'} / scene.usda / motion.usda")

    # ---- joint trajectory --------------------------------------------------
    with (out / "g1_joint_trajectory.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["frame", "timestamp_sec"] + g1.order)
        for i in range(cbd.n):
            writer.writerow([i, round(float(cbd.timestamps[i]), 4)]
                            + [round(float(v), 6) for v in q[i]])

    # ---- the GR00T-LeRobot dataset ----------------------------------------
    eef = np.zeros((cbd.n, 14))
    for i, frames in enumerate(local):
        for k, side in enumerate(("left", "right")):
            R, t = frames[f"{side}_hand_palm_link"]
            eef[i, k * 7:k * 7 + 3] = t
            eef[i, k * 7 + 3:k * 7 + 7] = mat_to_q(R)
    action = np.vstack([q[1:], q[-1:]])
    action_eef = np.vstack([eef[1:], eef[-1:]])
    yaw = np.array([math.atan2(R[1, 0], R[0, 0]) for R in pelvis_R])
    velocity = np.zeros((cbd.n, 3))
    velocity[:-1, :2] = np.einsum("nji,nj->ni", pelvis_R[:-1, :2, :2],
                                  np.diff(pelvis_t[:, :2], axis=0)) * cbd.fps
    velocity[:-1, 2] = np.diff(np.unwrap(yaw)) * cbd.fps
    velocity[-1] = velocity[-2] if cbd.n > 1 else 0.0
    waist_cols = [q[:, g1.index[n]] for n in ("waist_roll_joint", "waist_pitch_joint",
                                              "waist_yaw_joint")]
    columns = {
        "observation.state": q,
        "action": action,
        "timestamp": cbd.timestamps,
        "observation.eef_pose": eef,
        "action.eef_pose": action_eef,
        "teleop.base_height_command": pelvis_t[:, 2:3],
        "teleop.navigate_command": velocity,
        "teleop.torso_orientation_rpy_command": np.column_stack(waist_cols),
        "annotation.human.task_description": np.full(cbd.n, args.task_index),
        "episode_index": np.zeros(cbd.n, int),
        "task_index": np.full(cbd.n, args.task_index),
        "index": np.arange(cbd.n),
        "frame_index": np.arange(cbd.n),
        "next.reward": np.zeros(cbd.n),
        "next.done": np.array([i == cbd.n - 1 for i in range(cbd.n)]),
        "observation.img_state_delta": np.zeros(cbd.n),
    }
    task = cbd.task_text()
    episode, ego_video = write_groot_lerobot(
        out / "groot_lerobot", g1, cbd, columns, task, args.task_index,
        (args.ego_height, args.ego_width))
    print(f"GR00T dataset: {episode.parent.parent.parent}  task={task!r}")

    # ---- motion.npz --------------------------------------------------------
    np.savez_compressed(
        out / "motion.npz",
        joint_names=np.array(g1.order),
        joint_angles_rad=q.astype(np.float32),
        joint_limits_rad=g1.limit.astype(np.float32),
        pelvis_position_robot=pelvis_t.astype(np.float32),
        pelvis_orientation_wxyz=np.stack([mat_to_q(R) for R in pelvis_R]).astype(np.float32),
        eef_pose_pelvis_frame=eef.astype(np.float32),
        set_scale=np.array([scale], dtype=np.float32),
        fps=np.array([cbd.fps], dtype=np.float32),
        timestamp_sec=cbd.timestamps.astype(np.float32),
        up_axis=np.array(["Z"]),
        frame="G1/URDF: X forward, Y left, Z up, origin at the pelvis",
    )

    # ---- a derived view inside the dataset ---------------------------------
    adapters_dir = cbd.dir / "adapters"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    with (adapters_dir / "groot_g1_joint_angles.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["frame", "timestamp_sec", "group", "joint", "angle_rad",
                         "lower_rad", "upper_rad", "at_limit"])
        group_of = {n: g for g, names in g1.groups.items() for n in names}
        for i in range(cbd.n):
            for j, name in enumerate(g1.order):
                lo, hi = g1.limit[j]
                writer.writerow([i, round(float(cbd.timestamps[i]), 4), group_of[name],
                                 name, round(float(q[i, j]), 6), round(float(lo), 5),
                                 round(float(hi), 5),
                                 int(q[i, j] <= lo + 1e-6 or q[i, j] >= hi - 1e-6)])

    # ---- what it could not do ----------------------------------------------
    # Counted, not asserted: how much evidence the dataset actually carries for
    # the primary object being handled at all.
    hits = sum(1 for d in cbd.object_detections() if d.get("label") == cbd.primary_label)
    events = len(cbd.interaction_events())
    extra = [
        "the primary object: no glass, cup or other prop is placed. This clip "
        f"carries {hits} `{cbd.primary_label}` detection(s) over {cbd.n} frames, "
        f"{events} interaction event(s), and no per-frame canonical position for "
        "it, so there is no evidence the object was ever grasped or moved. The "
        "table's height is still derived from the primary hand's furthest reach "
        "-- see set_placement",
        "physics: this is a kinematic replay. The stage carries no rigid bodies, "
        "no articulation drives and no contact, so nothing here is a dynamically "
        "feasible G1 trajectory -- joint velocity, torque and balance limits are "
        "not checked",
        "the head: the G1's 29-DoF configuration has no neck joint, so the "
        "subject's head orientation is dropped entirely",
        "ring and little fingers: the Dex3 hand has three fingers, so two of the "
        "five CBD finger curls have nowhere to go",
        "thumb abduction: the CBD schema has no thumb abduction channel, so "
        f"`thumb_0` is driven to {Retargeter.THUMB_OPPOSITION} rad of opposition "
        "in proportion to the measured thumb flexion. That is an adapter choice, "
        "not a measurement",
    ]
    identity = [b for b in cbd.bone_order if np.allclose(cbd.rot[b][:, 0], 1.0, atol=1e-6)]
    if identity:
        extra.append("bones with no rotation signal in the dataset (written as "
                     "identity, not estimated), so the joints that would have "
                     "carried them stay at zero: " + ", ".join(identity))
    if cbd.manifest.get("face_landmark_count", 0) == 0:
        extra.append("face: no face landmarks or blendshapes in the dataset")
    if not ego_video.exists():
        extra.append(
            "the ego-view video the GR00T dataset declares is written by the "
            "render step, not by this one: run groot_g1_render.py and "
            "compose_video.py")

    (out / "README_GROOT_G1.md").write_text(README_TEMPLATE, encoding="utf-8")
    dataset_files = {
        "episode": os.path.relpath(episode, out),
        "ego_view_video": os.path.relpath(ego_video, out),
        "ego_view_written_by": "compose_video.py, after groot_g1_render.py",
    }
    report = write_report(out / "adapter_report.json", cbd, g1, dims, scale, accuracy,
                          at_limit, sett, camera_usd, plane, clip_log,
                          foot_clearance, extra, dataset_files)

    print(f"\ncamera: focal {camera_usd['focal_length_mm']:.1f} mm, "
          f"hFOV {camera_usd['horizontal_fov_deg']:.1f} deg")
    print("joints resting on a limit:")
    for name, info in sorted(at_limit.items(), key=lambda kv: -kv[1]["frames"])[:8]:
        print(f"  {name}: {info['frames']}/{info['of']} frames")
    print("\ncould not represent:")
    for line in report["not_represented"]:
        print(f"  - {line}")
    print(f"\nWrote: {out}")


if __name__ == "__main__":
    main()
