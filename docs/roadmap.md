# Roadmap

[← back to README](../README.md)

Nothing on this page exists as code yet, unless it is listed under
[Done](#done). Planned items are deliberately kept out of the repository tree:
an empty adapter directory is worse than an honest roadmap.

## Done

- **Video → CBD** — Demo A, [`examples/human-capture`](../examples/human-capture/)
- **CBD → MediaPipe overlay** — behavior data drawn back onto the source pixels
- **CBD → MuJoCo humanoid** — `humanoid.xml` + `motion.npz`, kinematic replay
- **CBD → Unity / VRM** — `motion.vrma`, playable on any VRM 1.0 avatar
- **CBD → behavior dataset** — `frames.jsonl` with vision, language, motion and
  phase on one timeline
- **Language → CBD** — Demo B, small learning prototype, generated behavior
  replaying through the same adapters

## Next: SO-101 pick & place

The most important open question is not capture quality or model size. It is:

> **Does behavior intent survive a change of embodiment?**

```text
Human video
   ↓
Common Behavior Data
   ↓
Behavior intent / end-effector representation
   ↓
SO-101 adapter
   ↓
MuJoCo SO-101
   ↓
Task success
```

The goal is **not** copying human joint angles onto a robot arm. A 5-DoF arm has
no spine, no shoulder blade and no fingers; joint-level transfer is meaningless.

What might transfer is the intent sequence:

```text
Reach → Grasp → Lift → Carry → Place → Release
```

If a CBD episode captured from a human can drive an SO-101 in MuJoCo to complete
a pick & place through that sequence, the representation is doing real work. If
it cannot, we learn exactly which part of the schema was too human-shaped — which
is also a useful result, and will be reported as one.

Success criterion, stated in advance: **task success in simulation**, not visual
similarity to the human demonstration.

### What this requires from the schema

- behavior intent as a first-class element, separable from human joint motion
- an end-effector / object-relative representation (currently objects only carry
  a proxy position)
- a way for an adapter to declare what it cannot represent

Expect the schema to change because of this experiment. That is the intended
order of events: adapters drive the specification, not the other way around.

## After that

Ordered by what would teach us the most, not by effort.

| Direction | Why it matters |
|---|---|
| **Schema extraction** | Turn "what the notebooks emit" into a validatable schema with a compatibility checker |
| **Object trajectory generation** | Demo B currently generates only the human body; behavior involving objects needs the objects |
| **LeRobot interoperability** | The most natural neighbour in the robot-learning ecosystem; a conversion in both directions would test the schema hard |
| **ROS 2 bridge** | Makes CBD reachable from existing robot stacks |
| **Isaac adapter** | A second simulator is the real test of engine independence |
| **Blender / Unreal exporters** | Extends reach into content pipelines, and stresses the avatar side of the schema |
| **IK and retargeting library** | Shared machinery every embodiment adapter otherwise reinvents |
| **Evaluation tooling** | How do you say one behavior dataset is *better* than another? Currently unanswered |
| **Multi-person capture** | Interaction between people is behavior too |
| **Motion tokenisation / diffusion** | Better generation once the corpus justifies it |

## Explicitly not planned

To keep the scope honest:

- a hosted API or SaaS product
- a foundation model
- large-scale dataset collection
- a production robot stack
- premature formal standardisation

## How the roadmap changes

Items move up when someone has a concrete use for them, and adapters written by
contributors are the strongest signal available. If you want something on this
list sooner, open a
[Discussion](https://github.com/Koichi3333/common-behavior-data/discussions) describing what you are trying to connect — a
real integration is worth more than a vote.

---

**See also:** [Ecosystem](ecosystem.md) · [Limitations](limitations.md) · [Contributing](../CONTRIBUTING.md)
