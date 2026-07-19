#!/usr/bin/env bash
# Simple daemon control for Agent Hub (macOS / Linux)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HERMES_ALI_STATE_DIR:-$HOME/.hermes/ali}"
PUBLIC_ENV_FILE="$STATE_DIR/public-access.env"
PUBLIC_HASH_FILE="$STATE_DIR/public-access.sha256"
PUBLIC_URL_FILE="$STATE_DIR/public-url"
PID_FILE="$STATE_DIR/ali.pid"
LOG_FILE="$STATE_DIR/ali.log"
HOST="${HERMES_ALI_HOST:-0.0.0.0}"
PORT="${HERMES_ALI_PORT:-8765}"
LABEL="com.agent-hub.gateway"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "$STATE_DIR"

# Optional machine-local public access configuration. This file is never part
# of the repository and should remain readable only by the current user.
if [[ -f "$PUBLIC_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PUBLIC_ENV_FILE"
  set +a
fi
if [[ -z "${HERMES_ALI_PASSWORD:-}" && -z "${HERMES_ALI_PASSWORD_SHA256:-}" && -f "$PUBLIC_HASH_FILE" ]]; then
  export HERMES_ALI_PASSWORD_SHA256="$(tr -d '[:space:]' <"$PUBLIC_HASH_FILE")"
fi
if [[ -z "${HERMES_ALI_PUBLIC_URL:-}" && -f "$PUBLIC_URL_FILE" ]]; then
  export HERMES_ALI_PUBLIC_URL="$(tr -d '\r\n' <"$PUBLIC_URL_FILE")"
fi

pick_python() {
  if [[ -n "${HERMES_ALI_PYTHON:-}" && -x "${HERMES_ALI_PYTHON}" ]]; then
    echo "$HERMES_ALI_PYTHON"
    return
  fi
  local candidate
  for candidate in \
    /opt/miniconda3/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    "$HOME/.pyenv/shims/python3"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  echo ""
}

health_ok() {
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1
}

listener_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2}' | sort -u
  fi
}

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if pid_alive "$pid"; then
      return 0
    fi
  fi
  # Adopt an already-listening Hub (e.g. started from an old Terminal .command)
  if health_ok; then
    local lp
    lp="$(listener_pids | head -n1 || true)"
    if [[ -n "$lp" ]]; then
      echo "$lp" >"$PID_FILE"
      return 0
    fi
  fi
  return 1
}

wait_health() {
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if health_ok; then
      return 0
    fi
    sleep 0.35
  done
  return 1
}

open_ui() {
  local url="http://127.0.0.1:$PORT"
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  fi
}

