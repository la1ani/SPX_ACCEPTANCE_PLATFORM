@echo off
setlocal
cd /d "%~dp0"

set "PORT=9222"
set "PROFILE_DIR=%USERPROFILE%\spx_tradingview_chrome_profile"
set "URL=https://www.tradingview.com"

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto start_chrome

set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto start_chrome

set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" goto start_chrome

echo Google Chrome was not found.
echo Install Google Chrome, or use Edge manually with remote debugging.
pause
exit /b 1

:start_chrome
echo Starting normal Chrome for the bot...
echo.
echo Chrome profile: %PROFILE_DIR%
echo Debug URL: http://127.0.0.1:%PORT%
echo.
echo IMPORTANT:
echo 1. Log into TradingView in the Chrome window that opens.
echo 2. Google sign-in is OK in this manually-opened Chrome.
echo 3. Keep this Chrome window open while the bot runs.
echo.
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE_DIR%" --no-first-run --new-window "%URL%"
pause
exit /b 0
