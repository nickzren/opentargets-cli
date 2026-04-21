#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v uv >/dev/null || {
  echo "uv is required. Install it from https://docs.astral.sh/uv/" >&2
  exit 1
}

cd "$ROOT"
uv tool install .

if ! command -v ot >/dev/null; then
  echo "Install finished, but ot is not on PATH. Add the uv tool bin directory to PATH and rerun ot doctor." >&2
  exit 1
fi

ot install-skills

if ! ot doctor; then
  echo "Install finished but some checks failed above. Fix them before restarting agents." >&2
  exit 1
fi

echo
echo "Restart Codex / Claude Code before asking Open Targets questions."
