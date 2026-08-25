# Demo A — Human Capture: Video → Common Behavior Data

[← back to README](../../README.md) · [Demo B →](../language-to-motion/README.md)

**One source video becomes reusable behavior data for multiple representations.**

<img src="../../docs/media/comparison.gif" width="760" alt="MediaPipe overlay, MuJoCo humanoid and Unity VRM avatar driven by the same behavior data">

The three panes above are **not three pipelines**. They are three adapters
reading the same `04_behavior_dataset/`, aligned on the same timeline.

```text
Video ──▶ MediaPipe ──▶ Common Behavior Data ──┬──▶ MediaPipe overlay
                        (the master data)      ├──▶ MuJoCo   (humanoid.xml + motion.npz)
                                               ├──▶ Unity/VRM (motion.vrma)
                                               └──▶ Behavior dataset (frames.jsonl, CSVs)
```

MediaPipe is never wired directly to MuJoCo or to Unity. Adding a fourth
consumer means writing one adapter, not one more pipeline.

## Outputs

| # | Output | Path |
|---|---|---|
| 1 | MediaPipe overlay video | `output/01_mediapipe_overlay/mediapipe_overlay.mp4` |
| 2 | MuJoCo | `output/02_mujoco/` — `humanoid.xml` + `motion.npz` + `replay_mujoco.py` + mp4 |
| 3 | Unity / VRM | `output/03_unity_vrm/motion.vrma` (record the video locally in Unity) |
| 4 | **Behavior dataset** | `output/04_behavior_dataset/` — the master data |
| + | Temporal captions | `04_behavior_dataset/captions/` (optional, Gemini API) |
| + | Motion comparison | `output/05_comparison/motion_comparison.mp4` |
| + | Bundle | `demo2_output_bundle.zip` — one episode, ready for Demo B |

## Run it

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Koichi3333/common-behavior-data/blob/main/examples/human-capture/human_behavior_demo_2_0.ipynb)

[`human_behavior_demo_2_0.ipynb`](human_behavior_demo_2_0.ipynb) — open in Colab.

1. `Runtime → Change runtime type → T4 GPU`
   (CPU completes too, just slower — nothing here requires a GPU)
2. *(optional)* Add a Colab secret named `GEMINI_API_KEY` for temporal captions
   in `[5.5]`. Without it that cell skips and everything else still runs.
3. Run `[1]` → `[10]` in order. Cell `[2]` asks for your video.
4. *(optional)* Play `motion.vrma` in Unity, record it, drop
   `unity_vrm_animation.mp4` back in, re-run `[9]` for the full three-pane video.

### Cells

| Cell | What it does | ~time (20 s clip, T4) |
|---|---|---|
| `[0]` | Optional Google Drive mount | — |
| `[1]` | Install packages, pick a GL backend, download 5 MediaPipe models | 2–3 min |
| `[2]` | **CONFIG** + video input + shared utilities | 1 min |
| `[3]` | Unified MediaPipe capture — pose, hands, face, gesture, objects, one shared clock | 3–8 min |
| `[3.5]` | *(optional)* AI-assisted object class re-mapping, human-confirmed | ~1 min + input |
| `[4]` | **Build the behavior data** — tracking, bone rotations, interaction candidates, metrics | seconds |
| `[5]` | Write the behavior dataset | seconds |
| `[5.5]` | *(optional)* Temporal captions via Gemini | seconds |
| `[6]` | Adapter: overlay video | 1–2 min |
| `[7]` | Adapter: MuJoCo export + offscreen render | 2–4 min |
| `[8]` | Adapter: `motion.vrma` | seconds |
| `[8.5]` | *(markdown)* Unity playback instructions | — |
| `[9]` | Three-pane comparison video | 1–2 min |
| `[10]` | Acceptance checks + bundle ZIP | 1 min |

### A good source video

One person, full body in frame, hands visible, picking up and putting down a
bottle / cup / box, 10–30 seconds, ~30 fps, fixed camera, front or three-quarter
view.

If any of that is missing the run does not stop. The affected modality is
omitted and the reason is recorded in `quality/quality.json` and
`runtime_info.json`.

### Playing it on a VRM avatar (optional, outside Colab)

Unity here is **playback only** — no inference, no motion computation. With
UniVRM's SimpleVrma sample scene it needs no code:

