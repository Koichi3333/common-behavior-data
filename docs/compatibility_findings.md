# Compatibility findings

[← back to README](../README.md) · [Adapters](../adapters/README.md) ·
[Specification](../specification/README.md) · [Limitations](limitations.md)

**One sentence:** *What survived the trip to each target, what broke, how it was
corrected, and how much the correction changed — kept as a record, because the
differences are the most useful thing this project produces.*

A behavior representation is only interesting if something reuses it. The moment
something does, you learn where it is thin. This page is the running register of
that: one row per thing that broke, with the target it broke on, what was done
about it, and where the fix has to live.

It is **not** a bug list. Most of these are not defects in an adapter — they are
places where two embodiments genuinely disagree, and the disagreement is the
finding.

## Why this page exists at all

The repository deliberately does **not** share code between adapters
([adapter rule: self-contained over DRY](../adapters/README.md#self-contained-beats-dry)).
Physics assumptions differ per simulator; body structure differs per robot; a
shared helper would have to be right for all of them and would quietly become
wrong for each.

Knowledge is the part that *should* be shared. So: code stays inside its
adapter, findings come here.

```text
Adapter finding
      │
      ├──▶ another adapter        "try this idea, in your own terms"
      ├──▶ the generator          "this channel is missing / degenerate"
      └──▶ the specification      "this belongs in canonical CBD"
```

## How to classify a finding

Before writing one down, decide which of these it is — the four have completely
different consequences:

| Class | Meaning | Who fixes it |
|---|---|---|
| **Source issue** | the capture itself was bad | recapture, or the generator's robustness |
| **Generator issue** | the channel exists in the spec but is written wrong or empty | [`generators/`](../generators/) |
| **Specification gap** | canonical CBD carries no such channel at all | [`specification/`](../specification/) — after a generality check |
| **Target constraint** | this target simply cannot do it | the adapter, and it is reported, not hidden |

The first three flow upstream. The last one stays local and is **published as a
number**, never silently approximated.

## Findings so far

Everything below comes from
[`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) — the first
target that is a machine rather than a figure built to the subject. That is not
a coincidence: the notebook adapters animate a body shaped like the subject, so
they can absorb almost anything. A robot cannot.

### Specification gaps

| Finding | Where it showed up | Consequence | Status |
|---|---|---|---|
| **Four bones carry no rotation** — `chest`, `neck`, `left_shoulder`, `right_shoulder` are identity in every frame (4 of 19) | G1 | The waist can only yaw, so a reach to the subject's *side* comes out as a reach to the robot's *front*. Largest remaining error in the output: 0.296 m of hand-vs-image disagreement | Open — the binding constraint |
| **No support relation** — nothing says what the subject rests on, or what rests on what | G1 | The seat had to be solved from the retargeted pelvis; the result is a 110 mm pad, not a chair | Open — proposed as a canonical channel |
| **`phase` has no validity signal** | G1 | All 96 frames of a pick-and-place clip read `("Pick And Place", "Idle")`, and the adapter has no way to know that from the data — it has to test the field's informativeness itself | Open |
| **No real scale is declared** | G1 | Canonical space is metre-ish but derived from monocular estimation. Load-bearing the moment a 1.32 m robot must sit on furniture derived from a taller subject | Open — [spec open questions](../specification/README.md#open-questions) |
| **No camera intrinsics** | G1 | An adapter that wants to place props in 3D must re-derive the image-to-canonical mapping itself from `human/pose_landmarks.csv` (3168 samples, 3.1 cm residual) and assume a camera distance | Open |
| **No force or contact channels** | G1 | Stands between a joint-space replay and a dynamically feasible trajectory. The adapter writes a GR00T-LeRobot dataset a policy could train on, and cannot say whether the robot could hold the pose | Open — [roadmap](roadmap.md) |

### Generator issues

| Finding | Where | Consequence | Status |
|---|---|---|---|
| **`interaction_events.csv` written as a header with no rows** | G1 | No contact phase available downstream; the adapter re-derives idle / reach / hold / retract from wrist excursion, for solver weighting only — never written back as CBD interactions (adapter rule 4) | Reported |
| **Limb geometry that no body can hold** — right knee 19 cm across the midline, reach ratio 1.050 | G1 | Cleaned per-adapter: smoothing, a midline clamp in *direction* space for legs only, then a rebuild of every limb at median bone length. Cost: 2.1 cm mean displacement; crossings 96 → 0, bone-length drift 68 % → 0 % | Corrected in adapter, reported upstream |

### Target constraints — reported, not fixed

| Finding | Target | Number |
|---|---|---|
| Ankle pitch runs out of travel on a seated clip | G1 | **both ankle pitch joints on their limit in all 96 frames** — not solver error, the robot has no more travel |
| A fixed-length limb cannot match a reach in metres | G1 | motion is *solved* by direction matching, not copied; residual **6.87° mean** across all segments, 65.08° worst (palm normal) |
| A 1.32 m robot cannot use furniture sized for the subject | G1 | the **set** is scaled instead, by one reported number (`scale = 0.835`) — scaling the robot would be a fabrication about hardware |
| No neck; three fingers per hand | G1 | head pose and two fingers per hand are dropped. A 29-DoF G1 has no neck and a Dex3 has three fingers — not the generator's to fix |
| Kinematic replay is not contact | MuJoCo | playback is `qpos` + `mj_forward`; physical correctness of contact is not claimed. See [limitations](limitations.md) |

### Corrections that worked, and are worth borrowing

Ideas, not code. Each target should implement these in its own terms.

| Idea | Found on | Why it generalises |
|---|---|---|
| **Solve the sole as a contact polygon, not a point.** Using the URDF's four foot contact spheres instead of "one point 3.5 cm below the ankle" | G1 | Commanded penetration 0.118 m → **0.000 m**, foot tilt 0.101 m → 0.001 m. Any legged target measuring ground contact at a single point has the same latent bug — and the *check* was reporting a pass while the toes were 87 mm underground |
| **Publish what the physics returned, not what you asked for.** The shipped angles are `q_actual` after PhysX resolved contact, self-collision and gravity; `q_target` is kept beside it | G1 | Any target with a solver can do this. It turns "the adapter believes" into "the simulator agreed", and costs one extra array |
| **Interpolate gaps, do not hold the nearest value.** A 4-frame hand dropout filled by nearest neighbour put a gap's whole change on one frame — 26.9° of curl between adjacent frames | G1 | Applies to every channel with dropouts, in every adapter |
| **Read the spec for the quantity's definition before assuming it.** `finger_curls_rad` is *mean flexion per finger*; treating it as whole-finger flexion under-drove the hand by exactly 3× | G1 | The failure mode — assuming a unit rather than checking — is not target-specific |
| **Report residuals in the target's own units.** Degrees per segment, joints resting on limits with frame counts, millimetres of penetration | G1 | A residual in canonical units tells a target's user nothing |

## Adding a finding

When an adapter surfaces something, record it where the work happened *and*
here:

1. In the adapter's own README or report — **what worked, what broke, what was
   corrected, why, how much it changed, what is unresolved**.
2. Here, as a row, classified by the table above.
3. If it is a specification gap, take it to
   [`specification/`](../specification/README.md) only after asking whether it
   is general: needed by many targets, part of behavior itself, observable or
   derivable from the source, reusable. `G1 ankle limits` fails that test;
   `support relation` passes it.

A finding with a number attached is worth several without one.
