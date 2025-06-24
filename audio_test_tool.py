import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import os
import threading
import time
import sys
import shutil
import pygame  # 用于本地音频播放
import re  # 用于解析设备列表
import platform

from ui_components import UIComponents
from devices_operations import DeviceOperations
from test_operations import TestOperations

class AudioTestTool(UIComponents, DeviceOperations, TestOperations):
    def __init__(self, root):
        self.root = root
        self.root.title("声测大师(AcouTest)V1.6")
        self.root.geometry("750x650")
        self.root.resizable(False, False)
        
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
        
        # 设置样式
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 12), padding=10)
        self.style.configure("TLabel", font=("Arial", 12))
        self.style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        self.style.configure("Device.TLabel", font=("Arial", 10))
        self.style.configure("Refresh.TButton", font=("Arial", 10), padding=5)
        self.style.configure("Small.TButton", font=("Arial", 10), padding=5)
        self.style.configure("Small.TCheckbutton", font=("Arial", 10))
        self.style.configure("Delete.TButton", font=("Arial", 10), padding=2)
        
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
        
        # 初始化父类
        UIComponents.__init__(self, self)
        DeviceOperations.__init__(self, self)
        TestOperations.__init__(self, self)
        
        # 初始化pygame混音器
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"初始化pygame混音器失败: {str(e)}")
        
        # 创建界面
        self.create_widgets()
        
        # 检查ADB设备
        self.refresh_devices()
        
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
        # 创建测试结果目录
        if not os.path.exists("test"):
            os.makedirs("test")
        
        # 确保音频文件目录存在
        if not os.path.exists("audio"):
            os.makedirs("audio")
    
    def create_widgets(self):
        # 标题和设备选择区域
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", padx=20, pady=10)
        
        # 左侧标题
        header = ttk.Label(header_frame, text="声测大师(AcouTest)", style="Header.TLabel")
        header.pack(side="left", pady=10)
        
        # 右侧设备选择
        device_frame = ttk.Frame(header_frame)
        device_frame.pack(side="right", padx=10)
        
        ttk.Label(device_frame, text="设备:", font=("Arial", 10)).pack(side="left", padx=5)
        
        # 设备下拉菜单
        self.device_var = tk.StringVar()
        self.device_combobox = ttk.Combobox(device_frame, textvariable=self.device_var, 
                                          width=30, state="readonly")
        self.device_combobox.pack(side="left", padx=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        # 刷新按钮
        refresh_button = ttk.Button(device_frame, text="刷新", 
                                  command=self.refresh_devices, style="Refresh.TButton")
        refresh_button.pack(side="left", padx=5)
        
        # 网络ADB连接按钮
        connect_button = ttk.Button(device_frame, text="网络连接", style="Refresh.TButton", 
                                  command=self.show_network_connect_dialog)
        connect_button.pack(side="left", padx=5)
        
        # 添加ADB调试按钮
        debug_button = ttk.Button(device_frame, text="调试ADB", style="Refresh.TButton", 
                                command=self.debug_adb_connection)
        debug_button.pack(side="left", padx=5)
        
        # 设备状态标签
        device_status = ttk.Label(self.root, textvariable=self.device_status_var, 
                                foreground="red", anchor="center")
        device_status.pack(fill="x", padx=20)
        
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
        
        version_label = ttk.Label(status_bar, text="V1.6", font=("Arial", 9))
        version_label.pack(side="right")
