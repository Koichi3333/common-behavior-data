# `examples/` — the initial demos

[← back to README](../README.md)

This directory holds the **initial end-to-end demos**: the two Colab notebooks
that show what Common Behavior Data is, running from real input to real output,
with their sample outputs committed so they can be read without running
anything.

| Demo | Direction | Notebook |
|---|---|---|
| [A — Human Capture](human-capture/) | Observation → behavior data | `human_behavior_demo_2_0.ipynb` |
| [B — Language to Motion](language-to-motion/) | Behavior data → learning → generation | `human_behavior_vla_trainer.ipynb` |

They are the technical source of truth for what CBD currently is, and they are
kept runnable top-to-bottom in a fresh Colab runtime with no local setup.

## Scope

`examples/` is a **showcase**, not the development surface. Ongoing development
happens in the four working directories:

[`generator/`](../generator/) · [`adapter/`](../adapter/) ·
[`experiment/`](../experiment/) · [`tool/`](../tool/)

As the generator, adapter, and learning code inside these notebooks is
extracted into those directories, the demos are expected to become thinner —
showing how the pieces fit together rather than containing the pieces
themselves.

Notebook conventions (English comments, cleared outputs, stable cell numbering,
no credentials) are in [`CONTRIBUTING.md`](../CONTRIBUTING.md#working-on-the-notebooks).
