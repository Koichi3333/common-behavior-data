# Common Behavior Data — current representation

[← back to README](../README.md) · [Architecture](../docs/architecture.md) · [Limitations](../docs/limitations.md)

> **Status: experimental · evolving · adapter-driven · open to feedback**
>
> This is **not** a normative specification, and there is deliberately no
> "CBD Standard v1.0" here. This page describes what the reference
> implementation actually emits today, and marks what is still open.
>
> The schema is expected to change when a real adapter proves it should. If you
> are implementing against it, pin a `dataset_version` and expect breakage while
> the project is at `0.x`.

## Why no formal schema yet

Formalising a representation before it has survived contact with several
consumers produces a specification that is precise about the wrong things.

Three notebook adapters plus one learning consumer was not enough evidence, and
the fourth target proved it. [`isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/)
drives a **Unitree G1** — fixed link lengths, hard joint limits, no willingness
to be rebuilt to the subject's proportions — and it surfaced six gaps in this
representation that three human-shaped figures had absorbed silently. They are
listed in [`docs/compatibility_findings.md`](../docs/compatibility_findings.md)
and reflected in [open questions](#open-questions) below.

That is the intended order of events: adapters drive the specification. Had a
`v1.0` been published first, it would have been broken by the G1 run or the G1
case would have been bent to fit a human-shaped schema.

**Extracting a validatable schema and a compatibility checker is open work**,
and now has a non-human adapter's findings to be built against.

## Layout on disk

What Demo A produces, and what Demo B consumes:

```text
04_behavior_dataset/
├── manifest.json              index, fps, frame count, coordinate systems
├── behavior_summary.json      what happened, primary hand/object, events
├── runtime_info.json          how it was computed (delegates, GL backend, timing)
├── README.md                  generated, describes this dataset
│
├── timeline/
│   ├── frames.jsonl           ROW view: one line = one complete frame
│   └── frames/000000.jpg …    one image per analysed frame
│
├── human/                     COLUMN view of the body
│   ├── pose_landmarks.csv     33 landmarks, normalised + world + visibility
│   ├── hand_landmarks.csv     21 landmarks per hand
│   ├── face_landmarks.jsonl   478-point mesh (referenced, not inlined)
│   ├── face_blendshapes.csv   expression coefficients
│   ├── gestures.csv           recognised gesture per hand
│   ├── bone_rotations.csv     canonical quaternions, T-pose relative
│   └── joint_angles.csv       body joint angles + per-finger flexion, degrees
│
├── objects/
│   ├── object_detections.csv  raw detector output, never rewritten
│   ├── object_tracks.csv      tracked objects with role and motion state
│   └── label_reclassification.json   detector label → confirmed class mapping
│
├── interactions/
│   └── interaction_events.csv reach / contact / grasp / carry / release CANDIDATES
│
├── metrics/
│   ├── motion_metrics.csv     path length, speeds, smoothness, coverage
│   └── object_metrics.csv     object motion + interaction counts
│
├── quality/quality.json       per-modality coverage and notes
│
└── adapters/                  DERIVED, engine-specific
    ├── mujoco_qpos.csv
    ├── mujoco_object_trajectory.csv
    └── vrm_bone_rotations.csv
```

## Canonical vs adapter-specific

This distinction is the load-bearing one.

| | Canonical | Adapter-specific |
|---|---|---|
| Where | `human/`, `objects/`, `interactions/`, `timeline/` | `adapters/`, `02_mujoco/`, `03_unity_vrm/` |
| Coordinate frame | Y-up, right-handed, person faces +Z | the engine's convention |
| Regenerable | no — this is the master | yes, always, from canonical |
| Changes when | the representation evolves | an engine's conventions change |

Anything under `adapters/` can be deleted and rebuilt. Nothing under `human/`
can. If you are writing a consumer, read canonical data — reading another
engine's adapter output is how coupling creeps back in.

## The common timeline

Every record carries `frame`, `timestamp_ms` and `timestamp_sec`, derived from
one clock. During capture, all five MediaPipe tasks receive the *same*
timestamp; they are never allowed to drift into separate time bases.

This is what makes the following true of a single line of `frames.jsonl`:

```text
vision + language + motion + phase + objects + interactions   ← all at time t
```

Sampling is by timestamp, not frame index, wherever sources have different rates
— which is how the three-pane comparison video aligns a 12 fps analysis with a
30 fps Unity recording.

## `timeline/frames.jsonl`

One JSON object per line.

| Field | Meaning |
|---|---|
| `frame`, `source_frame_index` | index in the analysed sequence / in the source video |
| `timestamp_ms`, `timestamp_sec` | position on the common timeline |
| `frame_image` | relative path to that frame's image, or `null` |
| `human` | see below |
| `objects` | list of tracked objects visible at this frame |
| `interactions` | list of interaction **candidates** at this frame |
| `phase` | `{ action, phase, hand }` — the behavior state at this frame |
| `caption` | `{ window_index, en, ja, source }`, or `null` |

`human` contains:

| Field | Meaning |
|---|---|
| `bone_rotations_xyzw` | 19 bones, quaternion `[x, y, z, w]`, parent-relative, T-pose rest |
| `hips_position` | root translation in canonical space |
| `finger_curls_rad` | mean flexion per finger, per hand, or `null` |
| `joint_angles_deg` | elbow / knee / shoulder angles |
| `hands_canonical`, `pose_canonical` | landmark arrays in canonical space |
| `face_blendshapes` | expression coefficients, or `null` |
| `face_landmarks_ref` | pointer to `human/face_landmarks.jsonl` (size) |
| `gestures` | recognised gesture per hand |

## Language, motion and object alignment

- **Captions** are generated over windows that follow **behavior phase
  boundaries**, not a fixed clock — so one caption describes one action. The
  caption is then injected into every frame it spans, which is what makes a
  single line a complete training sample.
- **Phase** (`Idle` / `Reach` / `Grasp` / `Carry` / `Release`) is the state that
  ties language to motion. It is also the target of Demo B's phase head, and its
  observed transition matrix becomes a generation-time grammar.
- **Objects** carry `track_id` (stable across frames), `label` (confirmed class),
  `detector_label` (raw), `role` (`target` / `environment`), and a motion state.

## Observed vs generated

Generated datasets from Demo B use the **same schema** and the same adapters.
They are distinguished by content, not format:

- `manifest.json` records the `prompt`, `generation_seed`, `smoothing_alpha`,
  and whether the lower body was frozen
- each `frames.jsonl` line carries the prompt it was generated from
- generated data has no `frame_image` and no observation provenance

**Do not mix observed and generated episodes in a corpus without tracking
which is which.** The format will not stop you, and nothing downstream can tell
them apart — which is the demo's point and also its sharpest edge.

That sentence was a defect, not a caveat. "The format will not stop you" is
exactly what the [anti-fabrication rule](#position_source--the-anti-fabrication-rule-in-the-one-place-it-exists)
forbids everywhere else, and a corpus used for training is the worst place to
rely on a reader's discipline.

Since `0.3.0` the format does say: `manifest.json` → `provenance.episode_kind`
is `observed` or `generated`, and `generated_by` names the model when it is the
latter. A generated episode is still written in the same schema and still plays
through the same adapters — that remains the point — but a corpus can now be
sorted without trusting whoever assembled it. **Demo B does not set the field
yet**; the learning prototype lives in a notebook that this change did not
touch.

## Raw vs derived

Raw observation is never overwritten.

- `objects/object_detections.csv` keeps every detection exactly as the detector
  produced it, including labels later corrected by re-classification
- `pose_landmarks.csv` keeps both normalised and world landmarks plus
  `visibility` / `presence`
- smoothing, interpolation and canonicalisation produce *additional* series

If a consumer disagrees with a derived value, the input it came from is present.

## Provenance and quality

| File | Answers |
|---|---|
| `runtime_info.json` | which delegate and GL backend actually ran, how long it took, achieved fps |
| `quality/quality.json` | per-modality coverage, missing-frame ratio, notes |
| `objects/label_reclassification.json` | every detected label, what it became, why, and what was excluded |
| `captions/temporal_captions.json` | which model generated the captions, and that they are not ground truth |
| `manifest.json` | fps, frame count, coordinate systems, which tasks ran — and since `0.3.0` the `provenance` block: episode kind, source terms, and a tier per channel |
| `quality/channel_provenance.json` | the per-channel ledger on its own (`0.3.0`) |

### `position_source` — the anti-fabrication rule, in the one place it exists

Any derived 3D object position carries how it was obtained:

| Value | Meaning |
|---|---|
| `detected_2d` | from an actual detection this frame |
| `estimated_from_hand` | object is being carried; follows the wrist |
| `estimated_from_hand_occlusion` | carried and not detected this frame |
| `last_known_position` | not visible, not carried — held, not interpolated |
| `projected_to_plane` | projected onto an assumed support plane |
| `fixed_depth_proxy` | depth is a constant assumption |

A consumer that needs measured positions can filter on this. A consumer that
does not check is at least not being lied to.

### Generalising it

`position_source` is the right idea applied to one field. Every other channel in
canonical CBD is written without it, and the consequences are measurable:

| Channel | What it looks like in the shipped sample | What a consumer cannot tell |
|---|---|---|
| `human/bone_rotations.csv` | `chest`, `neck`, `left_shoulder`, `right_shoulder` identity in all 96 frames (4 of 19) | "the torso was still" from "nothing measured the torso" |
| `phase` | `("Pick And Place", "Idle", "Right")` in all 96 frames of a pick-and-place clip | a real idle from a field that was never populated meaningfully |
| `interaction_events.csv` | header, zero rows | "no contact" from "the detector produced nothing" |
| `quality/quality.json` | `object_coverage: 1.0` while 1 of 173 per-frame object entries carries a 3D position | 2D detection coverage from 3D position availability |
| canonical units | metre-ish numbers from monocular estimation | an estimate from a measurement |
| the episode itself | no field for source terms, or for observed vs generated | a recording from a model's output |

The proposal is one vocabulary, declared per channel, used on both sides of the
adapter boundary:

| Tier | Meaning |
|---|---|
| `measured` | the source actually carried it |
| `derived` | computed from something measured |
| `estimated` | inferred under a model or assumption (monocular depth) |
| `prior` | a class-level constant (catalog, anthropometry) |
| `synthesized` | authored to keep a consumer self-consistent |
| `degenerate` | written, but carrying no information |
| `absent` | not written at all |

**None of this vocabulary is new** — which is the argument for it. The G1
adapter already implements five of the tiers in
[`provenance.py`](../adapters/isaac_sim_groot_g1/provenance.py), with
`unavailable` (= `absent` here) defined as *"nothing filled it — a defect, not
an outcome"*, weighted by channels × frames, and checked against a 70 %
evidence floor because *"Below the floor the run is not evidence any more."*
`estimated` is the distinction `position_source` already draws. And `degenerate`
is the adapter's word too: [`phases.py`](../adapters/isaac_sim_groot_g1/phases.py)
documents *"canonical phase is degenerate (one label for every frame)"* and
tests for it with `cbd_phase_is_informative()`.

Every one of those distinctions was invented downstream, by a consumer that
needed it and could not get it from the data.

Two things follow, and the second is a defect worth stating plainly:

1. **It belongs upstream.** A generator knows at write time whether it measured
   a channel; an adapter can only guess afterwards, per target, by hand.
2. **Target-side instrumentation grades what the target touched.** As shipped,
   the G1 ledger holds four entries — the legs it solved, two object placements,
   one wrist repair — totalling 1251 weight units against a 43-joint × 96-frame
   trajectory (4128 joint-frames), and reports *"measured+derived 99.8% >= floor
   70%"*. The retargeted arm, torso and waist joints are not in it, and
   `measured` reads `0.0000` because the shipping path reaches no `measured`
   call site. The floor passes at 99.8 % over roughly 30 % of the output.

#### What `0.3.0` actually writes

[`generators/video_to_cbd/`](../generators/video_to_cbd/) now answers the
question at write time, which is the only place it can be answered without
guessing. **Additive only** — every `0.2.0` field is still written, unchanged,
so an existing consumer keeps working.

| Where | What |
|---|---|
| `manifest.json` → `provenance` | the whole ledger: `episode_kind` (`observed` / `generated`), `generated_by`, `source` (`terms`, `redistributable`, `attribution`), the tier definitions, per-channel entries, and the `degenerate` / `absent` lists |
| `quality/channel_provenance.json` | the same ledger on its own, for a consumer that wants only this |
| `human/bone_rotations.csv` → `provenance` column | appended, so a reader of that file alone can tell a still bone from an unobserved one |
| `quality/quality.json` | `coverage_definitions` (what each number counts), `object_position_3d_coverage` (the 3D number, beside the 2D one), `degenerate_channels`, `absent_channels`, and `notes` naming each degenerate channel |

Two rules the generator holds itself to, and they matter more than the field
names:

1. **Tiers are measured, not asserted.** `degenerate` comes from testing the
   series — `prov_is_constant()` over the clip — so it stays correct if the
   construction changes. The four torso bones are flagged because they *are*
   constant, not because they are on a list.
2. **The ledger covers every channel the dataset writes**, including the ones
   that are not there: `camera_intrinsics`, `support_relation`,
   `contact_and_force` and `finger_bone_rotations` each get an `absent` entry
   with the reason. A ledger that grades a subset and publishes a total is worse
   than no ledger.

On this repository's own sample the generator now reports five degenerate
entries — `phase`, and `chest` / `neck` / `left_shoulder` / `right_shoulder` —
and eight absent channels.

**Status: implemented in the generator, not yet consumed.** What remains:

- **No adapter reads it yet.** `isaac_sim_groot_g1/` still detects a degenerate
  `phase` itself; it should trust the field and keep its test as a fallback.
- **The tier names are not fully reconciled** across the boundary: the generator
  writes `absent`, the adapter's ledger calls the same thing `unavailable`, and
  the adapter's `synthesized` has no generator-side meaning (by design — a
  generator that authors a value to satisfy a target is doing an adapter's job).
- **The committed sample output is a `0.2.0` bundle** and carries none of these
  fields; it predates the change and is not regenerated here. The figures above
  are what the current generator produces from it, not what the file contains.
- **A validator** — "does this bundle declare provenance for every channel it
  writes?" — does not exist. That is the check that would make the rule
  enforceable rather than aspirational.

## Interaction candidate vs ground truth

`interaction_events.csv` and the per-frame `interactions` list contain
**candidates**, produced by a distance-and-gesture state machine with
hysteresis. They are useful as weak labels and as an index into a clip. They are
not annotations.

The naming is intentional and should be preserved by any adapter: a field named
`grasp_candidate` cannot be silently promoted to `grasp` downstream.

## Engine independence

The rules that keep the representation from becoming a MuJoCo file with extra
steps:

1. Canonical data is stored in one frame (Y-up, right-handed, +Z forward)
2. Engine conversion happens **only** at the adapter boundary
3. Model and motion stay in separate files (`humanoid.xml` ↔ `motion.npz`,
   `avatar.vrm` ↔ `motion.vrma`)
4. Bone rotations are relative to a T-pose rest, so a skeleton authored at zero
   rotation needs a coordinate transform and nothing else
5. No adapter reads another adapter's output

## What gets into the representation

The schema changes because an adapter proved it should — never because one
adapter found it convenient. A finding takes this route:

```text
Adapter finding
      ↓
Specification feedback      ← docs/compatibility_findings.md
      ↓
Generality evaluation       ← the test below
      ↓
Specification update
```

The generality test, applied before anything is added:

| Add it if | Do **not** add it if |
|---|---|
| several targets need it | only one robot needs it |
| it describes the **behavior itself** | it describes a **runtime's API** |
| it can be observed or derived from the source | it can only be supplied by the target |
| it is reusable for more than one purpose | it is a particular robot's joint names |

Worked examples, all three from the G1 run:

- **Support relation** — nothing in canonical CBD says what the subject rests on.
  Every seated or surface-contact behavior needs it, any target with gravity
  needs it, and it is derivable from the source. **Candidate for the schema.**
- **Per-channel provenance** — the adapter defined a tier vocabulary and an
  evidence floor to grade its own output, and every other target needs the same
  thing to know what it is standing on. It describes the behavior record rather
  than any runtime's API, and the generator knows the answer at write time.
  **Passes the test; now the next step.**
- **Ankle pitch running out of travel** — real, measured, and reported in the
  adapter's own report. But it is a fact about a 1.32 m robot's hardware, not
  about the behavior. **Stays in the adapter.**

When the answer is "stays in the adapter", the constraint is still
[published as a number](../docs/compatibility_findings.md#target-constraints--reported-not-fixed)
rather than silently approximated. Reporting it is not the same as encoding it
here.

## Open questions

**One item left this list.** Per-channel provenance — generalising
`position_source` — is no longer undecided; it is the
[next step](../docs/roadmap.md#next-in-band-provenance), for the reasons in
[concept](../docs/concept.md). What is still open about it is narrower: the tier
names on the two sides of the adapter boundary, whether provenance rides on each
frame or in a per-channel manifest, and how a `degenerate` channel is detected
by the generator rather than asserted by hand.

Genuinely undecided, and good places to argue:

- **Behavior intent as a first-class element.** Currently intent is implicit in
  `phase` plus human joint motion. Re-embodiment needs it separable.
- **Object representation.** Class + track + proxy position is thin. Pose?
  Affordances? Articulation? Contact points?
- **Adapter contract.** What must a consumer find, how does it declare what it
  uses, how does it report what it could not represent?
- **Force and contact channels.** Grip force, torque, impact, tactile and IMU
  streams, material properties — same timeline as first-class channels, or a
  separate layer joined by timestamp?
- **Multi-person and multi-agent.** Interaction between people is behavior too.
- **Versioning and migration.** `dataset_version` exists; migration tooling does
  not.
- **Validation.** What does "a valid CBD dataset" mean, mechanically?
- **Units and scale.** Canonical space is metre-ish but derived from monocular
  estimation; how should real scale be declared when it is known?

If you have an opinion on any of these — especially one grounded in a system you
actually maintain — open a [Discussion](https://github.com/Koichi3333/common-behavior-data/discussions).

---

**See also:** [Architecture](../docs/architecture.md) · [Limitations](../docs/limitations.md) · [Contributing](../CONTRIBUTING.md)
