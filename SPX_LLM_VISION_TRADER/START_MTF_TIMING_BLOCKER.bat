@echo off
setlocal
title SPX MTF Timing Blocker - One Click Start
color 0B

set "ROOT_DIR=C:\SPX_ACCEPTANCE_PLATFORM"
set "PROJECT_DIR=C:\SPX_ACCEPTANCE_PLATFORM\SPX_LLM_VISION_TRADER"
set "PYTHON_EXE=.venv\Scripts\python.exe"
set "MAIN_FILE=mtf_timing_blocker_main.py"
set "LOOP_SECONDS=15"

echo ============================================================
echo  SPX MTF TIMING BLOCKER - ONE CLICK START
echo ============================================================
echo.
echo Reads:
echo   calls
echo   puts
echo   Manual_Signal_Input
echo.
echo Writes:
echo   MTF_Current_Blocker
echo   MTF_Event_Log
echo   MTF_Blocker_History
echo   MTF_Blocked_Trades
echo   MTF_Allowed_Trades
echo.

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo ERROR: Cannot find %ROOT_DIR%
  pause
  exit /b 1
)

echo [1/5] Updating code from GitHub...
git pull
echo.

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
  echo ERROR: Cannot find %PROJECT_DIR%
  pause
  exit /b 1
)

if not exist "%MAIN_FILE%" (
  echo ERROR: %MAIN_FILE% not found in:
  echo %PROJECT_DIR%
  echo.
  echo Git pull completed, but this file is missing.
  pause
  exit /b 1
)

if not exist ".env" (
  echo ERROR: .env file missing.
  echo Make sure .env has GOOGLE_SERVICE_ACCOUNT_FILE.
  pause
  exit /b 1
)

echo [2/5] Checking Python virtual environment...
if not exist "%PYTHON_EXE%" (
  echo .venv missing. Creating it now...
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create .venv
    pause
    exit /b 1
  )
)

echo [3/5] Installing/updating requirements...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo.
echo [4/5] Fast one-row test...
"%PYTHON_EXE%" "%MAIN_FILE%"
if errorlevel 1 (
  echo.
  echo ERROR: One-row test failed.
  echo Check .env and GOOGLE_SERVICE_ACCOUNT_FILE.
  echo Example:
  echo GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
  pause
  exit /b 1
)

echo.
echo [5/5] Starting live MTF loop every %LOOP_SECONDS% seconds...
echo.
echo Watch this Google Sheet tab live:
echo   MTF_Current_Blocker
echo.
echo Normal output should usually be:
echo   BLOCKED / NO_TRADE / WAIT_FOR_1M_FLIP
echo.
echo Rare good output:
echo   READY_TO_TRADE / GOOD_TIMING_FULL_HAND
echo.
"%PYTHON_EXE%" "%MAIN_FILE%" --loop --seconds %LOOP_SECONDS%

echo.
echo MTF Timing Blocker stopped or crashed. Check message above.
pause
