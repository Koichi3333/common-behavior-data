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
- output/05_comparison ......... three-screen comparison video
