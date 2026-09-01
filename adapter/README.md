# `adapter/` — CBD to a target system

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md)

**Status: first examples extracted.** [`ver0_example/`](ver0_example/) holds
three adapters lifted out of the Demo A notebook and made to stand on their
own — one notebook per target, each reading nothing but canonical CBD. Making
them reusable code rather than notebook cells is the next step.

## `ver0_example/` — three targets, one dataset

Each notebook consumes `cbd_dataset.zip` written by
[`generator/ver0_example/cbd_generator_video_to_cbd.ipynb`](../generator/ver0_example/cbd_generator_video_to_cbd.ipynb).
None of them runs MediaPipe, and none of them reads another adapter's output.

| Notebook | Target | Writes | Needs a GPU? |
|---|---|---|---|
| [`cbd_adapter_mediapipe_overlay.ipynb`](ver0_example/cbd_adapter_mediapipe_overlay.ipynb) | annotated video on the original pixels | `output/01_mediapipe_overlay/mediapipe_overlay.mp4` + `adapter_report.json` | no |
| [`cbd_adapter_mujoco.ipynb`](ver0_example/cbd_adapter_mujoco.ipynb) | MuJoCo | `output/02_mujoco/humanoid.xml`, `motion.npz`, `object_trajectory.csv`, `replay_mujoco.py`, `mujoco_simulation.mp4` | optional — T4 renders with EGL, CPU falls back to OSMesa |
| [`cbd_adapter_unity_vrm.ipynb`](ver0_example/cbd_adapter_unity_vrm.ipynb) | Unity / VRM 1.0 | `output/03_unity_vrm/motion.vrma`, `object_trajectory_unity.json`, `ObjectTrajectoryPlayer.cs`, `README_UNITY.md` | no — it writes files, Unity plays them |

Each notebook also writes an `adapter_report.json` saying what it could **not**
represent, and packages its own output zip
(`overlay_adapter_output.zip`, `mujoco_adapter_output.zip`,
`vrm_adapter_output.zip`).

### Recommended: run them from the Colab CLI

Every adapter looks for its input in the same order — the dataset already
unpacked in this runtime, then `/content/cbd_dataset.zip`, then the upload
widget (UI only) — so the **recommended way to run them is the Colab CLI, in
the same session the generator ran in**: the dataset is already there, and
nothing has to be uploaded between steps.

```bash
# same session as the generator — nothing to upload
colab exec -s cbd -f cbd_adapter_mediapipe_overlay.ipynb --timeout 1800
colab exec -s cbd -f cbd_adapter_mujoco.ipynb           --timeout 1800
colab exec -s cbd -f cbd_adapter_unity_vrm.ipynb        --timeout 900

colab download -s cbd \
  /content/human_behavior_demo_2_0/mujoco_adapter_output.zip ./mujoco_adapter_output.zip
```

A fresh session works just as well — hand it the zip first:

```bash
colab upload -s cbd2 ./cbd_dataset.zip /content/cbd_dataset.zip
colab exec   -s cbd2 -f cbd_adapter_mujoco.ipynb --timeout 1800
```

In a headless run no adapter opens an upload widget or embeds a video player;
it prints the output path instead, so `colab exec` always terminates.
`--timeout` applies **per cell**. The Colab UI is still fully supported — run
the cells top to bottom and the finished video is embedded in place.

The three-screen comparison is deliberately **not** here: it needs a Unity
recording made on your own machine, so it cannot run in the same CLI chain. The
comparison video it produces is already in
[`examples/human-capture/sample_output/05_comparison/`](../examples/human-capture/sample_output/05_comparison/).

Adding a target should mean writing one more notebook beside these three, not
touching the generator. That is the property the split is there to test.

## What belongs here

Anything that **reads** Common Behavior Data and converts it for a specific
engine, embodiment, or format. One subdirectory per target:

| Target | Today | Where it runs today |
|---|---|---|
| MediaPipe overlay video | Available | [`ver0_example/cbd_adapter_mediapipe_overlay.ipynb`](ver0_example/cbd_adapter_mediapipe_overlay.ipynb) |
| MuJoCo (`humanoid.xml` + `motion.npz`) | Available | [`ver0_example/cbd_adapter_mujoco.ipynb`](ver0_example/cbd_adapter_mujoco.ipynb) |
| Unity / VRM (`motion.vrma`) | Available | [`ver0_example/cbd_adapter_unity_vrm.ipynb`](ver0_example/cbd_adapter_unity_vrm.ipynb) |
| Dataset views (`frames.jsonl` + CSVs) | Available | Written by the generator; read directly |
| Robot embodiments (e.g. SO-101) | Planned | — |
| LeRobot · Isaac · ROS 2 · Blender / Unreal | Planned | — |

## Rules for an adapter

From [`CONTRIBUTING.md`](../CONTRIBUTING.md), unchanged:

1. **Read canonical data**, not another adapter's output
2. **Convert coordinates at your boundary** — canonical is Y-up, right-handed,
   person facing +Z
3. **Keep model and motion separate** where the target format allows it
4. **Do not promote candidates** — `grasp_candidate` must not become `grasp`
5. **Report what you could not represent**, rather than silently approximating
6. **Preserve provenance** — if you derive a position, say how

If a rule blocks you, that is interesting: it probably means the schema is
missing something. Open an issue.

## Open design question

The adapter *contract* is not formalised yet — what a consumer is guaranteed to
find, how it declares which parts it uses, and how it reports what it dropped.
The `adapter_report.json` each `ver0_example` notebook writes is a first,
informal answer to the last part of that.
See [Architecture → what the adapter interface has to become](../docs/architecture.md)
and [Specification → open questions](../specification/README.md#open-questions).
Adapters drive the specification here, not the other way around.
