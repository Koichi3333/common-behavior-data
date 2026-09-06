#!/usr/bin/env python3
"""Put the feet on the floor the retarget forgot about.

The physics pass measures a 0.2014 m foot error and blames the trajectory for
half of it, under `retarget.commanded_feet_on_floor`: with the pelvis exactly
where the retarget asked, v1's own joint angles put the soles between -0.055 m
and +0.103 m. Physics cannot put a foot on a floor the trajectory never sends it
to, so this is the stage that owes the fix.

The source capture is no better -- the subject's own landmarks have her left
foot 0 to 0.08 m above the floor plane and her right 0.023 to 0.114 m, over 96
frames in which she is seated and never moves her legs. A seated person's feet
do not bob 11 cm. That is monocular depth noise, and reproducing it is the v1
failure this whole revision exists to stop.

So: derive *contact* from the clip rather than heights from the capture. Seated
with no locomotion phase means both feet are down for the whole clip, and the
correction is whatever smallest change to the six leg joints puts each sole on
the floor. Damped least-norm with the joint limits as bounds -- of the many leg
poses that reach the floor it takes the one nearest the commanded pose, which is
the minimum-intervention rule the design asks for, expressed as arithmetic
rather than as a promise.

**A sole is four corners, not one point.** The first version of this solve
constrained the point directly under the ankle, and so did the check that
graded it, so both agreed the feet were within 10 mm of the floor while the
robot's toes were 53 to 87 mm underneath it -- visible in the render, invisible
in every number the pipeline produced. The foot has four contact spheres in the
URDF and the ankle carries 27 to 30 deg of commanded pitch; constraining one
point leaves the polygon free to rotate about it. Four corner heights pin the
plane instead, which is three constraints on a six-joint leg and still leaves
the solve underdetermined, so the minimum-intervention property is unchanged.

    commanded sole corners   -0.118 .. +0.182  ->  -0.000 .. +0.004 m
    deepest penetration       0.118            ->   0.000 m
    worst foot tilt           0.101            ->   0.001 m
    cost                      24.7 deg, right ankle pitch

Arms, waist and hands are not touched. Nothing about the reach changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from invariants import (FOOT_CONTACT_LOCAL,
                        FOOT_PENETRATION_TOL_M, KINEMATICS, _axang, _rpy)

LEG_JOINTS = ("hip_pitch", "hip_roll", "hip_yaw", "knee",
              "ankle_pitch", "ankle_roll")
FOOT_TOL_M = 0.005          # a sole this close to the floor counts as landed
MAX_ITERS = 12
DAMPING = 1e-3


class LegChain:
    """The six joints from the pelvis to one sole, and where the sole ends up."""

    def __init__(self, side: str, kinematics_path=KINEMATICS):
        J = json.loads(Path(kinematics_path).read_text("utf-8"))["joints"]
        self.side = side
        self.names = [f"{side}_{n}_joint" for n in LEG_JOINTS]
        self.origin = [np.asarray(J[n]["origin_xyz"], float) for n in self.names]
        self.rot0 = [_rpy(np.asarray(J[n]["origin_rpy"], float)) for n in self.names]
        self.axis = [np.asarray(J[n]["axis"], float) for n in self.names]

    def foot(self, q):
        """Ankle frame in the pelvis frame for this leg's six angles."""
        p, R = np.zeros(3), np.eye(3)
        for i in range(len(self.names)):
            p = p + R @ self.origin[i]
            R = R @ self.rot0[i] @ _axang(self.axis[i], float(q[i]))
        return p, R

    def contacts(self, q):
        """The four sole corners, in the pelvis frame. Four heights, not one.

        The single point under the ankle is what the first version solved, and
        it is not the foot: a plantarflexed ankle rotates the polygon about
        that point, so the height under the ankle can read 3 mm while the toe
        is 87 mm below the floor. Four corners pin the *plane*, which is what
        "the sole is on the floor" means, and the extra two constraints are
        free -- the leg has six joints and this asks three things of them.
        """
        p, R = self.foot(q)
        return p + FOOT_CONTACT_LOCAL @ R.T

    def sole(self, q):
        """Lowest sole corner -- what has to reach the floor and not pass it."""
        return self.contacts(q)[:, 2].min()


def contact_mask(pose_facts, phase_labels, n_frames):
    """Which feet are on the floor, per frame. Derived, never measured heights.

    A seated clip with no locomotion phase has both feet down throughout: the
    subject is not moving her legs, so every centimetre of variation in the
    captured foot height is capture error. A standing or walking clip needs the
    per-foot swing detection this does not do yet, and says so.
    """
    seated = bool(pose_facts.get("seated"))
    moving = any(l in ("walk", "step") for l in phase_labels)
    if seated and not moving:
        return (np.ones((n_frames, 2), bool),
                {"rule": "seated with no locomotion phase -- both feet down for "
                         "the whole clip", "source": "derived",
                 "frames_in_contact": [n_frames, n_frames]})
    return (np.zeros((n_frames, 2), bool),
            {"rule": "not a seated clip -- per-foot swing detection is not "
                     "implemented, so no contact is asserted",
             "source": "unavailable", "frames_in_contact": [0, 0]})


