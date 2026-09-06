<!-- Note added when this bundle was committed to the repository. -->
> **This is a real, unedited run of [Demo A](../README.md).** It is the
> `demo2_output_bundle.zip` produced by cell `[10]`, unpacked. The notebook
> writes these directories under `output/`; that one prefix was dropped when the
> bundle was copied into the repository, so paths below read one level deeper
> than what you see here.
>
> Start with `04_behavior_dataset/` — that directory is the master data, and
> everything else is derived from it.
>
> One honest caveat: in this clip the cup was detected in only one frame, so no
> interaction candidates fired and every frame's phase is `Idle`. That is
> explained in [the demo README](../README.md#what-this-sample-gets-wrong-and-why-we-shipped-it-anyway).

---

# Human Behavior Demo 2.0

One source video becomes one reusable Human Behavior Dataset for
avatars, simulation, analytics, and Physical AI.

- output/01_mediapipe_overlay ... MediaPipe overlay video
- output/02_mujoco ............. humanoid.xml + motion.npz + replay
- output/03_unity_vrm .......... motion.vrma (play locally with Unity/UniVRM)
- output/04_behavior_dataset ... master Common Behavior Data
- output/05_comparison ......... three- and four-screen comparison videos
- output/07_groot_g1_v2 ........ the clip on the real G1 asset, corrected, put
  through PhysX, and with the scene it acts in

`07_groot_g1_v2/` and `05_comparison/motion_comparison_4pane.mp4` were added
later than the rest of this bundle, by
[`adapters/isaac_sim_groot_g1/`](../../../adapters/isaac_sim_groot_g1/).
Everything in them is derived from `04_behavior_dataset/` — the same master data
the other three adapters read — so they can be deleted and rebuilt.

**There is no `06_groot_g1/` here, and the numbering says so on purpose.** That
directory is the adapter's v1 output, and it is now an *intermediate*: stage 1
(`cbd_adapter_groot_g1.py`) writes it from canonical CBD, the v2 stages read the
retarget out of it, and it is gitignored rather than shipped. Re-running stage 1
recreates it. What v1 *found* is not gone — it is in v2's own files, as numbers
rather than as 2 MB of regenerable binaries:
`07_groot_g1_v2/adapter_report.json` carries `change_from_v1_deg` (6.93° RMSE,
79.65° at `right_wrist_roll_joint`, with the eight worst joints named), and
`07_groot_g1_v2/motion.npz` carries `joint_angles_v1_rad` — v1's full 96×43
trajectory, beside the one that survived physics.

The retarget is this clip on a machine instead of a figure. A Unitree G1 has
fixed link lengths and hard joint limits, so the motion is solved into its
43-DoF joint space rather than copied, the set is scaled to the robot instead of
the robot to the subject, and the leftover is reported in degrees per segment.
`07_groot_g1_v2/adapter_report.json` also names every joint that ends up resting
on a limit and records where every number in the set came from. The render is
framed to match `source/source_video.mp4`: its camera is fitted from the
dataset's own paired image/canonical landmarks rather than placed by eye.

That much v1 already did, and it stopped there. Nothing stood on the table: this
clip detected the cup in a single frame and fired no interaction candidates, so
v1 read that as no evidence the object was ever grasped or moved. No GR00T
policy was run either — the dataset under `07_groot_g1_v2/groot_lerobot/` is
still what a policy would be trained or replayed on, not its output.

`07_groot_g1_v2/` is the answer to that paragraph. It reads the same master
data and changes what the adapter is willing to decide:

* **the vendor's robot**, referenced rather than rebuilt from capsules
* **physics**, so the published angles are what a position-drive controller
  actually tracked rather than what the retarget asked for
* **the feet on the floor** — the whole foot. A sole is the four contact
  spheres the URDF gives each ankle, not the point under it: one point leaves
  the foot free to pitch about it, and this clip's 27–30° of ankle pitch put
  the toe 87 mm underground while every number in the report read correct
* **the glass and the table**. One detection in 96 frames is not evidence the
  object does not exist — the caption, the behaviour summary and the wrist's
  own travel all say it does. `07_groot_g1_v2/` places it, on the hand that
  holds it, over a surface solved for the height it rests at, and records how
  far that is from where the image alone would have put it

v1 is what an adapter that only asserts what it can prove produces;
`07_groot_g1_v2/` is what one that fills the gaps and labels every fill
produces. The difference between them is the argument — which is why it is
kept as a measurement (`change_from_v1_deg`, `joint_angles_v1_rad`) rather than
as a second copy of the outputs.

The four-screen comparison `05_comparison/motion_comparison_4pane.mp4` is
overlay · MuJoCo · **Isaac Sim / GR00T G1** · Unity/VRM, built by
`05_comparison/build_comparison_4pane.py`.
