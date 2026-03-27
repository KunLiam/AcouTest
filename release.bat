@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "ROOT_DIR=%~dp0"
set "DIST_DIR=%ROOT_DIR%dist"
set "RELEASE_DIR=%ROOT_DIR%release"
set "CFG_FILE=%ROOT_DIR%feature_config.py"
set "SYNC_SCRIPT=%ROOT_DIR%sync_version_manifest.py"

echo.
echo =========================================
echo   AcouTest 一键准备发布脚本
echo =========================================
echo.

if not exist "%DIST_DIR%" (
    echo [ERROR] 未找到 dist 目录: "%DIST_DIR%"
    echo 请先完成打包，再执行本脚本。
    goto :end
)

if not exist "%RELEASE_DIR%" (
    mkdir "%RELEASE_DIR%" >nul 2>nul
)

if exist "%SYNC_SCRIPT%" (
    echo [INFO] 按 feature_config.py 的 RELEASE_CHANNEL 同步对应清单（internal 仅写 update_manifest_internal.json，public 仅写 update_manifest_public.json + notes）...
    python "%SYNC_SCRIPT%"
    if errorlevel 1 (
        echo [ERROR] 版本同步失败，请先修复后再发布。
        goto :end
    )
)

set "APP_VERSION="
for /f "tokens=2 delims==" %%V in ('findstr /R /C:"^APP_VERSION[ ]*=[ ]*\".*\"" "%CFG_FILE%"') do (
    set "APP_VERSION=%%V"
)
set "APP_VERSION=%APP_VERSION:"=%"
for /f "tokens=* delims= " %%A in ("%APP_VERSION%") do set "APP_VERSION=%%A"

if not defined APP_VERSION (
    echo [WARN] 未从 feature_config.py 读取到 APP_VERSION，使用 unknown。
    set "APP_VERSION=unknown"
)

set "RELEASE_CHANNEL=public"
for /f "tokens=2 delims==" %%C in ('findstr /R /C:"^RELEASE_CHANNEL[ ]*=[ ]*\".*\"" "%CFG_FILE%"') do (
    set "RELEASE_CHANNEL=%%C"
)
set "RELEASE_CHANNEL=%RELEASE_CHANNEL:"=%"
for /f "tokens=* delims= " %%A in ("%RELEASE_CHANNEL%") do set "RELEASE_CHANNEL=%%A"

set "SRC_EXE="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%DIST_DIR%\*.exe" 2^>nul') do (
    if not defined SRC_EXE set "SRC_EXE=%DIST_DIR%\%%F"
)

if not defined SRC_EXE (
    echo [ERROR] dist 目录中未找到 exe 文件: "%DIST_DIR%"
    goto :end
)

set "TARGET_NAME=AcouTest.v%APP_VERSION%.exe"
set "TARGET_PATH=%RELEASE_DIR%\%TARGET_NAME%"

copy /Y "%SRC_EXE%" "%TARGET_PATH%" >nul
if errorlevel 1 (
    echo [ERROR] 复制失败。
    echo 源文件: "%SRC_EXE%"
    echo 目标文件: "%TARGET_PATH%"
    goto :end
)

echo [OK] 已准备发布文件（通道: %RELEASE_CHANNEL%）：
echo      "%TARGET_PATH%"
echo.
echo 源文件（dist 最新）：
echo      "%SRC_EXE%"
echo.
echo 下一步：
echo   1. 将该 exe 上传到 GitHub Release。
echo   2. 将 update_manifest_public.json、update_manifest_internal.json 提交到仓库（或放到 Release 附件），
echo      保证外部/内部用户能访问到对应清单地址。

:end
echo.
pause
endlocal
