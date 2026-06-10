import os
import sys

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


def _maybe_run_wake_corpus_worker():
    """同一 exe 的无界面 worker：仅跑语料生成后退出，不启动主界面。"""
    if len(sys.argv) > 1 and sys.argv[1] == "--wake-corpus-worker":
        # 勿在此调用 patch_subprocess_no_console：它会替换 subprocess.Popen 为函数，
        # 导致 asyncio.windows_utils 里 class Popen(subprocess.Popen) 导入失败。
        from generate_wake_word import _configure_unbuffered_stdio, cli_main

        _configure_unbuffered_stdio()
        raise SystemExit(cli_main(sys.argv[2:]))


_maybe_run_wake_corpus_worker()

# 打包后尽早切换工作目录（须在 Tk 创建窗口之前）
from platform_utils import bootstrap_frozen_runtime_cwd

bootstrap_frozen_runtime_cwd()

from platform_utils import configure_macos_frozen_tk_env, augment_path_for_gui_app

configure_macos_frozen_tk_env()
augment_path_for_gui_app()

import tkinter as tk
from tkinter import ttk, messagebox
import platform

# Windows 下避免 subprocess 弹控制台窗口导致“闪屏”
from windows_subprocess_patch import patch_subprocess_no_console
patch_subprocess_no_console()

# 确保当前目录在Python路径中
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_test_tool import AudioTestTool
from platform_utils import configure_macos_ttk_style, safe_show_tk_window, schedule_macos_ui_repaint

if __name__ == "__main__":
    try:
        root = tk.Tk()
        root.minsize(720, 580)
        from ui_components import UIComponents
        UIComponents._ensure_global_mousewheel_on(root)
        app = AudioTestTool(root)
        if not root.winfo_exists():
            raise SystemExit(0)
        configure_macos_ttk_style(app.style, root)
        if not safe_show_tk_window(root):
            raise SystemExit(0)
        schedule_macos_ui_repaint(root, app.style)
        root.mainloop()
    except Exception as e:
        import traceback

        traceback.print_exc()
        try:
            messagebox.showerror("声测大师启动失败", f"{type(e).__name__}: {e}")
        except Exception:
            pass
        raise SystemExit(1)