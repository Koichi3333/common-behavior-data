# Generated behavior datasets — sample output

This is a real run of [Demo B](../README.md) cell `[6]`: three natural-language
instructions, three generated behavior datasets, written in the **same
CBD-compatible format that Demo A produces**.

```text
manifest.json                              prompts, seed, smoothing, freeze flags
01_the_person_picks_up_the_cup_.../
├── frames.jsonl      CBD-compatible; each line carries the prompt it came from
├── motion.vrma       plays in Unity (UniVRM SimpleVrma)
├── humanoid.xml      MuJoCo model
├── motion.npz        qpos trajectory
└── replay_mujoco.py  local viewer
02_the_person_reaches_for_the_cup_.../
03_the_person_carries_the_cup_.../
```

Replay any of them locally — the same commands as Demo A's output, because it is
the same adapter:

```bash
pip install mujoco
cd 01_the_person_picks_up_the_cup_drinks_and_p
python replay_mujoco.py --once
```

`SPACE` pauses, `R` restarts, `,` / `.` step frame by frame.

The animation in the [Demo B README](../README.md) was rendered from exactly
these three folders.

## Read this before drawing conclusions

- This is **generated** behavior from a **small learning prototype**, not
  observed data and not a general-purpose VLA. See
  [`docs/limitations.md`](../../../docs/limitations.md).
- `lower_body_frozen: true` in `manifest.json` — the legs are pinned to a seated
  pose, because the training corpus is seated video with occluded legs.
- There is no `frame_image` and no observation provenance in these datasets.
  Nothing in the format marks them as generated except the manifest, so **do not
  mix observed and generated episodes in a corpus without tracking which is
  which.**
