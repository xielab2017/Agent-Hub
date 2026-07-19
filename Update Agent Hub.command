#!/bin/bash
# Agent Hub GitHub updater - double-click launcher for macOS.

cd "$(dirname "$0")" || exit 1
chmod +x ./update.sh 2>/dev/null || true

./update.sh
STATUS=$?

echo
if [[ $STATUS -eq 0 ]]; then
  echo "同步完成。按 Enter 关闭窗口。"
else
  echo "同步未完成，请查看上面的错误信息。按 Enter 关闭窗口。"
fi
read -r _
exit "$STATUS"

