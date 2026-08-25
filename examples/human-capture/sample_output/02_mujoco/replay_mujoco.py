'''Replay Common Behavior motion in the local MuJoCo viewer.

Usage:
    python replay_mujoco.py          # loop playback
    python replay_mujoco.py --once   # play once and hold the last frame

Keys (press inside the viewer window):
    SPACE : pause / resume
    R     : restart from frame 0
    , / . : step one frame backward / forward (while paused)
'''
import sys
import time
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

HERE = Path(__file__).parent
# XMLは文字列として読み込む（Windowsで日本語を含むパスでも開けるようにするため。
# MjModel.from_xml_path はC++層でファイルを開くため非ASCIIパスで失敗する）
model = mujoco.MjModel.from_xml_string(
    (HERE / "humanoid.xml").read_text(encoding="utf-8"))
data = mujoco.MjData(model)

archive = np.load(HERE / "motion.npz")
qpos = archive["qpos"]
fps = float(archive["fps"][0])
object_pos = archive["object_pos"] if "object_pos" in archive else None
total = len(qpos)
loop = "--once" not in sys.argv

print(f"frames={total}  fps={fps:.2f}  duration={total / fps:.2f}s  "
      f"loop={loop}")
print("keys: SPACE=pause/resume  R=restart  ,/.=step  (progress printed below)")

paused = False
frame = 0


def key_callback(keycode):
    '''ビューアのキー入力（SPACE/R/,/.）で再生を制御する'''
    global paused, frame
    key = chr(keycode) if 32 <= keycode < 127 else ""
    if keycode == 32:                     # SPACE
        paused = not paused
    elif key in ("r", "R"):
        frame = 0
    elif key == "." and paused:
        frame = min(frame + 1, total - 1)
    elif key == "," and paused:
        frame = max(frame - 1, 0)


with mujoco.viewer.launch_passive(model, data,
                                  key_callback=key_callback) as viewer:
    while viewer.is_running():
        step_start = time.time()
        index = min(frame, total - 1)
        data.qpos[:] = qpos[index]
        if object_pos is not None and model.nmocap > 0:
            data.mocap_pos[0] = object_pos[index]
        mujoco.mj_forward(model, data)
        viewer.sync()

        # 進捗を1行で上書き表示（最初=0 / 最後=total-1 が目で追える）
        marker = " <<< FIRST" if index == 0 else (
            " >>> LAST" if index == total - 1 else "")
        print(f"\rframe {index + 1:4d}/{total}  "
              f"t={index / fps:6.2f}s{'  [PAUSED]' if paused else ''}"
              f"{marker}          ", end="", flush=True)

        if not paused:
            if frame >= total - 1:
                if loop:
                    print("\n--- loop ---")
                    frame = 0
                else:
                    paused = True         # --once は最終フレームで停止
            else:
                frame += 1
        wait = 1.0 / fps - (time.time() - step_start)
        if wait > 0:
            time.sleep(wait)
print()
