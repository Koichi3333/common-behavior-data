# `generator/` — producing Common Behavior Data

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md)

**Status: first example extracted.** [`ver0_example/`](ver0_example/) holds the
observation generator taken out of the Demo A notebook and made to stand on its
own: one video in, one canonical CBD dataset out, nothing else. The rest of
this directory is still to be written.

## `ver0_example/` — video → CBD

| Notebook | In | Out |
|---|---|---|
| [`cbd_generator_video_to_cbd.ipynb`](ver0_example/cbd_generator_video_to_cbd.ipynb) | one video of a person, 10–30 s | `cbd_dataset.zip` — `04_behavior_dataset/` with `timeline/frames.jsonl`, `human/`, `objects/`, `interactions/`, `metrics/`, `quality/`, optional `captions/` |

```text
source_video.mp4 ─▶ [ generator ] ─▶ cbd_dataset.zip ─▶ adapter notebooks
                     MediaPipe        (canonical CBD)
                     + tracking
                     + captions
```

It writes canonical CBD and only that — no MuJoCo, no VRM, no overlay video.
Those live in [`adapter/ver0_example/`](../adapter/ver0_example/), one notebook
per target, and `cbd_dataset.zip` is the hand-off between them.

### Recommended: run it from the Colab CLI

The notebook runs from both entry points — it detects at runtime whether stdin
is available and degrades gracefully — but the **Colab CLI is the recommended
way to run it**:

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

- **One session, one dataset.** Leave the session up and every adapter
  notebook finds the dataset already unpacked in the runtime — no zip to
  re-upload, no chance of an adapter reading a different episode.
- **Nothing blocks.** In a headless run the notebook never opens an upload
  widget and never embeds a video player; it prints paths instead, so
  `colab exec` always terminates. `--timeout` applies **per cell** (1800 s is
  comfortable for a 10–30 s video).
- **Scriptable and repeatable.** The same four commands run from a shell
  script or CI, which is what makes a generator → adapter chain reproducible.

The Colab UI stays fully supported: `Runtime → Change runtime type → T4 GPU`,
then run `[G1]` → `[G8]` in order (`[G2]` asks for the video). CPU also
completes, just slower.

*(optional)* Temporal captions and object re-classification need a Gemini key.
In the UI, add a Colab secret named `GEMINI_API_KEY` and grant the notebook
access. Headless, set it in the session before running the notebook:

```bash
colab exec -s cbd <<< 'import os; os.environ["GEMINI_API_KEY"] = "<key>"'
```

Without a key those two cells skip and every other output still works.

## What belongs here

Anything that **writes** Common Behavior Data:

- **Observation generators** — video → CBD (`ver0_example/`: MediaPipe pose /
  hands / face, tracking, smoothing, bone rotations, interaction candidates,
  metrics, quality)
- **Language generators** — instruction → CBD (the Demo B model's decode side,
  once it is separated from its training code)
- **Captioning and annotation passes** that write onto the canonical timeline
- **Synthetic / procedural generators**, if any

## What does not belong here

- Conversion of CBD into an engine-specific format → [`adapter/`](../adapter/)
- Training, evaluation, and research code → [`experiment/`](../experiment/)
- Inspection, validation, and conversion utilities → [`tool/`](../tool/)

## Rules for a generator

1. **Write canonical CBD**, not an adapter's output. The canonical frame is
   Y-up, right-handed, person facing +Z.
2. **Never overwrite raw observation data.** Derived values live beside the
   landmarks they came from, not on top of them.
3. **Preserve provenance.** Every derived 3D position carries a
   `position_source`; every caption records the model that produced it.
4. **Do not promote candidates.** A heuristic stays named as a candidate.
5. Observed and generated behavior are written in the **same schema** — there
   is no separate "generated motion format".

See [`specification/README.md`](../specification/README.md) for the
representation, and [`CONTRIBUTING.md`](../CONTRIBUTING.md) before opening a PR.
