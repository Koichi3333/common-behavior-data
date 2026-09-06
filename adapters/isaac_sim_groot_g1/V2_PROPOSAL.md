# Proposal: adapter v2 — correct the capture, weigh every channel, declare the fill

Status: **front end implemented and measured; the Isaac Sim half is next.**
Nothing in this proposal has been committed — the modules sit beside v1 and
change none of its behaviour until they are wired in.

## The problem, in v1's own words

`06_groot_g1/adapter_report.json` is unusually honest, and reading it is how
this proposal started:

> - *"the right knee sits **19 cm across the body midline** from its hip, which
>   a monocular capture of a seated subject does produce. **The retarget
>   reproduces it rather than correcting it**"* — and three more like it
> - *"bones with no rotation signal in the dataset (written as identity, not
>   estimated), so the joints that would have carried them **stay at zero**:
>   chest, neck, left_shoulder, right_shoulder"*
> - *"the head: the G1's 29-DoF configuration has no neck joint, so the
>   subject's head orientation is **dropped entirely**"*
> - *"**no glass, cup or other prop is placed**"* — in a clip whose
>   `behavior_summary` calls the cup the primary object
> - `"policy_was_run": false`

None of that is carelessness. It is adapter rules 4 and 5 — *do not promote
candidates*, *report what you could not represent rather than silently
approximating* — followed to the letter. v1 chose the record over the target
every time.

The result is a robot with a knee 19 cm inside the other thigh, a rigid chest,
no head, and a grasp on empty air. **Fidelity to a capture the target cannot
represent is not fidelity; it is error, passed through.** The penetration this
adapter gets blamed for begins in the input, not in the IK, and no
self-collision cost downstream can repair a pose that was already impossible
when it arrived.

## What changes

Priority order, applied to every trade-off:

1. **physical consistency** — no penetration, feet on the floor, no
   self-intersection. Never broken.
2. **the task happens** — the hand reaches what it grasps, the pelvis rests on
   what it sits on.
3. **plausible motion** — poses, speeds and balance a G1 could hold.
4. **fidelity to the source clip** — last.

v1 ran this list backwards. Rule 5's real requirement is *not silently*, and
that half is kept in full: every quantity now carries a tier —
`measured / derived / prior / synthesized` — and `unavailable` is treated as a
defect rather than an outcome. **Rule 4 is kept literally**: geometry may be
synthesized, but nothing here writes back into CBD's interaction stream. A
phase this adapter infers is not an observed `grasp`.

## Four modules, no GPU, all measured on the sample dataset

    provenance.py      the tier ledger, and the floor that stops synthesis
                       from quietly becoming the whole output
    cleanup.py         anatomical correction before anything is retargeted
    phases.py          the contact signal, derived when CBD's own is degenerate
    scene_objects.py   objects as hypotheses weighed against six channels
    object_catalog.json  metric priors for the whole COCO-80 vocabulary
    v2_preview.py      runs all four and prints what changed

```bash
python v2_preview.py --dataset ../../examples/human-capture/sample_output
```

### 1. cleanup.py — 96 frames of impossible geometry, gone

Smoothing, a midline clamp applied in *direction* space, then a rebuild of every
limb from the pelvis at median bone length. Measured on the sample:

| | before | after |
|---|---|---|
| right knee past the allowed midline margin | **96 frames** (max 0.110 m) | **0** |
| right ankle / heel / toe, same | 96 / 95 / 70 frames | **0 / 0 / 0** |
| right arm reach ÷ its own bone chain | **1.050** — impossible | 0.980 |
| left arm, same | **1.034** — impossible | 0.991 |
| worst bone-length drift over the clip | **68 %** | 0 % |

Cost: mean 2.1 cm of correction, p95 6.9 cm, max 11.2 cm. Bounded on purpose —
the pass makes the motion *possible*, not prettier. Arms are deliberately left
free to cross the midline, because reaching across the body is ordinary motion
and this very clip does it; only legs are held.

### 2. phases.py — the contact signal CBD did not supply

The sample's `phase` field is one label for all 96 frames and
`interaction_events.csv` is empty, so a phase-weighted objective would have
nothing to weight. The pose does have it — the wrist travels 0.31 m → 0.55 m and
back — so the phase is re-derived from the wrist excursion when CBD's own is
degenerate, and taken from CBD when it is not.

The derived segmentation, independently, reproduces the two captions:

    reach   0.00–1.67s ┐
    hold    1.75–2.58s ├── "reaches out, grabs a glass of water from the table"
    retract 2.67–2.92s ┘
    idle    3.00–5.75s      (drinking)
    reach   5.83–6.25s ┐
    hold    6.33–6.92s ├── "holding a glass of water, places it back on the table"
    retract 7.00–7.92s ┘

### 3. scene_objects.py — the cup comes back, the ghost chair does not

Detections are one channel of six, and on this clip the least reliable one:

