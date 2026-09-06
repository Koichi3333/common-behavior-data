#!/usr/bin/env python3
"""Where the objects go -- the step `scene_objects` deliberately stopped before.

`scene_objects.py` decides *which* objects exist and `fit_scene_to_target`
decides how big the scene is. Neither decides a position, and the v2 report
said so plainly: "the table and the cup are resolved from the catalog and then
not placed", which left `invariant.hand_contact` deferred and left the robot
reaching for nothing -- the same emptiness v1 was rejected for, one stage
further along.

The input makes this hard in a specific way. CBD carries objects as normalised
image boxes: `label, score, bbox_x/y/width/height` and a tracked centre. There
is no depth, no metric size, no camera. Three channels have to make up the
difference, and they are used in the order the design fixes:

    1  physical consistency   nothing penetrates anything
    2  the task happens       the hand that holds something holds something
    3  natural motion         (nothing here moves the robot)
    4  faithfulness           the image is right about direction and shape

So the solve runs in that order rather than as one least-squares. Each stage
may overrule the one below it, and every overrule is a number in the ledger.

    A  image estimate    bbox centre through the dataset's own image-plane fit,
                         with depth from apparent size against the catalog's
                         metric dimensions. This is the faithful answer, and on
                         this clip it is 0.35 m from where the robot's hand
                         actually goes -- not because the placement is wrong
                         but because the retarget's arm points elsewhere (the
                         waist carries no chest rotation, so a reach to the
                         subject's side comes out as a reach to the robot's
                         front). Recorded, not used, when B contradicts it.

    B  task binding      the handled object is placed *on the hand*: a grasp on
                         empty air is worth nothing as a video and less as
                         training data. Priority 2 beats priority 4, and this
                         is what that costs.

    C  support           the surface under the handled object is solved for the
                         height the object rests at, exactly as the seat is
                         solved for the robot's own shank rather than taken
                         from the catalog. Its footprint keeps the one scene
                         scale.

    D  carve             the support is pushed back until no robot link ever
                         enters it, on any frame -- the rule `seat_from_pose`
                         already uses, for the reason four failed seats taught:
                         a box that fights the legs is worse than no box.

Nothing here is specific to a cup or a table. The handled object is whatever
the phase signal says is held and the catalog says can be grasped; the support
is whatever the geometry says it rests on, or the floor.
"""
from __future__ import annotations

import numpy as np

# The camera the adapter itself authors sits 3.0 canonical metres from the
# subject (`derive_camera`, unchanged since v1), and that distance is what
# turns an apparent-size *ratio* into a depth in metres. It is a prior, not a
# measurement -- CBD records no intrinsics -- so it is tagged as one and the
# ratio is reported next to it, because the ratio is the part that is derived.
CAMERA_DISTANCE_M = 3.0
# a bbox side this close to the frame edge is cropped, and its apparent size
# says nothing about depth
BORDER_EPS = 0.015
# how far the handled object's rest position sits in from the near edge of the
# surface it rests on
EDGE_MARGIN_M = 0.06
# legs are inset from the top slab by this fraction of each span
LEG_INSET = 0.08
LEG_SIDE_M = 0.05
TOP_THICKNESS_M = 0.035
# nothing on the robot may come closer than this to a support surface
# how close robot geometry may come to a support surface. Small on
# purpose: the acting hand works at the surface, and a large margin
# there buys nothing the physics pass will not measure anyway.
SURFACE_CLEARANCE_M = 0.01
LEG_CLEARANCE_M = 0.02
# design section 10-1: contact deeper than this is a penetration. Anything
# shallower is a graze, and treating a graze as a blocker is what first turned
# a table that fits into scenery -- 29 frames of "overlap" measured at under
# 0.05 mm.
PENETRATION_TOL_M = 0.002


# --------------------------------------------------------------------------
# A -- the image estimate
# --------------------------------------------------------------------------
def _project(plane, u, v):
    return plane["sx"] * u + plane["cx"], plane["sy"] * v + plane["cy"]


