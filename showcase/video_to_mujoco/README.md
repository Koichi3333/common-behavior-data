# Video → CBD → MuJoCo

[← back to `showcase/`](../README.md)

One clip of a person reaching for a glass, replayed as a MuJoCo humanoid built
to that person's own measured bone lengths.

| | |
|---|---|
| **Source** | [`examples/human-capture/sample_output/source/source_video.mp4`](../../examples/human-capture/sample_output/source/source_video.mp4) |
| **Generator** | [`generators/video_to_cbd/`](../../generators/video_to_cbd/) → `04_behavior_dataset/` |
| **Adapter** | [`adapters/mujoco/`](../../adapters/mujoco/) |
| **Ran on** | Google Colab (T4; CPU also completes) |
| **Output** | [`examples/human-capture/sample_output/02_mujoco/`](../../examples/human-capture/sample_output/02_mujoco/) |
| **Video** | `02_mujoco/mujoco_simulation.mp4` |

## What was generated

`humanoid.xml` (the model) and `motion.npz` (the motion), kept as two files, plus
`object_trajectory.csv`, a standalone `replay_mujoco.py`, and the rendered mp4.

## What worked

- Canonical CBD alone was enough — the adapter never touches the video, never
  runs MediaPipe, and never reads another adapter's output.
- **Model and motion stayed separate.** The skeleton is built from the subject's
  measured segment lengths; the trajectory does not know about it.
- Bone rotations stored relative to a T-pose rest transferred without special
  cases.

## What broke

- **This is kinematic replay, not physics.** `qpos` + `mj_forward`. Contact is
  not resolved, and nothing here claims the pose is dynamically feasible. That
  question was only actually asked later, in
  [`video_to_isaac_g1/`](../video_to_isaac_g1/), with PhysX.
- Depth is monocular estimation, so absolute scale is plausible rather than
  measured.
- In this clip the glass was detected in a single frame of 96, so no interaction
  candidate fired — the object trajectory is thin, and the adapter says so
  rather than inventing one.

## Known limitations

Nothing about grasp correctness, contact force, or sim-to-real is claimed. Full
list: [`docs/limitations.md`](../../docs/limitations.md).

## See also

[`video_to_unity/`](../video_to_unity/) — the same data on an avatar nobody
measured · [`cross_simulator/`](../cross_simulator/) — side by side
