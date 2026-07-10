@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SPX WAR ROOM - Windows One Click Launcher
color 0A

set "ROOT_DIR=C:\SPX_ACCEPTANCE_PLATFORM"
set "PROJECT_DIR=C:\SPX_ACCEPTANCE_PLATFORM\SPX_LLM_VISION_TRADER"
set "PYTHON_EXE=.venv\Scripts\python.exe"
set "LOG_DIR=outputs"
set "DASHBOARD_LOG=%LOG_DIR%\dashboard_api.log"
set "MTF_LOG=%LOG_DIR%\mtf_timing_blocker.log"
set "BATTLE_LOG=%LOG_DIR%\battle_engine.log"
set "MTF_SECONDS=15"

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

echo [1/8] Pulling latest GitHub changes...
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

echo [2/8] Checking Python virtual environment...
if not exist "%PYTHON_EXE%" (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create .venv
    pause
    exit /b 1
  )
)

echo [3/8] Installing requirements...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] requirements install failed.
  pause
  exit /b 1
)

echo [4/8] Stopping old War Room processes...
for %%P in (dashboard_api.py mtf_timing_blocker_main.py main.py) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-CimInstance Win32_Process ^| Where-Object { $_.CommandLine -like '*%%P*' }; foreach($x in $p){ Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [5/8] Starting Dashboard API...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'dashboard_api.py' -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%PROJECT_DIR%\%DASHBOARD_LOG%' -RedirectStandardError '%PROJECT_DIR%\%DASHBOARD_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.dashboard_api.pid'"

echo [6/8] Starting MTF Timing Blocker every %MTF_SECONDS% seconds...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'mtf_timing_blocker_main.py --loop --seconds %MTF_SECONDS%' -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%PROJECT_DIR%\%MTF_LOG%' -RedirectStandardError '%PROJECT_DIR%\%MTF_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.mtf_timing_blocker.pid'"

echo [7/8] Starting LLM Battle Engine...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'main.py' -WorkingDirectory '%PROJECT_DIR%' -RedirectStandardOutput '%PROJECT_DIR%\%BATTLE_LOG%' -RedirectStandardError '%PROJECT_DIR%\%BATTLE_LOG%.err' -PassThru; $p.Id | Set-Content '%PROJECT_DIR%\.battle_engine.pid'"

echo [8/8] Waiting for services and running health checks...
timeout /t 8 /nobreak >nul

echo.
echo =============================================
echo SPX WAR ROOM BACKEND START STATUS
echo =============================================

set "DASH_PID=NOT_RUNNING"
set "MTF_PID=NOT_RUNNING"
set "BATTLE_PID=NOT_RUNNING"
if exist ".dashboard_api.pid" set /p DASH_PID=<.dashboard_api.pid
if exist ".mtf_timing_blocker.pid" set /p MTF_PID=<.mtf_timing_blocker.pid
if exist ".battle_engine.pid" set /p BATTLE_PID=<.battle_engine.pid

echo Dashboard API PID: %DASH_PID%
echo MTF Blocker PID:   %MTF_PID%
echo Battle Engine PID: %BATTLE_PID%
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
pause
