@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once install.bat calistirin.
  pause
  exit /b 1
)
.venv\Scripts\python main.py --demo kanye --demo-delay 5 --day 2 --reset-state
