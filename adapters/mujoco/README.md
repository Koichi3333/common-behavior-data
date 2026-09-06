# `mujoco/` — CBD to a MuJoCo humanoid

[← back to `adapters/`](../README.md) ·
[Specification](../../specification/README.md)

**What is this?** Canonical CBD becomes a MuJoCo model and a motion track,
deliberately as two separate files, plus a rendered replay.

| | |
|---|---|
| **Input** | canonical CBD — `cbd_dataset.zip` or an unpacked `04_behavior_dataset/` |
| **Output** | `output/02_mujoco/humanoid.xml` (model), `motion.npz` (motion), `object_trajectory.csv`, `replay_mujoco.py`, `mujoco_simulation.mp4`, `adapter_report.json` — packaged as `mujoco_adapter_output.zip` |
| **Runs in** | Google Colab — **CLI recommended**, UI supported |
| **GPU** | optional — T4 renders with EGL, CPU falls back to OSMesa |

Notebook: [`cbd_adapter_mujoco.ipynb`](cbd_adapter_mujoco.ipynb)

## Two things worth knowing before you read the output

- **Model and motion are separate** (adapter rule 3). `humanoid.xml` is built to
  the subject's measured bone lengths; `motion.npz` is the trajectory. Swap
  either without touching the other.
- **This is kinematic replay, not physics.** `qpos` + `mj_forward`. Contact is
  not resolved and no claim about physical correctness is made — that is what
  [`isaac_sim_groot_g1/`](../isaac_sim_groot_g1/) went and tested with PhysX.
  See [limitations](../../docs/limitations.md).

## Minimal example

```bash
# same Colab session the generator ran in — nothing to upload
colab exec -s cbd -f cbd_adapter_mujoco.ipynb --timeout 1800
colab download -s cbd \
  /content/human_behavior_demo_2_0/mujoco_adapter_output.zip ./mujoco_adapter_output.zip
```

Fresh session:

```bash
colab upload -s cbd2 ./cbd_dataset.zip /content/cbd_dataset.zip
colab exec   -s cbd2 -f cbd_adapter_mujoco.ipynb --timeout 1800
```

In a headless run it never opens an upload widget and never embeds a video
player — it prints the output path, so `colab exec` always terminates.

## Sample output

[`examples/human-capture/sample_output/02_mujoco/`](../../examples/human-capture/sample_output/02_mujoco/)
· video in [`showcase/video_to_mujoco/`](../../showcase/video_to_mujoco/)

## Related

[`mediapipe_overlay/`](../mediapipe_overlay/) · [`unity_vrm/`](../unity_vrm/) ·
[`isaac_sim_groot_g1/`](../isaac_sim_groot_g1/) ·
[adapter rules](../README.md#rules-for-an-adapter)