def depth_ratio(bbox, dims_m, plane):
    """How much further away than the subject this object is, from its size.

    The standard monocular trick, and the one the design picked over v1's
    "project it onto the subject's plane": an object of known metric size
    subtends an angle that falls off with distance, so `catalog / apparent`
    is the depth ratio directly. Two cautions are worth the code:

    * a side that touches the frame edge is cropped, and its apparent size is
      a lower bound rather than a measurement. On this clip the table's box
      ends at u = 0.987 and its width says the table is 3.4x further away than
      the subject; its (uncropped) height says 1.05x, which is right.
    * the catalog dimensions used here are the **unscaled** ones. The image
      and the canonical metres it maps to are the subject's world, at the
      subject's size; the scene scale belongs to the robot's world and is
      applied afterwards. Mixing them biases every depth by 1/scale, which on
      this clip read the glass as 0.56x the subject's distance -- half a metre
      of error out of a number that is otherwise good to a few percent.
    * with neither side usable the honest answer is the subject's own plane,
      ratio 1, tagged `prior`.
    """
    u0, v0, w, h = bbox
    usable, why = [], []
    if u0 > BORDER_EPS and u0 + w < 1.0 - BORDER_EPS:
        plane_w = abs(plane["sx"]) * w
        if plane_w > 1e-6:
            usable.append(dims_m[0] / plane_w)
            why.append(f"width {plane_w:.3f} m against catalog "
                       f"{dims_m[0]:.3f} m")
    else:
        why.append("width unusable -- the box is cropped by the frame edge")
    if v0 > BORDER_EPS and v0 + h < 1.0 - BORDER_EPS:
        plane_h = abs(plane["sy"]) * h
        if plane_h > 1e-6:
            usable.append(dims_m[2] / plane_h)
            why.append(f"height {plane_h:.3f} m against catalog "
                       f"{dims_m[2]:.3f} m")
    else:
        why.append("height unusable -- the box is cropped by the frame edge")
    if not usable:
        return 1.0, "prior", "no uncropped side; placed on the subject's plane"
    r = float(np.exp(np.mean(np.log(usable))))
    return r, "derived", "; ".join(why) + f" -> depth ratio {r:.3f}"


def image_estimate(hyp, plane, scale, floor_y):
    """The object's position in the robot frame, from the image alone.

    canonical -> robot is the permutation the adapter has used since v1:
    (x right, y up, z toward camera) -> (z, x, y), with the floor at zero and
    the whole set at the one scene scale.
    """
    bb = hyp.get("bbox_median")
    centre = hyp.get("center")
    if not bb or not centre:
        return None
    w, h = bb
    u, v = centre
    bbox = (u - w / 2.0, v - h / 2.0, w, h)
    dims = (hyp.get("catalog") or {}).get("dims_m")
    if not dims:
        return None
    r, tier, why = depth_ratio(bbox, dims, plane)
    axis_x, axis_y = _project(plane, 0.5, 0.5)
    px, py = _project(plane, u, v)
    x_c = axis_x + (px - axis_x) * r
    y_c = axis_y + (py - axis_y) * r
    z_c = CAMERA_DISTANCE_M * (1.0 - r)
    return {
        "position_m": [round(scale * z_c, 4), round(scale * x_c, 4),
                       round(scale * (y_c - floor_y), 4)],
        "depth_ratio": round(r, 4), "tier": tier, "why": why,
        "camera_distance_m": CAMERA_DISTANCE_M,
        "camera_distance_tier": "prior -- CBD records no camera intrinsics",
    }


# --------------------------------------------------------------------------
# support relations, from the boxes themselves
# --------------------------------------------------------------------------
def _box(hyp):
    if not hyp.get("bbox_median") or not hyp.get("center"):
        return None
    w, h = hyp["bbox_median"]
    u, v = hyp["center"]
    return (u - w / 2, v - h / 2, u + w / 2, v + h / 2)


def rests_on(a, b):
    """Does a's box sit on b's, in the image? Bottom inside, and higher up."""
    ba, bb = _box(a), _box(b)
    if not ba or not bb:
        return False
    foot_u, foot_v = (ba[0] + ba[2]) / 2, ba[3]
    return (bb[0] <= foot_u <= bb[2] and bb[1] <= foot_v <= bb[3]
            and foot_v < bb[3])