stop_listeners() {
  local pids
  pids="$(listener_pids || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.35
    pids="$(listener_pids || true)"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

cmd="${1:-status}"
case "$cmd" in
  start)
    if is_running; then
      echo "Already running (PID $(cat "$PID_FILE")) — http://127.0.0.1:$PORT"
      health_ok && curl -fsS "http://127.0.0.1:$PORT/api/health" && echo
      exit 0
    fi
    PY="$(pick_python)"
    if [[ -z "$PY" ]]; then
      echo "Python not found. Install Python 3.9+ first." >&2
      exit 1
    fi
    if health_ok; then
      lp="$(listener_pids | head -n1 || true)"
      [[ -n "$lp" ]] && echo "$lp" >"$PID_FILE"
      echo "Already healthy on port $PORT (PID $(cat "$PID_FILE")) — http://127.0.0.1:$PORT"
      exit 0
    fi
    # Detach from terminal / double-click .command so closing the window does not kill Hub.
    nohup "$PY" "$ROOT/server.py" --host "$HOST" --port "$PORT" --no-browser \
      >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    disown $! 2>/dev/null || true
    sleep 0.4
    if ! pid_alive "$(cat "$PID_FILE" 2>/dev/null || true)"; then
      # Port often already taken by a foreign process — try to adopt it
      if health_ok; then
        lp="$(listener_pids | head -n1 || true)"
        [[ -n "$lp" ]] && echo "$lp" >"$PID_FILE"
        echo "Port $PORT already served (PID $(cat "$PID_FILE")) — http://127.0.0.1:$PORT"
        echo "Tip: ./ctl.sh restart  # to replace with this repo build"
        exit 0
      fi
      echo "Failed to start — see $LOG_FILE" >&2
      rm -f "$PID_FILE"
      exit 1
    fi
    if wait_health; then
      # Prefer the real listener PID (more accurate than nohup shell race)
      lp="$(listener_pids | head -n1 || true)"
      [[ -n "$lp" ]] && echo "$lp" >"$PID_FILE"
      echo "Started PID $(cat "$PID_FILE") — http://127.0.0.1:$PORT  (log: $LOG_FILE)"
      echo "Gateway is backgrounded; closing Terminal does not stop Agent Hub."
      echo "Tip: ./ctl.sh install-service  # auto-start + KeepAlive via launchd (macOS)"
    else
      echo "Started PID $(cat "$PID_FILE") but /api/health not ready yet — see $LOG_FILE" >&2
      exit 1
    fi
    ;;
  stop)
    if [[ "$(uname -s)" == "Darwin" ]] && [[ -f "$PLIST" ]]; then
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    fi
    if [[ -f "$PID_FILE" ]]; then
      pid="$(cat "$PID_FILE" 2>/dev/null || true)"
      if pid_alive "$pid"; then
        kill "$pid" 2>/dev/null || true
        sleep 0.3
        pid_alive "$pid" && kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    stop_listeners
    rm -f "$PID_FILE"
    echo "Stopped"
    ;;
  restart)
    "$0" stop || true
    sleep 0.5
    "$0" start
    ;;
  status)
    if is_running; then
      echo "Running PID $(cat "$PID_FILE") on $HOST:$PORT"
      curl -fsS "http://127.0.0.1:$PORT/api/health" || true
      echo
    else
      echo "Not running"
      exit 1
    fi
    ;;
  logs)
    tail -n "${2:-80}" "$LOG_FILE"
    ;;
  open)
    open_ui
    echo "Opened http://127.0.0.1:$PORT"
    ;;
  install-service)
    if [[ "$(uname -s)" != "Darwin" ]]; then
      echo "install-service is macOS launchd only. Use: ./ctl.sh start" >&2
      exit 1
    fi
    PY="$(pick_python)"
    if [[ -z "$PY" ]]; then
      echo "Python not found." >&2
      exit 1
    fi
    mkdir -p "$HOME/Library/LaunchAgents" "$STATE_DIR"
    echo "$ROOT" >"$STATE_DIR/hub-root"
    # macOS TCC often blocks launchd/python from reading ~/Documents (Errno 1).
    # Install a watchdog under ~/.hermes/ali instead of exec'ing server.py directly.
    WATCH="$STATE_DIR/hub-watchdog.sh"
    cat >"$WATCH" <<'WATCHEOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="__ROOT__"
STATE_DIR="__STATE_DIR__"
HOST="__HOST__"
PORT="__PORT__"
PY="__PY__"
PID_FILE="$STATE_DIR/ali.pid"
LOG_FILE="$STATE_DIR/ali.log"
CMD_FILE="$ROOT/Start Agent Hub.command"
CTL_FILE="$ROOT/ctl.sh"
HEALTHY_INTERVAL=45
UNHEALTHY_INTERVAL=15

health() { curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; }

log() { echo "[$(date '+%F %T')] watchdog: $*" >>"$LOG_FILE"; }

in_documents() {
  [[ "$ROOT" == *"/Documents/"* || "$ROOT" == *"/Documents" ]]
}

start_via_ctl() {
  if [[ ! -x "$CTL_FILE" ]]; then
    return 1
  fi
  log "starting via ctl.sh start"
  HERMES_ALI_HOST="$HOST" HERMES_ALI_PORT="$PORT" HERMES_ALI_STATE_DIR="$STATE_DIR" HERMES_ALI_PYTHON="$PY" \
    /bin/bash "$CTL_FILE" start >>"$LOG_FILE" 2>&1 || true
  sleep 1.2
  health && return 0
  return 1
}

