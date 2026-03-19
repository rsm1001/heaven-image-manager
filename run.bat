@echo off
chcp 65001 > nul
setlocal

echo 天堂图片管理器 - PyQt版本
echo ==============================

REM 检查Python是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python
    pause
    exit /b 1
)

REM 检查依赖
echo 检查依赖...
python -c "import sys; import PyQt5; import PIL; import requests; import urllib3; print('依赖检查通过')" > nul 2>&1
if errorlevel 1 (
    echo 未找到必要依赖，正在安装...
    python install_deps.py
    if errorlevel 1 (
        echo 依赖安装失败
        pause
        exit /b 1
    )
)

REM 运行主程序
echo 启动天堂图片管理器...
python main.py

pause