@echo off
setlocal

rem Always run relative to this file, including when launched from Startup.
cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: %~dp0.env was not found.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python was not found in %~dp0.venv
    echo Create it with: python -m venv .venv
    pause
    exit /b 1
)

rem Load NAME=VALUE settings without printing secrets to the console.
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"

title BUSY Bar to Toggl Track
".venv\Scripts\python.exe" "src\busytoggl\app.py"

echo.
echo busytoggl stopped with exit code %errorlevel%.
pause
