#!/usr/bin/env python3
"""Anatomical cleanup of canonical landmarks, before anything is retargeted.

v1 did not do this, and said so:

    "the right knee sits 19 cm across the body midline from its hip, which a
     monocular capture of a seated subject does produce. The retarget
     reproduces it rather than correcting it"

Four entries like that in one 96-frame clip. Reproducing them is faithful to
the capture and destructive to the target: a knee 19 cm across the midline puts
the thigh inside the other thigh, and no amount of self-collision cost
downstream can undo a pose that was already impossible when it arrived. The
penetration this adapter is accused of starts here, not in the IK.

So: correct upstream, and declare the correction. Three passes, in this order.

1. **smooth** -- a short binomial kernel over positions. Monocular depth is
   noisy frame to frame; smoothing first keeps the later passes from chasing
   jitter.
2. **midline** -- a landmark may not sit arbitrarily far across the body's own
   centre line. Legs are held strictly: a seated subject's knees and ankles do
   not cross. **Arms are not** -- reaching across the body is ordinary, and the
   sample clip does exactly that (right hand to a table on the subject's left).
   Confusing the two would delete real motion, so the limits differ by chain.
3. **segments** -- rebuild every limb from the pelvis using the *median* bone
   length and the per-frame *direction*. Direction is what the retarget
   consumes, so nothing it cares about is thrown away, while the lengths stop
   breathing (up to 23% over one clip) and geometric impossibilities go with
   them -- a wrist 5% further from its shoulder than the arm is long cannot
   survive a chain built from fixed segments.

What this deliberately does not do: it does not make the motion prettier, only
possible. That bound is the whole reason it is safe to run by default -- see
the design note, minimum-intervention principle.

Every number below is reported before and after, so the cost of the correction
is visible rather than assumed.
"""
from __future__ import annotations

import numpy as np

LM = {"nose": 0, "l_ear": 7, "r_ear": 8, "l_sh": 11, "r_sh": 12,
      "l_elb": 13, "r_elb": 14, "l_wri": 15, "r_wri": 16,
      "l_idx": 19, "r_idx": 20, "l_hip": 23, "r_hip": 24,
      "l_knee": 25, "r_knee": 26, "l_ank": 27, "r_ank": 28,
      "l_heel": 29, "r_heel": 30, "l_toe": 31, "r_toe": 32}

# canonical CBD is x = right, y = up, z = toward the camera, subject facing +z,
# so the subject's own left sits at +x. Verified on the sample dataset:
# l_hip x = +0.123, r_hip x = -0.122.
SIDE_SIGN = {"l": +1.0, "r": -1.0}

# child, parent, segment name -- walked in order, so a parent is always fixed
# before its children.
CHAIN = [
    ("l_sh", "c_sh", "sh_half"), ("r_sh", "c_sh", "sh_half"),
    ("l_elb", "l_sh", "upper_arm"), ("l_wri", "l_elb", "lower_arm"),
    ("l_idx", "l_wri", "hand"),
    ("r_elb", "r_sh", "upper_arm"), ("r_wri", "r_elb", "lower_arm"),
    ("r_idx", "r_wri", "hand"),
    ("l_hip", "c_hip", "hip_half"), ("r_hip", "c_hip", "hip_half"),
    ("l_knee", "l_hip", "upper_leg"), ("l_ank", "l_knee", "lower_leg"),
    ("l_heel", "l_ank", "heel"), ("l_toe", "l_ank", "foot"),
    ("r_knee", "r_hip", "upper_leg"), ("r_ank", "r_knee", "lower_leg"),
    ("r_heel", "r_ank", "heel"), ("r_toe", "r_ank", "foot"),
    ("nose", "c_sh", "neck_to_nose"),
    ("l_ear", "nose", "ear"), ("r_ear", "nose", "ear"),
]

# segments measured per side and then averaged, so left and right match
PAIRED = {"upper_arm", "lower_arm", "hand", "upper_leg", "lower_leg",
          "foot", "heel", "ear"}

# how far a landmark may sit on the wrong side of the body midline, as a
# fraction of the pelvis half-width. Legs: essentially not at all. Arms: freely
# -- crossing the body to reach is normal motion, not capture error.
MIDLINE_LIMIT = {"l_knee": 0.3, "r_knee": 0.3, "l_ank": 0.3, "r_ank": 0.3,
                 "l_heel": 0.3, "r_heel": 0.3, "l_toe": 0.4, "r_toe": 0.4}