| track | label | detected | v1 | v2 |
|---|---|---|---|---|
| `obj_001` | chair | 96/96 | stood up | accepted — detector alone |
| `obj_003` | chair | 47/49 | stood up | accepted — detector alone |
| `obj_004` | chair | **1** | **stood up** | **rejected as spurious** |
| `obj_002` | dining table | 26 | stood up | accepted, resolves to a verified asset |
| `obj_005` | cup | **1 (1 %)** | **dropped** | **accepted** — `primary_object` and the caption vouch for it |

The rule that makes this work: label-level corroboration is *spent* by the
best-detected instance. "The caption says there is a chair" is evidence for one
chair, and a subject sits on exactly one seat — so the same sentence and the
same pelvis cannot also vouch for a one-frame ghost.

Seatedness is read from the **measured knee flexion** (109°), not from pelvis
height, which reads 95 % of a leg length above the floor and would call a seated
subject standing. The angle is in the dataset; the height is an artefact of the
monocular view.

### 4. object_catalog.json — 80 entries, and then it is finished

The generator's detector is MediaPipe's, whose vocabulary is **COCO-80 and
closed**. So the catalog is complete by construction rather than a growing pile
of special cases — and no language model is needed to know how big a chair is.
80 classes: dimensions, mass, static/dynamic, support surfaces, affordances.

Six classes resolve to real NVIDIA assets, each verified to return HTTP 200 on
2026-09-04; the rest fall back to parametric primitives. **Assets are referenced,
never vendored** — paths are also never guessed, because the library's naming is
not predictable (`Environments/Office/Props/SM_Chair_A1.usd` is a 404).

## Does it generalise? — four degraded variants

Each strips a channel the sample happens to have. No code changes.

| variant | behaviour |
|---|---|
| **no captions** | cup still recovered, on `behavior_summary` alone; ghost chair still rejected |
| **no behavior_summary** | cup still recovered, on the caption alone |
| **detector returns nothing at all** | floor derived from the feet; **chair and cup synthesized from the pose** — "the subject is seated and no sit-able object was detected; a seat has to exist or the robot floats". Evidence ratio still 94.6 % |
| **standing subject** | seatedness flips; no seat is synthesized; the ghost chair loses its last corroboration and is rejected |

The third is the whole policy working end to end: **the pipeline does not stop
when a channel fails, and it does not lie about having filled the gap.**

## Invariants — the properties correction is not allowed to spend

Correction changes a lot by design. What it may not change is whatever made the
clip *that* clip. The subject is seated for all 96 frames, and a G1 that ends up
standing, floating, or sunk into the chair has not been corrected — it has been
replaced. So a decisive property is **declared** (`invariants.py`), carried
alongside the motion, and checked after every stage that could break it. A
failing invariant is a failed run, not a footnote.

The seat forces the issue, and the numbers are not close. From
`g1_29dof_with_hand.urdf` — the foot contact spheres sit at z = −0.03 with
radius 0.005, so the sole plane is 0.035 m below the ankle frame:

| | |
|---|---|
| G1 knee → ankle | 0.3176 m |
| G1 ankle → sole | 0.0350 m |
| **G1 seated knee height** | **0.3526 m** ← where a seat top has to be |
| `object_catalog.json` "chair" | 0.4500 m ← human furniture |

**A G1 on a stock 0.45 m chair has its feet 0.097 m off the floor.** "Seated"
and "feet on the floor" are both true of the source clip; on human-sized
furniture the robot can hold at most one of them.

### One scale, anchored on the invariant

Solving each surface on its own looked tidier and was wrong: drop the seat to
0.353 m and leave the table at its human 0.75 m, and the robot sits 0.10 m lower
under a table that did not move — the subject's relationship to her own
furniture, which is what the clip is about, is gone.

So the scene takes **one** scale and the decisive invariant sets it:

    scale = 0.3526 / 0.450 = 0.7836

which is v1's instinct — *"the robot is not resized; the room is"* — with the
arbitrary ratio replaced by a number derived from the robot's own shank. The
sanity check is that it lands where a body-proportion argument would put it: the
URDF measures 1.261 m sole to head-camera frame, roughly three quarters of an
adult, without the adapter ever being told a human height. Same answer,
independent route.

    chair          0.450 -> 0.353 m seat
    dining table   0.750 -> 0.588 m top
    cup            0.090 -> 0.071 m       (a life-size mug is one a Dex3 hand
                                           cannot close around)

The cost is stated rather than hidden: `dims_scaled_m` sits beside the catalog's
`dims_m`, and the scale is in the report, so a consumer who needs metric
furniture has both numbers.

### What it catches

| variant | invariant | result |
|---|---|---|
| sample | `seated` | **ok** — seat top 0.353 m, target 0.353 m |
| detector returns nothing | `seated` | **ok** — the seat is synthesized from the pose and still lands at 0.353 m |
| standing subject | `standing` | declared; no seat synthesized, scene scale stays 1.0 |
| all | `hand_contact` | deferred — checked once the robot is posed |

