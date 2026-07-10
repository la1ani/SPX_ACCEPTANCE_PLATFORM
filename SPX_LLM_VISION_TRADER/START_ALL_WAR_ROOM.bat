@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SPX WAR ROOM - Windows One Click Launcher
color 0A

set "ROOT_DIR=C:\SPX_ACCEPTANCE_PLATFORM"
set "PROJECT_DIR=C:\SPX_ACCEPTANCE_PLATFORM\SPX_LLM_VISION_TRADER"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "LOG_DIR=%PROJECT_DIR%\outputs"
set "DASHBOARD_LOG=%LOG_DIR%\dashboard_api.log"
set "MTF_LOG=%LOG_DIR%\mtf_timing_blocker.log"
set "BATTLE_LOG=%LOG_DIR%\battle_engine.log"
set "MTF_SECONDS=15"
set "CHROME_PORT=9222"
set "CHROME_PROFILE=C:\chrome-debug-profile"

echo =============================================
echo SPX WAR ROOM - WINDOWS STARTUP
echo =============================================
echo.

cd /d "%ROOT_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find %ROOT_DIR%
  pause
  exit /b 1
)

echo [1/9] Pulling latest GitHub changes...
git pull origin main
if errorlevel 1 (
  echo [ERROR] git pull failed.
  pause
  exit /b 1
)

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find %PROJECT_DIR%
  pause
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [2/9] Checking Python virtual environment...
if not exist "%PYTHON_EXE%" (
  python -m venv "%PROJECT_DIR%\.venv"
  if errorlevel 1 (
    echo [ERROR] Could not create .venv
    pause
    exit /b 1
  )
)

echo [3/9] Installing requirements...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_EXE%" -m pip install -r "%PROJECT_DIR%\requirements.txt"
if errorlevel 1 (
  echo [ERROR] requirements install failed.
  pause
  exit /b 1
)

echo [4/9] Stopping old War Room Python processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$targets=@('dashboard_api.py','mtf_timing_blocker_main.py','main.py'); Get-CimInstance Win32_Process | Where-Object { $cl=$_.CommandLine; $cl -and $_.Name -match 'python' -and ($targets | Where-Object { $cl -like ('*'+$_+'*') }) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [5/9] Starting Chrome debug mode for TradingView...
set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if defined CHROME_EXE (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%CHROME_PORT%/json/version' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
  if errorlevel 1 (
    start "TradingView Chrome Debug" "%CHROME_EXE%" --remote-debugging-port=%CHROME_PORT% --user-data-dir="%CHROME_PROFILE%"
    timeout /t 5 /nobreak >nul
  ) else (
    echo [OK] Chrome debug port already active.
  )
) else (
  echo [WARNING] Google Chrome not found. Battle engine may fail.
)

echo [6/9] Starting Dashboard API...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('dashboard_api.py') -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%DASHBOARD_LOG%' -RedirectStandardError '%DASHBOARD_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.dashboard_api.pid'"

echo [7/9] Starting MTF Timing Blocker every %MTF_SECONDS% seconds...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('mtf_timing_blocker_main.py','--loop','--seconds','%MTF_SECONDS%') -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%MTF_LOG%' -RedirectStandardError '%MTF_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.mtf_timing_blocker.pid'"

echo [8/9] Starting LLM Battle Engine...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('main.py') -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%BATTLE_LOG%' -RedirectStandardError '%BATTLE_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.battle_engine.pid'"

echo [9/9] Waiting for services and running checks...
timeout /t 10 /nobreak >nul

echo.
echo =============================================
echo SPX WAR ROOM BACKEND START STATUS
echo =============================================

for %%N in (dashboard_api mtf_timing_blocker battle_engine) do (
  set "PID_FILE=%PROJECT_DIR%\.%%N.pid"
  set "PID_VALUE=NOT_RUNNING"
  if exist "!PID_FILE!" set /p PID_VALUE=<"!PID_FILE!"
  if not "!PID_VALUE!"=="NOT_RUNNING" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "if(Get-Process -Id !PID_VALUE! -ErrorAction SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
    if errorlevel 1 set "PID_VALUE=NOT_RUNNING"
  )
  if "%%N"=="dashboard_api" echo Dashboard API PID: !PID_VALUE!
  if "%%N"=="mtf_timing_blocker" echo MTF Blocker PID:   !PID_VALUE!
  if "%%N"=="battle_engine" echo Battle Engine PID: !PID_VALUE!
)
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/health' -TimeoutSec 5; if($r.StatusCode -eq 200){exit 0}else{exit 1} } catch { exit 1 }"
if errorlevel 1 (
  echo [ERROR] Dashboard API health failed
) else (
  echo [OK] Dashboard API health
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/mtf/current?force_refresh=true' -TimeoutSec 8; if($r.Content){exit 0}else{exit 1} } catch { exit 1 }"
if errorlevel 1 (
  echo [WARNING] MTF endpoint did not return data
) else (
  echo [OK] MTF endpoint responded
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/dashboard/current' -TimeoutSec 8; if($r.Content){exit 0}else{exit 1} } catch { exit 1 }"
if errorlevel 1 (
  echo [WARNING] War Room endpoint did not return data
) else (
  echo [OK] War Room endpoint responded
)

echo.
echo Local health:   http://127.0.0.1:8000/api/health
echo Local MTF API:  http://127.0.0.1:8000/api/mtf/current
echo Local War Room: http://127.0.0.1:8000/api/dashboard/current
echo.
echo Logs:
echo   Dashboard API: %DASHBOARD_LOG%
echo   MTF blocker:   %MTF_LOG%
echo   Battle engine: %BATTLE_LOG%
echo.
for /f "delims=" %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "try {(Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 5)} catch {'NOT_AVAILABLE'}"') do set "PUBLIC_IP=%%I"
echo Public VPS IP: %PUBLIC_IP%
echo.
echo IMPORTANT:
echo   Battle engine and MTF timing blocker remain separate decision systems.
echo   This script starts both; neither overrides the other.
echo =============================================
echo.
echo If any process shows NOT_RUNNING, open the matching .err log above.
echo.
pause
