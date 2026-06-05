@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM robocopy: /XO skips files in dist that are not older than source (incremental sync).
REM Set PACKAGER_FULL_RESYNC=1 before run to force full resource copy.
set "ROBO_BASE=/E /NFL /NDL /NJH /NJS /nc /ns /np"
set "ROBO_RES=!ROBO_BASE!"
if /I not "%PACKAGER_FULL_RESYNC%"=="1" set "ROBO_RES=!ROBO_BASE! /XO"

echo [Packager] Building standalone executable...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python first.
    pause
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Packager] Installing PyInstaller...
    pip install pyinstaller
)

python -m pip show pygame >nul 2>&1
if %errorlevel% neq 0 (
    echo [Packager] Installing pygame...
    python -m pip install pygame
)

python -c "import PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Packager] Installing Pillow...
    python -m pip install pillow
)

python -c "import certifi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Packager] Installing certifi...
    python -m pip install certifi
)

set "VER="
for /f "delims=" %%i in ('python -c "from feature_config import APP_VERSION; print(APP_VERSION)"') do set "VER=%%i"
if "%VER%"=="" set "VER=1.0"
set "EXE_NAME=AcouTest.v%VER%"
set "USE_ONEDIR=0"
if /I "%PACKAGER_ONEDIR%"=="1" set "USE_ONEDIR=1"
set "DIST_EXE=dist\%EXE_NAME%.exe"
if "!USE_ONEDIR!"=="1" set "DIST_EXE=dist\%EXE_NAME%\%EXE_NAME%.exe"
set "SPEC_FILE=%EXE_NAME%.spec"
echo [Packager] Version: %VER%  Output: %EXE_NAME%.exe
if "!USE_ONEDIR!"=="1" (echo [Packager] Mode: onedir) else (echo [Packager] Mode: onefile)

echo [Packager] Stopping running app instances if any...
taskkill /F /IM "%EXE_NAME%.exe" >nul 2>&1

echo [Packager] Cleaning old build artifacts...
if exist "!DIST_EXE!" del /F /Q "!DIST_EXE!" >nul 2>&1
if exist "dist\%EXE_NAME%" rmdir /S /Q "dist\%EXE_NAME%" >nul 2>&1
if exist "build" rmdir /S /Q "build" >nul 2>&1
if exist "!SPEC_FILE!" del /F /Q "!SPEC_FILE!" >nul 2>&1
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /S /Q "%%d" 2>nul
del /S /Q *.pyc 2>nul

echo [Packager] Generating logo...
python -c "from generate_high_quality_logo import create_high_quality_logo; create_high_quality_logo()"

echo [Packager] Converting icon...
python convert_icon.py

echo [Packager] Running PyInstaller...
if not exist "dist" mkdir "dist"

set "PI_MODE=--onefile"
if "!USE_ONEDIR!"=="1" set "PI_MODE=--onedir"
python -m PyInstaller --clean --noconsole !PI_MODE! --noupx --icon="logo\AcouTest.ico" ^
    --add-data "logo;logo" ^
    --hidden-import certifi ^
    --hidden-import updater_http ^
    --hidden-import generate_wake_word ^
    --hidden-import edge_tts ^
    --hidden-import edge_tts.exceptions ^
    --hidden-import imageio_ffmpeg ^
    --hidden-import asyncio ^
    --hidden-import asyncio.windows_events ^
    --hidden-import asyncio.windows_utils ^
    --hidden-import aiohttp ^
    --exclude-module numpy ^
    --name "%EXE_NAME%" ^
    main.py

if not exist "!DIST_EXE!" goto PACK_FAIL

echo [Packager] Build OK: !DIST_EXE!
echo [Packager] Syncing dist resources...

if exist "logo" (
    echo [Packager] Sync logo...
    robocopy "logo" "dist\logo" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [WARN] logo sync may be incomplete.
)

if exist "audio" (
    echo [Packager] Sync audio...
    robocopy "audio" "dist\audio" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [WARN] audio sync may be incomplete.
) else (
    echo [WARN] audio folder not found.
)

echo [Packager] Create dist\output folders...
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

if exist "elevoc_ukey" (
    echo [Packager] Sync elevoc_ukey...
    robocopy "elevoc_ukey" "dist\elevoc_ukey" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [WARN] elevoc_ukey sync may be incomplete.
) else (
    echo [WARN] elevoc_ukey folder not found.
)

if exist "wakeup_count" (
    echo [Packager] Sync wakeup_count...
    robocopy "wakeup_count" "dist\wakeup_count" !ROBO_RES! >nul
    if !errorlevel! GEQ 8 echo [WARN] wakeup_count sync may be incomplete.
) else (
    echo [WARN] wakeup_count folder not found.
)

echo [Packager] Done. dist is ready to zip for delivery.
goto PACK_END

:PACK_FAIL
echo [ERROR] Build failed. !DIST_EXE! not found.

:PACK_END
pause
