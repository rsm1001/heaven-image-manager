@echo off
chcp 65001 > nul
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

echo.
echo TianTang Image Manager - PyQt Version
echo ==============================
echo.

if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    py -3 -m venv "%PROJECT_ROOT%.venv"
)

if not exist "%VENV_PYTHON%" (
    python -m venv "%PROJECT_ROOT%.venv"
)

if not exist "%VENV_PYTHON%" (
    echo 请安装 Python 3.8+ 并加入 PATH
    pause
    exit /b 1
)

echo Installing dependencies...
"%VENV_PYTHON%" -m pip install -r "%PROJECT_ROOT%requirements.txt"
if errorlevel 1 (
    echo Dependency installation failed
    pause
    exit /b 1
)

echo Starting TianTang Image Manager...
cd /d "%PROJECT_ROOT%"
"%VENV_PYTHON%" main.py

pause
