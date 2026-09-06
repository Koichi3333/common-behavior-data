# `unity_vrm/` — CBD to Unity / VRM 1.0

[← back to `adapters/`](../README.md) ·
[Specification](../../specification/README.md)

**What is this?** Canonical CBD becomes a `motion.vrma` animation that plays on
**any** VRM 1.0 avatar, plus the object trajectory and a small C# player for it.
Nothing here renders — it writes files and Unity plays them.

| | |
|---|---|
| **Input** | canonical CBD — `cbd_dataset.zip` or an unpacked `04_behavior_dataset/` |
| **Output** | `output/03_unity_vrm/motion.vrma`, `object_trajectory_unity.json`, `ObjectTrajectoryPlayer.cs`, `README_UNITY.md`, `adapter_report.json` — packaged as `vrm_adapter_output.zip` |
| **Runs in** | Google Colab writes the files; **Unity plays them on your own machine** |
| **GPU** | no |

Notebook: [`cbd_adapter_unity_vrm.ipynb`](cbd_adapter_unity_vrm.ipynb)

Because bone rotations in canonical CBD are stored relative to a T-pose rest, an
avatar authored at zero rotation needs a coordinate transform and nothing else —
which is why the same file drives an avatar nobody measured.

Unity is used here for **playback and visualisation**, not as an inference
engine.

## Minimal example

```bash
# same Colab session the generator ran in — nothing to upload
colab exec -s cbd -f cbd_adapter_unity_vrm.ipynb --timeout 900
colab download -s cbd \
  /content/human_behavior_demo_2_0/vrm_adapter_output.zip ./vrm_adapter_output.zip
```

Then, locally: open the project in Unity with UniVRM, load any VRM 1.0 avatar,
play `motion.vrma` with SimpleVrma, and add `ObjectTrajectoryPlayer.cs` for the
tracked object. Step-by-step instructions ship in the generated
`README_UNITY.md`.

## Why the comparison video is not produced here

The multi-pane comparison needs a Unity recording made on your own machine, so
it cannot run in the Colab CLI chain. The finished comparisons are committed:
[`showcase/cross_simulator/`](../../showcase/cross_simulator/).

## Sample output

[`examples/human-capture/sample_output/03_unity_vrm/`](../../examples/human-capture/sample_output/03_unity_vrm/)
· video in [`showcase/video_to_unity/`](../../showcase/video_to_unity/)

## Related

[`mediapipe_overlay/`](../mediapipe_overlay/) · [`mujoco/`](../mujoco/) ·
[`isaac_sim_groot_g1/`](../isaac_sim_groot_g1/) ·
[adapter rules](../README.md#rules-for-an-adapter)