`hand_contact` is the one that will bite next: it declares that the acting hand
must be within 2 cm of the object for every `hold` frame, and it breaks if the
reach is matched in joint angles only. That is the whole-body reach problem,
stated as a check before the code that has to satisfy it exists.

## The physics pass — and what it found in the first run

`robot_stage.py` writes a stage that **references** the real asset (never
vendors it) and `physics_settle.py` drives it through PhysX inside the Isaac Sim
container. Both work end to end:

    articulation root: /World/G1/pelvis
    drive api:         apply_action(ArticulationAction)
    composed stage:    87 meshes, 43 revolute joints, 1 articulation root,
                       54 colliders, floor + seat + PhysicsScene
    43/43 joint names in motion.npz match the asset's — no remapping at all

The asset was downloaded to a local mirror laid out like the public server
(38,195,671 bytes, byte-identical in size to the copy inside the Arena image),
so `--asset-root` switches between the two without touching the stage.

**The first physics run failed, with numbers, and that is the result.** v1's
trajectory does not hold a seated pose on the real robot:

| deviation | asked | got | error | tol |
|---|---|---|---|---|
| `physics.tracking_rmse` | 0 | 10.11 | +10.11 | 3 deg |
| `physics.tracking_max.right_wrist_roll_joint` | 0 | 113.0 | +113.0 | 10 deg |
| `invariant.feet_on_floor` | 0 | 0.919 | +0.919 | 0.02 m |
| `invariant.pelvis_holds_height` | 0.6099 | 0.139 | +0.471 | 0.02 m |
| `invariant.seated.knee_max` | ≤ 140 | 151.3 | +11.3 | 0 deg |

The per-frame link heights say what happened plainly:

    frame 0    pelvis 0.4164 m    left sole 0.9540 m
    frame 95   pelvis 0.1395 m    left sole 0.1554 m

**At frame 0 the foot is half a metre above the hip.** v1's seated pose puts the
G1's legs in the air rather than under it — the robot then falls 0.28 m over the
clip and the knees straighten past the seated band. Whether that is a sign
convention in the hip pitch or a retarget that never had to be feasible, it is
a defect that the capsule figure and the kinematic replay could not show: no
contact, no gravity, nothing to be wrong against. `"policy_was_run": false` was
hiding a real number.

### Two of the errors it caught were mine

That is the part worth keeping. The ledger did not just grade v1:

1. **The seat height conflated three heights.** `seat_height_for_target()`
   returned the knee height (0.3526 m) as the seat top, the root position and
   the hip axis all at once. Placing the root there put the whole pelvis 0.15 m
   inside the seat box and PhysX ejected it — reported as
   `pelvis_on_seat: asked 0.3526, got 0.132, error 0.2206 m` before anyone
   looked at a picture. Measuring the asset's own bounding boxes separated them:
   hip axis 0.3526, seat top 0.3082 (one thigh half-thickness lower, because the
   thigh rests on the seat and its axis does not), pelvis origin 0.6099.
2. **The check itself compared the wrong pair** — pelvis origin against seat
   top, two heights that are 0.30 m apart by construction. Fixed to compare
   against the root the invariant asked for, plus a second check on how far the
   pelvis drifts from first frame to last, because a robot resting on something
   does not move.

An error ledger that only ever indicts the previous version is not measuring
anything.

### Correction: the pose was fine; the seat was not

The first read of that run said v1's seated pose "puts the legs in the air".
**That was wrong**, and forward kinematics on the commanded joints -- no
simulator, no contact -- says so plainly. Frame 0, in the pelvis frame:

    left knee    x +0.285   z -0.205        knees forward and below the pelvis
    left sole    x +0.291   z -0.554        feet below and forward
    right knee   x +0.318   z -0.184
    right sole   x +0.368   z -0.494

That is a person sitting. The 0.954 m foot was a transient *after* the robot had
already been ejected and tumbled — reading a settled simulation as if it were
the commanded pose. Worth stating because the ledger is supposed to prevent
exactly that kind of confident wrong reading, and here it needed FK to catch it.

**So: can the chair height be changed? Yes, and it had to be.** The idealised
sitter model was wrong in both height and position:

| | idealised | fitted to the commanded pose |
|---|---|---|
| seat top | 0.3082 m | **0.4454 m** (0.137 m higher) |
| seat centre x | 0.0 | **+0.168 m** |
| seat footprint | 0.35 × 0.35 | **0.457 × 0.350 m** |
| root (pelvis origin) | 0.6099 m | **0.5929 m**, from the retarget's own `pelvis_position_robot` |

`invariants.seat_from_pose()` forward-kinematics the trajectory, puts the soles
on the floor, and places the seat top at the pelvis underside with a footprint
spanning back to front of the knees. Nothing about a textbook sitter survives.

