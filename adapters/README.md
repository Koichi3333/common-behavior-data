# `adapters/` — Use CBD somewhere

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md) ·
[Findings](../docs/compatibility_findings.md)

**What is this?** The half of the pipeline that *consumes* Common Behavior
Data. An adapter reads canonical CBD and makes it usable in one specific place —
a simulator, an engine, a robot, a dataset format.

| | |
|---|---|
| **Input** | Canonical CBD — `04_behavior_dataset/`, or `cbd_dataset.zip` straight from the generator |
| **Output** | Whatever the target needs, plus a report of what could **not** be represented |
| **Purpose** | Prove the representation is portable — and measure exactly where it is not |
| **Related** | [`generators/`](../generators/) write what these read · [`showcase/`](../showcase/) shows the results · [findings](../docs/compatibility_findings.md) collects what broke |

**One subdirectory per target. Each is self-contained.**

## The four targets today

| Adapter | Target | Form | Where it runs |
|---|---|---|---|
| [`mediapipe_overlay/`](mediapipe_overlay/) | annotated video on the original pixels | notebook | Colab — CLI |
| [`mujoco/`](mujoco/) | MuJoCo humanoid — `humanoid.xml` + `motion.npz` | notebook | Colab — CLI |
| [`unity_vrm/`](unity_vrm/) | Unity / VRM 1.0 — `motion.vrma` | notebook | Colab writes it, Unity plays it |
| [`isaac_sim_groot_g1/`](isaac_sim_groot_g1/) | **Unitree G1 as NVIDIA GR00T drives it** — 43-DoF joint space, OpenUSD, GR00T-LeRobot | Python package | retarget anywhere; **render needs a GPU VM** |