def _binomial_kernel(width: int):
    k = np.array([1.0])
    for _ in range(max(0, width - 1)):
        k = np.convolve(k, [0.5, 0.5])
    return k / k.sum()


def smooth(p: np.ndarray, width: int = 5) -> np.ndarray:
    """Binomial smoothing along time, edges held by reflection."""
    if p.shape[0] < 3 or width < 2:
        return p.copy()
    k = _binomial_kernel(width)
    pad = len(k) // 2
    padded = np.concatenate([p[pad:0:-1], p, p[-2:-2 - pad:-1]], axis=0)
    out = np.empty_like(p)
    for i in range(p.shape[1]):
        for a in range(p.shape[2]):
            out[:, i, a] = np.convolve(padded[:, i, a], k, mode="valid")
    return out


def _centres(p):
    return ((p[:, LM["l_hip"]] + p[:, LM["r_hip"]]) / 2.0,
            (p[:, LM["l_sh"]] + p[:, LM["r_sh"]]) / 2.0)


def measure_segments(p: np.ndarray):
    """Median length of every segment in CHAIN, left and right averaged."""
    c_hip, c_sh = _centres(p)
    pos = {"c_hip": c_hip, "c_sh": c_sh}
    for name, i in LM.items():
        pos[name] = p[:, i]
    raw = {}
    for child, parent, seg in CHAIN:
        d = float(np.median(np.linalg.norm(pos[child] - pos[parent], axis=1)))
        raw.setdefault(seg, []).append(d)
    return {seg: float(np.mean(v)) if seg in PAIRED else float(np.mean(v))
            for seg, v in raw.items()}


def midline_report(p: np.ndarray, dims=None):
    """How far each limited landmark sits on the wrong side of the midline.

    `beyond_limit_frames` is the one that has to reach zero: a small crossing is
    allowed (MIDLINE_LIMIT), because real pelvises are not knife edges.
    """
    c_hip, _ = _centres(p)
    half = (dims or measure_segments(p)).get("hip_half", 0.12)
    out = {}
    for name, limit in MIDLINE_LIMIT.items():
        side = SIDE_SIGN[name[0]]
        # signed distance onto the subject's own side; negative = crossed over
        own = (p[:, LM[name], 0] - c_hip[:, 0]) * side
        crossed = np.maximum(0.0, -own)
        allow = limit * half
        out[name] = {"mean_cross_m": round(float(crossed.mean()), 4),
                     "max_cross_m": round(float(crossed.max()), 4),
                     "allowed_m": round(float(allow), 4),
                     "frames_crossed": int((crossed > 1e-4).sum()),
                     "beyond_limit_frames": int((crossed > allow + 1e-4).sum())}
    return out


def segment_report(p: np.ndarray):
    c_hip, c_sh = _centres(p)
    pos = {"c_hip": c_hip, "c_sh": c_sh}
    for name, i in LM.items():
        pos[name] = p[:, i]
    out = {}
    for child, parent, seg in CHAIN:
        d = np.linalg.norm(pos[child] - pos[parent], axis=1)
        med = float(np.median(d))
        if med < 1e-6:
            continue
        out[f"{child}<-{parent}"] = round(float((d.max() - d.min()) / med), 4)
    return out


def reach_report(p: np.ndarray):
    """End-effector distance over the chain length -- above 1.0 is impossible."""
    out = {}
    for side in ("l", "r"):
        sh, elb, wri = p[:, LM[f"{side}_sh"]], p[:, LM[f"{side}_elb"]], p[:, LM[f"{side}_wri"]]
        chain = (np.median(np.linalg.norm(sh - elb, axis=1))
                 + np.median(np.linalg.norm(elb - wri, axis=1)))
        out[f"{side}_arm"] = round(float(np.linalg.norm(wri - sh, axis=1).max() / chain), 4)
        hip, kn, ank = p[:, LM[f"{side}_hip"]], p[:, LM[f"{side}_knee"]], p[:, LM[f"{side}_ank"]]
        chain = (np.median(np.linalg.norm(hip - kn, axis=1))
                 + np.median(np.linalg.norm(kn - ank, axis=1)))
        out[f"{side}_leg"] = round(float(np.linalg.norm(ank - hip, axis=1).max() / chain), 4)
    return out


