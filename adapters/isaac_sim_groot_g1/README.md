# `adapters/isaac_sim_groot_g1/` — CBD to GR00T / Unitree G1

[← back to `adapters/`](../README.md) ·
[Specification](../../specification/README.md) ·
[Architecture](../../docs/architecture.md)

Target: the **Unitree G1** as NVIDIA GR00T drives it — a 43-DoF joint vector
(29 body DoF plus two Dex3 three-finger hands), a USD stage that replays it in
Isaac Sim, and a **GR00T-LeRobot dataset** in the Isaac Lab Arena G1 layout.
Reads nothing but canonical Common Behavior Data.

This is the fourth adapter and the first non-notebook one. The three notebook
adapters — [`mediapipe_overlay/`](../mediapipe_overlay/),
[`mujoco/`](../mujoco/), [`unity_vrm/`](../unity_vrm/) — all answer an easy
question: *can canonical CBD drive a figure built to the subject's own
proportions?* This one asks the hard one: **can it drive a machine whose
proportions are not negotiable?**

## The output

    examples/human-capture/sample_output/07_groot_g1_v2/
    ├── robot_v2.usda            the robot  — references NVIDIA's G1 asset, pins the base
    ├── scene_v2.usda            the set    — floor, seat, table, the carried glass, physics
    ├── motion_v2.usda           the live stage — sublayers the two above, for the solver
    ├── motion_baked.usda        the motion — time samples only; the stage to open
    ├── motion.npz               q_actual, q_target and v1's angles side by side
    ├── motion_v2.npz            q_target after the continuity and foot-contact passes
    ├── motion_retarget.npz      the retarget this build stands on
    ├── g1_joint_trajectory.csv  the 43 joint angles per frame, in the GR00T order
    ├── groot_lerobot/           a GR00T-LeRobot v2.1 dataset
    │   ├── meta/{info,modality,tasks,episodes,stats}.json(l)
    │   ├── data/chunk-000/episode_000000.parquet
    │   └── videos/chunk-000/observation.images.ego_view/episode_000000.mp4
    ├── settle_final.json/.npz   the physics result, and every deviation
    ├── stage_report.json        the seat fit, the placement, the repairs, the invariants
    ├── adapter_report.json      what this publishes and how far it moved
    ├── README_GROOT_G1_V2.md
    └── groot_g1_v2_simulation.mp4

Model, set and motion are three separate layers (adapter rule 3).
`motion_baked.usda` is the stage to open, and nothing in it is Isaac-specific —
`usdview motion_baked.usda` works.

**v1's output directory, `06_groot_g1/`, is not committed.** Stage 1 writes it
from canonical CBD and the v2 stages read the retarget out of it, so it is an
intermediate: gitignored, and recreated by re-running stage 1. The one thing
worth keeping from it travels inside v2 instead — `adapter_report.json` holds
`change_from_v1_deg` and `motion.npz` holds `joint_angles_v1_rad`.

## Where this runs — and why it is not Colab

> **This is the one adapter in the repository that does not run in Colab.**
> The three notebook adapters do, from the Colab CLI, in the same session the
> generator ran in. Isaac Sim does not fit there: it wants an RTX GPU the Colab
> runtime does not expose, a container measured in tens of gigabytes, and a
> shader cache that survives between runs. So the render and physics steps were
> developed and run on a **Google Compute Engine VM with a single NVIDIA L4**,
> and this page records that environment instead of pretending the step is
> portable.

| | |
|---|---|
| Where | Google Compute Engine VM, Linux, single GPU |
| Machine type | `g2-standard-16` — 16 vCPU, 64 GB memory |
| GPU | 1 × NVIDIA L4 |
| Isaac Sim | 6.0.0, NGC container `nvcr.io/nvidia/isaac-sim:6.0.0-dev2`, headless |
| Robot asset | NVIDIA's public `g1_29dof_with_hand_rev_1_0.usd`, mirrored locally — not committed here |
| A full v2 run | ≈15 min PhysX settle + ≈10 min render with a warm shader cache |

**Only `physics_settle.py` and `groot_g1_render.py` need the GPU** — steps 3 and
4 below. The retarget that turns canonical CBD into a 43-DoF trajectory, the v2
stage, the finalize and the video compose are plain Python on any machine, and
they are where most of this adapter's logic lives. You can read, run and modify
the retarget without a GPU at all. `bake_motion.py` needs no GPU either, but it
does need the robot asset to resolve, so in practice it runs on the same machine
— see step 3.

The mirror in the *Robot asset* row is a directory on that VM
(`/mnt/data/assets/isaac/...`), not something this repository ships or expects
you to have. Without one, `robot_stage.py` falls back to NVIDIA's public asset
server, which is correct for the stage it writes but coarsens one measurement —
see [`README_GROOT_G1_V2.md`][v2readme].

