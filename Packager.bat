@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

:: 始终切换到 bat 所在目录（项目根），保证 audio\sound、dist、logo 等相对路径正确
cd /d "%~dp0"

:: 资源同步：默认 robocopy 带 /XO（目标已存在且不比源旧则跳过该文件），减少大目录 audio 重复拷贝；源里更新过的文件仍会覆盖 dist。
:: 需要强制按源目录全量刷新 dist 内资源时，可在运行前执行：set PACKAGER_FULL_RESYNC=1
:: 打包耗时主要在 PyInstaller；/XO 主要省磁盘写入与大目录扫描时间。
:: exe 仍每次删除旧文件后整包重编，保证与当前代码、APP_VERSION 一致。

echo 正在创建独立可执行文件...

:: robocopy 公共参数（静默 + 子目录）；默认加 /XO 做增量，PACKAGER_FULL_RESYNC=1 时不加 /XO
set "ROBO_BASE=/E /NFL /NDL /NJH /NJS /nc /ns /np"
set "ROBO_RES=!ROBO_BASE!"
if /I not "%PACKAGER_FULL_RESYNC%"=="1" set "ROBO_RES=!ROBO_BASE! /XO"

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

:: certifi：打包进 exe，检查更新时 HTTPS 使用 Mozilla CA 包，减少「证书验证失败」
python -c "import certifi" > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装 certifi...
    python -m pip install certifi
)

:: 从 feature_config 读取版本号，输出 exe 名为 AcouTest.v<版本>.exe（与 release 与更新清单命名一致）
set "VER="
for /f "delims=" %%i in ('python -c "from feature_config import APP_VERSION; print(APP_VERSION)"') do set "VER=%%i"
if "%VER%"=="" set "VER=1.0"
set "EXE_NAME=AcouTest.v%VER%"
:: 完整 exe 路径放入变量，配合延迟展开，避免复杂文件名在 if 块内解析出错
:: 默认 onefile；可选 onedir：set PACKAGER_ONEDIR=1（见 README，适合磁盘紧张或不想依赖 %TEMP% 解压）
set "USE_ONEDIR=0"
if /I "%PACKAGER_ONEDIR%"=="1" set "USE_ONEDIR=1"
set "DIST_EXE=dist\%EXE_NAME%.exe"
if "!USE_ONEDIR!"=="1" set "DIST_EXE=dist\%EXE_NAME%\%EXE_NAME%.exe"
set "SPEC_FILE=%EXE_NAME%.spec"
echo 当前版本: %VER% ，输出文件名: %EXE_NAME%.exe
if "!USE_ONEDIR!"=="1" (echo 打包模式: onedir ^(子目录+exe^)) else (echo 打包模式: onefile ^(单 exe^))

:: 先尝试关闭可能正在运行的应用程序
echo 正在确保没有应用程序在运行...
taskkill /F /IM "声测大师(AcouTest).exe" > nul 2>&1
taskkill /F /IM "声测大师(AcouTest) v%VER%.exe" > nul 2>&1
taskkill /F /IM "%EXE_NAME%.exe" > nul 2>&1

:: 删除旧的输出文件和目录（含 Python 字节码缓存，确保打包用到的版本号等来自当前源码）
echo 正在清理旧文件...
if exist "dist\声测大师(AcouTest).exe" del /F /Q "dist\声测大师(AcouTest).exe" > nul 2>&1
del /F /Q "dist\声测大师*.exe" > nul 2>&1
if exist "!DIST_EXE!" del /F /Q "!DIST_EXE!" > nul 2>&1
if exist "dist\%EXE_NAME%" rmdir /S /Q "dist\%EXE_NAME%" > nul 2>&1
if exist "build" rmdir /S /Q "build" > nul 2>&1
if exist "声测大师(AcouTest).spec" del /F /Q "声测大师(AcouTest).spec" > nul 2>&1
if exist "声测大师(AcouTest) v%VER%.spec" del /F /Q "声测大师(AcouTest) v%VER%.spec" > nul 2>&1
if exist "!SPEC_FILE!" del /F /Q "!SPEC_FILE!" > nul 2>&1
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

:: 创建独立可执行文件（本行仅用 ASCII，避免部分环境下 UTF-8 与 cmd 解析组合导致误拆命令）
echo [Packager] Running PyInstaller...

:: 创建dist目录（如果不存在）
if not exist "dist" mkdir "dist"

:: 确保所有 Python 模块加入打包（--name 带版本号）
REM noupx: avoid UPX on OpenSSL DLLs; may cause onefile extract errors for libcrypto-3.dll
set "PI_MODE=--onefile"
if "!USE_ONEDIR!"=="1" set "PI_MODE=--onedir"
python -m PyInstaller --clean --noconsole !PI_MODE! --noupx --icon="logo\AcouTest.ico" ^
    --add-data "logo;logo" ^
    --hidden-import certifi ^
    --hidden-import updater_http ^
    --exclude-module numpy ^
    --name "%EXE_NAME%" ^
    main.py

REM 不用巨型 if (...) 块，避免 CMD 在嵌套括号与 :: 注释下报 syntax incorrect
if not exist "!DIST_EXE!" goto PACK_FAIL

echo 打包成功！执行文件已保存到 !DIST_EXE!
echo 正在同步交付资源到 dist...

if exist "logo" (
    echo 正在同步 logo...
    robocopy "logo" "dist\logo" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [警告] logo 同步可能不完整，请检查 robocopy 日志。
)

if exist "audio" (
    echo 正在同步 audio 目录...
    robocopy "audio" "dist\audio" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [警告] audio 同步可能不完整。
) else (
    echo [提示] 未找到 audio 目录，客户将无法使用默认扫频/喇叭等音频，请从源码目录保留 audio 后重新打包。
)

echo 正在创建 dist\output 子目录...
mkdir "dist\output" 2>nul
mkdir "dist\output\logcat" 2>nul
mkdir "dist\output\screenshots" 2>nul
mkdir "dist\output\mic_test" 2>nul
mkdir "dist\output\sweep_recordings" 2>nul
mkdir "dist\output\airtightness" 2>nul
mkdir "dist\output\loopback" 2>nul
mkdir "dist\output\hal_dump" 2>nul
mkdir "dist\output\hal_custom" 2>nul
python pack_dist_client_files.py 2>nul
if not exist "dist\output\README.txt" (
    echo 声测大师^(AcouTest^) 测试数据目录> "dist\output\README.txt"
    echo 程序运行后录音、日志、截图等默认保存在本目录各子文件夹中。>> "dist\output\README.txt"
)

if exist "elevoc_ukey" (
    echo 正在同步 elevoc_ukey...
    robocopy "elevoc_ukey" "dist\elevoc_ukey" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [警告] elevoc_ukey 同步可能不完整。
) else (
    echo [提示] 未找到 elevoc_ukey 目录，烧大象 key 功能将无法使用（若需要请保留该目录后重新打包）。
)

if exist "wakeup_count" (
    echo 正在同步 wakeup_count...
    robocopy "wakeup_count" "dist\wakeup_count" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [警告] wakeup_count 同步可能不完整。
) else (
    echo [提示] 未找到 wakeup_count 目录，唤醒率 100 条测试将无内置语料（若需要请保留该目录后重新打包）。
)

echo 完成！dist 目录已包含 exe、audio、output、elevoc_ukey、wakeup_count等资源，可直接打包 zip 发给客户。
goto PACK_END

:PACK_FAIL
echo 打包可能失败，未找到 !DIST_EXE!

:PACK_END
pause