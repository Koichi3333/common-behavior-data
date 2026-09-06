# `showcase/` — See what CBD can do

[← back to README](../README.md) · [Adapters](../adapters/README.md) ·
[Findings](../docs/compatibility_findings.md)

**What is this?** The results, in video form, before you read any code. One
behavior — a person reaching for a glass — carried into four different targets,
with an honest note on each about what worked and what broke.

| | |
|---|---|
| **Input** | one source clip → one canonical CBD dataset |
| **Output** | videos, and a short account of each run |
| **Purpose** | Let someone judge the idea in two minutes without cloning anything |
| **Related** | [`adapters/`](../adapters/) produce these · [`examples/`](../examples/) shows the minimal path |

**No code and no output files are copied here.** Each page links to the adapter
that made the result and the directory that holds it, so nothing can drift out
of sync.

<div align="center">
<img src="../docs/media/comparison.gif" width="760" alt="One behavior dataset replayed as a MediaPipe overlay, a MuJoCo humanoid, an Isaac Sim Unitree G1 and a Unity VRM avatar, all on the same timeline">

*One source video → one behavior dataset → different renderers, same timeline.*
</div>

## The runs

| Showcase | Target | What it proves |
|---|---|---|
| [`video_to_mujoco/`](video_to_mujoco/) | MuJoCo humanoid | canonical CBD drives a physics-engine model built to the subject's measurements |
| [`video_to_unity/`](video_to_unity/) | Unity / VRM 1.0 | the same data drives an avatar **nobody measured** — any VRM 1.0 model |
| [`video_to_isaac_g1/`](video_to_isaac_g1/) | **Unitree G1 / NVIDIA GR00T, Isaac Sim** | it drives a machine whose proportions are not negotiable — and reports exactly where that costs |
| [`cross_simulator/`](cross_simulator/) | all of them at once | the same behavior, side by side, on one timeline |

## Start here

If you read one page, read [`cross_simulator/`](cross_simulator/). Four panes on
one clock is the claim of this project made visible: the four targets share no
code and never read each other's output, and the only thing they have in common
is `04_behavior_dataset/`.

If you read two, read [`video_to_isaac_g1/`](video_to_isaac_g1/). It is where
the representation stopped being comfortable.

## What each page says

Every showcase page follows the same shape, and includes the parts that did not
work:

```text
Input           the source clip and the CBD dataset
Generated       what was written, and by which generator
Target          where it went, and on what machine
What worked
What broke
Corrections     and how much they changed
Known limitations
```

**Failures are kept deliberately.** "MuJoCo: worked. Isaac G1: both ankle pitch
joints on their limit for 96 frames. Correction: four-point contact solve.
Residual: a reach to the side comes out as a reach to the front." That sequence
is more useful than a clean video, and it is the material that feeds
[`docs/compatibility_findings.md`](../docs/compatibility_findings.md).

## Showcase vs. Examples

| | Question |
|---|---|
| [`showcase/`](.) | *What can CBD do?* — results |
| [`examples/`](../examples/) | *How did the initial CBD experience work?* — the minimal runnable path |

The intended route through the repository:

```text
README → showcase → examples → generators / adapters → experiments
```

## Adding a showcase

Do not copy code or large output trees. Add a directory with one README that
links to:

- the **generator** used
- the **adapter** used, and the machine it ran on
- the **source asset** and the **output** in place
- what worked, what broke, what you corrected, what is left
