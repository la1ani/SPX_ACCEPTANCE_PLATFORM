@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo SPX LLM VISION TRADER - LOCAL TESTS
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

echo Running compile check...
python -m compileall .
if errorlevel 1 goto error

echo Running strict-mode scan...
python main.py --test-strict
if errorlevel 1 goto error

echo Running database test...
python main.py --test-db
if errorlevel 1 goto error

echo.
echo Local health test passed.
pause
exit /b 0

:error
echo.
echo Test failed. Read the error above.
pause
exit /b 1
