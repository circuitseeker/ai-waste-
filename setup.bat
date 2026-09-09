@echo off
REM ============================================================
REM   AI Waste Segregation - ONE-TIME SETUP (Windows)
REM   Double-click this file once. It installs everything.
REM ============================================================
cd /d "%~dp0"
echo.
echo ============================================================
echo    AI Waste Segregation  -  First-time setup
echo ============================================================
echo.

REM --- check Python is installed ---
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo.
  echo   1. Download Python 3.12 from https://www.python.org/downloads/
  echo   2. During install, TICK "Add Python to PATH"
  echo   3. Then run this setup.bat again.
  echo.
  pause
  exit /b 1
)

echo Creating the environment...
python -m venv .venv
if errorlevel 1 ( echo [ERROR] Could not create environment. & pause & exit /b 1 )

echo.
echo Installing everything (first time downloads ~2 GB, please be patient)...
echo.
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Install failed. Check your internet and try again. & pause & exit /b 1 )

echo.
echo ============================================================
echo    Setup complete!  You can now double-click  run.bat
echo ============================================================
echo.
pause
