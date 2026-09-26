@echo off
REM Agent Hub - double-click STOP (Windows). Pair of start-agent-hub.bat.
REM Stops the detached gateway (PID file) and anything still listening on the Hub port.
cd /d "%~dp0"
set PORT=%HERMES_ALI_PORT%
if "%PORT%"=="" set PORT=8765
set STATE_DIR=%LOCALAPPDATA%\hermes-ali
set PID_FILE=%STATE_DIR%\ali.pid

echo ==========================================
echo   Agent Hub - stop gateway
echo ==========================================
echo.

if exist "%PID_FILE%" (
  for /f "usebackq delims=" %%p in ("%PID_FILE%") do (
    echo Stopping PID %%p ...
    taskkill /PID %%p /T /F >nul 2>&1
  )
  del /q "%PID_FILE%" >nul 2>&1
)

REM anything still listening on the port (e.g. started from a terminal)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Write-Host ('Stopping listener PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

REM confirm the page is really gone
powershell -NoProfile -Command "for ($i=0; $i -lt 10; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/health -TimeoutSec 1 | Out-Null; Start-Sleep -Milliseconds 500 } catch { exit 0 } }; exit 1"
if errorlevel 1 (
  echo Port %PORT% still answers - another program may be using it.
  set CODE=1
) else (
  echo Stopped: http://127.0.0.1:%PORT% is no longer running. Double-click start-agent-hub.bat to start again.
  set CODE=0
)

echo.
if not defined AGENT_HUB_NO_PAUSE timeout /t 3 >nul
exit /b %CODE%
