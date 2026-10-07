@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.11+ from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [Setup] Creating virtual environment .venv ...
  python -m venv .venv
  echo [Setup] Installing dependencies ^(first run only, a few minutes^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt -q
  echo [Setup] Installing Chromium for Playwright ^(about 150MB, one time^)...
  set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
  ".venv\Scripts\python.exe" -m playwright install chromium
  if errorlevel 1 echo [Warn] Playwright Chromium install failed - huawei source will report an error until it succeeds.
)

if not exist "backend\config.yaml" copy "backend\config.example.yaml" "backend\config.yaml" >nul

echo [Start] ContestRadar running at http://127.0.0.1:8300 (browser opens automatically)
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8300 --app-dir backend
pause