# --------------------------------------------------------------------------
# B -- the task binding
# --------------------------------------------------------------------------
def grasp_span(grasp, holds, rest_before, rest_after):
    """When the object is picked up and when it is put down.

    Not simply "the first hold frame to the last". The phase boundary is where
    the *pose* changes character; the grasp is where the hand actually arrives
    at the object, and on this clip those are seven frames apart -- taking the
    phase boundary makes the object jump 87 mm into the hand as the label
    changes. So the pick-up is the frame, at or before the first hold, where
    the hand is closest to the object sitting at rest, and the release is the
    matching frame at or after the last hold. Whatever gap remains at those two
    frames is the smallest this trajectory allows, and it is recorded.
    """
    first, last = min(holds), max(holds)
    pre = int(np.argmin([np.linalg.norm(grasp[t] - rest_before)
                         for t in range(0, first + 1)]))
    tail = range(last, len(grasp))
    post = last + int(np.argmin([np.linalg.norm(grasp[t] - rest_after)
                                 for t in tail]))
    return (pre, post,
            float(np.linalg.norm(grasp[pre] - rest_before)),
            float(np.linalg.norm(grasp[post] - rest_after)))


def carried_track(grasp, first, last, rest_before, rest_after, ease=2):
    """Where the handled object is on every frame.

    Held from the pick-up frame to the release frame -- a grasp and a release,
    which is what two hold segments with the same hand mean -- and resting on
    its surface outside that span. `ease` frames of blend either side absorb
    whatever gap `grasp_span` could not close.
    """
    n = len(grasp)
    track = np.empty((n, 3))
    for t in range(n):
        if first <= t <= last:
            track[t] = grasp[t]
        elif t < first:
            track[t] = rest_before
        else:
            track[t] = rest_after
    for k in range(1, ease + 1):
        t = first - k
        if t >= 0:
            w = k / (ease + 1.0)
            track[t] = (1 - w) * grasp[first] + w * rest_before
        t = last + k
        if t < n:
            w = k / (ease + 1.0)
            track[t] = (1 - w) * grasp[last] + w * rest_after
    return track


# --------------------------------------------------------------------------
# D -- carving the support out of the space the robot uses
# --------------------------------------------------------------------------
def _in_footprint(p, centre, half, yaw_deg, clearance):
    """Is this point over the surface? Tested in the surface's own frame -- an
    axis-aligned test on a yawed table is a different, larger table, and it
    pushed this one 0.13 m out from under the object it holds."""
    c, sn = np.cos(np.radians(-yaw_deg)), np.sin(np.radians(-yaw_deg))
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    lx, ly = c * dx - sn * dy, sn * dx + c * dy
    return (abs(lx) <= half[0] + clearance and abs(ly) <= half[1] + clearance,
            lx, ly)


def fit_legs(centre, half, top_z, thickness, swept, yaw_deg,
             clearance=LEG_CLEARANCE_M):
    """Pull the legs in until nothing under the top is inside one.

    The room under a table is the point of a table, so only the four columns
    are solid down there -- and where they stand is free, unlike the top. This
    walks the inset in rather than giving up on the surface, which is the same
    move `seat_from_pose` makes when it carves the seat back off the legs.
    """
    r0 = LEG_SIDE_M / 2.0 + clearance
    inset = LEG_INSET
    while inset <= 0.40:
        hx = half[0] - inset * 2 * half[0]
        hy = half[1] - inset * 2 * half[1]
        hit = False
        for p, _t, _hand, rad in swept:
            if p[2] >= top_z - thickness:
                continue
            _, lx, ly = _in_footprint(p, centre, half, yaw_deg, 0.0)
            r = r0 + rad
            for gx, gy in ((hx, hy), (hx, -hy), (-hx, hy), (-hx, -hy)):
                if abs(lx - gx) <= r and abs(ly - gy) <= r:
                    hit = True
                    break
            if hit:
                break
        if not hit:
            return True, round(inset, 3)
        inset += 0.02
    return False, LEG_INSET


def _pen(a, b, lo, hi):
    """How deep a span [a, b] is inside a band [lo, hi]. Negative means clear.

    A point is a span of zero width, and `min(b, hi) - max(a, lo)` calls that
    zero however far inside it sits -- which is how a fingertip 17.5 mm inside
    a tabletop was reported as no overlap at all, and why PhysX and this fit
    disagreed by 120 deg of wrist error. A span wholly inside the band is as
    deep as its nearest way out.
    """
    if a >= lo and b <= hi:
        return min(b - lo, hi - a)
    return min(b, hi) - max(a, lo)


