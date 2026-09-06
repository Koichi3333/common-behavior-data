#!/usr/bin/env python3
"""Build the four-screen motion comparison video.

    Overlay  |  MuJoCo  |  Isaac Sim / GR00T G1  |  Unity / VRM

One Common Behavior Dataset, four consumers, one timeline. This is the
three-pane `build_comparison_video.py` extended with the GR00T / Unitree G1
pane, and rewritten to auto-discover its inputs so it can be run without
hand-writing a config:

    python build_comparison_4pane.py --sample-output ..     # the dir holding 01_../06_..
    python build_comparison_4pane.py --config comparison_config.json

`--panes` takes a preset name or a comma-separated list of pane keys
(`overlay`, `mujoco`, `groot_g1`, `unity`), so a new adapter needs one line in
`PANE_SOURCES` rather than a new script.

Every pane is sampled by **timestamp**, never by frame index, so a 12 fps
analysis and a 30 fps Unity recording stay aligned on the common timeline. A
pane whose video is missing renders as "Pending" rather than shifting the
others -- which is what the Unity pane looks like until someone records it
locally.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

TITLE_BAND = 56
CAPTION_BAND = 96

# The sources have different aspect ratios (640x1136, 960x720, 720x1280,
# 1080x1350). A fixed portrait cell plus a centred "cover" crop is the only
# arrangement that gives every pane equal visual weight; "contain" is available
# for anyone who would rather see letterboxing than lose edges.
PANE_SOURCES = {
    "overlay": ("MediaPipe Overlay", "01_mediapipe_overlay/mediapipe_overlay.mp4"),
    "mujoco": ("MuJoCo", "02_mujoco/mujoco_simulation.mp4"),
    "groot_g1": ("Isaac Sim / GR00T G1", "06_groot_g1/groot_g1_simulation.mp4"),
    "unity": ("Unity / VRM", "03_unity_vrm/unity_vrm_animation.mp4"),
}
# The Unity pane goes last: it is the one recorded by hand, so it is the one
# most often "Pending", and a gap reads better at the edge.
PRESETS = {"default": ["overlay", "mujoco", "groot_g1", "unity"]}
PRESET_OUTPUT = {"default": "motion_comparison_4pane.mp4"}


def resolve_panes(spec):
    """A preset name, or a comma-separated list of PANE_SOURCES keys."""
    if spec in PRESETS:
        return PRESETS[spec], PRESET_OUTPUT[spec]
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    unknown = [k for k in keys if k not in PANE_SOURCES]
    if not keys or unknown:
        sys.exit(f"unknown pane(s): {', '.join(unknown) or spec}. "
                 f"Known: {', '.join(PANE_SOURCES)}; presets: {', '.join(PRESETS)}")
    return keys, "motion_comparison_" + "_".join(keys) + ".mp4"


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


def open_pane(label, path):
    if path and Path(path).exists():
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            return {"cap": cap, "label": label,
                    "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
                    "last": None, "last_index": -1}
    return {"cap": None, "label": label, "fps": 30.0, "last": None,
            "last_index": -1}


def fit(image, cell_w, cell_h, mode):
    """Scale `image` into a cell, either covering it or fitting inside it."""
    h, w = image.shape[:2]
    scale = (max if mode == "cover" else min)(cell_w / w, cell_h / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((cell_h, cell_w, 3), 22, np.uint8)
    if mode == "cover":
        x0 = max(0, (new_w - cell_w) // 2)
        y0 = max(0, (new_h - cell_h) // 2)
        crop = resized[y0:y0 + cell_h, x0:x0 + cell_w]
        canvas[:crop.shape[0], :crop.shape[1]] = crop
    else:
        x0 = (cell_w - new_w) // 2
        y0 = (cell_h - new_h) // 2
        canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas


def pane_frame(pane, timestamp, cell_w, cell_h, mode):
    if pane["cap"] is None:
        image = np.full((cell_h, cell_w, 3), 42, np.uint8)
        put(image, "Pending", 18, cell_h // 2 - 8, 0.7, (160, 160, 160))
        put(image, "(record locally)", 18, cell_h // 2 + 20, 0.45, (150, 150, 150))
        return image
    # Sampling is by timestamp, not frame index: that is what keeps a 12 fps
    # pane and a 30 fps pane on the same clock.
    target = int(round(timestamp * pane["fps"]))
    while pane["last_index"] < target:
        ok, frame = pane["cap"].read()
        if not ok:
            break
        pane["last"] = frame
        pane["last_index"] += 1
    if pane["last"] is None:
        return np.zeros((cell_h, cell_w, 3), np.uint8)
    return fit(pane["last"], cell_w, cell_h, mode)


def wrap(text, max_px, scale):
    """Trim to what fits on one line, with an ellipsis rather than a hard cut."""
    if cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] <= max_px:
        return text
    while text and cv2.getTextSize(text + " ...", cv2.FONT_HERSHEY_SIMPLEX,
                                   scale, 1)[0][0] > max_px:
        text = text[:-1]
    return text.rstrip() + " ..."


def load_captions(dataset: Path, frame_count, fps):
    rows = [json.loads(l) for l
            in (dataset / "timeline/frames.jsonl").read_text("utf-8").splitlines()
            if l.strip()]
    out = []
    for i in range(frame_count):
        row = rows[min(i, len(rows) - 1)]
        phase = row.get("phase") or {}
        caption = row.get("caption") or {}
        out.append({"frame": i, "time": f"{i / fps:05.2f}",
                    "action": phase.get("action", "-"),
                    "phase": phase.get("phase", "-"),
                    "hand": phase.get("hand", "-"),
                    "caption": caption.get("en", "")})
    return out


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample-output", default=None,
                    help="directory holding 01_.. .. 06_.. and 04_behavior_dataset")
    ap.add_argument("--panes", default="default",
                    help="preset (%s) or a comma-separated list of %s"
                         % (", ".join(PRESETS), ", ".join(PANE_SOURCES)))
    ap.add_argument("--config", default=None,
                    help="explicit config JSON, in the shape build_comparison_video.py takes")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cell-width", type=int, default=330)
    ap.add_argument("--cell-height", type=int, default=586)
    ap.add_argument("--fit", choices=["cover", "contain"], default="cover")
    ap.add_argument("--title", default=None,
                    help="default: \"Motion Comparison -- one dataset, N consumers\"")
    args = ap.parse_args()

    if args.config:
        config = json.loads(Path(args.config).read_text("utf-8"))
        root = Path(args.config).parent
        entries = [(v["label"], v.get("path")) for v in config["videos"]]
        fps = config["fps"]
        frame_count = config["frame_count"]
        captions = config["captions"]
        out_path = Path(args.out or config["out_path"])
    else:
        root = Path(args.sample_output or Path(__file__).resolve().parent.parent)
        dataset = root / "04_behavior_dataset"
        if not dataset.exists():
            sys.exit(f"no 04_behavior_dataset/ under {root}")
        manifest = json.loads((dataset / "manifest.json").read_text("utf-8"))
        fps = float(manifest["fps"])
        frame_count = int(manifest["frame_count"])
        keys, filename = resolve_panes(args.panes)
        entries = [(PANE_SOURCES[k][0], root / PANE_SOURCES[k][1]) for k in keys]
        captions = load_captions(dataset, frame_count, fps)
        out_path = Path(args.out or (root / "05_comparison" / filename))

    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    title = args.title or ("Motion Comparison -- one dataset, "
                           f"{words.get(len(entries), len(entries))} consumers")
    panes = [open_pane(label, path) for label, path in entries]
    have = [p["label"] for p in panes if p["cap"] is not None]
    print(f"panes present: {', '.join(have) or 'none'}")
    missing = [p["label"] for p in panes if p["cap"] is None]
    if missing:
        print(f"panes pending:  {', '.join(missing)}")

    cw, ch = args.cell_width, args.cell_height
    total_w = cw * len(panes)
    total_w -= total_w % 2
    total_h = TITLE_BAND + ch + CAPTION_BAND
    total_h -= total_h % 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = FrameWriter(out_path, fps, (total_w, total_h))
    for i in range(frame_count):
        timestamp = i / fps
        canvas = np.full((total_h, total_w, 3), 22, np.uint8)
        put(canvas, title, 16, 37, 0.78, (250, 250, 250), 2)
        x = 0
        for pane in panes:
            image = pane_frame(pane, timestamp, cw, ch, args.fit)
            canvas[TITLE_BAND:TITLE_BAND + ch, x:x + cw] = image
            cv2.rectangle(canvas, (x, TITLE_BAND), (x + cw - 1, TITLE_BAND + ch - 1),
                          (60, 60, 60), 1)
            # Three of the four sources burn their own header into the frame,
            # so the pane label needs an opaque chip or the two overlap into
            # unreadable mush.
            (tw, th), _ = cv2.getTextSize(pane["label"], cv2.FONT_HERSHEY_SIMPLEX,
                                          0.58, 1)
            cv2.rectangle(canvas, (x + 6, TITLE_BAND + 6),
                          (x + 18 + tw, TITLE_BAND + 18 + th), (28, 28, 32), -1)
            put(canvas, pane["label"], x + 12, TITLE_BAND + 12 + th, 0.58)
            x += cw
        meta = captions[min(i, len(captions) - 1)]
        y0 = TITLE_BAND + ch
        put(canvas, "Action: %s   Phase: %s   Hand: %s   Time: %s s   Frame: %d"
            % (meta["action"], meta["phase"], meta["hand"], meta["time"],
               meta["frame"]), 16, y0 + 30, 0.58)
        text = meta.get("caption") or ""
        if text:
            put(canvas, wrap(text, total_w - 32, 0.5), 16, y0 + 60, 0.5,
                (185, 200, 215))
        put(canvas, "All panes sampled by timestamp on the Common Timeline",
            16, y0 + 84, 0.44, (140, 145, 155))
        writer.write(canvas)
    writer.close()
    for pane in panes:
        if pane["cap"] is not None:
            pane["cap"].release()
    print(f"done: {out_path}  ({total_w}x{total_h}, {frame_count} frames @ {fps} fps)")


if __name__ == "__main__":
    main()
