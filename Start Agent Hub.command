#!/bin/bash
# Agent Hub — double-click launcher (macOS / Linux)
# Starts the gateway as a background daemon via ctl.sh so closing this
# Terminal window does NOT stop Hub / scheduled tasks / Claw control-plane.
cd "$(dirname "$0")" || exit 1
PORT="${HERMES_ALI_PORT:-8765}"
export HERMES_ALI_HOST="${HERMES_ALI_HOST:-0.0.0.0}"
export HERMES_ALI_PORT="$PORT"

echo "══════════════════════════════════════════"
echo "  Agent Hub — background gateway"
echo "══════════════════════════════════════════"
echo

chmod +x ./ctl.sh 2>/dev/null || true

if ! ./ctl.sh start; then
  echo
  echo "Failed to start. Check ~/.hermes/ali/ali.log"
  echo "Press Enter to close…"
  read -r _
  exit 1
fi

# Open UI (gateway already running detached)
./ctl.sh open >/dev/null 2>&1 || true

echo
echo "浏览器: http://127.0.0.1:${PORT}"
echo
echo "要点："
echo "  · 网关已在后台运行 — 可安全关闭本窗口，Hub 不会停"
echo "  · 关闭浏览器页签 ≠ 停止 Hub / Claw；显式停止请用："
echo "      ./ctl.sh stop"
echo "  · 开机自启 + 崩溃重启（macOS）："
echo "      ./ctl.sh install-service"
echo "  · 状态 / 日志："
echo "      ./ctl.sh status"
echo "      ./ctl.sh logs"
echo
echo "本窗口 3 秒后自动关闭（网关继续运行）…"
sleep 3
exit 0
