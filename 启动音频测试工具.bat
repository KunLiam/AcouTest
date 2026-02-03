@echo off
chcp 65001 > nul
echo 正在启动多声道音频测试工具...

:: 检查Python是否安装
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未检测到Python安装，请安装Python 3.6或更高版本
    echo 您可以从 https://www.python.org/downloads/ 下载Python
    pause
    exit /b
)

:: 检查必要的库
python -c "import tkinter" > nul 2>&1
if %errorlevel% neq 0 (
    echo 安装必要的Python库...
    pip install tk
)

:: 启动应用程序
python AudioTestTool.py

pause 