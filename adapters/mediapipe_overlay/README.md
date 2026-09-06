# `mediapipe_overlay/` — CBD back onto the original pixels

[← back to `adapters/`](../README.md) ·
[Specification](../../specification/README.md)

**What is this?** The simplest possible consumer of Common Behavior Data: it
redraws the dataset over the frames it came from. If the overlay lines up with
the video, the canonical data is intact — which makes this the adapter to run
first when something looks wrong further downstream.

| | |
|---|---|
| **Input** | canonical CBD — `cbd_dataset.zip` or an unpacked `04_behavior_dataset/` |
| **Output** | `output/01_mediapipe_overlay/mediapipe_overlay.mp4` + `adapter_report.json`, packaged as `overlay_adapter_output.zip` |
| **Runs in** | Google Colab — **CLI recommended**, UI supported |
| **GPU** | no |

Notebook: [`cbd_adapter_mediapipe_overlay.ipynb`](cbd_adapter_mediapipe_overlay.ipynb)

**It does not run MediaPipe.** Detection happened in the generator; this reads
the stored landmarks and draws them. That is the whole point — the picture is
evidence about the *data*, not about the detector.

## Minimal example

```bash
# same Colab session the generator ran in — nothing to upload
colab exec -s cbd -f cbd_adapter_mediapipe_overlay.ipynb --timeout 1800
```

Fresh session:

```bash
colab upload -s cbd2 ./cbd_dataset.zip /content/cbd_dataset.zip
colab exec   -s cbd2 -f cbd_adapter_mediapipe_overlay.ipynb --timeout 1800
```

In a headless run it never opens an upload widget and never embeds a video
player — it prints the output path, so `colab exec` always terminates.
`--timeout` applies per cell.

## Sample output

[`examples/human-capture/sample_output/01_mediapipe_overlay/`](../../examples/human-capture/sample_output/01_mediapipe_overlay/)
· side by side with the other targets in
[`showcase/cross_simulator/`](../../showcase/cross_simulator/)

## Related

[`mujoco/`](../mujoco/) · [`unity_vrm/`](../unity_vrm/) ·
[`isaac_sim_groot_g1/`](../isaac_sim_groot_g1/) ·
[adapter rules](../README.md#rules-for-an-adapter)
