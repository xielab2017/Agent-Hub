@echo off
REM Agent Hub GitHub updater - double-click launcher for Windows.
cd /d "%~dp0"

if "%AGENT_HUB_TEST_MODE%"=="1" (
  where powershell >nul 2>nul || exit /b 1
  if not exist "%~dp0update-agent-hub.ps1" exit /b 1
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-agent-hub.ps1"
set UPDATE_EXIT=%ERRORLEVEL%

echo.
if "%UPDATE_EXIT%"=="0" (
  echo Update complete. Press any key to close.
) else (
  echo Update did not complete. Review the error above, then press any key to close.
)
pause >nul
exit /b %UPDATE_EXIT%
