@echo off
REM Agent Hub — double-click launcher (Windows)
REM Starts gateway detached so closing this window does not stop Hub.
cd /d "%~dp0"
set PORT=%HERMES_ALI_PORT%
if "%PORT%"=="" set PORT=8765
set HOST=%HERMES_ALI_HOST%
if "%HOST%"=="" set HOST=0.0.0.0
set STATE_DIR=%LOCALAPPDATA%\hermes-ali
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"
set LOG_FILE=%STATE_DIR%\ali.log
set PID_FILE=%STATE_DIR%\ali.pid

echo ==========================================
echo   Agent Hub — background gateway
echo ==========================================
echo.

powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/health -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Already running on http://127.0.0.1:%PORT%
  start "" "http://127.0.0.1:%PORT%"
  goto :done
)

set EXE=
set ARGS=
where py >nul 2>nul && (
  set EXE=py
  set ARGS=-3 server.py --host %HOST% --port %PORT% --no-browser
  goto :launch
)
where python >nul 2>nul && (
  set EXE=python
  set ARGS=server.py --host %HOST% --port %PORT% --no-browser
  goto :launch
)
where python3 >nul 2>nul && (
  set EXE=python3
  set ARGS=server.py --host %HOST% --port %PORT% --no-browser
  goto :launch
)
echo Python not found. Install Python 3.9+ and retry.
pause
exit /b 1

:launch
echo Starting detached Hub on http://127.0.0.1:%PORT% ...
powershell -NoProfile -Command "$p = Start-Process -FilePath '%EXE%' -ArgumentList '%ARGS%' -WorkingDirectory '%CD%' -WindowStyle Hidden -RedirectStandardOutput '%LOG_FILE%' -RedirectStandardError '%LOG_FILE%' -PassThru; Set-Content -Path '%PID_FILE%' -Value $p.Id"

powershell -NoProfile -Command "for ($i=0; $i -lt 12; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/health -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch {} Start-Sleep -Milliseconds 400 }; exit 1"
if errorlevel 1 (
  echo Started but health not ready yet. See log: %LOG_FILE%
) else (
  echo Gateway ready — log: %LOG_FILE%
)

start "" "http://127.0.0.1:%PORT%"

:done
echo.
echo Gateway is backgrounded. Closing this window does NOT stop Agent Hub / Claw.
echo.
timeout /t 3 >nul
exit /b 0
