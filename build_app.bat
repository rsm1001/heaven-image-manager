@echo off
chcp 65001 > nul
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

echo Building TianTang Image Manager...

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

"%VENV_PYTHON%" -c "import PyInstaller" > nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed. Installing...
    "%VENV_PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller installation failed
        pause
        exit /b 1
    )
)

cd /d "%PROJECT_ROOT%"

echo Starting build...
"%VENV_PYTHON%" -m PyInstaller heaven_comic.spec

if errorlevel 1 (
    echo Build failed
    pause
    exit /b 1
)

echo.
echo Build completed.
echo Executable files are in the dist directory.
echo.

pause
