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

Start with one question, because it decides everything that follows:

```text
data gap    the record does not carry it      → closable upstream
body gap    the two bodies disagree           → not closable; publish the number
```

Then pick the class, which says **who** closes it. The four have completely
different consequences:

| Class | Which gap | Meaning | Who fixes it |
|---|---|---|---|
| **Source issue** | data | the capture itself was bad | recapture, or the generator's robustness |
| **Generator issue** | data | the channel exists in the spec but is written wrong or empty | [`generators/`](../generators/) |
| **Specification gap** | data | canonical CBD carries no such channel at all | [`specification/`](../specification/) — after a generality check |
| **Target constraint** | **body** | this target simply cannot do it | nobody. The adapter reports it, and it is not hidden |

The first three flow upstream. The last one stays local and is **published as a
number**, never silently approximated.

### One system, three vocabularies

`gap` is the reader's entrance, the class says who owns it, and the provenance
tier is what the data itself carries. They line up:

```text
gap (for a reader)      class (who owns it)        tier in the data (0.3.0)

data gap ──────────┬──  source issue          ──  coverage drops; notes
                   ├──  generator issue       ──  degenerate  (written, empty)
                   └──  specification gap     ──  absent  /  prior

body gap ───────────── target constraint      ──  (nothing)
                                                  published instead in the
                                                  adapter's own deviations,
                                                  in the target's units
```

**The asymmetry at the bottom is deliberate, and worth staring at.** A body gap
does not appear in the dataset's provenance at all — it cannot, because it is
not a property of the record. It belongs to the pair *(this behavior, this
target)*, so it lives in the adapter's report as
`asked` / `got` / `error` / `tolerance`. A reader who wants to know what CBD is
missing reads the tiers; a reader who wants to know what a G1 could not do reads
the adapter.