def _top_for(top_task, thickness, points, clearance):
    """The highest top plane a slab of this thickness fits under.

    A slab occupies one band, not everything below it -- the room under a
    table is the point of a table. So this looks for the highest gap the slab
    fits in, rather than lowering the plane until it clears the lowest point:
    lowering cascades (drop the top to clear one fingertip and the *underside*
    reaches the next one down) and cost 5.9 cm of table height on this clip
    before the difference was noticed.
    """
    # each point is a body with a radius, so it occupies [z - r, z + r]
    spans = sorted((float(p[2]) - rad, float(p[2]) + rad) for p, rad in points)
    cands = [top_task] + [lo - clearance for lo, _hi in reversed(spans)]
    for cand in cands:
        if cand > top_task:
            continue
        lo = cand - thickness - clearance
        if not any(_pen(a, b, lo, cand) > PENETRATION_TOL_M for a, b in spans):
            return cand
    return top_task - thickness


def _overlap(top, thickness, points, clearance):
    """How deep the robot is inside a slab at this height, and on what frames."""
    lo, hi = top - thickness - clearance, top
    worst, frames = 0.0, set()
    for (p, rad), t in points:
        a, b = float(p[2]) - rad, float(p[2]) + rad
        depth = _pen(a, b, lo, hi)
        if depth > PENETRATION_TOL_M:
            worst = max(worst, depth)
            frames.add(int(t))
    return worst, sorted(frames)


def fit_surface(rest_xy, top_task, span_x, span_y, obj_half_width, swept,
                holds, thickness=TOP_THICKNESS_M, clearance=SURFACE_CLEARANCE_M):
    """Where the near edge goes, how high the top is, and whether it is solid.

    Two things are being traded, and the design's priority order settles it:
    the surface has to carry the object (priority 2) and nothing may pass
    through it (priority 1). Reaching for the object takes the hand across the
    plane the object rests on -- with each link at the radius of its own
    collision mesh, this clip has the hand inside that plane on 20 frames of
    96, at every near edge the object allows.

    So the fit tries, in order:

    1  the task height with the near edge pulled back until the sweep is off
       the surface. If that works the surface is **solid** -- a real collider,
       and the physics pass measures it.
    2  a lower top that fits in a gap between the sweep and the object. Also
       solid.
    3  the task height, the edge that leaves the least overlap, and the
       surface authored as **scenery** -- geometry with its collider disabled,
       with the residual overlap measured and reported.

    Route 3 is not a shrug. Nothing rests on this surface but an object the
    hand carries kinematically, so a collider on it buys no physics: the seat
    is scenery for the same reason ("with the pelvis pinned the seat carries no
    load"), and the alternative measured here was 55 deg of thumb tracking
    error from a 2 cm residual the reach owns and the placement cannot fix.
    What the reach owes is in `docs -- whole-body reach`; what the placement
    owes is this number.
    """
    r_rest = float(np.linalg.norm(rest_xy))
    d = np.asarray(rest_xy, float) / (r_rest or 1.0)
    yaw = float(np.degrees(np.arctan2(d[1], d[0]))) + 90.0
    half = (span_x / 2.0, span_y / 2.0)
    edge0 = r_rest - EDGE_MARGIN_M
    edge_max = r_rest - obj_half_width
    best, fallback = None, None
    edge = edge0
    while edge <= edge_max + 1e-9:
        centre = d * (edge + span_y / 2.0)
        inside = [((p, rad), t) for p, t, is_hand, rad in swept
                  if (not (is_hand and t in holds))
                  and _in_footprint(p, centre, half, yaw, clearance + rad)[0]]
        top = _top_for(top_task, thickness, [pr for pr, _t in inside], clearance)
        cand = {"top_z_m": float(top), "edge_m": float(edge), "solid": True,
                "centre_xy_m": [float(centre[0]), float(centre[1])],
                "yaw_deg": yaw, "overlap_m": 0.0, "overlap_frames": []}
        if best is None or top > best["top_z_m"] + 1e-9:
            best = cand
        worst, frames = _overlap(top_task, thickness, inside, clearance)
        if fallback is None or worst < fallback["overlap_m"] - 1e-9:
            fallback = {"top_z_m": float(top_task), "edge_m": float(edge),
                        "solid": False,
                        "centre_xy_m": [float(centre[0]), float(centre[1])],
                        "yaw_deg": yaw, "overlap_m": round(float(worst), 4),
                        "overlap_frames": frames}
        if top >= top_task - 1e-6:
            break
        edge += 0.0025
    # a solid surface that has to drop more than the object is tall is not the
    # surface the object rests on any more -- take the scenery instead
    chosen = best
    if best["top_z_m"] < top_task - 2 * obj_half_width:
        chosen = fallback
    chosen["edge_pulled_back_m"] = round(chosen["edge_m"] - edge0, 4)
    chosen["top_lowered_m"] = round(top_task - chosen["top_z_m"], 4)
    chosen["edge_bound_by_object"] = bool(chosen["edge_m"] >= edge_max - 1e-9)
    chosen["solid_rejected"] = (None if chosen["solid"] else
                                {"best_solid_top_m": round(best["top_z_m"], 4),
                                 "task_top_m": round(top_task, 4)})
    return chosen