The first three animate a figure built to the subject's own proportions, and
they run in Colab. The fourth drives a machine whose proportions are not
negotiable, and it does not fit in Colab — see
[where things run](#where-these-run) below.

Every one of them reads canonical CBD and **nothing else** — never another
adapter's output. That is the property the split exists to test: adding a target
should mean adding one directory here, and touching no generator.

## `isaac_sim_groot_g1/` — the one that hurts, and is therefore the useful one

The notebook adapters answer an easy question: *can canonical CBD drive a figure
built to the subject's own measurements?* [`isaac_sim_groot_g1/`](isaac_sim_groot_g1/)
asks the hard one: **can it drive a machine?**

Three consequences follow from the target being hardware:

- **The motion is solved, not copied.** Per-frame damped least squares matching
  segment *directions* under the URDF's joint limits, because a fixed-length
  limb cannot reproduce a reach measured in metres. Residual: **6.87° mean**
  across all segments.
- **The set is scaled to the robot**, not the robot to the subject — by one
  reported number (`scale`: 0.835 in v1, 0.685 in v2, which anchors it on the
  robot's own geometry instead of the subject's). Stretching a G1 would be a
  fabrication about hardware.
- **What is left over is published as numbers**, including every joint that ends
  up resting on a limit. On the sample clip: both ankle pitch joints, in all 96
  frames.

v2 went further — NVIDIA's own G1 asset referenced rather than approximated, the
capture corrected before retargeting, the trajectory driven through **PhysX** and
published as `q_actual` (what came back) rather than `q_target` (what was asked),
and the objects the clip acts on placed as physical props. It also writes a
**GR00T-LeRobot v2.1 dataset** in the Isaac Lab Arena G1 modality — what a GR00T
G1 policy is post-trained or replayed on. It does not run one, and
`adapter_report.json` says `"policy_was_run": false`.

Output: [`examples/human-capture/sample_output/07_groot_g1_v2/`](../examples/human-capture/sample_output/07_groot_g1_v2/)
· video in [`showcase/video_to_isaac_g1/`](../showcase/video_to_isaac_g1/)
· full write-up in [`isaac_sim_groot_g1/README.md`](isaac_sim_groot_g1/README.md).

## Where these run

| Adapter | Environment |
|---|---|
| `mediapipe_overlay/`, `mujoco/` | Colab (CLI recommended), same session as the generator |
| `unity_vrm/` | Colab writes the files; Unity plays them on your own machine |
| `isaac_sim_groot_g1/` — retarget, compose | any machine, plain Python (`numpy`, `usd-core`, `pyarrow`) |
| `isaac_sim_groot_g1/` — **render, PhysX** | **Google Compute Engine, `g2-standard-16`, 1 × NVIDIA L4**, Isaac Sim 6.0 in the NGC container |

**The repository rule:** *Colab CLI where the target allows it; a documented
machine where it does not.* Isaac Sim is the one exception — it needs an RTX GPU
Colab does not expose, a container measured in tens of gigabytes, and a shader
cache that survives between runs. Its README states the machine at the top, and
its outputs are committed so the result can be read without ever touching a GPU.

Details and the rule for new targets:
[`docs/runtime_environments.md`](../docs/runtime_environments.md).

## Running the three notebook adapters

They chain off the generator through `cbd_dataset.zip`. Every one looks for its
input in the same order — the dataset already unpacked in this runtime, then
`/content/cbd_dataset.zip`, then the upload widget (UI only) — so the
**recommended way is the Colab CLI, in the same session the generator ran in**:

```bash
# same session as the generator — nothing to upload
colab exec -s cbd -f mediapipe_overlay/cbd_adapter_mediapipe_overlay.ipynb --timeout 1800
colab exec -s cbd -f mujoco/cbd_adapter_mujoco.ipynb                       --timeout 1800
colab exec -s cbd -f unity_vrm/cbd_adapter_unity_vrm.ipynb                 --timeout 900

colab download -s cbd \
  /content/human_behavior_demo_2_0/mujoco_adapter_output.zip ./mujoco_adapter_output.zip
```

A fresh session works just as well — hand it the zip first:

```bash
colab upload -s cbd2 ./cbd_dataset.zip /content/cbd_dataset.zip
colab exec   -s cbd2 -f mujoco/cbd_adapter_mujoco.ipynb --timeout 1800
```

`isaac_sim_groot_g1/` takes the same zip directly, no unpacking needed:

```bash
python isaac_sim_groot_g1/cbd_adapter_groot_g1.py --dataset ./cbd_dataset.zip
```

## Self-contained beats DRY

**An adapter keeps its own machinery, even when another adapter has something
that looks the same.** Retarget, cleanup, joint mapping, joint limits,
continuity, contact, collision, support, object placement, physics, validation,
provenance, deviation, reporting — all of it lives inside the adapter that needs
it.

When the G1 adapter found that a four-point foot contact polygon fixes ground
penetration that a single point silently misses, the fix did **not** move to
`tools/common_foot_contact.py` for everyone to import. It stayed in
`isaac_sim_groot_g1/`, and the *idea* was written down in
[findings](../docs/compatibility_findings.md) for the next legged target to
implement in its own terms.

Why, concretely:

- physics assumptions differ per simulator; body structure differs per robot
- a contributor can read and change one adapter without understanding the rest
- a shared helper has to be correct for every target at once, and quietly
  becomes wrong for each
- an adapter you can lift out and hand to someone is worth more than a
  deduplicated one you cannot

**Portability and readability of an adapter beat code DRY.** Share knowledge,
not implementations.

## But share what you learned

Code stays local. Findings do not. Every adapter README or report should say:

```text
What worked
What broke
What was corrected
Why it was corrected
How much it changed
What remains unresolved
```

and should distinguish these four, because they have different owners — and
first of all which **kind of gap** it is: a *data gap* the record could carry,
or a *body gap* where your target and the subject genuinely disagree
([the distinction](../docs/concept.md#the-problem)):

| Class | Gap | Owner |
|---|---|---|
| Source / capture issue | data | recapture, or generator robustness |
| **Generator issue** — the channel exists but is empty or wrong | data | [`generators/`](../generators/) |
| **Specification gap** — canonical CBD has no such channel | data | [`specification/`](../specification/), after a generality check |
| **Target constraint** — this target simply cannot | **body** | nobody. It stays here, and is **reported as a number** |

Getting this wrong is the common failure: a body gap filed upstream asks the
schema to fix a robot's hardware, and a data gap absorbed quietly in an adapter
means the next target rediscovers it from scratch.

The register: [`docs/compatibility_findings.md`](../docs/compatibility_findings.md).

## What belongs here

Anything that **reads** Common Behavior Data and converts it for a specific
engine, embodiment, or format.

| Target | Today |
|---|---|
| MediaPipe overlay video | Available — [`mediapipe_overlay/`](mediapipe_overlay/) |
| MuJoCo (`humanoid.xml` + `motion.npz`) | Available — [`mujoco/`](mujoco/) |
| Unity / VRM (`motion.vrma`) | Available — [`unity_vrm/`](unity_vrm/) |
| Isaac Sim / GR00T, Unitree G1 (43-DoF, OpenUSD, GR00T-LeRobot) | Available — [`isaac_sim_groot_g1/`](isaac_sim_groot_g1/) |
| Dataset views (`frames.jsonl` + CSVs) | Available — written by the generator, read directly |
| Other robot embodiments (e.g. SO-101) | Planned |
| LeRobot · ROS 2 · Blender / Unreal | Planned |

## Rules for an adapter

From [`CONTRIBUTING.md`](../CONTRIBUTING.md), unchanged:

1. **Read canonical data**, not another adapter's output
2. **Convert coordinates at your boundary** — canonical is Y-up, right-handed,
   person facing +Z
3. **Keep model and motion separate** where the target format allows it
4. **Do not promote candidates** — `grasp_candidate` must not become `grasp`
5. **Report what you could not represent**, rather than silently approximating
6. **Preserve provenance** — if you derive a position, say how

And three from the structure of this directory:

7. **Stay self-contained.** Do not factor your machinery into a shared library
   for other adapters to import.
8. **State where you run**, at the top of your README, if you do not run in
   Colab.
9. **Grade your own output** — and grade *all* of it. Tag every quantity you
   write with where it came from, and publish each deviation as
   `asked` / `got` / `error` / `tolerance` in the target's own units.
   `isaac_sim_groot_g1/` does this in [`provenance.py`](isaac_sim_groot_g1/provenance.py)
   and [`deviation.py`](isaac_sim_groot_g1/deviation.py) — and is also the
   cautionary example: its shipped ledger instruments only the quantities it
   *corrected*, about 30 % of the trajectory, while reporting its 70 % evidence
   floor as passed. A ledger that grades a subset and publishes a total is worse
   than no ledger, because it reads as a clean bill of health.

If a rule blocks you, that is interesting: it probably means the schema is
missing something. Open an issue.

Rule 6 is currently the hardest one to obey, because canonical CBD gives you
almost nothing to preserve: `position_source` is the only provenance it carries.
[Generalising that](../specification/README.md#generalising-it)
is the next step on the [roadmap](../docs/roadmap.md#next-in-band-provenance), and
it exists because rule 9 made the gap measurable.

## Open design question

The adapter *contract* is not formalised yet — what a consumer is guaranteed to
find, how it declares which parts it uses, and how it reports what it dropped.
The `adapter_report.json` every adapter here writes is a first, informal answer
to the last part of that. `provenance.py` goes one step further with
`spec_feedback()` — a `spec_gap` tag on any fill that exists only because the
schema has no channel for it — but exactly one call site sets it, so the shipped
report's `spec_feedback` is `{}`. The mechanism for an adapter to talk back to
the specification exists and is unused; formalising and using it is part of the
[next roadmap step](../docs/roadmap.md#next-in-band-provenance).
See [Architecture → what the adapter interface has to become](../docs/architecture.md)
and [Specification → open questions](../specification/README.md#open-questions).
Adapters drive the specification here, not the other way around.
