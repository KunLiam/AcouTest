"""
Windows 下避免命令行窗口闪烁的补丁

现象：
- 点击任意按钮会执行 adb / shell 命令（大量 subprocess.run(..., shell=True)）
- 在 Windows 上这些命令可能会短暂弹出控制台窗口，表现为“闪屏/闪一下”

方案（最小改动、全局生效）：
- 在程序启动时对 subprocess.run / subprocess.Popen 做一次轻量封装
- 默认注入 CREATE_NO_WINDOW + STARTUPINFO(SW_HIDE)

注意：
- 仅在 Windows 生效
- 如果某处显式传入 creationflags/startupinfo，则不会被覆盖
"""

from __future__ import annotations

import platform
import subprocess
from typing import Any


def patch_subprocess_no_console() -> None:
    """在 Windows 下让 subprocess 默认不弹出控制台窗口。"""
    if platform.system() != "Windows":
        return

    if getattr(subprocess, "_ACOUTEST_NO_CONSOLE_PATCHED", False):
        return

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE

    CREATE_NO_WINDOW = 0x08000000

    _orig_run = subprocess.run
    _orig_popen = subprocess.Popen

    def _run(*args: Any, **kwargs: Any):
        kwargs.setdefault("startupinfo", startupinfo)
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        return _orig_run(*args, **kwargs)

    def _popen(*args: Any, **kwargs: Any):
        kwargs.setdefault("startupinfo", startupinfo)
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        return _orig_popen(*args, **kwargs)

    subprocess.run = _run  # type: ignore[assignment]
    subprocess.Popen = _popen  # type: ignore[assignment]
    subprocess._ACOUTEST_NO_CONSOLE_PATCHED = True

