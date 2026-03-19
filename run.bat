@echo off
chcp 65001 > nul
setlocal

echo.
echo TianTang Image Manager - PyQt Version
echo ==============================
echo.

rem Check if Python is installed
python --version > nul 2>&1
if errorlevel 1 (
    echo Error: Python not found, please install Python first
    pause
    exit /b 1
)

rem Check dependencies
echo Checking dependencies...
python -c "import sys; import PyQt5; import PIL; import requests; import urllib3; print('Dependencies check passed')" > nul 2>&1
if errorlevel 1 (
    echo Dependencies not found, installing...
    python install_deps.py
    if errorlevel 1 (
        echo Dependency installation failed
        pause
        exit /b 1
    )
)

rem Run main program
echo Starting TianTang Image Manager...
python main.py

pause