It also surfaces a retarget finding on the way: the soles travel **0.158 m
vertically** over a clip in which the subject never stands up. Feet do not do
that while seated.

### It reproduces

Three fixes, each one found by a measurement rather than by looking at a picture.

**1. Pin the root.** A USD articulation is floating-base unless something holds
it, so the physics pass was measuring balance — which a seated clip does not
have to pass, because the seat is what holds the robot up. Teleporting a dynamic
root onto the trajectory each step was tried and is measurably worse (implied
velocity becomes energy: pelvis climbed to 0.834 m, feet to 2.09 m). A
`PhysicsFixedJoint` to the world is the third way, and on this clip it costs
almost nothing — the commanded pelvis moves 1.5 cm in z and 4.6 cm in y over 96
frames, recorded as a 0.0258 m approximation rather than assumed away.

**2. The seat was a plinth.** Fitted to the pose it was the right height, but
drawn as a solid block from the floor to 0.4454 m and sized out to the knees —
so the shins and feet were *inside* it and PhysX spent the clip pushing the legs
out. A seat is a surface on legs: 0.06 m thick, and reaching forward only as far
as the thighs never drop through that plane. Because the legs move, that limit
is the **smallest** clearance over the clip (0.055 m), not the largest (0.337 m).

**3. The joint vector was permuted twice.** `order[k]` is the articulation index
of `names[k]`, so values passed with `joint_indices=order` must stay in *names*
order; indexing them by `order` as well silently commands a scrambled pose. This
one cost three container runs, and it was invisible from the outside: the pelvis
held, the knees looked seated, and only the feet were wrong.

| | free root | + fixed base | + thin seat | + order fix, tuned |
|---|---|---|---|---|
| tracking RMSE | — | 31.6° | 14.4° | **3.77°** |
| worst joint | — | 649.8° | 92.9° | **21.3°** |
| joints within 3° | — | — | 29/43 | **33/43** |
| `pelvis_holds_height` | FAIL 0.387 m | **ok 0.004** | **ok** | **ok 0.0039 m** |
| `pelvis_not_falling` | FAIL | **ok** | **ok** | **ok 3.8e-06 m** |
| `seated.knee_max` | FAIL 151° | FAIL 150° | FAIL 147° | **ok 124.7°** |

**The robot sits, holds the pose for 96 frames, and its knees stay in the seated
band.** Four of the eight checks pass; the pelvis is stable to 3.9 mm.

### The feet, and the seat that was fighting them

