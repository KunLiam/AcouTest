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

class AudioTestTool:
    def __init__(self, root):
        self.root = root
        self.root.title("音频测试小助手V1.3")
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
        header = ttk.Label(header_frame, text="音频测试工具", style="Header.TLabel")
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
        
        # 屏幕录制选项卡
        self.setup_screenrecord_tab(screenshot_tab)
        
        # 状态栏
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", side="bottom", padx=20, pady=5)
        
        status_label = ttk.Label(status_bar, textvariable=self.status_var, font=("Arial", 9))
        status_label.pack(side="left")
        
        version_label = ttk.Label(status_bar, text="V1.2", font=("Arial", 9))
        version_label.pack(side="right")
    
    def refresh_devices(self):
        """刷新设备列表"""
        try:
            self.status_var.set("正在检查设备...")
            
            # 获取设备列表
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"ADB命令执行失败: {result.stderr}")
            
            # 解析设备列表
            lines = result.stdout.strip().split('\n')[1:]  # 跳过第一行标题
            self.devices = []
            
            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0].strip()
                        status = parts[1].strip()
                        
                        if status == "device":  # 只添加已连接的设备
                            try:
                                # 获取设备型号
                                model_result = subprocess.run(
                                    ["adb", "-s", device_id, "shell", "getprop", "ro.product.model"], 
                                    capture_output=True, text=True
                                )
                                
                                model = model_result.stdout.strip() if model_result.returncode == 0 else "未知型号"
                                
                                # 获取设备序列号
                                sn_result = subprocess.run(
                                    ["adb", "-s", device_id, "shell", "getprop", "ro.serialno"], 
                                    capture_output=True, text=True
                                )
                                
                                sn = sn_result.stdout.strip() if sn_result.returncode == 0 else device_id
                                
                                self.devices.append({
                                    "id": device_id,
                                    "model": model,
                                    "sn": sn,
                                    "display_name": f"{model} ({sn})"
                                })
                            except Exception as e:
                                print(f"获取设备信息出错: {str(e)}")
                                # 添加基本信息
                                self.devices.append({
                                    "id": device_id,
                                    "model": "未知型号",
                                    "sn": device_id,
                                    "display_name": f"设备 ({device_id})"
                                })
            
            # 更新设备下拉菜单
            self.device_combobox['values'] = [d["display_name"] for d in self.devices]
            
            # 更新设备状态
            if self.devices:
                self.device_status_var.set(f"检测到 {len(self.devices)} 个设备")
                # 更新设备状态标签颜色为绿色
                self.update_device_status_color("green")
                
                # 如果之前没有选择设备，自动选择第一个
                if not self.selected_device:
                    self.device_combobox.current(0)
                    self.on_device_selected(None)
            else:
                self.device_status_var.set("未检测到设备")
                # 更新设备状态标签颜色为红色
                self.update_device_status_color("red")
                
                self.selected_device = None
                if hasattr(self, 'device_combobox'):
                    self.device_combobox.set("")  # 清空选择
            
            self.status_var.set("设备检查完成")
            
        except Exception as e:
            self.device_status_var.set("设备检查出错")
            # 更新设备状态标签颜色为红色
            self.update_device_status_color("red")
            
            self.status_var.set(f"设备检查出错: {str(e)}")
            print(f"设备检查出错: {str(e)}")  # 打印到控制台以便调试
    
    def on_device_selected(self, event=None):
        """设备选择事件处理"""
        if not self.devices:  # 如果没有设备，直接返回
            return
            
        selected_index = self.device_combobox.current()
        if selected_index >= 0 and selected_index < len(self.devices):
            selected_device = self.devices[selected_index]
            self.selected_device = selected_device["id"]  # 保存设备ID
            self.status_var.set(f"已连接到设备: {selected_device['display_name']}")
            self.device_status_var.set(f"已选择设备: {selected_device['display_name']}")
            # 更新设备状态标签颜色为绿色
            self.update_device_status_color("green")
            
            # 自动创建HAL录音目录
            if hasattr(self, 'hal_dir_var'):
                # 在后台线程中创建目录，避免阻塞UI
                threading.Thread(target=self.auto_create_hal_dir, daemon=True).start()
        else:
            self.selected_device = None
            self.status_var.set("未选择设备")
            self.device_status_var.set("未选择设备")
            # 更新设备状态标签颜色为红色
            self.update_device_status_color("red")
    
    def get_adb_command(self, command):
        """获取带有设备ID的ADB命令"""
        if self.selected_device:
            return f"adb -s {self.selected_device} {command}"
        else:
            return f"adb {command}"
    
    def check_device_selected(self):
        """检查是否已选择设备"""
        if not self.selected_device:
            # 自动刷新设备列表而不是显示错误消息
            self.refresh_devices()
            if not self.selected_device:
                self.status_var.set("请先选择一个设备")
                return False
        return True
    
    def setup_loopback_tab(self, parent):
        """设置Loopback和Ref通道测试选项卡"""
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        frame = ttk.Frame(scrollable_frame, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="播放音频并同时录制通道音频\n用于验证音频回路和参考信号")
        desc.pack(pady=10)
        
        # 参数设置
        params_frame = ttk.LabelFrame(frame, text="参数设置")
        params_frame.pack(fill="x", pady=10, padx=5)
        
        # 设备ID
        device_frame = ttk.Frame(params_frame)
        device_frame.pack(fill="x", pady=5)
        ttk.Label(device_frame, text="录制设备ID:").pack(side="left", padx=5)
        self.loopback_device_var = tk.StringVar(value="6")
        ttk.Entry(device_frame, textvariable=self.loopback_device_var, width=5).pack(side="left", padx=5)
        
        # 通道数
        channel_frame = ttk.Frame(params_frame)
        channel_frame.pack(fill="x", pady=5)
        ttk.Label(channel_frame, text="通道数:").pack(side="left", padx=5)
        self.loopback_channel_var = tk.StringVar(value="10")
        ttk.Entry(channel_frame, textvariable=self.loopback_channel_var, width=5).pack(side="left", padx=5)
        
        # 采样率
        rate_frame = ttk.Frame(params_frame)
        rate_frame.pack(fill="x", pady=5)
        ttk.Label(rate_frame, text="采样率:").pack(side="left", padx=5)
        self.loopback_rate_var = tk.StringVar(value="16000")
        ttk.Entry(rate_frame, textvariable=self.loopback_rate_var, width=8).pack(side="left", padx=5)
        
        # 音频文件选择
        file_frame = ttk.LabelFrame(frame, text="音频文件")
        file_frame.pack(fill="x", pady=10, padx=5)
        
        # 默认文件选项
        self.audio_source_var = tk.StringVar(value="default")
        ttk.Radiobutton(file_frame, text="使用默认测试音频 (7.1声道)", 
                       variable=self.audio_source_var, value="default").pack(anchor="w", padx=5, pady=2)
        
        # 自定义文件选项
        custom_file_frame = ttk.Frame(file_frame)
        custom_file_frame.pack(fill="x", pady=5)
        ttk.Radiobutton(custom_file_frame, text="使用自定义音频文件:", 
                       variable=self.audio_source_var, value="custom").pack(side="left", padx=5)
        
        self.file_path_var = tk.StringVar(value="未选择文件")
        file_label = ttk.Label(custom_file_frame, textvariable=self.file_path_var, 
                              width=30, background="#f0f0f0", anchor="w")
        file_label.pack(side="left", padx=5, fill="x", expand=True)
        
        browse_button = ttk.Button(custom_file_frame, text="浏览...", 
                                  command=self.browse_audio_file, width=10)
        browse_button.pack(side="left", padx=5)
        
        # 按钮区域
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=20)
        
        # 开始按钮
        self.start_loopback_button = ttk.Button(button_frame, text="开始通道测试", 
                                         command=self.run_loopback_test, width=15)
        self.start_loopback_button.pack(side="left", padx=10, expand=True)
        
        # 停止按钮
        self.stop_loopback_button = ttk.Button(button_frame, text="停止录制", 
                                        command=self.stop_loopback_recording, width=15, state="disabled")
        self.stop_loopback_button.pack(side="left", padx=10, expand=True)
        
        # 状态显示
        self.loopback_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.loopback_status_var)
        status_label.pack(pady=10)
        
        # 添加一些额外的空间确保按钮可见
        spacer = ttk.Frame(frame, height=20)
        spacer.pack()
    
    def setup_mic_tab(self, parent):
        """设置麦克风测试选项卡"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="录制麦克风输入并保存为WAV文件\n用于测试麦克风功能")
        desc.pack(pady=10)
        
        # 参数设置
        params_frame = ttk.LabelFrame(frame, text="参数设置")
        params_frame.pack(fill="x", pady=10, padx=5)
        
        # 麦克风数量
        mic_frame = ttk.Frame(params_frame)
        mic_frame.pack(fill="x", pady=5)
        ttk.Label(mic_frame, text="麦克风数量:").pack(side="left", padx=5)
        self.mic_var = tk.StringVar(value="4")
        mic_combo = ttk.Combobox(mic_frame, textvariable=self.mic_var, 
                               values=["1", "2", "3", "4"], width=5, state="readonly")
        mic_combo.pack(side="left", padx=5)
        
        # PCM设备
        pcm_frame = ttk.Frame(params_frame)
        pcm_frame.pack(fill="x", pady=5)
        ttk.Label(pcm_frame, text="PCM设备:").pack(side="left", padx=5)
        self.mic_pcm_var = tk.StringVar(value="0")
        ttk.Entry(pcm_frame, textvariable=self.mic_pcm_var, width=5).pack(side="left", padx=5)
        
        # 设备ID
        device_frame = ttk.Frame(params_frame)
        device_frame.pack(fill="x", pady=5)
        ttk.Label(device_frame, text="设备ID:").pack(side="left", padx=5)
        self.mic_device_var = tk.StringVar(value="3")
        ttk.Entry(device_frame, textvariable=self.mic_device_var, width=5).pack(side="left", padx=5)
        
        # 采样率
        rate_frame = ttk.Frame(params_frame)
        rate_frame.pack(fill="x", pady=5)
        ttk.Label(rate_frame, text="采样率:").pack(side="left", padx=5)
        self.mic_rate_var = tk.StringVar(value="16000")
        ttk.Entry(rate_frame, textvariable=self.mic_rate_var, width=8).pack(side="left", padx=5)
        
        # 按钮区域
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=20)
        
        # 开始按钮
        self.start_mic_button = ttk.Button(button_frame, text="开始麦克风测试", 
                                     command=self.run_mic_test, width=15)
        self.start_mic_button.pack(side="left", padx=10, expand=True)
        
        # 停止按钮
        self.stop_mic_button = ttk.Button(button_frame, text="停止录制", 
                                    command=self.stop_mic_recording, width=15, state="disabled")
        self.stop_mic_button.pack(side="left", padx=10, expand=True)
        
        # 状态显示
        self.mic_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.mic_status_var)
        status_label.pack(pady=10)
    
    def setup_multichannel_tab(self, parent):
        """设置多声道测试选项卡"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="播放7.1声道测试音频\n用于验证多声道音频输出")
        desc.pack(pady=10)
        
        # 参数设置
        params_frame = ttk.LabelFrame(frame, text="参数设置")
        params_frame.pack(fill="x", pady=10, padx=5)
        
        # 采样率
        rate_frame = ttk.Frame(params_frame)
        rate_frame.pack(fill="x", pady=5)
        ttk.Label(rate_frame, text="采样率:").pack(side="left", padx=5)
        self.multi_rate_var = tk.StringVar(value="48000")
        ttk.Entry(rate_frame, textvariable=self.multi_rate_var, width=8).pack(side="left", padx=5)
        
        # 位深度
        bit_frame = ttk.Frame(params_frame)
        bit_frame.pack(fill="x", pady=5)
        ttk.Label(bit_frame, text="位深度:").pack(side="left", padx=5)
        self.multi_bit_var = tk.StringVar(value="16")
        ttk.Entry(bit_frame, textvariable=self.multi_bit_var, width=5).pack(side="left", padx=5)
        
        # 开始按钮
        start_button = ttk.Button(frame, text="开始多声道测试", 
                                command=self.run_multichannel_test)
        start_button.pack(pady=20)
    
    def setup_local_playback_tab(self, parent):
        """设置本地播放选项卡"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="选择本地电脑上的音频/视频文件\n通过Android设备播放，声音从设备音箱输出")
        desc.pack(pady=10)
        
        # 文件选择区域
        file_frame = ttk.LabelFrame(frame, text="选择音频/视频文件")
        file_frame.pack(fill="x", pady=20, padx=5)
        
        file_select_frame = ttk.Frame(file_frame)
        file_select_frame.pack(fill="x", pady=10, padx=5)
        
        self.local_file_path_var = tk.StringVar(value="未选择文件")
        file_label = ttk.Label(file_select_frame, textvariable=self.local_file_path_var, 
                              width=40, background="#f0f0f0", anchor="w")
        file_label.pack(side="left", padx=5, fill="x", expand=True)
        
        browse_button = ttk.Button(file_select_frame, text="浏览...", 
                                  command=self.browse_local_audio_file, width=10)
        browse_button.pack(side="left", padx=5)
        
        # 播放控制区域
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill="x", pady=20)
        
        # 播放方式选择
        self.playback_mode_var = tk.StringVar(value="device")
        mode_frame = ttk.LabelFrame(frame, text="播放方式")
        mode_frame.pack(fill="x", pady=10, padx=5)
        
        ttk.Radiobutton(mode_frame, text="通过Android设备播放（声音从设备音箱输出）", 
                       variable=self.playback_mode_var, value="device").pack(anchor="w", padx=5, pady=2)
        ttk.Radiobutton(mode_frame, text="在本地电脑播放（声音从电脑扬声器输出）", 
                       variable=self.playback_mode_var, value="local").pack(anchor="w", padx=5, pady=2)
        
        # 播放按钮
        play_button = ttk.Button(control_frame, text="播放", 
                               command=self.play_local_audio, width=15)
        play_button.pack(side="left", padx=10, expand=True)
        
        stop_button = ttk.Button(control_frame, text="停止", 
                               command=self.stop_local_audio, width=15)
        stop_button.pack(side="left", padx=10, expand=True)
        
        # 音量控制 (仅用于本地播放)
        volume_frame = ttk.LabelFrame(frame, text="音量 (仅用于本地播放)")
        volume_frame.pack(fill="x", pady=10, padx=5)
        
        self.volume_var = tk.DoubleVar(value=0.7)  # 默认音量70%
        volume_scale = ttk.Scale(volume_frame, from_=0, to=1, 
                               variable=self.volume_var, 
                               command=self.update_volume)
        volume_scale.pack(fill="x", padx=10, pady=10)
        
        # 播放状态
        self.playback_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.playback_status_var)
        status_label.pack(pady=10)
        
        # 调试信息
        debug_button = ttk.Button(frame, text="调试信息", 
                                command=self.show_debug_info, width=15)
        debug_button.pack(pady=5)
    
    def setup_sweep_tab(self, parent):
        """设置扫频测试选项卡"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 创建上下两栏布局
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", pady=5)
        
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill="both", expand=True, pady=5)
        
        # 上部 - 控制区域
        control_frame = ttk.LabelFrame(top_frame, text="扫频控制", padding=5)
        control_frame.pack(fill="x", expand=True)
        
        # 扫频文件选择
        file_frame = ttk.Frame(control_frame)
        file_frame.pack(fill="x", pady=2)
        
        # 扫频类型选择
        self.sweep_type_var = tk.StringVar(value="elephant")
        ttk.Radiobutton(file_frame, text="大象扫频文件", variable=self.sweep_type_var, 
                      value="elephant", command=self.update_sweep_file_options, 
                      style="Small.TCheckbutton").pack(side="left", padx=10)
        ttk.Radiobutton(file_frame, text="自定义扫频文件", variable=self.sweep_type_var, 
                      value="custom", command=self.update_sweep_file_options, 
                      style="Small.TCheckbutton").pack(side="left", padx=10)
        
        # 批量测试选项
        self.sweep_batch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(file_frame, text="批量测试所有文件", variable=self.sweep_batch_var,
                      style="Small.TCheckbutton").pack(side="right", padx=10)
        
        # 扫频文件下拉框
        file_select_frame = ttk.Frame(control_frame)
        file_select_frame.pack(fill="x", pady=2)
        
        ttk.Label(file_select_frame, text="扫频文件:", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.sweep_file_var = tk.StringVar()
        self.sweep_file_combobox = ttk.Combobox(file_select_frame, textvariable=self.sweep_file_var, 
                                              width=40, state="readonly")
        self.sweep_file_combobox.pack(side="left", fill="x", expand=True, padx=2)
        
        # 添加自定义文件按钮
        self.add_custom_sweep_button = ttk.Button(file_select_frame, text="添加文件", 
                                               command=self.add_custom_sweep_file, width=10, 
                                               style="Small.TButton", state="disabled")
        self.add_custom_sweep_button.pack(side="right", padx=2)
        
        # 播放设置
        playback_frame = ttk.LabelFrame(control_frame, text="播放设置", padding=5)
        playback_frame.pack(fill="x", pady=5)
        
        # 播放设备选择
        device_frame = ttk.Frame(playback_frame)
        device_frame.pack(fill="x", pady=2)
        
        ttk.Label(device_frame, text="播放设备:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 播放设备下拉菜单 - 使用PCM设备号
        self.sweep_playback_device_var = tk.StringVar(value="0")
        playback_device_combobox = ttk.Combobox(device_frame, textvariable=self.sweep_playback_device_var, 
                                          width=5, values=["0", "1", "2", "3", "4", "5"])
        playback_device_combobox.pack(side="left", padx=2)
        
        # 播放卡号
        ttk.Label(device_frame, text="卡号:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_playback_card_var = tk.StringVar(value="0")
        ttk.Combobox(device_frame, textvariable=self.sweep_playback_card_var, 
               width=5, values=["0", "1", "2"]).pack(side="left", padx=2)
        
        # 播放参数
        param_frame = ttk.Frame(playback_frame)
        param_frame.pack(fill="x", pady=2)
        
        ttk.Label(param_frame, text="采样率:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_playback_rate_var = tk.StringVar(value="48000")
        ttk.Entry(param_frame, textvariable=self.sweep_playback_rate_var, 
                font=("Arial", 9), width=8).pack(side="left", padx=2)
        
        ttk.Label(param_frame, text="通道数:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_playback_channels_var = tk.StringVar(value="4")
        ttk.Entry(param_frame, textvariable=self.sweep_playback_channels_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        ttk.Label(param_frame, text="位深:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_playback_bits_var = tk.StringVar(value="16")
        ttk.Entry(param_frame, textvariable=self.sweep_playback_bits_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        # 录制设置
        recording_frame = ttk.LabelFrame(control_frame, text="录制设置", padding=5)
        recording_frame.pack(fill="x", pady=5)
        
        # 录制设备选择
        rec_device_frame = ttk.Frame(recording_frame)
        rec_device_frame.pack(fill="x", pady=2)
        
        ttk.Label(rec_device_frame, text="录制设备:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 录制设备下拉菜单 - 使用PCM设备号
        self.sweep_recording_device_var = tk.StringVar(value="6")  # 默认使用LOOPBACK-A设备
        recording_device_combobox = ttk.Combobox(rec_device_frame, textvariable=self.sweep_recording_device_var, 
                                           width=5, values=["0", "1", "2", "3", "4", "5", "6"])
        recording_device_combobox.pack(side="left", padx=2)
        
        # 录制卡号
        ttk.Label(rec_device_frame, text="卡号:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_card_var = tk.StringVar(value="0")
        ttk.Combobox(rec_device_frame, textvariable=self.sweep_recording_card_var, 
               width=5, values=["0", "1", "2"]).pack(side="left", padx=2)
        
        # 录制参数
        rec_param_frame = ttk.Frame(recording_frame)
        rec_param_frame.pack(fill="x", pady=2)
        
        ttk.Label(rec_param_frame, text="采样率:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_rate_var = tk.StringVar(value="48000")
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_rate_var, 
                font=("Arial", 9), width=8).pack(side="left", padx=2)
        
        ttk.Label(rec_param_frame, text="通道数:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_channels_var = tk.StringVar(value="10")
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_channels_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        ttk.Label(rec_param_frame, text="位深:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_bits_var = tk.StringVar(value="16")
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_bits_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        ttk.Label(rec_param_frame, text="时长(秒):", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_duration_var = tk.StringVar(value="10")  # 增加默认录制时长
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_duration_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        # 保存路径设置
        save_path_frame = ttk.Frame(control_frame)
        save_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(save_path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 设置默认保存路径为当前目录下的sweep_recordings文件夹
        default_save_path = os.path.join(os.getcwd(), "sweep_recordings")
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path, exist_ok=True)
        
        self.sweep_save_path_var = tk.StringVar(value=default_save_path)
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.sweep_save_path_var, font=("Arial", 9))
        save_path_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览", 
                                      command=self.browse_sweep_save_path, width=5, style="Small.TButton")
        browse_save_button.pack(side="right", padx=2)
        
        # 操作按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)
        
        self.start_sweep_button = ttk.Button(button_frame, text="开始扫频测试", 
                                          command=self.start_sweep_test, width=15, style="TButton")
        self.start_sweep_button.pack(side="left", padx=5)
        
        self.stop_sweep_button = ttk.Button(button_frame, text="停止测试", 
                                         command=self.stop_sweep_test, width=15, style="TButton", state="disabled")
        self.stop_sweep_button.pack(side="left", padx=5)
        
        self.open_sweep_folder_button = ttk.Button(button_frame, text="打开文件夹", 
                                                command=self.open_sweep_folder, width=15, style="TButton")
        self.open_sweep_folder_button.pack(side="right", padx=5)
        
        # 下部 - 信息区域
        info_frame = ttk.LabelFrame(bottom_frame, text="测试信息", padding=5)
        info_frame.pack(fill="both", expand=True)
        
        # 信息文本框
        self.sweep_info_text = tk.Text(info_frame, height=10, font=("Arial", 9), wrap="word")
        self.sweep_info_text.pack(fill="both", expand=True, pady=2)
        self.sweep_info_text.insert("1.0", "扫频测试信息将显示在这里...\n")
        self.sweep_info_text.config(state="disabled")
        
        # 底部状态显示
        self.sweep_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.sweep_status_var, font=("Arial", 9))
        status_label.pack(pady=2)
        
        # 初始化扫频文件列表
        self.update_sweep_file_options()
    
    def setup_hal_recording_tab(self, parent):
        """设置 HAL 录音选项卡"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 创建左右两栏布局
        left_frame = ttk.Frame(frame, width=300)
        left_frame.pack(side="left", fill="y", padx=(0, 5))
        left_frame.pack_propagate(False)  # 防止被内容压缩
        
        right_frame = ttk.Frame(frame)
        right_frame.pack(side="left", fill="both", expand=True)
        
        # 左侧 - 属性管理区域
        prop_frame = ttk.LabelFrame(left_frame, text="录音属性管理", padding=5)
        prop_frame.pack(fill="both", expand=True, pady=5)
        
        # 添加属性区域
        add_prop_frame = ttk.Frame(prop_frame)
        add_prop_frame.pack(fill="x", pady=2)
        
        ttk.Label(add_prop_frame, text="属性:", font=("Arial", 9)).pack(side="left", padx=2)
        self.hal_prop_var = tk.StringVar()
        prop_entry = ttk.Entry(add_prop_frame, textvariable=self.hal_prop_var, font=("Arial", 9))
        prop_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        add_button = ttk.Button(add_prop_frame, text="添加", 
                              command=self.add_hal_prop, width=5, style="Small.TButton")
        add_button.pack(side="right", padx=2)
        
        # 属性列表区域 - 添加滚动条
        props_frame = ttk.Frame(prop_frame)
        props_frame.pack(fill="both", expand=True, pady=5)
        
        # 添加滚动条
        props_scrollbar = ttk.Scrollbar(props_frame)
        props_scrollbar.pack(side="right", fill="y")
        
        # 创建Canvas用于滚动
        props_canvas = tk.Canvas(props_frame, yscrollcommand=props_scrollbar.set, height=120)
        props_canvas.pack(side="left", fill="both", expand=True)
        props_scrollbar.config(command=props_canvas.yview)
        
        # 创建属性列表容器
        self.props_container = ttk.Frame(props_canvas)
        props_canvas.create_window((0, 0), window=self.props_container, anchor="nw")
        
        # 配置Canvas滚动区域
        self.props_container.bind("<Configure>", lambda e: props_canvas.configure(scrollregion=props_canvas.bbox("all")))
        
        # 添加默认属性
        self.hal_props = {}  # 存储属性和对应的变量
        default_props = [
            "vendor.media.audiohal.vpp.dump",
            "vendor.media.audiohal.indump",
            "vendor.media.audiohal.outdump"
        ]
        
        for prop in default_props:
            self.add_prop_to_ui(prop)
        
        # 左侧 - 录音目录设置
        dir_frame = ttk.LabelFrame(left_frame, text="录音目录设置", padding=5)
        dir_frame.pack(fill="x", pady=5)
        
        # 录音目录输入
        dir_path_frame = ttk.Frame(dir_frame)
        dir_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(dir_path_frame, text="目录:", font=("Arial", 9)).pack(side="left", padx=2)
        self.hal_dir_var = tk.StringVar(value="data/vendor/audiohal")  # 设置默认值
        dir_entry = ttk.Entry(dir_path_frame, textvariable=self.hal_dir_var, font=("Arial", 9))
        dir_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        # 目录操作按钮
        dir_button_frame = ttk.Frame(dir_frame)
        dir_button_frame.pack(fill="x", pady=2)
        
        create_dir_button = ttk.Button(dir_button_frame, text="创建目录", 
                                      command=self.create_hal_dir, width=8, style="Small.TButton")
        create_dir_button.pack(side="left", padx=2, pady=2)
        
        check_dir_button = ttk.Button(dir_button_frame, text="检查目录", 
                                     command=self.check_hal_dir, width=8, style="Small.TButton")
        check_dir_button.pack(side="left", padx=2, pady=2)
        
        # 右侧 - 上部控制区域
        control_frame = ttk.LabelFrame(right_frame, text="录音控制", padding=5)
        control_frame.pack(fill="x", pady=5)
        
        # 录音时长设置
        duration_frame = ttk.Frame(control_frame)
        duration_frame.pack(fill="x", pady=2)
        
        ttk.Label(duration_frame, text="自动停止(秒):", font=("Arial", 9)).pack(side="left", padx=2)
        self.hal_duration_var = tk.StringVar(value="0")
        ttk.Entry(duration_frame, textvariable=self.hal_duration_var, width=5, font=("Arial", 9)).pack(side="left", padx=2)
        ttk.Label(duration_frame, text="(0表示不自动停止)", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 保存路径设置
        save_path_frame = ttk.Frame(control_frame)
        save_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(save_path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 设置默认保存路径为当前目录下的hal_dump文件夹
        default_save_path = os.path.join(os.getcwd(), "hal_dump")
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path, exist_ok=True)
        
        self.hal_save_path_var = tk.StringVar(value=default_save_path)
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.hal_save_path_var, font=("Arial", 9))
        save_path_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览", 
                                      command=self.browse_hal_save_path, width=5, style="Small.TButton")
        browse_save_button.pack(side="right", padx=2)
        
        # 控制按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=2)
        
        self.start_hal_button = ttk.Button(button_frame, text="开始录音", 
                                         command=self.start_hal_recording, width=10, style="Small.TButton")
        self.start_hal_button.pack(side="left", padx=5)
        
        self.stop_hal_button = ttk.Button(button_frame, text="停止录音", 
                                        command=self.stop_hal_recording, width=10, state="disabled", style="Small.TButton")
        self.stop_hal_button.pack(side="left", padx=5)
        
        # 录音状态
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill="x", pady=2)
        
        ttk.Label(status_frame, text="状态:", font=("Arial", 9)).pack(side="left", padx=2)
        self.hal_recording_status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.hal_recording_status_var, font=("Arial", 9)).pack(side="left", padx=2)
        
        # 开始时间
        time_frame = ttk.Frame(control_frame)
        time_frame.pack(fill="x", pady=2)
        
        ttk.Label(time_frame, text="开始时间:", font=("Arial", 9)).pack(side="left", padx=2)
        self.hal_start_time_var = tk.StringVar(value="-")
        ttk.Label(time_frame, textvariable=self.hal_start_time_var, font=("Arial", 9)).pack(side="left", padx=2)
        
        # 右侧 - 下部信息区域
        info_frame = ttk.LabelFrame(right_frame, text="录音信息", padding=5)
        info_frame.pack(fill="both", expand=True, pady=5)
        
        # 信息文本框
        self.hal_info_text = tk.Text(info_frame, height=10, font=("Arial", 9), wrap="word")
        self.hal_info_text.pack(fill="both", expand=True, pady=2)
        self.hal_info_text.insert("1.0", "录音信息将显示在这里...\n")
        self.hal_info_text.config(state="disabled")
        
        # 底部状态显示
        self.hal_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.hal_status_var, font=("Arial", 9))
        status_label.pack(pady=2)
    
    def setup_custom_hal_tab(self, parent):
        """设置自定义 HAL 录音选项卡"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="自定义 HAL 录音功能\n可以设置多个录音属性和目录")
        desc.pack(pady=5)
        
        # 创建左右分栏
        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, pady=5)
        
        # 左侧 - 属性设置区域
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        # 属性管理区域
        prop_frame = ttk.LabelFrame(left_frame, text="录音属性管理")
        prop_frame.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 添加属性区域
        add_prop_frame = ttk.Frame(prop_frame)
        add_prop_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(add_prop_frame, text="属性名称:").pack(side="left", padx=5)
        self.custom_prop_var = tk.StringVar()
        prop_entry = ttk.Entry(add_prop_frame, textvariable=self.custom_prop_var, width=25)
        prop_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        add_button = ttk.Button(add_prop_frame, text="添加", 
                              command=self.add_custom_prop, width=8)
        add_button.pack(side="left", padx=5)
        
        # 属性列表区域
        prop_list_frame = ttk.Frame(prop_frame)
        prop_list_frame.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 添加滚动条
        prop_scrollbar = ttk.Scrollbar(prop_list_frame)
        prop_scrollbar.pack(side="right", fill="y")
        
        # 属性列表框
        self.custom_props_listbox = tk.Listbox(prop_list_frame, selectmode="multiple", 
                                             yscrollcommand=prop_scrollbar.set, height=6)
        self.custom_props_listbox.pack(side="left", fill="both", expand=True)
        prop_scrollbar.config(command=self.custom_props_listbox.yview)
        
        # 添加默认属性
        default_props = [
            "vendor.media.audiohal.vpp.dump",
            "vendor.media.audiohal.indump",
            "vendor.media.audiohal.outdump"
        ]
        
        for prop in default_props:
            self.custom_props_listbox.insert(tk.END, prop)
        
        # 属性操作按钮
        prop_button_frame = ttk.Frame(prop_frame)
        prop_button_frame.pack(fill="x", pady=5)
        
        remove_button = ttk.Button(prop_button_frame, text="删除选中", 
                                 command=self.remove_custom_prop, width=10)
        remove_button.pack(side="left", padx=5, pady=5)
        
        clear_button = ttk.Button(prop_button_frame, text="清空列表", 
                                command=self.clear_custom_props, width=10)
        clear_button.pack(side="left", padx=5, pady=5)
        
        reset_button = ttk.Button(prop_button_frame, text="重置默认", 
                                command=self.reset_custom_props, width=10)
        reset_button.pack(side="left", padx=5, pady=5)
        
        # 目录设置区域
        dir_frame = ttk.LabelFrame(left_frame, text="录音目录设置")
        dir_frame.pack(fill="x", pady=5, padx=5)
        
        dir_path_frame = ttk.Frame(dir_frame)
        dir_path_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(dir_path_frame, text="录音目录:").pack(side="left", padx=5)
        self.custom_dir_var = tk.StringVar(value="data/vendor/audiohal")
        dir_entry = ttk.Entry(dir_path_frame, textvariable=self.custom_dir_var, width=25)
        dir_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # 目录操作按钮
        dir_button_frame = ttk.Frame(dir_frame)
        dir_button_frame.pack(fill="x", pady=5)
        
        create_dir_button = ttk.Button(dir_button_frame, text="创建目录", 
                                     command=self.create_custom_dir, width=10)
        create_dir_button.pack(side="left", padx=5, pady=5)
        
        check_dir_button = ttk.Button(dir_button_frame, text="检查目录", 
                                    command=self.check_custom_dir, width=10)
        check_dir_button.pack(side="left", padx=5, pady=5)
        
        # 右侧 - 控制和文件区域
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        
        # 录音控制区域
        control_frame = ttk.LabelFrame(right_frame, text="录音控制")
        control_frame.pack(fill="x", pady=5, padx=5)
        
        # 录音时长设置
        duration_frame = ttk.Frame(control_frame)
        duration_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(duration_frame, text="自动停止(秒):").pack(side="left", padx=5)
        self.custom_duration_var = tk.StringVar(value="0")
        ttk.Entry(duration_frame, textvariable=self.custom_duration_var, width=5).pack(side="left", padx=5)
        ttk.Label(duration_frame, text="(0表示不自动停止)").pack(side="left", padx=5)
        
        # 控制按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=10)
        
        self.start_custom_button = ttk.Button(button_frame, text="开始录音", 
                                            command=self.start_custom_recording, width=15)
        self.start_custom_button.pack(side="left", padx=10, expand=True)
        
        self.stop_custom_button = ttk.Button(button_frame, text="停止录音", 
                                           command=self.stop_custom_recording, width=15, state="disabled")
        self.stop_custom_button.pack(side="left", padx=10, expand=True)
        
        # 录音状态
        self.custom_recording_status_frame = ttk.Frame(control_frame)
        self.custom_recording_status_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(self.custom_recording_status_frame, text="状态:").pack(side="left", padx=5)
        self.custom_recording_status_var = tk.StringVar(value="就绪")
        ttk.Label(self.custom_recording_status_frame, textvariable=self.custom_recording_status_var).pack(side="left", padx=5)
        
        # 开始时间
        self.custom_start_time_frame = ttk.Frame(control_frame)
        self.custom_start_time_frame.pack(fill="x", pady=2, padx=5)
        
        ttk.Label(self.custom_start_time_frame, text="开始时间:").pack(side="left", padx=5)
        self.custom_start_time_var = tk.StringVar(value="-")
        ttk.Label(self.custom_start_time_frame, textvariable=self.custom_start_time_var).pack(side="left", padx=5)
        
        # 文件管理区域
        files_frame = ttk.LabelFrame(right_frame, text="文件管理")
        files_frame.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 本地保存路径
        save_path_frame = ttk.Frame(files_frame)
        save_path_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(save_path_frame, text="本地保存路径:").pack(side="left", padx=5)
        self.custom_save_path_var = tk.StringVar(value="test/hal_recordings")
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.custom_save_path_var, width=20)
        save_path_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览...", 
                                      command=self.browse_custom_save_path, width=8)
        browse_save_button.pack(side="left", padx=5)
        
        # 文件列表
        file_list_frame = ttk.Frame(files_frame)
        file_list_frame.pack(fill="both", expand=True, pady=5, padx=5)
        
        # 添加滚动条
        file_scrollbar = ttk.Scrollbar(file_list_frame)
        file_scrollbar.pack(side="right", fill="y")
        
        # 文件列表框
        self.custom_files_listbox = tk.Listbox(file_list_frame, selectmode="extended", 
                                             yscrollcommand=file_scrollbar.set, height=8)
        self.custom_files_listbox.pack(side="left", fill="both", expand=True)
        file_scrollbar.config(command=self.custom_files_listbox.yview)
        
        # 文件操作按钮
        file_button_frame = ttk.Frame(files_frame)
        file_button_frame.pack(fill="x", pady=5)
        
        refresh_files_button = ttk.Button(file_button_frame, text="刷新文件列表", 
                                        command=self.refresh_custom_files, width=12)
        refresh_files_button.pack(side="left", padx=5, pady=5)
        
        pull_files_button = ttk.Button(file_button_frame, text="拉取选中文件", 
                                     command=self.pull_custom_files, width=12)
        pull_files_button.pack(side="left", padx=5, pady=5)
        
        delete_files_button = ttk.Button(file_button_frame, text="删除选中文件", 
                                       command=self.delete_custom_files, width=12)
        delete_files_button.pack(side="left", padx=5, pady=5)
        
        # 状态显示
        self.custom_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.custom_status_var)
        status_label.pack(pady=5)
        
        # 初始刷新文件列表
        self.refresh_custom_files()

    def setup_screenshot_tab(self, parent):
        """设置截图功能选项卡"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 创建上下两栏布局
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", pady=5)
        
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill="both", expand=True, pady=5)
        
        # 上部 - 控制区域
        control_frame = ttk.LabelFrame(top_frame, text="截图控制", padding=5)
        control_frame.pack(fill="x", expand=True)
        
        # 保存路径设置
        save_path_frame = ttk.Frame(control_frame)
        save_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(save_path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 设置默认保存路径为当前目录下的screenshots文件夹
        default_save_path = os.path.join(os.getcwd(), "screenshots")
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path, exist_ok=True)
        
        self.screenshot_save_path_var = tk.StringVar(value=default_save_path)
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.screenshot_save_path_var, font=("Arial", 9))
        save_path_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览", 
                                      command=self.browse_screenshot_save_path, width=5, style="Small.TButton")
        browse_save_button.pack(side="right", padx=2)
        
        # 截图按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)
        
        self.screenshot_button = ttk.Button(button_frame, text="截取屏幕", 
                                     command=self.take_screenshot, width=15, style="TButton")
        self.screenshot_button.pack(side="left", padx=5)
        
        self.open_folder_button = ttk.Button(button_frame, text="打开文件夹", 
                                      command=self.open_screenshot_folder, width=15, style="TButton")
        self.open_folder_button.pack(side="right", padx=5)
        
        # 下部 - 信息区域
        info_frame = ttk.LabelFrame(bottom_frame, text="截图信息", padding=5)
        info_frame.pack(fill="both", expand=True)
        
        # 信息文本框
        self.screenshot_info_text = tk.Text(info_frame, height=10, font=("Arial", 9), wrap="word")
        self.screenshot_info_text.pack(fill="both", expand=True, pady=2)
        self.screenshot_info_text.insert("1.0", "截图信息将显示在这里...\n")
        self.screenshot_info_text.config(state="disabled")
        
        # 底部状态显示
        self.screenshot_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.screenshot_status_var, font=("Arial", 9))
        status_label.pack(pady=2)
    
    def setup_screenrecord_tab(self, parent):
        """设置屏幕录制选项卡"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 创建上下两栏布局
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", pady=5)
        
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill="both", expand=True, pady=5)
        
        # 上部 - 控制区域
        control_frame = ttk.LabelFrame(top_frame, text="录制控制", padding=5)
        control_frame.pack(fill="x", expand=True)
        
        # 保存路径设置
        save_path_frame = ttk.Frame(control_frame)
        save_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(save_path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 设置默认保存路径为当前目录下的screenrecords文件夹
        default_save_path = os.path.join(os.getcwd(), "screenrecords")
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path, exist_ok=True)
        
        self.screenrecord_save_path_var = tk.StringVar(value=default_save_path)
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.screenrecord_save_path_var, font=("Arial", 9))
        save_path_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览", 
                                      command=self.browse_screenrecord_save_path, width=5, style="Small.TButton")
        browse_save_button.pack(side="right", padx=2)
        
        # 录制方式选择
        method_frame = ttk.Frame(control_frame)
        method_frame.pack(fill="x", pady=2)
        
        ttk.Label(method_frame, text="录制方式:", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.screenrecord_method_var = tk.StringVar(value="adb")
        ttk.Radiobutton(method_frame, text="ADB命令", variable=self.screenrecord_method_var, 
                      value="adb", style="Small.TCheckbutton").pack(side="left", padx=10)
        ttk.Radiobutton(method_frame, text="系统录屏", variable=self.screenrecord_method_var, 
                      value="system", style="Small.TCheckbutton").pack(side="left", padx=10)
        
        # 录制按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)
        
        self.start_record_button = ttk.Button(button_frame, text="开始录制", 
                                           command=self.start_screenrecord, width=15, style="TButton")
        self.start_record_button.pack(side="left", padx=5)
        
        self.stop_record_button = ttk.Button(button_frame, text="停止录制", 
                                          command=self.stop_screenrecord, width=15, style="TButton", state="disabled")
        self.stop_record_button.pack(side="left", padx=5)
        
        self.open_record_folder_button = ttk.Button(button_frame, text="打开文件夹", 
                                                 command=self.open_screenrecord_folder, width=15, style="TButton")
        self.open_record_folder_button.pack(side="right", padx=5)
        
        # 提示信息
        tip_frame = ttk.Frame(control_frame)
        tip_frame.pack(fill="x", pady=2)
        
        tip_text = "提示: 如果ADB录制方式不工作，请尝试系统录屏方式。系统录屏需要在设备上手动确认。"
        ttk.Label(tip_frame, text=tip_text, font=("Arial", 9), foreground="blue").pack(pady=2)
        
        # 下部 - 信息区域
        info_frame = ttk.LabelFrame(bottom_frame, text="录制信息", padding=5)
        info_frame.pack(fill="both", expand=True)
        
        # 信息文本框
        self.screenrecord_info_text = tk.Text(info_frame, height=10, font=("Arial", 9), wrap="word")
        self.screenrecord_info_text.pack(fill="both", expand=True, pady=2)
        self.screenrecord_info_text.insert("1.0", "录制信息将显示在这里...\n")
        self.screenrecord_info_text.config(state="disabled")
        
        # 录制状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=2)
        
        ttk.Label(status_frame, text="状态:", font=("Arial", 9)).pack(side="left", padx=2)
        self.screenrecord_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(status_frame, textvariable=self.screenrecord_status_var, font=("Arial", 9))
        status_label.pack(side="left", padx=2)
        
        # 录制时间显示
        self.screenrecord_time_var = tk.StringVar(value="00:00")
        time_label = ttk.Label(status_frame, textvariable=self.screenrecord_time_var, font=("Arial", 9))
        time_label.pack(side="right", padx=2)
        ttk.Label(status_frame, text="录制时间:", font=("Arial", 9)).pack(side="right", padx=2)
    
    def run_mic_test(self):
        """运行麦克风测试"""
        if not self.check_device_selected():
            return
            
        mic_count = self.mic_var.get()
        pcm_device = self.mic_pcm_var.get()
        device_id = self.mic_device_var.get()
        rate = self.mic_rate_var.get()
        
        self.status_var.set(f"正在执行{mic_count}mic测试...")
        
        # 禁用开始按钮，启用停止按钮
        self.start_mic_button.config(state="disabled")
        self.stop_mic_button.config(state="normal")
        
        # 在新线程中运行测试，避免GUI冻结
        self.mic_thread = threading.Thread(target=self._mic_test_thread, 
                                         args=(mic_count, pcm_device, device_id, rate), 
                                         daemon=True)
        self.mic_thread.start()
    
    def _mic_test_thread(self, mic_count, pcm_device, device_id, rate):
        try:
            # 准备工作
            subprocess.run(self.get_adb_command("root"), shell=True)
            
            # 开始录制
            self.mic_filename = f"test_{mic_count}mic.wav"
            record_cmd = self.get_adb_command(f"shell tinycap /sdcard/{self.mic_filename} -D {pcm_device} -d {device_id} -c {mic_count} -r {rate}")
            
            # 显示完整命令以便调试
            print(f"执行命令: {record_cmd}")
            self.root.after(0, lambda: self.status_var.set(f"执行命令: {record_cmd}"))
            
            # 启动录制进程
            self.mic_process = subprocess.Popen(record_cmd, shell=True)
            
            # 更新状态
            self.root.after(0, lambda: self.status_var.set(f"正在录制{mic_count}mic音频，请对着麦克风说话..."))
            self.root.after(0, lambda: self.mic_status_var.set("录制中..."))
            
            # 等待进程结束（由stop_mic_recording方法终止）
            self.mic_process.wait()
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            self.root.after(0, lambda: self.mic_status_var.set("录制出错"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
            
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_mic_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_mic_button.config(state="disabled"))
    
    def stop_mic_recording(self):
        """停止麦克风录音"""
        if not hasattr(self, 'mic_process') or self.mic_process is None:
            return
            
        try:
            # 停止录制进程
            subprocess.run(self.get_adb_command("shell pkill -f tinycap"), shell=True)
            self.mic_process.terminate()
            
            # 更新状态
            self.status_var.set("录制已停止，准备保存...")
            self.mic_status_var.set("录制已停止")
            
            # 恢复按钮状态
            self.start_mic_button.config(state="normal")
            self.stop_mic_button.config(state="disabled")
            
            # 提示用户选择保存位置
            save_path = filedialog.asksaveasfilename(
                initialdir="test",
                title="保存麦克风录音",
                initialfile=self.mic_filename,
                defaultextension=".wav",
                filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")]
            )
            
            if save_path:
                # 从设备拉取文件到用户选择的位置
                self.status_var.set("正在保存录音文件...")
                pull_cmd = self.get_adb_command(f"pull /sdcard/{self.mic_filename} \"{save_path}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"保存文件失败: {result.stderr}")
                
                self.status_var.set(f"麦克风测试完成，文件已保存")
                self.mic_status_var.set("录音已保存")
            else:
                self.status_var.set("麦克风测试已完成，但未保存录音")
                self.mic_status_var.set("录音未保存")
            
        except Exception as e:
            self.status_var.set(f"停止录音出错: {str(e)}")
            self.mic_status_var.set("停止录音失败")
            messagebox.showerror("错误", f"停止麦克风录音时出错:\n{str(e)}")
    
    def run_multichannel_test(self):
        """运行多声道测试"""
        if not self.check_device_selected():
            return
            
        rate = self.multi_rate_var.get()
        bit = self.multi_bit_var.get()
        
        self.status_var.set("正在执行多声道测试...")
        
        # 在新线程中运行测试，避免GUI冻结
        threading.Thread(target=self._multichannel_test_thread, 
                        args=(rate, bit), 
                        daemon=True).start()
    
    def _multichannel_test_thread(self, rate, bit):
        try:
            # 准备工作
            subprocess.run(self.get_adb_command("root"), shell=True)
            subprocess.run(self.get_adb_command("push audio/Nums_7dot1_16_48000.wav /sdcard/"), shell=True)
            
            # 重启audioserver
            for _ in range(3):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
            
            # 播放音频
            self.root.after(0, lambda: self.status_var.set("正在播放多声道音频..."))
            play_cmd = self.get_adb_command(f"shell tinyplay /sdcard/Nums_7dot1_16_48000.wav -r {rate} -b {bit}")
            
            # 显示命令以便调试
            print(f"执行命令: {play_cmd}")
            
            # 执行播放命令
            subprocess.run(play_cmd, shell=True)
            
            self.root.after(0, lambda: self.status_var.set("多声道测试完成"))
            messagebox.showinfo("测试完成", "多声道测试完成")
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
    
    def stop_multichannel_test(self):
        """停止多声道测试"""
        if not self.check_device_selected():
            return
            
        try:
            # 更新状态
            self.status_var.set("正在停止多声道测试...")
            
            # 停止HPlayer
            cmd = self.get_adb_command("shell am force-stop com.android.hplayer")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"停止测试失败: {result.stderr}")
                
            # 更新状态
            self.status_var.set("多声道测试已停止")
            self.multichannel_status_var.set("测试已停止")
            
        except Exception as e:
            self.multichannel_status_var.set(f"停止测试失败: {str(e)}")
            messagebox.showerror("错误", f"停止多声道测试时出错:\n{str(e)}")

    def browse_local_audio_file(self):
        """浏览并选择本地音频文件"""
        filetypes = [
            ("所有支持的格式", "*.wav;*.mp3;*.ogg;*.flac;*.mp4;*.avi;*.mkv"),
            ("WAV文件", "*.wav"),
            ("MP3文件", "*.mp3"),
            ("视频文件", "*.mp4;*.avi;*.mkv"),
            ("所有文件", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="选择音频/视频文件",
            filetypes=filetypes
        )
        
        if filename:
            self.local_audio_file = filename
            # 显示文件名而不是完整路径
            display_name = os.path.basename(filename)
            if len(display_name) > 40:
                display_name = display_name[:37] + "..."
            self.local_file_path_var.set(display_name)
            self.status_var.set(f"已选择文件: {display_name}")
            print(f"已选择文件: {filename}")  # 添加调试输出

    def play_local_audio(self):
        """播放本地音频文件"""
        if not self.local_audio_file:
            messagebox.showerror("错误", "请先选择音频/视频文件")
            return
        
        if not os.path.exists(self.local_audio_file):
            messagebox.showerror("错误", "所选文件不存在")
            return
        
        # 获取播放方式
        playback_mode = self.playback_mode_var.get()
        
        # 如果选择设备播放，检查设备是否已选择
        if playback_mode == "device" and not self.check_device_selected():
            return
        
        try:
            # 停止当前播放
            self.stop_local_audio()
            
            # 获取文件类型
            _, ext = os.path.splitext(self.local_audio_file)
            ext = ext.lower()
            
            # 记录调试信息
            self.debug_info = f"文件: {self.local_audio_file}\n类型: {ext}\n播放方式: {playback_mode}"
            print(self.debug_info)  # 添加调试输出
            
            # 通过Android设备播放
            if playback_mode == "device":
                self.playback_status_var.set("正在准备通过Android设备播放...")
                
                # 创建专用目录
                subprocess.run(self.get_adb_command("shell mkdir -p /sdcard/HPlayerFiles"), shell=True)
                
                # 推送文件到设备的专用目录
                self.status_var.set("正在推送文件到Android设备...")
                file_basename = os.path.basename(self.local_audio_file)
                remote_path = f"/sdcard/HPlayerFiles/{file_basename}"
                push_cmd = self.get_adb_command(f"push \"{self.local_audio_file}\" \"{remote_path}\"")
                
                # 执行推送命令
                result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
                if "error" in result.stderr.lower():
                    raise Exception(f"推送文件失败: {result.stderr}")
                
                # 确保媒体库更新
                self.status_var.set("正在更新媒体库...")
                scan_cmd = self.get_adb_command(f"shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_path}")
                subprocess.run(scan_cmd, shell=True)
                
                # 等待媒体扫描完成
                time.sleep(2)
                
                # 尝试直接播放文件
                self.status_var.set("正在尝试播放文件...")
                
                if ext in ['.mp3', '.wav', '.ogg', '.flac']:
                    # 音频文件
                    play_cmd = self.get_adb_command(f"shell am start -a android.intent.action.VIEW -d file://{remote_path} -t audio/*")
                    subprocess.run(play_cmd, shell=True)
                elif ext in ['.mp4', '.avi', '.mkv', '.mov']:
                    # 视频文件
                    play_cmd = self.get_adb_command(f"shell am start -a android.intent.action.VIEW -d file://{remote_path} -t video/*")
                    subprocess.run(play_cmd, shell=True)
                else:
                    # 其他文件，尝试通用方式打开
                    play_cmd = self.get_adb_command(f"shell am start -a android.intent.action.VIEW -d file://{remote_path}")
                    subprocess.run(play_cmd, shell=True)
                
                self.playback_status_var.set(f"已在设备上播放: {file_basename}")
                self.status_var.set("文件正在设备上播放")
            
            # 在本地电脑播放
            else:
                # 根据文件类型选择播放方式
                if ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv']:
                    # 视频文件使用系统默认播放器
                    self.playback_status_var.set("使用系统播放器播放视频文件...")
                    os.startfile(self.local_audio_file)
                    self.status_var.set(f"已启动系统播放器播放: {os.path.basename(self.local_audio_file)}")
                    return
                
                # 音频文件使用pygame播放
                try:
                    # 设置音量
                    pygame.mixer.music.set_volume(self.volume_var.get())
                    
                    # 加载并播放音频
                    pygame.mixer.music.load(self.local_audio_file)
                    pygame.mixer.music.play()
                    
                    self.playback_status_var.set("正在本地播放...")
                    self.status_var.set(f"正在播放: {os.path.basename(self.local_audio_file)}")
                    
                    # 启动线程监控播放状态
                    threading.Thread(target=self._monitor_playback, daemon=True).start()
                    
                except Exception as e:
                    # pygame播放失败，尝试使用系统默认播放器
                    self.debug_info += f"\nPygame错误: {str(e)}"
                    self.playback_status_var.set("使用系统播放器播放...")
                    os.startfile(self.local_audio_file)
                    self.status_var.set(f"已启动系统播放器播放: {os.path.basename(self.local_audio_file)}")
            
        except Exception as e:
            self.debug_info += f"\n错误: {str(e)}"
            self.playback_status_var.set("播放出错")
            messagebox.showerror("错误", f"播放音频时出错:\n{str(e)}")
    
    def pause_local_audio(self):
        """暂停本地音频播放"""
        try:
            pygame.mixer.music.pause()
            
            # 更新按钮状态
            self.play_button.config(state="normal")
            self.pause_button.config(state="disabled")
            
            # 更新状态
            self.status_var.set("本地音频已暂停")
            self.local_playback_status_var.set("播放已暂停")
            
        except Exception as e:
            self.local_playback_status_var.set(f"暂停失败: {str(e)}")
            messagebox.showerror("错误", f"暂停音频时出错:\n{str(e)}")
    
    def stop_local_audio(self):
        """停止播放本地音频"""
        playback_mode = self.playback_mode_var.get()
        
        try:
            # 停止Android设备上的播放
            if playback_mode == "device" and self.selected_device:
                # 尝试停止媒体播放
                subprocess.run(self.get_adb_command("shell input keyevent KEYCODE_MEDIA_STOP"), shell=True)
                # 或者尝试按返回键退出播放器
                subprocess.run(self.get_adb_command("shell input keyevent KEYCODE_BACK"), shell=True)
                
                self.playback_status_var.set("已尝试停止Android设备上的播放")
                self.status_var.set("就绪")
            
            # 停止本地播放
            else:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    self.playback_status_var.set("已停止")
                    self.status_var.set("就绪")
        except Exception:
            # 忽略停止过程中的错误
            pass
    
    def update_volume(self, *args):
        """更新音频播放音量"""
        try:
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.set_volume(self.volume_var.get())
        except Exception:
            # 忽略音量调整过程中的错误
            pass
    
    def update_playback_progress(self):
        """更新播放进度"""
        if pygame.mixer.music.get_busy():
            # 获取音频长度（这需要额外的库支持，如mutagen）
            # 这里简化处理，假设进度线性增长
            current_pos = pygame.mixer.music.get_pos() / 1000  # 转换为秒
            
            # 更新进度条
            # 假设音频长度为3分钟
            total_length = 180
            progress = min(current_pos / total_length, 1.0)
            self.progress_var.set(progress * 100)
            
            # 更新时间显示
            mins, secs = divmod(int(current_pos), 60)
            total_mins, total_secs = divmod(total_length, 60)
            self.time_var.set(f"{mins:02d}:{secs:02d} / {total_mins:02d}:{total_secs:02d}")
            
            # 继续更新
            self.root.after(1000, self.update_playback_progress)
        else:
            # 播放结束，重置UI
            self.play_button.config(state="normal")
            self.pause_button.config(state="disabled")
            self.stop_button.config(state="disabled")
            self.progress_var.set(0)
            self.time_var.set("00:00 / 00:00")
            self.local_playback_status_var.set("播放完成")

    def update_mic_countdown(self, remaining):
        """更新麦克风录音倒计时"""
        if remaining > 0:
            # 更新倒计时显示
            self.countdown_var.set(f"{remaining}")
            # 继续倒计时
            self.root.after(1000, lambda: self.update_mic_countdown(remaining - 1))
        else:
            # 倒计时结束
            self.countdown_var.set("")
            # 如果设置了录音时长，自动停止录音
            if int(self.duration_var.get()) > 0:
                self.stop_mic_recording()

    def browse_audio_file(self):
        """浏览并选择音频文件"""
        file_path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[
                ("音频文件", "*.wav;*.mp3;*.flac;*.ogg;*.aac"),
                ("WAV文件", "*.wav"),
                ("MP3文件", "*.mp3"),
                ("所有文件", "*.*")
            ]
        )
        
        if file_path:
            # 获取文件扩展名
            _, ext = os.path.splitext(file_path)
            self.file_extension = ext.lower()
            
            # 更新选中的文件
            self.selected_audio_file = file_path
            
            # 更新状态
            self.status_var.set(f"已选择音频文件: {os.path.basename(file_path)}")
            
            # 根据当前选项卡更新相应的变量
            current_tab = self.tab_control.tab(self.tab_control.select(), "text")
            
            if current_tab == "Loopback和Ref测试":
                # 更新Loopback测试的文件路径显示
                self.file_path_var.set(os.path.basename(file_path))
                # 确保选择了自定义音频选项
                self.audio_source_var.set("custom")
            elif current_tab == "本地播放":
                # 更新本地播放的文件路径
                self.local_file_path_var.set(os.path.basename(file_path))
                self.local_audio_file = file_path

    def run_loopback_test(self):
        """运行Loopback或Ref通道测试"""
        if not self.check_device_selected():
            return
            
        device = self.loopback_device_var.get()
        channels = self.loopback_channel_var.get()
        rate = self.loopback_rate_var.get()
        audio_source = self.audio_source_var.get()
        
        # 检查自定义音频文件
        if audio_source == "custom" and not self.selected_audio_file:
            messagebox.showerror("错误", "请先选择自定义音频文件")
            return
        
        self.status_var.set("正在执行通道测试...")
        
        # 禁用开始按钮，启用停止按钮
        self.start_loopback_button.config(state="disabled")
        self.stop_loopback_button.config(state="normal")
        
        # 在新线程中运行测试，避免GUI冻结
        self.loopback_thread = threading.Thread(target=self._loopback_test_thread, 
                                          args=(device, channels, rate, audio_source), 
                                          daemon=True)
        self.loopback_thread.start()
    
    def _loopback_test_thread(self, device, channels, rate, audio_source):
        try:
            # 准备工作
            subprocess.run(self.get_adb_command("root"), shell=True)
            
            # 根据选择的音频源处理
            if audio_source == "default":
                # 使用默认7.1声道测试音频
                audio_file = "audio/Nums_7dot1_16_48000.wav"
                if not os.path.exists(audio_file):
                    raise FileNotFoundError(f"默认测试音频文件不存在: {audio_file}")
                
                subprocess.run(self.get_adb_command(f"push {audio_file} /sdcard/test_audio.wav"), shell=True)
                remote_audio_file = "/sdcard/test_audio.wav"
            else:
                # 使用自定义音频文件
                # 获取文件扩展名
                _, ext = os.path.splitext(self.selected_audio_file)
                remote_filename = f"test_audio{ext}"
                
                self.root.after(0, lambda: self.status_var.set("正在推送自定义音频文件到设备..."))
                subprocess.run(self.get_adb_command(f"push \"{self.selected_audio_file}\" /sdcard/{remote_filename}"), shell=True)
                remote_audio_file = f"/sdcard/{remote_filename}"
            
            # 重启audioserver
            for _ in range(3):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
            
            # 开始录制 - 使用正确的参数格式
            self.loopback_filename = f"test_{channels}ch.wav"
            record_cmd = self.get_adb_command(f"shell tinycap /sdcard/{self.loopback_filename} -d {device} -c {channels} -r {rate} -p 480")
            self.loopback_process = subprocess.Popen(record_cmd, shell=True)
            
            # 更新状态
            self.root.after(0, lambda: self.status_var.set("正在录制通道音频..."))
            self.root.after(0, lambda: self.loopback_status_var.set("录制中..."))
            
            # 等待录制启动
            time.sleep(2)
            
            # 播放音频
            self.root.after(0, lambda: self.status_var.set("正在播放音频..."))
            
            # 根据文件类型选择播放方式
            if remote_audio_file.endswith('.wav'):
                # 使用tinyplay播放WAV文件
                play_cmd = self.get_adb_command(f"shell tinyplay {remote_audio_file} -d 0")
                subprocess.run(play_cmd, shell=True)
            else:
                # 对于其他格式，尝试使用系统媒体播放器
                play_cmd = self.get_adb_command(f"shell am start -a android.intent.action.VIEW -d file://{remote_audio_file} -t audio/*")
                subprocess.run(play_cmd, shell=True)
                
                # 等待一段时间让音频播放完成
                self.root.after(0, lambda: self.status_var.set("正在播放音频，请等待..."))
                time.sleep(30)  # 假设音频不超过30秒
            
            # 更新状态
            self.root.after(0, lambda: self.status_var.set("音频播放完成，录制继续进行中..."))
            self.root.after(0, lambda: self.loopback_status_var.set("音频播放完成，录制继续进行中..."))
            
            # 等待进程结束（由stop_loopback_recording方法终止）
            self.loopback_process.wait()
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            self.root.after(0, lambda: self.loopback_status_var.set("录制出错"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
            
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_loopback_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_loopback_button.config(state="disabled"))
    
    def create_default_test_audio(self):
        """创建默认测试音频文件"""
        try:
            # 确保audio目录存在
            if not os.path.exists("audio"):
                os.makedirs("audio")
                
            # 使用系统命令生成一个简单的测试音频
            # 这里使用ffmpeg生成一个1kHz的正弦波
            cmd = "ffmpeg -f lavfi -i \"sine=frequency=1000:duration=5\" -ac 8 -ar 48000 audio/default_test.wav -y"
            subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 如果ffmpeg不可用，可以尝试使用Python生成简单的测试音频
            # 这需要额外的库如numpy和scipy
            
        except Exception as e:
            print(f"创建默认测试音频失败: {str(e)}")

    def stop_loopback_test(self):
        """停止Loopback测试"""
        if not hasattr(self, 'loopback_process') or self.loopback_process is None:
            return
            
        try:
            # 停止录音进程
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /PID {self.loopback_process.pid}", shell=True)
            else:
                self.loopback_process.terminate()
            
            # 停止播放
            subprocess.run(self.get_adb_command("shell am force-stop com.android.hplayer"), shell=True)
            
            # 更新状态
            self.status_var.set("正在保存Loopback测试结果...")
            
            # 等待进程结束
            self.loopback_process.wait(timeout=2)
            
            # 拉取录音文件
            save_path = filedialog.asksaveasfilename(
                initialdir="test",
                title="保存Loopback测试录音",
                defaultextension=".wav",
                filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")]
            )
            
            if save_path:
                # 从设备拉取文件
                pull_cmd = self.get_adb_command("pull /sdcard/loopback_test.wav \"" + save_path + "\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"拉取文件失败: {result.stderr}")
                
                # 更新状态
                self.status_var.set(f"Loopback测试已完成，录音已保存到: {os.path.basename(save_path)}")
            else:
                self.status_var.set("Loopback测试已完成，但未保存录音")
            
            # 重置进程
            self.loopback_process = None
            
        except Exception as e:
            messagebox.showerror("错误", f"停止Loopback测试时出错:\n{str(e)}")

    def show_network_connect_dialog(self):
        """显示网络ADB连接对话框"""
        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("网络ADB连接")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)  # 设置为主窗口的临时窗口
        dialog.grab_set()  # 模态对话框
        
        # 添加说明
        ttk.Label(dialog, text="请输入设备IP地址和端口 (例如: 192.168.10.41:5555)", 
                 wraplength=350).pack(pady=10, padx=20)
        
        # 输入框
        input_frame = ttk.Frame(dialog)
        input_frame.pack(fill="x", padx=20, pady=10)
        
        ttk.Label(input_frame, text="设备地址:").pack(side="left", padx=5)
        address_var = tk.StringVar()
        address_entry = ttk.Entry(input_frame, textvariable=address_var, width=30)
        address_entry.pack(side="left", padx=5, fill="x", expand=True)
        address_entry.focus_set()  # 设置焦点
        
        # 状态显示
        status_var = tk.StringVar()
        status_label = ttk.Label(dialog, textvariable=status_var, foreground="blue")
        status_label.pack(fill="x", padx=20, pady=5)
        
        # 按钮区域
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=20, pady=10)
        
        def connect():
            """连接到网络ADB设备"""
            address = address_var.get().strip()
            if not address:
                status_var.set("请输入设备地址")
                return
                
            # 更新状态
            status_var.set(f"正在连接到 {address}...")
            dialog.update()
            
            try:
                # 执行ADB连接命令
                cmd = f"adb connect {address}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
                    status_var.set(f"已成功连接到 {address}")
                    # 刷新设备列表
                    self.refresh_devices()
                    # 延迟关闭对话框
                    dialog.after(1500, dialog.destroy)
                else:
                    status_var.set(f"连接失败: {result.stdout}")
            except Exception as e:
                status_var.set(f"连接错误: {str(e)}")
        
        # 连接按钮
        connect_button = ttk.Button(button_frame, text="连接", command=connect, width=10)
        connect_button.pack(side="left", padx=5)
        
        # 取消按钮
        cancel_button = ttk.Button(button_frame, text="取消", command=dialog.destroy, width=10)
        cancel_button.pack(side="right", padx=5)
        
        # 绑定回车键
        dialog.bind("<Return>", lambda e: connect())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        
        # 等待对话框关闭
        dialog.wait_window()

    def browse_mic_save_path(self):
        """浏览并选择麦克风录音保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择麦克风录音保存路径",
            initialdir=self.mic_save_path_var.get()
        )
        
        if folder_path:
            self.mic_save_path_var.set(folder_path)
            self.status_var.set(f"已设置麦克风录音保存路径: {folder_path}")

    def show_debug_info(self):
        """显示调试信息对话框"""
        # 收集调试信息
        debug_info = "音频测试工具调试信息\n"
        debug_info += "=" * 40 + "\n\n"
        
        # 系统信息
        debug_info += "系统信息:\n"
        debug_info += f"操作系统: {platform.system()} {platform.version()}\n"
        debug_info += f"Python版本: {sys.version}\n\n"
        
        # ADB信息
        debug_info += "ADB信息:\n"
        try:
            adb_version = subprocess.run("adb version", shell=True, capture_output=True, text=True)
            debug_info += f"ADB版本: {adb_version.stdout.strip()}\n"
        except:
            debug_info += "无法获取ADB版本\n"
        
        # 设备信息
        debug_info += "\n设备信息:\n"
        if self.selected_device:
            debug_info += f"当前设备: {self.selected_device}\n"
            
            # 尝试获取更多设备信息
            try:
                # 获取设备型号
                model_cmd = self.get_adb_command("shell getprop ro.product.model")
                model = subprocess.run(model_cmd, shell=True, capture_output=True, text=True)
                debug_info += f"设备型号: {model.stdout.strip()}\n"
                
                # 获取Android版本
                android_ver_cmd = self.get_adb_command("shell getprop ro.build.version.release")
                android_ver = subprocess.run(android_ver_cmd, shell=True, capture_output=True, text=True)
                debug_info += f"Android版本: {android_ver.stdout.strip()}\n"
                
                # 获取音频相关信息
                debug_info += "\n音频设备信息:\n"
                audio_devices_cmd = self.get_adb_command("shell tinymix")
                audio_devices = subprocess.run(audio_devices_cmd, shell=True, capture_output=True, text=True)
                # 只显示前几行
                audio_lines = audio_devices.stdout.strip().split('\n')[:10]
                debug_info += '\n'.join(audio_lines)
                debug_info += "\n...(更多音频设备信息省略)...\n"
            except:
                debug_info += "无法获取详细设备信息\n"
        else:
            debug_info += "未选择设备\n"
        
        # 应用状态信息
        debug_info += "\n应用状态:\n"
        debug_info += f"已选择音频文件: {self.selected_audio_file if self.selected_audio_file else '无'}\n"
        debug_info += f"本地音频文件: {self.local_audio_file if self.local_audio_file else '无'}\n"
        
        # 显示调试信息对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("调试信息")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        
        # 创建文本区域
        text_frame = ttk.Frame(dialog, padding=10)
        text_frame.pack(fill="both", expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        # 文本区域
        text_area = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        text_area.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_area.yview)
        
        # 插入调试信息
        text_area.insert("1.0", debug_info)
        text_area.config(state="disabled")  # 设为只读
        
        # 底部按钮
        button_frame = ttk.Frame(dialog, padding=10)
        button_frame.pack(fill="x")
        
        # 复制按钮
        def copy_to_clipboard():
            dialog.clipboard_clear()
            dialog.clipboard_append(debug_info)
            messagebox.showinfo("复制成功", "调试信息已复制到剪贴板")
        
        copy_button = ttk.Button(button_frame, text="复制到剪贴板", command=copy_to_clipboard)
        copy_button.pack(side="left", padx=5)
        
        # 关闭按钮
        close_button = ttk.Button(button_frame, text="关闭", command=dialog.destroy)
        close_button.pack(side="right", padx=5)
        
        # 绑定Escape键关闭对话框
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        
        # 等待对话框关闭
        dialog.wait_window()

    def stop_loopback_recording(self):
        """停止Loopback录音"""
        if not hasattr(self, 'loopback_process') or self.loopback_process is None:
            return
            
        try:
            # 停止录制进程
            subprocess.run(self.get_adb_command("shell pkill -f tinycap"), shell=True)
            self.loopback_process.terminate()
            
            # 更新状态
            self.status_var.set("录制已停止，准备保存...")
            self.loopback_status_var.set("录制已停止")
            
            # 恢复按钮状态
            self.start_loopback_button.config(state="normal")
            self.stop_loopback_button.config(state="disabled")
            
            # 提示用户选择保存位置
            save_path = filedialog.asksaveasfilename(
                initialdir="test",
                title="保存通道测试录音",
                initialfile=self.loopback_filename,
                defaultextension=".wav",
                filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")]
            )
            
            if save_path:
                # 从设备拉取文件到用户选择的位置
                self.status_var.set("正在保存录音文件...")
                pull_cmd = self.get_adb_command(f"pull /sdcard/{self.loopback_filename} \"{save_path}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"保存文件失败: {result.stderr}")
                
                self.status_var.set("通道测试完成，文件已保存")
                self.loopback_status_var.set("录音已保存")
            else:
                self.status_var.set("通道测试已完成，但未保存录音")
                self.loopback_status_var.set("录音未保存")
            
        except Exception as e:
            self.status_var.set(f"停止录音出错: {str(e)}")
            self.loopback_status_var.set("停止录音失败")
            messagebox.showerror("错误", f"停止通道录音时出错:\n{str(e)}")

    def _monitor_playback(self):
        """监控音频播放状态"""
        try:
            while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                time.sleep(0.5)
            
            # 播放结束
            if pygame.mixer.get_init() and not pygame.mixer.music.get_busy():
                self.root.after(0, lambda: self.playback_status_var.set("播放完成"))
                self.root.after(0, lambda: self.status_var.set("就绪"))
        except Exception as e:
            # 忽略监控过程中的错误
            pass

    def start_hal_dump(self):
        """开始 HAL 录音"""
        if not self.check_device_selected():
            return
        
        try:
            # 设置属性启用 HAL 录音
            self.status_var.set("正在启用 HAL 录音...")
            self.hal_status_var.set("正在启用 HAL 录音...")
            
            # 获取 root 权限
            subprocess.run(self.get_adb_command("root"), shell=True)
            time.sleep(1)  # 等待 root 权限生效
            
            # 设置 SELinux 为 permissive 模式
            subprocess.run(self.get_adb_command("shell setenforce 0"), shell=True)
            
            # 启用 HAL 录音
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.vpp.dump 1"), shell=True)
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.indump 1"), shell=True)
            
            self.status_var.set("HAL 录音已启用，请进行音频操作...")
            self.hal_status_var.set("HAL 录音进行中...")
            
            # 提示用户
            messagebox.showinfo("HAL 录音", "HAL 录音已启用\n\n请进行您需要的音频操作\n\n完成后点击'停止 HAL 录音'按钮")
            
        except Exception as e:
            self.status_var.set(f"启用 HAL 录音出错: {str(e)}")
            self.hal_status_var.set("启用失败")
            messagebox.showerror("错误", f"启用 HAL 录音时出错:\n{str(e)}")

    def stop_hal_dump(self):
        """停止 HAL 录音"""
        if not self.check_device_selected():
            return
        
        try:
            # 停止 HAL 录音
            self.status_var.set("正在停止 HAL 录音...")
            self.hal_status_var.set("正在停止 HAL 录音...")
            
            # 禁用 HAL 录音
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.vpp.dump 0"), shell=True)
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.indump 0"), shell=True)
            
            self.status_var.set("HAL 录音已停止")
            self.hal_status_var.set("HAL 录音已停止")
            
            # 刷新文件列表
            self.refresh_hal_files()
            
            # 提示用户
            messagebox.showinfo("HAL 录音", "HAL 录音已停止\n\n请使用'刷新文件列表'按钮查看生成的文件\n然后选择并拉取需要的文件")
            
        except Exception as e:
            self.status_var.set(f"停止 HAL 录音出错: {str(e)}")
            self.hal_status_var.set("停止失败")
            messagebox.showerror("错误", f"停止 HAL 录音时出错:\n{str(e)}")

    def refresh_hal_files(self):
        """刷新HAL录音文件列表"""
        if not self.check_device_selected():
            return
        
        directory = self.hal_dir_var.get().strip()
        if not directory:
            self.update_info_text("警告: 请输入录音目录路径")
            return
        
        try:
            self.hal_status_var.set(f"正在获取文件列表: {directory}...")
            self.update_info_text(f"正在获取文件列表: {directory}...")
            
            # 获取文件列表
            ls_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    self.hal_status_var.set(f"目录不存在: {directory}")
                    self.update_info_text(f"目录不存在: {directory}")
                    if messagebox.askyesno("目录不存在", f"目录 {directory} 不存在，是否创建？"):
                        self.create_hal_dir()
                else:
                    raise Exception(f"获取文件列表失败: {result.stderr}")
            else:
                lines = result.stdout.strip().split('\n')
                files = []
                
                for line in lines:
                    if line.endswith('.pcm') or line.endswith('.raw'):
                        # 提取文件名和大小
                        parts = line.split()
                        if len(parts) >= 8:
                            filename = parts[-1]
                            size = parts[4]
                            date_str = f"{parts[5]} {parts[6]}"
                            
                            # 将大小转换为更友好的格式
                            try:
                                size_num = int(size)
                                if size_num > 1024*1024:
                                    size_str = f"{size_num/(1024*1024):.1f} MB"
                                elif size_num > 1024:
                                    size_str = f"{size_num/1024:.1f} KB"
                                else:
                                    size_str = f"{size_num} B"
                            except:
                                size_str = size
                            
                            files.append(f"{filename} ({size_str}) - {date_str}")
                
                # 更新状态和信息
                if files:
                    self.hal_status_var.set(f"找到 {len(files)} 个录音文件")
                    self.update_info_text(f"找到 {len(files)} 个录音文件:")
                    for file_info in files:
                        self.update_info_text(f"  {file_info}")
                else:
                    self.hal_status_var.set("未找到录音文件")
                    self.update_info_text("未找到录音文件")
        
        except Exception as e:
            self.hal_status_var.set(f"刷新文件列表出错: {str(e)}")
            self.update_info_text(f"刷新文件列表出错: {str(e)}")
            messagebox.showerror("错误", f"刷新文件列表时出错:\n{str(e)}")

    def pull_hal_files(self):
        """拉取选中的HAL录音文件"""
        if not self.check_device_selected():
            return
        
        # 获取选中的文件
        selected_indices = self.hal_files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要拉取的文件")
            return
        
        # 获取录音目录
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        # 获取本地保存路径
        base_save_dir = self.hal_save_path_var.get().strip()
        if not base_save_dir:
            # 如果未设置保存路径，使用文件对话框选择
            base_save_dir = filedialog.askdirectory(title="选择保存目录", initialdir="test")
            if not base_save_dir:
                return
            self.hal_save_path_var.set(base_save_dir)
        
        # 创建带时间戳的子文件夹
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(base_save_dir, f"hal_dump_{timestamp}")
        
        try:
            self.hal_status_var.set("正在拉取录音文件...")
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 拉取选中的文件
            success_count = 0
            for index in selected_indices:
                file_info = self.hal_files_listbox.get(index)
                # 提取文件名 (文件名在括号前)
                filename = file_info.split(' (')[0]
                
                # 拉取文件
                pull_cmd = self.get_adb_command(f"pull {directory}/{filename} \"{os.path.join(save_dir, filename)}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                else:
                    messagebox.showwarning("拉取失败", f"拉取文件 {filename} 失败:\n{result.stderr}")
            
            if success_count > 0:
                self.hal_status_var.set(f"成功拉取 {success_count} 个录音文件到 {save_dir}")
                
                # 询问是否打开保存目录
                if messagebox.askyesno("拉取完成", f"成功拉取 {success_count} 个录音文件到:\n{save_dir}\n\n是否打开保存目录？"):
                    # 打开保存目录
                    if platform.system() == "Windows":
                        os.startfile(save_dir)
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", save_dir])
                    else:  # Linux
                        subprocess.run(["xdg-open", save_dir])
            else:
                self.hal_status_var.set("未成功拉取任何文件")
        
        except Exception as e:
            self.hal_status_var.set(f"拉取文件出错: {str(e)}")
            messagebox.showerror("错误", f"拉取录音文件时出错:\n{str(e)}")

    def get_sweep_files(self):
        """获取音频目录中的扫频文件"""
        sweep_files = []
        
        # 检查音频目录
        if os.path.exists("audio"):
            for file in os.listdir("audio"):
                if file.lower().endswith(('.wav', '.mp3')) and "sweep" in file.lower():
                    sweep_files.append(file)
        
        # 如果没有找到扫频文件，添加一些默认选项
        if not sweep_files:
            sweep_files = ["sweep_20-20000Hz.wav", "sweep_100-10000Hz.wav"]
        
        return sweep_files

    def browse_sweep_file(self):
        """浏览并选择扫频音频文件"""
        filetypes = [
            ("音频文件", "*.wav;*.mp3"),
            ("WAV文件", "*.wav"),
            ("MP3文件", "*.mp3"),
            ("所有文件", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="选择扫频音频文件",
            filetypes=filetypes
        )
        
        if filename:
            self.custom_sweep_file = filename
            self.custom_sweep_file_var.set(os.path.basename(filename))
            self.sweep_files_var.set("custom")

    def play_sweep_audio(self):
        """播放扫频音频"""
        if not self.check_device_selected():
            return
        
        # 获取选择的文件
        selected_file = self.sweep_files_var.get()
        
        if selected_file == "custom":
            if not hasattr(self, 'custom_sweep_file') or not self.custom_sweep_file:
                messagebox.showerror("错误", "请先选择自定义扫频文件")
                return
            audio_file = self.custom_sweep_file
        else:
            # 使用预设文件
            audio_file = os.path.join("audio", selected_file)
            if not os.path.exists(audio_file):
                # 如果文件不存在，尝试创建音频目录并提示用户
                os.makedirs("audio", exist_ok=True)
                messagebox.showerror("错误", f"扫频文件不存在: {audio_file}\n请将扫频文件放入audio目录")
                return
        
        try:
            # 停止当前播放
            self.stop_sweep_audio()
            
            self.status_var.set("正在准备播放扫频音频...")
            self.sweep_status_var.set("准备中...")
            
            # 推送文件到设备
            remote_filename = "sweep_audio" + os.path.splitext(audio_file)[1]
            self.status_var.set("正在推送扫频文件到设备...")
            push_cmd = self.get_adb_command(f"push \"{audio_file}\" /sdcard/{remote_filename}")
            result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"推送文件失败: {result.stderr}")
            
            # 使用tinyplay播放
            self.status_var.set("正在播放扫频音频...")
            self.sweep_status_var.set("播放中...")
            
            # 在新线程中运行播放命令
            self.sweep_thread = threading.Thread(
                target=self._play_sweep_thread,
                args=(remote_filename,),
                daemon=True
            )
            self.sweep_thread.start()
            
        except Exception as e:
            self.status_var.set(f"播放扫频音频出错: {str(e)}")
            self.sweep_status_var.set("播放出错")
            messagebox.showerror("错误", f"播放扫频音频时出错:\n{str(e)}")

    def _play_sweep_thread(self, remote_filename):
        """在线程中播放扫频音频"""
        try:
            # 使用tinyplay播放
            play_cmd = self.get_adb_command(f"shell tinyplay /sdcard/{remote_filename}")
            self.sweep_process = subprocess.Popen(play_cmd, shell=True)
            
            # 等待播放完成
            self.sweep_process.wait()
            
            # 播放完成
            self.root.after(0, lambda: self.status_var.set("扫频音频播放完成"))
            self.root.after(0, lambda: self.sweep_status_var.set("播放完成"))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"播放扫频音频出错: {str(e)}"))
            self.root.after(0, lambda: self.sweep_status_var.set("播放出错"))

    def stop_sweep_audio(self):
        """停止播放扫频音频"""
        if hasattr(self, 'sweep_process') and self.sweep_process:
            try:
                # 停止tinyplay进程
                subprocess.run(self.get_adb_command("shell pkill -f tinyplay"), shell=True)
                self.sweep_process.terminate()
                self.sweep_process = None
                
                self.status_var.set("已停止播放扫频音频")
                self.sweep_status_var.set("已停止")
                
            except Exception as e:
                self.status_var.set(f"停止播放出错: {str(e)}")
                self.sweep_status_var.set("停止出错")

    def start_hal_recording(self):
        """开始 HAL 录音"""
        if not self.check_device_selected():
            return
        
        try:
            # 首先确保录音目录存在
            directory = self.hal_dir_var.get().strip()
            if not directory:
                messagebox.showwarning("警告", "请输入录音目录路径")
                return
            
            # 自动创建录音目录
            self.ensure_hal_dir(directory)
            
            # 获取所有选中的属性
            enabled_props = []
            for prop, var in self.hal_props.items():
                if var.get():
                    enabled_props.append(prop)
            
            if not enabled_props:
                messagebox.showwarning("警告", "请至少选择一个录音属性")
                return
            
            # 更新状态
            self.hal_status_var.set("正在开始录音...")
            self.hal_recording_status_var.set("正在开始...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_hal_button.config(state="disabled")
            self.stop_hal_button.config(state="normal")
            
            # 设置所有选中的属性为1
            for prop in enabled_props:
                set_cmd = self.get_adb_command(f"shell setprop {prop} 1")
                result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"设置属性 {prop} 失败: {result.stderr}")
            
            # 记录开始时间
            start_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self.hal_start_time_var.set(start_time)
            
            # 更新状态
            self.hal_status_var.set("录音已开始")
            self.hal_recording_status_var.set("录音中")
            self.update_info_text(f"录音已开始，时间: {start_time}")
            self.update_info_text(f"启用的属性: {', '.join(enabled_props)}")
            
            # 如果设置了自动停止时间，启动定时器
            try:
                duration = int(self.hal_duration_var.get())
                if duration > 0:
                    self.hal_timer = threading.Timer(duration, self.stop_hal_recording)
                    self.hal_timer.daemon = True
                    self.hal_timer.start()
                    self.update_info_text(f"已设置自动停止，时长: {duration}秒")
            except (ValueError, TypeError):
                # 如果输入的不是有效数字，忽略自动停止
                pass
            
        except Exception as e:
            self.hal_status_var.set(f"开始录音出错: {str(e)}")
            self.hal_recording_status_var.set("开始失败")
            self.update_info_text(f"开始录音出错: {str(e)}")
            messagebox.showerror("错误", f"开始录音时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")

    def stop_hal_recording(self):
        """停止 HAL 录音"""
        if not self.check_device_selected():
            return
        
        try:
            # 更新状态
            self.hal_status_var.set("正在停止 HAL 录音...")
            self.hal_recording_status_var.set("正在停止...")
            
            # 取消定时器（如果存在）
            if hasattr(self, 'hal_timer') and self.hal_timer:
                self.hal_timer.cancel()
                self.hal_timer = None
            
            # 禁用所有 HAL 录音
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.indump 0"), shell=True)
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.vpp.dump 0"), shell=True)
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.outdump 0"), shell=True)
            
            # 等待一段时间确保文件写入完成
            time.sleep(1)
            
            # 恢复按钮状态
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")
            
            # 刷新文件列表
            self.refresh_hal_files()
            
            # 更新状态
            self.status_var.set("HAL 录音已停止")
            self.hal_status_var.set("已停止")
            
        except Exception as e:
            self.status_var.set(f"停止 HAL 录音出错: {str(e)}")
            self.hal_status_var.set("停止失败")
            messagebox.showerror("错误", f"停止 HAL 录音时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")

    def delete_hal_files(self):
        """删除选中的 HAL 录音文件"""
        if not self.check_device_selected():
            return
        
        # 获取选中的文件
        selected_indices = self.hal_files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要删除的文件")
            return
        
        # 确认删除
        file_count = len(selected_indices)
        if not messagebox.askyesno("确认删除", f"确定要删除选中的 {file_count} 个文件吗？\n此操作不可撤销！"):
            return
        
        try:
            self.status_var.set("正在删除 HAL 录音文件...")
            self.hal_status_var.set("正在删除文件...")
            
            # 删除选中的文件
            success_count = 0
            for index in selected_indices:
                file_info = self.hal_files_listbox.get(index)
                filename = file_info.split(' ')[0]  # 提取文件名
                
                # 删除文件
                delete_cmd = self.get_adb_command(f"shell rm /data/vendor/audiohal/{filename}")
                result = subprocess.run(delete_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                else:
                    messagebox.showwarning("删除失败", f"删除文件 {filename} 失败:\n{result.stderr}")
            
            # 刷新文件列表
            self.refresh_hal_files()
            
            if success_count > 0:
                self.status_var.set(f"成功删除 {success_count} 个 HAL 录音文件")
                self.hal_status_var.set(f"成功删除 {success_count} 个文件")
            else:
                self.status_var.set("未成功删除任何文件")
                self.hal_status_var.set("删除失败")
        
        except Exception as e:
            self.status_var.set(f"删除 HAL 文件出错: {str(e)}")
            self.hal_status_var.set("删除失败")
            messagebox.showerror("错误", f"删除 HAL 文件时出错:\n{str(e)}")

    def refresh_sweep_files(self):
        """刷新扫频音频文件列表"""
        sweep_dir = self.sweep_dir_var.get()
        if not os.path.exists(sweep_dir):
            messagebox.showwarning("警告", f"扫频文件目录不存在: {sweep_dir}")
            return
        
        try:
            self.sweep_files_listbox.delete(0, tk.END)
            for file in os.listdir(sweep_dir):
                if file.lower().endswith(('.wav', '.mp3')):
                    self.sweep_files_listbox.insert(tk.END, file)
            self.sweep_status_var.set(f"已加载 {len(self.sweep_files_listbox.get(0, tk.END))} 个扫频文件")
        except Exception as e:
            messagebox.showerror("错误", f"刷新扫频文件列表时出错:\n{str(e)}")

    def browse_sweep_dir(self):
        """浏览并选择扫频音频文件目录"""
        folder_path = filedialog.askdirectory(
            title="选择扫频音频文件目录",
            initialdir=self.sweep_dir_var.get()
        )
        
        if folder_path:
            self.sweep_dir_var.set(folder_path)
            self.status_var.set(f"已设置扫频音频文件目录: {folder_path}")

    def add_custom_prop(self):
        """添加自定义录音属性"""
        prop = self.custom_prop_var.get().strip()
        if not prop:
            messagebox.showwarning("警告", "请输入属性名称")
            return
        
        # 检查是否已存在
        existing_props = self.custom_props_listbox.get(0, tk.END)
        if prop in existing_props:
            messagebox.showwarning("警告", f"属性 '{prop}' 已存在")
            return
        
        # 添加到列表
        self.custom_props_listbox.insert(tk.END, prop)
        self.custom_prop_var.set("")  # 清空输入框
        self.custom_status_var.set(f"已添加属性: {prop}")

    def remove_custom_prop(self):
        """删除选中的录音属性"""
        selected_indices = self.custom_props_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要删除的属性")
            return
        
        # 从后往前删除，避免索引变化
        for index in sorted(selected_indices, reverse=True):
            prop = self.custom_props_listbox.get(index)
            self.custom_props_listbox.delete(index)
            self.custom_status_var.set(f"已删除属性: {prop}")

    def clear_custom_props(self):
        """清空录音属性列表"""
        if not messagebox.askyesno("确认", "确定要清空所有属性吗？"):
            return
        
        self.custom_props_listbox.delete(0, tk.END)
        self.custom_status_var.set("已清空属性列表")

    def reset_custom_props(self):
        """重置为默认录音属性"""
        if not messagebox.askyesno("确认", "确定要重置为默认属性吗？"):
            return
        
        # 清空当前列表
        self.custom_props_listbox.delete(0, tk.END)
        
        # 添加默认属性
        default_props = [
            "vendor.media.audiohal.vpp.dump",
            "vendor.media.audiohal.indump",
            "vendor.media.audiohal.outdump"
        ]
        
        for prop in default_props:
            self.custom_props_listbox.insert(tk.END, prop)
        
        self.custom_status_var.set("已重置为默认属性")

    def create_custom_dir(self):
        """创建自定义录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.custom_status_var.set(f"正在创建目录: {directory}...")
            
            # 获取 root 权限
            subprocess.run(self.get_adb_command("root"), shell=True)
            time.sleep(1)  # 等待 root 权限生效
            
            # 设置 SELinux 为 permissive 模式
            subprocess.run(self.get_adb_command("shell setenforce 0"), shell=True)
            
            # 创建目录
            mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
            result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"创建目录失败: {result.stderr}")
            
            # 设置权限
            chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
            result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"设置目录权限失败: {result.stderr}")
            
            self.custom_status_var.set(f"已成功创建目录: {directory}")
            messagebox.showinfo("成功", f"已成功创建录音目录:\n{directory}")
            
            # 刷新文件列表
            self.refresh_custom_files()
            
        except Exception as e:
            self.custom_status_var.set(f"创建目录出错: {str(e)}")
            messagebox.showerror("错误", f"创建录音目录时出错:\n{str(e)}")

    def check_custom_dir(self):
        """检查自定义录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.custom_status_var.set(f"正在检查目录: {directory}...")
            
            # 检查目录是否存在
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    self.custom_status_var.set(f"目录不存在: {directory}")
                    if messagebox.askyesno("目录不存在", f"目录 {directory} 不存在，是否创建？"):
                        self.create_custom_dir()
                else:
                    raise Exception(f"检查目录失败: {result.stderr}")
            else:
                self.custom_status_var.set(f"目录已存在: {directory}")
                messagebox.showinfo("目录检查", f"目录 {directory} 已存在")
                
                # 刷新文件列表
                self.refresh_custom_files()
            
        except Exception as e:
            self.custom_status_var.set(f"检查目录出错: {str(e)}")
            messagebox.showerror("错误", f"检查录音目录时出错:\n{str(e)}")

    def browse_custom_save_path(self):
        """浏览并选择本地保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择本地保存路径",
            initialdir=self.custom_save_path_var.get()
        )
        
        if folder_path:
            self.custom_save_path_var.set(folder_path)
            self.custom_status_var.set(f"已设置本地保存路径: {folder_path}")

    def start_custom_recording(self):
        """开始自定义录音"""
        if not self.check_device_selected():
            return
        
        # 获取选中的属性
        selected_indices = self.custom_props_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要启用的录音属性")
            return
        
        # 获取录音目录
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        # 获取自动停止时间
        try:
            auto_stop_duration = int(self.custom_duration_var.get())
            if auto_stop_duration < 0:
                messagebox.showwarning("警告", "自动停止时间不能为负数")
                return
        except ValueError:
            messagebox.showwarning("警告", "自动停止时间必须是整数")
            return
        
        try:
            # 更新状态
            self.custom_status_var.set("正在准备录音...")
            self.custom_recording_status_var.set("准备中...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_custom_button.config(state="disabled")
            self.stop_custom_button.config(state="normal")
            
            # 获取 root 权限
            subprocess.run(self.get_adb_command("root"), shell=True)
            time.sleep(1)  # 等待 root 权限生效
            
            # 设置 SELinux 为 permissive 模式
            subprocess.run(self.get_adb_command("shell setenforce 0"), shell=True)
            
            # 检查并创建目录
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    # 创建目录
                    mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
                    result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"创建目录失败: {result.stderr}")
                    
                    # 设置权限
                    chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
                    result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
            
            # 清空录音目录中的旧文件
            if messagebox.askyesno("确认", "是否清空录音目录中的旧文件？"):
                clear_cmd = self.get_adb_command(f"shell rm -f {directory}/*.pcm {directory}/*.raw")
                subprocess.run(clear_cmd, shell=True)
                self.custom_status_var.set("已清空录音目录中的旧文件")
            
            # 设置选中的属性
            selected_props = []
            for index in selected_indices:
                prop = self.custom_props_listbox.get(index)
                selected_props.append(prop)
                
                # 设置属性为1
                set_cmd = self.get_adb_command(f"shell setprop {prop} 1")
                result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"设置属性 {prop} 失败: {result.stderr}")
            
            # 记录开始时间
            start_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self.custom_start_time_var.set(start_time)
            
            # 更新状态
            self.custom_status_var.set(f"录音已开始，已启用 {len(selected_props)} 个属性")
            self.custom_recording_status_var.set("录音中...")
            
            # 如果设置了自动停止时间
            if auto_stop_duration > 0:
                self.custom_status_var.set(f"录音已开始，将在 {auto_stop_duration} 秒后自动停止")
                
                # 启动定时器自动停止录音
                self.custom_timer = threading.Timer(auto_stop_duration, self.stop_custom_recording)
                self.custom_timer.daemon = True
                self.custom_timer.start()
            
        except Exception as e:
            self.custom_status_var.set(f"启动录音出错: {str(e)}")
            self.custom_recording_status_var.set("启动失败")
            self.start_custom_button.config(state="normal")
            self.stop_custom_button.config(state="disabled")
            messagebox.showerror("错误", f"启动录音时出错:\n{str(e)}")

    def stop_custom_recording(self):
        """停止自定义录音"""
        if not self.check_device_selected():
            return
        
        try:
            # 更新状态
            self.custom_status_var.set("正在停止录音...")
            self.custom_recording_status_var.set("正在停止...")
            
            # 取消定时器（如果存在）
            if hasattr(self, 'custom_timer') and self.custom_timer:
                self.custom_timer.cancel()
                self.custom_timer = None
            
            # 获取所有属性
            all_props = self.custom_props_listbox.get(0, tk.END)
            
            # 禁用所有属性
            for prop in all_props:
                set_cmd = self.get_adb_command(f"shell setprop {prop} 0")
                subprocess.run(set_cmd, shell=True)
            
            # 等待一段时间确保文件写入完成
            time.sleep(1)
            
            # 恢复按钮状态
            self.start_custom_button.config(state="normal")
            self.stop_custom_button.config(state="disabled")
            
            # 刷新文件列表
            self.refresh_custom_files()
            
            # 记录结束时间
            end_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 计算持续时间
            start_time = self.custom_start_time_var.get()
            if start_time != "-":
                duration = self.calculate_duration(start_time, end_time)
            else:
                duration = "未知"
            
            # 更新状态
            self.custom_status_var.set(f"录音已停止，持续时间: {duration}")
            self.custom_recording_status_var.set("已停止")
            
            # 询问是否拉取文件
            if messagebox.askyesno("录音完成", f"录音已完成，持续时间: {duration}\n\n是否立即拉取录音文件？"):
                self.pull_custom_files()
            
        except Exception as e:
            self.custom_status_var.set(f"停止录音出错: {str(e)}")
            self.custom_recording_status_var.set("停止失败")
            messagebox.showerror("错误", f"停止录音时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_custom_button.config(state="normal")
            self.stop_custom_button.config(state="disabled")

    def calculate_duration(self, start_time_str, end_time_str):
        """计算录音持续时间"""
        try:
            start_time = time.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            end_time = time.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            
            start_timestamp = time.mktime(start_time)
            end_timestamp = time.mktime(end_time)
            
            duration_seconds = int(end_timestamp - start_timestamp)
            
            if duration_seconds < 60:
                return f"{duration_seconds} 秒"
            elif duration_seconds < 3600:
                minutes = duration_seconds // 60
                seconds = duration_seconds % 60
                return f"{minutes} 分 {seconds} 秒"
            else:
                hours = duration_seconds // 3600
                minutes = (duration_seconds % 3600) // 60
                seconds = duration_seconds % 60
                return f"{hours} 小时 {minutes} 分 {seconds} 秒"
        except:
            return "未知"

    def refresh_custom_files(self):
        """刷新自定义录音文件列表"""
        if not self.check_device_selected():
            return
        
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.custom_status_var.set(f"正在获取文件列表: {directory}...")
            
            # 清空列表框
            self.custom_files_listbox.delete(0, tk.END)
            
            # 获取文件列表
            ls_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    self.custom_status_var.set(f"目录不存在: {directory}")
                    if messagebox.askyesno("目录不存在", f"目录 {directory} 不存在，是否创建？"):
                        self.create_custom_dir()
                else:
                    raise Exception(f"获取文件列表失败: {result.stderr}")
            else:
                lines = result.stdout.strip().split('\n')
                files = []
                
                for line in lines:
                    if line.endswith('.pcm') or line.endswith('.raw'):
                        # 提取文件名和大小
                        parts = line.split()
                        if len(parts) >= 8:
                            filename = parts[-1]
                            size = parts[4]
                            
                            # 将大小转换为更友好的格式
                            try:
                                size_num = int(size)
                                if size_num > 1024*1024:
                                    size_str = f"{size_num/(1024*1024):.1f} MB"
                                elif size_num > 1024:
                                    size_str = f"{size_num/1024:.1f} KB"
                                else:
                                    size_str = f"{size_num} B"
                            except:
                                size_str = size
                            
                            files.append(f"{filename} ({size_str})")
                
                # 添加到列表框
                for file in files:
                    self.custom_files_listbox.insert(tk.END, file)
                
                self.custom_status_var.set(f"找到 {len(files)} 个录音文件")
        
        except Exception as e:
            self.custom_status_var.set(f"刷新文件列表出错: {str(e)}")
            messagebox.showerror("错误", f"刷新文件列表时出错:\n{str(e)}")

    def pull_custom_files(self):
        """拉取选中的自定义录音文件"""
        if not self.check_device_selected():
            return
        
        # 获取选中的文件
        selected_indices = self.custom_files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要拉取的文件")
            return
        
        # 获取录音目录
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        # 获取本地保存路径
        save_dir = self.custom_save_path_var.get().strip()
        if not save_dir:
            # 如果未设置保存路径，使用文件对话框选择
            save_dir = filedialog.askdirectory(title="选择保存目录", initialdir="test")
            if not save_dir:
                return
            self.custom_save_path_var.set(save_dir)
        
        try:
            self.custom_status_var.set("正在拉取录音文件...")
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 拉取选中的文件
            success_count = 0
            for index in selected_indices:
                file_info = self.custom_files_listbox.get(index)
                filename = file_info.split(' ')[0]  # 提取文件名
                
                # 拉取文件
                pull_cmd = self.get_adb_command(f"pull {directory}/{filename} \"{os.path.join(save_dir, filename)}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                else:
                    messagebox.showwarning("拉取失败", f"拉取文件 {filename} 失败:\n{result.stderr}")
            
            if success_count > 0:
                self.custom_status_var.set(f"成功拉取 {success_count} 个录音文件")
                
                # 询问是否打开保存目录
                if messagebox.askyesno("拉取完成", f"成功拉取 {success_count} 个录音文件到:\n{save_dir}\n\n是否打开保存目录？"):
                    # 打开保存目录
                    if platform.system() == "Windows":
                        os.startfile(save_dir)
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", save_dir])
                    else:  # Linux
                        subprocess.run(["xdg-open", save_dir])
            else:
                self.custom_status_var.set("未成功拉取任何文件")
        
        except Exception as e:
            self.custom_status_var.set(f"拉取文件出错: {str(e)}")
            messagebox.showerror("错误", f"拉取录音文件时出错:\n{str(e)}")

    def delete_custom_files(self):
        """删除选中的自定义录音文件"""
        if not self.check_device_selected():
            return
        
        # 获取选中的文件
        selected_indices = self.custom_files_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要删除的文件")
            return
        
        # 获取录音目录
        directory = self.custom_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        # 确认删除
        file_count = len(selected_indices)
        if not messagebox.askyesno("确认删除", f"确定要删除选中的 {file_count} 个文件吗？\n此操作不可撤销！"):
            return
        
        try:
            self.custom_status_var.set("正在删除录音文件...")
            
            # 删除选中的文件
            success_count = 0
            for index in selected_indices:
                file_info = self.custom_files_listbox.get(index)
                filename = file_info.split(' ')[0]  # 提取文件名
                
                # 删除文件
                delete_cmd = self.get_adb_command(f"shell rm {directory}/{filename}")
                result = subprocess.run(delete_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                else:
                    messagebox.showwarning("删除失败", f"删除文件 {filename} 失败:\n{result.stderr}")
            
            # 刷新文件列表
            self.refresh_custom_files()
            
            if success_count > 0:
                self.custom_status_var.set(f"成功删除 {success_count} 个录音文件")
            else:
                self.custom_status_var.set("未成功删除任何文件")
        
        except Exception as e:
            self.custom_status_var.set(f"删除文件出错: {str(e)}")
            messagebox.showerror("错误", f"删除录音文件时出错:\n{str(e)}")

    def add_hal_prop(self):
        """添加新的录音属性"""
        prop = self.hal_prop_var.get().strip()
        if not prop:
            messagebox.showwarning("警告", "请输入属性名称")
            return
        
        # 检查是否已存在
        if prop in self.hal_props:
            messagebox.showwarning("警告", f"属性 '{prop}' 已存在")
            return
        
        # 添加到列表
        self.hal_props[prop] = tk.StringVar()
        self.add_prop_to_ui(prop)

    def add_prop_to_ui(self, prop):
        """将新的录音属性添加到UI"""
        if prop in self.hal_props and hasattr(self.hal_props[prop], 'frame'):
            return  # 属性已存在
        
        # 创建属性行
        prop_frame = ttk.Frame(self.props_container)
        prop_frame.pack(fill="x", pady=1)
        
        # 创建复选框
        var = tk.BooleanVar(value=True)
        var.frame = prop_frame  # 保存对应的frame引用
        self.hal_props[prop] = var
        
        cb = ttk.Checkbutton(prop_frame, text=prop, variable=var, style="Small.TCheckbutton")
        cb.pack(side="left", padx=2)
        
        # 创建删除按钮
        delete_button = ttk.Button(prop_frame, text="×", width=2, 
                                 command=lambda p=prop: self.remove_prop(p), style="Delete.TButton")
        delete_button.pack(side="right", padx=2)

    def remove_prop(self, prop):
        """删除选中的录音属性"""
        if prop in self.hal_props:
            # 获取对应的frame并销毁
            if hasattr(self.hal_props[prop], 'frame'):
                self.hal_props[prop].frame.destroy()
            # 从字典中删除
            del self.hal_props[prop]
            self.hal_status_var.set(f"已删除属性: {prop}")

    def create_hal_dir(self):
        """创建自定义录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.hal_status_var.set(f"正在创建目录: {directory}...")
            self.update_info_text(f"正在创建目录: {directory}...")
            
            # 创建目录
            mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
            result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"创建目录失败: {result.stderr}")
            
            # 设置权限
            chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
            result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"设置目录权限失败: {result.stderr}")
            
            self.hal_status_var.set(f"目录创建成功: {directory}")
            self.update_info_text(f"目录创建成功: {directory}")
            
            # 刷新文件列表
            self.refresh_hal_files()
            
        except Exception as e:
            self.hal_status_var.set(f"创建目录出错: {str(e)}")
            self.update_info_text(f"创建目录出错: {str(e)}")
            messagebox.showerror("错误", f"创建目录时出错:\n{str(e)}")

    def check_hal_dir(self):
        """检查自定义录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.hal_status_var.set(f"正在检查目录: {directory}...")
            
            # 检查目录是否存在
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    self.hal_status_var.set(f"目录不存在: {directory}")
                    if messagebox.askyesno("目录不存在", f"目录 {directory} 不存在，是否创建？"):
                        self.create_hal_dir()
                else:
                    raise Exception(f"检查目录失败: {result.stderr}")
            else:
                self.hal_status_var.set(f"目录已存在: {directory}")
                messagebox.showinfo("目录检查", f"目录 {directory} 已存在")
                
                # 刷新文件列表
                self.refresh_hal_files()
            
        except Exception as e:
            self.hal_status_var.set(f"检查目录出错: {str(e)}")
            messagebox.showerror("错误", f"检查录音目录时出错:\n{str(e)}")

    def browse_hal_save_path(self):
        """浏览并选择本地保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择本地保存路径",
            initialdir=self.hal_save_path_var.get()
        )
        
        if folder_path:
            self.hal_save_path_var.set(folder_path)
            self.hal_status_var.set(f"已设置本地保存路径: {folder_path}")

    def add_prop_to_ui(self, prop):
        """将属性添加到UI界面"""
        if prop in self.hal_props and hasattr(self.hal_props[prop], 'frame'):
            return  # 属性已存在
        
        # 创建属性行
        prop_frame = ttk.Frame(self.props_container)
        prop_frame.pack(fill="x", pady=1)
        
        # 创建复选框
        var = tk.BooleanVar(value=True)
        var.frame = prop_frame  # 保存对应的frame引用
        self.hal_props[prop] = var
        
        cb = ttk.Checkbutton(prop_frame, text=prop, variable=var, style="Small.TCheckbutton")
        cb.pack(side="left", padx=2)
        
        # 创建删除按钮
        delete_button = ttk.Button(prop_frame, text="×", width=2, 
                                 command=lambda p=prop: self.remove_prop(p), style="Delete.TButton")
        delete_button.pack(side="right", padx=2)

    def remove_prop_from_ui(self, prop, frame):
        """从UI界面移除属性"""
        if prop in self.hal_props:
            del self.hal_props[prop]
        frame.destroy()
        self.hal_status_var.set(f"已删除属性: {prop}")

    def add_hal_prop(self):
        """添加HAL录音属性"""
        prop = self.hal_prop_var.get().strip()
        if not prop:
            messagebox.showwarning("警告", "请输入属性名称")
            return
        
        # 检查是否已存在
        if prop in self.hal_props:
            messagebox.showwarning("警告", f"属性 '{prop}' 已存在")
            return
        
        # 添加到UI
        self.add_prop_to_ui(prop)
        self.hal_prop_var.set("")  # 清空输入框
        self.hal_status_var.set(f"已添加属性: {prop}")

    def create_hal_dir(self):
        """创建HAL录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.hal_status_var.set(f"正在创建目录: {directory}...")
            
            # 获取 root 权限
            subprocess.run(self.get_adb_command("root"), shell=True)
            time.sleep(1)  # 等待 root 权限生效
            
            # 设置 SELinux 为 permissive 模式
            subprocess.run(self.get_adb_command("shell setenforce 0"), shell=True)
            
            # 创建目录
            mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
            result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"创建目录失败: {result.stderr}")
            
            # 设置权限
            chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
            result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"设置目录权限失败: {result.stderr}")
            
            self.hal_status_var.set(f"已成功创建目录: {directory}")
            messagebox.showinfo("成功", f"已成功创建录音目录:\n{directory}")
            
            # 刷新文件列表
            self.refresh_hal_files()
            
        except Exception as e:
            self.hal_status_var.set(f"创建目录出错: {str(e)}")
            messagebox.showerror("错误", f"创建录音目录时出错:\n{str(e)}")

    def check_hal_dir(self):
        """检查HAL录音目录"""
        if not self.check_device_selected():
            return
        
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        try:
            self.hal_status_var.set(f"正在检查目录: {directory}...")
            
            # 检查目录是否存在
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    self.hal_status_var.set(f"目录不存在: {directory}")
                    if messagebox.askyesno("目录不存在", f"目录 {directory} 不存在，是否创建？"):
                        self.create_hal_dir()
                else:
                    raise Exception(f"检查目录失败: {result.stderr}")
            else:
                self.hal_status_var.set(f"目录已存在: {directory}")
                messagebox.showinfo("目录检查", f"目录 {directory} 已存在")
                
                # 刷新文件列表
                self.refresh_hal_files()
            
        except Exception as e:
            self.hal_status_var.set(f"检查目录出错: {str(e)}")
            messagebox.showerror("错误", f"检查录音目录时出错:\n{str(e)}")

    def browse_hal_save_path(self):
        """浏览并选择本地保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择本地保存路径",
            initialdir=self.hal_save_path_var.get()
        )
        
        if folder_path:
            self.hal_save_path_var.set(folder_path)
            self.hal_status_var.set(f"已设置本地保存路径: {folder_path}")

    def start_hal_recording(self):
        """开始HAL录音"""
        if not self.check_device_selected():
            return
        
        # 获取选中的属性
        selected_props = []
        for prop, var in self.hal_props.items():
            if var.get():
                selected_props.append(prop)
        
        if not selected_props:
            messagebox.showwarning("警告", "请先选择要启用的录音属性")
            return
        
        # 获取录音目录
        directory = self.hal_dir_var.get().strip()
        if not directory:
            messagebox.showwarning("警告", "请输入录音目录路径")
            return
        
        # 获取自动停止时间
        try:
            auto_stop_duration = int(self.hal_duration_var.get())
            if auto_stop_duration < 0:
                messagebox.showwarning("警告", "自动停止时间不能为负数")
                return
        except ValueError:
            messagebox.showwarning("警告", "自动停止时间必须是整数")
            return
        
        try:
            # 更新状态
            self.hal_status_var.set("正在准备录音...")
            self.hal_recording_status_var.set("准备中...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_hal_button.config(state="disabled")
            self.stop_hal_button.config(state="normal")
            
            # 获取 root 权限
            subprocess.run(self.get_adb_command("root"), shell=True)
            time.sleep(1)  # 等待 root 权限生效
            
            # 设置 SELinux 为 permissive 模式
            subprocess.run(self.get_adb_command("shell setenforce 0"), shell=True)
            
            # 检查并创建目录
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "No such file or directory" in result.stderr:
                    # 创建目录
                    mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
                    result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"创建目录失败: {result.stderr}")
                    
                    # 设置权限
                    chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
                    result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
            
            # 清空录音目录中的旧文件
            if messagebox.askyesno("确认", "是否清空录音目录中的旧文件？"):
                clear_cmd = self.get_adb_command(f"shell rm -f {directory}/*.pcm {directory}/*.raw")
                subprocess.run(clear_cmd, shell=True)
                self.hal_status_var.set("已清空录音目录中的旧文件")
            
            # 设置选中的属性
            for prop in selected_props:
                # 设置属性为1
                set_cmd = self.get_adb_command(f"shell setprop {prop} 1")
                result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"设置属性 {prop} 失败: {result.stderr}")
            
            # 记录开始时间
            start_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self.hal_start_time_var.set(start_time)
            
            # 更新状态
            self.hal_status_var.set(f"录音已开始，已启用 {len(selected_props)} 个属性")
            self.hal_recording_status_var.set("录音中...")
            
            # 如果设置了自动停止时间
            if auto_stop_duration > 0:
                self.hal_status_var.set(f"录音已开始，将在 {auto_stop_duration} 秒后自动停止")
                
                # 启动定时器自动停止录音
                self.hal_timer = threading.Timer(auto_stop_duration, self.stop_hal_recording)
                self.hal_timer.daemon = True
                self.hal_timer.start()
            
        except Exception as e:
            self.hal_status_var.set(f"启动录音出错: {str(e)}")
            self.hal_recording_status_var.set("启动失败")
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")
            messagebox.showerror("错误", f"启动录音时出错:\n{str(e)}")

    def stop_hal_recording(self):
        """停止HAL录音并自动拉取文件"""
        if not self.check_device_selected():
            return
        
        try:
            # 更新状态
            self.hal_status_var.set("正在停止录音...")
            self.hal_recording_status_var.set("正在停止...")
            
            # 取消定时器（如果存在）
            if hasattr(self, 'hal_timer') and self.hal_timer:
                self.hal_timer.cancel()
                self.hal_timer = None
            
            # 获取所有属性
            all_props = list(self.hal_props.keys())
            
            # 禁用所有属性
            for prop in all_props:
                set_cmd = self.get_adb_command(f"shell setprop {prop} 0")
                subprocess.run(set_cmd, shell=True)
            
            # 等待一段时间确保文件写入完成
            time.sleep(1)
            
            # 恢复按钮状态
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")
            
            # 记录结束时间
            end_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 计算持续时间
            start_time = self.hal_start_time_var.get()
            if start_time != "-":
                duration = self.calculate_duration(start_time, end_time)
            else:
                duration = "未知"
            
            # 更新状态
            self.hal_status_var.set(f"录音已停止，持续时间: {duration}")
            self.hal_recording_status_var.set("已停止")
            
            # 自动拉取文件
            self.update_info_text(f"录音已停止，持续时间: {duration}\n正在拉取录音文件...")
            self.auto_pull_hal_files()
            
        except Exception as e:
            self.hal_status_var.set(f"停止录音出错: {str(e)}")
            self.hal_recording_status_var.set("停止失败")
            messagebox.showerror("错误", f"停止录音时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_hal_button.config(state="normal")
            self.stop_hal_button.config(state="disabled")

    def auto_pull_hal_files(self):
        """自动拉取HAL录音文件"""
        if not self.check_device_selected():
            return
        
        # 获取录音目录
        directory = self.hal_dir_var.get().strip()
        if not directory:
            self.update_info_text("错误: 录音目录未设置")
            return
        
        # 获取本地保存路径
        base_save_dir = self.hal_save_path_var.get().strip()
        if not base_save_dir:
            # 如果未设置保存路径，使用当前目录下的hal_dump文件夹
            base_save_dir = os.path.join(os.getcwd(), "hal_dump")
            os.makedirs(base_save_dir, exist_ok=True)
            self.hal_save_path_var.set(base_save_dir)
        
        # 创建带时间戳的子文件夹
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(base_save_dir, f"hal_dump_{timestamp}")
        
        try:
            self.hal_status_var.set("正在拉取录音文件...")
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取文件列表
            ls_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"获取文件列表失败: {result.stderr}")
            
            # 解析文件列表
            lines = result.stdout.strip().split('\n')
            files_to_pull = []
            
            for line in lines:
                if line.endswith('.pcm') or line.endswith('.raw'):
                    # 提取文件名
                    parts = line.split()
                    if len(parts) >= 8:
                        filename = parts[-1]
                        files_to_pull.append(filename)
            
            if not files_to_pull:
                self.update_info_text("未找到录音文件")
                self.hal_status_var.set("未找到录音文件")
                return
            
            # 拉取文件
            success_count = 0
            self.update_info_text(f"找到 {len(files_to_pull)} 个录音文件，开始拉取...")
            
            for filename in files_to_pull:
                self.update_info_text(f"正在拉取: {filename}")
                
                # 拉取文件
                pull_cmd = self.get_adb_command(f"pull {directory}/{filename} \"{os.path.join(save_dir, filename)}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                else:
                    self.update_info_text(f"拉取失败: {filename}")
            
            if success_count > 0:
                self.hal_status_var.set(f"成功拉取 {success_count} 个录音文件到 {save_dir}")
                self.update_info_text(f"成功拉取 {success_count} 个录音文件到:\n{save_dir}")
                
                # 打开保存目录
                if platform.system() == "Windows":
                    os.startfile(save_dir)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", save_dir])
                else:  # Linux
                    subprocess.run(["xdg-open", save_dir])
            else:
                self.hal_status_var.set("未成功拉取任何文件")
                self.update_info_text("未成功拉取任何文件")
        
        except Exception as e:
            self.hal_status_var.set(f"拉取文件出错: {str(e)}")
            self.update_info_text(f"拉取文件出错: {str(e)}")

    def update_info_text(self, message):
        """更新信息文本框"""
        self.hal_info_text.config(state="normal")
        self.hal_info_text.insert("end", message + "\n")
        self.hal_info_text.see("end")  # 滚动到底部
        self.hal_info_text.config(state="disabled")

    def update_device_status_color(self, color):
        """更新设备状态标签的颜色"""
        # 查找设备状态标签并更新颜色
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Label) and hasattr(widget, 'cget') and widget.cget("textvariable") == str(self.device_status_var):
                widget.configure(foreground=color)
                return

    def auto_create_hal_dir(self):
        """自动创建HAL录音目录"""
        try:
            directory = "data/vendor/audiohal"
            
            # 检查目录是否存在
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            # 如果目录不存在，则创建
            if result.returncode != 0 or "No such file or directory" in result.stderr:
                # 创建目录
                mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
                subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
                
                # 设置权限
                chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
                subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
                
                if hasattr(self, 'hal_status_var') and hasattr(self, 'update_info_text'):
                    self.hal_status_var.set(f"已自动创建录音目录: {directory}")
                    self.update_info_text(f"已自动创建录音目录: {directory}")
        except Exception as e:
            print(f"自动创建HAL录音目录出错: {str(e)}")

    def ensure_hal_dir(self, directory):
        """确保HAL录音目录存在"""
        try:
            # 检查目录是否存在
            check_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            # 如果目录不存在，则创建
            if result.returncode != 0 or "No such file or directory" in result.stderr:
                self.update_info_text(f"目录 {directory} 不存在，正在创建...")
                
                # 创建目录
                mkdir_cmd = self.get_adb_command(f"shell mkdir -p {directory}")
                mkdir_result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
                
                if mkdir_result.returncode != 0:
                    raise Exception(f"创建目录失败: {mkdir_result.stderr}")
                
                # 设置权限
                chmod_cmd = self.get_adb_command(f"shell chmod 777 {directory}")
                chmod_result = subprocess.run(chmod_cmd, shell=True, capture_output=True, text=True)
                
                if chmod_result.returncode != 0:
                    raise Exception(f"设置目录权限失败: {chmod_result.stderr}")
                
                self.update_info_text(f"已成功创建目录: {directory}")
            else:
                self.update_info_text(f"目录 {directory} 已存在")
            
            return True
        except Exception as e:
            self.update_info_text(f"确保目录存在时出错: {str(e)}")
            messagebox.showerror("错误", f"确保录音目录存在时出错:\n{str(e)}")
            return False

    def setup_screenshot_tab(self, parent):
        """设置截图功能选项卡"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 创建上下两栏布局
        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", pady=5)
        
        bottom_frame = ttk.Frame(frame)
        bottom_frame.pack(fill="both", expand=True, pady=5)
        
        # 上部 - 控制区域
        control_frame = ttk.LabelFrame(top_frame, text="截图控制", padding=5)
        control_frame.pack(fill="x", expand=True)
        
        # 保存路径设置
        save_path_frame = ttk.Frame(control_frame)
        save_path_frame.pack(fill="x", pady=2)
        
        ttk.Label(save_path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 设置默认保存路径为当前目录下的screenshots文件夹
        default_save_path = os.path.join(os.getcwd(), "screenshots")
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path, exist_ok=True)
        
        self.screenshot_save_path_var = tk.StringVar(value=default_save_path)
        save_path_entry = ttk.Entry(save_path_frame, textvariable=self.screenshot_save_path_var, font=("Arial", 9))
        save_path_entry.pack(side="left", fill="x", expand=True, padx=2)
        
        browse_save_button = ttk.Button(save_path_frame, text="浏览", 
                                      command=self.browse_screenshot_save_path, width=5, style="Small.TButton")
        browse_save_button.pack(side="right", padx=2)
        
        # 截图按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)
        
        self.screenshot_button = ttk.Button(button_frame, text="截取屏幕", 
                                     command=self.take_screenshot, width=15, style="TButton")
        self.screenshot_button.pack(side="left", padx=5)
        
        self.open_folder_button = ttk.Button(button_frame, text="打开文件夹", 
                                      command=self.open_screenshot_folder, width=15, style="TButton")
        self.open_folder_button.pack(side="right", padx=5)
        
        # 下部 - 信息区域
        info_frame = ttk.LabelFrame(bottom_frame, text="截图信息", padding=5)
        info_frame.pack(fill="both", expand=True)
        
        # 信息文本框
        self.screenshot_info_text = tk.Text(info_frame, height=10, font=("Arial", 9), wrap="word")
        self.screenshot_info_text.pack(fill="both", expand=True, pady=2)
        self.screenshot_info_text.insert("1.0", "截图信息将显示在这里...\n")
        self.screenshot_info_text.config(state="disabled")
        
        # 底部状态显示
        self.screenshot_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.screenshot_status_var, font=("Arial", 9))
        status_label.pack(pady=2)
    
    def take_screenshot(self):
        """截取设备屏幕"""
        if not self.check_device_selected():
            return
    
        try:
            self.screenshot_status_var.set("正在截取屏幕...")
            self.update_screenshot_info("正在截取屏幕...")
            
            # 获取时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 确保保存目录存在
            save_dir = self.screenshot_save_path_var.get().strip()
            if not save_dir:
                save_dir = os.path.join(os.getcwd(), "screenshots")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 截图文件名
            filename = f"screenshot_{timestamp}.png"
            device_path = f"/sdcard/{filename}"
            local_path = os.path.join(save_dir, filename)
            
            # 在设备上截图
            screencap_cmd = self.get_adb_command(f"shell screencap -p {device_path}")
            result = subprocess.run(screencap_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"截图失败: {result.stderr}")
            
            # 拉取截图到本地
            pull_cmd = self.get_adb_command(f"pull {device_path} \"{local_path}\"")
            result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"拉取截图失败: {result.stderr}")
            
            # 删除设备上的临时文件
            rm_cmd = self.get_adb_command(f"shell rm {device_path}")
            subprocess.run(rm_cmd, shell=True)
            
            self.screenshot_status_var.set(f"截图已保存: {filename}")
            self.update_screenshot_info(f"截图已保存: {local_path}")
            
            # 打开截图文件夹
            self.open_screenshot_folder()
            
        except Exception as e:
            self.screenshot_status_var.set(f"截图出错: {str(e)}")
            self.update_screenshot_info(f"截图出错: {str(e)}")
            messagebox.showerror("错误", f"截图时出错:\n{str(e)}")

    def open_screenshot_folder(self):
        """打开截图保存文件夹"""
        save_dir = self.screenshot_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "screenshots")
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", save_dir])
            else:  # Linux
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.screenshot_status_var.set(f"打开文件夹出错: {str(e)}")
            self.update_screenshot_info(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def browse_screenshot_save_path(self):
        """浏览截图保存路径"""
        folder = filedialog.askdirectory(initialdir=self.screenshot_save_path_var.get())
        if folder:
            self.screenshot_save_path_var.set(folder)
            self.update_screenshot_info(f"已设置保存路径: {folder}")

    def update_screenshot_info(self, message):
        """更新截图信息文本框"""
        self.screenshot_info_text.config(state="normal")
        self.screenshot_info_text.insert("end", message + "\n")
        self.screenshot_info_text.see("end")  # 滚动到底部
        self.screenshot_info_text.config(state="disabled")

    def browse_screenrecord_save_path(self):
        """浏览屏幕录制保存路径"""
        folder = filedialog.askdirectory(initialdir=self.screenrecord_save_path_var.get())
        if folder:
            self.screenrecord_save_path_var.set(folder)
            self.update_screenrecord_info(f"已设置保存路径: {folder}")

    def update_screenrecord_info(self, message):
        """更新屏幕录制信息文本框"""
        self.screenrecord_info_text.config(state="normal")
        self.screenrecord_info_text.insert("end", message + "\n")
        self.screenrecord_info_text.see("end")  # 滚动到底部
        self.screenrecord_info_text.config(state="disabled")

    def start_screenrecord(self):
        """开始屏幕录制"""
        if not self.check_device_selected():
            return
    
        try:
            # 获取保存路径
            save_dir = self.screenrecord_save_path_var.get().strip()
            if not save_dir:
                save_dir = os.path.join(os.getcwd(), "screenrecords")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取Android版本
            version_cmd = self.get_adb_command("shell getprop ro.build.version.release")
            version_result = subprocess.run(version_cmd, shell=True, capture_output=True, text=True)
            
            android_version = "unknown"
            if version_result.returncode == 0:
                android_version = version_result.stdout.strip()
                self.update_screenrecord_info(f"检测到Android版本: {android_version}")
            
            # 更新状态
            self.screenrecord_status_var.set("正在准备录制...")
            self.update_screenrecord_info("正在准备录制屏幕...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_record_button.config(state="disabled")
            self.stop_record_button.config(state="normal")
            
            # 获取时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.screenrecord_filename = f"screenrecord_{timestamp}.mp4"
            
            # 使用UI自动化方式启动系统录屏
            self.update_screenrecord_info("尝试使用系统录屏功能...")
            
            # 方法1: 使用快速设置面板
            try:
                # 下拉通知栏两次以显示快速设置
                subprocess.run(self.get_adb_command("shell cmd statusbar expand-settings"), shell=True)
                time.sleep(1)
                
                # 查找并点击"屏幕录制"图标 (不同设备可能位置不同)
                # 这里我们尝试模拟在快速设置面板中滑动和点击
                # 注意: 这种方法高度依赖于设备UI布局，可能需要针对特定设备调整
                
                # 在快速设置面板中滑动查找屏幕录制按钮
                for i in range(3):  # 尝试滑动几次
                    # 点击可能的屏幕录制按钮位置
                    tap_cmd = self.get_adb_command("shell input tap 500 500")  # 示例坐标，需要调整
                    subprocess.run(tap_cmd, shell=True)
                    time.sleep(1)
                    
                    # 检查是否出现录制确认对话框
                    # 如果出现，点击开始录制按钮
                    tap_cmd = self.get_adb_command("shell input tap 500 700")  # 示例坐标，需要调整
                    subprocess.run(tap_cmd, shell=True)
                    time.sleep(1)
                    
                    # 如果没有找到，尝试滑动查找
                    swipe_cmd = self.get_adb_command("shell input swipe 500 500 200 500")
                    subprocess.run(swipe_cmd, shell=True)
                    time.sleep(1)
                
                self.update_screenrecord_info("已尝试启动系统录屏，请在设备上确认")
                
            except Exception as e:
                self.update_screenrecord_info(f"使用系统录屏失败: {str(e)}")
                
                # 回退到传统方法
                self.update_screenrecord_info("尝试使用adb screenrecord命令...")
                
                # 设置录制文件路径
                self.device_video_path = f"/sdcard/{self.screenrecord_filename}"
                
                # 获取录制时长
                try:
                    duration = int(self.screenrecord_duration_var.get().strip())
                    if duration < 0:
                        duration = 0
                    elif duration > 180:  # Android默认最大180秒
                        duration = 180
                        self.screenrecord_duration_var.set("180")
                except ValueError:
                    duration = 180
                    self.screenrecord_duration_var.set("180")
                
                # 构建录制命令
                cmd = self.get_adb_command(f"shell screenrecord {self.device_video_path}")
                if duration > 0:
                    cmd = self.get_adb_command(f"shell screenrecord --time-limit {duration} {self.device_video_path}")
                
                self.update_screenrecord_info(f"执行命令: {cmd}")
                
                # 启动录制进程
                self.screenrecord_process = subprocess.Popen(cmd, shell=True)
            
            # 记录开始时间
            self.screenrecord_start_time = time.time()
            
            # 启动计时器
            self.update_screenrecord_timer()
            
            # 更新状态
            self.screenrecord_status_var.set("正在录制...")
            self.update_screenrecord_info("录制已开始，请在设备上操作")
            
        except Exception as e:
            self.screenrecord_status_var.set(f"录制出错: {str(e)}")
            self.update_screenrecord_info(f"录制出错: {str(e)}")
            messagebox.showerror("错误", f"开始录制时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_record_button.config(state="normal")
            self.stop_record_button.config(state="disabled")

    def update_screenrecord_timer(self):
        """更新录制时间"""
        if hasattr(self, 'screenrecord_process') and self.screenrecord_process.poll() is None:
            # 计算已录制时间
            elapsed = time.time() - self.screenrecord_start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            
            # 更新时间显示
            self.screenrecord_time_var.set(f"{minutes:02d}:{seconds:02d}")
            
            # 每秒更新一次
            self.root.after(1000, self.update_screenrecord_timer)
        else:
            # 如果进程已结束，停止计时器
            if hasattr(self, 'screenrecord_process') and self.screenrecord_process.poll() is not None:
                self.stop_screenrecord()

    def stop_screenrecord(self):
        """停止屏幕录制"""
        try:
            self.update_screenrecord_info("正在停止录制...")
            
            # 尝试停止系统录屏
            try:
                # 点击状态栏中的录制通知
                subprocess.run(self.get_adb_command("shell cmd statusbar expand"), shell=True)
                time.sleep(1)
                
                # 点击停止按钮 (坐标需要根据设备调整)
                tap_cmd = self.get_adb_command("shell input tap 500 300")  # 示例坐标
                subprocess.run(tap_cmd, shell=True)
                time.sleep(1)
                
                # 如果出现保存对话框，点击保存
                tap_cmd = self.get_adb_command("shell input tap 500 700")  # 示例坐标
                subprocess.run(tap_cmd, shell=True)
                time.sleep(2)
                
                self.update_screenrecord_info("已尝试停止系统录屏，请在设备上确认")
                
            except Exception as e:
                self.update_screenrecord_info(f"停止系统录屏失败: {str(e)}")
                
                # 如果有传统录制进程，尝试停止它
                if hasattr(self, 'screenrecord_process') and self.screenrecord_process.poll() is None:
                    # 尝试多种方法停止录制进程
                    methods_tried = 0
                    max_methods = 3
                    
                    # 方法1: 使用按键事件发送CTRL+C
                    if methods_tried < max_methods and self.screenrecord_process.poll() is None:
                        methods_tried += 1
                        self.update_screenrecord_info("尝试方法1: 发送按键事件...")
                        try:
                            stop_cmd = self.get_adb_command("shell input keyevent KEYCODE_CTRL_LEFT KEYCODE_C")
                            subprocess.run(stop_cmd, shell=True, timeout=2)
                            
                            # 等待进程结束
                            for i in range(3):  # 等待3秒
                                if self.screenrecord_process.poll() is not None:
                                    self.update_screenrecord_info("方法1成功: 进程已终止")
                                    break
                                time.sleep(1)
                        except:
                            self.update_screenrecord_info("方法1失败")
                    
                    # 方法2: 使用killall命令
                    if methods_tried < max_methods and self.screenrecord_process.poll() is None:
                        methods_tried += 1
                        self.update_screenrecord_info("尝试方法2: 使用killall命令...")
                        try:
                            kill_cmd = self.get_adb_command("shell killall screenrecord")
                            subprocess.run(kill_cmd, shell=True, timeout=2)
                            
                            # 等待进程结束
                            for i in range(3):  # 等待3秒
                                if self.screenrecord_process.poll() is not None:
                                    self.update_screenrecord_info("方法2成功: 进程已终止")
                                    break
                                time.sleep(1)
                        except:
                            self.update_screenrecord_info("方法2失败")
                    
                    # 方法3: 强制终止本地进程
                    if methods_tried < max_methods and self.screenrecord_process.poll() is None:
                        methods_tried += 1
                        self.update_screenrecord_info("尝试方法3: 强制终止本地进程...")
                        try:
                            if platform.system() == "Windows":
                                subprocess.run(f"taskkill /F /PID {self.screenrecord_process.pid}", shell=True)
                            else:
                                import signal
                                os.kill(self.screenrecord_process.pid, signal.SIGTERM)
                            
                            # 等待进程结束
                            for i in range(3):  # 等待3秒
                                if self.screenrecord_process.poll() is not None:
                                    self.update_screenrecord_info("方法3成功: 进程已终止")
                                    break
                                time.sleep(1)
                        except:
                            self.update_screenrecord_info("方法3失败")
            
            # 等待一段时间，让设备保存录制文件
            self.update_screenrecord_info("等待设备保存录制文件...")
            time.sleep(3)
            
            # 查找最近创建的视频文件
            self.update_screenrecord_info("查找录制文件...")
            find_cmd = self.get_adb_command("shell find /sdcard -name \"*.mp4\" -mtime -1")
            find_result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
            
            if find_result.returncode == 0 and find_result.stdout.strip():
                # 找到了最近创建的视频文件
                found_files = find_result.stdout.strip().split('\n')
                
                # 显示找到的文件
                self.update_screenrecord_info(f"找到 {len(found_files)} 个最近创建的视频文件:")
                for i, file in enumerate(found_files):
                    self.update_screenrecord_info(f"{i+1}. {file}")
                
                # 使用最近的文件
                self.device_video_path = found_files[0]
                self.screenrecord_filename = os.path.basename(self.device_video_path)
                self.update_screenrecord_info(f"选择文件: {self.device_video_path}")
                
                # 获取文件大小
                size_cmd = self.get_adb_command(f"shell stat -c %s {self.device_video_path}")
                size_result = subprocess.run(size_cmd, shell=True, capture_output=True, text=True)
                
                if size_result.returncode == 0:
                    try:
                        file_size = int(size_result.stdout.strip())
                        self.update_screenrecord_info(f"文件大小: {file_size/1024/1024:.2f} MB")
                    except:
                        self.update_screenrecord_info("无法获取文件大小")
                
                # 拉取视频文件
                save_dir = self.screenrecord_save_path_var.get().strip()
                if not save_dir:
                    save_dir = os.path.join(os.getcwd(), "screenrecords")
                
                os.makedirs(save_dir, exist_ok=True)
                local_path = os.path.join(save_dir, self.screenrecord_filename)
                
                self.update_screenrecord_info(f"正在从设备拉取视频: {self.device_video_path}")
                pull_cmd = self.get_adb_command(f"pull {self.device_video_path} \"{local_path}\"")
                pull_result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if pull_result.returncode == 0:
                    self.update_screenrecord_info(f"视频已保存到: {local_path}")
                    
                    # 打开视频文件夹
                    self.open_screenrecord_folder()
                else:
                    self.update_screenrecord_info(f"拉取视频失败: {pull_result.stderr}")
            else:
                self.update_screenrecord_info("未找到最近创建的视频文件")
            
            # 恢复按钮状态
            self.start_record_button.config(state="normal")
            self.stop_record_button.config(state="disabled")
            
            # 更新状态
            self.screenrecord_status_var.set("录制已停止")
            
        except Exception as e:
            self.screenrecord_status_var.set(f"停止录制出错: {str(e)}")
            self.update_screenrecord_info(f"停止录制出错: {str(e)}")
            messagebox.showerror("错误", f"停止录制时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_record_button.config(state="normal")
            self.stop_record_button.config(state="disabled")

    def open_screenrecord_folder(self):
        """打开屏幕录制保存文件夹"""
        save_dir = self.screenrecord_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "screenrecords")
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", save_dir])
            else:  # Linux
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.screenrecord_status_var.set(f"打开文件夹出错: {str(e)}")
            self.update_screenrecord_info(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def update_sweep_file_options(self):
        """更新扫频文件选项"""
        sweep_type = self.sweep_type_var.get()
        
        # 清空当前选项
        self.sweep_file_combobox['values'] = []
        self.sweep_file_var.set("")
        
        # 根据选择的类型更新文件列表
        if sweep_type == "elephant":
            # 禁用添加文件按钮
            self.add_custom_sweep_button.config(state="disabled")
            
            # 查找audio目录下的大象扫频文件
            elephant_dir = os.path.join(os.getcwd(), "audio", "elephant")
            if not os.path.exists(elephant_dir):
                os.makedirs(elephant_dir, exist_ok=True)
            
            # 获取所有wav文件
            elephant_files = [f for f in os.listdir(elephant_dir) if f.lower().endswith('.wav')]
            
            if elephant_files:
                self.sweep_file_combobox['values'] = elephant_files
                self.sweep_file_var.set(elephant_files[0])
                self.update_sweep_info(f"已加载 {len(elephant_files)} 个大象扫频文件")
            else:
                self.update_sweep_info("未找到大象扫频文件，请在audio/elephant目录中添加.wav文件")
        
        else:  # custom
            # 启用添加文件按钮
            self.add_custom_sweep_button.config(state="normal")
            
            # 查找audio目录下的自定义扫频文件
            custom_dir = os.path.join(os.getcwd(), "audio", "custom")
            if not os.path.exists(custom_dir):
                os.makedirs(custom_dir, exist_ok=True)
            
            # 获取所有音频文件
            custom_files = [f for f in os.listdir(custom_dir) if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg'))]
            
            if custom_files:
                self.sweep_file_combobox['values'] = custom_files
                self.sweep_file_var.set(custom_files[0])
                self.update_sweep_info(f"已加载 {len(custom_files)} 个自定义扫频文件")
            else:
                self.update_sweep_info("未找到自定义扫频文件，请点击'添加文件'按钮添加")

    def update_sweep_info(self, message):
        """更新扫频测试信息文本框"""
        self.sweep_info_text.config(state="normal")
        self.sweep_info_text.insert("end", f"{message}\n")
        self.sweep_info_text.see("end")
        self.sweep_info_text.config(state="disabled")
        self.root.update()

    def add_custom_sweep_file(self):
        """添加自定义扫频文件"""
        file_types = [
            ('音频文件', '*.wav;*.mp3;*.flac;*.ogg'),
            ('WAV文件', '*.wav'),
            ('MP3文件', '*.mp3'),
            ('FLAC文件', '*.flac'),
            ('OGG文件', '*.ogg'),
            ('所有文件', '*.*')
        ]
        
        files = filedialog.askopenfilenames(
            title="选择扫频音频文件",
            filetypes=file_types
        )
        
        if not files:
            return
        
        # 确保自定义目录存在
        custom_dir = os.path.join(os.getcwd(), "audio", "custom")
        if not os.path.exists(custom_dir):
            os.makedirs(custom_dir, exist_ok=True)
        
        # 复制文件到自定义目录
        copied_files = []
        for file in files:
            filename = os.path.basename(file)
            dest_path = os.path.join(custom_dir, filename)
            
            try:
                shutil.copy2(file, dest_path)
                copied_files.append(filename)
            except Exception as e:
                self.update_sweep_info(f"复制文件 {filename} 失败: {str(e)}")
        
        if copied_files:
            self.update_sweep_info(f"已添加 {len(copied_files)} 个自定义扫频文件")
            
            # 更新文件列表
            self.update_sweep_file_options()

    def browse_sweep_save_path(self):
        """浏览扫频测试保存路径"""
        folder = filedialog.askdirectory(initialdir=self.sweep_save_path_var.get())
        if folder:
            self.sweep_save_path_var.set(folder)
            self.update_sweep_info(f"已设置保存路径: {folder}")

    def start_sweep_test(self):
        """开始扫频测试"""
        if not self.check_device_selected():
            return
    
        try:
            # 获取选择的扫频文件
            sweep_type = self.sweep_type_var.get()
            sweep_file = self.sweep_file_var.get()
            
            if not sweep_file:
                messagebox.showerror("错误", "请选择扫频文件")
                return
            
            # 确定源文件路径
            if sweep_type == "elephant":
                source_path = os.path.join(os.getcwd(), "audio", "elephant", sweep_file)
            else:  # custom
                source_path = os.path.join(os.getcwd(), "audio", "custom", sweep_file)
            
            if not os.path.exists(source_path):
                messagebox.showerror("错误", f"文件不存在: {source_path}")
                return
            
            # 获取保存路径
            save_dir = self.sweep_save_path_var.get().strip()
            if not save_dir:
                save_dir = os.path.join(os.getcwd(), "sweep_recordings")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 更新状态
            self.sweep_status_var.set("正在准备测试...")
            self.update_sweep_info("正在准备扫频测试...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_sweep_button.config(state="disabled")
            self.stop_sweep_button.config(state="normal")
            
            # 准备工作 - 与Loopback测试相同
            subprocess.run(self.get_adb_command("root"), shell=True)
            
            # 重启audioserver - 与Loopback测试相同
            for _ in range(3):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
            
            # 获取时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 设置设备上的临时文件路径 - 直接使用原始文件名
            device_audio_path = f"/sdcard/{sweep_file}"
            
            # 推送音频文件到设备
            self.update_sweep_info(f"正在推送音频文件: {sweep_file}")
            push_cmd = self.get_adb_command(f"push \"{source_path}\" {device_audio_path}")
            result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"推送音频文件失败: {result.stderr}")
            
            # 设置录制文件名
            file_base_name = os.path.splitext(sweep_file)[0]  # 获取不带扩展名的文件名
            recording_filename = f"{file_base_name}_recording_{timestamp}.wav"
            device_recording_path = f"/sdcard/{recording_filename}"
            
            # 获取录制参数
            recording_device = self.sweep_recording_device_var.get().strip()
            recording_channels = self.sweep_recording_channels_var.get().strip()
            recording_rate = self.sweep_recording_rate_var.get().strip()
            recording_bits = self.sweep_recording_bits_var.get().strip()
            recording_duration = self.sweep_recording_duration_var.get().strip()
            
            # 开始录制
            self.update_sweep_info("开始录制...")
            self.sweep_status_var.set("正在录制...")
            
            # 使用与Loopback测试完全相同的命令格式
            tinycap_cmd = f"shell tinycap {device_recording_path} -d {recording_device} -c {recording_channels} -r {recording_rate} -b {recording_bits} -p 480"
            tinycap_full_cmd = self.get_adb_command(tinycap_cmd)
            self.update_sweep_info(f"执行命令: {tinycap_full_cmd}")
            self.tinycap_process = subprocess.Popen(tinycap_full_cmd, shell=True)
            
            # 等待录制启动
            time.sleep(2)
            
            # 播放音频
            self.update_sweep_info("开始播放音频...")
            playback_device = self.sweep_playback_device_var.get().strip()
            tinyplay_cmd = f"shell tinyplay {device_audio_path} -d {playback_device}"
            tinyplay_full_cmd = self.get_adb_command(tinyplay_cmd)
            self.update_sweep_info(f"执行命令: {tinyplay_full_cmd}")
            self.tinyplay_process = subprocess.Popen(tinyplay_full_cmd, shell=True)
            
            # 启动监控线程
            self.sweep_monitor_thread = threading.Thread(target=self.monitor_sweep_test, 
                                                      args=(device_recording_path, save_dir, recording_filename, sweep_file, float(recording_duration), device_audio_path))
            self.sweep_monitor_thread.daemon = True
            self.sweep_monitor_thread.start()
            
        except Exception as e:
            self.sweep_status_var.set(f"测试出错: {str(e)}")
            self.update_sweep_info(f"测试出错: {str(e)}")
            messagebox.showerror("错误", f"开始扫频测试时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")

    def stop_sweep_test(self):
        """停止扫频测试"""
        try:
            self.update_sweep_info("正在停止测试...")
            
            # 停止播放进程
            if hasattr(self, 'tinyplay_process') and self.tinyplay_process.poll() is None:
                # 使用killall命令停止tinyplay
                kill_cmd = self.get_adb_command("shell killall tinyplay")
                subprocess.run(kill_cmd, shell=True)
                
                # 等待进程结束
                for i in range(5):
                    if self.tinyplay_process.poll() is not None:
                        break
                    time.sleep(0.5)
                
                # 如果进程仍在运行，强制终止
                if self.tinyplay_process.poll() is None:
                    if platform.system() == "Windows":
                        subprocess.run(f"taskkill /F /PID {self.tinyplay_process.pid}", shell=True)
                    else:
                        import signal
                        os.kill(self.tinyplay_process.pid, signal.SIGTERM)
                
                self.update_sweep_info("已停止播放")
            
            # 停止录制进程
            if hasattr(self, 'tinycap_process') and self.tinycap_process.poll() is None:
                # 使用killall命令停止tinycap
                kill_cmd = self.get_adb_command("shell killall tinycap")
                subprocess.run(kill_cmd, shell=True)
                
                # 等待进程结束
                for i in range(5):
                    if self.tinycap_process.poll() is not None:
                        break
                    time.sleep(0.5)
                
                # 如果进程仍在运行，强制终止
                if self.tinycap_process.poll() is None:
                    if platform.system() == "Windows":
                        subprocess.run(f"taskkill /F /PID {self.tinycap_process.pid}", shell=True)
                    else:
                        import signal
                        os.kill(self.tinycap_process.pid, signal.SIGTERM)
                
                self.update_sweep_info("已停止录制")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")
            
            # 更新状态
            self.sweep_status_var.set("测试已停止")
            self.update_sweep_info("扫频测试已手动停止")
            
        except Exception as e:
            self.sweep_status_var.set(f"停止测试出错: {str(e)}")
            self.update_sweep_info(f"停止测试出错: {str(e)}")
            messagebox.showerror("错误", f"停止扫频测试时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")

    def monitor_sweep_test(self, device_recording_path, save_dir, recording_filename, original_filename, recording_duration, device_audio_path):
        """监控扫频测试进程"""
        try:
            # 等待播放进程结束
            if hasattr(self, 'tinyplay_process'):
                self.update_sweep_info("等待播放完成...")
                self.tinyplay_process.wait()
                self.update_sweep_info("播放已完成")
            
            # 等待一段时间确保录制完整
            time.sleep(2)
            
            # 停止录制进程
            if hasattr(self, 'tinycap_process') and self.tinycap_process.poll() is None:
                self.update_sweep_info("正在停止录制...")
                
                # 使用killall命令停止tinycap
                kill_cmd = self.get_adb_command("shell killall tinycap")
                subprocess.run(kill_cmd, shell=True)
                
                # 等待进程结束
                for i in range(5):
                    if self.tinycap_process.poll() is not None:
                        break
                    time.sleep(1)
                
                self.update_sweep_info("录制已停止")
            
            # 等待一段时间确保文件写入完成
            time.sleep(2)
            
            # 拉取录制文件
            self.update_sweep_info("正在获取录制文件...")
            local_path = os.path.join(save_dir, recording_filename)
            
            pull_cmd = self.get_adb_command(f"pull {device_recording_path} \"{local_path}\"")
            result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.update_sweep_info(f"拉取录制文件失败: {result.stderr}")
                
                # 尝试查找可能的录制文件
                find_cmd = self.get_adb_command("shell find /data/local/tmp -name \"*.wav\" -mtime -1")
                find_result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
                
                if find_result.stdout.strip():
                    found_files = find_result.stdout.strip().split("\n")
                    self.update_sweep_info(f"找到可能的录制文件: {found_files}")
                    
                    # 使用第一个找到的文件
                    if found_files:
                        device_recording_path = found_files[0]
                        self.update_sweep_info(f"尝试使用文件: {device_recording_path}")
                        
                        # 再次尝试拉取
                        pull_cmd = self.get_adb_command(f"pull {device_recording_path} \"{local_path}\"")
                        result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                        
                        if result.returncode != 0:
                            self.update_sweep_info(f"再次拉取录制文件失败: {result.stderr}")
                            return
                else:
                    self.update_sweep_info("未找到任何最近创建的WAV文件")
                    return
            
            # 检查文件大小
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                self.update_sweep_info(f"录制文件大小: {file_size/1024:.2f} KB")
                
                if file_size < 1000:  # 小于1KB的文件可能是空的
                    self.update_sweep_info("警告: 录制文件可能为空或损坏")
            
            # 删除设备上的临时文件
            self.update_sweep_info("正在清理临时文件...")
            rm_cmd = self.get_adb_command(f"shell rm {device_recording_path}")
            subprocess.run(rm_cmd, shell=True)
            
            rm_audio_cmd = self.get_adb_command(f"shell rm {device_audio_path}")
            subprocess.run(rm_audio_cmd, shell=True)
            
            # 更新状态
            self.sweep_status_var.set("测试完成")
            self.update_sweep_info(f"扫频测试完成，录制文件已保存到: {local_path}")
            
            # 如果是批量测试模式，检查是否有更多文件需要测试
            if self.sweep_batch_var.get():
                # 获取当前文件列表
                if self.sweep_type_var.get() == "elephant":
                    files_dir = os.path.join(os.getcwd(), "audio", "elephant")
                else:
                    files_dir = os.path.join(os.getcwd(), "audio", "custom")
                
                audio_files = [f for f in os.listdir(files_dir) if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg'))]
                
                # 找到当前文件的索引
                try:
                    current_index = audio_files.index(original_filename)
                    
                    # 如果还有下一个文件
                    if current_index < len(audio_files) - 1:
                        next_file = audio_files[current_index + 1]
                        self.update_sweep_info(f"准备测试下一个文件: {next_file}")
                        
                        # 设置下一个文件
                        self.sweep_file_var.set(next_file)
                        
                        # 等待一段时间后开始下一个测试
                        time.sleep(2)
                        
                        # 启动下一个测试
                        self.root.after(1000, self.start_sweep_test)
                        return
                    else:
                        self.update_sweep_info("所有文件测试完成")
                except ValueError:
                    pass  # 如果找不到当前文件，就不继续测试
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")
            
        except Exception as e:
            self.sweep_status_var.set(f"监控测试出错: {str(e)}")
            self.update_sweep_info(f"监控测试出错: {str(e)}")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")

    def open_sweep_folder(self):
        """打开扫频测试保存文件夹"""
        save_dir = self.sweep_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "sweep_recordings")
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", save_dir])
            else:  # Linux
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.sweep_status_var.set(f"打开文件夹出错: {str(e)}")
            self.update_sweep_info(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def setup_speaker_tab(self, parent):
        """设置喇叭测试选项卡"""
        # 创建框架
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建标题
        ttk.Label(frame, text="喇叭测试", style="Header.TLabel").pack(pady=10)
        
        # 创建说明
        ttk.Label(frame, text="此功能将打开系统喇叭测试工具，并可以选择使用默认或自定义的测试音频文件。", 
                 wraplength=600).pack(pady=10)
        
        # 音频文件选择区域
        audio_frame = ttk.LabelFrame(frame, text="测试音频")
        audio_frame.pack(fill="x", padx=10, pady=10)
        
        # 音频源选择
        source_frame = ttk.Frame(audio_frame)
        source_frame.pack(fill="x", padx=10, pady=5)
        
        self.speaker_audio_source = tk.StringVar(value="default")
        
        # 默认音频选项
        default_radio = ttk.Radiobutton(source_frame, text="使用默认测试音频", 
                                  variable=self.speaker_audio_source, value="default",
                                  command=self.update_speaker_audio_source)
        default_radio.pack(anchor="w", padx=5, pady=5)
        
        # 自定义音频选项
        custom_radio = ttk.Radiobutton(source_frame, text="使用自定义音频文件", 
                                 variable=self.speaker_audio_source, value="custom",
                                 command=self.update_speaker_audio_source)
        custom_radio.pack(anchor="w", padx=5, pady=5)
        
        # 自定义音频选择框架
        custom_audio_frame = ttk.Frame(audio_frame)
        custom_audio_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(custom_audio_frame, text="音频文件:").pack(side="left", padx=5)
        
        self.speaker_audio_var = tk.StringVar()
        self.speaker_audio_entry = ttk.Entry(custom_audio_frame, textvariable=self.speaker_audio_var, width=40)
        self.speaker_audio_entry.pack(side="left", padx=5)
        self.speaker_audio_entry.config(state="disabled")
        
        self.speaker_browse_button = ttk.Button(custom_audio_frame, text="浏览", 
                                         command=self.browse_speaker_audio,
                                         style="Small.TButton")
        self.speaker_browse_button.pack(side="left", padx=5)
        self.speaker_browse_button.config(state="disabled")
        
        # 默认音频文件状态
        default_status_frame = ttk.Frame(audio_frame)
        default_status_frame.pack(fill="x", padx=10, pady=5)
        
        self.default_audio_status_var = tk.StringVar()
        self.check_default_audio_file()  # 检查默认音频文件是否存在
        
        default_status_label = ttk.Label(default_status_frame, textvariable=self.default_audio_status_var,
                                       foreground="blue")
        default_status_label.pack(anchor="w", padx=5)
        
        # 添加默认音频文件按钮
        self.add_default_audio_button = ttk.Button(default_status_frame, text="添加默认音频文件", 
                                                command=self.add_default_audio_file,
                                                style="Small.TButton")
        self.add_default_audio_button.pack(side="left", padx=5)
        if os.path.exists(os.path.join(os.getcwd(), "audio", "speaker", "test.wav")):
            self.add_default_audio_button.config(state="disabled")
        
        # 状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", padx=10, pady=10)
        
        self.speaker_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(status_frame, textvariable=self.speaker_status_var)
        status_label.pack(side="left", padx=5)
        
        # 操作按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)
        
        self.start_speaker_button = ttk.Button(button_frame, text="启动喇叭测试", 
                                            command=self.start_speaker_test)
        self.start_speaker_button.pack(side="left", padx=10)

    def check_default_audio_file(self):
        """检查默认音频文件是否存在"""
        default_audio_path = os.path.join(os.getcwd(), "audio", "speaker", "test.wav")
        if os.path.exists(default_audio_path):
            self.default_audio_status_var.set("默认音频文件已存在")
            if hasattr(self, 'add_default_audio_button'):
                self.add_default_audio_button.config(state="disabled")
        else:
            self.default_audio_status_var.set("默认音频文件不存在，请添加默认音频文件或使用自定义音频")
            if hasattr(self, 'add_default_audio_button'):
                self.add_default_audio_button.config(state="normal")

    def add_default_audio_file(self):
        """添加默认音频文件"""
        file_path = filedialog.askopenfilename(
            title="选择默认音频文件",
            filetypes=[("WAV文件", "*.wav")]
        )
        if file_path:
            # 确保目录存在
            speaker_dir = os.path.join(os.getcwd(), "audio", "speaker")
            if not os.path.exists(speaker_dir):
                os.makedirs(speaker_dir, exist_ok=True)
            
            # 复制文件
            try:
                shutil.copy(file_path, os.path.join(speaker_dir, "test.wav"))
                messagebox.showinfo("成功", "默认音频文件已添加")
                self.check_default_audio_file()
            except Exception as e:
                messagebox.showerror("错误", f"添加默认音频文件失败:\n{str(e)}")

    def update_speaker_audio_source(self):
        """更新喇叭测试音频源"""
        if self.speaker_audio_source.get() == "default":
            self.speaker_audio_entry.config(state="disabled")
            self.speaker_browse_button.config(state="disabled")
        else:  # custom
            self.speaker_audio_entry.config(state="normal")
            self.speaker_browse_button.config(state="normal")

    def browse_speaker_audio(self):
        """浏览选择喇叭测试音频文件"""
        file_path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("音频文件", "*.wav *.mp3 *.ogg *.flac")]
        )
        if file_path:
            self.speaker_audio_var.set(file_path)

    def start_speaker_test(self):
        """启动喇叭测试"""
        if not self.check_device_selected():
            return
    
        try:
            self.speaker_status_var.set("正在准备喇叭测试...")
            
            # 确定要推送的音频文件
            if self.speaker_audio_source.get() == "default":
                # 使用默认测试音频
                audio_file = os.path.join(os.getcwd(), "audio", "speaker", "test.wav")
                if not os.path.exists(audio_file):
                    messagebox.showerror("错误", "默认测试音频文件不存在，请先添加默认音频文件或选择使用自定义音频")
                    self.speaker_status_var.set("错误: 默认测试音频文件不存在")
                    return
            else:  # custom
                # 使用自定义音频
                audio_file = self.speaker_audio_var.get().strip()
                if not audio_file or not os.path.exists(audio_file):
                    messagebox.showerror("错误", "请选择有效的音频文件")
                    self.speaker_status_var.set("错误: 请选择有效的音频文件")
                    return
            
            # 推送音频文件到设备
            self.speaker_status_var.set("正在推送音频文件...")
            push_cmd = self.get_adb_command(f"push \"{audio_file}\" /sdcard/test.wav")
            result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"推送音频文件失败: {result.stderr}")
            
            # 启动喇叭测试应用
            self.speaker_status_var.set("正在启动喇叭测试应用...")
            launch_cmd = self.get_adb_command("shell am start -n com.nes.sound/.component.activity.SoundLocateActivity")
            result = subprocess.run(launch_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"启动喇叭测试应用失败: {result.stderr}")
            
            self.speaker_status_var.set("喇叭测试已启动")
            
        except Exception as e:
            self.speaker_status_var.set(f"测试出错: {str(e)}")
            messagebox.showerror("错误", f"启动喇叭测试时出错:\n{str(e)}")

    def setup_logcat_tab(self, parent):
        """设置Logcat选项卡"""
        # 创建框架
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建标题
        ttk.Label(frame, text="音频日志控制", style="Header.TLabel").pack(pady=10)
        
        # 左右分栏布局
        main_frame = ttk.Frame(frame)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 左侧属性管理区域 - 设置宽度为40%
        left_frame = ttk.Frame(main_frame, width=320)
        left_frame.pack(side="left", fill="both", padx=5, pady=5)
        left_frame.pack_propagate(False)  # 防止子组件改变frame大小
        
        # 右侧日志控制区域 - 设置宽度为60%
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        
        # 左侧 - 属性管理
        props_frame = ttk.LabelFrame(left_frame, text="logcat属性管理")
        props_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 属性输入区域
        input_frame = ttk.Frame(props_frame)
        input_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(input_frame, text="属性:", font=("Arial", 9)).pack(side="left", padx=5)
        self.logcat_prop_var = tk.StringVar()
        prop_entry = ttk.Entry(input_frame, textvariable=self.logcat_prop_var, width=20)
        prop_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        add_button = ttk.Button(input_frame, text="添加", 
                              command=self.add_logcat_prop, style="Small.TButton",
                              width=4)
        add_button.pack(side="left", padx=5)
        
        # 属性列表区域 - 使用Canvas和Scrollbar
        canvas_frame = ttk.Frame(props_frame)
        canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建Canvas和Scrollbar
        self.logcat_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.logcat_canvas.yview)
        self.logcat_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.logcat_canvas.pack(side="left", fill="both", expand=True)
        
        # 创建属性列表框架
        self.logcat_props_frame = ttk.Frame(self.logcat_canvas)
        self.logcat_canvas_window = self.logcat_canvas.create_window((0, 0), window=self.logcat_props_frame, anchor="nw")
        
        # 配置Canvas滚动
        self.logcat_props_frame.bind("<Configure>", lambda e: self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all")))
        self.logcat_canvas.bind("<Configure>", self.resize_logcat_props_frame)
        
        # 定义默认属性列表
        self.logcat_props = [
            {"name": "sys.droidlogic.audio.debug", "debug_value": "1", "normal_value": "0"},
            {"name": "vendor.media.audio.hal.debug", "debug_value": "4096", "normal_value": "0"},
            {"name": "media.audio.hal.debug", "debug_value": "4096", "normal_value": "0"},
            {"name": "vendor.media.audiohal.debug", "debug_value": "4096", "normal_value": "0"},
            {"name": "vendor.media.audiohal.hwsync", "debug_value": "1", "normal_value": "0"},
            {"name": "vendor.media.c2.audio.decoder.debug", "debug_value": "1", "normal_value": "0"},
            {"name": "vendor.media.omx.audio.dump", "debug_value": "1", "normal_value": "0"},
            {"name": "vendor.media.droidaudio.debug", "debug_value": "1", "normal_value": "0"},
            {"name": "log.tag.APM_AudioPolicyManager", "debug_value": "V", "normal_value": "D"}
        ]
        
        # 创建属性列表
        self.logcat_props_vars = []
        self.logcat_prop_frames = []
        
        # 添加默认属性到列表
        for prop in self.logcat_props:
            self.add_prop_to_list(prop["name"])
        
        # 右侧 - 日志控制
        control_frame = ttk.LabelFrame(right_frame, text="日志控制")
        control_frame.pack(fill="both", expand=False, padx=5, pady=5)
        
        # 日志保存路径
        path_frame = ttk.Frame(control_frame)
        path_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(path_frame, text="保存路径:", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.logcat_save_path_var = tk.StringVar(value=os.path.join(os.getcwd(), "logcat"))
        path_entry = ttk.Entry(path_frame, textvariable=self.logcat_save_path_var)
        path_entry.pack(side="left", padx=2, fill="x", expand=True)
        
        browse_button = ttk.Button(path_frame, text="浏览", 
                                 command=self.browse_logcat_save_path,
                                 style="Small.TButton", width=4)
        browse_button.pack(side="left", padx=2)
        
        # 自动停止时间
        auto_stop_frame = ttk.Frame(control_frame)
        auto_stop_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(auto_stop_frame, text="自动停止(秒):", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.logcat_auto_stop_var = tk.StringVar(value="0")
        auto_stop_entry = ttk.Entry(auto_stop_frame, textvariable=self.logcat_auto_stop_var, width=5)
        auto_stop_entry.pack(side="left", padx=2)
        
        ttk.Label(auto_stop_frame, text="(0表示不自动停止)", font=("Arial", 9)).pack(side="left", padx=2)
        
        # 日志过滤器
        filter_frame = ttk.Frame(control_frame)
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(filter_frame, text="日志过滤:", font=("Arial", 9)).pack(side="left", padx=2)
        
        self.logcat_filter_var = tk.StringVar(value="*:V")
        filter_entry = ttk.Entry(filter_frame, textvariable=self.logcat_filter_var)
        filter_entry.pack(side="left", padx=2, fill="x", expand=True)
        
        # 操作按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", padx=5, pady=5)
        
        self.enable_debug_button = ttk.Button(button_frame, text="放开打印", 
                                            command=self.enable_logcat_debug,
                                            style="Small.TButton")
        self.enable_debug_button.pack(side="left", padx=5)
        
        self.disable_debug_button = ttk.Button(button_frame, text="停止打印", 
                                             command=self.disable_logcat_debug,
                                             style="Small.TButton")
        self.disable_debug_button.pack(side="left", padx=5)
        self.disable_debug_button.config(state="disabled")
        
        # 日志抓取按钮
        capture_frame = ttk.Frame(control_frame)
        capture_frame.pack(fill="x", padx=5, pady=5)
        
        self.start_capture_button = ttk.Button(capture_frame, text="开始抓取", 
                                             command=self.start_logcat_capture,
                                             style="Small.TButton")
        self.start_capture_button.pack(side="left", padx=5)
        
        self.stop_capture_button = ttk.Button(capture_frame, text="停止抓取", 
                                            command=self.stop_logcat_capture,
                                            style="Small.TButton")
        self.stop_capture_button.pack(side="left", padx=5)
        self.stop_capture_button.config(state="disabled")
        
        open_folder_button = ttk.Button(capture_frame, text="打开文件夹", 
                                      command=self.open_logcat_folder,
                                      style="Small.TButton")
        open_folder_button.pack(side="left", padx=5)
        
        # 状态显示
        status_frame = ttk.LabelFrame(right_frame, text="日志信息")
        status_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建文本框用于显示状态
        self.logcat_status_text = tk.Text(status_frame, height=10, width=40, font=("Arial", 9))
        self.logcat_status_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.logcat_status_text.config(state="disabled")
        
        # 初始状态信息
        self.update_logcat_status("就绪")

    def resize_logcat_props_frame(self, event):
        """调整属性列表框架大小"""
        self.logcat_canvas.itemconfig(self.logcat_canvas_window, width=event.width)

    def update_logcat_status(self, message):
        """更新日志状态信息"""
        self.logcat_status_text.config(state="normal")
        self.logcat_status_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.logcat_status_text.see(tk.END)
        self.logcat_status_text.config(state="disabled")

    def add_logcat_prop(self):
        """添加日志属性"""
        prop_name = self.logcat_prop_var.get().strip()
        if not prop_name:
            messagebox.showerror("错误", "请输入属性名")
            return
        
        # 检查是否已存在
        for prop in self.logcat_props_vars:
            if prop["name"] == prop_name:
                messagebox.showerror("错误", f"属性 {prop_name} 已存在")
                return
        
        # 添加到列表
        self.add_prop_to_list(prop_name)
        
        # 清空输入框
        self.logcat_prop_var.set("")
        
        self.update_logcat_status(f"已添加属性: {prop_name}")

    def add_prop_to_list(self, prop_name):
        """将属性添加到列表显示"""
        # 创建属性框架
        prop_frame = ttk.Frame(self.logcat_props_frame)
        prop_frame.pack(fill="x", padx=2, pady=1)
        
        # 复选框
        var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(prop_frame, variable=var, text="")
        check.pack(side="left", padx=1)
        
        # 属性名标签 - 使用更小的字体
        prop_label = ttk.Label(prop_frame, text=prop_name, font=("Arial", 9))
        prop_label.pack(side="left", padx=2, fill="x", expand=True)
        
        # 删除按钮
        delete_button = ttk.Button(prop_frame, text="×", width=1,
                                 command=lambda p=prop_name, f=prop_frame: self.remove_logcat_prop(p, f),
                                 style="Delete.TButton")
        delete_button.pack(side="right", padx=1)
        
        # 保存属性信息
        self.logcat_props_vars.append({
            "name": prop_name,
            "var": var,
            "frame": prop_frame
        })
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))

    def remove_logcat_prop(self, prop_name, frame):
        """从列表中移除属性"""
        # 从UI中移除
        frame.destroy()
        
        # 从数据中移除
        for i, prop in enumerate(self.logcat_props_vars):
            if prop["name"] == prop_name:
                self.logcat_props_vars.pop(i)
                break
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))
        
        self.update_logcat_status(f"已移除属性: {prop_name}")

    def enable_logcat_debug(self):
        """放开日志打印"""
        if not self.check_device_selected():
            return
        
        try:
            self.update_logcat_status("正在放开日志打印...")
            
            # 设置属性
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的调试值
                    debug_value = "1"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            debug_value = default_prop["debug_value"]
                            break
                    
                    cmd = self.get_adb_command(f"shell setprop {prop['name']} {debug_value}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"设置属性 {prop['name']} 失败: {result.stderr}")
                    
                    self.update_logcat_status(f"已设置: {prop['name']}={debug_value}")
            
            # 更新按钮状态
            self.enable_debug_button.config(state="disabled")
            self.disable_debug_button.config(state="normal")
            
            self.update_logcat_status("日志打印已放开")
            
        except Exception as e:
            self.update_logcat_status(f"放开日志打印出错: {str(e)}")
            messagebox.showerror("错误", f"放开日志打印时出错:\n{str(e)}")

    def disable_logcat_debug(self):
        """停止日志打印"""
        if not self.check_device_selected():
            return
        
        try:
            self.update_logcat_status("正在停止日志打印...")
            
            # 恢复属性
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的正常值
                    normal_value = "0"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            normal_value = default_prop["normal_value"]
                            break
                    
                    cmd = self.get_adb_command(f"shell setprop {prop['name']} {normal_value}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"恢复属性 {prop['name']} 失败: {result.stderr}")
                    
                    self.update_logcat_status(f"已恢复: {prop['name']}={normal_value}")
            
            # 更新按钮状态
            self.enable_debug_button.config(state="normal")
            self.disable_debug_button.config(state="disabled")
            
            self.update_logcat_status("日志打印已停止")
            
        except Exception as e:
            self.update_logcat_status(f"停止日志打印出错: {str(e)}")
            messagebox.showerror("错误", f"停止日志打印时出错:\n{str(e)}")

    def start_logcat_capture(self):
        """开始抓取日志"""
        if not self.check_device_selected():
            return
    
        try:
            self.update_logcat_status("正在开始抓取日志...")
            
            # 确保保存目录存在
            save_dir = self.logcat_save_path_var.get().strip()
            if not save_dir:
                save_dir = os.path.join(os.getcwd(), "logcat")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 生成日志文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.log_file_path = os.path.join(save_dir, f"audio_logcat_{timestamp}.txt")
            
            # 开始抓取日志
            filter_str = self.logcat_filter_var.get().strip()
            if not filter_str:
                filter_str = "*:V"
            
            logcat_cmd = self.get_adb_command(f"logcat -v threadtime {filter_str}")
            
            # 打开日志文件
            self.logcat_file = open(self.log_file_path, "w", encoding="utf-8")
            
            # 启动日志进程
            self.logcat_process = subprocess.Popen(logcat_cmd, shell=True, stdout=self.logcat_file, stderr=subprocess.PIPE, text=True)
            
            # 更新按钮状态
            self.start_capture_button.config(state="disabled")
            self.stop_capture_button.config(state="normal")
            
            self.update_logcat_status(f"正在抓取日志到: {self.log_file_path}")
            
            # 检查是否需要自动停止
            auto_stop_time = self.logcat_auto_stop_var.get().strip()
            if auto_stop_time and auto_stop_time != "0":
                try:
                    seconds = int(auto_stop_time)
                    if seconds > 0:
                        self.update_logcat_status(f"将在 {seconds} 秒后自动停止抓取")
                        self.root.after(seconds * 1000, self.stop_logcat_capture)
                except ValueError:
                    self.update_logcat_status("自动停止时间格式无效，将不会自动停止")
            
        except Exception as e:
            self.update_logcat_status(f"开始抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"开始抓取日志时出错:\n{str(e)}")

    def stop_logcat_capture(self):
        """停止抓取日志"""
        if not hasattr(self, 'logcat_process') or self.logcat_process is None:
            return
    
        try:
            self.update_logcat_status("正在停止抓取日志...")
            
            # 停止日志进程
            if platform.system() == "Windows":
                # 使用taskkill强制终止进程树
                subprocess.run(f"taskkill /F /T /PID {self.logcat_process.pid}", shell=True)
            else:
                import signal
                # 发送SIGTERM信号
                os.kill(self.logcat_process.pid, signal.SIGTERM)
                # 等待进程结束
                try:
                    self.logcat_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 如果超时，发送SIGKILL信号强制终止
                    os.kill(self.logcat_process.pid, signal.SIGKILL)
            
            # 关闭日志文件
            if hasattr(self, 'logcat_file') and self.logcat_file:
                self.logcat_file.close()
                self.logcat_file = None
            
            # 清理进程引用
            self.logcat_process = None
            
            # 更新按钮状态
            self.start_capture_button.config(state="normal")
            self.stop_capture_button.config(state="disabled")
            
            self.update_logcat_status("日志抓取已停止")
            
            # 询问是否打开日志文件
            if messagebox.askyesno("完成", "日志抓取已完成，是否打开日志文件夹？"):
                self.open_logcat_folder()
            
        except Exception as e:
            self.update_logcat_status(f"停止抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"停止抓取日志时出错:\n{str(e)}")

    def open_logcat_folder(self):
        """打开日志保存文件夹"""
        save_dir = self.logcat_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "logcat")
    
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
    
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", save_dir])
            else:  # Linux
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.logcat_status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def browse_logcat_save_path(self):
        """浏览并选择日志保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择日志保存路径",
            initialdir=self.logcat_save_path_var.get()
        )
        
        if folder_path:
            self.logcat_save_path_var.set(folder_path)
            self.update_logcat_status(f"已设置日志保存路径: {folder_path}")

    def resize_logcat_props_frame(self, event):
        """调整属性列表框架大小"""
        self.logcat_canvas.itemconfig(self.logcat_canvas_window, width=event.width)

    def update_logcat_status(self, message):
        """更新日志状态信息"""
        self.logcat_status_text.config(state="normal")
        self.logcat_status_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.logcat_status_text.see(tk.END)
        self.logcat_status_text.config(state="disabled")

    def add_logcat_prop(self):
        """添加日志属性"""
        prop_name = self.logcat_prop_var.get().strip()
        if not prop_name:
            messagebox.showerror("错误", "请输入属性名")
            return
        
        # 检查是否已存在
        for prop in self.logcat_props_vars:
            if prop["name"] == prop_name:
                messagebox.showerror("错误", f"属性 {prop_name} 已存在")
                return
        
        # 添加到列表
        self.add_prop_to_list(prop_name)
        
        # 清空输入框
        self.logcat_prop_var.set("")
        
        self.update_logcat_status(f"已添加属性: {prop_name}")

    def add_prop_to_list(self, prop_name):
        """将属性添加到列表显示"""
        # 创建属性框架
        prop_frame = ttk.Frame(self.logcat_props_frame)
        prop_frame.pack(fill="x", padx=2, pady=1)
        
        # 复选框
        var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(prop_frame, variable=var, text="")
        check.pack(side="left", padx=1)
        
        # 属性名标签 - 使用更小的字体
        prop_label = ttk.Label(prop_frame, text=prop_name, font=("Arial", 9))
        prop_label.pack(side="left", padx=2, fill="x", expand=True)
        
        # 删除按钮
        delete_button = ttk.Button(prop_frame, text="×", width=1,
                                 command=lambda p=prop_name, f=prop_frame: self.remove_logcat_prop(p, f),
                                 style="Delete.TButton")
        delete_button.pack(side="right", padx=1)
        
        # 保存属性信息
        self.logcat_props_vars.append({
            "name": prop_name,
            "var": var,
            "frame": prop_frame
        })
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))

    def remove_logcat_prop(self, prop_name, frame):
        """从列表中移除属性"""
        # 从UI中移除
        frame.destroy()
        
        # 从数据中移除
        for i, prop in enumerate(self.logcat_props_vars):
            if prop["name"] == prop_name:
                self.logcat_props_vars.pop(i)
                break
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))
        
        self.update_logcat_status(f"已移除属性: {prop_name}")

    def enable_logcat_debug(self):
        """放开日志打印"""
        if not self.check_device_selected():
            return
        
        try:
            self.update_logcat_status("正在放开日志打印...")
            
            # 设置属性
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的调试值
                    debug_value = "1"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            debug_value = default_prop["debug_value"]
                            break
                    
                    cmd = self.get_adb_command(f"shell setprop {prop['name']} {debug_value}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"设置属性 {prop['name']} 失败: {result.stderr}")
                    
                    self.update_logcat_status(f"已设置: {prop['name']}={debug_value}")
            
            # 更新按钮状态
            self.enable_debug_button.config(state="disabled")
            self.disable_debug_button.config(state="normal")
            
            self.update_logcat_status("日志打印已放开")
            
        except Exception as e:
            self.update_logcat_status(f"放开日志打印出错: {str(e)}")
            messagebox.showerror("错误", f"放开日志打印时出错:\n{str(e)}")

    def disable_logcat_debug(self):
        """停止日志打印"""
        if not self.check_device_selected():
            return
        
        try:
            self.update_logcat_status("正在停止日志打印...")
            
            # 恢复属性
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的正常值
                    normal_value = "0"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            normal_value = default_prop["normal_value"]
                            break
                    
                    cmd = self.get_adb_command(f"shell setprop {prop['name']} {normal_value}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"恢复属性 {prop['name']} 失败: {result.stderr}")
                    
                    self.update_logcat_status(f"已恢复: {prop['name']}={normal_value}")
            
            # 更新按钮状态
            self.enable_debug_button.config(state="normal")
            self.disable_debug_button.config(state="disabled")
            
            self.update_logcat_status("日志打印已停止")
            
        except Exception as e:
            self.update_logcat_status(f"停止日志打印出错: {str(e)}")
            messagebox.showerror("错误", f"停止日志打印时出错:\n{str(e)}")

    def start_logcat_capture(self):
        """开始抓取日志"""
        if not self.check_device_selected():
            return
    
        try:
            self.update_logcat_status("正在开始抓取日志...")
            
            # 确保保存目录存在
            save_dir = self.logcat_save_path_var.get().strip()
            if not save_dir:
                save_dir = os.path.join(os.getcwd(), "logcat")
            
            os.makedirs(save_dir, exist_ok=True)
            
            # 生成日志文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.log_file_path = os.path.join(save_dir, f"audio_logcat_{timestamp}.txt")
            
            # 开始抓取日志
            filter_str = self.logcat_filter_var.get().strip()
            if not filter_str:
                filter_str = "*:V"
            
            logcat_cmd = self.get_adb_command(f"logcat -v threadtime {filter_str}")
            
            # 打开日志文件
            self.logcat_file = open(self.log_file_path, "w", encoding="utf-8")
            
            # 启动日志进程
            self.logcat_process = subprocess.Popen(logcat_cmd, shell=True, stdout=self.logcat_file, stderr=subprocess.PIPE, text=True)
            
            # 更新按钮状态
            self.start_capture_button.config(state="disabled")
            self.stop_capture_button.config(state="normal")
            
            self.update_logcat_status(f"正在抓取日志到: {self.log_file_path}")
            
            # 检查是否需要自动停止
            auto_stop_time = self.logcat_auto_stop_var.get().strip()
            if auto_stop_time and auto_stop_time != "0":
                try:
                    seconds = int(auto_stop_time)
                    if seconds > 0:
                        self.update_logcat_status(f"将在 {seconds} 秒后自动停止抓取")
                        self.root.after(seconds * 1000, self.stop_logcat_capture)
                except ValueError:
                    self.update_logcat_status("自动停止时间格式无效，将不会自动停止")
            
        except Exception as e:
            self.update_logcat_status(f"开始抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"开始抓取日志时出错:\n{str(e)}")

    def stop_logcat_capture(self):
        """停止抓取日志"""
        if not hasattr(self, 'logcat_process') or self.logcat_process is None:
            return
    
        try:
            self.update_logcat_status("正在停止抓取日志...")
            
            # 停止日志进程
            if platform.system() == "Windows":
                # 使用taskkill强制终止进程树
                subprocess.run(f"taskkill /F /T /PID {self.logcat_process.pid}", shell=True)
            else:
                import signal
                # 发送SIGTERM信号
                os.kill(self.logcat_process.pid, signal.SIGTERM)
                # 等待进程结束
                try:
                    self.logcat_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 如果超时，发送SIGKILL信号强制终止
                    os.kill(self.logcat_process.pid, signal.SIGKILL)
            
            # 关闭日志文件
            if hasattr(self, 'logcat_file') and self.logcat_file:
                self.logcat_file.close()
                self.logcat_file = None
            
            # 清理进程引用
            self.logcat_process = None
            
            # 更新按钮状态
            self.start_capture_button.config(state="normal")
            self.stop_capture_button.config(state="disabled")
            
            self.update_logcat_status("日志抓取已停止")
            
            # 询问是否打开日志文件
            if messagebox.askyesno("完成", "日志抓取已完成，是否打开日志文件夹？"):
                self.open_logcat_folder()
            
        except Exception as e:
            self.update_logcat_status(f"停止抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"停止抓取日志时出错:\n{str(e)}")

    def open_logcat_folder(self):
        """打开日志保存文件夹"""
        save_dir = self.logcat_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "logcat")
    
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
    
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", save_dir])
            else:  # Linux
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.logcat_status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioTestTool(root)
    root.mainloop()