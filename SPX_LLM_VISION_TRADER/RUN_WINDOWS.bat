@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo SPX LLM VISION TRADER - LIVE RUN
echo ========================================

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

echo Installing Playwright Chromium browser...
playwright install chromium
if errorlevel 1 goto error

if not exist ".env" (
    echo Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo.
    echo IMPORTANT: .env was created. Fill it before live run:
    echo - LLM provider/model/key
    echo - TradingView URL
    echo - Google Sheet ID
    echo - CALL and PUT tab names
    echo - Google service account JSON path
    echo.
    pause
    exit /b 1
)

echo Starting live battle watcher...
python main.py
pause
exit /b 0

:error
echo.
echo Setup failed. Read the error above.
pause
exit /b 1
