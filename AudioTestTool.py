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

class AudioTestTool:
    def __init__(self, root):
        self.root = root
        self.root.title("音频测试工具")
        self.root.geometry("650x580")  # 增加高度以适应设备选择区域
        self.root.resizable(False, False)
        
        # 设置样式
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 12), padding=10)
        self.style.configure("TLabel", font=("Arial", 12))
        self.style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        self.style.configure("Device.TLabel", font=("Arial", 10))
        self.style.configure("Refresh.TButton", font=("Arial", 10), padding=5)
        
        # 创建目录结构
        self.ensure_directories()
        
        # 初始化变量
        self.selected_audio_file = None
        self.local_audio_file = None
        self.file_extension = ""
        self.debug_info = ""
        self.devices = []  # 存储检测到的设备列表
        self.selected_device = None  # 当前选择的设备
        
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
        device_frame.pack(side="right", pady=10)
        
        ttk.Label(device_frame, text="设备:", style="Device.TLabel").pack(side="left", padx=5)
        
        # 设备下拉菜单
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=30, state="readonly")
        self.device_combo.pack(side="left", padx=5)
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        # 刷新按钮
        refresh_button = ttk.Button(device_frame, text="刷新", style="Refresh.TButton", 
                                  command=self.refresh_devices)
        refresh_button.pack(side="left", padx=5)
        
        # 设备状态标签
        self.device_status_var = tk.StringVar(value="未检测到设备")
        device_status = ttk.Label(self.root, textvariable=self.device_status_var, 
                                foreground="red", anchor="center")
        device_status.pack(fill="x", padx=20)
        
        # 创建主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 创建选项卡
        self.tab_control = ttk.Notebook(main_frame)
        
        # 10通道测试选项卡
        loopback_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(loopback_tab, text="10通道测试")
        
        # 麦克风测试选项卡
        mic_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(mic_tab, text="麦克风测试")
        
        # 多声道测试选项卡
        multichannel_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(multichannel_tab, text="多声道测试")
        
        # 本地播放选项卡
        local_playback_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(local_playback_tab, text="本地播放")
        
        self.tab_control.pack(expand=1, fill="both")
        
        # 10通道测试内容
        self.setup_loopback_tab(loopback_tab)
        
        # 麦克风测试内容
        self.setup_mic_tab(mic_tab)
        
        # 多声道测试内容
        self.setup_multichannel_tab(multichannel_tab)
        
        # 本地播放内容
        self.setup_local_playback_tab(local_playback_tab)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x")
    
    def refresh_devices(self):
        """刷新ADB设备列表"""
        try:
            self.status_var.set("正在检测设备...")
            result = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
            
            # 解析设备列表
            lines = result.stdout.strip().split('\n')
            self.devices = []
            
            if len(lines) > 1:  # 第一行是标题
                for line in lines[1:]:
                    if line.strip():
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            device_id = parts[0].strip()
                            status = parts[1].strip()
                            if status == "device":  # 只添加已授权的设备
                                self.devices.append(device_id)
            
            # 更新设备下拉菜单
            if self.devices:
                self.device_combo['values'] = self.devices
                self.device_combo.current(0)  # 默认选择第一个设备
                self.selected_device = self.devices[0]
                self.device_status_var.set(f"已连接设备: {len(self.devices)}个")
                for widget in self.root.winfo_children():
                    if isinstance(widget, ttk.Label) and widget.cget("textvariable") == str(self.device_status_var):
                        widget.configure(foreground="green")
                        break
                self.status_var.set("设备已连接，可以开始测试")
            else:
                self.device_combo['values'] = ["无可用设备"]
                self.device_combo.current(0)
                self.selected_device = None
                self.device_status_var.set("未检测到已授权的Android设备")
                for widget in self.root.winfo_children():
                    if isinstance(widget, ttk.Label) and widget.cget("textvariable") == str(self.device_status_var):
                        widget.configure(foreground="red")
                        break
                self.status_var.set("请连接Android设备并启用USB调试")
                
                # 提示用户连接设备
                messagebox.showwarning("设备未连接", "未检测到已授权的Android设备\n请确保设备已连接并启用USB调试")
        
        except Exception as e:
            self.status_var.set(f"检测设备出错: {str(e)}")
            messagebox.showerror("错误", f"检测ADB设备时出错:\n{str(e)}")
    
    def on_device_selected(self, event):
        """当用户选择设备时触发"""
        selected = self.device_var.get()
        if selected in self.devices:
            self.selected_device = selected
            self.status_var.set(f"已选择设备: {selected}")
            
            # 获取设备信息
            try:
                # 获取设备型号
                model_result = subprocess.run(f"adb -s {selected} shell getprop ro.product.model", 
                                           shell=True, capture_output=True, text=True)
                model = model_result.stdout.strip()
                
                # 获取Android版本
                version_result = subprocess.run(f"adb -s {selected} shell getprop ro.build.version.release", 
                                             shell=True, capture_output=True, text=True)
                version = version_result.stdout.strip()
                
                self.device_status_var.set(f"已选择: {model} (Android {version})")
                for widget in self.root.winfo_children():
                    if isinstance(widget, ttk.Label) and widget.cget("textvariable") == str(self.device_status_var):
                        widget.configure(foreground="green")
                        break
            except:
                self.device_status_var.set(f"已选择: {selected}")
        else:
            self.selected_device = None
            self.device_status_var.set("未选择有效设备")
            for widget in self.root.winfo_children():
                if isinstance(widget, ttk.Label) and widget.cget("textvariable") == str(self.device_status_var):
                    widget.configure(foreground="red")
                    break
    
    def get_adb_command(self, cmd):
        """获取带有设备指定的ADB命令"""
        if self.selected_device:
            return f"adb -s {self.selected_device} {cmd}"
        else:
            return f"adb {cmd}"
    
    def check_device_selected(self):
        """检查是否已选择设备"""
        if not self.selected_device:
            messagebox.showerror("错误", "未选择设备，请先选择一个设备")
            return False
        return True
    
    def setup_loopback_tab(self, parent):
        """设置10通道测试选项卡"""
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
                        text="播放音频并同时录制10通道音频\n用于验证音频回路和参考信号")
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
        
        # 开始按钮 - 确保它在最后并且有足够的空间
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=20)
        
        start_button = ttk.Button(button_frame, text="开始10通道测试", 
                                command=self.run_loopback_test)
        start_button.pack(pady=10)
        
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
        self.mic_var = tk.StringVar(value="2")
        mic_combo = ttk.Combobox(mic_frame, textvariable=self.mic_var, 
                               values=["2", "4"], width=5, state="readonly")
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
        
        # 开始按钮
        start_button = ttk.Button(frame, text="开始麦克风测试", 
                                command=self.run_mic_test)
        start_button.pack(pady=20)
    
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
    
    def browse_audio_file(self):
        """浏览并选择音频文件"""
        filetypes = [
            ("音频文件", "*.wav;*.mp3;*.flac;*.ogg"),
            ("WAV文件", "*.wav"),
            ("所有文件", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=filetypes
        )
        
        if filename:
            self.selected_audio_file = filename
            self.file_path_var.set(os.path.basename(filename))
            self.audio_source_var.set("custom")
    
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
    
    def run_loopback_test(self):
        """运行10通道测试"""
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
        
        self.status_var.set("正在执行10通道测试...")
        
        # 在新线程中运行测试，避免GUI冻结
        threading.Thread(target=self._loopback_test_thread, 
                        args=(device, channels, rate, audio_source), 
                        daemon=True).start()
    
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
            
            # 开始录制
            filename = f"test_{channels}ch.wav"
            record_cmd = self.get_adb_command(f"shell tinycap /sdcard/{filename} -d {device} -c {channels} -r {rate} -p 480")
            record_process = subprocess.Popen(record_cmd, shell=True)
            
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
            
            # 提示用户停止录制
            self.root.after(0, lambda: self.status_var.set("播放完成，请点击确定停止录制"))
            messagebox.showinfo("操作提示", "播放已完成，点击确定停止录制")
            
            # 停止录制
            subprocess.run(self.get_adb_command("shell pkill -f tinycap"), shell=True)
            record_process.terminate()
            
            # 拉取录制文件
            self.root.after(0, lambda: self.status_var.set("正在拉取录制文件..."))
            subprocess.run(self.get_adb_command(f"pull /sdcard/{filename} test/"), shell=True)
            
            self.root.after(0, lambda: self.status_var.set(f"{channels}通道测试完成，文件已保存为test/{filename}"))
            
            # 移除播放提示，直接显示完成信息
            messagebox.showinfo("测试完成", f"{channels}通道测试完成，文件已保存为test/{filename}")
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
    
    def run_mic_test(self):
        """运行麦克风测试"""
        if not self.check_device_selected():
            return
            
        mic_count = self.mic_var.get()
        pcm_device = self.mic_pcm_var.get()
        device_id = self.mic_device_var.get()
        rate = self.mic_rate_var.get()
        
        self.status_var.set(f"正在执行{mic_count}mic测试...")
        
        # 在新线程中运行测试，避免GUI冻结
        threading.Thread(target=self._mic_test_thread, 
                        args=(mic_count, pcm_device, device_id, rate), 
                        daemon=True).start()
    
    def _mic_test_thread(self, mic_count, pcm_device, device_id, rate):
        try:
            # 准备工作
            subprocess.run(self.get_adb_command("root"), shell=True)
            
            # 开始录制
            filename = f"test_{mic_count}mic.wav"
            record_cmd = self.get_adb_command(f"shell tinycap /sdcard/{filename} -D {pcm_device} -d {device_id} -c {mic_count} -r {rate}")
            
            # 显示完整命令以便调试
            print(f"执行命令: {record_cmd}")
            self.root.after(0, lambda: self.status_var.set(f"执行命令: {record_cmd}"))
            
            # 启动录制进程
            record_process = subprocess.Popen(record_cmd, shell=True)
            
            # 提示用户
            self.root.after(0, lambda: self.status_var.set(f"正在录制{mic_count}mic音频，请对着麦克风说话..."))
            messagebox.showinfo("操作提示", f"正在录制{mic_count}mic音频，请对着麦克风说话...\n完成后点击确定停止录制")
            
            # 停止录制
            subprocess.run(self.get_adb_command("shell pkill -f tinycap"), shell=True)
            record_process.terminate()
            
            # 拉取录制文件
            self.root.after(0, lambda: self.status_var.set("正在拉取录制文件..."))
            subprocess.run(self.get_adb_command(f"pull /sdcard/{filename} test/"), shell=True)
            
            self.root.after(0, lambda: self.status_var.set(f"{mic_count}mic测试完成，文件已保存为test/{filename}"))
            
            # 移除播放提示，直接显示完成信息
            messagebox.showinfo("测试完成", f"{mic_count}mic测试完成，文件已保存为test/{filename}")
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
    
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
                
                # 启动HPlayer
                self.status_var.set("正在启动HPlayer...")
                launch_cmd = self.get_adb_command("shell am start -n com.nes.seihplayer/.component.activity.SplashActivity")
                subprocess.run(launch_cmd, shell=True)
                
                # 提示用户在HPlayer中找到并播放文件
                self.playback_status_var.set("已启动HPlayer")
                self.status_var.set(f"请在HPlayer中找到并播放: {file_basename}")
                
                # 显示详细指导
                messagebox.showinfo("播放指南", 
                                   f"文件已推送到设备的HPlayerFiles文件夹中\n\n"
                                   f"文件名: {file_basename}\n\n"
                                   f"请在HPlayer中:\n"
                                   f"1. 点击'本地'或'文件'选项\n"
                                   f"2. 浏览到'HPlayerFiles'文件夹\n"
                                   f"3. 找到并点击'{file_basename}'开始播放")
                
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
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    self.playback_status_var.set("已停止")
                    self.status_var.set("就绪")
        except Exception:
            # 忽略停止过程中的错误
            pass
    
    def update_volume(self, *args):
        """更新音量"""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.set_volume(self.volume_var.get())
        except Exception:
            # 忽略音量调整过程中的错误
            pass
    
    def _monitor_playback(self):
        """监控音频播放状态"""
        try:
            while pygame.mixer.music.get_busy():
                time.sleep(0.5)
            
            # 播放结束
            if not pygame.mixer.music.get_busy():
                self.root.after(0, lambda: self.playback_status_var.set("播放完成"))
                self.root.after(0, lambda: self.status_var.set("就绪"))
        except Exception as e:
            # 忽略监控过程中的错误
            pass
    
    def show_debug_info(self):
        """显示调试信息"""
        if hasattr(self, 'debug_info'):
            messagebox.showinfo("调试信息", self.debug_info)
        else:
            messagebox.showinfo("调试信息", "尚无调试信息")

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioTestTool(root)
    root.mainloop()