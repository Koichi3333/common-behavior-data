# Observation as a reusable behavior asset

[← back to README](../README.md) · [Concept](concept.md) ·
[Architecture](architecture.md) · [Specification](../specification/README.md)

**One sentence:** *An observation of behavior — most often a video — is worth
keeping as an asset that can be re-analysed, re-generated, re-targeted and
re-used, not as a one-time input to one pipeline.*

## The usual shape, and the problem with it

Behavior is normally captured *into* a tool. A motion capture format, a game
engine's animation clip, a simulator's trajectory file, a dataset schema, a
model's output head, one robot's joint layout. The recording served its purpose
the day it was made, and after that it is worth roughly as much as the tool that
holds it.

The next tool means rebuilding the pipeline. The next model means recapturing.
The footage you already have — which cost the most to produce — participates in
none of it.

## The alternative

Treat the observation as the durable thing and everything downstream as
regenerable:

```text
Video / Screen capture / Sensor / Other observation
        │
        ▼
   Behavior extraction          ← replaceable: a better model re-runs on the same source
        │
        ▼
   Canonical CBD                ← the asset
        │
        ├─▶ MuJoCo              ← replaceable: an adapter per target
        ├─▶ Unity / VRM
        ├─▶ Isaac Sim / Unitree G1
        └─▶ ML dataset
```

A source clip you keep can be:

- **re-analysed** when a better pose or detection model exists
- **re-generated** into CBD by a different generator, without recapturing
- **re-targeted** to an embodiment nobody had in mind when it was filmed
- **read as a dataset** — one line of `frames.jsonl` is a complete training sample
- **compared across simulators**, because the same behavior reaches all of them
- **reused by tools that do not exist yet**

None of that is available if the recording only survives as a MuJoCo trajectory.

The [GR00T / Unitree G1 adapter](../adapters/isaac_sim_groot_g1/) is the current
proof: it drives a robot from a clip filmed long before that robot was a target,
with no recapture and no change to the representation.

## Why video specifically

Video is emphasised because it is the most *available* observation, not because
it is the most accurate:

- footage already exists, in quantity, and can be reused
- filming needs no rig, no suit, no calibrated capture volume
- datasets grow without a studio
- a clip can be re-analysed years later by a better model
- new models can be applied backwards over everything already captured
- it works in settings where specialised sensors will never be installed

Its weaknesses are real and stated plainly in
[`docs/limitations.md`](limitations.md): monocular depth is estimation, contact
is inferred, scale is not measured.

## Sensors are not the opposite of this

Video being the easiest entrance does not make it the only one, and it does not
make sensors a competing approach. They answer precisely the questions video
answers badly:

| Sensors are good for | Because video gives |
|---|---|
| accuracy correction | estimated depth |
| ground truth | heuristic candidates |
| calibration and scale | a scene of unknown metre size |
| validation | plausibility, not measurement |
| physical quantities — force, torque, contact, tactile, IMU | nothing at all |

The [roadmap](roadmap.md) treats force and contact channels as an open schema
question, and the G1 adapter is the reason it is now a concrete one: a
joint-space replay cannot say whether the robot could physically hold the pose.

The principle:

> **Turn observations into reusable behavior assets.**
> Video is the most available observation. Sensors make it more trustworthy.

## Not only human body motion

The pipeline today extracts human body motion, and that is where the evidence
is. But nothing in *observation → behavior → reuse* is specific to a skeleton.
The same shape covers, at least in principle:

```text
Human body motion              Robot demonstration
Hand / object manipulation     Work procedure
Screen recording               PC / UI operation
Application workflow           Task demonstration
```

Screen behavior is the clearest adjacent case — an interaction, a state, an
action, on a timeline, extracted from a recording — and the same
generator / adapter split would apply. **It is not specified and not
implemented**, and there is deliberately no empty directory for it. It is on
the [roadmap](roadmap.md) as a direction, and it is here as a reason not to
build human-skeleton assumptions into the repository's structure.

## What this asks of the repository

Three consequences, and they are why the directories are shaped the way they
are:

1. **Generators are replaceable, canonical CBD is not.** A generator can be
   rewritten around a better model; what it wrote stays readable. See
   [`generators/`](../generators/).
2. **Adapters are replaceable, and there is one per target.** Deleting an
   adapter loses no behavior. See [`adapters/`](../adapters/).
3. **What broke on the way to a target is itself an asset.** Differences between
   embodiments are recorded, not smoothed away — see
   [`docs/compatibility_findings.md`](compatibility_findings.md).