Nothing about that VM's identity is recorded here or matters to the result: no
project, network, or host names. What matters is the class of machine —
**one L4-class RTX GPU, 64 GB of memory, Isaac Sim 6.0 in a container**. Anything
that clears that bar should reproduce these outputs.

See [`docs/runtime_environments.md`](../../docs/runtime_environments.md) for the
repository-wide rule this follows: *Colab CLI where the target allows it, a
documented environment where it does not.*

## Running it

The shipped output is v2, and v2 is a chain: the retarget runs first and
everything after it reads the retarget. Only `physics_settle.py` and
`groot_g1_render.py` need a GPU and an Isaac Sim install; every other stage runs
on a laptop.

**1 — CBD to G1: the retarget.** numpy and `usd-core`; `pyarrow` for the parquet
file. No Isaac Sim, no GPU:

```bash
pip install numpy usd-core pyarrow
python cbd_adapter_groot_g1.py --dataset ../../examples/human-capture/sample_output
```

It also takes **the generator's zip directly**, which is what
`generators/video_to_cbd/cbd_generator_video_to_cbd.ipynb` hands you at the end
of a Colab run:

```bash
python cbd_adapter_groot_g1.py --dataset ./cbd_dataset.zip
# unpacks beside the zip into cbd_dataset_unpacked/ and writes 06_groot_g1/ there
python cbd_adapter_groot_g1.py --dataset ./cbd_dataset.zip --workdir /tmp/cbd --output /tmp/out
```

**Do not skip this step because `06_groot_g1/` is missing from the repository.**
It is gitignored — an intermediate, not a deliverable — and every stage below
reads the retarget out of it: `robot_stage.py --motion` and `finalize.py --v1`
both default to `<dataset>/06_groot_g1`. This is the one stage that turns
canonical CBD into joint angles, and nothing downstream repeats it.

**2 — the v2 stage.** Host, `usd-core`. Writes `07_groot_g1_v2/` with the real
G1 referenced, the scene solved and the base pinned:

```bash
# v2_preview is optional -- it prints what the four host-side passes change
python v2_preview.py  --dataset ../../examples/human-capture/sample_output
python robot_stage.py --dataset ../../examples/human-capture/sample_output
```

**3 — physics, then bake.** `physics_settle.py` drives `q_target` through PhysX
inside the Isaac Sim runtime — this is the GPU step. `bake_motion.py` then
writes what came back as time samples on a stage that opens anywhere.

`bake_motion.py` needs no GPU, but it does need **the robot asset to resolve**:
it writes a transform per link, and it finds the links by opening the stage. A
`prepend references` that does not resolve — a mirror path you do not have, or
the public URL, which plain `usd-core` cannot fetch — leaves it with no links to
write. It **reports `"links_written": 0` and exits 0**, so check that number
rather than the exit code. In practice this stage belongs beside the physics
pass, on the machine that has the asset.

**4 — render.** Also inside the runtime. Two cameras: the film camera and the
robot's own head camera on `d435_link`, which is what the GR00T dataset's
`observation.images.ego_view` has to be.

```bash
# NGC container (handles the caches and the uid-1234 mounts for you).
# It renders whichever stage it is pointed at; as shipped that is v1's.
./run_groot_g1_docker.sh ../../examples/human-capture/sample_output

# or a local install, on the v2 stage
/isaac-sim/python.sh groot_g1_render.py \
    --stage ../../examples/human-capture/sample_output/07_groot_g1_v2/motion_baked.usda \
    --out /tmp/g1_frames
```

**5 — finalize, then compose.** Back on the host, with numpy, pyarrow, OpenCV
and ffmpeg. `finalize.py` publishes `q_actual` — the trajectory, the CSV, the
patched GR00T-LeRobot dataset and the report — and `compose_video.py` writes
both videos into it. Finalize first: it rebuilds `groot_lerobot/` from v1's
copy, and compose is what writes the ego view into that.

```bash
python finalize.py --dataset ../../examples/human-capture/sample_output
python compose_video.py --frames /tmp/g1_frames \
    --dataset ../../examples/human-capture/sample_output/04_behavior_dataset \
    --out-dir ../../examples/human-capture/sample_output/07_groot_g1_v2 \
    --name groot_g1_v2_simulation.mp4
```

The exact flags for stages 3 and 4, and the asset-mirror note that goes with
them, are in [`README_GROOT_G1_V2.md`][v2readme].

[v2readme]: ../../examples/human-capture/sample_output/07_groot_g1_v2/README_GROOT_G1_V2.md#reproducing-it

The comparison video that puts this pane beside the other three. It needs no
GPU — it reads the four finished mp4s — and the Isaac pane is v2's:

```bash
python ../../examples/human-capture/sample_output/05_comparison/build_comparison_4pane.py \
    --sample-output ../../examples/human-capture/sample_output
```

## Design notes

