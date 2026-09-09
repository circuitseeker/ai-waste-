@echo off
REM ============================================================
REM   AI Waste Segregation - START (Windows)
REM   Double-click to run. Put waste near the sensor; it sorts.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo Environment not found.  Please double-click  setup.bat  first.
  echo.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
echo.
echo Starting AI Waste Segregation...
echo (First start of the day takes ~10-20 seconds to load the model.)
echo Close this window or press Ctrl+C to stop.
echo.
python run.py --sensor

echo.
echo Stopped.
pause
