# `experiments/` — Try something with CBD

[← back to README](../README.md) ·
[Roadmap](../docs/roadmap.md) ·
[Limitations](../docs/limitations.md)

**What is this?** Where a question gets asked using the pieces that already
exist. An experiment *uses* generators, adapters, datasets and tools — it does
not become one.

| | |
|---|---|
| **Input** | existing CBD datasets, existing generators, existing adapters, existing tools |
| **Output** | a result and an honest statement of what it does and does not show |
| **Purpose** | Test a hypothesis about behavior data without disturbing the stable surface |
| **Related** | [`examples/`](../examples/) is the *minimum* experience; this is the *exploratory* one |

**Status: placeholder.** The learning work currently lives in the Demo B
notebook in [`examples/language-to-motion/`](../examples/language-to-motion/).
Moving it here is a pending step. No empty directories have been created for
experiments nobody has started.

## The shape of an experiment

```text
Existing video
      ↓
Existing generator          ← generators/
      ↓
CBD dataset
      ↓
The new thing               ← the experiment
      ↓
Generated / predicted CBD
      ↓
Existing adapter            ← adapters/
      ↓
MuJoCo / Unity / Isaac Sim
      ↓
Evaluation
```

Only the middle box is new. Everything above and below it is borrowed, and that
is what keeps an experiment cheap enough to abandon.

## Dependency direction

Allowed:

```text
generators/  ──▶  experiments/  ──▶  adapters/
tools/       ──▶  experiments/
```

Forbidden:

```text
generators/  ──▶ imports experiments/     ✗
adapters/    ──▶ imports experiments/     ✗
```

An experiment sits on the consumer side. Nothing stable may depend on it, which
is what makes it safe to delete.

## Examples and `experiments/` are different things

| | [`examples/`](../examples/) | `experiments/` |
|---|---|---|
| Question | *How did the original CBD experience work?* | *What happens if we try this?* |
| Content | the smallest end-to-end run | a hypothesis using existing pieces |
| Stability | preserved, kept runnable | may break, may be deleted |
| Shape | video → CBD → MuJoCo | video → generator → CBD → ML → CBD → adapter → sim → evaluation |

## What belongs here

Candidate directions — listed as directions, **not** created as empty
directories:

- **Motion generation from CBD** — the Demo B learning prototype, once it is
  lifted out of its notebook
- **VLA-style training** on `frames.jsonl`, where one line is already a complete
  supervised sample
- **Language-conditioned motion** — instruction in, behavior out
- **Cross-simulator transfer** — the same CBD through several adapters, and what
  differs
- **Behavior dataset quality** — coverage, provenance, what a corpus is missing
- **Video behavior retrieval** — finding a behavior across a library of clips
- **Screen behavior learning** — the [non-body direction](../docs/behavior_asset.md#not-only-human-body-motion),
  unspecified and unimplemented

## Expectations

- **Nothing here is stable.** It may break, and it may be deleted once it has
  answered its question.
- **Say what a result does not show.** The current learning prototype memorises
  and interpolates; it does not generalise to unseen instructions. Claims in
  this directory are held to [`docs/limitations.md`](../docs/limitations.md).
- **Reuse, do not fork.** If you need a generator or adapter to behave
  differently, that is a finding — take it to
  [`docs/compatibility_findings.md`](../docs/compatibility_findings.md) rather
  than copying the code in here.

## Promotion to the stable surface

An experiment does not become core because it worked once.

```text
Experiment
     ↓  repeated success
     ↓  a clear interface
     ↓  useful outside the experiment
  Promote
```

Where it goes:

| If it does | It becomes |
|---|---|
| Source → CBD | a [`generator`](../generators/) |
| CBD → a target | an [`adapter`](../adapters/) |
| Something independently useful | a [`tool`](../tools/) |
