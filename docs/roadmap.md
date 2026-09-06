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
- **CBD → Isaac Sim / GR00T, Unitree G1** — the same dataset onto a real robot's
  kinematics: 43-DoF trajectory, layered USD stage, PhysX-settled poses and a
  GR00T-LeRobot dataset ([`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/)).
  **Kinematics only — no policy, no task-success claim**

## Next: re-embodiment

The most important open question is not capture quality or model size. It is:

> **Does behavior intent survive a change of embodiment?**

**Half of this has now been answered.** The G1 adapter above took canonical CBD
onto a machine whose proportions are not negotiable, and the representation
carried — for *kinematics*, at a stated cost, with the residuals published. What
it did **not** answer is the half that matters most, because the adapter runs no
policy: it writes a dataset a policy could be trained on and never asks the
robot to accomplish anything. The success criterion below is still unmet.

```text
Human video
   ↓
Common Behavior Data
   ↓
Behavior intent / end-effector representation
   ↓
Embodiment adapter
   ↓
Simulated robot  ← done for the G1, kinematically
   ↓
Task success     ← still open: no policy has been run
```

The goal is **not** copying human joint angles onto a robot arm. A robot arm has
no spine, no shoulder blade and no fingers; joint-level transfer is meaningless.

What might transfer is the intent sequence:

```text
Reach → Grasp → Lift → Carry → Place → Release
```

If a CBD episode captured from a human can drive a robot in simulation to
complete a pick & place through that sequence, the representation is doing real
work. If it cannot, we learn exactly which part of the schema was too
human-shaped — which is also a useful result, and will be reported as one.

Success criterion, stated in advance: **task success in simulation**, not visual
similarity to the human demonstration.

### Which platform carries it to task success is open

The G1 fixed the first embodiment; it did not fix the one that will close this
question. Driving a policy to task success on a G1 in Isaac Lab Arena is the
direct continuation, and the GR00T-LeRobot dataset the adapter already writes is
the input for it. A low-cost arm such as SO-101 in MuJoCo is the other
candidate, and for a different reason: the barrier to reproducing a result on
real hardware is low, and a robot arm shares almost nothing with the human
skeleton the schema grew around — which makes it the harsher test of the two.

The choice should be driven by what someone actually wants to connect, so if you
have a platform in mind, an issue or a discussion is the place to raise it.

### What this requires from the schema

- behavior intent as a first-class element, separable from human joint motion
- an end-effector / object-relative representation (currently objects only carry
  a proxy position)
- a way for an adapter to declare what it cannot represent

Expect the schema to change because of this experiment. That is the intended
order of events: adapters drive the specification, not the other way around.

## Also open: what CBD carries

Today the timeline holds vision, language, and kinematics. Behavior in the
physical world also involves forces: contact and impact events, grip and applied
force, torque and load, tactile and IMU readings, and material or strength
properties of the objects involved.

Whether these belong on the same timeline as first-class channels, or in a
separate layer referenced by timestamp, is an open schema question. It is worth
answering with a real sensor integration rather than in the abstract — the same
rule as the embodiment question: adapters drive the specification.

## After that

Ordered by what would teach us the most, not by effort.

The **Isaac adapter** that used to head this list has landed, and landed on
hardware ([`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/)): the
same dataset onto a Unitree G1, the machine NVIDIA GR00T drives, rendered in
Isaac Sim. A second simulator was the real test of engine independence and the
schema survived it — the adapter reads only `04_behavior_dataset/`, converts
frames once at its boundary, and needed no change to the representation. Going
straight to a *robot* rather than to a figure built from the subject's own
measurements made the test sharper: fixed link lengths and hard joint limits are
what say whether the representation carries enough. It does — but only for
kinematics, and the adapter is precise about the cost. The motion has to be
*solved* rather than copied, the set has to be scaled to the robot by a number
the schema cannot supply, and both ankle pitch joints sit on their limit for the
whole sample clip.

What it surfaced is four gaps worth taking to the schema. Canonical space
declares no real scale — and that is not merely unstated but load-bearing once a
1.32 m robot has to sit on furniture derived from a taller subject. Four bones
(`chest`, `neck`, and both shoulders) are always written as identity, so the
robot's waist moves in yaw only. An adapter that wants to place props in 3D has
to re-derive the image-to-canonical mapping itself from
`human/pose_landmarks.csv`. And the missing force and contact channels are
exactly what stands between a joint-space replay and a dynamically feasible G1
trajectory — the adapter writes a GR00T-LeRobot dataset a policy could be
trained on, and cannot say whether the robot could hold the pose. See
[specification → open questions](../specification/README.md#open-questions).

**v2 of that adapter took the last of those on** (`07_groot_g1_v2/`): the real
G1 asset, the capture corrected before it is retargeted, the trajectory driven
through PhysX and published as what came back, and the objects the clip acts on
placed rather than described. It narrows the schema request rather than
answering it. What is missing is not "force and contact" in general but three
specific things: a **validity signal on `phase`** (all 96 frames of the sample
read `Idle` while the wrist travels 0.31 → 0.55 m), a **support relation**
saying what the subject rests on and what rests on what, and **rotation for the
four bones that carry none** — the reason a reach to the subject's side comes
out as a reach to the robot's front, which is the single largest remaining
error in the output.

| Direction | Why it matters |
|---|---|
| **Schema extraction** | Turn "what the notebooks emit" into a validatable schema with a compatibility checker |
| **Object trajectory generation** | Demo B currently generates only the human body; behavior involving objects needs the objects |
| **LeRobot interoperability** | The most natural neighbour in the robot-learning ecosystem; a conversion in both directions would test the schema hard |
| **ROS 2 bridge** | Makes CBD reachable from existing robot stacks |
| **Blender / Unreal exporters** | Extends reach into content pipelines, and stresses the avatar side of the schema |
| **IK and retargeting library** | Shared machinery every embodiment adapter otherwise reinvents — `isaac_sim_groot_g1/` now has a working direction-matching solver, a contact-polygon foot solve and an object placement solver that the next embodiment should not have to rewrite |
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
