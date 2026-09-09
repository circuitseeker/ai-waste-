@echo off
REM ============================================================
REM   AI WASTE SEGREGATION  -  ONE-CLICK START (Windows)
REM
REM   Just double-click this file. It will:
REM     * check Python is installed
REM     * install everything the FIRST time (one time only)
REM     * list the connected COM ports
REM     * detect the ESP32-CAM and the ESP32 board
REM     * start sorting
REM ============================================================
cd /d "%~dp0"
title AI Waste Segregation

echo ============================================================
echo    AI  WASTE  SEGREGATION
echo ============================================================
echo.

REM ---- 1. Python installed? ----
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python is not installed.
  echo.
  echo     1^) Get Python 3.12 from  https://www.python.org/downloads/
  echo     2^) During install, TICK  "Add Python to PATH"
  echo     3^) Then double-click this file again.
  echo.
  pause
  exit /b 1
)

REM ---- 2. First-time install (only if the environment is missing) ----
if not exist ".venv\Scripts\activate.bat" (
  echo First-time setup: installing everything.
  echo This downloads about 2 GB and happens ONCE. Please wait...
  echo.
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip >nul
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

REM ---- 3. Show the COM ports Windows can see ----
echo.
echo Connected COM ports:
powershell -NoProfile -Command "$p=[System.IO.Ports.SerialPort]::getportnames(); if($p){$p|%%{'   '+$_}}else{'   (none - is the device plugged in? are the USB drivers installed?)'}"
echo.

REM ---- 4. Start (run.py auto-detects the ESP32-CAM and the ESP32 board) ----
echo Starting - detecting the ESP32-CAM and the ESP32 board...
echo (First start of the day takes ~15 seconds to load the model.)
echo Put a piece of waste near the sensor to sort it. Close this window to stop.
echo.

python run.py --sensor

echo.
echo Stopped. You can close this window.
pause
