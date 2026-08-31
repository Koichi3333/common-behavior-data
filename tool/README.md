# `tool/` — utilities around CBD

[← back to README](../README.md) ·
[Specification](../specification/README.md)

**Status: placeholder.** No tools have been extracted here yet.

## What belongs here

Small, focused utilities that make CBD easier to work with — they neither
produce behavior data nor target a specific engine.

**This directory is cross-cutting: anything useful at *any* stage of the
pipeline belongs here**, whether it helps while generating behavior data,
while writing or debugging an adapter, or while running an experiment. A tool
does not have to be tied to one stage — a bundle inspector is equally useful to
someone checking a capture, someone checking an adapter's input, and someone
checking a training set.

Typical categories:

- **Validation** — does a bundle match the current representation? Do the
  row-oriented (`frames.jsonl`) and column-oriented (CSV) views agree?
- **Inspection** — summarise a bundle, diff two of them, list what a dataset
  actually contains
- **Visualisation** — plots of joint angles, trajectories, phase timelines
- **Conversion and packing** — bundle/unbundle, resampling, trimming, merging
  episodes
- **Dataset statistics** — coverage, quality and provenance reporting

## Which stage a tool serves

Worth stating in a tool's own README, because it tells people when to reach for
it:

| Stage | Examples of what helps |
|---|---|
| [`generator/`](../generator/) | check a capture's quality and provenance, preview a timeline, spot dropped frames |
| [`adapter/`](../adapter/) | inspect what an adapter received, compare its output against the canonical data, diff two runs |
| [`experiment/`](../experiment/) | dataset statistics, coverage over instructions and phases, plotting a training set before training on it |
| Any / all | validation, bundle packing, format conversion, visualisation |

## Expectations

- Small and single-purpose. A tool that grows an engine-specific output belongs
  in [`adapter/`](../adapter/) instead.
- Read-only by default where possible; never rewrite raw observation data.
- Tools should fail loudly on a bundle they do not understand rather than
  silently guessing — the schema is unstable, and a clear error is a useful
  signal about where it broke.
