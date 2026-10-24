# `video_to_cbd/` — one video in, canonical CBD out

[← back to `generators/`](../README.md) ·
[Specification](../../specification/README.md)

**What is this?** The reference generator. One video of a person becomes one
canonical CBD dataset, and nothing else — no MuJoCo, no VRM, no overlay video.
Those are [adapters](../../adapters/), and `cbd_dataset.zip` is the hand-off
between them.

| | |
|---|---|
| **Input** | one video of a person, 10–30 s, single subject |
| **Output** | `cbd_dataset.zip` → `04_behavior_dataset/` |
| **Runs in** | Google Colab — **CLI recommended**, UI fully supported |
| **GPU** | T4 helps; CPU completes, just slower |

Notebook: [`cbd_generator_video_to_cbd.ipynb`](cbd_generator_video_to_cbd.ipynb)

## What it writes

```text
04_behavior_dataset/
├── manifest.json           index, fps, frame count, coordinate systems
├── behavior_summary.json   what happened, primary hand/object, events
├── runtime_info.json       how it was computed
├── timeline/
│   ├── frames.jsonl        ROW view — one line is one complete frame
│   └── frames/000000.jpg … one image per analysed frame
├── human/                  pose · hands · face · gestures · bone rotations · joint angles
├── objects/                detections (never rewritten) · tracks · label reclassification
├── interactions/           reach / contact / grasp / carry / release CANDIDATES
├── metrics/                motion and object metrics
├── quality/
│   ├── quality.json        per-modality coverage, what each number counts, notes
│   └── channel_provenance.json   a tier per channel: what each one stands on
└── captions/               optional, Gemini — temporal captions over phase windows
```

Field-by-field description: [`specification/README.md`](../../specification/README.md).

## Recommended: run it from the Colab CLI

The notebook runs from both entry points — it detects at runtime whether stdin
is available and degrades gracefully — but the **Colab CLI is the recommended
way**:

```bash
colab new -s cbd
colab upload -s cbd ./source_video.mp4 /content/source_video.mp4
colab exec   -s cbd -f cbd_generator_video_to_cbd.ipynb --timeout 1800
colab download -s cbd \
  /content/human_behavior_demo_2_0/cbd_dataset.zip ./cbd_dataset.zip
# keep the session alive to run the adapters on the same VM, then:
colab stop -s cbd
```

Why this is the recommended path:

- **One session, one dataset.** Leave the session up and every adapter notebook
  finds the dataset already unpacked in the runtime — no zip to re-upload, no
  chance of an adapter reading a different episode.
- **Nothing blocks.** In a headless run the notebook never opens an upload
  widget and never embeds a video player; it prints paths instead, so
  `colab exec` always terminates. `--timeout` applies **per cell** (1800 s is
  comfortable for a 10–30 s video).
- **Scriptable and repeatable.** The same four commands run from a shell script
  or CI, which is what makes a generator → adapter chain reproducible.

See [`docs/runtime_environments.md`](../../docs/runtime_environments.md) for why
this is the repository's default, and which single step does not follow it.

## Colab UI

`Runtime → Change runtime type → T4 GPU`, then run `[G1]` → `[G8]` in order
(`[G2]` asks for the video). CPU also completes.

## Optional: captions and object re-classification

Temporal captions and object re-classification need a Gemini key. In the UI, add
a Colab secret named `GEMINI_API_KEY` and grant the notebook access. Headless,
set it in the session before running the notebook:

```bash
colab exec -s cbd <<< 'import os; os.environ["GEMINI_API_KEY"] = "<key>"'
```

Without a key those two cells skip and every other output still works. No
credential is ever written into the notebook.

## Known data gaps — and the fact that the data now declares them

Every gap below is a **data gap**: the record does not carry it, so it is
closable here rather than in an adapter. A *body gap* — a 1.32 m robot with no
spine — is not this file's problem and never appears in a generator
([the distinction](../../docs/concept.md#the-problem)).

These gaps are real and unchanged. What changed in `0.3.0` is that the dataset
**says so itself**, instead of leaving it to this README
([findings](../../docs/compatibility_findings.md)):

| Gap | Still true | Now declared as |
|---|---|---|
| four of the nineteen bones — `chest`, `neck`, `left_shoulder`, `right_shoulder` — are identity in every frame | yes | `degenerate`, per bone, in the `provenance` column of `human/bone_rotations.csv` and in the ledger. **Tested, not listed**: the generator measures whether each bone's series is constant |
| `phase` can be all `Idle` with nothing to say so | yes | `degenerate` when one label covers the clip, with the label counts, plus a `quality.json` note telling a consumer to derive phase itself |
| `interaction_events.csv` ships as a header with no rows | yes | `absent`, with the reason: *the state machine fired nothing, NOT that no contact occurred* |
| `object_coverage: 1.0` read as "3D positions available" | the number is unchanged | `coverage_definitions` says it counts 2D detections, and `object_position_3d_coverage` is published beside it |
| no camera intrinsics, no support relation, no force or contact, no finger bones | yes | an `absent` entry each, with the consequence for a consumer |
| real scale is a configured constant, not a measurement | yes | `prior`, naming `canonical.frame_world_width` |

Why the bones are identity, since the README used to imply a capture failure:
MediaPipe pose has no landmark that separates the chest, neck or clavicles from
the shoulders, so `chest`, `neck` and both shoulders are all assigned the same
shoulder-derived orientation — and a parent-relative rotation against a parent
holding the same orientation is identity **by construction**. It is a
well-formed skeleton, not an observation.

What is **not** fixed: no adapter reads these fields yet, there is no validator,
and the committed sample output is a `0.2.0` bundle that predates them.

Full list: [`docs/limitations.md`](../../docs/limitations.md).

## Next

Feed the zip to any adapter — it is the only thing they take:

- [`adapters/mediapipe_overlay/`](../../adapters/mediapipe_overlay/) — CBD drawn back onto the original pixels
- [`adapters/mujoco/`](../../adapters/mujoco/) — `humanoid.xml` + `motion.npz` + rendered mp4
- [`adapters/unity_vrm/`](../../adapters/unity_vrm/) — `motion.vrma` for any VRM 1.0 avatar
- [`adapters/isaac_sim_groot_g1/`](../../adapters/isaac_sim_groot_g1/) — a Unitree G1, in Isaac Sim
