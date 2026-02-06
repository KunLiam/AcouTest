import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import os
import threading
import time
import sys
import shutil
import re  # 用于解析设备列表
import platform
import urllib.parse

from ui_components import UIComponents
from devices_operations import DeviceOperations
from test_operations import TestOperations
from optional_deps import try_import_pygame
from output_paths import get_output_dir, DIR_MIC_TEST
from feature_config import APP_VERSION

class AudioTestTool(UIComponents, DeviceOperations, TestOperations):
    def __init__(self, root):
        self.root = root
        self.root.title(f"声测大师(AcouTest) v{APP_VERSION}")
        self.root.geometry("750x650")
        self.root.resizable(False, False)

        # pygame 是可选依赖：只用于“本地播放”
        # 在某些 PyInstaller + numpy 环境下导入可能崩溃，因此必须按需、可失败
        self._pygame = None
        self._pygame_error = None
        
        # 首先初始化所有UI变量
        self.init_mic_variables()
        
        # 调用父类初始化
        UIComponents.__init__(self, root)
        DeviceOperations.__init__(self, root)
        TestOperations.__init__(self, root)
        
        # 设置应用图标/logo - 更强健的版本
        try:
            # 尝试多种可能的路径
            possible_paths = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(sys._MEIPASS, "logo", "AcouTest.png") if hasattr(sys, "_MEIPASS") else None
            ]
            
            logo_loaded = False
            for path in possible_paths:
                if path and os.path.exists(path):
                    print(f"找到logo: {path}")
                    try:
                        icon_image = tk.PhotoImage(file=path)
                        self.root.tk.call('wm', 'iconphoto', self.root._w, icon_image)
                        print(f"成功加载logo: {path}")
                        logo_loaded = True
                        break
                    except Exception as e:
                        print(f"加载 {path} 失败: {e}")
            
            if not logo_loaded:
                print("无法加载任何logo文件")
        except Exception as e:
            print(f"设置Logo时出错: {str(e)}")
        
        # 在Windows系统上使用.ico文件
        if platform.system() == "Windows":
            try:
                ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo", "AcouTest.ico")
                if os.path.exists(ico_path):
                    self.root.iconbitmap(ico_path)
                elif os.path.exists("logo/AcouTest.ico"):
                    self.root.iconbitmap("logo/AcouTest.ico")
            except Exception as e:
                print(f"设置Windows图标出错: {str(e)}")
        
        # 设置样式（统一更耐看的默认灰色风格：不强制绿/红按钮）
        self.style = ttk.Style()
        font_family = "Microsoft YaHei UI" if platform.system() == "Windows" else "Arial"
        self.style.configure("TButton", font=(font_family, 10), padding=(12, 6))
        self.style.configure("TLabel", font=(font_family, 10))
        self.style.configure("Header.TLabel", font=(font_family, 13, "bold"))
        self.style.configure("Device.TLabel", font=(font_family, 9))
        self.style.configure("Refresh.TButton", font=(font_family, 9), padding=(10, 4))
        self.style.configure("Small.TButton", font=(font_family, 9), padding=(10, 4))
        self.style.configure("Small.TCheckbutton", font=(font_family, 9))
        self.style.configure("Delete.TButton", font=(font_family, 9), padding=(6, 2))
        self.style.configure("Muted.TLabel", font=(font_family, 9), foreground="#666666")
        
        # 创建目录结构
        self.ensure_directories()
        
        # 初始化变量
        self.selected_audio_file = None
        self.local_audio_file = None
        self.file_extension = ""
        self.debug_info = ""
        self.devices = []  # 存储检测到的设备列表
        self.selected_device = None  # 当前选择的设备
        self.status_var = tk.StringVar(value="就绪")  # 初始化状态变量
        self.device_status_var = tk.StringVar(value="未检测到设备")  # 初始化设备状态变量
        
        # 尝试初始化 pygame 混音器（失败不影响其它功能）
        self._init_pygame_mixer()
        
        # 创建界面
        self.create_widgets()
        
        # 检查ADB设备
        self.refresh_devices()

        # 键盘挂载：当应用获得焦点时，用电脑键盘通过 ADB 给设备输入
        self._setup_keyboard_adb_input()
        
        # 在__init__方法的最后
        try:
            # 检查打包后的文件结构
            base_dir = os.path.dirname(os.path.abspath(__file__))
            print("基础目录:", base_dir)
            print("目录内容:", os.listdir(base_dir))
            if os.path.exists(os.path.join(base_dir, "logo")):
                print("Logo目录内容:", os.listdir(os.path.join(base_dir, "logo")))
        except Exception as e:
            print(f"检查目录结构时出错: {str(e)}")
        
    def ensure_directories(self):
        """确保必要的目录结构存在"""
        # Loopback/Ref 等测试录音已统一保存到 output/loopback/（见 output_paths），不再创建旧版 test/ 目录

        # audio/ 作为用户可放置自定义文件的入口（文件夹可以为空）
        if not os.path.exists("audio"):
            os.makedirs("audio")

    def _setup_keyboard_adb_input(self):
        """
        键盘挂载（仅当应用窗口获得焦点/鼠标进入窗口时生效）：
        - 方向键/回车/ESC/Backspace 等 -> adb shell input keyevent
        - 可打印字符 -> adb shell input text

        设计目标：不影响用户在本工具的输入框里编辑参数。
        """

        def _focus_on_enter(widget):
            try:
                widget.bind("<Enter>", lambda e: widget.focus_set(), add=True)
            except Exception:
                pass

        _focus_on_enter(self.root)

        def _is_text_widget(w) -> bool:
            """
            是否应当把该控件视为“用户正在本工具里输入”的控件。
            - Entry/Combobox：一律视为输入控件（不转发到设备）
            - Text：仅当可编辑（state != disabled）时视为输入控件；
              只读日志窗口（disabled）不应阻止键盘挂载。
            """
            try:
                if isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox)):
                    return True
                if isinstance(w, tk.Text):
                    try:
                        if str(w.cget("state")) == "disabled":
                            return False
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
            return False

        def _mods(e: tk.Event):
            # Tk state bitmask: 0x4=Control, 0x8=Alt(usually Mod1)
            try:
                ctrl = bool(e.state & 0x4)
                alt = bool(e.state & 0x8)
            except Exception:
                ctrl, alt = False, False
            return ctrl, alt

        def _adb_serial() -> str:
            try:
                return (self.device_var.get() or "").strip()
            except Exception:
                return ""

        def _run_adb(args):
            # 关键点：shell=False，避免 Windows cmd.exe 对 %xx / %s 做环境变量展开，导致 input text 失效
            try:
                subprocess.run(args, shell=False, capture_output=True, text=True)
            except Exception:
                pass

        def _adb_input_keyevent(android_key: str):
            serial = _adb_serial()
            if not serial:
                return
            _run_adb(["adb", "-s", serial, "shell", "input", "keyevent", f"KEYCODE_{android_key}"])

        def _adb_input_text(txt: str):
            serial = _adb_serial()
            if not serial:
                return
            # adb input text：空格用 %s；其余字符用 URL 编码（注意：adb input 本身对中文支持也有限）
            encoded = urllib.parse.quote(txt, safe="")
            encoded = encoded.replace("%20", "%s")
            _run_adb(["adb", "-s", serial, "shell", "input", "text", encoded])

        key_map = {
            "Up": "DPAD_UP",
            "Down": "DPAD_DOWN",
            "Left": "DPAD_LEFT",
            "Right": "DPAD_RIGHT",
            # 参考你的“使用帮助”：Enter -> 遥控器 OK（DPAD_CENTER）
            "Return": "DPAD_CENTER",
            "KP_Enter": "DPAD_CENTER",
            "Escape": "BACK",
            "BackSpace": "DEL",
            "Delete": "FORWARD_DEL",
            "Home": "HOME",
        }

        def _on_keypress(e: tk.Event):
            # 当用户在输入框里输入时，不拦截（否则会影响填写参数/粘贴）
            try:
                if _is_text_widget(e.widget):
                    return
            except Exception:
                pass

            keysym = getattr(e, "keysym", "") or ""
            char = getattr(e, "char", "") or ""
            ctrl, alt = _mods(e)

            # Ctrl+V：把剪贴板内容发送到设备（不支持中文属于 adb input 的限制）
            if ctrl and (not alt) and keysym.lower() == "v":
                try:
                    clip = self.root.clipboard_get()
                except Exception:
                    clip = ""
                if clip:
                    _adb_input_text(clip)
                    return "break"
                return

            # Ctrl+Alt+Enter：作为“软键盘确认”（走 KEYCODE_ENTER）
            if ctrl and alt and keysym in ("Return", "KP_Enter"):
                _adb_input_keyevent("ENTER")
                return "break"

            # 其它 Ctrl/Alt 组合键默认不转发，避免干扰用户在 PC 侧的快捷键/系统行为
            if ctrl or alt:
                return

            if keysym in key_map:
                _adb_input_keyevent(key_map[keysym])
                return "break"

            # 可打印字符：转为 input text
            if char and char.isprintable():
                _adb_input_text(char)
                return "break"

        # bind_all：让所有窗口（含 Toplevel）在获得焦点时都能响应
        self.root.bind_all("<KeyPress>", _on_keypress, add=True)
    
    def create_widgets(self):
        # 标题和设备选择区域
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", padx=10, pady=5)
        
        # 标题
        title_label = ttk.Label(header_frame, text="声测大师(AcouTest)", 
                               font=("Arial", 16, "bold"))
        title_label.pack(side="left")
        
        # 设备选择区域
        device_frame = ttk.Frame(header_frame)
        device_frame.pack(side="right")
        
        # 设备选择
        ttk.Label(device_frame, text="设备:", font=("Arial", 9)).pack(side="left", padx=(0, 5))
        
        self.device_var = tk.StringVar()
        self.device_combobox = ttk.Combobox(device_frame, textvariable=self.device_var, 
                                           width=20, state="readonly", font=("Arial", 9))
        self.device_combobox.pack(side="left", padx=(0, 5))
        self.device_combobox.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        # 刷新按钮 - 调小字体
        refresh_btn = ttk.Button(device_frame, text="刷新", command=self.refresh_devices, width=6)
        refresh_btn.pack(side="left", padx=(0, 5))
        refresh_btn.configure(style="Small.TButton")
        
        # 网络连接按钮 - 调小字体
        network_btn = ttk.Button(device_frame, text="网络连接", command=self.show_network_connect_dialog, width=8)
        network_btn.pack(side="left", padx=(0, 5))
        network_btn.configure(style="Small.TButton")
        
        # 软件信息：小问号图标 + 悬停提示「查看软件信息」+ 点击弹窗
        about_icon = tk.Label(
            device_frame, text="?", font=("Arial", 10, "bold"), fg="#0066cc", bg="#cce5ff",
            width=2, cursor="hand2", relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#99ccff"
        )
        about_icon.pack(side="left", padx=(0, 5), ipady=1, ipadx=1)
        about_icon.bind("<Button-1>", lambda e: self.show_software_info())
        self._about_tooltip_after = None
        self._about_tooltip_win = None
        def _show_about_tooltip():
            self._about_tooltip_after = None
            if not about_icon.winfo_exists():
                return
            self._about_tooltip_win = tk.Toplevel(about_icon)
            self._about_tooltip_win.overrideredirect(True)
            self._about_tooltip_win.wm_attributes("-topmost", True)
            lbl = tk.Label(self._about_tooltip_win, text="查看软件信息", font=("Arial", 9),
                           bg="#ffffe0", fg="#333", relief="solid", bd=1, padx=6, pady=3)
            lbl.pack()
            self._about_tooltip_win.update_idletasks()
            tw = self._about_tooltip_win.winfo_reqwidth()
            x = about_icon.winfo_rootx() + about_icon.winfo_width() // 2 - tw // 2
            y = about_icon.winfo_rooty() + about_icon.winfo_height() + 4
            self._about_tooltip_win.geometry(f"+{max(0, x)}+{y}")
        def _on_about_enter(e):
            if self._about_tooltip_after:
                self.root.after_cancel(self._about_tooltip_after)
            self._about_tooltip_after = self.root.after(500, _show_about_tooltip)
        def _on_about_leave(e):
            if self._about_tooltip_after:
                self.root.after_cancel(self._about_tooltip_after)
                self._about_tooltip_after = None
            if self._about_tooltip_win and self._about_tooltip_win.winfo_exists():
                self._about_tooltip_win.destroy()
                self._about_tooltip_win = None
        about_icon.bind("<Enter>", _on_about_enter)
        about_icon.bind("<Leave>", _on_about_leave)
        
        # 创建小字体样式
        style = ttk.Style()
        style.configure("Small.TButton", font=("Arial", 9))
        
        # 主内容区域
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 使用改进的分类标签页设计
        self.create_main_ui(main_container)
        
        # 状态栏
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom", padx=20, pady=5)
        
        status_label = ttk.Label(status_bar, textvariable=self.status_var, font=("Arial", 9))
        status_label.pack(side="left")
        
        version_label = ttk.Label(status_bar, text=f"V{APP_VERSION} | 软件信息", font=("Arial", 9), cursor="hand2")
        version_label.pack(side="right")
        version_label.bind("<Button-1>", lambda e: self.show_software_info())

    def init_mic_variables(self):
        """初始化麦克风测试相关变量"""
        print("开始初始化麦克风测试变量...")
        
        # 初始化所有麦克风测试相关的StringVar变量
        self.mic_count_var = tk.StringVar(value="4")
        self.pcm_device_var = tk.StringVar(value="0") 
        self.device_id_var = tk.StringVar(value="3")
        self.rate_var = tk.StringVar(value="16000")
        self.mic_save_path_var = tk.StringVar(value=get_output_dir(DIR_MIC_TEST))
        self.mic_info_var = tk.StringVar(value="准备就绪")
        
        # 初始化测试状态变量
        self.mic_is_testing = False
        self._starting_mic_test = False
        self._mic_thread_running = False
        
        print("麦克风测试变量初始化完成")
        print(f"mic_count_var: {self.mic_count_var}")
        print(f"pcm_device_var: {self.pcm_device_var}")
        print(f"device_id_var: {self.device_id_var}")
        print(f"rate_var: {self.rate_var}")
        print(f"mic_save_path_var: {self.mic_save_path_var}")
        print(f"mic_info_var: {self.mic_info_var}")

    def _init_pygame_mixer(self):
        """初始化 pygame mixer（可失败，不阻塞主流程）"""
        pg, err = try_import_pygame()
        self._pygame = pg
        self._pygame_error = err

        if not pg:
            print(f"pygame 不可用（将禁用本地播放）: {err}")
            return

        try:
            pg.mixer.init()
        except Exception as e:
            self._pygame = None
            self._pygame_error = f"{type(e).__name__}: {e}"
            print(f"初始化pygame混音器失败（将禁用本地播放）: {self._pygame_error}")
