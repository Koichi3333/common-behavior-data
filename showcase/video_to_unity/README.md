# Video → CBD → Unity / VRM

[← back to `showcase/`](../README.md)

The same clip, playing on a **VRM 1.0 avatar that was never measured against the
subject**. This is the cheapest test of whether the representation is really
engine-independent: the avatar is a stranger.

| | |
|---|---|
| **Source** | [`examples/human-capture/sample_output/source/source_video.mp4`](../../examples/human-capture/sample_output/source/source_video.mp4) |
| **Generator** | [`generators/video_to_cbd/`](../../generators/video_to_cbd/) → `04_behavior_dataset/` |
| **Adapter** | [`adapters/unity_vrm/`](../../adapters/unity_vrm/) |
| **Ran on** | Colab writes the files; **Unity plays them on a local machine** |
| **Output** | [`examples/human-capture/sample_output/03_unity_vrm/`](../../examples/human-capture/sample_output/03_unity_vrm/) |
| **Video** | `03_unity_vrm/unity_vrm_animation.mp4` |

## What was generated

`motion.vrma` (playable on any VRM 1.0 avatar via UniVRM SimpleVrma),
`object_trajectory_unity.json`, and `ObjectTrajectoryPlayer.cs` to drive the
object.

## What worked

- **Retargeting cost nothing.** Bone rotations are stored relative to a T-pose
  rest, so an avatar authored at zero rotation needs a coordinate transform and
  no per-avatar tuning.
- The adapter writes files and nothing else — no renderer, no engine coupling.
  Unity is used for playback and visualisation, not inference.

## What broke

- **The recording step cannot be automated in the Colab chain.** Unity runs on
  your machine, which is why the comparison videos exist as committed artifacts
  rather than as a step in a CLI pipeline.
- Proportions differ between the subject and the avatar, so a reach ends where
  *the avatar's* arm ends. On a human-shaped avatar this is barely visible —
  which is exactly why the [G1 run](../video_to_isaac_g1/) was the informative
  one.

## Known limitations

Full list: [`docs/limitations.md`](../../docs/limitations.md).

## See also

[`video_to_mujoco/`](../video_to_mujoco/) · [`cross_simulator/`](../cross_simulator/)
