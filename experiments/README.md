# `experiments/` — Try something with CBD

[← back to README](../README.md) ·
[The gap register](../docs/compatibility_findings.md) ·
[Roadmap](../docs/roadmap.md) ·
[Limitations](../docs/limitations.md)

**In one sentence:** an experiment takes CBD that already exists, does
something new with it, and reports honestly what happened — including the
**gaps** it ran into.

| | |
|---|---|
| **Input** | CBD datasets, and the existing generators, adapters and tools |
| **Output** | a result, a statement of what it does and does not show, and the gaps it found |
| **Purpose** | Ask a new question about behavior data without disturbing the stable parts |
| **Where the code lives** | here, **or in its own repository** — listed below either way |

## The experiments

| Experiment | The question | Status | Where |
|---|---|---|---|
| **[vla-maker-from-cbd](#vla-maker-from-cbd--a-vla-trained-on-cbd)** | Can a real VLA learn from CBD, and drive any body through CBD's adapters? | **Runs end to end**, kinematic only · research preview | [github.com/Koichi3333/vla-maker-from-cbd](https://github.com/Koichi3333/vla-maker-from-cbd) |
| *yours* | see [ideas](#ideas-nobody-has-started-yet) | — | [start one](#start-your-own-experiment) |

Its small ancestor, Demo B, is kept in
[`examples/language-to-motion/`](../examples/language-to-motion/) as part of the
Initial Minimum Experience.

---

## vla-maker-from-cbd — a VLA trained on CBD

<div align="center">
<img src="https://raw.githubusercontent.com/Koichi3333/vla-maker-from-cbd/main/docs/media/hero_video_to_vla.gif" width="544" alt="Left: a person on a chair reaches for a glass and drinks, with the tracked skeleton overlaid. Right: a simulated humanoid driven by the VLA reaches for a magenta glass and brings it to its mouth">

*Left: an ordinary video, turned into CBD. Right: the VLA, told "a seated person
picks up a glass from the table, drinks from it, and puts it back".*

<sub>Kinematic MuJoCo — no forces, no fingers; the glass attaches once the hand reaches it.
An outside planner guides the hand until it reaches the glass. One of 12 trials of this scene; in the other 11 the glass stops at chin height or below.</sub>
</div>

### What it is, in plain words

A **VLA** (vision-language-action model) looks at a camera image, reads an
instruction, and outputs body motion. This one is NVIDIA **GR00T N1.7** (3B
parameters), fine-tuned on CBD.

It works in three steps, and only the middle one is new:

```text
1. video / mocap ──► CBD                     the generators in this repository
2. CBD ──► training data ──► VLA ──► CBD     vla-maker-from-cbd
3. CBD ──► MuJoCo · Unitree G1 · VRM         the adapters in this repository
```

The important design choice: **the model outputs CBD, not robot joints** — 19
bone rotations plus the hip position, 117 numbers per frame. So the same model
reaches a MuJoCo humanoid, a Unitree G1 or a VRM avatar through the adapters
that already exist, and **no body needs its own retraining**.

### What it showed

Held-out scenes, kinematic MuJoCo. Every number is in its
[results](https://github.com/Koichi3333/vla-maker-from-cbd/blob/main/docs/results.md).

| | Result |
|---|---|
| Hand reaches the object, guided by an outside planner | **0.93** (goal picked by a VLM) · 0.94 (true goal) |
| Same, the model alone | 0.51 — it turns toward the object, but reaches it about half as often |
| A VLM picks the requested object in the image | **378 / 378** |
| Mixing video-derived CBD into up to half the training data | does **not** hurt prediction on the original mocap (9.24–9.55° vs a 9.65° bar) |
| Instructions with no verbatim match in training | `walks forward` +3.06 m · `crawls on the floor` on all fours in 6 of 8 |
| Generated walking on a **Unitree G1**, through CBD's adapter | median direction residual **0.96°** (the teacher walks: 1.54°) |

### What it does not show

- Success in a physics simulator or on a real robot — everything is kinematic
- Grasping with fingers — "held" means the hand came within reach
- Precise reaching by the model alone, without guidance
- Beating *"just hold the current pose"* at predicting video motion (5.53° vs 5.05°)
- Commercial use — the weights are non-commercial, because GR00T N1.7, AMASS and
  SMPL are. The code is Apache-2.0

### The gaps it found

This is the part that matters most for CBD. Training a real model, and putting
its output on a real robot, ran straight into the gaps this repository records
— and added one.

| Gap | Kind | What happened |
|---|---|---|
| Four torso bones carry no rotation (`chest`, `neck`, both shoulders) | **data gap**, closed at a price | To train on video clips, the VLA fitted the torso with SMPL (ROMP). That closed the gap — and brought SMPL's non-commercial, no-redistribution terms into the training data with it |
| The G1's waist travels ±30° | **body gap** | The robot cannot follow the deep bends the generated motion asks for. Not closable; published as a number |
| No locomotion phase | **data gap** | The G1 adapter's foot-contact solve never triggers on a walking clip, so the generated walking reaches the G1 without its feet being solved to the floor |
| No finger bones | **data gap** | "Holding" can only be checked as *the hand came close to the object* |
| No way to state a source's terms | **data gap**, field added in `0.3.0` | *"AMASS-derived motion data must never be redistributed"* — until `0.3.0`, no CBD bundle could say that about itself. The VLA does not set the field yet |

Every row is also in the [gap register](../docs/compatibility_findings.md),
where it is classified and kept.

### Try it

- **No GPU, a few minutes:** the
  [CPU smoke test](https://github.com/Koichi3333/vla-maker-from-cbd#1-cpu-smoke-test-no-gpu-no-weights)
  swaps the model for a fake one and checks that guidance, evaluation and video
  output all run.
- **On Colab A100:** the
  [usable form](https://github.com/Koichi3333/vla-maker-from-cbd#2-run-the-usable-form-on-colab),
  with the weights from
  [Hugging Face](https://huggingface.co/Koichi3333/vla-maker-from-cbd) (gated,
  non-commercial).
- **With your own clip:** record it, convert it with
  [`generators/video_to_cbd/`](../generators/video_to_cbd/), then
  [bring your own CBD](https://github.com/Koichi3333/vla-maker-from-cbd#4-bring-your-own-cbd).

### Help wanted

The VLA is a one-person project so far. Its
[help-wanted list](https://github.com/Koichi3333/vla-maker-from-cbd#help-wanted)
has eight problems, each with an issue, from 🔴 *make the VLA reach objects on
its own* to 🟢 *translate log messages*. Two of them are really CBD problems and
can be solved from this side:

- **Record scenes with objects and contribute them as CBD**
  ([VLA #2](https://github.com/Koichi3333/vla-maker-from-cbd/issues/2)) —
  data is what is missing most, and only data you own leads to a model that can
  be used commercially.
- **Add fingers** ([VLA #6](https://github.com/Koichi3333/vla-maker-from-cbd/issues/6)) —
  a CBD channel first, then a model output.

### Why it lives in its own repository

It needs a 3B-parameter model, an A100, and weights under non-commercial terms.
None of that belongs in a repository whose code is Apache-2.0 and whose
pipeline runs in a free Colab session. And it does not need to live here: it
**only reads CBD and writes CBD**, which is exactly the boundary every
experiment is supposed to keep.

---

## Start your own experiment

### The shape

```text
Existing video
      ↓
Existing generator          ← generators/
      ↓
CBD dataset
      ↓
The new thing               ← the experiment  (only this box is new)
      ↓
Generated / predicted CBD
      ↓
Existing adapter            ← adapters/
      ↓
MuJoCo / Unity / Isaac Sim / robot
      ↓
Evaluation — and the gaps you found
```

Everything above and below the middle box is borrowed. That is what keeps an
experiment cheap enough to abandon.

### Five rules

1. **Read CBD, and emit CBD if you emit behavior.** Then every existing adapter
   works on your output for free — the way the VLA reaches the G1.
2. **Nothing stable may import from an experiment.** `generators/` and
   `adapters/` never depend on `experiments/`, which is what makes an experiment
   safe to delete.

   ```text
   allowed     generators/ ──▶ experiments/ ──▶ adapters/      tools/ ──▶ experiments/
   forbidden   generators/ or adapters/ importing experiments/   ✗
   ```

3. **Say what a result does not show**, in the same voice as what it does.
   Claims here are held to [`docs/limitations.md`](../docs/limitations.md).
4. **Report the gaps you hit.** If a generator or adapter has to behave
   differently for you, that is a gap — take it to the
   [gap register](../docs/compatibility_findings.md) with a number, rather than
   copying the code in here.
5. **Here or elsewhere is your choice.** Small experiments can be a directory
   here. Large ones — big models, special hardware, other licences — can be
   their own repository. Either way, add a row to [the table above](#the-experiments).

### Ideas nobody has started yet

Listed as ideas, **not** created as empty directories:

- **Re-embodiment to task success** — a policy, trained on CBD, completing a pick
  and place on a robot in a *physics* simulator. The roadmap's
  [open question](../docs/roadmap.md#then-re-embodiment)
- **A body unlike any we have** — an SO-101 arm, a quadruped — and what its gap
  looks like
- **Cross-simulator transfer** — the same CBD through several adapters, and
  exactly where they differ
- **Behavior dataset quality** — coverage, provenance, what a corpus is missing
- **Video behavior retrieval** — finding a behavior across a library of clips
- **Screen behavior learning** — the
  [non-body direction](../docs/behavior_asset.md#not-only-human-body-motion),
  unspecified and unimplemented

### When an experiment graduates

It does not become core because it worked once.

```text
Experiment
     ↓  repeated success
     ↓  a clear interface
     ↓  useful outside the experiment
  Promote
```

| If it does | It becomes |
|---|---|
| Source → CBD | a [`generator`](../generators/) |
| CBD → a body | an [`adapter`](../adapters/) |
| Something independently useful | a [`tool`](../tools/) |

## Examples, Showcase and Experiments

| | Question | Stability |
|---|---|---|
| [`examples/`](../examples/) | *How did the original CBD experience work?* | preserved, kept runnable |
| [`showcase/`](../showcase/) | *What can CBD do?* | results, linked in place |
| `experiments/` | *What happens if we try this?* | may break, may be deleted |