### Retarget, not measure — and the residual is in degrees

The other CBD adapters measure the subject's bone lengths and animate a figure
built to them. A G1 cannot be built to anyone: its links are 0.20 m of upper
arm, 0.23 m of forearm, 0.77 m of pelvis-to-ankle, and its joints stop where
the URDF says they stop.

So the motion is *solved* rather than copied. For every frame, damped least
squares over each limb chain matches **segment directions** — upper arm,
forearm, hand axis and palm normal for the arms; thigh, shank and foot forward
for the legs — in the frame of the joint that carries them, with the URDF's
limits as box constraints and the previous frame as the warm start. The waist
is the torso's rotation relative to the pelvis, decomposed in the waist chain's
own Z-X-Y order.

Directions, not metres, because a direction is the part a fixed-length limb can
actually reproduce. What is left over is reported per segment, in degrees:

| Segment | mean | max |
|---|---|---|
| upper arms | 0.09° / 0.47° | 1.46° |
| forearms | 1.71° / 3.46° | 7.17° |
| hand axis | 5.47° / 12.56° | 24.66° |
| palm normal | 6.21° / 10.66° | 65.08° |
| thighs | 2.91° / 5.69° | 9.35° |
| shanks | 0.98° / 1.59° | 4.02° |
| **foot forward** | **16.10° / 28.27°** | **38.44°** |
| all segments | **6.87°** | 65.08° |

The feet are the interesting row. A G1's ankle has pitch and roll and no yaw,
and the pitch stops at 0.52 rad — so on this seated clip **both ankle pitch
joints sit on their limit in all 96 frames**. That is not solver error; it is
the robot running out of travel, and `adapter_report.json` names every joint it
happens to, with the frame count.

### The robot keeps its size; the room is resized

A 1.32 m G1 cannot sit on furniture derived from a taller subject. Stretching
the robot to fit would be a fabrication about hardware, so the **set** is scaled
instead — one number, `scale` in the report (0.835 on the sample clip), defined
as the robot's own seated pelvis height, computed from its retargeted leg pose
with factory link lengths, divided by the subject's. Floor, chair, table and
camera are multiplied by it; the robot is not touched. The report also carries
the resulting foot clearance (−0.1 cm median on the sample clip), so you can
check that the feet actually reach the floor.

### The camera reproduces the source framing, at set scale

The camera is not eyeballed to look like the source clip. The dataset stores
each pose landmark twice — normalized image coordinates in
`human/pose_landmarks.csv` and canonical metres in the same row — so the mapping
between the source frame and canonical space is *measured* by a least-squares
fit (3168 samples, 3.1 cm residual on the sample clip) and the camera is placed
to reproduce it: optical axis through the canonical point that maps to the
centre of the source frame, horizontal field of view covering the width the fit
measured. Scaling the whole set by
`scale` leaves the framing identical, which is why the G1 pane and the overlay
pane line up.

### What v1 refused to do — and where v2 stands

