@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

echo 正在创建独立可执行文件...

:: 检查Python是否已安装
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python
    pause
    exit /b 1
)

:: 检查PyInstaller是否已安装
python -c "import PyInstaller" > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装PyInstaller...
    pip install pyinstaller
)

:: 检查pygame是否安装
python -m pip show pygame > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装pygame...
    python -m pip install pygame
)

:: 检查Pillow是否安装
python -c "import PIL" > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装Pillow...
    python -m pip install pillow
)

:: 从 feature_config 读取版本号，打包为 声测大师(AcouTest) v<APP_VERSION>.exe
set "VER="
for /f "delims=" %%i in ('python -c "from feature_config import APP_VERSION; print(APP_VERSION)"') do set "VER=%%i"
if "%VER%"=="" set "VER=1.0"
set "EXE_NAME=声测大师(AcouTest) v%VER%"
echo 当前版本: %VER% ，输出文件名: %EXE_NAME%.exe

:: 先尝试关闭可能正在运行的应用程序
echo 正在确保没有应用程序在运行...
taskkill /F /IM "声测大师(AcouTest).exe" > nul 2>&1
taskkill /F /IM "%EXE_NAME%.exe" > nul 2>&1

:: 删除旧的输出文件和目录（含 Python 字节码缓存，确保打包用到的版本号等来自当前源码）
echo 正在清理旧文件...
if exist "dist\声测大师(AcouTest).exe" del /F /Q "dist\声测大师(AcouTest).exe" > nul 2>&1
if exist "dist\%EXE_NAME%.exe" del /F /Q "dist\%EXE_NAME%.exe" > nul 2>&1
if exist "build" rmdir /S /Q "build" > nul 2>&1
if exist "声测大师(AcouTest).spec" del /F /Q "声测大师(AcouTest).spec" > nul 2>&1
if exist "%EXE_NAME%.spec" del /F /Q "%EXE_NAME%.spec" > nul 2>&1
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /S /Q "%%d" 2>nul
del /S /Q *.pyc 2>nul

:: 生成高清logo
echo 正在生成高清logo...
python -c "from generate_high_quality_logo import create_high_quality_logo; create_high_quality_logo()"

:: 转换图标
echo 正在转换图标...
python convert_icon.py

:: 修复文件中的中文引号
::echo 修复源代码中的引号问题...
::python -c "import re; files = ['ui_components.py', 'audio_test_tool.py', 'main.py']; [open(f, 'w', encoding='utf-8').write(re.sub(r'([^\\])\"([^\"]+)\"', r'\1\"\2\"', open(f, 'r', encoding='utf-8').read())) for f in files if os.path.exists(f)]" 2>nul

:: 创建独立可执行文件
echo 正在打包应用程序...

:: 创建dist目录（如果不存在）
if not exist "dist" mkdir "dist"

:: 确保所有Python模块文件添加到打包中（--name 带版本号，输出 声测大师(AcouTest) v<APP_VERSION>.exe）
python -m PyInstaller --clean --noconsole --onefile --icon="logo\AcouTest.ico" ^
    --add-data "logo;logo" ^
    --exclude-module numpy ^
    --name "%EXE_NAME%" ^
    main.py

:: 检查打包是否成功
if exist "dist\%EXE_NAME%.exe" (
    echo 打包成功！执行文件已保存到 dist\%EXE_NAME%.exe
    
    :: 复制必要的文件和目录
    echo 正在复制必要文件...
    :: 音频资源不再随包内置（避免体积膨胀）。默认测试音频将由程序运行时生成/用户自选。
    
    :: 复制logo目录
    if not exist "dist\logo" mkdir "dist\logo"
    xcopy /E /Y "logo" "dist\logo\" >nul 2>nul
    
    :: Loopback/Ref 录音已保存到 dist\output\loopback\，不再创建 dist\test

    :: 复制 elevoc_ukey（不内置到 exe，避免 onefile 体积膨胀；运行时与 exe 同级目录读取）
    if exist "elevoc_ukey" (
        echo 正在复制 elevoc_ukey...
        if not exist "dist\elevoc_ukey" mkdir "dist\elevoc_ukey"
        xcopy /E /Y "elevoc_ukey" "dist\elevoc_ukey\" >nul 2>nul
    )
    
    :: 创建启动脚本（启动带版本号的 exe）
    echo @echo off > "dist\启动测试工具.bat"
    echo chcp 65001 ^> nul >> "dist\启动测试工具.bat"
    echo echo 正在启动声测大师(AcouTest)... >> "dist\启动测试工具.bat"
    echo start "" "%EXE_NAME%.exe" >> "dist\启动测试工具.bat"
    
    echo 完成！打包已成功，可以使用 dist 目录中的程序。
) else (
    echo 打包可能失败，未找到 dist\%EXE_NAME%.exe
) 

pause