# Limitations

[← back to README](../README.md)

This page exists because the fastest way to lose a technical reader's trust is
to make them discover a limitation themselves. Everything below is a real
constraint of what is in this repository today.

## Claims this project does **not** make

- ❌ CBD is an established standard, or has industry adoption
- ❌ The schema is complete or stable
- ❌ Demo B is a general-purpose VLA
- ❌ The VLA reaches objects precisely on its own, without outside guidance
- ❌ Arbitrary natural language works
- ❌ Video directly trains a robot
- ❌ Human motion transfers directly to a robot
- ❌ Physical grasping is solved
- ❌ Sim-to-real works
- ❌ Robot task success has been demonstrated

None of these have been shown here, and the repository is written so that no
sentence implies them.

## Demo A — Human Capture

| Limitation | Detail |
|---|---|
| **Single person** | The pipeline assumes one subject. With several people in frame it follows the largest detection. |
| **Monocular depth** | 3D object positions are estimates from a single camera plus heuristics. Every derived position carries a `position_source` field naming how it was obtained. |
| **Interaction candidates** | `reach` / `contact` / `grasp` / `carry` / `release` come from a distance-and-gesture state machine with hysteresis. They are **heuristic candidates, not ground truth**, and the column names keep the word *candidate*. |
| **Kinematic replay** | The MuJoCo output is `qpos` assignment plus `mj_forward`. No contact, no forces, no dynamics. It proves the motion transferred, not that it is physically valid. |
| **Finger angles** | Approximated as per-finger curl from MediaPipe hand landmarks. Not accurate per-joint angles. |
| **Fixed vocabularies** | Gesture and object detection are limited to the pretrained models' classes (COCO-80 for objects). Custom objects are unsupported. |
| **Captions are AI-generated** | Temporal captions come from the Gemini API and are descriptions, not verified annotations. The model that produced them is recorded in the dataset. |
| **Face mesh often absent** | Face landmarks depend on the subject's distance and framing; `quality.json` records the coverage that was actually achieved. |

### An honest example

The sample output shipped in
[`examples/human-capture/sample_output/`](../examples/human-capture/sample_output/)
contains **zero interaction events**, and every frame's phase is `Idle`.

The cup in that clip was detected in only one frame, so the interaction state
machine never fired. The person is visibly picking up and drinking from a glass.

That is not a bug we hid — it is exactly why interactions are labelled
candidates and why `quality.json` exists. A single missed detection changes the
behavioral reading of a clip, and any downstream system needs to know that.