launch_via_gui() {
  if [[ -x "$CTL_FILE" ]]; then
    log "starting via ctl.sh through Terminal (user TCC)"
    /usr/bin/open -gj -a Terminal "$CTL_FILE" --args start >/dev/null 2>&1 || true
    return 0
  fi
  if [[ -f "$CMD_FILE" ]]; then
    log "falling back to Start Agent Hub.command (user TCC)"
    /usr/bin/open -gj "$CMD_FILE" >/dev/null 2>&1 || true
    return 0
  fi
  return 1
}

start_hub() {
  if health; then return 0; fi
  mkdir -p "$STATE_DIR"
  log "Hub offline — attempting restart"

  # launchd often cannot read ~/Documents; GUI Terminal inherits user TCC.
  if in_documents; then
    launch_via_gui || true
    sleep 2.5
    if health; then return 0; fi
  fi

  if start_via_ctl; then return 0; fi

  launch_via_gui || true
}

start_hub || true
while true; do
  if health; then
    sleep "$HEALTHY_INTERVAL"
  else
    start_hub || true
    sleep "$UNHEALTHY_INTERVAL"
  fi
done

WATCHEOF
    # Fill absolute paths safely
    python3 - "$WATCH" "$ROOT" "$STATE_DIR" "$HOST" "$PORT" "$PY" <<'FILL'
import pathlib, sys
path, root, state, host, port, py = sys.argv[1:7]
text = pathlib.Path(path).read_text()
text = (text
  .replace("__ROOT__", root)
  .replace("__STATE_DIR__", state)
  .replace("__HOST__", host)
  .replace("__PORT__", port)
  .replace("__PY__", py))
pathlib.Path(path).write_text(text)
FILL
    chmod +x "$WATCH"

    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    # Unload prior watchdog only — do not "$0" stop (would kill a healthy Hub on reinstall).
    sleep 0.3

    cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${STATE_DIR}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WATCH}</string>
  </array>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_FILE}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HERMES_ALI_HOST</key>
    <string>${HOST}</string>
    <key>HERMES_ALI_PORT</key>
    <string>${PORT}</string>
    <key>HERMES_ALI_STATE_DIR</key>
    <string>${STATE_DIR}</string>
    <key>HERMES_ALI_PYTHON</key>
    <string>${PY}</string>
    <key>PATH</key>
    <string>/opt/miniconda3/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF
    if ! launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
      launchctl bootstrap "gui/$(id -u)" "$PLIST"
    fi
    launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || true
    sleep 1.2
    if wait_health; then
      lp="$(listener_pids | head -n1 || true)"
      [[ -n "$lp" ]] && echo "$lp" >"$PID_FILE"
      echo "Installed LaunchAgent $LABEL (watchdog KeepAlive under ~/.hermes/ali)"
      echo "Gateway: http://127.0.0.1:$PORT  log: $LOG_FILE"
      echo "Uninstall: ./ctl.sh uninstall-service"
    else
      "$0" start >/dev/null 2>&1 || true
      if wait_health; then
        echo "Watchdog installed; Hub started via ctl.sh — http://127.0.0.1:$PORT"
      else
        echo "LaunchAgent installed but health check pending — see $LOG_FILE" >&2
        echo "Tip: double-click Start Agent Hub.command once (Terminal needs Documents access)." >&2
      fi
    fi
    ;;
  uninstall-service)
    if [[ "$(uname -s)" != "Darwin" ]]; then
      echo "uninstall-service is macOS only." >&2
      exit 1
    fi
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    "$0" stop >/dev/null 2>&1 || true
    echo "Removed LaunchAgent $LABEL"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|open|install-service|uninstall-service}"
    exit 1
    ;;
esac
