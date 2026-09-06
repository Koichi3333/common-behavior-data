# One behavior, four targets, one timeline

[← back to `showcase/`](../README.md)

The whole claim of this project, in one video: a single source clip becomes a
single canonical dataset, and four independent adapters replay it side by side
on the same clock.

<div align="center">
<img src="../../docs/media/comparison.gif" width="760" alt="One behavior dataset replayed as a MediaPipe overlay, a MuJoCo humanoid, and a Unity VRM avatar, all on the same timeline">
</div>

| | |
|---|---|
| **Source** | [`examples/human-capture/sample_output/source/source_video.mp4`](../../examples/human-capture/sample_output/source/source_video.mp4) |
| **Generator** | [`generators/video_to_cbd/`](../../generators/video_to_cbd/) → `04_behavior_dataset/` |
| **Videos** | [`05_comparison/motion_comparison_4pane.mp4`](../../examples/human-capture/sample_output/05_comparison/motion_comparison_4pane.mp4) · [`motion_comparison.mp4`](../../examples/human-capture/sample_output/05_comparison/motion_comparison.mp4) (3-pane) |
| **Built by** | `05_comparison/build_comparison_4pane.py` · `build_comparison_video.py` |

## The four panes

| Pane | Adapter | Ran on |
|---|---|---|
| MediaPipe overlay | [`mediapipe_overlay/`](../../adapters/mediapipe_overlay/) | Colab |
| MuJoCo humanoid | [`mujoco/`](../../adapters/mujoco/) | Colab |
| **Isaac Sim / GR00T Unitree G1** | [`isaac_sim_groot_g1/`](../../adapters/isaac_sim_groot_g1/) | GCE, 1 × NVIDIA L4 |
| Unity / VRM avatar | [`unity_vrm/`](../../adapters/unity_vrm/) | Colab + local Unity |

## Why this is the page that matters

The four adapters **share no code**. None of them reads another's output. None
of them touches the source video except the overlay, which draws onto it. The
only thing they have in common is `04_behavior_dataset/`.

So if the four panes agree, the agreement is a property of the representation
rather than of a shared implementation. **That is the bet, and this is the
evidence for it.**

## How the alignment works

Sampling is **by timestamp, not by frame index**. The analysis runs at 12 fps
and the Unity recording at 30 — they line up because every record in CBD carries
`timestamp_ms` derived from one clock, and all five MediaPipe tasks receive the
*same* timestamp during capture. Time bases are never allowed to drift apart.

## What the comparison shows that a single pane cannot

- **Where the panes agree**, the behavior is carried by the data.
- **Where they diverge**, an embodiment ran out of room. The G1 pane is where
  that happens: a reach the human and both figures perform to the side comes out
  to the front, because `chest` and both shoulders carry no rotation and the
  robot's waist can only yaw.
- **The human-shaped targets hide this.** MuJoCo and VRM are built to human
  proportions and absorb the gap. Only the machine exposes it — which is the
  argument for adding targets that are *unlike* the ones you have.

## Adding a pane

One line in `build_comparison_4pane.py`'s `PANE_SOURCES`, not a new script.

## Reproducing it

Three of the four panes come out of the Colab CLI chain in one session. The G1
pane needs the GPU box ([why](../../docs/runtime_environments.md)), and the
Unity pane needs a local Unity recording — which is why the finished videos are
committed rather than produced by a single command.

## See also

[`video_to_mujoco/`](../video_to_mujoco/) ·
[`video_to_unity/`](../video_to_unity/) ·
[`video_to_isaac_g1/`](../video_to_isaac_g1/) ·
[findings](../../docs/compatibility_findings.md)
