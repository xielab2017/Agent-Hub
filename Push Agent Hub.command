#!/bin/bash
# Agent Hub publisher - double-click launcher for macOS.

cd "$(dirname "$0")" || exit 1

PYTHON=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
fi

if [[ -z "$PYTHON" ]]; then
  echo "Python 3 not found."
  STATUS=1
else
  "$PYTHON" scripts/publish_agent_hub.py
  STATUS=$?
fi

echo
if [[ $STATUS -eq 0 ]]; then
  echo "发布完成。按 Enter 关闭窗口。"
else
  echo "发布未完成，请查看上面的信息。按 Enter 关闭窗口。"
fi
read -r _
exit "$STATUS"

