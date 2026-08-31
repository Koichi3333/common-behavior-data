# `generator/` — producing Common Behavior Data

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md)

**Status: placeholder.** This directory is where CBD *generators* will live.
Nothing has been extracted here yet — the working generators currently sit
inside the demo notebooks in [`examples/`](../examples/).

## What belongs here

Anything that **writes** Common Behavior Data:

- **Observation generators** — video → CBD (the Demo A pipeline: MediaPipe
  pose / hands / face, tracking, smoothing, bone rotations, interaction
  candidates, metrics, quality)
- **Language generators** — instruction → CBD (the Demo B model's decode side,
  once it is separated from its training code)
- **Captioning and annotation passes** that write onto the canonical timeline
- **Synthetic / procedural generators**, if any

## What does not belong here

- Conversion of CBD into an engine-specific format → [`adapter/`](../adapter/)
- Training, evaluation, and research code → [`experiment/`](../experiment/)
- Inspection, validation, and conversion utilities → [`tool/`](../tool/)

## Rules for a generator

1. **Write canonical CBD**, not an adapter's output. The canonical frame is
   Y-up, right-handed, person facing +Z.
2. **Never overwrite raw observation data.** Derived values live beside the
   landmarks they came from, not on top of them.
3. **Preserve provenance.** Every derived 3D position carries a
   `position_source`; every caption records the model that produced it.
4. **Do not promote candidates.** A heuristic stays named as a candidate.
5. Observed and generated behavior are written in the **same schema** — there
   is no separate "generated motion format".

See [`specification/README.md`](../specification/README.md) for the
representation, and [`CONTRIBUTING.md`](../CONTRIBUTING.md) before opening a PR.