def _clamp_direction(parent, unit, length, name, c_hip, half):
    """Bend a segment's direction so its tip stops at the midline boundary.

    Clamping the *position* and then rebuilding at a fixed length undoes the
    clamp -- the median segment is often longer than the frame's own, so the
    tip travels back across. Clamping the direction instead keeps the segment
    length exact and the constraint satisfied at the same time.
    """
    side = SIDE_SIGN[name[0]]
    allow = MIDLINE_LIMIT[name] * half
    boundary = c_hip[:, 0] - side * allow          # furthest x it may reach
    tip_x = parent[:, 0] + unit[:, 0] * length
    over = (tip_x - boundary) * side < 0.0         # crossed past the boundary
    if not over.any():
        return unit, np.zeros(len(unit), bool), 0.0
    want_x = (boundary - parent[:, 0]) / max(length, 1e-9)
    want_x = np.clip(want_x, -1.0, 1.0)
    out = unit.copy()
    push = np.abs(tip_x - boundary)
    # replace the lateral component, then rescale the rest to keep |unit| = 1
    rest = np.linalg.norm(unit[:, 1:], axis=1)
    keep = np.sqrt(np.maximum(0.0, 1.0 - want_x ** 2))
    scale = np.where(rest < 1e-9, 0.0, keep / np.where(rest < 1e-9, 1.0, rest))
    out[over, 0] = want_x[over]
    out[over, 1:] = unit[over, 1:] * scale[over, None]
    return out, over, float(push[over].max())


def _rebuild(p: np.ndarray, dims, clamp: bool = True):
    """Rebuild the skeleton from the pelvis with fixed segment lengths.

    The midline clamp happens here, inside the walk, so a clamped parent's
    children are placed from its corrected position rather than patched after.
    """
    out = p.copy()
    c_hip, c_sh = _centres(p)
    half = dims.get("hip_half", 0.12)
    pos = {"c_hip": c_hip}
    # the torso first: shoulder centre at its median distance from the pelvis
    d = c_sh - c_hip
    n = np.linalg.norm(d, axis=1, keepdims=True)
    pos["c_sh"] = c_hip + np.divide(d, np.where(n < 1e-9, 1.0, n)) * float(np.median(n))
    clamped = {}
    for child, parent, seg in CHAIN:
        raw_p = pos[parent] if parent in ("c_hip", "c_sh") else pos[parent]
        d = p[:, LM[child]] - (p[:, LM[parent]] if parent not in ("c_hip", "c_sh")
                               else (c_hip if parent == "c_hip" else c_sh))
        n = np.linalg.norm(d, axis=1, keepdims=True)
        unit = np.divide(d, np.where(n < 1e-9, 1.0, n))
        length = dims[seg]
        if clamp and child in MIDLINE_LIMIT:
            unit, over, push = _clamp_direction(raw_p, unit, length, child, c_hip, half)
            if over.any():
                clamped[child] = {"frames": int(over.sum()),
                                  "max_push_m": round(push, 4)}
        pos[child] = raw_p + unit * length
        out[:, LM[child]] = pos[child]
    return out, clamped


def clean(pose: np.ndarray, smooth_width: int = 5):
    """Return (cleaned pose, report). `pose` is (frames, 33, 3) canonical.

    Landmarks outside CHAIN (face and hand detail) pass through smoothed only.
    """
    dims0 = measure_segments(pose)
    before = {"midline": midline_report(pose, dims0), "segment_drift": segment_report(pose),
              "reach_ratio": reach_report(pose)}

    smoothed = smooth(pose, smooth_width)
    dims = measure_segments(smoothed)
    rebuilt, moved = _rebuild(smoothed, dims)

    after = {"midline": midline_report(rebuilt, dims), "segment_drift": segment_report(rebuilt),
             "reach_ratio": reach_report(rebuilt)}
    disp = np.linalg.norm(rebuilt - pose, axis=2)
    report = {
        "applied": ["binomial smoothing (width %d)" % smooth_width,
                    "segment rebuild from the pelvis at median bone lengths, "
                    "with the midline clamp applied in direction space "
                    "(legs %.1fx pelvis half-width; arms unlimited)"
                    % MIDLINE_LIMIT["l_knee"]],
        "midline_clamped": moved,
        "displacement_m": {"mean": round(float(disp.mean()), 4),
                           "max": round(float(disp.max()), 4),
                           "p95": round(float(np.percentile(disp, 95)), 4)},
        "before": before, "after": after,
        "segment_lengths_m": {k: round(v, 4) for k, v in sorted(dims.items())},
    }
    return rebuilt, report
