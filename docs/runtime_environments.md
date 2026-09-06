# Where things run

[← back to README](../README.md) · [Architecture](architecture.md) ·
[Adapters](../adapters/README.md)

**One sentence:** *Colab CLI where the target allows it; a documented machine
where it does not — and the README of anything in the second group says so on
its own page.*

This repository is meant to be reproducible by someone who is not the author and
does not have the author's machine. Most of it clears that bar the easy way: a
free Colab runtime. One part does not, and hiding that would be worse than
writing it down.

## The rule

| | |
|---|---|
| **Default** | Google Colab, driven from the **Colab CLI**. Anything new that can run there, should. |
| **Exception** | A target whose runtime cannot exist in Colab. Then the adapter's own README must state **what machine it was run on**, at the level of *class of machine* — not identity. |
| **Never** | A step that only runs on a machine nobody describes. |

"Class of machine" means: GPU, memory, OS, the container or runtime version, and
roughly what a full run costs in time. It does **not** mean cloud project names,
VM or host names, networks, zones, addresses, accounts, or credentials — none of
those affect whether you can reproduce the result, and none of them appear
anywhere in this repository.

## Why Colab CLI is the default

The generator and the three notebook adapters are chained through one artifact,
`cbd_dataset.zip`. Run them from the CLI in a single session and that chain
becomes a shell script:

```bash
colab new -s cbd
colab upload -s cbd ./source_video.mp4 /content/source_video.mp4
colab exec   -s cbd -f cbd_generator_video_to_cbd.ipynb    --timeout 1800
colab exec   -s cbd -f cbd_adapter_mujoco.ipynb            --timeout 1800
colab stop   -s cbd
```

Three properties follow, and they are the reason this is the default rather
than a preference:

- **One session, one dataset.** Every adapter finds the dataset already unpacked
  in the runtime. Nothing is re-uploaded, and no adapter can silently read a
  different episode than the one the generator wrote.
- **Nothing blocks.** Each notebook detects a headless run and never opens an
  upload widget or embeds a video player; it prints paths instead, so
  `colab exec` always terminates. `--timeout` is per cell.
- **Scriptable.** The same commands run from CI. That is what makes a
  generator → adapter chain reproducible by a stranger.

The Colab UI stays fully supported for all of these. The CLI is what makes them
*checkable*.

## What runs where today

| Step | Where | GPU |
|---|---|---|
| [`generators/video_to_cbd/`](../generators/video_to_cbd/) | Colab (CLI or UI) | T4 helps; CPU completes |
| [`adapters/mediapipe_overlay/`](../adapters/mediapipe_overlay/) | Colab (CLI or UI) | no |
| [`adapters/mujoco/`](../adapters/mujoco/) | Colab (CLI or UI) | optional — T4 renders via EGL, CPU falls back to OSMesa |
| [`adapters/unity_vrm/`](../adapters/unity_vrm/) | Colab writes the files; **Unity plays them on your own machine** | no |
| [`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) — retarget + compose | any machine, plain Python | no |
| [`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) — **render + PhysX** | **Google Compute Engine, one NVIDIA L4** | yes |

## The one exception: Isaac Sim

Isaac Sim does not fit in a Colab runtime. It wants an RTX GPU that the runtime
does not expose, a container measured in tens of gigabytes, and a shader cache
that survives between runs — a cold cache costs about ten minutes before a
single frame is drawn. So the render and physics passes of the GR00T / Unitree
G1 adapter were developed and run on a cloud GPU VM:

| | |
|---|---|
| Where | Google Compute Engine VM, Linux, single GPU |
| Machine type | `g2-standard-16` — 16 vCPU, 64 GB memory |
| GPU | 1 × NVIDIA L4 |
| Isaac Sim | 6.0.0, NGC container `nvcr.io/nvidia/isaac-sim:6.0.0-dev2`, headless |
| Robot asset | NVIDIA's public `g1_29dof_with_hand_rev_1_0.usd`, mirrored locally — not committed here |
| A full v2 run | ≈15 min PhysX settle + ≈10 min render with a warm shader cache |

Two things keep this from becoming a private-machine dependency:

1. **The split is at the GPU boundary, not the adapter boundary.** The retarget
   — canonical CBD to a 43-DoF trajectory and a USD stage — is `numpy` and
   `usd-core`, and so is the video compose. That is most of the adapter's logic,
   and you can read, run and change it on a laptop. Only the middle pass needs
   the GPU box.
2. **The outputs are committed.** `06_groot_g1/` and `07_groot_g1_v2/` are in
   the repository, so the result is inspectable — USD stages, joint CSVs, the
   GR00T-LeRobot dataset, the physics report and the video — by someone who
   never runs the GPU step at all.

Any machine of that class should reproduce it: `run_groot_g1_docker.sh` takes
the image and the scratch directory from environment variables and mounts the
repository read-only. Nothing in it is specific to the VM it was written on.

## Adding a new target

If your target runs in Colab, follow the notebook adapters and say so in your
README's first paragraph.

If it does not, that is fine — say **that**, in a section near the top of the
adapter's README, and include:

- what class of machine you ran it on (GPU, memory, OS, runtime version)
- which of your steps actually need it, and which are plain Python
- roughly what a full run costs
- committed outputs, so the result can be read without the machine

Leave out anything that identifies a particular host or account. If a reader
cannot tell from your README whether they can reproduce your result, the README
is not finished.
