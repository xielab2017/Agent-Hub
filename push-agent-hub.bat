@echo off
REM Agent Hub publisher - double-click launcher for Windows.
cd /d "%~dp0"
set PYTHONUTF8=1

if "%AGENT_HUB_TEST_MODE%"=="1" (
  if not exist "%~dp0scripts\publish_agent_hub.py" exit /b 1
  where py >nul 2>nul && (py -3 -m py_compile scripts\publish_agent_hub.py || exit /b 1) && exit /b 0
  where python >nul 2>nul && (python -m py_compile scripts\publish_agent_hub.py || exit /b 1) && exit /b 0
  exit /b 1
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\publish_agent_hub.py
  goto :done
)

where python >nul 2>nul
if not errorlevel 1 (
  python scripts\publish_agent_hub.py
  goto :done
)

echo Python 3 not found.
set PUBLISH_EXIT=1
goto :pause

:done
set PUBLISH_EXIT=%ERRORLEVEL%

:pause
echo.
if "%PUBLISH_EXIT%"=="0" (
  echo Publish complete. Press any key to close.
) else (
  echo Publish did not complete. Review the message above, then press any key to close.
)
pause >nul
exit /b %PUBLISH_EXIT%
