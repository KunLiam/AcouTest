# -*- coding: utf-8 -*-
"""
供 Packager.bat 调用：写入 dist 内客户辅助文件，避免 bat 在 if (...) 块中因括号解析失败。

- dist/output/README.txt
- dist/启动测试工具.bat
"""
from pathlib import Path

import feature_config

README = """声测大师(AcouTest) 测试数据目录
========================================

本目录下各子目录用途：

  logcat/           Logcat 抓取文件
  screenshots/      设备截图
  mic_test/         麦克风测试录音
  sweep_recordings/ 扫频测试录音
  airtightness/     气密性测试录音（堵mic/不堵mic）
  loopback/         Loopback/Ref 测试录音
  hal_dump/         HAL 录音拉取
  hal_custom/       自定义 HAL 录音拉取
"""


def main() -> None:
    root = Path(__file__).resolve().parent
    ver = getattr(feature_config, "APP_VERSION", "1.0")
    exe_name = f"AcouTest.v{ver}.exe"

    out_readme = root / "dist" / "output" / "README.txt"
    out_readme.parent.mkdir(parents=True, exist_ok=True)
    out_readme.write_text(README, encoding="utf-8")

    launcher = root / "dist" / "启动测试工具.bat"
    lines = [
        "@echo off",
        "chcp 65001 > nul",
        'cd /d "%~dp0"',
        "echo 正在启动声测大师(AcouTest)...",
        f'start "" "{exe_name}"',
    ]
    bat_body = "\r\n".join(lines) + "\r\n"
    try:
        launcher.write_bytes(bat_body.encode("gbk"))
    except LookupError:
        launcher.write_text(bat_body, encoding="utf-8")


if __name__ == "__main__":
    main()
