@echo off
setlocal
cd /d "%~dp0"

set "PORT=9222"
set "CDP_URL=http://127.0.0.1:%PORT%"
set "PROFILE_DIR=%USERPROFILE%\spx_tradingview_chrome_profile"
set "START_URL=https://www.tradingview.com"
set "LOG_DIR=%~dp0outputs\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "TODAY=%%d%%b%%c"
for /f "tokens=1-2 delims=: " %%a in ("%time%") do set "NOW=%%a%%b"
set "LOG_FILE=%LOG_DIR%\vps_run_%TODAY%_%NOW%.log"

echo ========================================>> "%LOG_FILE%"
echo SPX BOT AUTO VPS RUN %date% %time%>> "%LOG_FILE%"
echo ========================================>> "%LOG_FILE%"

taskkill /F /IM chrome.exe >> "%LOG_FILE%" 2>>&1
timeout /t 2 /nobreak >nul

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto chrome_found

echo ERROR: Google Chrome was not found.>> "%LOG_FILE%"
exit /b 1

:chrome_found
echo Starting Chrome on %CDP_URL%>> "%LOG_FILE%"
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE_DIR%" --no-first-run --new-window "%START_URL%"

echo Waiting for Chrome debug port...>> "%LOG_FILE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ if(Test-NetConnection 127.0.0.1 -Port %PORT% -InformationLevel Quiet){ $ok=$true; break }; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
    echo ERROR: Chrome debug port did not open.>> "%LOG_FILE%"
    exit /b 1
)

set "BROWSER_CDP_URL=%CDP_URL%"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...>> "%LOG_FILE%"
    python -m venv .venv >> "%LOG_FILE%" 2>>&1
    if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate"
if errorlevel 1 exit /b 1

python -m pip install --upgrade pip >> "%LOG_FILE%" 2>>&1
pip install -r requirements.txt >> "%LOG_FILE%" 2>>&1
if errorlevel 1 exit /b 1

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo ERROR: .env was missing and has been created. Fill .env, then run again.>> "%LOG_FILE%"
    exit /b 1
)

echo Starting bot...>> "%LOG_FILE%"
python main.py >> "%LOG_FILE%" 2>>&1
exit /b %ERRORLEVEL%
