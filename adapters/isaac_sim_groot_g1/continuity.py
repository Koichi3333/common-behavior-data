#!/usr/bin/env python3
"""Repair the discontinuities a clipped retarget leaves behind.

The physics pass leaves one joint outside tolerance:
`right_wrist_yaw_joint`, 22.06 deg. It is not a systematic tracking failure --
the joint's mean error over the clip is 0.53 deg and only one frame of 96 is
above 10. Frame 71 is the whole of it, and the cause is upstream:

    frame            68      69       70       71       72
    wrist roll    -34.3  -113.0*  -113.0*   -33.0    -36.6      * = at its limit
    wrist yaw      -6.1    +39.8    +47.5    -39.6    -48.1

The roll axis saturates at exactly its limit for two frames -- the retarget
asked for a wrist orientation the G1 cannot reach -- and the yaw swings 87 deg
in one frame coming out of it. That is a Euler branch flip through a clipped
singularity, and no drive follows an 87 deg step in 1/12 s on a joint whose
effort limit is 5 N.m, the smallest on the robot. (Its *velocity* limit,
22 rad/s, is 105 deg per frame: velocity was never the constraint. Torque was.)

So the repair belongs here rather than in the gains: interpolate through the
clipped run, so the trajectory only asks for orientations the wrist can hold.

**Selective on purpose.** Saturation is not by itself a defect: the foot-contact
solve deliberately drives ankles and hips onto their limits to put the soles on
the floor, and those runs are smooth on both sides. Only a run whose boundary
carries a jump far outside the joint's own habit is repaired -- so this pass
never undoes the one before it.
"""
from __future__ import annotations

import numpy as np

import re

LIMIT_TOL = 1e-3            # this close to a limit counts as saturated
# Three axes of one wrist are one orientation. When the decomposition clips on
# any of them the whole triple is unreliable over that run -- on the sample the
# roll saturates and the *yaw* is what jumps 87 deg, so repairing only the
# saturated axis leaves the discontinuity exactly where it was.
_AXIS = re.compile(r"^(?P<chain>.+)_(roll|pitch|yaw)_joint$")
JUMP_DEG = 20.0             # a boundary step smaller than this is not a flip
JUMP_RATIO = 5.0            # ... nor is one within this much of the joint's habit


def _runs(mask):
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def _chain_of(name):
    m = _AXIS.match(name)
    return m.group("chain") if m else None


def repair(q, joint_names, limits, jump_deg=JUMP_DEG, ratio=JUMP_RATIO,
           prov=None, dev=None):
    """Smooth through limit-clipped runs that end in a discontinuity."""
    q = np.array(q, dtype=float, copy=True)
    original = q.copy()
    limits = np.asarray(limits, float)
    before = np.abs(np.diff(q, axis=0)).max(axis=0)
    repaired = []
    chains = {}
    for i, name in enumerate(joint_names):
        c = _chain_of(name)
        if c:
            chains.setdefault(c, []).append(i)

    def _interp(col_i, a, b):
        lhs, rhs = q[a - 1, col_i], q[b + 1, col_i]
        k = b - a + 2
        q[a:b + 1, col_i] = lhs + (rhs - lhs) * (np.arange(1, k) / k)

    for i, name in enumerate(joint_names):
        lo, hi = limits[i]
        col = original[:, i]
        sat = (np.abs(col - lo) < LIMIT_TOL) | (np.abs(col - hi) < LIMIT_TOL)
        if not sat.any():
            continue
        step = np.abs(np.diff(col))
        habit = float(np.median(step[step > 1e-9])) if (step > 1e-9).any() else 0.0
        for a, b in _runs(sat):
            if a == 0 or b == len(col) - 1:
                continue                      # no good frame on one side
            jump = max(abs(col[a] - col[a - 1]), abs(col[b + 1] - col[b]))
            if np.degrees(jump) < jump_deg or jump < ratio * habit:
                continue                      # a sustained clamp, not a flip
            group = chains.get(_chain_of(name)) or [i]
            for k in group:
                _interp(k, a, b)
            repaired.append({
                "joint": name, "chain_repaired": [joint_names[k] for k in group],
                "frames": [a, b],
                "was_deg": [round(float(np.degrees(original[f, i])), 2)
                            for f in (a, b)],
                "now_deg": [round(float(np.degrees(q[f, i])), 2) for f in (a, b)],
                "boundary_jump_deg": round(float(np.degrees(jump)), 2),
                "joint_habit_deg": round(float(np.degrees(habit)), 3)})

    after = np.abs(np.diff(q, axis=0)).max(axis=0)
    report = {
        "rule": ("interpolate through a run clipped to a joint limit when the "
                 "step at its boundary is both > %.0f deg and > %.0fx the "
                 "joint's median step" % (jump_deg, ratio)),
        "repaired": repaired,
        "worst_step_deg": {"before": round(float(np.degrees(before.max())), 2),
                           "after": round(float(np.degrees(after.max())), 2)},
    }
    if prov and repaired:
        prov.synthesized(
            "joint.continuity",
            "clipped wrist run interpolated -- the commanded orientation was "
            "outside the joint's range and coming out of it was a step no "
            "drive can follow",
            sum(r["frames"][1] - r["frames"][0] + 1 for r in repaired),
            spec_gap=None)
    if dev and repaired:
        dev.record("retarget.worst_command_step", "retarget", 0.0,
                   float(np.degrees(before.max())), "deg", tolerance=30.0,
                   how="largest single-frame command step before the repair")
        dev.record("retarget.worst_command_step_repaired", "retarget", 0.0,
                   float(np.degrees(after.max())), "deg", tolerance=30.0,
                   how="after the repair")
    return q, report
