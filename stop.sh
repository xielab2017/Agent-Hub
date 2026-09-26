#!/usr/bin/env bash
# Stop Agent Hub (macOS / Linux) — pair of start.sh / ctl.sh start.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT_HUB_NO_PAUSE=1 exec "$ROOT/Stop Agent Hub.command"
