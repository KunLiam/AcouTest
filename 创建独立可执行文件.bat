@echo off
chcp 65001 > nul
echo 正在创建独立可执行文件...

:: 检查PyInstaller是否安装
python -m pip show pyinstaller > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装PyInstaller...
    python -m pip install pyinstaller
)

:: 检查pygame是否安装
python -m pip show pygame > nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装pygame...
    python -m pip install pygame
)

:: 创建独立可执行文件
echo 正在打包应用程序，这可能需要几分钟时间...
python -m PyInstaller --onefile --noconsole --name="音频测试工具" AudioTestTool.py

:: 复制必要的文件到dist目录
echo 正在复制必要文件...
if exist "audio\Nums_7dot1_16_48000.wav" (
    if not exist "dist\audio" mkdir "dist\audio"
    copy "audio\Nums_7dot1_16_48000.wav" "dist\audio\"
) else (
    echo 警告: 未找到测试音频文件 audio\Nums_7dot1_16_48000.wav
)

:: 创建test目录
if not exist "dist\test" mkdir "dist\test"

:: 创建启动脚本
echo @echo off > "dist\启动测试工具.bat"
echo chcp 65001 ^> nul >> "dist\启动测试工具.bat"
echo echo 正在启动音频测试工具... >> "dist\启动测试工具.bat"
echo 音频测试工具.exe >> "dist\启动测试工具.bat"
echo pause >> "dist\启动测试工具.bat"

echo.
echo 打包完成！
echo 所有文件已保存在dist文件夹中。
echo 您可以将整个dist文件夹分发给其他用户。
echo.

pause 