# --------------------------------------------------------------------------
# the solve
# --------------------------------------------------------------------------
def solve(resolved, plane, scale, floor_y, grasp, hold_frames, swept,
          hand="right", primary_label=None, prov=None, dev=None):
    """Place every accepted object. Returns (placed, carried_track, report).

    `grasp`  (n,3) world positions of the acting hand's grasp centre
    `swept`  every robot link position on every frame, world -- the space a
             support surface may not occupy
    """
    placed, notes = [], []
    by_label = {}
    for h in resolved:
        if h.get("label", "").startswith("_") or not h.get("catalog"):
            continue
        by_label.setdefault(h["label"], h)
        h["image_estimate"] = image_estimate(h, plane, scale, floor_y)

    # ---- which object is handled --------------------------------------
    graspable = [h for h in by_label.values()
                 if "grasp" in (h["catalog"].get("afford") or [])]
    handled = None
    if graspable and hold_frames is not None and len(hold_frames):
        handled = next((h for h in graspable if h["label"] == primary_label),
                       graspable[0])

    carried = None
    if handled is not None:
        dims = handled.get("dims_scaled_m") or handled["catalog"]["dims_m"]
        half_h = float(dims[2]) / 2.0
        holds = sorted(int(t) for t in hold_frames)
        first, last = holds[0], holds[-1]
        # the surface may not be penetrated, so it goes under the *lowest*
        # point the object is held at -- the put-down, on this clip, which is
        # 2.9 cm below the pick-up. Recorded rather than averaged away.
        held_z = np.array([grasp[t][2] for t in holds])
        surface_top = float(held_z.min()) - half_h
        rest_before = np.array([grasp[first][0], grasp[first][1],
                                surface_top + half_h])
        rest_after = np.array([grasp[last][0], grasp[last][1],
                               surface_top + half_h])
        first, last, _gap0, _gap1 = grasp_span(grasp, holds, rest_before,
                                              rest_after)
        carried = carried_track(grasp, first, last, rest_before, rest_after)

        handled["placement"] = {
            "kind": "carried",
            "rest_before_m": [round(float(v), 4) for v in rest_before],
            "rest_after_m": [round(float(v), 4) for v in rest_after],
            "held_frames": [first, last],
            "hold_phase_frames": [holds[0], holds[-1]],
            "tier": "derived",
            "why": (f"the {hand} hand's grasp centre -- the midpoint of the "
                    f"palm and the middle fingertip, so the object is where a "
                    f"closed hand would hold it -- over frames {first}-{last}, "
                    f"the span from the first hold to the last. Outside it the "
                    f"object rests on its surface at the pick-up and put-down "
                    f"positions"),
        }
        placed.append(handled)
        if prov:
            prov.derived(f"object.{handled['label']}.position",
                         "placed on the acting hand's grasp centre: the phase "
                         "signal says it is held, and an object that is held "
                         "is where the hand is", len(grasp))
        if dev:
            est = handled.get("image_estimate")
            if est:
                gap = float(np.linalg.norm(
                    np.asarray(est["position_m"]) - rest_before))
                dev.record(f"scene.{handled['label']}.image_vs_hand", "scene",
                           0.0, gap, "m", tolerance=None,
                           how="how far the image-derived position is from the "
                               "hand that holds it -- the object is placed on "
                               "the hand (priority 2) and this is what that "
                               "costs against the image (priority 4)",
                           note="the gap is in the retarget's arm direction, "
                                "not in the placement: the waist carries no "
                                "chest rotation, so a reach to the subject's "
                                "side comes out as a reach to the robot's front")
            dev.record(f"scene.{handled['label']}.pickup_above_surface",
                       "scene", 0.0,
                       float(grasp[first][2] - held_z.min()), "m",
                       tolerance=None,
                       how="the trajectory takes the object at one height and "
                           "sets it down at another; the surface goes under "
                           "the lower of the two so the object never "
                           "penetrates it, which leaves the pick-up starting "
                           "this far above it")

        # ---- C -- the surface it rests on -----------------------------
        support = next((h for h in by_label.values()
                        if h is not handled
                        and (h["catalog"].get("support")
                             or "support" in (h["catalog"].get("afford") or []))
                        and rests_on(handled, h)), None)
        if support is None:
            support = next((h for h in by_label.values()
                            if h is not handled and h["catalog"].get("support")
                            and "sit" not in (h["catalog"].get("afford") or [])),
                           None)
            if support is not None:
                notes.append(f"{support['label']}: no image overlap put the "
                             f"{handled['label']} on it; taken as its support "
                             f"because it is the only surface in the scene")
        if support is not None:
            dims_s = support.get("dims_scaled_m") or support["catalog"]["dims_m"]
            span_x, span_y = float(dims_s[0]), float(dims_s[1])
            obj_dims = handled.get("dims_scaled_m") or handled["catalog"]["dims_m"]
            fitted = fit_surface(rest_before[:2], surface_top, span_x, span_y,
                                 float(obj_dims[0]) / 2.0, swept, set(holds))
            surface_top = fitted["top_z_m"]
            cleared, leg_inset = fit_legs(
                np.asarray(fitted["centre_xy_m"]),
                (span_x / 2.0, span_y / 2.0), surface_top, TOP_THICKNESS_M,
                swept, fitted["yaw_deg"])
            # the object rests on whatever the surface turned out to be
            rest_before[2] = rest_after[2] = surface_top + half_h
            first, last, gap0, gap1 = grasp_span(grasp, holds, rest_before,
                                                 rest_after)
            carried = carried_track(grasp, first, last, rest_before, rest_after)
            handled["placement"]["held_frames"] = [first, last]
            handled["placement"]["grasp_transition_m"] = [round(gap0, 4),
                                                          round(gap1, 4)]
            if dev:
                dev.record(f"scene.{handled['label']}.grasp_transition", "scene",
                           0.0, max(gap0, gap1), "m", tolerance=None,
                           how="how far the object moves on the frame the hand "
                               "takes it -- the closest this trajectory brings "
                               "the hand to the object where it rests")
            handled["placement"]["rest_before_m"] = [round(float(v), 4)
                                                     for v in rest_before]
            handled["placement"]["rest_after_m"] = [round(float(v), 4)
                                                    for v in rest_after]
            support["placement"] = {
                "kind": "support_surface",
                "centre_xy_m": [round(v, 4) for v in fitted["centre_xy_m"]],
                "top_z_m": round(surface_top, 4),
                "size_m": [round(span_x, 4), round(span_y, 4),
                           round(surface_top, 4)],
                "yaw_deg": round(fitted["yaw_deg"], 2),
                "near_edge_m": round(fitted["edge_m"], 4),
                "edge_pulled_back_m": fitted["edge_pulled_back_m"],
                "top_lowered_m": fitted["top_lowered_m"],
                "edge_bound_by_object": fitted["edge_bound_by_object"],
                "top_thickness_m": TOP_THICKNESS_M,
                "leg_side_m": LEG_SIDE_M, "leg_inset": leg_inset,
                "legs_clear_of_robot": bool(cleared),
                "solid": bool(fitted["solid"]),
                "overlap_m": fitted["overlap_m"],
                "overlap_frames": fitted["overlap_frames"],
                "solid_rejected": fitted["solid_rejected"],
                "tier": "derived",
                "why": (f"its top is solved for the target, not taken from the "
                        f"catalog: the {handled['label']} rests at "
                        f"{surface_top + half_h:.4f} m, so the surface is at "
                        f"{surface_top:.4f} m. The catalog's "
                        f"{support['catalog']['dims_m'][2]:.2f} m at scene "
                        f"scale would be {float(dims_s[2]):.4f} m -- the same "
                        f"rule the seat follows, and the two agree to "
                        f"{abs(surface_top - float(dims_s[2])):.3f} m. "
                        f"Footprint at the one scene scale, oriented with its "
                        f"near edge across the reach, pulled back "
                        f"{fitted['edge_pulled_back_m']:.3f} m and lowered "
                        f"{fitted['top_lowered_m']:.3f} m. "
                        + ("No robot geometry passes through it, so it is a "
                           "collider and the physics pass measures it."
                           if fitted["solid"] else
                           f"No height clears the reach -- the hand is inside "
                           f"the plane the object rests on, by "
                           f"{fitted['overlap_m'] * 1000:.0f} mm at worst on "
                           f"{len(fitted['overlap_frames'])} frames of the "
                           f"approach and the withdrawal -- so the surface is "
                           f"scenery: geometry with its collider disabled. "
                           f"Nothing rests on it but an object the hand "
                           f"carries kinematically, and the overlap is the "
                           f"reach's to fix")),
            }
            placed.append(support)
            if prov:
                prov.derived(f"object.{support['label']}.position",
                             "the surface under the handled object: its height "
                             "from where that object rests, its footprint at "
                             "the scene scale", 1)
            if dev:
                dev.record(f"scene.{support['label']}.height_solved_vs_catalog",
                           "scene", float(dims_s[2]), surface_top, "m",
                           tolerance=None,
                           how="a support surface is solved for the target; "
                               "the catalog height at scene scale is what it "
                               "would have been")
                dev.record(f"scene.{support['label']}.reach_overlap", "scene",
                           0.0, float(fitted["overlap_m"]), "m",
                           tolerance=None,
                           how="how far the acting arm reaches inside the "
                               "surface it reaches over, with every link at "
                               "the radius of its own collision mesh -- a "
                               "reach defect, which is why the surface is "
                               "scenery rather than a collider")
                dev.record(f"scene.{support['label']}.top_lowered", "scene",
                           0.0, fitted["top_lowered_m"], "m", tolerance=None,
                           how="how far the surface had to drop below the "
                               "height the object rests at, so the reach that "
                               "takes the object does not pass through it")
                dev.record(f"scene.{support['label']}.legs_clear_of_robot",
                           "scene", 0.0, 0.0 if cleared else 1.0, "bool",
                           tolerance=0.0,
                           how="no robot link is inside a leg on any frame")

    # everything else keeps its image estimate, standing on the floor
    for h in by_label.values():
        if h.get("placement"):
            continue
        est = h.get("image_estimate")
        if est is None:
            notes.append(f"{h['label']}: no box to place it from; left out")
            continue
        if "sit" in (h["catalog"].get("afford") or []):
            notes.append(f"{h['label']}: the seat is solved from the robot's "
                         f"own pose by `invariants.seat_from_pose`, not placed "
                         f"from its box")
            continue
        dims = h.get("dims_scaled_m") or h["catalog"]["dims_m"]
        pos = list(est["position_m"])
        pos[2] = float(dims[2]) / 2.0            # standing on the floor
        h["placement"] = {"kind": "free_standing", "position_m":
                          [round(v, 4) for v in pos],
                          "size_m": [round(float(v), 4) for v in dims],
                          "yaw_deg": 0.0, "tier": est["tier"],
                          "why": "image estimate: " + est["why"]}
        placed.append(h)
        if prov:
            prov.record(f"object.{h['label']}.position", est["tier"],
                        est["why"], 1)

    report = {
        "placed": [{"label": h["label"], **h["placement"]} for h in placed],
        "image_estimates": {h["label"]: h.get("image_estimate")
                            for h in by_label.values()},
        "handled": handled["label"] if handled is not None else None,
        "acting_hand": hand,
        "notes": notes,
        "rule": ("physical consistency, then the task, then the image -- "
                 "the design's priority order, applied in that sequence"),
    }
    return placed, carried, report


