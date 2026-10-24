@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once install.bat calistirin.
  pause
  exit /b 1
)
.venv\Scripts\python main.py %*
if errorlevel 1 pause
