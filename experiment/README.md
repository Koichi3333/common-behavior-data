# `experiment/` — research and learning code

[← back to README](../README.md) ·
[Roadmap](../docs/roadmap.md) ·
[Limitations](../docs/limitations.md)

**Status: placeholder.** Experimental work currently lives in the Demo B
notebook in [`examples/language-to-motion/`](../examples/language-to-motion/).

## What belongs here

Code that **asks a question about CBD** rather than providing a stable piece of
it:

- **Learning prototypes** — the VLA-like causal Transformer with vision and
  text conditioning, training loops, dataloaders over `frames.jsonl`
- **Re-embodiment experiments** — whether behavior intent (reach, grasp, lift,
  carry, place, release) survives a change of body; see the
  [roadmap](../docs/roadmap.md)
- **Schema experiments** — e.g. carrying contact, force, torque, tactile or IMU
  channels on the same timeline
- **Evaluation** — task success, reconstruction error, ablations

## Expectations

- Nothing here is part of the stable surface. It may break, and it may be
  deleted once it has answered its question.
- **Say what a result does not show.** The current learning prototype
  memorises and interpolates; it does not generalise to unseen instructions.
  Claims in this directory are held to
  [`docs/limitations.md`](../docs/limitations.md).
- If an experiment stabilises into something reusable, it graduates into
  [`generator/`](../generator/), [`adapter/`](../adapter/) or
  [`tool/`](../tool/).