# --------------------------------------------------------------------------
# the inputs this needs from elsewhere
# --------------------------------------------------------------------------
def image_plane(dataset):
    """The dataset's own image <-> canonical fit -- v1's function, reused.

    Not re-derived here on purpose: `fit_image_plane` measures the mapping from
    the landmarks CBD carries in both views, and a second implementation of it
    would be a second thing to keep true.
    """
    from pathlib import Path

    import cbd_adapter_groot_g1 as v1

    class _Landmarks:
        pose_landmarks_2d = v1.Cbd.pose_landmarks_2d

        def __init__(self, d):
            self.dir = Path(d)

    return v1.fit_image_plane(_Landmarks(dataset))


def robot_tracks(q, joint_names, root_pos, hand="right", boxes=None,
                 default_radius=0.04):
    """(grasp centre per frame, the robot's swept collision geometry), in world.

    The grasp centre is the midpoint of the palm and the middle fingertip --
    the middle of a closed hand, taken from the robot's own kinematics rather
    than authored as an offset, so a different hand changes it for free.

    The sweep is the corners of every link's collision box on every frame, each
    tagged with its frame and whether it belongs to the acting hand. The fit
    needs both tags. That hand has business at a surface -- it takes something
    off it -- but only while it is holding: leave it in for the whole clip and
    the fit pushes the table out from under the object it holds up; leave it
    out for the whole clip and the fingers sweep 63 mm through the top on the
    way in and out. Both were measured, in that order.
    """
    from invariants import forward_kinematics

    root = np.asarray(root_pos, float)
    boxes = boxes or {}
    corners = {}
    for name, (lo, hi) in boxes.items():
        corners[name] = np.array([[lo[0] if i else hi[0], lo[1] if j else hi[1],
                                   lo[2] if k else hi[2]]
                                  for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    grasp, swept = [], []
    for t in range(len(q)):
        P, R = forward_kinematics(q[t], joint_names, with_rot=True)
        palm = P.get(f"{hand}_hand_palm_link")
        tip = P.get(f"{hand}_hand_middle_1_link")
        if palm is None:
            palm = tip = P[f"{hand}_wrist_yaw_link"]
        elif tip is None:
            tip = palm
        grasp.append(root + (palm + tip) / 2.0)
        for k, v in P.items():
            is_hand = k.startswith(f"{hand}_hand")
            if k in corners:
                for w in root + v + corners[k] @ R[k].T:
                    swept.append((w, t, is_hand, 0.0))
            else:
                swept.append((root + v, t, is_hand, default_radius))
    return np.asarray(grasp), swept


def link_boxes(uri):
    """Each link's *collision* extent, as a box in that link's own frame.

    A link position is the origin of a frame, not the extent of a body, and
    treating it as a point is what let the first fit call a table clear while
    the hand's collision mesh was 3 cm inside it -- PhysX charged 55 deg of
    thumb tracking for the difference.

    A single radius per link is the other wrong answer: the G1's thigh collider
    is 0.63 m long, so its half-diagonal is 0.315 m and one link swallows the
    scene. The box is kept as a box and rotated with the link, which is exact
    enough for a slab test and costs eight points a link.
    """
    from pathlib import Path

    if not uri or "://" in uri or not Path(uri).exists():
        return {}, "asset not local; links fall back to a point plus a margin"
    try:
        from pxr import Usd, UsdGeom, UsdPhysics
        stage = Usd.Stage.Open(str(uri))
        root = stage.GetDefaultPrim()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                   UsdGeom.Tokens.guide, UsdGeom.Tokens.proxy])
        out = {}
        for link in root.GetChildren():
            colliders = [c for c in Usd.PrimRange(link)
                         if c.HasAPI(UsdPhysics.CollisionAPI)]
            if not colliders:
                continue
            inv = UsdGeom.Xformable(link).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default()).GetInverse()
            lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
            for c in colliders:
                r = cache.ComputeWorldBound(c).ComputeAlignedRange()
                mn, mx = r.GetMin(), r.GetMax()
                for i in (0, 1):
                    for j in (0, 1):
                        for k in (0, 1):
                            v = inv.Transform((mn[0] if i else mx[0],
                                               mn[1] if j else mx[1],
                                               mn[2] if k else mx[2]))
                            lo, hi = np.minimum(lo, v), np.maximum(hi, v)
            out[link.GetName()] = (lo, hi)
        return out, f"{len(out)} links, from the asset's own collision bounds"
    except Exception as e:                                   # noqa: BLE001
        return {}, f"could not read the asset ({e.__class__.__name__})"


def asset_bounds(uri):
    """The asset's own extent, so a catalog dimension can scale it.

    Only for an asset that resolves to a local file: usd-core cannot fetch a
    URL, and guessing is worse than saying so.
    """
    from pathlib import Path

    if not uri or "://" in uri or not Path(uri).exists():
        return None
    try:
        from pxr import Usd, UsdGeom
        stage = Usd.Stage.Open(str(uri))
        prim = stage.GetDefaultPrim()
        if not prim:
            return None
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        return ([float(v) for v in r.GetMin()], [float(v) for v in r.GetMax()])
    except Exception:                                        # noqa: BLE001
        return None
