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
- **CBD → VLA → CBD** — an [experiment](../experiments/) in its own repository,
  [`vla-maker-from-cbd`](https://github.com/Koichi3333/vla-maker-from-cbd): NVIDIA
  GR00T N1.7 fine-tuned on CBD, emitting CBD, so its motion reaches the MuJoCo
  humanoid and the G1 through the existing adapters with no per-body retraining.
  **Kinematic evaluation only; precise reaching needs outside guidance (0.93
  guided vs 0.51 alone); non-commercial weights**

## Next: in-band provenance

**The step before everything below.** Canonical CBD describes behavior
confidently and says almost nothing about how much of it was observed. The G1
adapter had to answer that question for itself, and built the machinery to do
it: a five-tier provenance ledger, a degeneracy test, and a 70 % evidence floor
that fails its own run
([`provenance.py`](../adapters/isaac_sim_groot_g1/provenance.py),
[`phases.py`](../adapters/isaac_sim_groot_g1/phases.py)).

That machinery is right, private to one target, and incomplete — as shipped it
holds four entries totalling 1251 weight units against a 43-joint × 96-frame
trajectory (4128 joint-frames), instruments only the quantities that stage
corrected, and reports *"measured+derived 99.8% >= floor 70%"* over that subset.
`measured` reads `0.0000` because the shipping path reaches no `measured` call
site, not because the dataset was weighed. **A check that grades about 30 % of
the output and publishes a pass** is exactly the defect class this repository
already caught in a foot solve; this time it is in our own instrumentation.

**The generator half has landed.** Dataset version `0.3.0` from
[`generators/video_to_cbd/`](../generators/video_to_cbd/) writes a tier for
every channel it produces — `measured` / `derived` / `estimated` / `prior` /
`degenerate` / `absent` — into `manifest.json`,
`quality/channel_provenance.json` and a `provenance` column in
`human/bone_rotations.csv`, plus `episode_kind` (`observed` / `generated`) and
the source's terms. Tiers are measured from the series rather than asserted, and
the ledger covers every channel including the absent ones. On this repository's
own sample it reports five degenerate entries and eight absent channels. See
[specification → generalising it](../specification/README.md#generalising-it).

What this step still is:

- **An adapter that reads it.** Nothing consumes the field yet.
  `isaac_sim_groot_g1/` still detects a degenerate `phase` itself; it should
  trust the declaration and keep its own test as a fallback. Until a consumer
  depends on it, the ledger is a claim rather than a contract.
- **A validator.** *"Does this bundle declare provenance for every channel it
  writes?"* — the check that makes the rule enforceable instead of aspirational.
  It belongs in [`tools/`](../tools/), which already lists validation as its
  own.
- **Reconcile the two vocabularies.** The generator writes `absent`; the
  adapter's ledger calls the same thing `unavailable`. One of them has to move.
- **Regenerate the sample output.** The committed bundle is `0.2.0` and carries
  none of this, so the repository's own showcase still demonstrates the old
  behaviour. Needs a Colab run.
- **Producers that set `episode_kind`.** The field exists; the two things that
  emit generated CBD do not write it. Demo B's notebook is untouched, and
  [`vla-maker-from-cbd`](https://github.com/Koichi3333/vla-maker-from-cbd)
  trains on CBD and emits CBD with a redistribution ban
  (*"AMASS-derived motion data must never be redistributed"*) that its bundles
  still cannot state about themselves.
- **A ledger that covers what it grades.** Instrument the quantities taken
  straight from the dataset, not only the ones a stage corrected, so the
  evidence floor measures the output rather than a subset of it. This is a
  defect in [`isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) today and a
  requirement on any contract that replaces it.
- **Carry `spec_feedback` through.** `provenance.py` implements it — a
  `spec_gap` tag on a fill that exists only because the schema has no channel for
  it — and exactly one call site sets it, so the shipped report's
  `spec_feedback` is `{}`. Tag the fills that qualify, and give the channel a
  consumer upstream.
- **Fix `quality.json` where it overstates.** `object_coverage: 1.0` on a clip
  with one 3D object position is worse than no number at all.

Why first, and why now:

- it needed **no GPU and no new target** — a generator and schema change,
  runnable where the pipeline already runs, which is why it went first
- it turns [the findings register](compatibility_findings.md) from prose into
  something a consumer can check, which is the only way those findings reach
  anyone who does not read this repository
- everything after it is more trustworthy for having it: a policy trained on a
  corpus that cannot distinguish a measurement from a derived guess will still
  produce a number, and that number will not mean anything

What it is **not**: a validation framework, a formal schema release, or a version
1.0. It is the honesty the representation already claims, written where a machine
can read it.

## Then: re-embodiment

The most important open question is not capture quality or model size. It is:

> **Does behavior intent survive a change of embodiment?**

**Half of this has now been answered.** The G1 adapter above took canonical CBD
onto a machine whose proportions are not negotiable, and the representation
carried — for *kinematics*, at a stated cost, with the residuals published. What
it did **not** answer is the half that matters most, because the adapter runs no
policy: it writes a dataset a policy could be trained on and never asks the
robot to accomplish anything. The success criterion below is still unmet.

**A policy has now been run — but not on this question yet.**
[`vla-maker-from-cbd`](https://github.com/Koichi3333/vla-maker-from-cbd) trains a
VLA on CBD and has it reach for objects: the hand reaches the object in 0.93 of
held-out trials with an outside planner guiding it, 0.51 without. That is
kinematic MuJoCo on a human-shaped body, and its G1 output so far is generated
walking, not a task. It moves the question from *can a policy learn from CBD* —
yes, at a measured cost — to *can it complete a task on a body unlike the
human, under physics*, which is still open.

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
Task success     ← still open: no policy has completed a task under physics
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

What it surfaced is four **data gaps** worth taking to the schema — gaps in the record, not places where the two bodies disagree. Canonical space
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
| **LeRobot interoperability** | The most natural neighbour in the robot-learning ecosystem; a conversion in both directions would test the schema hard. CBD → LeRobot already exists twice, in the G1 adapter and in the VLA repository; the reverse does not |
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
