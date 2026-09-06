# `07_groot_g1_v2/` — the trajectory that survived physics

The v2 output of `adapters/isaac_sim_groot_g1/`. Same input as `06_groot_g1/` —
nothing but canonical CBD — and five differences that matter:

1. **the real robot.** `g1_29dof_with_hand_rev_1_0.usd` (87 meshes, 43 revolute
   joints, the asset IsaacLab Arena drove), referenced by URL, never vendored.
   v1 built a stand-in out of capsules.
2. **physics ran.** v1's report says `"policy_was_run": false` and "nothing here
   is a dynamically feasible G1 trajectory". These angles are `q_actual` — what
   the robot did with contact, self-collision and gravity resolved — not
   `q_target`.
3. **the feet are on the floor** — the whole foot. A sole is the four contact
   spheres the URDF gives each `ankle_roll_link`, not the single point under
   the ankle: with 27–30 deg of commanded ankle pitch, that point can sit 3 mm
   off the floor while the toe is 87 mm under it, which is what the first
   render showed and what every number in the first report missed. All four
   corners are now solved and measured. Commanded penetration 0.118 m → 0.000;
   after physics the worst corner is 4.2 mm off the floor and 0.3 mm into it.
4. **the table and the glass are there.** `placement.py` puts the handled
   object on the hand that holds it, and the surface under it at the height it
   rests. v1 wrote "no glass, cup or other prop is placed" and the robot mimed
   a grasp on empty air.
5. **the command is continuous.** v1's wrist decomposition clipped to a joint
   limit for two frames and came out of it with an 87 deg step, which no drive
   follows in 1/12 s on a joint whose effort limit is 5 N.m. Repaired to 29 deg.

## Files

    motion_baked.usda        the stage to open -- time samples only, no simulator
    motion_v2.usda           the live stage: references the asset, pins the root
      robot_v2.usda            the reference and the fixed base
      scene_v2.usda            floor, seat, table, the carried glass, physics scene
    motion_retarget.npz      the retarget this build stands on -- v1's, with the
                             finger-curl fix. v1's own `06_groot_g1/` is left as
                             it shipped, because every `change_from_v1` number is
                             measured against it
    motion.npz               q_actual, q_target and v1's angles side by side
    motion_v2.npz            q_target after the continuity and foot-contact passes
    g1_joint_trajectory.csv  43 joint angles per frame, q_actual
    groot_lerobot/           GR00T-LeRobot v2.1, v1's layout with the joints
                             swapped and the ego view re-rendered from this stage
    groot_g1_v2_simulation.mp4   96 frames, 12 fps, 720x1280
    settle_final.json/.npz   every deviation, and the physics result
    stage_report.json        the seat fit, the placement, the repairs, the invariants
    adapter_report.json      what this publishes and how far it moved

## What it measured

| check | asked | got | |
|---|---|---|---|
| `physics.tracking_rmse` | 0 | **0.180 deg** | ok (tol 3) |
| `physics.tracking_max` | 0 | 3.31 deg | ok (tol 10) |
| `invariant.feet_on_floor` | 0 | **0.0041 m** | ok (tol 0.02) |
| `invariant.feet_not_penetrating` | 0 | **0.0001 m** | ok (tol 0.005) |
| `retarget.commanded_feet_on_floor` | 0 | 0.0010 m | ok |
| `invariant.pelvis_holds_height` | 0.5929 | 0.5929 m | ok (1e-06) |
| `invariant.pelvis_not_falling` | 0 | 1e-07 m | ok |
| `invariant.seated.knee_min` / `knee_max` | 60–140 | 119.6 / 133.7 deg | ok |
| `invariant.hand_contact` | 0 | 0 m | ok (tol 0.02) |

**Nine of nine**, and the ninth was deferred until there was something to hold.

Distance from v1: **19.72 deg RMSE, 79.7 deg worst joint** — the right wrist
from the continuity repair, the legs from the foot-contact solve, and the ten
finger joints from the curl-semantics fix (`right_hand_middle_1` moves
60.5 deg). v1's `06_groot_g1/` is deliberately left as it shipped, since it is
the baseline this number is measured against; the corrected retarget this build
stands on is `motion_retarget.npz`.

## The seat

Its height, footprint and thickness are solved for *this robot in this pose*,
not taken from furniture dimensions. A G1 on a stock 0.45 m chair has its feet
0.097 m off the floor: "seated" and "feet on the floor" are both true of the
source clip and human-sized furniture lets a G1 hold only one of them.

The footprint is carved out of the space the robot never occupies — every leg
link, every frame — which is why it is a 110 mm pad rather than a chair. Three
earlier shapes each collided with the legs and each cost a container run to
diagnose; the numbers are in `../../../adapters/isaac_sim_groot_g1/V2_PROPOSAL.md`.

## The table and the glass

