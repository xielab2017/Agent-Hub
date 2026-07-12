#!/usr/bin/env bash
# Hermes-ALI launcher for macOS / Linux
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export HERMES_ALI_HOST="${HERMES_ALI_HOST:-0.0.0.0}"
export HERMES_ALI_PORT="${HERMES_ALI_PORT:-8765}"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.9+ is required." >&2
  exit 1
fi

exec "$PY" "$ROOT/bootstrap.py" "$@"
