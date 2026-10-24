# `generators/` — Create CBD

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md)

**What is this?** The half of the pipeline that *produces* Common Behavior
Data. A generator reads an observation and writes canonical CBD. That is all it
does.

| | |
|---|---|
| **Input** | An observation — today, one video of a person |
| **Output** | Canonical CBD: `04_behavior_dataset/`, packaged as `cbd_dataset.zip` |
| **Purpose** | Turn a recording into a reusable behavior asset that any adapter can consume |
| **Related** | [`adapters/`](../adapters/) consume what this writes · [`specification/`](../specification/) defines the format |

```text
source_video.mp4 ──▶ [ generator ] ──▶ cbd_dataset.zip ──▶ any adapter
                      MediaPipe        (canonical CBD)
                      + tracking
                      + captions
```

## What is here

| Generator | In | Out | Runs in |
|---|---|---|---|
| [`video_to_cbd/`](video_to_cbd/) | one video of a person, 10–30 s | `cbd_dataset.zip` — `04_behavior_dataset/` with `timeline/frames.jsonl`, `human/`, `objects/`, `interactions/`, `metrics/`, `quality/`, optional `captions/` | Colab — **CLI recommended** |

That is the only one today. It is the extraction of the Demo A notebook's
observation half, made to stand on its own.

## Minimal example

```bash
colab new -s cbd
colab upload -s cbd ./source_video.mp4 /content/source_video.mp4
colab exec   -s cbd -f video_to_cbd/cbd_generator_video_to_cbd.ipynb --timeout 1800
colab download -s cbd \
  /content/human_behavior_demo_2_0/cbd_dataset.zip ./cbd_dataset.zip
# keep the session alive and run the adapters on the same VM
```

Full instructions, the Colab UI path, and the optional Gemini captions:
[`video_to_cbd/README.md`](video_to_cbd/README.md).

## What belongs here

Anything that **writes** Common Behavior Data:

- **Observation generators** — video → CBD (`video_to_cbd/`: MediaPipe pose /
  hands / face, tracking, smoothing, bone rotations, interaction candidates,
  metrics, quality)
- **Language generators** — instruction → CBD (the Demo B model's decode side,
  once it is separated from its training code)
- **Captioning and annotation passes** that write onto the canonical timeline
- **Synthetic / procedural generators**, if any

Directions that are plausible but **not implemented and deliberately have no
empty directory**: screen-recording → CBD, sensor-assisted video → CBD. They are
in the [roadmap](../docs/roadmap.md); a directory appears when code does.

## What does not belong here

| | Goes to |
|---|---|
| Conversion of CBD into an engine-specific format | [`adapters/`](../adapters/) |
| Training, evaluation, research questions | [`experiments/`](../experiments/) |
| Video prep, asset creation, inspection utilities | [`tools/`](../tools/) |

## No target-specific knowledge, in either direction

A generator must not contain anything about a particular consumer. Not a G1
ankle limit, not a Dex3 finger count, not an Isaac Sim physics quirk, not a
MuJoCo solver setting. If a generator starts knowing about a robot, the
representation has stopped being canonical and everything downstream of it
inherits that robot's assumptions.

The traffic in the *other* direction is not only allowed, it is the point. When
an adapter discovers that canonical CBD is genuinely missing something — a
rotation nobody writes, a phase field that is degenerate, a support relation
that has no channel — that comes back here:

```text
Adapter finding ──▶ specification feedback ──▶ generality check ──▶ generator improvement
```

Real examples with numbers are in
[`docs/compatibility_findings.md`](../docs/compatibility_findings.md). Two of
them are the generator's to answer: `interaction_events.csv` currently ships as
a header with no rows, and four of the nineteen bones (`chest`, `neck`, both
shoulders) are written as identity in every frame.

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
6. **Never write a channel that cannot be told apart from a measurement.** If a
   channel was not observed, say so in the data rather than writing a plausible
   default. This is the rule the current pipeline breaks: `chest`, `neck` and
   both shoulders are written as identity rotations in every frame, and `phase`
   is written for all 96 frames of a pick-and-place clip as `Idle` — both
   indistinguishable, on disk, from a real observation.

Rule 6 is **implemented in [`video_to_cbd/`](video_to_cbd/) as of dataset
version `0.3.0`**: a per-channel provenance ledger in `manifest.json` and
`quality/channel_provenance.json`, a `provenance` column in
`human/bone_rotations.csv`, and `degenerate` for a field that is populated
without carrying information. Tiers are **measured from the series, not
asserted**, and the ledger covers every channel the dataset writes — including
the absent ones.

It had to land here before anywhere else: the generator is the only stage that
knows the answer at write time. An adapter can only guess afterwards, per
target, by hand — which is what
[`isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) still does.

See [specification → generalising it](../specification/README.md#generalising-it)
for the fields, and the [roadmap](../docs/roadmap.md#next-in-band-provenance)
for what is still missing (no adapter consumes it, and there is no validator).

See [`specification/README.md`](../specification/README.md) for the
representation, and [`CONTRIBUTING.md`](../CONTRIBUTING.md) before opening a PR.
