@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python 3 is required to install Regravity.
    echo Please install Python 3 from https://python.org or Windows Store.
    pause
    exit /b 1
)

python "%~dp0install.py" %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Installation encountered an error.
    pause
)
