"""Build the three-screen motion comparison video.

Usage:
    python build_comparison_video.py comparison_config.json

The config lists the source videos, the common timeline (fps / duration),
and per-frame behavior captions taken from the Common Behavior Dataset.
All panes are sampled by *timestamp*, so videos with different fps are
still aligned to the same Common Timeline (Section 31.3).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PANE_HEIGHT = 420
TITLE_BAND = 52
CAPTION_BAND = 78


def put(image, text, x, y, scale=0.55, color=(235, 235, 235), thick=1):
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
                (15, 15, 15), thick + 2, cv2.LINE_AA)
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
                color, thick, cv2.LINE_AA)


def open_pane(entry):
    path = entry.get("path")
    if path and Path(path).exists():
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            pane_width = max(2, int(round(width * PANE_HEIGHT / height)))
            pane_width -= pane_width % 2
            return {"cap": cap, "fps": fps, "width": pane_width,
                    "label": entry["label"], "last": None, "last_index": -1}
    pane_width = int(PANE_HEIGHT * 9 / 16)
    return {"cap": None, "fps": 30.0, "width": pane_width - pane_width % 2,
            "label": entry["label"], "last": None, "last_index": -1}


def pane_frame(pane, timestamp):
    if pane["cap"] is None:
        image = np.full((PANE_HEIGHT, pane["width"], 3), 45, np.uint8)
        put(image, "Pending", 20, PANE_HEIGHT // 2 - 10, 0.7, (160, 160, 160))
        put(image, "(capture in local Unity)", 20, PANE_HEIGHT // 2 + 18,
            0.45, (160, 160, 160))
        return image
    target = int(round(timestamp * pane["fps"]))
    while pane["last_index"] < target:
        success, frame = pane["cap"].read()
        if not success:
            break
        pane["last"] = frame
        pane["last_index"] += 1
    frame = pane["last"]
    if frame is None:
        return np.zeros((PANE_HEIGHT, pane["width"], 3), np.uint8)
    return cv2.resize(frame, (pane["width"], PANE_HEIGHT))


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    panes = [open_pane(entry) for entry in config["videos"]]
    fps = config["fps"]
    frame_count = config["frame_count"]
    captions = config["captions"]

    total_width = sum(p["width"] for p in panes)
    total_width -= total_width % 2
    total_height = TITLE_BAND + PANE_HEIGHT + CAPTION_BAND

    writer = cv2.VideoWriter(config["out_path"],
                             cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (total_width, total_height))
    for fi in range(frame_count):
        timestamp = fi / fps
        canvas = np.full((total_height, total_width, 3), 22, np.uint8)
        put(canvas, "Motion Comparison", 16, 34, 0.85, (250, 250, 250), 2)
        x = 0
        for pane in panes:
            image = pane_frame(pane, timestamp)
            height, width = image.shape[:2]
            canvas[TITLE_BAND:TITLE_BAND + height, x:x + width] = \
                image[:, :total_width - x] if x + width > total_width else image
            put(canvas, pane["label"], x + 10, TITLE_BAND + 24, 0.55)
            x += width
        meta = captions[min(fi, len(captions) - 1)]
        y0 = TITLE_BAND + PANE_HEIGHT
        put(canvas, "Action: %s   Phase: %s   Hand: %s" %
            (meta["action"], meta["phase"], meta["hand"]), 16, y0 + 30, 0.6)
        put(canvas, "Time: %s s   Frame: %d" % (meta["time"], meta["frame"]),
            16, y0 + 58, 0.6)
        writer.write(canvas)
    writer.release()
    for pane in panes:
        if pane["cap"] is not None:
            pane["cap"].release()
    print("done:", config["out_path"])


if __name__ == "__main__":
    main()
