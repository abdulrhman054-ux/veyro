@echo off
setlocal
chcp 65001 >nul
title Veyro
cd /d "%~dp0"

echo.
echo   ==============================
echo     Veyro  -  فيرو
echo   ==============================
echo.

rem ---- 1) Python environment (first run only) ----
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Preparing Veyro for the first time... this takes a few minutes.
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
  if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   Python 3.11 or newer is needed. Install it from https://www.python.org/downloads/
    echo   then double-click start.bat again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo   Installing failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
) else (
  echo [1/3] Ready.
)

rem ---- 2) Built interface must be present ----
if not exist "frontend\dist\index.html" (
  echo   The interface files are missing: frontend\dist
  echo   Ask whoever gave you Veyro for a complete copy.
  pause
  exit /b 1
)

rem ---- 3) Start the local server (only on this PC: 127.0.0.1) and open the browser ----
echo [2/3] Starting the office...
start "Veyro server" /min cmd /c "cd /d "%~dp0backend" && "%~dp0.venv\Scripts\python.exe" -m veyro"

powershell -NoProfile -Command "$u='http://127.0.0.1:8765/api/health'; for($i=0;$i -lt 60;$i++){ try { Invoke-WebRequest -UseBasicParsing $u -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 700 } }; exit 1"
if errorlevel 1 (
  echo   The office did not open in time. Close this window and try again.
  pause
  exit /b 1
)

echo [3/3] Opening Veyro in your browser...
if not defined VEYRO_NO_BROWSER start "" "http://127.0.0.1:8765/"
echo.
echo   Veyro is running. To stop it, close the window called "Veyro server".
ping -n 6 127.0.0.1 >nul
endlocal
