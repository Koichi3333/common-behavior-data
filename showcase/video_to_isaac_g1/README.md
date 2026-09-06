# Video → CBD → Isaac Sim / GR00T, Unitree G1

[← back to `showcase/`](../README.md)

The same clip, on a **machine**. A Unitree G1 as NVIDIA GR00T drives it: 43 DoF,
fixed link lengths, hard joint limits, and no willingness to be rebuilt to
anyone's proportions.

This is the run where the representation stopped being comfortable, which is why
it is the most useful page here.

| | |
|---|---|
| **Source** | [`examples/human-capture/sample_output/source/source_video.mp4`](../../examples/human-capture/sample_output/source/source_video.mp4) |
| **Generator** | [`generators/video_to_cbd/`](../../generators/video_to_cbd/) → `04_behavior_dataset/` |
| **Adapter** | [`adapters/isaac_sim_groot_g1/`](../../adapters/isaac_sim_groot_g1/) |
| **Ran on** | retarget & compose: any machine · **render & PhysX: Google Compute Engine, `g2-standard-16`, 1 × NVIDIA L4**, Isaac Sim 6.0 |
| **Output** | [`07_groot_g1_v2/`](../../examples/human-capture/sample_output/07_groot_g1_v2/) (current) · [`06_groot_g1/`](../../examples/human-capture/sample_output/06_groot_g1/) (v1, kept as the baseline) |
| **Video** | `07_groot_g1_v2/groot_g1_v2_simulation.mp4` |

> **Not Colab.** Isaac Sim needs an RTX GPU the Colab runtime does not expose, a
> container measured in tens of gigabytes, and a shader cache that survives
> between runs. The retarget and the video compose are plain Python and run
> anywhere; only the render and physics passes need the GPU box. The outputs are
> committed, so this result is readable without one. See
> [`docs/runtime_environments.md`](../../docs/runtime_environments.md).

## What was generated

- **43-DoF joint trajectory** — 29 body DoF plus two Dex3 three-finger hands, in
  the GR00T order (`g1_joint_trajectory.csv`, `motion.npz`)
- **OpenUSD stage** — robot, set and motion as three separate layers, openable in
  plain `usdview`
- **A GR00T-LeRobot v2.1 dataset** in the Isaac Lab Arena G1 modality — 43-DoF
  state and action, an ego-view video from the robot's own head camera, a task
  string from the CBD caption
- **`adapter_report.json`** — every residual, every joint on a limit, and where
  each number came from

## What worked

- **The schema survived a second simulator, and a robot.** The adapter reads
  only `04_behavior_dataset/`, converts frames once at its boundary, and required
  **no change to the representation**.
- **Physics agreed with the retarget.** The trajectory was driven through PhysX
  and the published angles are `q_actual` — what came back — not `q_target`.
  Tracking RMSE **0.18°**, worst joint 3.31°.
- **The feet are on the floor.** Contact measured on the four sole spheres per
  foot: penetration **0.118 m → 0.000 m**, foot tilt 0.101 m → 0.001 m.
- **Nothing was fabricated silently.** 99.8 % of the stage is `measured` or
  `derived`; 0.16 % is `synthesized` and labelled as such.

## What broke

| | |
|---|---|
| **A fixed limb cannot match a reach in metres** | The motion had to be *solved* — per-frame damped least squares on segment directions under the URDF's limits. Residual **6.87° mean**, 65.08° worst (palm normal) |
| **The robot ran out of travel** | **Both ankle pitch joints sit on their limit in all 96 frames.** Not solver error — a G1 ankle has pitch and roll, no yaw, and the pitch stops at 0.52 rad |
| **Furniture sized for a taller subject** | A 1.32 m G1 cannot use it. The **set** was scaled instead — `scale = 0.685` in v2, anchored on the robot's own geometry; stretching the robot would be a fabrication about hardware |
| **Four bones carry no rotation** | `chest`, `neck`, and both shoulders are identity in every frame, so the waist yaws and nothing else. **A reach to the subject's side comes out as a reach to the robot's front** — the largest remaining error, 0.296 m |
| **`phase` was degenerate** | All 96 frames read `("Pick And Place", "Idle")` on a clip that picks and places, and `interaction_events.csv` was a header with no rows. The adapter re-derived idle / reach / hold / retract from wrist excursion — for solver weighting only, never written back as CBD interactions |
| **The subject's limbs did not close** | Right knee 19 cm across the midline; reach ratio 1.050, which no body can do with its own bones. Cleaned, at a cost of 2.1 cm mean displacement |
| **A silently wrong unit** | `finger_curls_rad` is *mean flexion per finger*; the adapter had treated it as whole-finger flexion, under-driving the hand by exactly 3× |
| **No neck, three fingers** | Head pose and two fingers per hand are dropped. That is the hardware, not the data |

## Corrections, and what they cost

| Correction | Change |
|---|---|
| Four-point contact polygon instead of a point under the ankle | penetration 0.118 → 0.000 m; up to 24.7° of joint change to achieve it |
| Limb rebuild at median bone length, midline clamp in direction space | 2.1 cm mean displacement, p95 6.9 cm; crossings 96 frames → 0, bone-length drift 68 % → 0 % |
| Continuity pass through limit-clipped runs | worst adjacent step 87.1° → 29.1° |
| Linear interpolation across a 4-frame hand dropout | removed a 26.9° single-frame jump the nearest-neighbour fill had created |
| Object placement: the glass onto the acting hand, the surface solved for its height | hand-contact error 0.0 m over 19 frames — true by construction, and labelled as such |

Between v1 and v2 the trajectory changed by **19.7° RMSE**, 79.7° worst joint.
Both are kept: `06_groot_g1/` is what an adapter that only asserts what it can
prove produces; `07_groot_g1_v2/` is what one that fills the gaps and labels
every fill produces. **The difference between them is the argument.**

## Known limitations

- **No policy was run.** `adapter_report.json` records
  `"policy_was_run": false`. The LeRobot dataset is what a GR00T G1 policy would
  be trained or replayed on, not its output.
- The table is **scenery** — its collider is disabled, because no solid top
  clears the reach sweep while the shoulders carry no rotation.
- The glass is drawn as a neutral grey cylinder, not a mug: CBD has a COCO label
  and a caption, and measured no handle, glaze or taper. Drawing one would be
  fabrication.
- Whole-body reach is now the binding constraint, and three more clips are
  needed before any of this can be called general.

## Where the findings went

Every row above is classified — source, generator, specification, or target
constraint — in
[`docs/compatibility_findings.md`](../../docs/compatibility_findings.md). Four
of them are requests to the specification: a validity signal on `phase`, a
support relation, rotation for the four bones that carry none, and a declared
real-world scale.

## See also

[`cross_simulator/`](../cross_simulator/) — this pane beside the other three ·
the adapter's full write-up:
[`adapters/isaac_sim_groot_g1/README.md`](../../adapters/isaac_sim_groot_g1/README.md)
and [`V2_PROPOSAL.md`](../../adapters/isaac_sim_groot_g1/V2_PROPOSAL.md)
