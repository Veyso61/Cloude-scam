@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once install.bat calistirin.
  pause
  exit /b 1
)
echo ============================================================
echo  NVIDIA ekran karti destegi (CUDA 12 + cuDNN 9) kuruluyor
echo  Yaklasik 1.3 GB indirilecek. Sadece NVIDIA kartlar icin.
echo  Kurulmazsa program yine islemciyle (CPU) calisir.
echo ============================================================
.venv\Scripts\python -m pip install "nvidia-cublas-cu12" "nvidia-cuda-runtime-cu12" "nvidia-cuda-nvrtc-cu12" "nvidia-cudnn-cu12>=9,<10"
if errorlevel 1 (
  echo.
  echo GPU paketleri kurulamadi. Program CPU ile calismaya devam eder.
  pause
  exit /b 1
)
echo.
echo Tamam. run.bat ile baslatin; overlay altta "Whisper hazir: small.en (cuda)" yazmali.
pause
