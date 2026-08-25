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

Two adapters (MuJoCo, VRM) plus one learning consumer is not enough evidence.
The [SO-101 experiment](../docs/roadmap.md#next-so-101-pick--place) is expected
to change the schema, because a robot arm has none of the human joints the
current representation is built around. Publishing a `v1.0` first would mean
either breaking it immediately or bending the robot case to fit a human-shaped
schema.

**Extracting a validatable schema and a compatibility checker is open work.**
It is a good contribution, and it should follow at least one non-human adapter.

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
| `manifest.json` | fps, frame count, coordinate systems, which tasks ran |

### `position_source` — the anti-fabrication rule

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

## Open questions

Genuinely undecided, and good places to argue:

- **Behavior intent as a first-class element.** Currently intent is implicit in
  `phase` plus human joint motion. Re-embodiment needs it separable.
- **Object representation.** Class + track + proxy position is thin. Pose?
  Affordances? Articulation? Contact points?
- **Adapter contract.** What must a consumer find, how does it declare what it
  uses, how does it report what it could not represent?
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
