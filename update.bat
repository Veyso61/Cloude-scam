@echo off
setlocal
rem ============================================================
rem  Kocu en son surume gunceller (GitHub'dan indirir).
rem  Korunan dosyalar: config.json, state.json, characters_custom.json,
rem  characters_imported.json, logs\ ve .venv\ (kurulu paketler).
rem ============================================================
set "REPO=Veyso61/Cloude-scam"
set "BRANCH=ccr-c56d4dc6-5mxr8o"

rem Bu dosya guncelleme sirasinda uzerine yazilacagi icin once TEMP'e kopyalanip oradan calisir.
if /i not "%~1"=="--from-temp" (
  copy /y "%~f0" "%TEMP%\swyf-coach-update.bat" >nul
  "%TEMP%\swyf-coach-update.bat" --from-temp "%~dp0"
  exit /b
)
set "APPDIR=%~2"
set "ZIP=%TEMP%\swyf-coach-update.zip"
set "UNPACK=%TEMP%\swyf-coach-update"

echo ============================================================
echo  SWYF Koc guncelleniyor
echo  Klasor: %APPDIR%
echo ============================================================
echo [1/3] En son surum indiriliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/%REPO%/archive/refs/heads/%BRANCH%.zip' -OutFile '%ZIP%';" ^
  "if (Test-Path '%UNPACK%') { Remove-Item -Recurse -Force '%UNPACK%' };" ^
  "Expand-Archive -Force '%ZIP%' '%UNPACK%'"
if errorlevel 1 (
  echo.
  echo HATA: indirilemedi. Internet baglantisini kontrol edip tekrar deneyin.
  pause
  exit /b 1
)

set "SRC="
for /d %%D in ("%UNPACK%\*") do set "SRC=%%D"
if not defined SRC (
  echo HATA: indirilen arsiv bos.
  pause
  exit /b 1
)

echo [2/3] Dosyalar kopyalaniyor (ayarlarin ve kayitlarin korunuyor)...
robocopy "%SRC%" "%APPDIR%." /E /NFL /NDL /NJH /NJS /NP ^
  /XF config.json state.json characters_custom.json characters_imported.json ^
  /XD logs .venv .git >nul
if errorlevel 8 (
  echo HATA: dosyalar kopyalanamadi. Koc aciksa kapatip tekrar deneyin.
  pause
  exit /b 1
)

echo [3/3] Paketler kontrol ediliyor...
if exist "%APPDIR%.venv\Scripts\python.exe" (
  "%APPDIR%.venv\Scripts\python.exe" -m pip install -q -r "%APPDIR%requirements.txt"
  rem OCR - ekrandan arayan adini okuma - artik varsayilan acik; paketler yoksa kur, olmazsa atla.
  for %%P in (mss rapidocr onnxruntime) do (
    "%APPDIR%.venv\Scripts\python.exe" -m pip install -q %%P >nul 2>nul || echo   %%P kurulamadi, atlandi.
  )
) else (
  echo Sanal ortam yok: once install.bat calistirin.
)

del /q "%ZIP%" >nul 2>nul
rmdir /s /q "%UNPACK%" >nul 2>nul
echo.
echo Guncelleme tamam. run.bat ile baslatabilirsin.
pause
