import tkinter as tk
from tkinter import ttk
import os
import sys
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