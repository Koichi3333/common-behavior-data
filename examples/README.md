# `examples/` — Initial Minimum Experience

[← back to README](../README.md) · [Showcase](../showcase/) ·
[Experiments](../experiments/)

> **Initial Minimum Experience**
> The original examples are preserved as the smallest end-to-end demonstrations
> of the Common Behavior Data concept.

**What is this?** The two notebooks the project started from, kept as they were.
They run from real input to real output, in a fresh Colab runtime, with no local
setup, and their sample outputs are committed so they can be read without
running anything.

| | |
|---|---|
| **Input** | one video of a person (Demo A) · Demo A output bundles (Demo B) |
| **Output** | a CBD dataset and its replays · a trained prototype and generated behavior |
| **Purpose** | Learn how CBD works by following the smallest complete path through it |
| **Related** | [`showcase/`](../showcase/) shows *results* · [`experiments/`](../experiments/) tries *new things* |

| Demo | Direction | Notebook |
|---|---|---|
| [A — Human Capture](human-capture/) | Observation → behavior data → MuJoCo / Unity | `human_behavior_demo_2_0.ipynb` |
| [B — Language to Motion](language-to-motion/) | Behavior data → learning → generated behavior | `human_behavior_vla_trainer.ipynb` |

## Why these are kept as they are

```text
Video  →  CBD  →  MuJoCo / Unity
```

That is the whole original idea, proven at the smallest scale that proves
anything. It is the project's origin, its first architecture, and the baseline
every later adapter is compared against — including the
[GR00T / Unitree G1 adapter](../adapters/isaac_sim_groot_g1/), whose whole
interest is in *how differently* it behaves from this.

So they are **not** being modernised into the current structure. Rewriting them
to match today's layout would destroy the thing they are useful for. They stay
runnable, and they stay simple.

Development happens elsewhere: [`generators/`](../generators/) ·
[`adapters/`](../adapters/) · [`experiments/`](../experiments/) ·
[`tools/`](../tools/). The Demo A pipeline has already been split into one
generator and three adapters that talk only through `cbd_dataset.zip` — that
split is the recommended way to *run* CBD today. These notebooks remain the
easiest way to *understand* it.

## Where the newer outputs live

`human-capture/sample_output/` has grown past what the Demo A notebook itself
produces. It is now the shared output directory for every adapter that has run
on this clip:

| Directory | Written by |
|---|---|
| `source/` | the source clip |
| `01_mediapipe_overlay/` · `02_mujoco/` · `03_unity_vrm/` | Demo A, and now [`adapters/`](../adapters/) |
| `04_behavior_dataset/` | the generator — **this is canonical CBD**, everything else is derived from it |
| `05_comparison/` | the 3-pane and 4-pane comparison builders |
| `06_groot_g1/` · `07_groot_g1_v2/` | [`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) — v1 and v2 |

The finished videos, with what each run proved and what it broke, are collected
in [`showcase/`](../showcase/).

## Examples vs. Showcase vs. Experiments

| | Question it answers |
|---|---|
| [`examples/`](.) | *How did the initial CBD experience work?* |
| [`showcase/`](../showcase/) | *What can CBD do?* |
| [`experiments/`](../experiments/) | *What happens if we try this?* |

## Conventions

Notebook conventions (English comments, cleared outputs, stable cell numbering,
no credentials) are in
[`CONTRIBUTING.md`](../CONTRIBUTING.md#working-on-the-notebooks).
