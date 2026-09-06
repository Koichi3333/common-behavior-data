#!/usr/bin/env python3
"""The properties of a clip that every later stage has to preserve.

Correction is allowed to change a lot -- that is the point of `cleanup`, of the
physics pass, of the whole-body reach. What it is not allowed to change is
whatever made the clip *that* clip. In the sample dataset the subject is seated
for all 96 frames, and a G1 that ends up standing, floating, or sunk into the
chair has not been corrected, it has been replaced.

So a decisive property is declared here as an **invariant**: derived once from
canonical CBD, carried alongside the motion, and checked after every stage that
could break it. An invariant that fails is a failed run, not a note in a report.

The seat is the case that forces the issue, and the numbers are not close:

    G1, from g1_29dof_with_hand.urdf
      pelvis -> knee      0.4346 m
      knee   -> ankle     0.3176 m
      ankle  -> sole      0.0350 m   (foot contact spheres at z = -0.03, r = 0.005)
      seated knee height  0.3526 m   <- where a seat top has to be

    object_catalog.json, "chair"     0.4500 m   <- human furniture

Put the G1 on a stock 0.45 m chair and its feet hang 0.10 m above the floor.
Both "seated" and "feet on the floor" are true of the source clip; on a
human-sized chair the robot can hold at most one of them.

The resolution keeps v1's instinct -- *"the robot is not resized; the room is"*
-- and gives it a rule: **a support surface is solved for the target; a free
standing object keeps its catalog size.** The chair the subject sat on is not a
chair in the scene, it is the height her pelvis was at, and the height a G1's
pelvis is at is its own business. Objects nobody sits on or puts anything on
are unaffected.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KINEMATICS = HERE / "g1_kinematics.json"

# From g1_29dof_with_hand.urdf: every foot collision sphere on
# {left,right}_ankle_roll_link sits at z = -0.03 with radius 0.005, so the sole
# plane is 0.035 m below the ankle roll frame. Hardware, not an estimate --
# measured 2026-09-04 from the URDF NVIDIA ships inside the Arena image.
ANKLE_TO_SOLE_M = 0.035

# A foot is a polygon, not a point. The same URDF gives each ankle_roll_link
# *four* contact spheres -- heel at x = -0.050 (y = +/-0.025), toe at
# x = +0.120 (y = +/-0.030) -- and the shipped asset's own visual mesh bottoms
# out at z = -0.0354, so the sphere plane and the render agree to 0.4 mm.
#
# Constraining only the point under the ankle, which is what the first foot
# contact solve did, leaves the foot free to pitch about it. This clip commands
# 27-30 deg of ankle pitch: the point under the ankle came out within 3 mm of
# the floor -- and every check passed -- while the toe was 53 to 87 mm *under*
# it, which is what "the feet are buried" looks like from the outside. The
# check and the solver shared the model, so nothing measured the error.
FOOT_CONTACT_LOCAL = np.array([
    [-0.050,  0.025, -ANKLE_TO_SOLE_M],     # heel, outer
    [-0.050, -0.025, -ANKLE_TO_SOLE_M],     # heel, inner
    [+0.120,  0.030, -ANKLE_TO_SOLE_M],     # toe, outer
    [+0.120, -0.030, -ANKLE_TO_SOLE_M],     # toe, inner
])
FOOT_PENETRATION_TOL_M = 0.005   # design section 10-1: no contact deeper than 5 mm


def foot_contact_points(P, R, side):
    """The four sole corners of one foot, in whatever frame P and R are in."""
    return P[f"{side}_ankle_roll_link"] + FOOT_CONTACT_LOCAL @ R[f"{side}_ankle_roll_link"].T

# Measured from the asset's own bounding boxes (g1_29dof_with_hand_rev_1_0.usd,
# 2026-09-04): the thigh link is 0.0887 m across its short axis, so a thigh
# lying on a seat puts its axis half that above the surface; the pelvis body
# runs from +0.0025 to -0.1475 about its own origin. Both are needed because a
# seated robot touches the seat with its thighs, not with the frame the root
# transform addresses.
THIGH_HALF_THICKNESS_M = 0.0444
PELVIS_ORIGIN_TO_BOTTOM_M = 0.1475
# pelvis origin down to the hip flexion axis, from the URDF chain
PELVIS_TO_HIP_M = 0.2573
# a seat is a surface on legs; a solid block from the floor swallows the shins
SEAT_THICKNESS_M = 0.06
# With the pelvis pinned, the seat carries no load -- it is scenery, and its one
# job is not to intersect the robot. Sitting its top exactly on the pelvis
# underside means zero clearance, which for mesh colliders is interpenetration:
# measured as 0.3004 m of foot error and 18.9 deg RMSE, against 0.0558 m and
# 3.11 deg for the same clip with the seat removed entirely. A 5 mm gap is
# invisible and costs nothing.
SEAT_CLEARANCE_M = 0.005

SEATED_KNEE_RANGE_DEG = (60.0, 140.0)
FOOT_CLEARANCE_TOL_M = 0.02      # a sole this far off the floor is "not on it"
PELVIS_SUPPORT_TOL_M = 0.02      # a pelvis this far from the seat is "not on it"


def leg_geometry(kinematics_path: Path = KINEMATICS, side: str = "right"):
    """Vertical link lengths of one leg, from the URDF-derived kinematics."""
    K = json.loads(Path(kinematics_path).read_text("utf-8"))
    J = K["joints"]

    def dz(joint):
        return abs(float(J[joint]["origin_xyz"][2]))

    thigh = sum(dz(f"{side}_{n}_joint") for n in
                ("hip_pitch", "hip_roll", "hip_yaw", "knee"))
    shank = dz(f"{side}_ankle_pitch_joint") + dz(f"{side}_ankle_roll_joint")
    return {
        "pelvis_to_knee_m": round(thigh, 4),
        "knee_to_ankle_m": round(shank, 4),
        "ankle_to_sole_m": ANKLE_TO_SOLE_M,
        "pelvis_to_sole_m": round(thigh + shank + ANKLE_TO_SOLE_M, 4),
        "source": ("g1_kinematics.json (from g1_29dof_with_hand.urdf); sole "
                   "offset measured from the URDF's foot collision spheres"),
    }


def seat_height_for_target(geom=None) -> dict:
    """Where a seat top has to be for this robot to sit with its feet down.

    Knees square, thighs horizontal, soles on the floor. Three heights come out
    of that and they are not the same number -- an earlier version of this
    function returned one for all three, the physics pass measured the result,
    and the robot fell off the seat:

        knee / hip axis   shank + sole                       0.3526 m
        seat top          that, less the thigh's half        0.3082 m
                          thickness -- the thigh rests on
                          the seat, its axis sits above it
        pelvis origin     hip axis + the pelvis-to-hip drop  0.6099 m
                          -- what the root transform sets

    Placing the root at the knee height put the whole pelvis 0.15 m inside the
    seat box, and PhysX ejected it. Reported as `physics.pelvis_on_seat: asked
    0.3526, got 0.132, error 0.2206 m` before anyone had to look at a picture.
    """
    g = geom or leg_geometry()
    hip = g["knee_to_ankle_m"] + g["ankle_to_sole_m"]
    return {
        "hip_axis_m": round(hip, 4),
        "seat_top_m": round(hip - THIGH_HALF_THICKNESS_M, 4),
        "root_z_m": round(hip + PELVIS_TO_HIP_M, 4),
        "why": (f"hip axis at knee height {hip:.4f} (shank "
                f"{g['knee_to_ankle_m']:.4f} + sole {g['ankle_to_sole_m']:.4f}); "
                f"seat top one thigh half-thickness "
                f"({THIGH_HALF_THICKNESS_M:.4f}) below it; pelvis origin "
                f"{PELVIS_TO_HIP_M:.4f} above it"),
        "geometry": g,
    }


def support_conflict(catalog_height: float, geom=None) -> dict:
    """How badly a human-scale support surface fits the target."""
    want = seat_height_for_target(geom)["seat_top_m"]
    gap = float(catalog_height) - want
    if gap > FOOT_CLEARANCE_TOL_M:
        verdict = f"feet would hang {gap:.3f} m above the floor"
    elif gap < -FOOT_CLEARANCE_TOL_M:
        verdict = f"knees would fold {-gap:.3f} m past square"
    else:
        verdict = "within tolerance"
    return {"catalog_m": round(float(catalog_height), 4), "target_m": want,
            "foot_clearance_m": round(gap, 4), "verdict": verdict,
            "resolves_to": want}


# --------------------------------------------------------------------------
# fitting the support to the pose that was actually commanded
# --------------------------------------------------------------------------
def _rpy(r):
    cr, sr = np.cos(r[0]), np.sin(r[0])
    cp, sp = np.cos(r[1]), np.sin(r[1])
    cy, sy = np.cos(r[2]), np.sin(r[2])
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _axang(axis, t):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K


def forward_kinematics(q, joint_names, kinematics_path=KINEMATICS, with_rot=False):
    """Link positions in the pelvis frame for one joint vector. No simulator.

    `with_rot` also returns the orientations, which the sole needs: the foot's
    0.035 m offset is along the *ankle's* z, not the world's, and ignoring that
    is worth 3.5 mm at the 30 deg ankle pitch this clip commands.
    """
    J = json.loads(Path(kinematics_path).read_text("utf-8"))["joints"]
    idx = {n: i for i, n in enumerate(joint_names)}
    children = {}
    for name, j in J.items():
        children.setdefault(j["parent"], []).append((name, j))
    pos, rot, stack = {"pelvis": np.zeros(3)}, {"pelvis": np.eye(3)}, ["pelvis"]
    while stack:
        link = stack.pop()
        for name, j in children.get(link, []):
            R = rot[link] @ _rpy(np.asarray(j["origin_rpy"], float))
            p = pos[link] + rot[link] @ np.asarray(j["origin_xyz"], float)
            if j["type"] == "revolute" and name in idx:
                R = R @ _axang(j["axis"], float(q[idx[name]]))
            child = j["child"]
            pos[child], rot[child] = p, R
            stack.append(child)
    return (pos, rot) if with_rot else pos


def seat_from_pose(q_traj, joint_names, root_z_traj=None, margin=0.02):
    """Size and place the seat from the pose the robot was actually asked to hold.

    The idealised model -- knees square, thighs horizontal -- gave a seat at
    0.308 m and put it under the pelvis. The commanded pose is not that pose:
    the knees sit 0.20 m below the pelvis and 0.29 m *in front* of it, so a seat
    sized for a textbook sitter is both too low and too far back, and on the
    first physics run nothing touched anything. The robot fell 0.28 m and the
    ledger said so.

    So measure instead. Forward-kinematics the commanded joints, put the soles
    on the floor, and the seat follows: its top where the pelvis underside is,
    its footprint spanning from behind the pelvis to under the knees.
    """
    q_traj = np.asarray(q_traj, float)
    soles, hips, knees, ys, swept = [], [], [], [], []
    LEG_LINKS = [f"{s}_{n}_link" for s in ("left", "right") for n in
                 ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch",
                  "ankle_roll")]
    for t in range(len(q_traj)):
        P, R = forward_kinematics(q_traj[t], joint_names, with_rot=True)
        soles.append(min(float(foot_contact_points(P, R, s)[:, 2].min())
                         for s in ("left", "right")))
        for side in ("left", "right"):
            hips.append(P[f"{side}_hip_pitch_link"])
            knees.append(P[f"{side}_knee_link"])
            ys.append(float(P[f"{side}_knee_link"][1]))
        swept.append([P[L] for L in LEG_LINKS if L in P])
    soles = np.asarray(soles)
    # world heights, once the root height below is known -- filled after root_z

    root_z = (float(np.median(np.asarray(root_z_traj)))
              if root_z_traj is not None else float(-np.median(soles)))
    seat_top = root_z - PELVIS_ORIGIN_TO_BOTTOM_M - SEAT_CLEARANCE_M
    swept = [[np.array([p[0], p[1], root_z + p[2]]) for p in frame]
             for frame in swept]

    # How far forward the seat may reach. A seat is a surface, not a plinth: it
    # may only occupy space the body is *above*. In this pose the thighs slope
    # down -- hip at z 0.494 world, knee at 0.392, seat top at 0.4454 -- so a
    # seat drawn out to the knees swallows the shins and the feet, and PhysX
    # spends the clip pushing the legs out of it. That is what the first fitted
    # seat did: a solid block from the floor to 0.4454 with the knees inside it,
    # measured as 40-93 deg of hip tracking error.
    # Carve the seat out of the space the robot never occupies, rather than
    # inferring it from two landmark heights. Three attempts failed that way:
    # a plinth to the floor swallowed the shins; a footprint out to the knees
    # grazed the hip link (8 mm past the front edge, 23 mm above it); and 5 mm
    # of clearance under the pelvis was not enough, because the hip chain
    # *sweeps* forward and down through the seat's z band on its way to the
    # knee. Every one of those showed up as the same symptom -- one leg joint
    # 120 deg off and the feet in the air -- and none of them was visible from
    # the landmark arithmetic.
    #
    # So: sample every leg link over every frame, and shrink the seat until
    # nothing ever comes within a link radius of it. If nothing fits, say so and
    # leave the seat out; with the pelvis pinned the seat carries no load, and a
    # box that fights the legs is worse than no box at all.
    seat_lo, seat_hi = seat_top - SEAT_THICKNESS_M, seat_top
    x1 = 0.0
    for pts in swept:
        for w in pts:
            if seat_lo - THIGH_HALF_THICKNESS_M <= w[2] <= seat_hi + THIGH_HALF_THICKNESS_M:
                x1 = min(x1, float(w[0]) - THIGH_HALF_THICKNESS_M - margin)
    fits = x1 > -PELVIS_ORIGIN_TO_BOTTOM_M + 0.05
    x0 = -PELVIS_ORIGIN_TO_BOTTOM_M
    half_y = max(abs(min(ys)), abs(max(ys))) + margin
    return {
        "root_z_m": round(root_z, 4),
        "seat_top_m": round(seat_top, 4),
        "thickness_m": SEAT_THICKNESS_M,
        "clearance_m": SEAT_CLEARANCE_M,
        "fits": bool(fits),
        "forward_edge_m": round(float(x1), 4),
        "centre_xy": [round((x0 + x1) / 2.0, 4), 0.0],
        "size_xy": [round(x1 - x0, 4), round(2 * half_y, 4)],
        "foot_drop_m": {"min": round(float(-soles.max()), 4),
                        "max": round(float(-soles.min()), 4),
                        "spread": round(float(soles.max() - soles.min()), 4)},
        # what the *commanded* trajectory puts the soles at, with the pelvis
        # where the retarget asked. Physics cannot put a foot on the floor that
        # the trajectory never sends there, so this is the ceiling on how well
        # `invariant.feet_on_floor` can ever do without fixing the retarget.
        "commanded_sole_z_m": {"min": round(float(root_z + soles.min()), 4),
                               "max": round(float(root_z + soles.max()), 4)},
        "why": (f"soles on the floor puts the pelvis origin at {root_z:.4f} m; "
                f"its underside, {PELVIS_ORIGIN_TO_BOTTOM_M:.4f} m lower, is "
                f"where the seat top goes. It reaches to x={x1:.3f}, "
                f"carved back until no leg link ever "
                f"comes within {THIGH_HALF_THICKNESS_M + margin:.3f} m of it -- "
                f"and is "
                f"{SEAT_THICKNESS_M:.3f} m thick, not a block to the floor, "
                f"and {SEAT_CLEARANCE_M * 1000:.0f} mm clear of the pelvis "
                f"because a pinned robot needs scenery, not a contact"),
        "source": ("root from the retarget's own pelvis trajectory"
                   if root_z_traj is not None else "root from FK, soles on floor"),
    }


def derive(pose: np.ndarray, dims, phase_labels, pose_facts, prov=None):
    """The decisive properties of this clip, as checkable declarations."""
    n = len(pose)
    inv = []
    if pose_facts.get("seated"):
        knee = pose_facts.get("knee_flexion_deg")
        seat = seat_height_for_target()
        inv.append({
            "name": "seated", "source": "measured",
            "evidence": (f"median knee flexion {knee:.0f} deg over all {n} frames"
                         if knee is not None else "pelvis below leg length"),
            "requires": [
                f"the pelvis rests on a support surface (+/- {PELVIS_SUPPORT_TOL_M} m)",
                f"both soles stay on the floor (+/- {FOOT_CLEARANCE_TOL_M} m)",
                "knee flexion stays inside %.0f-%.0f deg" % SEATED_KNEE_RANGE_DEG],
            "seat_top_m": seat["seat_top_m"], "hip_axis_m": seat["hip_axis_m"],
            "root_z_m": seat["root_z_m"], "seat_why": seat["why"],
            "breaks_if": ("the seat keeps its human-scale catalog height, or the "
                          "physics pass is allowed to drop the root to the floor"),
        })
        if prov:
            prov.measured("invariant.seated", "knee flexion over the whole clip", n)
            prov.derived("scene.seat_top",
                         "solved from the G1's own shank and sole -- not from the "
                         "subject, not from the catalog", n,
                         detail={"seat_top_m": seat["seat_top_m"]})
    else:
        inv.append({
            "name": "standing", "source": "measured",
            "evidence": "knee flexion outside the seated band",
            "requires": [f"both soles stay on the floor (+/- {FOOT_CLEARANCE_TOL_M} m)"],
            "breaks_if": "the root height is taken from the subject rather than solved",
        })
        if prov:
            prov.measured("invariant.standing", "knee flexion over the whole clip", n)

    holds = [i for i, l in enumerate(phase_labels) if l == "hold"]
    if holds:
        inv.append({
            "name": "hand_contact", "source": "derived",
            "evidence": f"{len(holds)} frames labelled hold",
            "requires": ["the acting hand is within 2 cm of the handled object "
                         "for every hold frame"],
            "frames": [holds[0], holds[-1]],
            "breaks_if": ("the reach is matched in joint angles only -- the G1's "
                          "arm is shorter than the subject's, so equal angles "
                          "land the hand short"),
        })
        if prov:
            prov.derived("invariant.hand_contact",
                         "hold frames from the derived phase", len(holds))
    return inv


def check_scene(invariants, resolved_objects, tol=PELVIS_SUPPORT_TOL_M):
    """Verify the scene as built still satisfies what was declared.

    Only the parts observable before the robot is posed; the rest carries the
    same declarations into the physics pass.
    """
    out = []
    for inv in invariants:
        if inv["name"] != "seated":
            out.append({"invariant": inv["name"], "stage": "scene",
                        "status": "deferred",
                        "note": "checked once the robot is posed"})
            continue
        seats = [o for o in resolved_objects
                 if "sit" in ((o.get("catalog") or {}).get("afford") or [])]
        if not seats:
            out.append({"invariant": "seated", "stage": "scene", "status": "FAIL",
                        "note": "the clip is seated and the scene has nothing to sit on"})
            continue
        want = inv["seat_top_m"]
        got = [s for s in seats if abs(s.get("support_top_m", -99) - want) <= tol]
        out.append({
            "invariant": "seated", "stage": "scene",
            "status": "ok" if got else "FAIL",
            "note": (f"seat top at {got[0]['support_top_m']:.3f} m, target "
                     f"{want:.3f} m" if got else
                     f"no seat at the target height {want:.3f} m; found "
                     f"{[round(s.get('support_top_m', -1), 3) for s in seats]}"),
        })
    return out
