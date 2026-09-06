# `tools/` — Prepare and manipulate assets

[← back to README](../README.md) ·
[Specification](../specification/README.md)

**What is this?** Standalone utilities for working with behavior assets — video
preparation, dataset creation, 3D asset building, inspection, comparison. Each
one is useful on its own, and none of them is part of any adapter's internals.

| | |
|---|---|
| **Input** | videos, CBD datasets, object metadata — whatever the tool takes |
| **Output** | processed video, an asset, a report, a plot, a comparison |
| **Purpose** | Make behavior assets easier to produce, check and reuse |
| **Related** | [`generators/`](../generators/) · [`adapters/`](../adapters/) · [`experiments/`](../experiments/) |

**Status: mostly empty.** The comparison-video builders currently live beside
the sample output they compose
([`examples/human-capture/sample_output/05_comparison/`](../examples/human-capture/sample_output/05_comparison/));
they are the clearest candidates to move here once they take an arbitrary set of
inputs rather than that sample. No empty directories have been created for the
rest — a directory appears when code does.

## What this directory is *not*

**It is not the place to factor out shared adapter logic.** That is the trap
this README exists to name.

When an adapter finds something that works — a four-point foot contact solve, a
placement solver, a continuity pass — the instinct is to lift it into `tools/`
so every adapter can import it. **Do not.** Physics assumptions differ per
simulator, body structure differs per robot, and a shared helper has to be right
for all of them at once. Adapters stay [self-contained](../adapters/README.md#self-contained-beats-dry);
what travels between them is the *finding*, recorded in
[`docs/compatibility_findings.md`](../docs/compatibility_findings.md).

So: nothing target-specific here. No Isaac Sim internals, no G1 joint tables, no
MuJoCo solver settings, no Unity conventions.

## What belongs here

Independent utilities that help build and check behavior assets:

| Category | Examples |
|---|---|
| **Video preparation** | cropping, trimming, resampling, stabilisation, format normalisation |
| **Masking and anonymisation** | person / object / background masks; faces removed before a clip is shared |
| **Asset creation** | COCO object class → metadata or primitive → Blender asset; prop libraries |
| **Comparison** | build a side-by-side video from a source clip and several target outputs |
| **Dataset utilities** | inspect, summarise, diff two bundles, resample, trim, merge episodes |
| **Validation** | does a bundle match the current representation? Do `frames.jsonl` and the CSVs agree? |
| **Visualisation** | joint-angle plots, trajectories, phase timelines |
| **Statistics** | coverage, quality, provenance reporting over a corpus |

## Why these matter as much as the pipeline

Behavior assets are only reusable if they can be prepared and inspected. A clip
that cannot be anonymised cannot be shared. A dataset nobody can summarise
cannot be trusted. A result nobody can put beside its source cannot be judged.
Tools are what make the [asset](../docs/behavior_asset.md) part of "reusable
behavior asset" true.

## Which stage a tool serves

Worth stating in a tool's own README, because it tells people when to reach for
it:

| Stage | What helps |
|---|---|
| [`generators/`](../generators/) | prepare and mask source video, check a capture's quality and provenance, spot dropped frames |
| [`adapters/`](../adapters/) | inspect what an adapter received, compare its output against the source, diff two runs |
| [`experiments/`](../experiments/) | dataset statistics, coverage over instructions and phases, plotting a training set before training on it |
| Any / all | validation, bundle packing, format conversion, visualisation |

## Expectations

- **Single-purpose and standalone.** A tool that grows an engine-specific output
  belongs in [`adapters/`](../adapters/) instead.
- **Useful on its own**, not only as a step in one pipeline.
- **Read-only by default** where possible; never rewrite raw observation data.
- **Fail loudly** on a bundle it does not understand rather than silently
  guessing — the schema is unstable, and a clear error is a useful signal.
- **Say which stage it serves** in its own README.
