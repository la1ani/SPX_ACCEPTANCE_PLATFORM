@echo off
setlocal
title SPX LLM Vision Trader - One Click Start
color 0A

set "PROJECT_DIR=C:\SPX_ACCEPTANCE_PLATFORM\SPX_LLM_VISION_TRADER"
set "ROOT_DIR=C:\SPX_ACCEPTANCE_PLATFORM"
set "CHROME_PROFILE=C:\chrome-debug-profile"
set "CHROME_PORT=9222"

echo ============================================================
echo  SPX LLM VISION TRADER - ONE CLICK START
echo ============================================================
echo.

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo ERROR: Cannot find %ROOT_DIR%
  pause
  exit /b 1
)

echo [1/6] Updating code from GitHub...
git pull
echo.

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
  echo ERROR: Cannot find %PROJECT_DIR%
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python virtual environment missing.
  echo Run INSTALL_FAST.ps1 first.
  pause
  exit /b 1
)

if not exist ".env" (
  echo ERROR: .env file missing.
  echo Open .env and add OpenAI key, TradingView URL, Google Sheet ID.
  pause
  exit /b 1
)

if not exist "service_account.json" (
  echo ERROR: service_account.json missing in this folder:
  echo %PROJECT_DIR%
  pause
  exit /b 1
)

echo [2/6] Checking Chrome path...
set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if "%CHROME_EXE%"=="" (
  echo ERROR: Google Chrome not found.
  echo Install Chrome, then run this file again.
  pause
  exit /b 1
)

echo Chrome found: %CHROME_EXE%
echo.

echo [3/6] Closing old Chrome debug windows...
taskkill /F /IM chrome.exe >nul 2>nul
timeout /t 2 /nobreak >nul

echo [4/6] Starting Chrome with debug port %CHROME_PORT%...
start "TradingView Chrome Debug" "%CHROME_EXE%" --remote-debugging-port=%CHROME_PORT% --user-data-dir="%CHROME_PROFILE%"

echo.
echo Chrome is opening now.
echo Log in to TradingView if needed.
echo Close popups/search boxes on TradingView.
echo.
echo Waiting 10 seconds before bot starts...
timeout /t 10 /nobreak

echo.
echo [5/6] Testing Chrome debug port...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%CHROME_PORT%/json/version | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo ERROR: Chrome debug port %CHROME_PORT% is not responding.
  echo Keep Chrome open and run this file again.
  pause
  exit /b 1
)

echo Chrome debug port is ready.
echo.

echo [6/6] Starting SPX bot...
echo Watch_Log will be cleaned and rebuilt by main.py.
echo.
".venv\Scripts\python.exe" main.py

echo.
echo Bot stopped or crashed. Check the message above.
pause
