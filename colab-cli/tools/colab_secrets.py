#!/usr/bin/env python3
"""Hand API keys to a Colab CLI session and make `userdata.get()` work there.

Colab Secrets (`google.colab.userdata`) cannot be read from the CLI at all:
`userdata.get()` waits for a reply from the browser frontend and always times
out after 10 s. So the keys travel from *this* machine instead, and
`userdata.get()` is replaced in the running kernel -- the notebook itself is
not modified and still uses the real Colab Secrets when opened in the browser.

    python3 colab-cli/tools/colab_secrets.py --list                 # names only, never values
    python3 colab-cli/tools/colab_secrets.py -s cbd GEMINI_API_KEY
    python3 colab-cli/tools/colab_secrets.py -s cbd HF_TOKEN=MY_HF   # rename in transit

Where a NAME is looked up, first match wins:

  1. the environment of this process         (local: `export GEMINI_API_KEY=...`)
  2. colab-cli/.env, or the file in --env-file (local: KEY=value lines, gitignored)
  3. GitHub Codespaces secrets                (cloud: Settings -> Codespaces -> Secrets)

Run it once per session, after `colab new` and before the first `colab exec`.
The values reach the VM only through `colab upload`, which logs the path but
not the content. They never appear in code passed to `colab exec`: that command
appends both the code and its output to ~/.config/colab-cli/history/<session>.jsonl
in plain text.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENV_FILE = os.path.join(HERE, ".env")
CODESPACES_SECRETS = "/workspaces/.codespaces/shared/.env-secrets"
REMOTE_PATH = "/content/.secrets.json"


def load_env_file(path):
    """KEY=value lines; `export ` prefixes, comments and surrounding quotes allowed."""
    found = {}
    if not path or not os.path.exists(path):
        return found
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if key and value:
                found[key] = value
    return found


def load_codespaces_secrets(path=CODESPACES_SECRETS):
    """Codespaces secrets, stored base64-encoded.

    /etc/profile.d/codespaces.sh only exports these when $SSH_CONNECTION is
    set, so a VS Code terminal (and anything it starts, Claude Code included)
    often cannot see them as environment variables. Read the file directly.
    """
    found = {}
    if not os.path.exists(path):
        return found
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            try:
                found[key] = base64.b64decode(value).decode("utf-8")
            except Exception:
                print(f"[secrets] {key}: could not base64-decode; skipped", file=sys.stderr)
    return found


def resolve(specs, sources):
    """`NAME` or `REMOTE=LOCAL` -> {remote name: value}, plus the names not found."""
    resolved, missing = {}, []
    for spec in specs:
        remote, _, local = spec.partition("=")
        local = local or remote
        for _, pool in sources:
            if pool.get(local):
                resolved[remote] = pool[local]
                break
        else:
            missing.append(local)
    return resolved, missing


PRELUDE = '''# @title Prelude: serve userdata.get() from keys shipped by colab_secrets.py
import json, os
from google.colab import userdata as _ud

with open({remote!r}) as _fh:
    _SECRETS = json.load(_fh)
os.remove({remote!r})            # leave no plaintext on the VM

def _get(key):
    if key not in _SECRETS:
        raise _ud.SecretNotFoundError(key)
    return _SECRETS[key]

_ud.get = _get
os.environ.update(_SECRETS)      # for libraries that read os.environ directly
print("[secrets] userdata.get() available for:", sorted(_SECRETS))
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--session", help="Colab CLI session name")
    ap.add_argument("names", nargs="*", metavar="NAME[=SOURCE]",
                    help="secret names to ship; REMOTE=LOCAL renames in transit")
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE,
                    help="KEY=value file to read (default: colab-cli/.env)")
    ap.add_argument("--list", action="store_true",
                    help="print the names available from the .env file and Codespaces, never the values")
    args = ap.parse_args()

    sources = [
        ("environment", dict(os.environ)),
        (os.path.relpath(args.env_file), load_env_file(args.env_file)),
        ("Codespaces secrets", load_codespaces_secrets()),
    ]

    if args.list:
        for label, pool in sources[1:]:
            print(f"# {label}: {'(none)' if not pool else ''}")
            for name in sorted(pool):
                print(name)
        print("# plus anything exported in this shell's environment")
        return 0
    if not args.session or not args.names:
        ap.error("need -s/--session and at least one NAME (or --list)")

    resolved, missing = resolve(args.names, sources)
    if missing:
        print(f"[secrets] not found: {', '.join(missing)}", file=sys.stderr)
        print("[secrets] looked in: environment, "
              f"{os.path.relpath(args.env_file)}, Codespaces secrets (see --list)", file=sys.stderr)
        return 1

    tmp_dir = tempfile.mkdtemp(prefix="colab-secrets-")
    payload = os.path.join(tmp_dir, "secrets.json")
    prelude = os.path.join(tmp_dir, "prelude.py")
    try:
        # Create as 0600 before writing, so there is no window where others can read it.
        fd = os.open(payload, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(resolved, fh)
        with open(prelude, "w", encoding="utf-8") as fh:
            fh.write(PRELUDE.format(remote=REMOTE_PATH))

        for cmd in (
            ["colab", "upload", "-s", args.session, payload, REMOTE_PATH],
            ["colab", "exec", "-s", args.session, "-f", prelude, "--timeout", "120"],
        ):
            if subprocess.call(cmd) != 0:
                print(f"[secrets] failed: {' '.join(cmd[:4])}", file=sys.stderr)
                return 1
    finally:
        for path in (payload, prelude):
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(tmp_dir)

    print(f"[secrets] shipped {len(resolved)} key(s) to '{args.session}'. "
          "Later cells can call userdata.get() / os.environ unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
