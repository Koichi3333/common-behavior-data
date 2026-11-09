# `colab-cli/` — Run this repository's notebooks on Colab from a terminal

[日本語](README.ja.md) · [Field guide](guide/field_guide.md) ·
[Where things run](../docs/runtime_environments.md)

Everything needed to drive Google Colab from the command line with the official
[`google-colab-cli`](https://github.com/googlecolab/google-colab-cli) — install,
sign-in, keys, a smoke test, and the notes on what behaves differently without a
browser. It is self-contained: nothing outside this directory is required or
modified.

The repository's rule is *Colab CLI where the target allows it*
([why](../docs/runtime_environments.md)). This directory is how you get there.

**The same three commands work in the cloud (GitHub Codespaces, a remote Linux
box over SSH) and on a local macOS or Linux machine.** On Windows, use WSL.

## Quick start

From the repository root:

```bash
colab-cli/setup.sh        # install uv + google-colab-cli 0.7.5 (safe to re-run)
colab-cli/auth.sh         # sign in once per machine
colab-cli/smoke_test.sh   # allocate a CPU VM, run code, fetch a file, stop it (~1 min)
```

That is the whole setup. A Google account is enough — Workspace accounts work,
no `gcloud`, no GCP project, no OAuth client of your own. The free Colab tier is
enough for the smoke test and for every notebook here.

## Cloud or local: what differs

Only three things, and the scripts handle the first one for you.

| | Cloud (Codespaces, SSH) | Local (macOS / Linux / WSL) |
|---|---|---|
| **Sign-in** | `auth.sh` opens the page in *your* browser via `$BROWSER` (Codespaces, VS Code Remote). Plain SSH: it writes `ws/.auth/auth_url.txt` + a one-link `index.html`, or serves it with `--serve 8765` behind a port forward | `auth.sh` opens your default browser |
| **API keys** (optional) | Codespaces secrets: GitHub → Settings → Codespaces → Secrets, with **this repository** under *Repository access*, then **rebuild** the Codespace. A secret shared only with another repository is invisible here — `python3 colab-cli/tools/colab_secrets.py --list` shows what arrived | `cp colab-cli/.env.example colab-cli/.env`, fill it in (gitignored), or just `export` the variable |
| **What survives** | Rebuilding or recreating a Codespace deletes `~/.local` and `~/.config` — the CLI *and* its token. Re-run `setup.sh` and `auth.sh` | Nothing to redo |

Either way the sign-in itself is the CLI's own flow: you approve in a browser and
paste the code Google shows. `auth.sh` exists because the sign-in URL is about
700 characters, and copied out of a terminal it gets cut and Google answers
*Error 400: Missing required parameter: scope*
([details](guide/field_guide.md#the-one-real-trap-the-url-is-cut)). For agents
and scripts there is a two-step form: `auth.sh --url-only`, then
`auth.sh --code <CODE>`.

## Running this repository's notebooks

Work inside `colab-cli/ws/` (gitignored), and **copy notebooks there** rather than
pointing `-f` at them: `colab exec -f X.ipynb` writes `X_output.ipynb` *next to
the input*, so `-f ../../generators/...` would drop it into the source tree.

The main line is generator → adapters **in one session**: each adapter finds the
dataset the generator unpacked on the VM, so nothing is re-uploaded. With the
sample clip that ships in the repository, on CPU:

```bash
cd colab-cli/ws
R=../..
cp $R/generators/video_to_cbd/cbd_generator_video_to_cbd.ipynb \
   $R/adapters/mujoco/cbd_adapter_mujoco.ipynb .

colab new -s cbd                                         # add --gpu T4 if you have one
python3 ../tools/colab_secrets.py -s cbd GEMINI_API_KEY   # optional, and before the first exec
colab upload -s cbd $R/examples/human-capture/sample_output/source/source_video.mp4 \
                    /content/source_video.mp4
colab exec   -s cbd -f cbd_generator_video_to_cbd.ipynb --timeout 1800 2>&1 | tee generator.log
colab exec   -s cbd -f cbd_adapter_mujoco.ipynb         --timeout 1800 2>&1 | tee mujoco.log
grep -nE "^(Traceback|[A-Za-z]*Error:)" *.log            # cells fail without stopping the run
colab download -s cbd /content/human_behavior_demo_2_0/cbd_dataset.zip ./cbd_dataset.zip
colab stop -s cbd && colab sessions                      # always, and confirm
```

Use your own clip by uploading it to the same `/content/source_video.mp4`.
The adapters print their output paths at the end; zip that directory on the VM
and `colab download` it before stopping. Edit the originals, not the copies in
`ws/` — those are disposable.

### Which notebooks run headless

| Notebook | From the CLI | Notes |
|---|---|---|
| [`generators/video_to_cbd/`](../generators/video_to_cbd/) | **Yes, unchanged** | Detects a headless run and never opens the upload widget; reads `/content/source_video.mp4`. `GEMINI_API_KEY` is read from `os.environ` — without it, only the captions and object re-classification cells skip |
| [`adapters/mediapipe_overlay/`](../adapters/mediapipe_overlay/), [`mujoco/`](../adapters/mujoco/), [`unity_vrm/`](../adapters/unity_vrm/) | **Yes, unchanged** | Same headless detection; read the dataset left by the generator in the same session (Unity playback itself happens on your machine) |
| [`examples/human-capture/human_behavior_demo_2_0.ipynb`](../examples/human-capture/) | **Not as is** | Two `input()` calls, `drive.mount()` and `userdata.get()`: needs the [recipes](guide/field_guide.md#what-breaks-without-a-browser), and a browser approval for Drive every session |
| [`examples/language-to-motion/human_behavior_vla_trainer.ipynb`](../examples/language-to-motion/) | Not yet checked | Calls `drive.mount()` |
| [`adapters/isaac_sim_groot_g1/`](../adapters/isaac_sim_groot_g1/) | **No — not Colab** | Retarget, finalize and compose are plain Python on any machine; render and PhysX need an RTX GPU VM ([why](../docs/runtime_environments.md#the-one-exception-isaac-sim)) |

Keys go through `colab_secrets.py`, never into code passed to `colab exec`:
that command appends the code *and* its output in plain text to
`~/.config/colab-cli/history/<session>.jsonl`. The notebooks are not modified
and still use real Colab Secrets when opened in the browser.

## Five rules

1. **Always `colab stop -s <name>`.** Closing the terminal does not release the
   VM. Check with `colab sessions`. If you use Claude Code in this repository,
   it warns you about any session still running each time it finishes a
   reply. The Stop hook is in the repository's `.claude/settings.json`, so it
   works without setup.
2. **Always pass `--timeout`.** The default is 30 s, it caps total run time (not
   silence), and for a notebook it applies per cell.
3. **The exit code lies.** A failing cell does not stop the run and
   `colab exec` still exits 0. Grep the log for `Traceback`.
4. **Collect before stopping.** `/content` vanishes with the session, and
   `files.download()` silently does nothing without a browser — use
   `colab download` (files only; zip directories on the VM first).
5. **No browser means no widgets.** `input()`, `files.upload()` and
   `userdata.get()` need the recipes in the
   [field guide](guide/field_guide.md#what-breaks-without-a-browser).

## What's in this directory

| Path | What it is |
|---|---|
| [`setup.sh`](setup.sh) | Installs `uv` and `google-colab-cli` (pinned to 0.7.5; `COLAB_CLI_VERSION=latest` to override), creates `ws/`, writes the Claude Code skill |
| [`auth.sh`](auth.sh) → [`tools/auth.py`](tools/auth.py) | Sign-in that never routes the URL through the terminal |
| [`smoke_test.sh`](smoke_test.sh) | New → exec → download → stop, stopping even on failure. Extra args go to `colab new` (e.g. `--gpu T4`) |
| [`tools/colab_secrets.py`](tools/colab_secrets.py) | Ships keys (environment → `.env` → Codespaces secrets) to a session and makes `userdata.get()` work there |
| [`tools/ptyrun.py`](tools/ptyrun.py) | Lets `colab drivemount` / `colab auth` finish without a terminal |
| [`hooks/colab_session_guard.py`](hooks/colab_session_guard.py) | Claude Code Stop hook, registered for everyone in the repository's `.claude/settings.json`: warns about sessions left running |
| [`examples/drive/`](examples/drive/) | Write from a `.py`, read back from a `.ipynb`, through a mounted Drive |
| [`guide/field_guide.md`](guide/field_guide.md) · [`.ja.md`](guide/field_guide.ja.md) | The measured behaviour: auth, notebooks, secrets, results, Drive, troubleshooting |
| [`CLAUDE.md`](CLAUDE.md) | Operating rules for Claude Code when it works in this directory |
| [`.env.example`](.env.example) | Template for local keys |
| `ws/` | Working directory; everything in it except `.gitkeep` is ignored |
| `.claude/skills/colab-operator/` | Generated by `setup.sh` from `colab skill`, so it matches the installed CLI (gitignored) |

## Status — what has and has not been run

Honest about the edges, as everywhere in this repository:

- **Checked on 0.7.5, in a Codespace:** `setup.sh` (fresh and re-run), the Stop
  hook's output (with and without a leftover session, and with no Colab CLI
  installed), the `--serve` page.
- **Run end-to-end on 0.7.5, in a Codespace (2026-11-07, CPU runtime):**
  - **Sign-in.** `auth.sh --url-only` → browser → `auth.sh --code` worked.
    `colab whoami` reports `Auth provider: oauth2` with the `colaboratory` scope.
  - **`smoke_test.sh`.** It passed. The VM ran Python 3.13.18 with no GPU.
  - **The notebook chain.** `colab_secrets.py` shipped `GEMINI_API_KEY` from
    Codespaces secrets → the generator → the MuJoCo adapter, all in one session.
    The sample video was the input.
    - The generator took about 2 minutes. Captions and Gemini re-classification
      ran. It produced `cbd_dataset.zip` (2.6 MB, 122 files).
    - The MuJoCo adapter took about 1 minute and rendered with `osmesa` on the
      CPU. It passed every acceptance check and produced
      `/content/human_behavior_demo_2_0/mujoco_adapter_output.zip` (0.3 MB, 9 files).
    - Neither log has a traceback. The dataset's gaps match the committed
      sample exactly: the cup is seen in 1 frame, there are no interaction
      events, and face coverage is 0.
  - **After the run.** `colab stop` → `colab sessions` showed nothing left. The
    key's value was not found in `ws/` or in `~/.config/colab-cli/` (the CLI
    history included).
- **Not yet re-checked on 0.7.5:**
  - What happens when a cell fails. The run above had no failing cell, so the
    "exit code is 0 anyway" note is still from 0.6.0.
  - The `input()` / `files.upload()` / `drive.mount()` recipes.
  - GPU runtimes for this repository's notebooks. (The same tools ran an A100 job on 0.7.5 in
    [vla-maker-from-cbd](https://github.com/Koichi3333/vla-maker-from-cbd/tree/main/colab-cli), 2026-11-09.)
  - The mediapipe_overlay and unity_vrm adapters.

  The other behaviour notes in the field guide were measured on **0.6.0**. The
  guide marks where 0.7.5's source shows a change (the sign-in flow, the
  `jupyter-kernel-client` pin, the keep-alive daemon).
- **Not yet run on a local machine.** The local path differs only in how the
  browser is opened (`webbrowser.open`) and where keys come from.
- **The first CBD run (2026-11-04, from the template) stopped before sign-in.**
  It installed 0.7.5 and got as far as serving the sign-in link, then paused
  because `GEMINI_API_KEY` was defined as a Codespaces secret but shared with a
  different repository, so it never reached the Codespace. That is why the
  sharing step is spelled out above. The headless table above comes from that
  run's reading of the notebooks, re-checked against the sources here.

If one of these breaks for you, that is a finding — please open an issue.

## Where this came from

Adapted from a standalone Colab CLI setup template by the same author, measured
on `google-colab-cli` 0.6.0 in a Codespace. Changes on the way in: moved under
one directory with paths fixed; sign-in rebuilt on 0.7.x's own flow (the 0.6.0
loopback helpers were dropped); local `.env` support in `colab_secrets.py`; the
Stop hook rewritten in Python (no `jq`) and registered for the whole repository; the official skill
generated at setup instead of vendored. The CBD findings from the template's test run
(2026-11-04) went into the headless table and the secret-sharing note above; the
hand-off notes themselves were left out — they record one person's account and
machine, not anything a reader needs.
