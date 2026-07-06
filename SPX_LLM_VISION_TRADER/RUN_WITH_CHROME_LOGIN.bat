@echo off
setlocal
cd /d "%~dp0"

set "PORT=9222"
set "CDP_URL=http://127.0.0.1:%PORT%"
set "PROFILE_DIR=%USERPROFILE%\spx_tradingview_chrome_profile"
set "START_URL=https://www.tradingview.com"

echo ========================================
echo SPX BOT - GOOGLE LOGIN CHROME RUN
echo ========================================
echo.
echo This will close existing Chrome windows so the debug port can start cleanly.
echo Save any Chrome work before continuing.
echo.
pause

taskkill /F /IM chrome.exe >nul 2>nul
timeout /t 2 /nobreak >nul

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

echo ERROR: Google Chrome was not found.
echo Install Google Chrome first.
pause
exit /b 1

:chrome_found
echo Starting Chrome with bot connection enabled...
echo Profile: %PROFILE_DIR%
echo Bot URL: %CDP_URL%
echo.
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE_DIR%" --no-first-run --new-window "%START_URL%"

echo Waiting for Chrome debug port...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ if(Test-NetConnection 127.0.0.1 -Port %PORT% -InformationLevel Quiet){ $ok=$true; break }; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
    echo.
    echo ERROR: Chrome did not open debug port %PORT%.
    echo Close Chrome and try again.
    pause
    exit /b 1
)

echo.
echo Chrome is ready for the bot.
echo.
echo STEP 1: In the Chrome window, log into TradingView with Google.
echo STEP 2: Open/load your SPX chart if needed.
echo STEP 3: Keep Chrome open.
echo STEP 4: Come back here and press any key.
echo.
pause

set "BROWSER_CDP_URL=%CDP_URL%"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate"
if errorlevel 1 goto error

echo Installing / updating Python packages...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error

if not exist ".env" (
    echo Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo.
    echo IMPORTANT: .env was created. Fill it before live run.
    pause
    exit /b 1
)

echo Confirming Chrome is still open on %CDP_URL%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if(Test-NetConnection 127.0.0.1 -Port %PORT% -InformationLevel Quiet){ exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo.
    echo ERROR: Chrome is no longer open on port %PORT%.
    echo Run this file again and keep Chrome open.
    pause
    exit /b 1
)

echo Starting live battle watcher using existing Chrome...
python main.py
pause
exit /b 0

:error
echo.
echo Setup failed. Read the error above.
pause
exit /b 1
