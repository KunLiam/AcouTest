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
        self.root.title("音频调试小助手V1.5")
        self.root.geometry("750x650")  # 增加宽度从650到750
        self.root.resizable(False, False)
        
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
        header = ttk.Label(header_frame, text="音频调试工具", style="Header.TLabel")
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
        
        # 设备状态标签
        device_status = ttk.Label(self.root, textvariable=self.device_status_var, 
                                foreground="red", anchor="center")
        device_status.pack(fill="x", padx=20)
        
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 创建选项卡
        self.tab_control = ttk.Notebook(main_frame)
        
        # Loopback和Ref通道测试选项卡 (原10通道测试)
        loopback_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(loopback_tab, text="Loopback和Ref测试")
        
        # 麦克风测试选项卡
        mic_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(mic_tab, text="麦克风测试")
        
        # 多声道测试选项卡
        multichannel_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(multichannel_tab, text="多声道测试")
        
        # 本地播放选项卡
        local_playback_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(local_playback_tab, text="本地播放")
        
        # mic扫频测试选项卡
        sweep_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(sweep_tab, text="mic扫频测试")
        
        # 喇叭测试选项卡
        speaker_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(speaker_tab, text="喇叭测试")
        
        # HAL 录音选项卡
        hal_recording_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(hal_recording_tab, text="HAL 录音")
        
        # Logcat选项卡
        logcat_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(logcat_tab, text="Logcat")
        
        # 截图选项卡
        screenshot_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(screenshot_tab, text="截图")
        
        # 在其他选项卡添加之后，添加雷达检查选项卡
        radar_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(radar_tab, text="雷达检查")
        self.setup_radar_tab(radar_tab)
        
        # 在其他选项卡添加之后，添加遥控器选项卡
        remote_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(remote_tab, text="遥控器")
        self.setup_remote_tab(remote_tab)
        
        self.tab_control.pack(expand=1, fill="both")
        
        # Loopback和Ref通道测试内容
        self.setup_loopback_tab(loopback_tab)
        
        # 麦克风测试内容
        self.setup_mic_tab(mic_tab)
        
        # 多声道测试内容
        self.setup_multichannel_tab(multichannel_tab)
        
        # 本地播放内容
        self.setup_local_playback_tab(local_playback_tab)
        
        # mic扫频测试内容
        self.setup_sweep_tab(sweep_tab)
        
        # 喇叭测试内容
        self.setup_speaker_tab(speaker_tab)
        
        # HAL 录音内容
        self.setup_hal_recording_tab(hal_recording_tab)
        
        # Logcat内容
        self.setup_logcat_tab(logcat_tab)
        
        # 截图内容
        self.setup_screenshot_tab(screenshot_tab)
        
        # 状态栏
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom", padx=20, pady=5)
        
        status_label = ttk.Label(status_bar, textvariable=self.status_var, font=("Arial", 9))
        status_label.pack(side="left")
        
        version_label = ttk.Label(status_bar, text="V1.5", font=("Arial", 9))
        version_label.pack(side="right") 