The glass is the clip's `primary_object`, detected in **one frame of 96**.
`scene_objects.py` keeps it anyway, on the strength of the caption and the
behaviour summary; `placement.py` is what finally puts it somewhere.

    glass    on the acting hand's grasp centre -- the midpoint of the palm and
             the middle fingertip -- from frame 20, where the hand first
             reaches it, to frame 84, where it last leaves. Resting on the
             table before and after, at the pick-up and put-down positions.
    table    top at 0.7155 m: where the glass rests, less half its height.
             The catalog's 0.75 m at scene scale would be 0.5137 m; a support
             surface is solved for the target, exactly as the seat is.
             Footprint 0.82 x 0.55 m at the one scene scale, near edge across
             the reach, on four legs rather than a block to the floor.

Two numbers are worth reading before trusting the picture:

* `scene.cup.image_vs_hand` = **0.296 m**. That is how far the glass is from
  where the image says it is. The image is not wrong — its depth-from-apparent-
  size estimate is good to a few percent on the person, the chair and the
  table. The *arm* is: `chest` and both `shoulder` bones carry no rotation in
  this dataset, so the waist moves in yaw only and a reach to the subject's
  side comes out as a reach to the robot's front. The design's priority order
  puts the task above faithfulness, so the glass goes where the hand is and
  this number goes in the ledger.
* `scene.dining table.reach_overlap` = **0.0223 m** on 10 frames of 96. The
  reach passes through the plane the glass rests on, on the way in and on the
  way out. No solid surface avoids that: the best top that clears the sweep is
  0.590 m, which is 0.125 m below the glass. So the table is **scenery** —
  geometry at the right height with its collider disabled — and the overlap is
  the reach's to fix, not the placement's.

The glass is animated rather than simulated for a measured reason: nothing
closes the fingers on it, so a body driven along the hand is a body inside the
hand. The same clip measures 0.165 deg tracking RMSE without the prop and
9.52 deg — 135 deg on the right wrist — with it present as a kinematic body.

**It is inside the fist for the whole hold, and that is the current defect.**
The finger curls are the subject's, and after the curl-semantics fix they are
all of the subject's — 99 deg, correct for a human hand round a human-sized
glass. Applied to a Dex3 holding a 61.6 mm cylinder they close past its
surface: the largest cylinder that clears every hand link is 26.9 mm across on
the worst frame. Placement cannot fix it — both alternatives measured worse —
and the fix is a solve that closes each finger onto the object's own radius.
`../../../adapters/isaac_sim_groot_g1/V2_PROPOSAL.md` has the plan and the
numbers. The prop is visible whenever it rests on the table, which is every
frame outside 20-83.

It is drawn as a **plain grey upright cylinder**, 0.062 m across and 0.069 m
tall at the scene scale, and that is a claim about evidence rather than a
placeholder. The catalog used to point `cup` at `Props/YCB/Axis_Aligned/025_mug.usd`;
what CBD actually carries is the COCO label `cup` and a caption that says *a
glass of water*. Nothing measured a handle, a glaze or a taper, so drawing one
would assert a shape the data does not support — and a viewer reads a rendered
mug as something the pipeline knew. The cylinder is the class's own metric
prior and no more, which is what `source: prior` means in
`object_catalog.json`. 75 of the 80 classes there are primitives for the same
reason.

## Reproducing it

```bash
python v2_preview.py     --dataset <sample_output>          # host, no GPU
python robot_stage.py    --dataset <sample_output> --asset-root <mirror>
# Isaac Sim container, GPU:
python physics_settle.py --stage .../motion_v2.usda --motion .../motion_v2.npz \
                         --invariants .../stage_report.json --report <out>.json
python bake_motion.py    --stage .../motion_v2.usda --settle <out>.npz \
                         --stage-report .../stage_report.json --out motion_baked.usda
python groot_g1_render.py --stage motion_baked.usda --out <frames> \
                         --ego-camera /World/G1/d435_link/ego_cam
# host:
python finalize.py       --dataset <sample_output>
python compose_video.py  --frames <frames> --dataset <...>/04_behavior_dataset \
                         --out-dir <...>/07_groot_g1_v2 \
                         --name groot_g1_v2_simulation.mp4
```

`finalize` before `compose_video`: finalize rebuilds `groot_lerobot/` from v1's
copy, and compose is what writes the ego view into it.

**The shipped `robot_v2.usda` references a local mirror.** This build was made
on the GPU VM (see the adapter README's *Where this runs*), so the reference in
the committed file reads `/mnt/data/assets/isaac/Samples/Groot/Robots/...` and
will not resolve on your machine. `robot_stage.py` defaults to NVIDIA's **public**
asset server when `--asset-root` is omitted, so re-running it writes a stage that
opens anywhere. To open the committed files as they are, edit that one
`prepend references` line in `robot_v2.usda` to the public URL or to your own
mirror — `motion_v2.usda` and `motion_baked.usda` both sublayer it, so the one
edit fixes both.

Mount a local asset mirror at the **same path inside the container** as outside:
the stage references the asset absolutely, so `-v /path:/path:ro`. On this clip
the only referenced asset is the robot; a mirror that also serves catalog props
needs their textures beside them (`Props/YCB/Axis_Aligned/Materials/Textures/`
for the YCB ones), or the material resolves to nothing.

`robot_stage.py --no-props` builds the floor-and-seat scene with no placement
solve. It is the isolation switch: a tracking regression is either the props or
it is not, and one container run says which.
