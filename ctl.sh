#!/usr/bin/env bash
# Simple daemon control for Hermes-ALI (macOS / Linux)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HERMES_ALI_STATE_DIR:-$HOME/.hermes/ali}"
PID_FILE="$STATE_DIR/ali.pid"
LOG_FILE="$STATE_DIR/ali.log"
HOST="${HERMES_ALI_HOST:-0.0.0.0}"
PORT="${HERMES_ALI_PORT:-8765}"

mkdir -p "$STATE_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

cmd="${1:-status}"
case "$cmd" in
  start)
    if is_running; then
      echo "Already running (PID $(cat "$PID_FILE"))"
      exit 0
    fi
    nohup python3 "$ROOT/server.py" --host "$HOST" --port "$PORT" --no-browser \
      >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "Started PID $(cat "$PID_FILE") — http://127.0.0.1:$PORT  (log: $LOG_FILE)"
    ;;
  stop)
    if ! is_running; then
      echo "Not running"
      rm -f "$PID_FILE"
      exit 0
    fi
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Stopped"
    ;;
  restart)
    "$0" stop || true
    "$0" start
    ;;
  status)
    if is_running; then
      echo "Running PID $(cat "$PID_FILE") on $HOST:$PORT"
      curl -fsS "http://127.0.0.1:$PORT/api/health" || true
      echo
    else
      echo "Not running"
    fi
    ;;
  logs)
    tail -n "${2:-80}" "$LOG_FILE"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
