# Colab CLI — operating rules for Claude Code

How to run this repository's notebooks on Google Colab from here. Human-facing
setup is in [`README.md`](README.md); the measured behaviour behind each rule is
in [`guide/field_guide.md`](guide/field_guide.md). Paths below are from the
repository root.

## Setup and sign-in

- Install / repair: `colab-cli/setup.sh`. Never `uv tool upgrade google-colab-cli`
  bare — re-run `setup.sh` (it pins the version the notes were checked against).
- **Do not run any `colab` command before a token exists**
  (`~/.config/colab-cli/token.json`): without one, `colab sessions` / `whoami` /
  `new` start an interactive sign-in and wait on stdin.
- Signing in from an agent is two steps, and the human does the middle:
  1. `colab-cli/auth.sh --url-only` — writes `colab-cli/ws/.auth/auth_url.txt`
     and `index.html`. In Codespaces, open it for the user with
     `"$BROWSER" "$(cat colab-cli/ws/.auth/auth_url.txt)"`; otherwise point them
     at `index.html`. **Never print the URL for them to copy** — it is ~700
     characters and arrives truncated (`Error 400: Missing required parameter: scope`).
  2. The user approves and gives you the code → `colab-cli/auth.sh --code <CODE>`.
     It checks that the `colaboratory` scope was granted.
- The generated skill (`colab-cli/.claude/skills/colab-operator/SKILL.md`) says the
  default auth is `adc` and recommends `gcloud`. That is stale: the default is
  `oauth2`, and `auth.sh` is the way here. Ignore its auth section.

## Running notebooks

```bash
cd colab-cli/ws
cp ../../generators/video_to_cbd/cbd_generator_video_to_cbd.ipynb .   # copy, then -f
colab new -s cbd
colab exec -s cbd -f cbd_generator_video_to_cbd.ipynb --timeout 1800 2>&1 | tee run.log
grep -nE "^(Traceback|[A-Za-z]*Error:)" run.log                       # exit code is 0 regardless
colab download -s cbd /content/human_behavior_demo_2_0/cbd_dataset.zip ./cbd_dataset.zip
colab stop -s cbd
```

- **Work in `colab-cli/ws/` and copy notebooks in.** `-f X.ipynb` writes
  `X_output.ipynb` next to the input; `-f ../../generators/...` would write into
  the source tree. Edit the originals, never the `ws/` copies.
- **`.ipynb` only runs through `colab exec`.** `colab run` treats the file as
  Python and fails on JSON. Use `colab run` only for a throwaway `.py`.
- **Always pass `--timeout`.** Default 30 s, total run time not silence, per cell.
- **A failing cell does not stop the run and the exit code is still 0.** Read the
  log; do not report success from the exit status.
- Kernel state persists across `colab exec` calls in one session — use it to run
  part of a notebook, read the output, then continue.
- **Collect before stopping.** `/content` is gone after `colab stop`.
  `files.download()` does nothing headless; `colab download` takes files only
  (zip directories on the VM first).

## Which notebooks run headless

- **As is:** the generator and the three notebook adapters (mediapipe_overlay,
  mujoco, unity_vrm). They detect a headless run, read
  `/content/source_video.mp4` / the dataset already on the VM, and print paths
  instead of opening widgets. Run them in **one session**, generator first.
  Sample input: `examples/human-capture/sample_output/source/source_video.mp4`.
- **Not as is:** `examples/human-capture/human_behavior_demo_2_0.ipynb` —
  2× `input()`, `drive.mount()`, `userdata.get()`. Needs the recipes below and a
  human for the Drive consent. `examples/language-to-motion/human_behavior_vla_trainer.ipynb`
  calls `drive.mount()`; not checked headless yet.
- **Not Colab:** `adapters/isaac_sim_groot_g1/` render + PhysX (RTX GPU VM). Its
  retarget / finalize / compose are plain Python — run locally if the user agrees.
- The generator reads `GEMINI_API_KEY` from `os.environ`; missing → only the
  captions and object re-classification cells skip, silently. Ship it with
  `colab_secrets.py` before the first exec if the user wants those outputs.
  If `colab_secrets.py --list` does not show it in a Codespace, the secret is not
  shared with this repository (or the Codespace was not rebuilt since) — ask the
  user; you cannot fix it from inside.

## Always stop

- `colab stop -s <name>` when done, then `colab sessions` to confirm. Closing the
  shell does not release the VM. Stop GPU sessions first.
- The Stop hook (`colab-cli/hooks/colab_session_guard.py`, registered in the
  repository's `.claude/settings.json`) warns about leftovers when a reply ends.
  It is a safety net, not a substitute: still stop and confirm yourself.

## Keys

- Ship keys with `python3 colab-cli/tools/colab_secrets.py -s <name> NAME ...`,
  once per session, after `colab new` and **before** the first `colab exec`.
  It resolves from the environment, then `colab-cli/.env`, then Codespaces secrets.
- **Never put a key in code passed to `colab exec`** (logged in plain text to
  `~/.config/colab-cli/history/<session>.jsonl`), never `print` one (also lands in
  `_output.ipynb`), never `echo` one while debugging. Check presence only:
  `[ -n "$NAME" ] && echo set || echo "NOT SET"`. Note
  `echo "${X:+set}${X:-NOT SET}"` **prints the value** when it is set.
- Do not write the userdata prelude into a notebook; `colab_secrets.py` injects it
  into the kernel so the `.ipynb` stays unchanged for the browser.

## Things that hang or fail without a browser

| In the notebook | Headless behaviour | Do this |
|---|---|---|
| `input()` | `StdinNotImplementedError` | Replace `input` **in the same cell** (ipykernel rebinds it before every cell) |
| `files.upload()` | Hangs, then the whole run dies | `colab upload` first, then replace `files.upload` (any earlier cell) |
| `files.download()` | Returns instantly, does nothing | `colab download` before stopping |
| `userdata.get()` | `TimeoutException` after 10 s | `colab_secrets.py` |
| `drive.mount()` / `colab drivemount` | Waits on `/dev/tty` | `colab-cli/tools/ptyrun.py`; the user must approve in a browser for **every** session |

Never start `colab repl`, `colab console`, `colab auth` or `colab drivemount`
directly — they need a TTY. Recipes: [field guide](guide/field_guide.md#what-breaks-without-a-browser).

## Prefer upload/download over Drive

Mount Drive only when the data already lives there or must be shared from there.
Mounting needs a human in a browser once per session, so it cannot be automated.
