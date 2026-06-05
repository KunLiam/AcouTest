import os
import sys


def _maybe_run_wake_corpus_worker():
    """同一 exe 的无界面 worker：仅跑语料生成后退出，不启动主界面。"""
    if len(sys.argv) > 1 and sys.argv[1] == "--wake-corpus-worker":
        # 勿在此调用 patch_subprocess_no_console：它会替换 subprocess.Popen 为函数，
        # 导致 asyncio.windows_utils 里 class Popen(subprocess.Popen) 导入失败。
        from generate_wake_word import _configure_unbuffered_stdio, cli_main

        _configure_unbuffered_stdio()
        raise SystemExit(cli_main(sys.argv[2:]))


_maybe_run_wake_corpus_worker()

import tkinter as tk
from tkinter import ttk
import platform

# Windows 下避免 subprocess 弹控制台窗口导致“闪屏”
from windows_subprocess_patch import patch_subprocess_no_console
patch_subprocess_no_console()

# 确保当前目录在Python路径中
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_test_tool import AudioTestTool

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioTestTool(root)
    root.mainloop() 