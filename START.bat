@echo off
REM ============================================================
REM   AI WASTE SEGREGATION  -  ONE-CLICK START (Windows)
REM   Double-click this file. It installs itself the first time,
REM   finds the ESP32-CAM + ESP32 board, and starts sorting.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title AI Waste Segregation

echo ============================================================
echo    AI  WASTE  SEGREGATION
echo ============================================================
echo.

REM ---- Find a REAL Python (ignore the Microsoft Store stub) ----
REM The store stub answers "where python" but fails to actually run, so we
REM test by running Python, not by looking for the file.
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY py -c "import sys" >nul 2>nul && set "PY=py"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if defined PY goto HAVE_PY

echo Python is not installed. Trying to install it automatically (winget)...
echo.
where winget >nul 2>nul || goto NO_PY
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
REM make the just-installed Python visible to THIS window
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts"
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PY goto HAVE_PY

:NO_PY
echo.
echo [X] Python is not installed and could not be installed automatically.
echo.
echo   Do this once, then double-click this file again:
echo     1^) Install Python 3.12 from  https://www.python.org/downloads/
echo        -- TICK "Add Python to PATH" during setup.
echo     2^) If it still says "Python was not found":
echo        Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo        -- turn OFF  "python.exe"  and  "python3.exe"  (App Installer).
echo.
pause
exit /b 1

:HAVE_PY
echo Using Python: %PY%
echo.

REM ---- First-time install (only if the environment is missing) ----
if not exist ".venv\Scripts\activate.bat" (
  echo First-time setup: installing everything.
  echo This downloads about 2 GB and happens ONCE. Please wait...
  echo.
  %PY% -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [X] Install failed. Check your internet connection and run this again.
    pause
    exit /b 1
  )
) else (
  call ".venv\Scripts\activate.bat"
)

REM ---- Show the COM ports Windows can see ----
echo.
echo Connected COM ports:
powershell -NoProfile -Command "$p=[System.IO.Ports.SerialPort]::getportnames(); if($p){$p|%%{'   '+$_}}else{'   (none - plug in the device and install the USB drivers)'}"
echo.

REM ---- Start (run.py auto-detects the ESP32-CAM and the ESP32 board) ----
echo Starting - detecting the ESP32-CAM and the ESP32 board...
echo (First start of the day takes ~15 seconds to load the model.)
echo Put a piece of waste near the sensor to sort it. Close this window to stop.
echo.
python run.py --sensor

echo.
echo Stopped. You can close this window.
pause
