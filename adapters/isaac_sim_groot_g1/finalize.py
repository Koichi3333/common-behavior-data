#!/usr/bin/env python3
"""Assemble the v2 output directory: the trajectory that survived physics.

Everything upstream decides; this writes the deliverable. The joint angles it
publishes are `q_actual` -- what the robot did once PhysX had resolved contact
and self-collision -- rather than `q_target`, which is what the retarget asked
for and v1 shipped unchecked. The gap between them is in `adapter_report.json`
under `physics.tracking_*`, per joint, so choosing the measured one costs no
information.

The GR00T-LeRobot dataset is *patched* rather than regenerated: the layout, the
meta and the episode structure are v1's and are correct, and only the 43-wide
joint vectors changed. Rewriting `observation.state` and `action` in place, and
the two matching entries in `meta/stats.json`, keeps this from becoming a second
implementation of a file format that already works.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np


def write_csv(path: Path, q, names, timestamps):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "timestamp_sec"] + list(names))
        for t in range(len(q)):
            w.writerow([t, round(float(timestamps[t]), 6)]
                       + [round(float(v), 6) for v in q[t]])
    return path


def patch_lerobot(src: Path, dst: Path, q):
    """Copy v1's dataset and swap in the joint vectors that survived physics.

    Anything already written into the destination's `videos/` is kept: the ego
    view is rendered from the v2 stage by `compose_video.py`, and re-copying
    v1's over it would put the capsule stand-in back into a dataset whose
    states are the real robot's.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    keep = None
    if (dst / "videos").exists():
        keep = dst.parent / (dst.name + ".videos.keep")
        if keep.exists():
            shutil.rmtree(keep)
        shutil.copytree(dst / "videos", keep)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if keep is not None:
        if (dst / "videos").exists():
            shutil.rmtree(dst / "videos")
        shutil.copytree(keep, dst / "videos")
        shutil.rmtree(keep)
    pfile = next((dst / "data").rglob("*.parquet"))
    table = pq.read_table(pfile)
    if table.num_rows != len(q):
        raise SystemExit(f"{table.num_rows} rows but {len(q)} frames")
    rows = [[float(v) for v in row] for row in q]
    cols, names = [], []
    for name in table.schema.names:
        names.append(name)
        if name in ("observation.state", "action"):
            cols.append(pa.array(rows, type=table.schema.field(name).type))
        else:
            cols.append(table.column(name))
    pq.write_table(pa.Table.from_arrays(cols, names=names), pfile)

    stats_path = dst / "meta/stats.json"
    stats = json.loads(stats_path.read_text("utf-8"))
    a = np.asarray(q, float)
    for key in ("observation.state", "action"):
        if key in stats:
            stats[key] = {
                "mean": a.mean(0).tolist(), "std": a.std(0).tolist(),
                "min": a.min(0).tolist(), "max": a.max(0).tolist(),
                "q01": np.percentile(a, 1, axis=0).tolist(),
                "q99": np.percentile(a, 99, axis=0).tolist()}
    stats_path.write_text(json.dumps(stats, indent=2), "utf-8")
    return pfile


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default=None, help="default <dataset>/07_groot_g1_v2")
    ap.add_argument("--v1", default=None, help="default <dataset>/06_groot_g1")
    a = ap.parse_args(argv)

    ds = Path(a.dataset)
    out = Path(a.out) if a.out else ds / "07_groot_g1_v2"
    v1 = Path(a.v1) if a.v1 else ds / "06_groot_g1"

    settle = np.load(out / "settle_final.npz")
    q = np.asarray(settle["joint_angles_rad"], float)
    names = [str(s) for s in settle["joint_names"]]
    target = np.asarray(settle["joint_angles_target_rad"], float)
    v1z = np.load(v1 / "motion.npz")
    stage = json.loads((out / "stage_report.json").read_text("utf-8"))
    physics = json.loads((out / "settle_final.json").read_text("utf-8"))
    ts = np.asarray(v1z["timestamp_sec"], float)

    write_csv(out / "g1_joint_trajectory.csv", q, names, ts)
    np.savez_compressed(
        out / "motion.npz", joint_names=np.array(names),
        joint_angles_rad=q.astype("float32"),
        joint_angles_target_rad=target.astype("float32"),
        joint_angles_v1_rad=np.asarray(v1z["joint_angles_rad"], "float32"),
        joint_limits_rad=np.asarray(v1z["joint_limits_rad"], "float32"),
        pelvis_position_robot=np.asarray(v1z["pelvis_position_robot"], "float32"),
        pelvis_orientation_wxyz=np.asarray(v1z["pelvis_orientation_wxyz"], "float32"),
        fps=np.asarray(v1z["fps"], "float32"), timestamp_sec=ts.astype("float32"))
    parquet = patch_lerobot(v1 / "groot_lerobot", out / "groot_lerobot", q)

    d_v1 = np.degrees(np.abs(q - np.asarray(v1z["joint_angles_rad"], float)))
    report = {
        "adapter": "cbd_adapter_groot_g1 v2",
        "publishes": "q_actual -- the trajectory after the physics pass",
        "source": stage,
        "physics": {k: physics[k] for k in
                    ("settings", "articulation_root", "drive_api", "tracking",
                     "contact") if k in physics},
        "deviations": physics.get("deviations"),
        "stage_deviations": stage.get("stage_deviations"),
        "stage_provenance": stage.get("stage_provenance"),
        "change_from_v1_deg": {
            "rmse": round(float(np.sqrt((d_v1 ** 2).mean())), 3),
            "max": round(float(d_v1.max()), 3),
            "per_joint_max": {names[i]: round(float(d_v1[:, i].max()), 3)
                              for i in np.argsort(-d_v1.max(0))[:8]}},
        "writes": ["motion_baked.usda", "motion.npz", "g1_joint_trajectory.csv",
                   "groot_lerobot/", "settle_final.json", "stage_report.json"],
    }
    (out / "adapter_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), "utf-8")
    print(json.dumps({"csv": str(out / "g1_joint_trajectory.csv"),
                      "parquet": str(parquet),
                      "change_from_v1_deg": report["change_from_v1_deg"]["rmse"],
                      "max_change_deg": report["change_from_v1_deg"]["max"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