And the two are not independent: **a data gap becomes a body gap the moment the
body changes** — the four identity bones are a missing field that arrives on the
G1 as 0.296 m of reach error. See
[concept](concept.md#the-two-are-connected-and-that-is-the-interesting-part).

## Findings so far

Everything below comes from
[`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) — the first
target that is a machine rather than a figure built to the subject. That is not
a coincidence: the notebook adapters animate a body shaped like the subject, so
they can absorb almost anything. A robot cannot.

### Is the finding in the data, or only on this page?

Every row below has a column for it. This used to be the finding behind the
findings — the register was prose, and a consumer that read only the dataset
learned none of it.

**Dataset version `0.3.0` changed most of these answers.** The generator now
declares a tier per channel, and the gaps themselves are written down: see
[specification → generalising it](../specification/README.md#generalising-it).
Two caveats on reading the column:

- **"Yes, `0.3.0`" means the generator writes it, not that anything reads it.**
  No adapter consumes the field yet, and there is no validator.
- **The committed sample output is a `0.2.0` bundle** and carries none of it.

A **No** in the column still means *a consumer will get this wrong and will not
find out*.

### Specification gaps

| Finding | Where it showed up | Consequence | In the data? | Status |
|---|---|---|---|---|
| **Four bones carry no rotation** — `chest`, `neck`, `left_shoulder`, `right_shoulder` are identity in every frame (4 of 19) | G1 | The waist can only yaw, so a reach to the subject's *side* comes out as a reach to the robot's *front*. Largest remaining error in the output: 0.296 m of hand-vs-image disagreement. **Cause:** no pose landmark separates these bones from their parent, so the parent-relative rotation is identity by construction — not a capture failure | **Yes, `0.3.0`** — tier `degenerate` per bone, tested rather than listed, in the `provenance` column of `bone_rotations.csv` and in the ledger | Open — the binding constraint. Declaring it does not supply the rotation |
| **No support relation** — nothing says what the subject rests on, or what rests on what | G1 | The seat had to be solved from the retargeted pelvis; the result is a 110 mm pad, not a chair | **Yes, `0.3.0`** — an explicit `absent` entry with the consequence, so a consumer knows to solve it | Open — proposed as a canonical channel |
| **`phase` has no validity signal** | G1 | All 96 frames of a pick-and-place clip read `("Pick And Place", "Idle")`, and the adapter had no way to know that from the data — it tests the field's informativeness itself | **Yes, `0.3.0`** — tier `degenerate` with the label counts, plus a `quality.json` note. The adapter's own test should become a fallback | Closed in the generator; open until an adapter trusts the field |
| **No real scale is declared** | G1 | Canonical space is metre-ish but derived from monocular estimation. Load-bearing the moment a 1.32 m robot must sit on furniture derived from a taller subject | **Partly, `0.3.0`** — `manifest.canonical_scale` publishes the constant and the ledger marks it tier `prior`, so a consumer knows it is configured rather than measured. A *measured* scale still does not exist | Open — [spec open questions](../specification/README.md#open-questions) |
| **No camera intrinsics** | G1 | An adapter that wants to place props in 3D must re-derive the image-to-canonical mapping itself from `human/pose_landmarks.csv` (3168 samples, 3.1 cm residual) and assume a camera distance | **Yes, `0.3.0`** — an `absent` entry naming that consequence. The adapter already marked its assumed distance `prior — CBD records no camera intrinsics`; now both sides agree | Open |
| **No force or contact channels** | G1 | Stands between a joint-space replay and a dynamically feasible trajectory. The adapter writes a GR00T-LeRobot dataset a policy could train on, and cannot say whether the robot could hold the pose | **Yes, `0.3.0`** — `contact_and_force` is an `absent` entry. Declaring it is not carrying it | Open — [roadmap](roadmap.md) |
| **Quality metadata overstates coverage** — `object_coverage: 1.0` while 1 of 173 per-frame object entries carries a 3D position, and that one is `[NaN, NaN, 0.3]` | G1, and any consumer that trusts `quality.json` | The one file whose job is to report trustworthiness reported 2D detection presence under a name a consumer reads as 3D availability | **Fixed, `0.3.0`** — `coverage_definitions` states what each number counts, `object_position_3d_coverage` is published beside it, and a note fires when the two diverge. The original key is unchanged, so no consumer breaks | Closed in the generator |
| **No episode-level provenance** — nothing records the source's terms, or whether the episode was observed or generated | Demo B corpus; [`vla-maker-from-cbd`](https://github.com/Koichi3333/vla-maker-from-cbd) | Observed and generated episodes were indistinguishable downstream; the spec said so plainly — *"the format will not stop you"*. The second consumer trains on CBD, **emits CBD**, and carries a redistribution ban — *"AMASS-derived motion data must never be redistributed"* — that no CBD bundle could state about itself | **Yes, `0.3.0`** — `provenance.episode_kind` (`observed` / `generated`), `generated_by`, and `source.terms` / `redistributable` / `attribution` | Open until the producers set it: Demo B and the VLA both still emit CBD without it |
| **No locomotion phase, and no vocabulary for one** — the generator's phase labels, and the adapter's, are both `idle` / `reach` / `hold` / `retract` | G1; the VLA's generated walking | `foot_contact.contact_mask()` tests `any(l in ("walk","step"))`, which those labels can never satisfy, so a non-seated clip falls through to *"per-foot swing detection is not implemented, so no contact is asserted"* (tier `unavailable`) and the feet are never solved to the floor. Honest, and it means the G1 adapter cannot currently place a walking clip | **No** — a walking clip and a seated one are still the same shape of data. `0.3.0` publishes the phase labels present, which is a hint, not a locomotion channel | Open |
| **No finger bone rotations** — `bone_rotations.csv` carries 19 body bones and no fingers; hand state exists only as `finger_curls_rad` and landmarks | G1; the VLA | Two independent consumers now ask for the same channel. The VLA states it as *"CBD has no finger bones yet, so 'holding' is a check of whether the hand is close to the object"*; the G1 drops to two of three Dex3 fingers | **Partly** — the curls are present and documented, but nothing says they are not bone rotations | Open |

### Generator issues

| Finding | Where | Consequence | In the data? | Status |
|---|---|---|---|---|
| **`interaction_events.csv` written as a header with no rows** | G1 | No contact phase available downstream; the adapter re-derives idle / reach / hold / retract from wrist excursion, for solver weighting only — never written back as CBD interactions (adapter rule 4) | **Yes, `0.3.0`** — tier `absent` with the reason stated: *the state machine fired nothing, NOT that no contact occurred*. The empty table is unchanged | Reported; the detector's sensitivity is a separate issue |
| **Limb geometry that no body can hold** — right knee 19 cm across the midline, reach ratio 1.050 | G1 | Cleaned per-adapter: smoothing, a midline clamp in *direction* space for legs only, then a rebuild of every limb at median bone length. Cost: 2.1 cm mean displacement; crossings 96 → 0, bone-length drift 68 % → 0 % | **No** — the implausible geometry is written as plausible numbers | Corrected in adapter, reported upstream |

### Target constraints — reported, not fixed

| Finding | Target | Number |
|---|---|---|
| Ankle pitch runs out of travel on a seated clip | G1 | **both ankle pitch joints on their limit in all 96 frames** — not solver error, the robot has no more travel. Measured on the retarget stage; v2's contact-polygon foot solve then moves `right_ankle_pitch` by 24.8°, so this figure needs re-cutting against v2's own output |
| A fixed-length limb cannot match a reach in metres | G1 | motion is *solved* by direction matching, not copied; residual **6.87° mean** across all segments, 65.08° worst (palm normal) |
| A 1.32 m robot cannot use furniture sized for the subject | G1 | the **set** is scaled instead, by one reported number — `scale = 0.835` in v1, **`0.685` in v2**, which anchors it on the robot's own geometry rather than the subject's. Scaling the robot would be a fabrication about hardware |
| No neck; three fingers per hand | G1 | head pose and two fingers per hand are dropped. A 29-DoF G1 has no neck and a Dex3 has three fingers — not the generator's to fix |
| Kinematic replay is not contact | MuJoCo | playback is `qpos` + `mj_forward`; physical correctness of contact is not claimed. See [limitations](limitations.md) |

### Our own instrumentation

Outside the four classes above, because it is a defect in this repository's
reporting rather than in a representation or a target — and the register is the
right place for it.

| Finding | Where | Consequence | Status |
|---|---|---|---|
| **The provenance ledger grades a subset and reports a total.** As shipped, `stage_provenance` holds four entries — the legs solved for floor contact, two object placements, one wrist repair — totalling 1251 weight units against a 43-joint × 96-frame trajectory (4128 joint-frames) | G1 v2 | It reports *"measured+derived 99.8% >= floor 70%"* over roughly 30 % of the output. The retargeted arm, torso and waist joints are absent from it, and `measured` reads `0.0000` because the shipping path reaches no `measured` call site — not because the dataset was weighed and found empty. Same shape as the foot check that passed with the toes 87 mm underground | Open — [roadmap](roadmap.md#next-in-band-provenance) |
| **`spec_feedback` is implemented and unused.** `provenance.py` collects any fill tagged with a `spec_gap`; one call site sets the tag (`scene_objects.py`), and `continuity.py` explicitly passes `spec_gap=None` | G1 v2 | The channel designed to carry a schema gap back upstream ships as `{}`, so the adapter's own findings still travel only as prose on this page | Open |

### Corrections that worked, and are worth borrowing

Ideas, not code. Each target should implement these in its own terms.

| Idea | Found on | Why it generalises |
|---|---|---|
| **Solve the sole as a contact polygon, not a point.** Using the URDF's four foot contact spheres instead of "one point 3.5 cm below the ankle" | G1 | Commanded penetration 0.118 m → **0.000 m**, foot tilt 0.101 m → 0.001 m. Any legged target measuring ground contact at a single point has the same latent bug — and the *check* was reporting a pass while the toes were 87 mm underground |
| **Publish what the physics returned, not what you asked for.** The shipped angles are `q_actual` after PhysX resolved contact, self-collision and gravity; `q_target` is kept beside it | G1 | Any target with a solver can do this. It turns "the adapter believes" into "the simulator agreed", and costs one extra array |
| **Interpolate gaps, do not hold the nearest value.** A 4-frame hand dropout filled by nearest neighbour put a gap's whole change on one frame — 26.9° of curl between adjacent frames | G1 | Applies to every channel with dropouts, in every adapter |
| **Read the spec for the quantity's definition before assuming it.** `finger_curls_rad` is *mean flexion per finger*; treating it as whole-finger flexion under-drove the hand by exactly 3× | G1 | The failure mode — assuming a unit rather than checking — is not target-specific |
| **Report residuals in the target's own units.** Degrees per segment, joints resting on limits with frame counts, millimetres of penetration | G1 | A residual in canonical units tells a target's user nothing |
| **Grade your own output by where each quantity came from.** [`provenance.py`](../adapters/isaac_sim_groot_g1/provenance.py) tags every written quantity `measured` / `derived` / `prior` / `synthesized` / `unavailable`, weights it by channels × frames, and fails the run below a 70 % evidence floor | G1 | Any adapter can do this, and the result is a single number for how much of its output stands on the representation rather than on its own geometry. **Borrow the mechanism, not its coverage** — see the instrumentation defect below |
| **Detect a degenerate channel instead of trusting it.** `cbd_phase_is_informative()` returns false when every frame carries the same label; the adapter then re-derives phase from wrist excursion and records it as `derived`, never writing it back as an observed `grasp` | G1 | Every channel can be degenerate, and a populated field with one value is indistinguishable from an observation until something tests it. The test is four lines; the alternative is weighting a retarget against a signal that says nothing |
| **State deviations as `asked` / `got` / `error` / `tolerance` / `how`.** Nine checks across physics, contact and placement, each with a unit and a pass rule | G1 | It makes "the adapter worked" falsifiable, and a reader can disagree with a tolerance instead of with a conclusion |

## Adding a finding

When an adapter surfaces something, record it where the work happened *and*
here:

1. In the adapter's own README or report — **what worked, what broke, what was
   corrected, why, how much it changed, what is unresolved**.
2. Here, as a row, classified by the table above — including **In the data?**:
   could a consumer that reads only the dataset have detected this? If the
   answer is no, that is a second finding, and usually the more important one.
3. If it is a specification gap, take it to
   [`specification/`](../specification/README.md) only after asking whether it
   is general: needed by many targets, part of behavior itself, observable or
   derivable from the source, reusable. `G1 ankle limits` fails that test;
   `support relation` passes it.

A finding with a number attached is worth several without one.
