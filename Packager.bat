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

:: 先尝试关闭可能正在运行的应用程序
echo 正在确保没有应用程序在运行...
taskkill /F /IM "声测大师(AcouTest).exe" > nul 2>&1

:: 删除旧的输出文件和目录
echo 正在清理旧文件...
if exist "dist\声测大师(AcouTest).exe" del /F /Q "dist\声测大师(AcouTest).exe" > nul 2>&1
if exist "build" rmdir /S /Q "build" > nul 2>&1
if exist "声测大师(AcouTest).spec" del /F /Q "声测大师(AcouTest).spec" > nul 2>&1

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

:: 确保所有Python模块文件添加到打包中
python -m PyInstaller --noconsole --onefile --icon="logo\AcouTest.ico" ^
    --add-data "logo;logo" ^
    --exclude-module numpy ^
    --name "声测大师(AcouTest)" ^
    main.py

:: 检查打包是否成功
if exist "dist\声测大师(AcouTest).exe" (
    echo 打包成功！执行文件已保存到dist目录
    
    :: 复制必要的文件和目录
    echo 正在复制必要文件...
    :: 音频资源不再随包内置（避免体积膨胀）。默认测试音频将由程序运行时生成/用户自选。
    
    :: 复制logo目录
    if not exist "dist\logo" mkdir "dist\logo"
    xcopy /E /Y "logo" "dist\logo\" >nul 2>nul
    
    :: 创建test目录
    if not exist "dist\test" mkdir "dist\test"

    :: 复制 elevoc_ukey（不内置到 exe，避免 onefile 体积膨胀；运行时与 exe 同级目录读取）
    if exist "elevoc_ukey" (
        echo 正在复制 elevoc_ukey...
        if not exist "dist\elevoc_ukey" mkdir "dist\elevoc_ukey"
        xcopy /E /Y "elevoc_ukey" "dist\elevoc_ukey\" >nul 2>nul
    )
    
    :: 创建启动脚本
    echo @echo off > "dist\启动测试工具.bat"
    echo chcp 65001 ^> nul >> "dist\启动测试工具.bat"
    echo echo 正在启动声测大师(AcouTest)... >> "dist\启动测试工具.bat"
    echo start 声测大师(AcouTest).exe >> "dist\启动测试工具.bat"
    
    echo 完成！打包已成功，可以使用dist目录中的程序。
) 

pause