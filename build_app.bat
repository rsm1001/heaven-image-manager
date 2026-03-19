@echo off
chcp 65001 > nul
setlocal

echo 正在打包天堂图片管理器...
echo ==============================

REM 检查PyInstaller是否安装
python -c "import PyInstaller" > nul 2>&1
if errorlevel 1 (
    echo 未安装PyInstaller，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller安装失败
        pause
        exit /b 1
    )
)

REM 进入项目目录
cd /d "C:\Users\27185\Desktop\新建文件夹\天堂_PyQt"

REM 执行打包
echo 开始打包...
pyinstaller heaven_comic.spec

if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

echo.
echo 打包完成！
echo 可执行文件位于: dist\\天堂图片管理器 目录中
echo.

pause
