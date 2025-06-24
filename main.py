import tkinter as tk
from tkinter import ttk
import os
import sys
import platform

# 确保当前目录在Python路径中
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_test_tool import AudioTestTool

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioTestTool(root)
    root.mainloop() 