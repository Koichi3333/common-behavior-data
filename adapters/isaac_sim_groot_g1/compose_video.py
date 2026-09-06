#!/usr/bin/env python3
"""Turn the G1 PNG sequences into the two videos this adapter owes.

    06_groot_g1/groot_g1_simulation.mp4
        the film camera, with the behavior caption burned in -- the pane the
        comparison video shows

    06_groot_g1/groot_lerobot/videos/chunk-000/observation.images.ego_view/
    episode_000000.mp4
        the robot's own head camera, clean: it is the dataset's
        `observation.images.ego_view`, so nothing is drawn on top of it

Kept out of `groot_g1_render.py` on purpose: the render step needs the Isaac
Sim runtime, this one needs OpenCV, and neither should drag in the other.

    python compose_video.py --frames <render dir> \\
        --dataset <...>/04_behavior_dataset --out-dir <...>/06_groot_g1
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def put(image, text, x, y, scale=0.55, color=(235, 235, 235), thick=1):
    """Text with a dark halo, drawn so the halo does not drift.

    The obvious way to halo text -- one pass at `thick + 2`, one at `thick` --
    is wrong: cv2.putText advances each glyph by a thickness-dependent amount,
    so the thicker pass ends up measurably wider and its tail sticks out past
    the thin pass as a ghost of the last few characters. Offsetting a
    same-thickness pass in eight directions keeps every glyph in register.
    """
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1),
                   (0, -2), (0, 2), (-2, 0), (2, 0)):
        cv2.putText(image, text, (x + dx, y + dy), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (15, 15, 15), thick, cv2.LINE_AA)
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
                color, thick, cv2.LINE_AA)


class FrameWriter:
    """Write frames straight into ffmpeg, with no lossy intermediate.

    cv2.VideoWriter's mp4v encoder re-compresses at a fixed default quality,
    and re-encoding that to H.264 leaves visible ghosting around small text --
    which is most of what these videos carry. Piping raw BGR into ffmpeg keeps
    the only lossy step the final H.264 encode. cv2.VideoWriter stays as the
    fallback for environments with no ffmpeg on PATH.
    """

    def __init__(self, path, fps, size, crf=18):
        self.path = Path(path)
        self.size = size
        self.proc = None
        self.fallback = None
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow",
               "-crf", str(crf), "-movflags", "+faststart", str(self.path)]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE)
        except FileNotFoundError:
            self.fallback = cv2.VideoWriter(
                str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
            print("ffmpeg not on PATH; falling back to the mp4v encoder")

    def write(self, frame):
        if frame.shape[1] != self.size[0] or frame.shape[0] != self.size[1]:
            frame = cv2.resize(frame, self.size)
        if self.proc is not None:
            self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        else:
            self.fallback.write(frame)

    def close(self):
        if self.proc is not None:
            self.proc.stdin.close()
            if self.proc.wait() != 0:
                raise RuntimeError(self.proc.stderr.read().decode()[-2000:])
        else:
            self.fallback.release()


def encode(images, out, fps, rows=None, label=None, limits=None):
    first = cv2.imread(str(images[0]))
    if first is None:
        sys.exit(f"could not read {images[0]}")
    height, width = first.shape[:2]
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = FrameWriter(out, fps, (width, height))
    band = 96 if width >= 480 else 64
    for i, path in enumerate(images):
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        if frame.shape[:2] != (height, width):
            frame = cv2.resize(frame, (width, height))
        if rows is not None:
            meta = rows[min(i, len(rows) - 1)]
            phase = meta.get("phase") or {}
            frame[:band] = (frame[:band].astype(np.float32) * 0.35).astype(np.uint8)
            put(frame, label, 12, 30, 0.68)
            put(frame, "Source: Common Behavior Data   Mode: Retarget (43-DoF joint space)",
                12, 54, 0.42)
            line = (f"Action: {phase.get('action', '-')}   "
                    f"Phase: {phase.get('phase', '-')}")
            if limits:
                line += f"   Joints on a limit: {limits[min(i, len(limits) - 1)]}"
            put(frame, line, 12, 76, 0.42)
            put(frame, f"Frame: {i}   Time: {i / fps:05.2f} s", 12, height - 16, 0.45)
        writer.write(frame)
    writer.close()
    print(f"Wrote: {out}  ({len(images)} frames @ {fps} fps)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", required=True,
                    help="the render directory holding film/ and ego/")
    ap.add_argument("--dataset", required=True, help="04_behavior_dataset directory")
    ap.add_argument("--out-dir", required=True, help="the 06_groot_g1 directory")
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--no-overlay", action="store_true",
                    help="write the bare film render, with no caption band")
    ap.add_argument("--name", default="groot_g1_simulation.mp4",
                    help="file name for the film video inside --out-dir")
    args = ap.parse_args()

    frame_root = Path(args.frames)
    film = sorted((frame_root / "film").glob("rgb_*.png")) \
        or sorted(frame_root.glob("rgb_*.png"))
    if not film:
        sys.exit(f"no film frames under {frame_root}")
    ego = sorted((frame_root / "ego").glob("rgb_*.png"))

    dataset = Path(args.dataset)
    manifest = json.loads((dataset / "manifest.json").read_text("utf-8"))
    fps = args.fps or float(manifest["fps"])
    rows = [json.loads(l) for l
            in (dataset / "timeline/frames.jsonl").read_text("utf-8").splitlines()
            if l.strip()]

    out_dir = Path(args.out_dir)
    # the caption band reports how many joints are pinned to a limit -- the
    # number the adapter report gives per joint, per frame, on the pixels
    limits = None
    trajectory = out_dir / "adapter_report.json"
    angles = out_dir / "g1_joint_trajectory.csv"
    if trajectory.exists() and angles.exists():
        import csv
        report = json.loads(trajectory.read_text("utf-8"))
        # v1 reports the at-limit joints under `retarget`; the v2 report is a
        # different document and simply does not carry them. An absent band is
        # the right answer there, not a traceback.
        bounds = {name: info["limit_rad"] for name, info
                  in (report.get("retarget", {})
                      .get("joints_resting_on_a_limit", {})).items()}
        if bounds:
            limits = []
            with angles.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    limits.append(sum(1 for name, (lo, hi) in bounds.items()
                                      if float(row[name]) <= lo + 1e-6
                                      or float(row[name]) >= hi - 1e-6))

    encode(film, out_dir / args.name, fps,
           None if args.no_overlay else rows, "Isaac Sim - GR00T / Unitree G1", limits)
    if ego:
        # no overlay: this one is the GR00T dataset's observation, not a figure
        encode(ego, out_dir / "groot_lerobot/videos/chunk-000"
               / "observation.images.ego_view/episode_000000.mp4", fps)
    else:
        print("no ego/ frames found -- the GR00T dataset's ego_view video is "
              "still missing; re-run the render without --no-ego")


if __name__ == "__main__":
    main()
