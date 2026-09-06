#!/usr/bin/env python3
"""Run the v2 front end over a CBD dataset and show what it changes.

The v2 adapter replaces four decisions v1 made, all of them upstream of any
joint angle and none of them needing a GPU:

    cleanup        correct the capture before retargeting it, instead of
                   reproducing monocular error into a machine
    phases         derive the contact signal from the pose when CBD's own
                   phase field is degenerate
    scene_objects  weigh every channel before standing an object up, instead
                   of instantiating the detector's output
    provenance     record what filled every quantity, instead of refusing to
                   fill it

This is the reviewable half. Nothing here writes into the dataset or the
repository: it reads, decides, and prints. The asset swap and the physics pass
come next and need Isaac Sim; these do not.

    python v2_preview.py --dataset ../../examples/human-capture/sample_output
    python v2_preview.py --dataset <...> --json report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cleanup                    # noqa: E402
import invariants                 # noqa: E402
import phases                     # noqa: E402
import scene_objects              # noqa: E402
from provenance import Provenance  # noqa: E402


def find_dataset(spec: str) -> Path:
    p = Path(spec)
    for cand in (p, p / "04_behavior_dataset"):
        if (cand / "timeline/frames.jsonl").exists():
            return cand
    raise SystemExit(f"no 04_behavior_dataset under {spec}")


def read(dataset: Path):
    frames = [json.loads(l) for l
              in (dataset / "timeline/frames.jsonl").read_text("utf-8").splitlines()
              if l.strip()]
    manifest = json.loads((dataset / "manifest.json").read_text("utf-8"))
    summary = json.loads((dataset / "behavior_summary.json").read_text("utf-8"))
    inter = []
    ip = dataset / "interactions/interaction_events.csv"
    if ip.exists():
        with open(ip, newline="") as fh:
            inter = list(csv.DictReader(fh))
    return frames, manifest, summary, inter


def run(dataset: Path):
    frames, manifest, summary, interactions = read(dataset)
    pose = np.array([f["human"]["pose_canonical"] for f in frames], float)
    n = len(frames)
    fps = float(manifest.get("fps", 12.0))
    hand = (summary.get("primary_hand") or "right")
    prov = Provenance()

    # 1 -- cleanup
    clean_pose, clean_rep = cleanup.clean(pose)
    dims = cleanup.measure_segments(clean_pose)
    prov.measured("pose.landmarks", "pose_canonical, cleaned but not invented",
                  n * pose.shape[1])
    prov.derived("pose.segment_lengths", "medians over the clip", len(dims))

    # 2 -- phases
    labels, phase_rep = phases.resolve([f.get("phase") for f in frames],
                                       clean_pose, hand, fps, prov)

    # 3 -- objects
    facts = scene_objects.pose_requirements(
        clean_pose, dims, labels,
        [f["human"].get("joint_angles_deg", {}) for f in frames])
    catalog = scene_objects.load_catalog()
    captions = [f.get("caption") or {} for f in frames]
    accepted, rejected = scene_objects.arbitrate(
        dataset, summary, captions, interactions, facts, n)
    for h in accepted:
        prov.record(f"object.{h['label']}", h["tier"], h["decision"], n)
    made = scene_objects.synthesize_missing(accepted, facts, catalog, prov, n)
    resolved = [scene_objects.resolve(h, catalog) for h in accepted + made]

    # 4 -- what must survive every later stage
    inv = invariants.derive(clean_pose, dims, labels, facts, prov)
    resolved, scene_scale = scene_objects.fit_scene_to_target(resolved, inv, prov)
    checks = invariants.check_scene(inv, resolved)

    return {
        "invariants": inv, "invariant_checks": checks, "scene_scale": scene_scale,
        "dataset": str(dataset), "frames": n, "fps": fps, "primary_hand": hand,
        "cleanup": clean_rep, "phases": phase_rep, "pose_facts": facts,
        "objects": {"accepted": accepted, "rejected": rejected,
                    "synthesized": made, "resolved": resolved},
        "provenance": prov.report(),
        "_summary_line": prov.summary_line(),
    }


def show(r):
    w = print
    w("=" * 78)
    w(f"CBD -> G1 adapter v2 front end   {r['dataset']}")
    w(f"{r['frames']} frames @ {r['fps']:g} fps, primary hand {r['primary_hand']}")
    w("=" * 78)

    c = r["cleanup"]
    w("\n1. CLEANUP -- correcting the capture before retargeting it")
    for line in c["applied"]:
        w(f"   - {line}")
    w("\n   midline crossings beyond the allowed margin (frames):")
    for k in sorted(c["before"]["midline"]):
        b, a = c["before"]["midline"][k], c["after"]["midline"][k]
        if b["beyond_limit_frames"] or a["beyond_limit_frames"]:
            w(f"     {k:<8} {b['beyond_limit_frames']:>3} -> {a['beyond_limit_frames']:>3}"
              f"   (max {b['max_cross_m']:.3f} -> {a['max_cross_m']:.3f} m,"
              f" allowed {a['allowed_m']:.3f})")
    w("\n   reach ratio -- above 1.000 the limb is longer than its own bones:")
    for k in sorted(c["before"]["reach_ratio"]):
        b, a = c["before"]["reach_ratio"][k], c["after"]["reach_ratio"][k]
        flag = "  <- impossible" if b > 1.0 else ""
        w(f"     {k:<6} {b:.3f} -> {a:.3f}{flag}")
    drift = sorted(c["before"]["segment_drift"].items(), key=lambda kv: -kv[1])[:3]
    w("\n   worst bone-length drift over the clip:")
    for k, v in drift:
        w(f"     {k:<22} {v:>5.0%} -> {c['after']['segment_drift'][k]:.0%}")
    d = c["displacement_m"]
    w(f"\n   correction applied: mean {d['mean']*100:.1f} cm, "
      f"p95 {d['p95']*100:.1f} cm, max {d['max']*100:.1f} cm")

    p = r["phases"]
    w(f"\n2. PHASES -- source: {p['source']}")
    if p.get("why"):
        w(f"   {p['why']}")
    for s in p.get("segments", []):
        w(f"     {s['phase']:<8} frames {s['start_frame']:>3}-{s['end_frame']:<3}"
          f" ({s['start_sec']:.2f}-{s['end_sec']:.2f}s)")

    f = r["pose_facts"]
    w(f"\n3. SCENE -- {f['seated_because']}")
    o = r["objects"]
    w(f"\n   accepted ({len(o['accepted'])}):")
    for h in o["accepted"]:
        w(f"     {h['label']:<14} {h['clip_rate']:>6.0%}  [{h['tier']}] {h['decision']}")
        for c2 in h["corroboration"]:
            w(f"       + {c2}")
        if h["merged_from"]:
            w(f"       + merged duplicate tracks {h['merged_from']}")
    w(f"\n   rejected ({len(o['rejected'])}):")
    for h in o["rejected"]:
        w(f"     {h['label']:<14} {h['clip_rate']:>6.0%}  {h['decision']}")
    w(f"\n   synthesized ({len(o['synthesized'])}):")
    for h in o["synthesized"]:
        w(f"     {h['label']:<14}         [{h['tier']}] {h['decision']}")
    w("\n   resolution:")
    for h in o["resolved"]:
        if h.get("catalog"):
            cat = h["catalog"]
            w(f"     {h['label']:<14} {h['resolution']:<10} "
              f"{cat['dims_m']} m  {cat['body']}"
              + (f"  asset {cat['asset']}" if cat["asset"] else ""))
            if h.get("dims_scaled_m"):
                extra = (f"  support top {h['support_top_m']:.3f} m "
                         f"(catalog {h['support_catalog_m']:.3f})"
                         if h.get("support_top_m") is not None else "")
                w(f"       at scene scale {h['dims_scaled_m']} m{extra}")

    ss = r["scene_scale"]
    w("\n4. INVARIANTS -- what no later stage may break")
    w(f"   scene scale x{ss['scale']:.4f}  ({ss['why']})")
    for i in r["invariants"]:
        w(f"     {i['name']:<14} [{i['source']}] {i['evidence']}")
        for req in i["requires"]:
            w(f"       requires: {req}")
        w(f"       breaks if: {i['breaks_if']}")
    for c in r["invariant_checks"]:
        mark = {"ok": "ok  ", "FAIL": "FAIL", "deferred": "--  "}[c["status"]]
        w(f"     [{mark}] {c['invariant']} @ {c['stage']}: {c['note']}")

    pr = r["provenance"]
    w("\n5. PROVENANCE")
    for t, v in pr["tiers"]["ratio"].items():
        if v:
            w(f"     {t:<12} {v:>6.1%}")
    e = pr["evidence"]
    w(f"   {'PASS' if e['passed'] else 'FAIL'}: {e['note']}")
    if pr["unavailable"]:
        w(f"   unavailable (should be empty): {pr['unavailable']}")
    if pr["spec_feedback"]:
        w("\n   schema gaps this run had to paper over:")
        for gap, qs in pr["spec_feedback"].items():
            w(f"     - {gap}\n       ({', '.join(qs)})")
    w("")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--json", help="also write the full report here")
    a = ap.parse_args(argv)
    r = run(find_dataset(a.dataset))
    show(r)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1, ensure_ascii=False), "utf-8")
        print(f"written: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
