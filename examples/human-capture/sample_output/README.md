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
- output/06_groot_g1 ........... the motion retargeted onto a Unitree G1, plus a
  GR00T-LeRobot dataset and a render
- output/07_groot_g1_v2 ........ the same clip on the real G1 asset, corrected,
  put through PhysX, and with the scene it acts in

`06_groot_g1/` and `05_comparison/motion_comparison_4pane.mp4` were added later
than the rest of this bundle, by
[`adapters/isaac_sim_groot_g1/`](../../../adapters/isaac_sim_groot_g1/).
Everything in them is derived from `04_behavior_dataset/` — the same master data
the other three adapters read — so they can be deleted and rebuilt.

`06_groot_g1/` is this clip on a machine instead of a figure. A Unitree G1 has
fixed link lengths and hard joint limits, so the motion is solved into its
43-DoF joint space rather than copied, the set is scaled to the robot instead of
the robot to the subject, and the leftover is reported in degrees per segment
(6.87° mean). `06_groot_g1/adapter_report.json` also names every joint that ends
up resting on a limit — on this clip both ankle pitch joints, in all 96 frames —
and records where every number in the set came from. The render is framed to
match `source/source_video.mp4`: its camera is fitted from the dataset's own
paired image/canonical landmarks rather than placed by eye.

Nothing stands on the table. This clip detected the cup in a single frame and
fired no interaction candidates, so there is no evidence the object was ever
grasped or moved; the table's own height is still derived from the frame where
the primary hand reached furthest, and `set_placement` in the report says so.
No GR00T policy was run either — the dataset under `06_groot_g1/groot_lerobot/`
is what a policy would be trained or replayed on, not its output.

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

Both directories are kept. `06_groot_g1/` is what an adapter that only asserts
what it can prove produces; `07_groot_g1_v2/` is what one that fills the gaps
and labels every fill produces. The difference between them is the argument.

The four-screen comparison `05_comparison/motion_comparison_4pane.mp4` is
overlay · MuJoCo · **Isaac Sim / GR00T G1** · Unity/VRM, built by
`05_comparison/build_comparison_4pane.py`.
