#!/usr/bin/env bash
# End-to-end check: allocate a VM, run code on it, bring a file back, release it.
#
#   colab-cli/smoke_test.sh              # CPU, about a minute
#   colab-cli/smoke_test.sh --gpu T4     # also checks that a GPU is granted
#
# The session is stopped on exit even if a step fails.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:$PATH"
S="cbd-smoke-$$"
OUT="$HERE/ws/smoke_test.txt"

command -v colab >/dev/null || { echo "run colab-cli/setup.sh first" >&2; exit 1; }
[ -f "$HOME/.config/colab-cli/token.json" ] || { echo "run colab-cli/auth.sh first" >&2; exit 1; }

echo "[smoke] colab new -s $S $*"
colab new -s "$S" "$@"
trap 'echo "[smoke] colab stop -s $S"; colab stop -s "$S" || echo "[smoke] stop failed — check: colab sessions" >&2' EXIT

colab exec -s "$S" --timeout 120 <<'PY'
# @title smoke test
import platform, subprocess, sys
print("python", sys.version.split()[0], "on", platform.platform())
try:
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
except FileNotFoundError:
    gpu = ""
print("gpu:", gpu or "none")
open("/content/smoke_test.txt", "w").write("hello from the Colab VM\n")
PY

mkdir -p "$HERE/ws"
colab download -s "$S" /content/smoke_test.txt "$OUT"
echo "[smoke] downloaded: $(cat "$OUT")"
echo "[smoke] OK"
