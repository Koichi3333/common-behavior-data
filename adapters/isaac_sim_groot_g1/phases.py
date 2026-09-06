#!/usr/bin/env python3
"""What the subject is doing, per frame -- from CBD when it says, from the
pose when it does not.

The design wants the retarget's objective to change with the phase: while the
hand is free, matching the human's joint angles is what makes the result look
like the source; while the hand is *on* something, the hand's position in space
matters more than any joint angle, because a grasp that does not touch is worth
nothing in a video and worse than nothing in a training set.

That plan needs a phase signal. Canonical CBD has a `phase` field, and on the
sample dataset it is degenerate:

    phase: {("Pick And Place", "Idle"): 96}      all 96 frames
    interaction_events.csv:                      empty

while the pose says the opposite -- the right wrist travels from 0.316 m to
0.552 m from its shoulder and back. The caption agrees with the pose:
"reaches out, grabs a glass of water from the table, and drinks from it".

So this module trusts `phase` when it carries information (tier `measured`) and
re-derives it from the wrist excursion when it does not (tier `derived`). It
never writes its conclusion back into the CBD interaction stream: adapter rule
4 is *do not promote candidates*, and a phase this module inferred is not an
observed `grasp`. It stays here, as the adapter's own weighting signal.
"""
from __future__ import annotations

import numpy as np

LM = {"l_sh": 11, "r_sh": 12, "l_elb": 13, "r_elb": 14, "l_wri": 15, "r_wri": 16}

PHASES = ("idle", "reach", "hold", "retract")

# how much of the objective goes to task space rather than joint fidelity
TASK_WEIGHT = {"idle": 0.0, "reach": 0.6, "hold": 1.0, "retract": 0.4}

MIN_EXCURSION = 0.12    # fraction of arm length; below this nothing happened
ENTER, EXIT = 0.55, 0.35   # hysteresis on the normalised excursion
HOLD_SPEED = 0.35          # of peak speed -- slow near the peak means holding
HOLD_BAND = 0.25           # within this much of a bout's own peak counts as "at" it
MIN_BOUT_FRAMES = 3        # shorter than this is jitter, not a reach


def cbd_phase_is_informative(phases) -> bool:
    """False when every frame carries the same label (or none at all)."""
    labels = {(p or {}).get("phase") for p in phases}
    labels.discard(None)
    return len(labels) > 1


def excursion(pose: np.ndarray, hand: str):
    """Wrist distance from its shoulder, over the arm's own chain length."""
    s = "r" if hand.lower().startswith("r") else "l"
    sh, elb, wri = pose[:, LM[f"{s}_sh"]], pose[:, LM[f"{s}_elb"]], pose[:, LM[f"{s}_wri"]]
    chain = (float(np.median(np.linalg.norm(sh - elb, axis=1)))
             + float(np.median(np.linalg.norm(elb - wri, axis=1))))
    d = np.linalg.norm(wri - sh, axis=1)
    return d / max(chain, 1e-9), d, chain


def _speed(pose, hand, fps):
    s = "r" if hand.lower().startswith("r") else "l"
    w = pose[:, LM[f"{s}_wri"]]
    v = np.zeros(len(w))
    if len(w) > 1:
        v[1:] = np.linalg.norm(np.diff(w, axis=0), axis=1) * fps
        v[0] = v[1]
    return v


