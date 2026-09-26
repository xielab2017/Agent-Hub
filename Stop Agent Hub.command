#!/bin/bash
# Agent Hub — double-click STOP (macOS / Linux). Pair of "Start Agent Hub.command".
# Stops the background gateway started by ctl.sh (also any Hub still listening on the port).
cd "$(dirname "$0")" || exit 1
PORT="${HERMES_ALI_PORT:-8765}"
export HERMES_ALI_PORT="$PORT"

echo "══════════════════════════════════════════"
echo "  Agent Hub — stop gateway"
echo "══════════════════════════════════════════"
echo

chmod +x ./ctl.sh 2>/dev/null || true
./ctl.sh stop

# confirm the page is really gone
stopped=1
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    stopped=0
    sleep 0.5
  else
    stopped=1
    break
  fi
done

echo
if [[ "$stopped" == 1 ]]; then
  echo "已停止：http://127.0.0.1:${PORT} 不再运行。重新启动请双击「Start Agent Hub.command」。"
  code=0
else
  echo "端口 ${PORT} 上仍有服务在响应（可能是其他程序或开机自启服务）。"
  echo "查看：./ctl.sh status    开机自启：./ctl.sh uninstall-service"
  code=1
fi
if [[ -z "${AGENT_HUB_NO_PAUSE:-}" ]]; then
  echo
  echo "本窗口 3 秒后自动关闭…"
  sleep 3
fi
exit "$code"