def solve(q_traj, joint_names, root_z, mask, limits=None, floor_z=0.0,
          prov=None, dev=None):
    """Adjust the leg joints so every foot in contact reaches the floor."""
    q = np.array(q_traj, dtype=float, copy=True)
    idx = {n: i for i, n in enumerate(joint_names)}
    legs = [LegChain("left"), LegChain("right")]
    cols = [[idx[n] for n in leg.names] for leg in legs]
    lo = hi = None
    if limits is not None:
        limits = np.asarray(limits, float)
        lo, hi = limits[:, 0], limits[:, 1]

    before, after, moved = [], [], np.zeros(len(joint_names))
    tilt_before, tilt_after = [], []
    for t in range(len(q)):
        for li, leg in enumerate(legs):
            c = cols[li]
            qi = q[t, c].copy()
            z0 = root_z + leg.contacts(qi)[:, 2]
            before.append(z0)
            tilt_before.append(float(z0.max() - z0.min()))
            if not mask[t, li]:
                after.append(z0)
                tilt_after.append(float(z0.max() - z0.min()))
                continue
            for _ in range(MAX_ITERS):
                z = root_z + leg.contacts(qi)[:, 2]
                err = floor_z - z                      # four residuals, one per corner
                if np.abs(err).max() < FOOT_TOL_M:
                    break
                # numerical Jacobian of the four corner heights in these six
                # joints. Four rows, six columns: the system is underdetermined
                # (and rank 3, since four coplanar corners pin a plane), so the
                # damped least-norm step is still the smallest change that
                # lands the foot -- the minimum-intervention rule, unchanged.
                J = np.empty((len(err), len(c)))
                for k in range(len(c)):
                    dq = np.zeros(len(c))
                    dq[k] = 1e-4
                    J[:, k] = ((leg.contacts(qi + dq)[:, 2]
                                - leg.contacts(qi - dq)[:, 2]) / 2e-4)
                A = J @ J.T + DAMPING * np.eye(len(err))
                qi = qi + J.T @ np.linalg.solve(A, err)
                if lo is not None:
                    qi = np.clip(qi, lo[c], hi[c])
            moved[c] = np.maximum(moved[c], np.abs(qi - q[t, c]))
            q[t, c] = qi
            z1 = root_z + leg.contacts(qi)[:, 2]
            after.append(z1)
            tilt_after.append(float(z1.max() - z1.min()))

    before, after = np.asarray(before), np.asarray(after)
    report = {
        "joints_touched": sorted({joint_names[i] for leg in legs
                                  for i in cols[legs.index(leg)]}),
        "measured_on": "the four sole corners of each foot, not the point "
                       "under the ankle",
        "sole_z_before_m": {"min": round(float(before.min()), 4),
                            "max": round(float(before.max()), 4)},
        "sole_z_after_m": {"min": round(float(after.min()), 4),
                           "max": round(float(after.max()), 4)},
        "sole_tilt_before_m": {"max": round(float(np.max(tilt_before)), 4)},
        "sole_tilt_after_m": {"max": round(float(np.max(tilt_after)), 4)},
        "penetration_before_m": round(float(max(0.0, -before.min())), 4),
        "penetration_after_m": round(float(max(0.0, -after.min())), 4),
        "worst_joint_change_deg": {joint_names[i]: round(float(np.degrees(moved[i])), 3)
                                   for i in np.argsort(-moved)[:6] if moved[i] > 0},
        "max_change_deg": round(float(np.degrees(moved.max())), 3),
        "tolerance_m": FOOT_TOL_M,
    }
    if prov:
        prov.derived("joint.legs", "leg joints solved so the soles reach the "
                                   "floor the contact mask asserts",
                     int(mask.sum()) * len(LEG_JOINTS))
    if dev:
        dev.record("retarget.commanded_feet_on_floor", "retarget", 0.0,
                   float(np.abs(before).max()), "m", tolerance=0.02,
                   how="worst sole corner, before the contact solve")
        dev.record("retarget.corrected_feet_on_floor", "retarget", 0.0,
                   float(np.abs(after).max()), "m", tolerance=0.02,
                   how="worst sole corner, after the contact solve")
        dev.record("retarget.commanded_foot_penetration", "retarget", 0.0,
                   float(max(0.0, -before.min())), "m",
                   tolerance=FOOT_PENETRATION_TOL_M,
                   how="deepest sole corner below the floor before the solve "
                       "-- the toe, which the single-point model could not see")
        dev.record("retarget.corrected_foot_penetration", "retarget", 0.0,
                   float(max(0.0, -after.min())), "m",
                   tolerance=FOOT_PENETRATION_TOL_M,
                   how="deepest sole corner below the floor after the solve")
    return q, report