`retarget.commanded_feet_on_floor` said the trajectory itself put the soles
between -0.055 m and +0.103 m, so `foot_contact.py` pays that bill: contact is
*derived* (seated with no locomotion phase means both feet down for the whole
clip -- the capture's own 0-0.11 m of foot bob is monocular noise, and a seated
person's feet do not do that), and the six leg joints per side are solved by
damped least-norm to put each sole on the floor. Of the many leg poses that
reach, it takes the one nearest the commanded pose. Arms, waist and hands are
not touched -- verified, not asserted.

    commanded sole z    -0.0492 .. +0.1590  ->  -0.0033 .. +0.0049 m
    largest joint change                        28.4 deg (right hip pitch)
    solve time                                  0.7 s, on the host

That made the physics *worse*, which took three more runs to explain. The seat
was the culprit each time, and none of it was visible from the landmark
arithmetic -- every failure looked identical from outside: one leg joint ~120 deg
off, feet in the air.

| seat | `feet_on_floor` | RMSE | what was wrong |
|---|---|---|---|
| plinth to the floor, out to the knees | 0.919 m | 31.6° | shins and feet inside it |
| thin slab, min clearance | 0.2014 m | 3.77° | (before the foot fix) |
| same, after the foot fix | 0.3004 m | 18.9° | corrected thighs now graze the front edge |
| + 5 mm under the pelvis | 0.3219 m | 18.6° | not marginal — the hip chain *sweeps* through |
| **none at all** (diagnostic) | 0.0558 m | 3.11° | proof the seat, not the control, was the fault |
| **carved from the swept volume** | **0.0716 m** | **3.86°** | fits |

The fix is to stop inferring the seat from two landmark heights and carve it out
of the space the robot never occupies: sample every leg link over every frame,
shrink until nothing comes within a link radius. It lands at x -0.147..-0.038 —
a 109 mm pad behind the hip chain — and reports `fits: false` rather than
placing a box that fights the legs, because with the pelvis pinned the seat
carries no load and a bad box is worse than none.

### Where it ends up

    [ok  ] invariant.pelvis_holds_height     4.5e-07 m  / 0.02
    [ok  ] invariant.pelvis_not_falling      1.8e-07 m  / 0.02
    [ok  ] invariant.seated.knee_min         102.3 deg  in 60-140
    [ok  ] invariant.seated.knee_max         122.0 deg  in 60-140
    [ok  ] retarget.commanded_feet_on_floor  0.0033 m   / 0.02
    [FAIL] physics.tracking_rmse             3.858 deg  / 3
    [FAIL] physics.tracking_max.right_hip_yaw 33.2 deg  / 10
    [FAIL] invariant.feet_on_floor           0.0716 m   / 0.02

**Five of eight, and the robot sits on a seat with its feet on the floor for 96
frames.** Over the whole session `feet_on_floor` went 0.919 -> 0.0716 m and the
tracking RMSE 31.6 -> 3.86 deg. The three that remain are close rather than
structural: 33/43 joints track within 3 deg, and the residual foot error is
7 cm on a robot whose commanded soles are now within 5 mm of the floor — it is
tracking, not geometry.

### The output

`07_groot_g1_v2/` is complete: the baked stage, the trajectory, the patched
GR00T-LeRobot dataset, the video, and every measurement.

    motion_baked.usda        time samples only -- `usdview` works, no simulator
    g1_joint_trajectory.csv  43 angles per frame, q_actual
    groot_lerobot/           v1's layout, joints and stats swapped for q_actual
    groot_g1_v2_simulation.mp4   96 frames, 12 fps, 720x1280
    motion.npz               q_actual, q_target and v1's angles, side by side
    settle_final.json        every deviation
    README_GROOT_G1_V2.md

Final measurement, on the published stage:

| check | asked | got | |
|---|---|---|---|
| `physics.tracking_rmse` | 0 | **0.165 deg** | ok (tol 3) |
| `physics.tracking_max.right_wrist_pitch_joint` | 0 | 3.19 deg | ok (tol 10) |
| `invariant.feet_on_floor` | 0 | **0.0097 m** | ok (tol 0.02) |
| `retarget.commanded_feet_on_floor` | 0 | 0.0033 m | ok |
| `invariant.pelvis_holds_height` | 0.5929 | 0.5929 m | ok (5e-07) |
| `invariant.pelvis_not_falling` | 0 | 7e-06 m | ok |
| `invariant.seated.knee_min` | >= 60 | 102.1 deg | ok |
| `invariant.seated.knee_max` | <= 140 | 122.1 deg | ok |

**Eight of eight.** The published angles sit 4.38 deg RMSE from v1's, 79.7 deg
at the worst joint -- the legs, from the foot solve, and the right wrist, below.

### The last failure was also upstream

`right_wrist_yaw_joint` was 22.06 deg out, and the shape of the error said where
to look: mean 0.53 deg over the clip, one frame of 96 above 10. Frame 71 was all
of it.

    frame            68      69       70       71       72
    wrist roll    -34.3  -113.0*  -113.0*   -33.0    -36.6     * = at its limit
    wrist yaw      -6.1    +39.8    +47.5    -39.6    -48.1

The roll axis is clipped to its limit for two frames -- the retarget asked for a
wrist orientation the G1 cannot reach -- and the yaw swings **87 deg in one
frame** coming out of it: a Euler branch flip through a clipped singularity. The
joint's *velocity* limit is 22 rad/s, 105 deg per frame, so velocity was never
the constraint; its **effort limit is 5 N.m, the smallest on the robot**, and
torque is.

`continuity.py` interpolates through a clipped run when the step at its boundary
is both over 20 deg and over five times that joint's own median step. Two details
earned themselves:

* **the whole Euler triple is repaired, not the clipped axis.** Only the roll
  saturates; the *yaw* is what jumps. Repairing roll alone left the worst step at
  87.11 deg, unchanged.
* **selective, so it cannot undo the pass before it.** The foot solve
  deliberately drives ankles and hips onto their limits -- 45 of the 47 saturated
  joint-frames in the clip -- and those runs are smooth on both sides, so the
  boundary test leaves them alone.

```
worst single-frame command step   87.11 -> 29.06 deg
tracking RMSE                     0.410 -> 0.165 deg
worst joint                       22.06 -> 3.19 deg
```

Two more of the session's own errors were caught by looking at the render rather
than the numbers, and both had every number right:

* **the floor was a `UsdGeom.Plane`** -- it collides but does not draw, so the
  first video was a robot and a seat in white space. Swapping it for a slab also
  took the tracking RMSE from 3.86 to **0.41 deg** and the feet from 0.0716 to
  **0.0099 m**: an infinite-plane collider was costing accuracy as well as
  pixels.
* **the root was applied twice** -- `/World/G1` already carries it, and the bake
  added it to each link as well, so the robot played back at z 1.19 instead of
  0.59. It read as hovering a metre above its own seat while every authored
  value was correct.

### What still fails, and whose fault it is

    [FAIL] physics.tracking_rmse                 3.77 deg   / 3
    [FAIL] physics.tracking_max.right_wrist_yaw  21.3 deg   / 10
    [FAIL] invariant.feet_on_floor               0.2014 m   / 0.02
    [FAIL] retarget.commanded_feet_on_floor      0.1028 m   / 0.02

The last line is the one that matters. It is computed on the host, by forward
kinematics, with no simulator involved: **with the pelvis exactly where the
retarget asked, v1's own trajectory puts the soles between −0.055 m and
+0.103 m.** The feet are 10 cm in the air on some frames and 5.5 cm through the
floor on others, travelling 0.158 m vertically in a clip where the subject never
stands up.

Physics cannot put a foot on a floor the trajectory never sends it to. So about
half of the 0.2014 m foot error is inherited, and the rest is tracking. The
check is in the ledger under `retarget.` rather than `physics.` for that reason
— **the pass now says which stage owes the fix**, which is what an error ledger
is for.

That is the next piece of work: the retarget has to be told the feet are on the
floor. The invariant that will grade it is already written.

### The root is not the chair

With the fitted seat the robot stops falling — `invariant.pelvis_not_falling`
went to **ok, 0.0137 m of drift** — but it comes to rest in the wrong
configuration (pelvis 0.201 m, feet 0.74 m up): it settles onto its back rather
than onto the seat. A seated clip does not test balance, so the root should
follow the retarget's pelvis trajectory rather than fall. Teleporting it there
each step was tried and is measurably worse:

    free      pelvis 0.5929 -> 0.201 (rests)      feet 0.74 m up
    driven    pelvis 0.5929 -> 0.834 (climbing)   feet 2.09 m up

Setting a dynamic body's world pose every step implies an enormous velocity and
PhysX converts it to energy. The right implementation is a **kinematic root** --
flag the pelvis so the solver may not move it, or pin it to the world with a
joint whose target follows the trajectory. `--root-mode driven` is left in place
only so that measurement stays reproducible; the default is back to `free`.

### What it does not yet do

The seat is placed at the origin because **object placement is still deferred** —
`fit_scene_to_target` fixes heights, not positions. The thighs extend forward of
a seat that is centred under the pelvis, so on this run nothing was in contact
with anything. Fixing the retarget and solving placement are the same next step,
and the invariants above are already written to grade it.

## The floor, and why it matters more than the tiers

Tags alone are not a brake. `provenance.check_floor()` fails a run when
`measured + derived` drops below **70 %** of the weighted output. Below that the
result stops being evidence that canonical CBD can drive this target, which is
the claim the whole `06_groot_g1/` output exists to make.

Sample dataset: **measured 91.8 % / derived 8.2 %, PASS.** With the detector
fully disabled: **94.6 %, PASS**, with 5.4 % synthesized and declared.

## What this asks of the adapter contract

The repository says: *"If a rule blocks you, that is interesting: it probably
means the schema is missing something. Open an issue."* Three did.

1. **Rule 5 wants a second reading.** As written it prefers refusal over
   approximation. A target with fixed link lengths cannot use refusal — a
   dropped channel becomes a broken robot, not a blank one. Proposed wording:
   *approximate where the target requires it, and declare the tier of every
   quantity you approximate.* The ledger is the mechanism.
2. **`phase` needs a validity signal.** A field that is legally "Idle" for every
   frame is indistinguishable from a field that means it. A per-clip confidence,
   or an explicit `unknown`, would let a consumer tell them apart without
   re-deriving the phase from the pose.
3. **Nothing states what the subject is supported by.** Seatedness is
   recoverable from knee flexion, but *what* is being sat on is not in the
   schema — `scene_objects` reports this as a spec gap whenever it has to
   synthesize a seat. A `support` relation in the interactions stream would
   close it.

None of these are blocking: v2 runs today under the rules as written, because
synthesis stays on the adapter's side of the boundary. They are the issues the
README invites.

## The check that could not fail

Every number above was right, and the render was still wrong in the first place
a person looks: **the robot's toes were 87 mm underground.**

`invariant.feet_on_floor` reported 0.0097 m and was correct about what it
measured. Both it and `foot_contact` modelled the sole as the single point
0.035 m below the ankle roll frame. That point was on the floor. The foot was
not — the clip commands 27 to 30 deg of ankle pitch, and one point leaves the
foot polygon free to rotate about it, driving the toe under while lifting the
heel 38 mm clear. `physics_settle` had the same model: it subtracted 0.035 from
the ankle link's world *height*, ignoring the orientation it could have read
from the same call.

The URDF has been carrying the answer the whole time. Four contact spheres per
foot — heel at x = -0.050, toe at x = +0.120, all at z = -0.030 with radius
0.005 — and the shipped asset's visual mesh bottoms out at z = -0.0354, so the
spheres and the render agree to 0.4 mm. `FOOT_CONTACT_LOCAL` is those four
points; the solve puts all four on the floor (three constraints on a six-joint
leg, so the minimum-intervention property survives) and the physics pass
measures all four from the ankle's simulated pose.

    commanded sole corners   -0.118 .. +0.182  ->  -0.000 .. +0.004 m
    deepest penetration       0.118            ->   0.000 m
    worst foot tilt           0.101            ->   0.001 m
    physics feet_on_floor     0.0097 (1 point) ->   0.0042 m (4 corners)
    cost                      24.7 deg, right ankle pitch

**A check that shares its model with the solve it grades cannot fail.** That is
the generalisable finding, and it is worth more than the fix: an invariant has
to carry its own geometry, independently of whatever produced the pose.

## Placement — the table, the glass, and four ways to get it wrong

`placement.py` runs the design's priority order as a *sequence* rather than
folding it into one least-squares. Each stage may overrule the one below it,
and every overrule is a number in the ledger.

    A  image estimate   bbox centre through the dataset's own image-plane fit,
                        depth from apparent size against the catalog
    B  task binding     the handled object goes on the acting hand's grasp
                        centre -- palm and middle fingertip, midpoint
    C  support          the surface under it is solved for the height it rests
                        at, the same rule the seat follows
    D  carve            pull the near edge back, then lower the top, until no
                        robot geometry is inside the surface

Four implementation errors, each caught by a number rather than by reading:

1. **Scene scale in the depth estimate.** The image and the canonical metres it
   maps to are the *subject's* world at the subject's size; the scene scale
   belongs to the robot's. Using scaled catalog dimensions biases every depth
   by 1/scale — it read the glass at 0.56x the subject's distance, half a metre
   of error out of an estimate that is otherwise good to a few percent.
2. **Cropped bbox sides.** The table's box ends at u = 0.987 and its width
   claims the table is 3.4x further away than the subject; its uncropped height
   says 1.05x, which is right. A side touching the frame edge is a lower bound,
   not a measurement, and is dropped.
3. **A link origin is not a link.** Carving against link origins called a table
   clear with a hand's collision mesh 17.5 mm inside it. One radius per link is
   the opposite error: the G1's thigh collider is 0.63 m long, so its
   half-diagonal is 0.315 m and a single link swallows the scene. The asset's
   collision bounds are kept as a *box per link* and rotated with it.
4. **Point-vs-slab depth.** `min(b, hi) - max(a, lo)` is zero for a zero-width
   span however deep it sits, so a fingertip 17.5 mm inside a tabletop measured
   as no overlap at all. A span wholly inside a band is as deep as its nearest
   way out.

### Why the table has no collider

With the geometry measured properly, no solid surface fits this clip. Reaching
for the glass takes the hand through the plane the glass rests on — 22.3 mm at
worst, on 10 frames of 96, all approach or withdrawal — and the best top that
clears the sweep is 0.590 m, which is 0.125 m below where the hand holds the
glass. The trade is between priority 1 (nothing penetrates) and priority 2 (the
task happens), and neither can be had whole.

So the table is **scenery**: geometry at the right height, collider disabled,
residual overlap in the ledger as `scene.dining table.reach_overlap`. This is
the seat's rule — "with the pelvis pinned the seat carries no load, and a box
that fights the legs is worse than no box" — applied to a surface nothing leans
on. The overlap is the whole-body reach's to fix, and the reach's own cause is
upstream of the arm: `chest` and both `shoulder` bones carry no rotation signal
in this dataset, so the waist moves in yaw only and a reach to the subject's
side comes out as a reach to the robot's front.

The same reasoning, measured, for the glass:

| | tracking RMSE | worst joint |
|---|---|---|
| no props | **0.165 deg** | 2.96 |
| glass as a kinematic body, `collisionEnabled` false | 9.52 deg | 135.5 (right wrist) |
| glass animated, table solid | 8.38 deg | 119.8 |
| **glass animated, table scenery** | **0.165 deg** | **2.96** |

Nothing closes the fingers on the glass, so a body driven along the hand is a
body inside the hand. `robot_stage.py --no-props` builds the floor-and-seat
scene that produced the first row; a props regression is one container run
away from being attributed.

### The grasp is not the phase boundary

`carried_track` first held the object from the first hold frame to the last. A
phase boundary is where the *pose* changes character; a grasp is where the hand
arrives at the object, and on this clip they are seven frames apart — the
object jumped 87 mm into the hand as the label changed. `grasp_span` takes the
frame where the hand comes closest to the object at rest, and records the
27 mm that remain.

### One more that only the render showed

The scene layer's `timeCodesPerSecond` defaulted to 24 against a 12 fps root,
and USD rescales a sublayer's time samples by that ratio: every prop ran at
double speed. The glass was at the robot's mouth on frame 26 and back on the
table by frame 50 — frames 52 and 100 of a 96-frame clip. Same family as the
doubled root transform: correct numbers, composed wrong.

## Next, and what it needs

1. **whole-body reach** — when the G1's arm cannot span what the subject's did,
   lean and step rather than fake the joint angles. It is now the binding
   constraint: it owns the 0.296 m between where the image puts the glass and
   where the hand goes, and the 22.3 mm that keep the table from being solid.
   Upstream of it, the four bones with no rotation signal are what the
   specification could supply.
2. **generality** — three clips with different furniture, a standing subject
   and a partially-framed one. Everything above has been measured on one clip
   and four degraded variants of it.
3. **a grasp** — closing the fingers under physics would let the prop be a
   rigid body and make `invariant.hand_contact` a measurement rather than a
   construction. The section below is the plan, and why the two cheaper things
   that were tried instead do not work.

## The grasp, and two wrong turns before it

The curl fix (`CURL_JOINTS_PER_FINGER`, above) closed the hand from a third of
the subject's grip to all of it, and the carried cylinder **disappeared inside
the fist**. Everything in this section was measured on the sample clip, over
the hold, frames 21-83, with the cylinder at r = 0.0308 m and h = 0.0685 m.

### Wrong turn 1: offset the object from the palm by its radius

The reasoning was that the grasp centre — the midpoint of the palm and the
middle fingertip — is defined without reference to the object, so an object of
any size lands at the same point, and pushing it out along the palm normal by
its own radius would seat it in the grip. In the palm's own frame the object
already sits at y = 0.038 m from the palm plane against a radius of 0.0308 m.
**The offset is the distance it already has.** There was nothing to correct.

### Wrong turn 2: move the object to the pinch point

If not against the palm, then in the opening — the midpoint of the thumb tip
and the middle fingertip, where opposed fingers actually pinch. Measured, the
deepest hand link inside the cylinder over the hold:

| grasp centre | worst | mean | frames with any |
|---|---|---|---|
| current (palm .. middle tip) | 17.3 mm | 3.7 mm | 37/63 |
| pinch (thumb tip .. middle tip) | **22.1 mm** | 11.5 mm | 63/63 |
| pinch (thumb tip .. index+middle) | **26.6 mm** | 18.3 mm | 63/63 |

Both are worse, and both penetrate on every frame of the hold. Moving the
object into the opening moves it into the fingertips.

### What the measurement actually says

There is no room. The largest cylinder that clears every hand link origin:

| centre | worst frame | median frame |
|---|---|---|
| current | **26.9 mm** diameter | 60.9 mm |
| pinch | **17.4 mm** diameter | 38.7 mm |

The cup is **61.6 mm** across. On the worst frames the closed hand has less
than half the room it needs, so **no placement of this object avoids the
links**. It is not a placement problem.

It is the arm's problem, one joint further down. The finger angles are copied
from the subject — 99 deg of curl, correct for a human hand round a human-sized
glass — and applied to a Dex3 that is not that hand, holding an object that is
not that glass. Matching joint angles and missing the object is exactly what
[What is left](README.md#what-is-left) #1 says about the reach; the fingers are
the same failure at a smaller scale, and the design's priority order — the task
above fidelity to the source — is what settles it. **The curl during a hold is
the adapter's to solve, not the subject's to dictate.**

### The plan

Bisect each finger's curl until its links are tangent to the object, during
hold frames only:

1. `phases.py` already says which frames are a hold and which hand acts.
2. For that hand, each finger's curl enters `hand()` as one scalar which is then
   split across its two Dex3 joints. Penetration is monotonic in that scalar, so
   a bisection on it — 20 iterations, no IK, no solver library — finds the curl
   at which the finger's links first touch the object's surface.
3. Clamp to the subject's own curl: the robot never closes *further* than the
   subject did, only less far. A hold where the object is too small for the hand
   comes out as a hand that cannot close on it, which is the honest result and
   is what the report should say.
4. Ease the clamp in and out across the hold boundary so the command stays
   continuous — `continuity.py`'s 20 deg / 5x median rule is the check.
5. Record it: a new deviation `grasp.finger_penetration` (asked 0), the curl
   given up per finger in degrees, and the tier — `synthesized`, because the
   adapter authored it to keep the target consistent.

What it buys, in order of what matters: the fingers stop at the object's
surface, so **penetration goes to zero by construction rather than staying a
number in the ledger**; the cylinder becomes visible between the fingers, which
is what a viewer checks first; `invariant.hand_contact` becomes a measurement
rather than a construction; and the prop can then be a rigid body, which is the
one thing standing between this and a physically simulated manipulation.

Cost: no new dependency. `physics_settle` must re-run because the fingers are in
the articulation (~15 min GPU), then bake, render (~10 min) and compose.

### The other thing this exposed

The handled object's dimensions are multiplied by the **scene scale** (0.6849),
so the catalog's 90 mm cup is built at 61.6 mm. The scene scale exists because a
1.32 m G1 cannot use furniture derived from a taller subject — but the hand that
holds this object is the real G1 hand, at 100%. A manipuland is not scenery, and
scaling it to the room while the gripper stays unscaled is a decision nobody
made deliberately. Note it does **not** explain the fist: unscaled the cylinder
would be 90 mm, which fits the closed hand even worse. Worth settling on its own
terms, after the grasp solve, not as a fix for this.