def estimate(pose: np.ndarray, hand: str = "right", fps: float = 12.0):
    """Per-frame phase from the pose alone. Returns (labels, detail)."""
    ext, dist, chain = excursion(pose, hand)
    lo, hi = float(np.percentile(ext, 20)), float(ext.max())
    span = hi - lo
    n = len(ext)
    if span < MIN_EXCURSION:
        return ["idle"] * n, {
            "method": "pose excursion", "hand": hand, "arm_chain_m": round(chain, 4),
            "excursion_span": round(span, 4),
            "verdict": f"span {span:.3f} < {MIN_EXCURSION} -- no reach in this clip",
            "segments": [], "counts": {"idle": n}}

    norm = (ext - lo) / span
    v = _speed(pose, hand, fps)
    vpeak = float(v.max()) or 1.0

    # 1. activity bouts, by hysteresis on the excursion. A clip can hold more
    #    than one -- the sample has two, "take" and "put back", which is what
    #    its two captions describe.
    active, on = np.zeros(n, bool), False
    for i in range(n):
        if not on and norm[i] >= ENTER:
            on = True
        elif on and norm[i] < EXIT:
            on = False
        active[i] = on
    bouts, start = [], None
    for i in range(n + 1):
        if i < n and active[i] and start is None:
            start = i
        elif (i == n or not active[i]) and start is not None:
            if i - start >= MIN_BOUT_FRAMES:
                bouts.append((start, i - 1))
            start = None

    # 2. label inside each bout against *its own* peak, not a global one --
    #    otherwise the second bout is read as one long retraction from the first.
    labels = ["idle"] * n
    for a, b in bouts:
        seg = ext[a:b + 1]
        peak = a + int(np.argmax(seg))
        near = seg >= (seg.max() - HOLD_BAND * span)
        for i in range(a, b + 1):
            slow = v[i] / vpeak < HOLD_SPEED
            if near[i - a] and slow:
                labels[i] = "hold"
            else:
                labels[i] = "reach" if i < peak else "retract"
        if "hold" not in labels[a:b + 1]:
            labels[peak] = "hold"

    segs, start = [], 0
    for i in range(1, n + 1):
        if i == n or labels[i] != labels[start]:
            segs.append({"phase": labels[start], "start_frame": start,
                         "end_frame": i - 1,
                         "start_sec": round(start / fps, 2),
                         "end_sec": round((i - 1) / fps, 2)})
            start = i
    counts = {p: labels.count(p) for p in PHASES if labels.count(p)}
    return labels, {
        "method": "pose excursion", "hand": hand, "arm_chain_m": round(chain, 4),
        "excursion_m": {"min": round(float(dist.min()), 4),
                        "max": round(float(dist.max()), 4),
                        "peak_frame": peak},
        "excursion_span": round(span, 4),
        "bouts": [{"start_frame": a, "end_frame": b} for a, b in bouts],
        "thresholds": {"enter": ENTER, "exit": EXIT, "hold_speed": HOLD_SPEED,
                       "hold_band": HOLD_BAND, "min_bout_frames": MIN_BOUT_FRAMES},
        "segments": segs, "counts": counts}


def resolve(cbd_phases, pose: np.ndarray, hand: str, fps: float, prov=None):
    """Use CBD's phase if it says anything; otherwise derive it from the pose.

    Returns (labels, detail). `prov` is a Provenance ledger, if one is running.
    """
    n = len(pose)
    if cbd_phase_is_informative(cbd_phases):
        labels = [str((p or {}).get("phase", "idle")).lower() for p in cbd_phases]
        detail = {"source": "cbd", "method": "frames.jsonl phase",
                  "counts": {l: labels.count(l) for l in set(labels)}}
        if prov:
            prov.measured("phase", "frames.jsonl carries per-frame phase", n)
        return labels, detail

    labels, detail = estimate(pose, hand, fps)
    detail["source"] = "derived"
    detail["why"] = ("canonical phase is degenerate (one label for every frame) "
                     "and interaction_events is empty, so the retarget would "
                     "have no contact signal to weight against")
    if prov:
        prov.derived("phase", "re-derived from wrist excursion -- CBD phase was "
                              "one label for every frame", n,
                     detail={"counts": detail.get("counts")})
    return labels, detail


def task_weights(labels):
    """Per-frame weight for task-space goals versus joint-angle fidelity."""
    return np.array([TASK_WEIGHT.get(l, 0.0) for l in labels], float)
