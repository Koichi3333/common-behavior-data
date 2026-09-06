#!/usr/bin/env python3
"""Which objects are actually in the scene -- from every channel, not just the
detector.

v1 instantiated the detector's output and nothing else, and on the sample
dataset that is wrong three ways at once:

    obj_001  chair          96/96 frames            the chair she sits on
    obj_003  chair          47/49 frames            a second chair, by the table
    obj_004  chair           1 frame                spurious -- v1 would stand it up
    obj_005  cup             1 frame (rate 0.01)    the glass the clip is *about*
                                                    -- v1 dropped it

The dropped one matters most: `behavior_summary.primary_object` names that cup,
the caption says "grabs a glass of water from the table", and the wrist travels
0.31 m -> 0.55 m and back. Three channels agree the object is there; only the
detector, which saw a small transparent thing for one frame out of ninety-six,
does not. v1 read the detector alone and reported "no glass, cup or other prop
is placed", so the robot mimed a grasp on empty air.

So an object here is a *hypothesis*, weighed against six channels:

    1 detections / tracks       position and label -- and duplicates, splits,
                                spurious singletons and misses
    2 behavior_summary          which object the clip is about
    3 caption                   what is being sat on, taken, put down
    4 interaction_events        observed contact (often empty)
    5 the subject's own pose    sitting proves a seat; reaching proves a target
    6 object_metrics            detection rate, hand distance

Rule 4 of the adapter contract -- *do not promote candidates* -- is why nothing
here writes back into CBD's interaction stream. Accepting the cup places
geometry; it does not turn a `grasp_candidate` into a `grasp`. The distinction
is the whole reason the synthesis is safe.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "object_catalog.json"

# a detection this sparse needs corroboration; above it, the detector is enough
WELL_DETECTED = 0.25
# same label, centres this close, both stationary -> one object seen twice
MERGE_RADIUS = 0.12

# words a caption may use for a COCO label. Small and explicit on purpose: this
# is a lookup table, not language understanding.
SYNONYMS = {
    "cup": ("cup", "glass", "mug"), "dining table": ("table", "desk", "worktop"),
    "couch": ("couch", "sofa", "settee"), "tv": ("tv", "television", "screen"),
    "cell phone": ("phone", "cellphone", "smartphone"), "potted plant": ("plant", "pot"),
    "wine glass": ("wine", "glass", "goblet"), "remote": ("remote", "controller"),
    "laptop": ("laptop", "notebook", "computer"), "bottle": ("bottle", "flask"),
}


def load_catalog(path=CATALOG_PATH):
    return json.loads(Path(path).read_text("utf-8"))


def _spend(spent, label):
    """Mark a label -- and the affordances only one object can satisfy -- used."""
    spent.add(label)
    afford = load_catalog()["classes"].get(label, {}).get("afford", [])
    if "sit" in afford:
        spent.add("afford:sit")


def _synonyms(label):
    return SYNONYMS.get(label, (label,)) + tuple(label.split())


# --------------------------------------------------------------------------
# channel 1 + 6 -- what the detector and the tracker actually said
# --------------------------------------------------------------------------
def gather(dataset: Path):
    """Per-track statistics, with the median bbox matched in from detections."""
    dataset = Path(dataset)
    tracks = defaultdict(list)
    with open(dataset / "objects/object_tracks.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            tracks[r["track_id"]].append(r)
    dets = defaultdict(list)
    with open(dataset / "objects/object_detections.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            dets[(int(r["frame"]), r["label"])].append(r)

    out = {}
    for tid, rows in tracks.items():
        label = rows[0]["label"]
        seen = [r for r in rows if r["detected"] == "True"]
        c = np.array([[float(r["center_x"]), float(r["center_y"])] for r in rows])
        # the bbox of the detection nearest this track, frame by frame
        boxes = []
        for r in seen:
            cand = dets.get((int(r["frame"]), r.get("detector_label") or label), [])
            if not cand:
                continue
            cx, cy = float(r["center_x"]), float(r["center_y"])
            best = min(cand, key=lambda d: (float(d["bbox_x"]) + float(d["bbox_width"]) / 2 - cx) ** 2
                       + (float(d["bbox_y"]) + float(d["bbox_height"]) / 2 - cy) ** 2)
            boxes.append((float(best["bbox_width"]), float(best["bbox_height"])))
        b = np.array(boxes) if boxes else np.zeros((0, 2))
        out[tid] = {
            "track_id": tid, "label": label,
            "role": rows[0].get("role", ""), "frames": len(rows),
            "detected": len(seen),
            "detection_rate": round(len(seen) / max(len(rows), 1), 4),
            "clip_rate": None,          # filled by arbitrate(), needs the frame count
            "center": [round(float(c[:, 0].mean()), 4), round(float(c[:, 1].mean()), 4)],
            "spread": [round(float(c[:, 0].std()), 4), round(float(c[:, 1].std()), 4)],
            "stationary": all(r.get("motion_state") == "stationary" for r in rows),
            "bbox_median": ([round(float(np.median(b[:, 0])), 4),
                             round(float(np.median(b[:, 1])), 4)] if len(b) else None),
        }
    return out


def merge_duplicates(stats):
    """One object seen as two tracks becomes one hypothesis."""
    order = sorted(stats.values(), key=lambda s: -s["detected"])
    groups, merged = [], {}
    for s in order:
        for g in groups:
            h = g[0]
            if (h["label"] == s["label"] and h["stationary"] and s["stationary"]
                    and np.hypot(h["center"][0] - s["center"][0],
                                 h["center"][1] - s["center"][1]) < MERGE_RADIUS):
                g.append(s)
                merged.setdefault(h["track_id"], []).append(s["track_id"])
                break
        else:
            groups.append([s])
    return groups, merged


# --------------------------------------------------------------------------
# channels 2-6 -- corroboration
# --------------------------------------------------------------------------
def corroborate(label, track_ids, summary, captions, interactions, pose_facts,
                spent=None):
    """Reasons, from channels other than the detector, to believe this exists.

    `spent` carries the labels *and affordances* whose corroboration a better
    detected hypothesis already used. "The caption says there is a chair" is
    evidence for one chair, not for every marginal chair box in the clip, and a
    subject sits on exactly one seat -- without this, the sample's one-frame
    spurious chair rides in on the same sentence, and then on the same pelvis,
    that vouch for the chair she is actually sitting on. Evidence naming a
    specific track is never spent: it points at one object.
    """
    found = []
    spent = spent if spent is not None else set()
    used_label = label in spent
    primary = ((summary or {}).get("primary_object") or {})
    if primary.get("track_id") in track_ids:
        found.append(("behavior_summary", "named as the clip's primary_object"))
    elif primary.get("label") == label and not used_label:
        found.append(("behavior_summary", "its label is the clip's primary_object"))
    words = _synonyms(label)
    if not used_label:
        for cap in captions:
            text = " ".join(str(cap.get(k, "")) for k in ("en", "ja")).lower()
            hit = [w for w in words if w in text]
            if hit:
                found.append(("caption", f"mentioned as {hit[0]!r}"))
                break
    if any(str(e.get("object_id")) in track_ids for e in interactions):
        found.append(("interaction_events", "carries an observed contact"))
    if ("sit" in (pose_facts.get("needs") or [])
            and label in pose_facts.get("sit_labels", ())
            and "afford:sit" not in spent):
        found.append(("pose", "the subject is seated and this can be sat on"))
    return found


def arbitrate(dataset: Path, summary, captions, interactions, pose_facts, n_frames):
    """Accept, merge or reject every track. Returns (accepted, rejected)."""
    stats = gather(dataset)
    for s in stats.values():
        s["clip_rate"] = round(s["detected"] / max(n_frames, 1), 4)
    groups, merged = merge_duplicates(stats)

    accepted, rejected = [], []
    spent = set()   # labels whose caption / summary mention is already claimed
    groups.sort(key=lambda g: -sum(s["detected"] for s in g))
    for g in groups:
        head = g[0]
        ids = [s["track_id"] for s in g]
        detected = sum(s["detected"] for s in g)
        rate = detected / max(n_frames, 1)
        support = corroborate(head["label"], ids, summary, captions,
                              interactions, pose_facts, spent)
        hyp = {
            "label": head["label"], "track_ids": ids, "role": head["role"],
            "detected_frames": detected, "clip_rate": round(rate, 4),
            "center": head["center"], "bbox_median": head["bbox_median"],
            "stationary": head["stationary"],
            "merged_from": merged.get(head["track_id"], []),
            "corroboration": [f"{c}: {why}" for c, why in support],
        }
        if rate >= WELL_DETECTED:
            hyp["tier"], hyp["decision"] = "measured", (
                f"detected in {rate:.0%} of frames -- the detector alone is enough")
            accepted.append(hyp)
            _spend(spent, head["label"])
        elif support:
            hyp["tier"], hyp["decision"] = "derived", (
                f"detected in only {rate:.0%} of frames, but "
                + " and ".join(c for c, _ in support) + " corroborate it")
            accepted.append(hyp)
            _spend(spent, head["label"])
        else:
            hyp["tier"], hyp["decision"] = None, (
                f"detected in {rate:.0%} of frames with nothing else to support it "
                "-- spurious")
            rejected.append(hyp)
    return accepted, rejected


# --------------------------------------------------------------------------
# what the pose alone proves must be there
# --------------------------------------------------------------------------
SEATED_KNEE_DEG = 140.0    # 180 is a straight leg; a seated knee is near 90


def pose_requirements(pose: np.ndarray, dims, phase_labels, joint_angles=None):
    """Facts about the scene that follow from the body, not from any detector.

    Seatedness is read from the *measured* knee flexion, not from how high the
    pelvis sits. Monocular capture of a seated subject foreshortens the legs
    badly -- on the sample the pelvis lands 95% of a leg length above the floor,
    which reads as standing, while the knees are bent to 109 deg, which is not
    something a standing person does. The angle is in the dataset; the height
    is an artefact of the view.
    """
    LMh = {"l_hip": 23, "r_hip": 24, "l_ank": 27, "r_ank": 28, "l_heel": 29,
           "r_heel": 30, "l_toe": 31, "r_toe": 32}
    pelvis = (pose[:, LMh["l_hip"]] + pose[:, LMh["r_hip"]]) / 2.0
    floor_y = float(pose[:, [LMh["l_heel"], LMh["r_heel"],
                             LMh["l_toe"], LMh["r_toe"]], 1].min())
    leg = dims["upper_leg"] + dims["lower_leg"]
    pelvis_h = float(np.median(pelvis[:, 1])) - floor_y
    knee = None
    if joint_angles:
        vals = [a[k] for a in joint_angles for k in
                ("left_knee_flexion", "right_knee_flexion") if k in a]
        if vals:
            knee = float(np.median(vals))
    if knee is not None:
        seated = knee < SEATED_KNEE_DEG
        by_height = pelvis_h < 0.75 * leg
        agree = "agrees" if by_height == seated else "disagrees, and is the artefact"
        why = (f"median knee flexion {knee:.0f} deg "
               f"({'<' if seated else '>='} {SEATED_KNEE_DEG:.0f}) -- "
               f"{'seated' if seated else 'standing'}; the pelvis height "
               f"({pelvis_h / leg:.0%} of leg) {agree}")
    else:
        seated = pelvis_h < 0.75 * leg
        why = (f"no knee angle in the dataset; pelvis at {pelvis_h / leg:.0%} "
               f"of leg length -- {'seated' if seated else 'standing'}")
    needs = ["floor"]
    if seated:
        needs.append("sit")
    if any(l in ("reach", "hold") for l in phase_labels):
        needs.append("reach_target")
    return {
        "floor_y": round(floor_y, 4),
        "pelvis_height_m": round(pelvis_h, 4),
        "leg_length_m": round(leg, 4),
        "seated": bool(seated),
        "knee_flexion_deg": (round(knee, 1) if knee is not None else None),
        "seated_because": why,
        "needs": needs,
        "sit_labels": tuple(sorted(
            k for k, v in load_catalog()["classes"].items() if "sit" in v["afford"])),
    }


def synthesize_missing(accepted, pose_facts, catalog, prov=None, n_frames=1):
    """Author what the pose requires and the detector did not supply."""
    have = {h["label"] for h in accepted}
    classes = catalog["classes"]
    made = []

    def add(label, why, gap=None):
        spec = classes.get(label, {})
        made.append({"label": label, "tier": "synthesized", "decision": why,
                     "track_ids": [], "clip_rate": 0.0, "corroboration": ["pose"],
                     "catalog": spec})
        if prov:
            prov.synthesized(f"object.{label}", why, n_frames, spec_gap=gap)

    if "floor" in pose_facts["needs"]:
        made.append({"label": "_floor", "tier": "derived", "track_ids": [],
                     "clip_rate": 0.0, "corroboration": ["pose"],
                     "decision": f"lowest foot landmark, y = {pose_facts['floor_y']:.3f}"})
        if prov:
            prov.derived("object._floor", "floor plane from the lowest foot landmark",
                         n_frames)
    if "sit" in pose_facts["needs"] and not (have & set(pose_facts["sit_labels"])):
        add("chair", "the subject is seated and no sit-able object was detected; "
                     "a seat has to exist or the robot floats",
            gap="no channel states what the subject is supported by")
    if "reach_target" in pose_facts["needs"]:
        graspable = [h for h in accepted
                     if "grasp" in classes.get(h["label"], {}).get("afford", [])]
        if not graspable:
            add("cup", "the hand reaches and holds but no graspable object survived; "
                       "a grasp on empty air is worse than a wrong prop",
                gap="no channel carries the 3D position of the object being handled")
    return made


def fit_scene_to_target(resolved, invariant_list, prov=None):
    """Scale the scene so the target can actually use it -- one factor, anchored
    on the clip's decisive invariant.

    Solving each surface on its own looks tidier and is wrong: drop the seat to
    the G1's 0.353 m and leave the table at its human 0.75 m, and the robot now
    sits 0.10 m lower under a table that did not move. The subject's relationship
    to her own furniture -- the thing the clip is actually about -- is gone.

    So the scene takes **one** scale, and the decisive invariant sets it:

        scale = seat height the target needs / seat height the catalog carries

    which is v1's instinct -- *"the robot is not resized; the room is"* -- with
    the arbitrary ratio replaced by a number derived from the robot's own shank.
    On the sample that is 0.3526 / 0.45 = 0.784. The sanity check is that it
    lands where a body-proportion argument would put it -- the URDF measures
    1.261 m from sole to head-camera frame, roughly three quarters of an adult --
    without ever having been told a human height. Same answer, independent route.

    Graspable objects scale too. A real-size mug in a Dex3 hand is a mug the
    robot cannot close its fingers around, and "the task happens" outranks
    "the prop measures 9 cm".

    The cost is stated plainly: the scene is at scene scale, not life size, and
    `dims_scaled_m` sits next to the catalog's `dims_m` so a consumer can see
    both. A dataset consumer who needs metric furniture wants the catalog value
    and the scale, which are both in the report.
    """
    seated = next((i for i in invariant_list if i["name"] == "seated"), None)
    scale, why = 1.0, "nothing decisive constrains the scene; catalog scale"
    if seated:
        catalog_seat = None
        for h in resolved:
            cat = h.get("catalog") or {}
            if "sit" in (cat.get("afford") or []) and cat.get("support"):
                catalog_seat = float(cat["support"][0]["h"])
                break
        if catalog_seat:
            scale = float(seated["seat_top_m"]) / catalog_seat
            why = (f"seat {seated['seat_top_m']:.4f} m (solved for the G1) over "
                   f"catalog {catalog_seat:.3f} m -- {seated['seat_why']}")
    for h in resolved:
        cat = h.get("catalog") or {}
        if not cat:
            continue
        h["scene_scale"] = round(scale, 4)
        h["dims_scaled_m"] = [round(v * scale, 4) for v in cat["dims_m"]]
        surfaces = cat.get("support") or []
        if surfaces:
            h["support_top_m"] = round(float(surfaces[0]["h"]) * scale, 4)
            h["support_catalog_m"] = float(surfaces[0]["h"])
    if prov:
        prov.derived("scene.scale", why, 1, detail={"scale": round(scale, 4)})
    return resolved, {"scale": round(scale, 4), "why": why,
                      "anchor": "seated" if seated else None}


def resolve(hypothesis, catalog):
    """Attach the catalog entry, or fall back to a parametric primitive."""
    cls = catalog["classes"].get(hypothesis["label"])
    if cls is None:
        hypothesis["resolution"] = "unresolved"
        hypothesis["catalog"] = None
        return hypothesis
    hypothesis["catalog"] = cls
    hypothesis["resolution"] = "asset" if cls["asset"] else "primitive"
    return hypothesis
