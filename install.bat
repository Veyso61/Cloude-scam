@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Sanal ortam olusturuluyor (.venv)...
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo Python bulunamadi. https://www.python.org/downloads/ adresinden Python 3.11 kurun ^(Add to PATH^).
  pause
  exit /b 1
)
echo [2/3] Cekirdek paketler kuruluyor...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo [3/3] Opsiyonel paketler (AI, OCR, ceviri)...
.venv\Scripts\python -m pip install -r requirements-optional.txt
echo.
echo Kurulum tamam. Baslatmak icin run.bat
pause