**But the dataset does not actually say so, and that is the sharper
limitation.** The empty event table reads as "no contact occurred"; 96 frames of
`Idle` read as "nothing happened"; `quality/quality.json` reports
`object_coverage: 1.0` for the clip in which that cup was detected once. A
consumer reading only the data draws the wrong conclusion and has no way to
detect it. The same holds for the four bones — `chest`, `neck` and both
shoulders are identity in every frame, which is indistinguishable from a
motionless torso. `position_source` is the one field in the whole
representation that avoids this, and
[generalising it](../specification/README.md#generalising-it)
is the next step on the [roadmap](roadmap.md#next-in-band-provenance).

## Demo B — Language to Motion

The critical framing, repeated from the README and the notebook:

> At the current scale this is a **small VLA-like learning prototype**
> demonstrating memorisation, interpolation, and language-conditioned behavior
> generation. It is not a general-purpose VLA.

| Works today | Does not work |
|---|---|
| Regenerating a learned behavior from a prompt close to its caption | Unseen instructions ("with your left hand", "wave both arms") |
| Selecting between 2–3 learned behaviors by instruction | Non-English prompts (training captions are English) |
| Grammatically valid phase sequences (Idle → Reach → Grasp → Carry → Release → end) | Object trajectory generation — output is the human body only |
| Conditioning on a frame image from the training episodes | Physically consistent contact or grasping |

Additional constraints:

- **Lower body is frozen by default** (`FREEZE_LOWER_BODY = True`). The current
  corpus is seated video where the legs are occluded, so the model would
  faithfully learn the estimation noise. This is a training-data problem, not an
  accuracy problem, and the flag is documented in the notebook and recorded in
  the generated `manifest.json`.
- **Scale estimate.** Early signs of interpolation appear around 10 episodes.
  Anything resembling generalisation needs roughly 100 episodes of the same task
  family. Real generalisation needs orders of magnitude more, plus a proper
  video encoder.
- **Generated motion is smoothed** after sampling. The raw autoregressive output
  has per-frame jitter; `GEN_SMOOTHING_ALPHA` is a post-process, and it is
  recorded in the manifest.

## The representation itself

- **The schema is unstable.** It will change, and changes will not always be
  backward compatible while the project is at `0.x`. See
  [`specification/README.md`](../specification/README.md).
- **There is no standalone schema file yet.** The representation is currently
  defined by what the notebooks emit. Extracting a validatable schema is
  explicitly open work.
- **No versioned compatibility guarantees.** `manifest.json` carries a
  `dataset_version`, but there is no migration tooling.
- **Object semantics are thin.** Objects have a class, a track, a role and a
  proxy position. No affordances, no pose, no articulation.
- **Behavior intent is not yet represented separately from motion.** This is the
  gap the re-embodiment experiment is designed to expose, since intent is the
  part that should survive a change of embodiment.
- **No force, contact or tactile channels.** The timeline carries vision,
  language and kinematics only. Grip force, torque, impact and material
  properties are not represented, and whether they belong on the same timeline
  is undecided — see [Roadmap](roadmap.md#also-open-what-cbd-carries).
- **Provenance is declared but not yet consumed.** Since dataset version
  `0.3.0` the generator writes a tier for every channel — including `degenerate`
  for a field that is populated and uninformative, and `absent` for a channel
  that does not exist — plus `episode_kind` for observed vs generated. **No
  adapter reads any of it**, there is no validator, and the producers of
  generated CBD (Demo B, and the VLA repository) do not set `episode_kind`.
  Separately, the G1 adapter's own provenance ledger covers roughly 30 % of the
  trajectory it ships while reporting a pass over the whole of it — see
  [findings](compatibility_findings.md) and
  [Roadmap](roadmap.md#next-in-band-provenance).

## Known inconsistencies

Recorded rather than hidden:

- The **committed sample output is a `0.2.0` bundle** and carries none of the
  `0.3.0` provenance fields: no per-channel tiers, no `episode_kind`, no
  `provenance` column in `bone_rotations.csv`. Regenerating it needs a Colab
  run, so the repository's own showcase still demonstrates the old behaviour.
  Figures quoted elsewhere about what the generator *now* reports for this clip
  were produced by running the current code against it, not read out of the
  committed files.
- The **sample output was generated by an earlier run** of Demo A. Its
  `captions/temporal_captions.json` uses fixed-width windows
  (`window_seconds: 5`), whereas the current notebook segments captions at
  behavior-phase boundaries and records `window_basis`. The data is otherwise in
  the current format.
- **`face_landmark_count` is 0** in the sample dataset: the face task ran but
  detected nothing at that framing, which `quality.json` reports as
  `face_coverage: 0.0`. This is the one case where the quality file does its job.
- **`object_coverage: 1.0` in the same file is misleading.** It reports that
  objects were detected in every frame — 2D presence — while exactly 1 of 173
  per-frame object entries carries a 3D position, and that one is
  `proxy_canonical: [NaN, NaN, 0.3]`. A consumer reading the field name expects
  3D availability. The number is not wrong for what it measures; the name is
  wrong for what a consumer will do with it.

## Reporting more

If you find a claim in this repository that the code does not support, that is a
bug worth filing. Open an [issue](https://github.com/Koichi3333/common-behavior-data/issues) — corrections to the honesty of
the documentation are as welcome as code.

---

**See also:** [Roadmap](roadmap.md) · [Specification](../specification/README.md)
