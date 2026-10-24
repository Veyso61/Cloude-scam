@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  SWYF Koc kurulumu
echo ============================================================

if exist .venv\Scripts\python.exe goto venv_ready
echo [1/3] Python araniyor ve sanal ortam (.venv) olusturuluyor...
set "PYCMD="
for %%V in (3.12 3.11 3.13 3.14 3) do (
  if not defined PYCMD (
    py -%%V -c "import sys" >nul 2>nul && set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  python -c "import sys" >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo Python bulunamadi. https://www.python.org/downloads/ adresinden Python kurun
  echo ve kurulumda "Add Python to PATH" kutusunu isaretleyin. Sonra bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)
%PYCMD% -m venv .venv
if not exist .venv\Scripts\python.exe (
  echo Sanal ortam olusturulamadi.
  pause
  exit /b 1
)

:venv_ready
echo Kullanilan Python:
.venv\Scripts\python --version

echo.
echo [2/3] Temel paketler kuruluyor (ses dinleme + konusma tanima)...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo HATA: Temel paketler kurulamadi. Yukaridaki kirmizi mesajin ekran goruntusunu gonderin.
  pause
  exit /b 1
)

echo.
echo [3/3] Istege bagli paketler tek tek kuruluyor (AI, OCR, ceviri)...
set "OPTFAIL="
call :opt "anthropic>=2.0"
call :opt "deep-translator>=1.11"
call :opt "mss>=9.0"
call :opt "onnxruntime>=1.17"
call :opt "rapidocr>=2.0"
call :opt "SpeechRecognition>=3.10"
call :opt "scipy>=1.10"

echo.
echo ============================================================
echo  Kurulum tamam. Baslatmak icin run.bat dosyasina cift tiklayin.
if defined OPTFAIL echo  Not: bazi istege bagli paketler atlandi; ana ozellikler yine calisir.
echo ============================================================
pause
exit /b 0

:opt
echo   - "%~1"
.venv\Scripts\python -m pip install "%~1" >nul 2>nul
if errorlevel 1 (
  echo     atlandi: "%~1" - istege bagli, program yine calisir
  set "OPTFAIL=1"
)
exit /b 0