Three of these four were v1's position and **v2 reverses them**; the reversal is
the subject of [the v2 section below](#v2--the-corrections-the-errors-and-what-is-left).
They are kept here because stage 1 still takes these positions in code, and
anyone re-running it gets an output that says them.

- **No policy is run, and none is implied.** *Still true in v2.* This adapter
  writes the two things a GR00T G1 stack consumes — a joint-space trajectory and
  a GR00T-LeRobot dataset — from human behavior data. v1's
  `adapter_report.json` says `"policy_was_run": false`; v2 runs PhysX position
  drives, which is a simulator and not a policy either. Calling either result a
  GR00T rollout would be a fabrication about where the numbers came from.
- **No glass, no cup, no prop.** ~~On this clip the cup was detected in **one**
  frame and no interaction candidates fired, so there is no evidence the object
  was ever grasped or moved. Standing a static prop on the table anyway, in a
  render about where the robot's joints go, would be decoration with nothing
  behind it.~~ **Reversed in v2.** The one detection and the empty
  `interaction_events.csv` are still the whole of the direct evidence, but they
  are not the only evidence: `scene_objects.py` corroborates across six
  channels — the caption, the behaviour summary and the object metrics all
  carry the glass — and `placement.py` puts it on the hand that holds it. What
  v1 read as "no evidence" was one channel being empty.
- **No physics.** ~~Kinematic replay: no rigid bodies, no articulation drives,
  no contact. Joint velocity, torque and balance limits are not checked, so this
  is not a dynamically feasible G1 trajectory.~~ **Reversed in v2.**
  `physics_settle.py` runs contact, self-collision and gravity, and the
  published angles are `q_actual`.
- **No correction of the source.** ~~On this clip the canonical landmarks put
  the right knee 19 cm across the body midline, which is what a monocular
  capture of a seated subject does. The retarget reproduces it and the report
  says so, rather than quietly straightening the legs.~~ **Reversed in v2.**
  Reproducing a monocular artefact is not fidelity, it is transcription: the
  design's priority order puts physical consistency above faithfulness to the
  source. `cleanup.py` clamps it and records the displacement (mean 2.1 cm),
  which is a correction that is declared rather than one that is silent.

## The GR00T dataset

`groot_lerobot/` is LeRobot v2.1 on disk with the **Isaac Lab Arena G1**
modality: `observation.state` and `action` are a flat 43-vector, and
`meta/modality.json` slices it into `left_leg` (6), `right_leg` (6), `waist`
(3), `left_arm` (7), `left_hand` (7), `right_arm` (7), `right_hand` (7) — the
same grouping and the same joint order the Arena G1 pick-and-place
configuration uses, so a loader set up for that embodiment reads this without
changes.

| Field | What this adapter puts in it |
|---|---|
| `observation.state` | the 43 solved joint angles, radians |
| `action` | `state[t+1]`, last frame repeated — a kinematic replay, so the commanded next pose *is* the next pose |
| `observation.eef_pose` / `action.eef_pose` | each palm link as `[x, y, z, qw, qx, qy, qz]`, **in the pelvis frame**, left then right |
| `teleop.base_height_command` | the pelvis height |
| `teleop.navigate_command` | the pelvis's planar velocity `(vx, vy, ωz)`, differenced from the root trajectory |
| `teleop.torso_orientation_rpy_command` | the solved waist roll, pitch, yaw |
| `annotation.human.task_description` | the CBD caption, via `meta/tasks.jsonl` |
| `observation.images.ego_view` | the robot's head camera, rendered from `d435_link` |

`meta/stats.json` is computed from the episode. The frame the dataset declares
for `eef_pose` is written down rather than assumed: a consumer that wants it in
the torso frame can rebase it with the waist angles in the same row.

## Files

| File | Runs where | Needs |
|---|---|---|
| `cbd_adapter_groot_g1.py` | anywhere | numpy, usd-core, pyarrow (optional) |
| `g1_kinematics.json` | — | the G1's joint origins, axes and limits |
| `groot_g1_render.py` | inside Isaac Sim | Isaac Sim 4.5+/6.0, an RTX GPU |
| `compose_video.py` | anywhere | OpenCV, ffmpeg |
| `run_groot_g1_docker.sh` | host with Docker + NVIDIA runtime | the NGC image |
| **v2** | | |
| `provenance.py` | anywhere | — (the tier ledger) |
| `deviation.py` | anywhere | — (asked / got / error) |
| `cleanup.py` | anywhere | numpy |
| `phases.py` | anywhere | numpy |
| `scene_objects.py` + `object_catalog.json` | anywhere | numpy; COCO-80 metric priors |
| `continuity.py` | anywhere | numpy |
| `foot_contact.py` | anywhere | numpy (the four-corner sole solve) |
| `placement.py` | anywhere | numpy, usd-core (object positions, surface fit) |
| `invariants.py` | anywhere | numpy (FK, seat fit, invariant checks) |
| `v2_preview.py` | anywhere | runs the four host-side passes and prints the diff |
| `robot_stage.py` | anywhere | usd-core; writes the stage, references the asset |
| `physics_settle.py` | inside Isaac Sim | Isaac Sim 6.0, an RTX GPU |
| `bake_motion.py` | anywhere the asset resolves | usd-core; bakes `q_actual` to time samples |
| `finalize.py` | anywhere | numpy, pyarrow |

`g1_kinematics.json` holds joint origins, axes, limits and link masses taken
from the official Unitree G1 URDF (`g1_29dof_with_hand.urdf`) — kinematic
parameters only, no meshes and no inertia tensors. The shells in the v1 stage's
`g1_robot.usda` are capsules spanning those same joint origins, so that robot
has the G1's proportions and no vendor mesh is redistributed here.
See [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

v2 additionally **references** NVIDIA's own G1 asset
(`Samples/Groot/Robots/g1_29dof_with_hand_rev_1_0.usd`, 87 meshes, 43 revolute
joints) rather than building capsules, and can reference catalog props the same
way. They are referenced by URL and never vendored; `--asset-root` switches
between the public asset server and a local mirror laid out the same way. A
mirror has to carry an asset's textures beside it —
`Props/YCB/Axis_Aligned/Materials/Textures/` for the YCB props — or the
material resolves to nothing and the prop renders untextured.

**The robot takes an asset; a prop earns one.** 75 of the catalog's 80 classes
have `asset: null` and are built as parametric primitives, and `cup` is one of
them: what the dataset carries is the COCO class and a caption saying *a glass
of water*, not which cup. A `025_mug.usd` is a particular mug with a handle, and
standing it in the scene states a shape nothing measured — the same fabrication
the adapter refuses everywhere else. The class's own metric prior is a
0.09 m diameter, 0.10 m tall upright cylinder, so that is what is drawn, in a
neutral grey, at the scene scale. An entry gets an asset only where the class
*is* the object it names (`bowl`, `banana`); the tier says which, and
`source: prior` on `cup` is the honest one. It makes no difference to a support
surface either way — those are parametric even when the catalog names an asset,
because their height is solved for the target.

A **support surface is built parametrically even when the catalog names an
asset**, because its height is solved for the target rather than taken from the
catalog, and an asset arrives at its own. That is the same rule the seat
follows.

## v2 — the corrections, the errors, and what is left

v1 ends by saying the next step needs physics. It ran, and `07_groot_g1_v2/` is
what came back. See [`V2_PROPOSAL.md`](V2_PROPOSAL.md) for the working and the
wrong turns; this is the summary a consumer needs.

The published angles are **`q_actual`** — what the robot did once PhysX had
resolved contact, self-collision and gravity — not the retarget's `q_target`.
Both are in `motion.npz`, alongside v1's, so nothing is lost by the choice.

### The gap from the generator's output, and what fills it

One table, because the three questions a generator author asks — *what was
missing, what did you put there instead, and what did it cost* — are answered in
three different sections below. Every number is from the sample dataset and is
reproducible with `v2_preview.py`; the tier column is `provenance.py`'s.

| missing from canonical CBD | filled by | tier | what it still costs |
|---|---|---|---|
| **`chest`, `neck`, `left_shoulder`, `right_shoulder` rotations** — identity in all 96 frames, 4 of the 19 bones | nothing can fill it: the waist moves in yaw alone, so a reach to the subject's side comes out as a reach to the robot's front | — | `scene.cup.image_vs_hand` **0.296 m**; `scene.dining table.reach_overlap` **22.3 mm** on 10 frames. The binding constraint — see [What is left](#what-is-left) |
| **A limb geometry that a body can hold** — the right knee sits 19 cm across the midline and the reach ratio is 1.050, which no limb can do with its own bones | `cleanup.py`: smoothing, a midline clamp in *direction* space (legs only — reaching across the body is ordinary), then a rebuild of every limb from the pelvis at median bone length | derived | displacement mean **2.1 cm**, p95 6.9 cm, max 11.2 cm. Crossings 96 frames → 0, reach ratio → 0.980, bone-length drift 68 % → 0 % |
| **A usable contact phase** — the `phase` field exists and is degenerate: `("Pick And Place", "Idle")` on all 96 frames of a clip that picks and places, and `interactions/interaction_events.csv` is a header with no rows | `phases.py` checks whether CBD's own phase is informative and, here, re-derives idle / reach / hold / retract from the wrist's excursion from its shoulder (0.316 → 0.552 m and back), with hysteresis. Used to weight the solve only; **never written back into CBD's interaction stream** (adapter rule 4 — do not promote candidates) | derived | the 19 hold frames are a derivation, so `invariant.hand_contact` is true by construction rather than measured |
| **What the subject is resting on** — no channel states a support relation | `invariants.py` solves the seat for *this robot in this pose*: height from the retargeted pelvis, footprint carved out of the space the legs never occupy | derived | a 110 mm pad rather than a chair; human-scale furniture would put a G1's feet 0.097 m off the floor |
| **The 3D position of a handled object** — detections are 2D boxes | `placement.py`: the handled object onto the acting hand's grasp centre, the surface under it solved for the height it rests at | derived | the table is **scenery**, collider disabled — no solid top clears the reach sweep |
| **Camera intrinsics** — the dataset records none | depth from apparent size against the catalog's unscaled metric dimensions, with the camera distance assumed at 3.0 m; the image-plane mapping itself is *measured* by least squares on the landmarks CBD stores twice (3168 samples, 3.1 cm residual) | **prior** for the distance, derived for the rest | `camera_distance_tier: "prior -- CBD records no camera intrinsics"` in every object's placement record |
| **The glass, in the detector's own channel** — 1 detection in 96 frames | corroboration across the other five: the caption names a glass, `behavior_summary.json` says *"Person interacts with a cup"*, `object_metrics.csv` carries `obj_005`. A detection is one channel of six | derived | none for existence; its *position* is the row above |
| **Collision geometry** — the kinematic table has none, so v1 authored `SOLE_BELOW_ANKLE` at 3 cm | the URDF's own four foot contact spheres per foot, 0.035 m below the ankle | **measured** — closed | none. The shipped asset's visual mesh agrees to 0.4 mm |
| **Finger curls on the frames where the hand is not detected** — the right hand drops out for 4 of 96 frames, in the middle of the close | `np.interp` between the detections either side; the nearest value is held only outside the detected range | derived | none that shows. Nearest-neighbour fill put a gap's whole change at one frame in its middle — 26.9 deg of curl between adjacent frames — and this removes it |

Two things this table is not. It is not a list of *target*-side losses — the
head and two fingers are dropped because a 29-DoF G1 has no neck and a Dex3 has
three fingers, which is under [Known limits](#known-limits) and is not the
generator's to fix. And it is not the machine-readable version: `provenance.py`
carries a `spec_feedback` channel for exactly these, keyed by the gap string.
It is **empty** in the v2 report, because every quantity above ended up at
`derived` or better once `placement.py` ran — `spec_feedback` only collects the
gaps that forced something to be *synthesized*. The table is the wider set: what
CBD did not carry, whether or not the fill had to be authored.

One open item that belongs here rather than in a commit message.
`fit_scene_to_target` anchors the scene scale on an **idealised** seat of
0.3082 m, derived from the G1's shank length, while the seat actually built is
fitted to the commanded pose at **0.4404 m**. `invariants.check_scene` compares
catalog × scale against the idealised value and passes, 0.13 m away from the
seat the robot is sitting on. The effect is bounded — support-surface *heights*
are always solved back from the target, so the idealised number is not used for
them — and reaches only the furniture footprints (the table is 0.82 × 0.55 m;
anchored on the real seat it would be 1.17 × 0.78 m).
`scene.dining table.height_solved_vs_catalog` (0.514 → 0.716 m, +0.202 m) is
that discrepancy as a number. Which anchor is right is not obvious: 0.3082 is a
property of the robot and does not move between clips, 0.4404 is this clip's
actual seated height. The robot-side one is kept for generality, and whole-body
reach should shrink the difference on its own. **Deferred and recorded, not
ignored.**

### What corrects what, and how far it may go

Every pass is bounded, declared, and runs before the one below it.

| pass | file | what it changes | bound |
|---|---|---|---|
| **cleanup** | `cleanup.py` | landmark positions, before any retarget | smoothing, midline clamp (legs only), segment rebuild at median bone length. Makes the capture *possible*, not prettier |
| **phases** | `phases.py` | nothing — derives the contact signal | used only to weight; never written back into CBD's interaction stream (rule 4) |
| **objects** | `scene_objects.py` | which objects exist | a detection is one channel of six; corroboration is spent by the best-detected instance |
| **continuity** | `continuity.py` | joint angles clipped to a limit | only when the boundary step is > 20 deg **and** > 5x that joint's median step |
| **foot contact** | `foot_contact.py` | the 12 leg joints | damped least-norm: of the poses that put all four sole corners of each foot on the floor, the one nearest the command. Arms, waist and hands untouched |
| **scene fit** | `invariants.py` | seat height, footprint, scene scale | solved for this robot in this pose; carved out of the space the legs never occupy |
| **placement** | `placement.py` | where every object stands | the handled object goes on the hand; the surface under it is solved for the height it rests at and pulled back off the robot's swept collision geometry |
| **physics** | `physics_settle.py` | the trajectory itself | position drives track `q_target`; what PhysX returns is published |

Two rules hold across all of them. **Minimum intervention**: a correction goes
as far as removing a physical contradiction and no further. **Nothing is
silent**: `provenance.py` tags every quantity `measured / derived / prior /
synthesized`, and `unavailable` is treated as a defect rather than an outcome.

### The errors, as numbers

`deviation.py` records every stage as *asked / got / error* in the quantity's
own units. On the sample dataset, after all of the above:

| check | asked | got | tol | |
|---|---|---|---|---|
| `physics.tracking_rmse` | 0 | 0.165 deg | 3 | ok |
| `physics.tracking_max.right_wrist_pitch_joint` | 0 | 2.96 deg | 10 | ok |
| `invariant.feet_on_floor` | 0 | 0.0042 m | 0.02 | ok |
| `invariant.feet_not_penetrating` | 0 | 0.00028 m | 0.005 | ok |
| `retarget.commanded_feet_on_floor` | 0 | 0.0010 m | 0.02 | ok |
| `invariant.pelvis_holds_height` | 0.5929 | 0.5929 m | 0.02 | ok |
| `invariant.pelvis_not_falling` | 0 | 1e-07 m | 0.02 | ok |
| `invariant.seated.knee_min` / `knee_max` | 60–140 | 119.6 / 133.7 deg | — | ok |
| `invariant.hand_contact` | 0 | 0 m | 0.02 | ok |

Nine of nine. What that cost, measured before and after each pass:

    midline crossings beyond the margin   96 frames  ->  0
    reach ratio (limb over its own bones) 1.050      ->  0.980   (>1 is impossible)
    worst bone-length drift               68 %       ->  0 %
    commanded sole corners  -0.118 .. +0.182 m       ->  -0.000 .. +0.004 m
    deepest commanded foot penetration    0.118 m    ->  0.000 m
    worst single-frame command step       87.11 deg  ->  29.06 deg
    cleanup displacement                  mean 2.1 cm, p95 6.9 cm, max 11.2 cm
    distance from v1                      6.93 deg RMSE, 79.7 deg worst joint

### The sole is four corners

`invariant.feet_on_floor` read 0.0097 m for a robot whose toes were 87 mm
underground, and it was right about what it measured. Both the solve and the
check modelled the sole as the single point 0.035 m below the ankle roll frame.
That point was on the floor. The foot was not: the clip commands 27-30 deg of
ankle pitch, which rotates the polygon about that point and drives the toe
under while lifting the heel 38 mm clear.

The URDF has four foot contact spheres per foot -- heel at x = -0.050, toe at
x = +0.120, all 0.035 m below the ankle -- and the shipped asset's visual mesh
bottoms out at z = -0.0354, so the spheres and the render agree to 0.4 mm.
`invariants.FOOT_CONTACT_LOCAL` is those four points; `foot_contact` solves all
four heights at once and `physics_settle` measures all four, using the ankle
link's simulated orientation rather than its height alone. A new deviation,
`invariant.feet_not_penetrating`, grades the deepest of them against the design's
5 mm penetration budget.

The lesson is not about feet. **A check that shares its model with the solve it
grades cannot fail**, and this one could not: every number in the report was
correct, and the result was still wrong in the one place a person looks first.

### The table and the glass

`placement.py` is the stage the first pass stopped before, and it runs in the
priority order the design fixes rather than as one least-squares:

1. **image estimate** -- bbox centre through the dataset's own image-plane fit,
   with depth from apparent size against the catalog's *unscaled* metric
   dimensions. A bbox side touching the frame edge is cropped and its size says
   nothing, so it is dropped: the table's width claims 3.4x the subject's
   distance, its uncropped height 1.05x, which is right.
2. **task binding** -- the handled object is placed on the acting hand's grasp
   centre, the midpoint of the palm and the middle fingertip, from the frame
   the hand first reaches it to the frame it last leaves. On this clip that is
   0.296 m from the image estimate, and the gap is the retarget's arm
   direction, not the placement: the waist carries no chest rotation, so a
   reach to the subject's side comes out as a reach to the robot's front.
   Recorded as `scene.cup.image_vs_hand`.
3. **support** -- the surface under it is solved for the height the object
   rests at, the same rule the seat follows. Its footprint keeps the one scene
   scale, and it is a top on four legs rather than a block to the floor.
4. **carve** -- the near edge is pulled back, and the top lowered if that is
   not enough, until no robot link enters the surface. Links are taken at the
   extent of their own collision boxes, read from the asset: a link origin is
   the origin of a frame, not the extent of a body, and treating it as a point
   put a hand's collision mesh 17.5 mm inside a table the fit called clear.

On this clip no solid surface fits. Reaching for the glass takes the hand
through the plane the glass rests on -- 22.3 mm at worst, on 10 of 96 frames,
all of them approach or withdrawal -- and the best top that does clear the
sweep is 0.590 m, 0.125 m below where the hand holds the glass. So the table is
authored as **scenery**: the geometry, at the right height, with its collider
disabled and the residual overlap in the ledger as
`scene.dining table.reach_overlap`. That is the seat's rule ("with the pelvis
pinned the seat carries no load") applied to a surface nothing leans on, and
the overlap belongs to the whole-body reach, which is still open.

The carried object is animated rather than simulated, for a measured reason:
nothing closes the fingers on it, so a kinematic body driven along the hand is
a body inside the hand. The same clip measured **0.165 deg** tracking RMSE with
the prop absent and **9.52 deg** -- 135 deg on the right wrist alone -- with it
present as a kinematic body, `physics:collisionEnabled` false and all.
`--no-props` builds the floor-and-seat scene that isolates exactly this.

`fixed_base_approximation` is the one deliberate simplification: the pelvis is
pinned rather than balanced, because a seated clip's support is the seat and the
retarget already decided where the pelvis goes. Its cost is recorded — the
commanded pelvis moves 1.5 cm in z and 4.6 cm in y over 96 frames.

### Two v1 limits closed

`SOLE_BELOW_ANKLE` was authored at 3 cm because the kinematic table carries no
collision geometry. It is **0.035 m**, measured from the URDF's own foot contact
spheres (`z = -0.03`, radius `0.005`), and `invariants.ANKLE_TO_SOLE_M` uses
that. The sole is also four of those spheres rather than one, which is the
section above.

The **ego view** is now the v2 stage's. `bake_motion` writes the same camera v1
authored -- parented to `d435_link`, D435 field of view -- into the baked stage,
so `observation.images.ego_view` is the real robot's head camera looking at the
real table, rather than the capsule stand-in looking at an empty room.
`finalize` keeps whatever is already in the dataset's `videos/` when it patches
the joint vectors, so the two do not fight.

### What is left

1. **Whole-body reach.** When the G1's arm cannot span what the subject's did,
   lean and step rather than match joint angles and miss. This is now the
   binding constraint rather than a note: it owns `scene.cup.image_vs_hand`
   (0.296 m between where the image puts the glass and where the hand goes) and
   `scene.dining table.reach_overlap` (22.3 mm of hand inside the tabletop on
   10 frames, which is why that surface is scenery rather than a collider). The
   direct cause is upstream of the arm -- `chest` and both `shoulder` bones
   carry no rotation signal, so the waist moves in yaw only and a reach to the
   subject's side comes out as a reach to the robot's front.
2. **Generality.** The passes have been measured on one clip and on four
   degraded variants of it. Three clips with different furniture, a standing
   subject and a partially-framed one are what would actually settle it.
3. **A balanced root.** `--root-mode free` is honest for a standing clip and
   fails there for the right reason; a seated clip is pinned. A clip that stands
   up needs neither.
4. **A grasp — now the visible defect.** The handled object is animated onto
   the hand, not held by it, and since the curl fix the closed hand hides it:
   the cylinder is inside the fist for the whole hold. Fixing the curl was not
   a grasp and the measurement says so — the deepest hand link inside the
   cylinder went 18.5 mm to 16.0 mm and moved from the middle finger's base to
   the thumb's. Two cheaper repairs were tried and **both are worse**: seating
   the object off the palm by its own radius is the distance it already has,
   and moving it to the pinch point takes the worst penetration from 17.3 mm to
   22.1 mm, on 63 frames of 63 instead of 37. The reason is not placement. The
   largest cylinder that clears every hand link is **26.9 mm** across on the
   worst frame and the cup is **61.6 mm**, so no position for this object
   avoids the links: the hand is closed too far for it, because the curl is
   copied from the subject and never looks at what is being held. That is item
   1's failure one joint further down — matching angles and missing the object
   — and the priority order settles it the same way: during a hold the curl is
   the adapter's to solve. The plan, the two wrong turns and the numbers behind
   them are in [`V2_PROPOSAL.md`](V2_PROPOSAL.md#the-grasp-and-two-wrong-turns-before-it);
   it needs a bisection on each finger's curl, no IK and no new dependency.

## Known limits

- **The head is dropped.** The G1's 29-DoF configuration has no neck joint, so
  the subject's head orientation has nowhere to go.
- **A curl is a mean, and was read as a total.** `finger_curls_rad` is defined
  by the specification as *mean flexion per finger*; the hand map treated it as
  the finger's whole bend and split that across the two Dex3 joints. On the
  sample clip the subject's index bends 99.3 deg over its three joints and the
  mean is 33.1; the robot closed to 33 deg where it should have closed to 99,
  about a third of a grip, against 190 deg of available travel. **Fixed** — the
  total is `CURL_JOINTS_PER_FINGER` times the mean, and only the 14 hand joints
  moved; every other joint is bit-identical. The lesson is the foot's again: a
  quantity's definition was assumed rather than read, and here it was written
  down.
- **Two fingers are dropped.** A Dex3 hand has three fingers; CBD carries five
  curls. Ring and little have nowhere to go, and `thumb_0` is an abduction
  rather than a curl, so it is driven to a fixed opposition angle in proportion
  to the measured thumb flexion — an adapter choice, and labelled as one.
- **Four bones carry no signal.** On this dataset `chest`, `neck`,
  `left_shoulder` and `right_shoulder` are written as identity, so the waist
  moves in yaw only.
- **Scale is still monocular.** The `scale` number inherits the canonical
  capture's leg-to-torso ratio; see
  [specification → units and scale](../../specification/README.md#open-questions).
- **`SOLE_BELOW_ANKLE` is authored** *in v1*. 3 cm, because the kinematic table
  carries no collision geometry to measure the sole from. v2 measures it, and
  the whole contact polygon, from the URDF's foot spheres.
- **The props are not simulated.** The carried object is animated onto the hand
  and the surface it rests on is scenery; both are recorded as such with the
  numbers that forced it. The floor, the seat and the robot's own body are the
  contact set the physics pass measures.

## Where this points

The natural next step is the one this adapter deliberately stops short of:
feeding `groot_lerobot/` to a GR00T G1 policy — post-training on it, or
replaying it in Isaac Lab Arena, whose `ReplayLerobotActionPolicy` takes a
dataset in exactly this layout. That needs physics, and physics needs the force
and contact channels the specification does not have yet. Which is the useful
part: the adapter found the gap by hitting it.

**v2 took that step.** Physics ran, and the gap it found is narrower and more
specific than "force and contact": what the schema is missing is a *validity
signal on `phase`*, a *support relation* saying what the subject is resting on,
and channels for the bones that carry no rotation. All three are listed with the
evidence in [`V2_PROPOSAL.md`](V2_PROPOSAL.md#what-this-asks-of-the-adapter-contract).