1. Unity 2022.3 LTS (or Unity 6), 3D project
2. From [UniVRM Releases](https://github.com/vrm-c/UniVRM/releases) import
   **both** `UniVRM-*.unitypackage` and `VRM_Samples-*.unitypackage`
3. Open `Assets/VRM10_Samples/SimpleVrma/SimpleVrma`, press Play
4. Load a VRM 1.0 avatar and this notebook's `motion.vrma`; turn off **BoxMan**
5. Record the Game view with Unity Recorder — **30/60 fps is fine**, cell `[9]`
   aligns by timestamp, not frame index
6. Save as `unity_vrm_animation.mp4` into `output/03_unity_vrm/` and re-run `[9]`

Cell `[8]` writes full instructions to `output/03_unity_vrm/README_UNITY.md`,
along with an optional `ObjectTrajectoryPlayer.cs` for replaying the tracked
object alongside the avatar.

## Sample output

[`sample_output/`](sample_output/) is a real, unedited run of this notebook —
the same data the GIF above was rendered from.

```text
sample_output/
├── source/source_video.mp4               8 s, one person, seated, drinking
├── 01_mediapipe_overlay/                 overlay video
├── 02_mujoco/                            humanoid.xml, motion.npz, replay script, mp4
├── 03_unity_vrm/                         motion.vrma, Unity recording, C# object player
├── 04_behavior_dataset/                  ← the master data
└── 05_comparison/                        three-pane video + build script
```

Replay the MuJoCo output locally:

```bash
pip install mujoco
cd sample_output/02_mujoco
python replay_mujoco.py          # loop
python replay_mujoco.py --once   # play once, hold the final pose
```

`SPACE` pauses, `R` restarts, `,` / `.` step frame by frame.

### What this sample gets wrong, and why we shipped it anyway

In this particular clip the cup is detected in **one frame out of 96**. So:

- `interactions/interaction_events.csv` is **empty**
- every frame's phase is `Idle`
- `behavior_summary.json` lists **no events**

The person is visibly picking up and drinking from a glass.

We kept this sample rather than swapping in a flattering one, because it shows
the properties that matter more than a clean result:

- interaction detection is **heuristic candidates**, and a single missed
  detection changes the behavioral reading of a clip
- `quality/quality.json` reports what was actually achieved
  (`object_coverage: 1.0`, `face_coverage: 0.0`) rather than hiding gaps
- the captions are still correct, because they come from the frames rather than
  from the interaction state machine

The tuning table below is what you would reach for to fix it — raising
`object.min_confidence` sensitivity and `behavior.contact_distance` are the
first two levers.

> Note: this sample was produced by an earlier run. Its
> `captions/temporal_captions.json` uses fixed-width caption windows
> (`window_seconds: 5`); the current notebook segments captions at behavior-phase
> boundaries. Everything else is in the current format.

## Tuning

Edit `CONFIG` in `[2]`, re-run from the listed cell.

| Symptom | Fix | Re-run from |
|---|---|---|
| Left/right hands swapped | `mediapipe.mirror_handedness = True` | `[3]` |
| Slow / out of memory | lower `video.analysis_fps`, shorten `max_analysis_seconds` | `[3]` |
| Object never picked up (label) | add it to `object.target_labels` — see the "Detected objects" line at the end of `[3]` | `[4]` |
| Object never picked up (score) | lower `object.min_confidence` | `[3]` |
| One object splits into several tracks | normalise with `object.label_aliases`, or use `[3.5]` | `[4]` |
| No contact / grasp candidates | raise `behavior.contact_distance` (e.g. `0.45`) | `[4]` |
| Too many candidates | lower `behavior.contact_distance`, raise `behavior.reach_window` | `[4]` |
| Motion jittery | lower `cleaning.smoothing_alpha` (e.g. `0.35`) | `[4]` |
| Motion laggy | raise `cleaning.smoothing_alpha` (e.g. `0.7`) | `[4]` |
| Figure leaves the MuJoCo frame | lower `mujoco.frame_world_width`, or `use_image_translation = False` | `[4]` |
| MuJoCo render fails | `mujoco.render_width = 640`; if it persists, restart the runtime | `[7]` |
| Object stays stuck to the hand after release | release also triggers on an open hand (Open_Palm / finger curl) — film so the hand gesture is visible | `[4]` |
| `ParseXML: Error opening file` locally | MuJoCo cannot open non-ASCII paths; move to an ASCII-only path | — |
| No captions | check the secret is named `GEMINI_API_KEY` and notebook access is on | `[5.5]` |

## What this demo does not claim

- Interaction events are **candidates**, not ground truth
- MuJoCo playback is **kinematic replay** (`qpos` + `mj_forward`) — not physically
  correct contact or forces
- Object 3D positions are monocular estimates and always carry `position_source`
- Captions are **AI-generated descriptions**, not verified annotations
- Finger angles are curl approximations, not per-joint measurements

Full list: [`docs/limitations.md`](../../docs/limitations.md).

## Next

`demo2_output_bundle.zip` from `[10]` is one complete behavior episode. Feed a
few of them into **[Demo B — Language to Motion](../language-to-motion/README.md)**
and the same representation becomes training data.
