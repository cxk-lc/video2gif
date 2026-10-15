@echo off
rem ============================================================
rem  Video to GIF converter - launcher (double-click to start)
rem  If this window closes immediately, run the command below
rem  in a terminal to see the error:
rem    .venv\Scripts\python.exe src\main.py
rem ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] .venv not found. See README.md for setup steps.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import tkinter, PIL" 2>nul
if errorlevel 1 (
  echo [ERROR] Dependencies missing. Run:
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "src\main.py" %*
exit /b 0
