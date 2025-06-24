import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import time
import pygame
import subprocess
import platform
import re
import shutil

class UIComponents:
    def __init__(self, parent):
        self.parent = parent
    
    def setup_loopback_tab(self, parent):
        """设置Loopback和Ref测试标签页"""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        
        # 添加标题说明
        title_label = ttk.Label(frame, text="播放音频并同时录制通道音频", font=("Arial", 11, "bold"))
        title_label.pack(pady=(10, 0))
        subtitle_label = ttk.Label(frame, text="用于验证音频回路和参考信号", font=("Arial", 9))
        subtitle_label.pack(pady=(0, 10))
        
        # 缺少初始化的变量
        self.audio_source_var = tk.StringVar(value="default")
        
        # 创建设置区域
        settings_frame = ttk.LabelFrame(frame, text="参数设置")
        settings_frame.pack(fill="x", padx=20, pady=10)
        
        # 设备参数设置 - 使用网格布局
        grid_frame = ttk.Frame(settings_frame)
        grid_frame.pack(fill="x", padx=10, pady=10)
        
        # 录制设备ID
        ttk.Label(grid_frame, text="录制设备ID:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.loopback_device_var = tk.StringVar(value="6")
        ttk.Entry(grid_frame, textvariable=self.loopback_device_var, width=10).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # 通道数
        ttk.Label(grid_frame, text="通道数:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.loopback_channel_var = tk.StringVar(value="10")
        ttk.Entry(grid_frame, textvariable=self.loopback_channel_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # 采样率
        ttk.Label(grid_frame, text="采样率:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.loopback_rate_var = tk.StringVar(value="16000")
        ttk.Entry(grid_frame, textvariable=self.loopback_rate_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # 添加保存路径设置
        ttk.Label(grid_frame, text="保存路径:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.loopback_save_path_var = tk.StringVar(value=os.path.join(os.getcwd(), "test"))
        path_frame = ttk.Frame(grid_frame)
        path_frame.grid(row=3, column=1, columnspan=3, sticky="w", padx=5, pady=5)
        
        path_entry = ttk.Entry(path_frame, textvariable=self.loopback_save_path_var, width=25)
        path_entry.pack(side="left", padx=2)
        
        browse_button = ttk.Button(path_frame, text="浏览...", 
                                   command=self.browse_loopback_save_path, width=8, 
                                   style="Small.TButton")
        browse_button.pack(side="left", padx=2)
        
        folder_button = ttk.Button(path_frame, text="打开文件夹", 
                                   command=self.open_loopback_folder, width=10,
                                   style="Small.TButton")
        folder_button.pack(side="left", padx=2)
        
        # 音频文件部分
        audio_frame = ttk.LabelFrame(frame, text="音频文件")
        audio_frame.pack(fill="x", padx=20, pady=10)
        
        # 音频源选择
        source_frame = ttk.Frame(audio_frame)
        source_frame.pack(fill="x", padx=10, pady=5)
        
        # 默认音频选项
        default_radio = ttk.Radiobutton(
            source_frame, 
            text="使用默认音频 (7.1声道)",
            variable=self.audio_source_var,
            value="default"
        )
        default_radio.pack(anchor="w", padx=10, pady=2)
        
        # 自定义音频选项
        custom_frame = ttk.Frame(audio_frame)
        custom_frame.pack(fill="x", padx=10, pady=5)
        
        custom_radio = ttk.Radiobutton(
            custom_frame, 
            text="使用自定义音频文件:",
            variable=self.audio_source_var,
            value="custom"
        )
        custom_radio.pack(side="left", padx=10)
        
        self.file_path_var = tk.StringVar(value="未选择文件")
        ttk.Label(custom_frame, textvariable=self.file_path_var, width=20).pack(side="left", padx=5, fill="x", expand=True)
        
        browse_button = ttk.Button(custom_frame, text="浏览...", command=self.browse_audio_file, width=8)
        browse_button.pack(side="right", padx=10)
        
        # 按钮区域
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)
        
        self.start_loopback_button = ttk.Button(
            button_frame, 
            text="开始通道测试",
            command=self.run_loopback_test,
            width=15
        )
        self.start_loopback_button.pack(side="left", padx=20)
        
        self.stop_loopback_button = ttk.Button(
            button_frame, 
            text="停止录制",
            command=self.stop_loopback_test,
            width=15, 
            state="disabled"
        )
        self.stop_loopback_button.pack(side="left", padx=20)
        
        # 状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=10)
        
        self.loopback_status_var = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.loopback_status_var, font=("Arial", 10)).pack(anchor="center", pady=10)
    
    def setup_mic_tab(self, parent):
        """设置麦克风测试选项卡"""
        frame = ttk.Frame(parent, padding=20)
        frame.pack(fill="both", expand=True)
        
        # 标题
        title_label = ttk.Label(frame, text="麦克风测试", style="Header.TLabel")
        title_label.pack(pady=10)
        
        # 参数设置区域
        settings_frame = ttk.LabelFrame(frame, text="测试设置", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=10)
        
        # 麦克风数量选择
        mic_frame = ttk.Frame(settings_frame)
        mic_frame.pack(fill="x", pady=5)
        
        ttk.Label(mic_frame, text="麦克风数量:").pack(side="left", padx=5)
        
        self.mic_count_var = tk.StringVar(value="4")  # 默认值为4
        mic_combobox = ttk.Combobox(mic_frame, textvariable=self.mic_count_var, 
                                   values=["2", "4"], width=5, state="readonly")
        mic_combobox.pack(side="left", padx=5)
        
        # PCM设备设置
        pcm_frame = ttk.Frame(settings_frame)
        pcm_frame.pack(fill="x", pady=5)
        
        ttk.Label(pcm_frame, text="PCM设备(-D):").pack(side="left", padx=5)
        
        self.mic_pcm_var = tk.StringVar(value="0")
        pcm_entry = ttk.Entry(pcm_frame, textvariable=self.mic_pcm_var, width=5)
        pcm_entry.pack(side="left", padx=5)
        
        # 设备ID设置
        device_frame = ttk.Frame(settings_frame)
        device_frame.pack(fill="x", pady=5)
        
        ttk.Label(device_frame, text="设备ID(-d):").pack(side="left", padx=5)
        
        self.mic_device_var = tk.StringVar(value="3")
        device_entry = ttk.Entry(device_frame, textvariable=self.mic_device_var, width=5)
        device_entry.pack(side="left", padx=5)
        
        # 采样率设置
        rate_frame = ttk.Frame(settings_frame)
        rate_frame.pack(fill="x", pady=5)
        
        ttk.Label(rate_frame, text="采样率(-r):").pack(side="left", padx=5)
        
        self.mic_rate_var = tk.StringVar(value="16000")
        rate_combobox = ttk.Combobox(rate_frame, textvariable=self.mic_rate_var, 
                                     values=["8000", "16000", "44100", "48000"], width=8)
        rate_combobox.pack(side="left", padx=5)
        
        # 按钮区域
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)
        
        # 开始按钮
        self.start_mic_button = ttk.Button(button_frame, text="开始麦克风测试", 
                                  command=self.start_mic_test, width=15)
        self.start_mic_button.pack(side="left", padx=10, expand=True)
        
        # 停止按钮
        self.stop_mic_button = ttk.Button(button_frame, text="停止录制", 
                                 command=self.stop_mic_test, width=15, state="disabled")
        self.stop_mic_button.pack(side="left", padx=10, expand=True)
        
        # 状态区域
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=10)
        
        self.mic_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(status_frame, textvariable=self.mic_status_var)
        status_label.pack(side="left")
    
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
        self.sweep_type_var = tk.StringVar(value="custom")
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
                                               style="Small.TButton")
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
        self.sweep_recording_device_var = tk.StringVar(value="7")  # 默认使用LOOPBACK-A设备
        recording_device_combobox = ttk.Combobox(rec_device_frame, textvariable=self.sweep_recording_device_var, 
                                           width=5, values=["0", "1", "2", "3", "4", "5", "6", "7"])
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
        self.sweep_recording_rate_var = tk.StringVar(value="16000")
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
        self.sweep_recording_duration_var = tk.StringVar(value="5")  # 增加默认录制时长
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_duration_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        # 周期大小
        ttk.Label(rec_param_frame, text="周期:", font=("Arial", 9)).pack(side="left", padx=2)
        self.sweep_recording_periods_var = tk.StringVar(value="480")
        ttk.Entry(rec_param_frame, textvariable=self.sweep_recording_periods_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        
        # 批量测试间隔
        batch_frame = ttk.Frame(recording_frame)
        batch_frame.pack(fill="x", pady=2)
        
        ttk.Label(batch_frame, text="批量测试间隔:", font=("Arial", 9)).pack(side="left", padx=2)
        self.batch_interval_var = tk.StringVar(value="5")
        ttk.Entry(batch_frame, textvariable=self.batch_interval_var, 
                font=("Arial", 9), width=5).pack(side="left", padx=2)
        ttk.Label(batch_frame, text="秒", font=("Arial", 9)).pack(side="left")
        
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
        
        # 在添加属性区域和属性列表区域之间添加全选/取消全选按钮
        select_buttons_frame = ttk.Frame(prop_frame)
        select_buttons_frame.pack(fill="x", pady=2)
        
        # 全选按钮
        select_all_button = ttk.Button(select_buttons_frame, text="全选", 
                                   command=lambda: self.toggle_all_props(True, "hal"),
                                   width=8, style="Small.TButton")
        select_all_button.pack(side="left", padx=2, pady=2)
        
        # 取消全选按钮
        deselect_all_button = ttk.Button(select_buttons_frame, text="取消全选", 
                                      command=lambda: self.toggle_all_props(False, "hal"),
                                      width=8, style="Small.TButton")
        deselect_all_button.pack(side="left", padx=2, pady=2)
        
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
            "vendor.media.audiohal.vpp.dump 1",
            "vendor.media.audiohal.indump 1",
            "vendor.media.audiohal.dspc 1",
            "vendor.media.audiohal.loopback 1",
            "vendor.media.audiohal.import 1",
            "vendor.media.audiohal.outdump 1",
            "vendor.media.audiohal.inport 1",
            "vendor.media.audiohal.alsadump 1",
            "vendor.media.audiohal.a2dpdump 1",
            "vendor.media.audiohal.tvdump 1",
            "vendor.media.audiohal.btpcm 1",
            "vendor.media.audiohal.ms12dump 0xfff",
            "media.audiohal.indump 1",
            "media.audiohal.outdump 1",
            "media.audiohal.alsadump 1",
            "media.audiohal.a2dpdump 1",
            "media.audiohal.ms12dump 0xfff",
            "media.audiohal.a2dp 1",
            "vendor.media.audiohal.in.dump 1",
            "vendor.media.audiohal.out.dump 1",
            "vendor.media.audiohal.ms12.dump 0xffff",
            "vendor.media.audiohal.spdif.dump 1",
            "vendor.media.audiohal.submixing.dump 0xffff",
            "vendor.media.audiohal.tv.dump 1",
            "vendor.media.audiohal.dtv.dump 1",
            "vendor.media.audiohal.mmap.dump 1",
            "vendor.media.audiohal.hfp.dump 1",
            "vendor.media.audiohal.sco.dump 1",
            "vendor.media.audiohal.a2dp.dump 1",
            "vendor.media.audiohal.usb.dump 1",
            "vendor.media.audiohal.decoder.dump 1",
            "vendor.media.audiohal.resample.dump 1",
            "vendor.media.audiohal.speed.dump 1",
            "vendor.media.audiohal.effect.dump 1",
            "vendor.media.c2.audio.decoder.dump 1",
            "vendor.media.omx.audio.dump 1"
        ]
        
        for prop in default_props:
            parts = prop.split()
            if len(parts) >= 2:
                self.add_prop_to_ui(parts[0], parts[1])
            else:
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
        
        # 控制按钮区域
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)
        
        # 使用较小的样式和宽度
        self.start_hal_button = ttk.Button(button_frame, text="开始录音", 
                                         command=self.start_hal_recording, width=10, style="Small.TButton")
        self.start_hal_button.pack(side="left", padx=5)
        
        self.stop_hal_button = ttk.Button(button_frame, text="停止录音", 
                                        command=self.stop_hal_recording, width=10, 
                                        state="disabled", style="Small.TButton")
        self.stop_hal_button.pack(side="left", padx=5)
        
        # 添加打开录音文件夹按钮
        self.open_hal_folder_button = ttk.Button(button_frame, text="打开文件夹", 
                                           command=self.open_hal_folder, width=10, style="Small.TButton")
        self.open_hal_folder_button.pack(side="left", padx=5)
        
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
        
        # 在属性输入区域之后添加全选/取消全选按钮
        select_buttons_frame = ttk.Frame(props_frame)
        select_buttons_frame.pack(fill="x", padx=5, pady=5)
        
        # 全选按钮
        select_all_button = ttk.Button(select_buttons_frame, text="全选", 
                                   command=lambda: self.toggle_all_props(True, "logcat"),
                                   width=8, style="Small.TButton")
        select_all_button.pack(side="left", padx=5, pady=2)
        
        # 取消全选按钮
        deselect_all_button = ttk.Button(select_buttons_frame, text="取消全选", 
                                      command=lambda: self.toggle_all_props(False, "logcat"),
                                      width=8, style="Small.TButton")
        deselect_all_button.pack(side="left", padx=5, pady=2)
        
        # 属性列表区域 - 使用Canvas和Scrollbar
        canvas_frame = ttk.Frame(props_frame)
        canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 创建Canvas和Scrollbar，调整Scrollbar样式使其更明显
        self.logcat_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.logcat_canvas.yview)
        
        # 配置滚动条样式使其更加明显
        self.style = ttk.Style()
        self.style.configure("Logcat.Vertical.TScrollbar", background="#bbbbbb", troughcolor="#dddddd", 
                            arrowcolor="#555555", bordercolor="#999999")
        scrollbar.configure(style="Logcat.Vertical.TScrollbar")
        
        self.logcat_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.logcat_canvas.pack(side="left", fill="both", expand=True)
        
        # 创建属性列表框架
        self.logcat_props_frame = ttk.Frame(self.logcat_canvas)
        self.logcat_canvas_window = self.logcat_canvas.create_window((0, 0), window=self.logcat_props_frame, anchor="nw")
        
        # 配置Canvas滚动
        self.logcat_props_frame.bind("<Configure>", lambda e: self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all")))
        self.logcat_canvas.bind("<Configure>", self.resize_logcat_props_frame)
        
        # 定义默认属性列表 - 使用您提供的属性和值
        self.logcat_props = [
            "vendor.avdebug.debug 1",
            "vendor.avdebug.dspc-debug 1",
            "sys.droidlogic.audio.debug 1",
            "vendor.media.audio.hal.debug 4096",
            "media.audio.hal.debug 4096",
            "vendor.media.audiohal.debug 4096",
            "vendor.media.audiohal.hwsync 1",
            "vendor.media.c2.audio.decoder.debug 1",
            "vendor.media.omx.audio.dump 1",
            "vendor.media.droidaudio.debug 1",
            "log.tag.APM_AudioPolicyManager V"
        ]
        
        # 创建属性列表
        self.logcat_props_vars = []
        self.logcat_prop_frames = []
        
        # 添加默认属性到列表
        for prop in self.logcat_props:
            parts = prop.split()
            if len(parts) >= 2:
                self.add_prop_to_list(parts[0], parts[1])
            else:
                self.add_prop_to_list(prop)
        
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
        
        # 清理已有的删除按钮
        self.root.after(100, self.clean_logcat_delete_buttons)

    def clean_logcat_delete_buttons(self):
        """清理Logcat属性列表中所有删除按钮"""
        try:
            # 遍历所有logcat属性框架
            for widget in self.logcat_props_frame.winfo_children():
                # 查找每个框架中的删除按钮并删除
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button) and child.cget("text") == "×":
                        child.destroy()
            
            # 刷新Canvas显示
            self.logcat_props_frame.update_idletasks()
            self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))
            
        except Exception as e:
            print(f"清理删除按钮出错: {e}")
    
    def add_prop_to_list(self, prop_name, prop_value="1"):
        """将属性添加到列表显示"""
        # 创建属性框架
        prop_frame = ttk.Frame(self.logcat_props_frame)
        prop_frame.pack(fill="x", padx=2, pady=1)
        
        # 复选框
        var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(prop_frame, variable=var, text="")
        check.pack(side="left", padx=1)
        
        # 属性名标签 - 使用更小的字体，显示为"属性名 属性值"
        prop_label = ttk.Label(prop_frame, text=f"{prop_name} {prop_value}", font=("Arial", 9))
        prop_label.pack(side="left", padx=2, fill="x", expand=True)
        
        # 保存属性信息
        self.logcat_props_vars.append({
            "name": prop_name,
            "var": var,
            "value": prop_value,
            "frame": prop_frame
        })
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))
    
    def add_logcat_prop(self):
        """添加日志属性"""
        prop_text = self.logcat_prop_var.get().strip()
        if not prop_text:
            messagebox.showerror("错误", "请输入属性名称和值，格式为: 属性名 值")
            return
        
        # 分割属性名和值
        parts = prop_text.split()
        if len(parts) < 2:
            messagebox.showerror("错误", "格式错误，请输入属性名和值，例如: vendor.media.audiohal.log 1")
            return
        
        prop_name = parts[0]
        prop_value = parts[1]
        
        # 检查是否已存在
        for prop in self.logcat_props_vars:
            if prop["name"] == prop_name:
                messagebox.showerror("错误", f"属性 {prop_name} 已存在")
                return
        
        # 添加到列表
        self.add_prop_to_list(prop_name, prop_value)
        
        # 清空输入框
        self.logcat_prop_var.set("")
        
        self.update_logcat_status(f"已添加属性: {prop_name}={prop_value}")

    def enable_logcat_debug(self):
        """放开日志打印"""
        if not self.check_device_selected():
            return
        
        try:
            self.update_logcat_status("正在放开日志打印...")
            
            # 首先尝试获取root权限
            root_cmd = self.get_adb_command("root")
            subprocess.run(root_cmd, shell=True)
            time.sleep(1)  # 等待root权限生效
            
            # 设置属性
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 设置对应的调试值
                    debug_value = prop["value"] if "value" in prop else "1"
                    
                    cmd = self.get_adb_command(f"shell setprop {prop['name']} {debug_value}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        self.update_logcat_status(f"警告: 设置属性 {prop['name']} 可能失败，继续其他属性设置")
                    else:
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
                    # 确定正常值
                    if prop["name"] == "log.tag.APM_AudioPolicyManager":
                        normal_value = "D"
                    else:
                        normal_value = "0"
                    
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
    
    def toggle_all_props(self, state, prop_type):
        """全选或取消全选所有属性
        
        Args:
            state: True表示全选，False表示取消全选
            prop_type: 'hal'表示HAL录音属性，'logcat'表示日志属性
        """
        if prop_type == "hal":
            # 处理HAL录音属性
            for prop, var in self.hal_props.items():
                var.set(state)
        elif prop_type == "logcat":
            # 处理Logcat属性
            for prop in self.logcat_props_vars:
                prop["var"].set(state)
        
        # 更新状态提示
        if prop_type == "hal":
            action = "已全选" if state else "已取消全选"
            self.hal_status_var.set(f"{action}所有HAL录音属性")
        else:
            action = "已全选" if state else "已取消全选"
            self.update_logcat_status(f"{action}所有Logcat属性")
    
    def setup_device_section(self, parent):
        """设置设备选择区域"""
        device_frame = ttk.LabelFrame(parent, text="设备控制")
        device_frame.pack(fill="x", padx=10, pady=5)
        
        # 设备选择区域
        select_frame = ttk.Frame(device_frame)
        select_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(select_frame, text="设备:").pack(side="left", padx=5)
        
        self.device_var = tk.StringVar()
        self.device_combobox = ttk.Combobox(select_frame, textvariable=self.device_var, width=30)
        self.device_combobox.pack(side="left", padx=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self.on_device_selected)
        
        refresh_button = ttk.Button(select_frame, text="刷新", command=self.refresh_devices, width=8)
        refresh_button.pack(side="left", padx=5)
        
        # 添加遥控器适配按钮
        remote_button = ttk.Button(select_frame, text="适配遥控器", command=self.adapt_remote_controller, width=12)
        remote_button.pack(side="left", padx=5)
        
        # 设备状态显示
        status_frame = ttk.Frame(device_frame)
        status_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(status_frame, text="状态:").pack(side="left", padx=5)
        self.device_status_var = tk.StringVar(value="未连接")
        status_label = ttk.Label(status_frame, textvariable=self.device_status_var, foreground="red")
        status_label.pack(side="left", padx=5)
        
        # 初始刷新设备列表
        self.refresh_devices()
    
    def adapt_remote_controller(self):
        """重新适配设备的遥控器"""
        if not self.check_device_selected():
            return
        
        try:
            self.status_var.set("正在适配遥控器...")
            
            # 直接执行遥控器适配命令，不显示确认对话框
            pairing_cmd = self.get_adb_command("shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS")
            subprocess.run(pairing_cmd, shell=True)
            
            # 简单更新状态，不显示消息框
            self.status_var.set("遥控器适配已启动")
            
        except Exception as e:
            self.status_var.set(f"适配遥控器失败: {str(e)}")
    
    def update_readme_with_remote_info(self):
        """更新README文件中的遥控器配对说明"""
        try:
            readme_path = "README.md"
            if os.path.exists(readme_path):
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # 如果README中没有提到新的配对指令，添加说明
                if "com.nes.intent.action.NES_RESET_LONGPRESS" not in content:
                    remote_section = "### 11. 遥控器管理\n"
                    remote_section_new = (
                        "### 11. 遥控器管理\n"
                        "- 支持遥控器配对和管理\n"
                        "- 使用`adb shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS`指令进行配对\n"
                        "- 支持发送遥控器按键命令\n"
                        "- 可移除已配对的遥控器\n"
                    )
                    content = content.replace(remote_section, remote_section_new)
                    
                    with open(readme_path, "w", encoding="utf-8") as f:
                        f.write(content)
        except Exception as e:
            print(f"更新README文件时出错: {str(e)}")
    
    def setup_remote_tab(self, parent):
        """设置遥控器控制标签页"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 遥控器状态
        self.remote_status_var = tk.StringVar(value="就绪")
        
        # 创建一个大的框架来包含所有按钮
        remote_frame = ttk.LabelFrame(frame, text="遥控器控制")
        remote_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建滚动画布以支持更多按钮
        canvas = tk.Canvas(remote_frame)
        scrollbar = ttk.Scrollbar(remote_frame, orient="vertical", command=canvas.yview)
        self.remote_content_frame = ttk.Frame(canvas)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 创建窗口来放置内容框架
        canvas_window = canvas.create_window((0, 0), window=self.remote_content_frame, anchor="nw")
        
        # 配置画布大小随内容调整
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)
        
        self.remote_content_frame.bind("<Configure>", configure_canvas)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        # 设置按钮部分
        # 1. 方向键和确认键部分
        direction_frame = ttk.Frame(self.remote_content_frame)
        direction_frame.pack(pady=10)
        
        # 上方向键
        up_button = ttk.Button(direction_frame, text="↑", 
                               command=lambda: self.send_keycode("DPAD_UP"), 
                               width=5, style="Remote.TButton")
        up_button.grid(row=0, column=1, pady=2)
        
        # 左方向键、确认键、右方向键
        left_button = ttk.Button(direction_frame, text="←", 
                                command=lambda: self.send_keycode("DPAD_LEFT"), 
                                width=5, style="Remote.TButton")
        left_button.grid(row=1, column=0, padx=2)
        
        ok_button = ttk.Button(direction_frame, text="OK", 
                              command=lambda: self.send_keycode("DPAD_CENTER"), 
                              width=5, style="Remote.TButton")
        ok_button.grid(row=1, column=1, padx=2)
        
        right_button = ttk.Button(direction_frame, text="→", 
                                 command=lambda: self.send_keycode("DPAD_RIGHT"), 
                                 width=5, style="Remote.TButton")
        right_button.grid(row=1, column=2, padx=2)
        
        # 下方向键
        down_button = ttk.Button(direction_frame, text="↓", 
                                command=lambda: self.send_keycode("DPAD_DOWN"), 
                                width=5, style="Remote.TButton")
        down_button.grid(row=2, column=1, pady=2)
        
        # 2. 音量和返回/配对按钮
        volume_frame = ttk.Frame(self.remote_content_frame)
        volume_frame.pack(pady=10)
        
        # 音量增加
        vol_up_button = ttk.Button(volume_frame, text="Vol+", 
                                  command=lambda: self.send_keycode("VOLUME_UP"), 
                                  width=8, style="Remote.TButton")
        vol_up_button.grid(row=0, column=0, padx=10, pady=5)
        
        # 返回按钮
        back_button = ttk.Button(volume_frame, text="返回", 
                                command=lambda: self.send_keycode("BACK"), 
                                width=8, style="Remote.TButton")
        back_button.grid(row=0, column=1, padx=10, pady=5)
        
        # 音量减少
        vol_down_button = ttk.Button(volume_frame, text="Vol-", 
                                    command=lambda: self.send_keycode("VOLUME_DOWN"), 
                                    width=8, style="Remote.TButton")
        vol_down_button.grid(row=1, column=0, padx=10, pady=5)
        
        # 配对遥控器
        pair_button = ttk.Button(volume_frame, text="配对遥控", 
                               command=self.adapt_remote_controller, 
                               width=8, style="Remote.TButton")
        pair_button.grid(row=1, column=1, padx=10, pady=5)
        
        # 状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=5)
        
        status_label = ttk.Label(status_frame, textvariable=self.remote_status_var)
        status_label.pack(side="left")
        
        # 添加说明图示
        instruction_frame = ttk.LabelFrame(frame, text="配对说明")
        instruction_frame.pack(fill="both", expand=True, pady=10)
        
        instruction_text = tk.Text(instruction_frame, height=8, wrap="word")
        instruction_text.pack(fill="both", expand=True, padx=5, pady=5)
        instruction_text.insert("1.0", "配对步骤：\n"
                              + "1. 确保遥控器有电池并处于待配对状态\n"
                              + "2. 点击\"配对遥控\"按钮\n"
                              + "3. 长按遥控器上的\"返回\"和\"主页\"键直到LED闪烁\n"
                              + "4. 等待配对完成\n\n"
                              + "注意：如果遥控器已经配对，请先在设备设置中删除旧的配对记录")
        instruction_text.config(state="disabled")

        # 添加设置按钮
        settings_button = ttk.Button(direction_frame, text="设置", 
                                 command=lambda: self.send_keycode("KEYCODE_MENU"), 
                                 width=8, style="Remote.TButton")
        settings_button.grid(row=3, column=1, pady=8)
    
    def setup_radar_tab(self, parent):
        """设置雷达检查选项卡"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 标题
        title_label = ttk.Label(frame, text="雷达传感器检查", style="Header.TLabel")
        title_label.pack(pady=10)
        
        # 说明文本
        desc = ttk.Label(frame, 
                       text="此功能可以帮助您检查设备的雷达传感器是否正常工作",
                       wraplength=600)
        desc.pack(pady=5)
        
        # 创建不同检查方法的区域
        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 方法1: TTY设备检查
        tty_frame = ttk.Frame(notebook, padding=10)
        notebook.add(tty_frame, text="TTY设备检查")
        self.setup_tty_check(tty_frame)
        
        # 方法2: logcat监控
        logcat_frame = ttk.Frame(notebook, padding=10)
        notebook.add(logcat_frame, text="Logcat监控")
        self.setup_radar_logcat(logcat_frame)
        
        # 方法3: AIEQ操作指南
        aieq_frame = ttk.Frame(notebook, padding=10)
        notebook.add(aieq_frame, text="AIEQ操作指南")
        self.setup_aieq_guide(aieq_frame)
        
        # 状态显示
        self.radar_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.radar_status_var)
        status_label.pack(pady=5)

    def setup_tty_check(self, parent):
        """TTY设备检查设置"""
        # 说明
        ttk.Label(parent, text="检查设备中是否存在ttyACM设备，存在则表明有雷达节点，是否工作还需要进一步检查").pack(pady=5)
        
        # 操作区域
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", pady=10)
        
        check_button = ttk.Button(action_frame, text="检查TTY设备", 
                                command=self.check_tty_devices, width=15, style="Small.TButton")
        check_button.pack(side="left", padx=5)
        
        # 结果显示区域
        result_frame = ttk.LabelFrame(parent, text="检查结果")
        result_frame.pack(fill="both", expand=True, pady=10)
        
        # 创建文本框显示结果
        self.tty_result_text = tk.Text(result_frame, height=10, width=50)
        self.tty_result_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.tty_result_text, command=self.tty_result_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.tty_result_text.config(yscrollcommand=scrollbar.set)
        
        # 初始状态
        self.tty_result_text.insert("1.0", "点击\"检查TTY设备\"按钮开始检查...\n")
        self.tty_result_text.config(state="disabled")

    def setup_radar_logcat(self, parent):
        """Logcat监控设置"""
        # 说明部分减小高度
        ttk.Label(parent, text="监控logcat中的updateGain日志，遮挡雷达传感器时应该有数值变化", 
                 font=("Arial", 9)).pack(pady=2)
        
        # 操作区域减小高度
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", pady=5)
        
        self.start_radar_monitor_button = ttk.Button(action_frame, text="开始监控", 
                                                   command=self.start_radar_monitor, width=15,
                                                   style="Small.TButton")
        self.start_radar_monitor_button.pack(side="left", padx=5)
        
        self.stop_radar_monitor_button = ttk.Button(action_frame, text="停止监控", 
                                                  command=self.stop_radar_monitor, width=15, 
                                                  state="disabled", style="Small.TButton")
        self.stop_radar_monitor_button.pack(side="left", padx=5)
        
        # 指导信息框减小高度
        guide_frame = ttk.LabelFrame(parent, text="测试步骤")
        guide_frame.pack(fill="x", pady=5)
        
        guide_text = """    1. 点击"开始监控"按钮启动日志监控
        2. 用手或物体靠近/远离雷达传感器区域
        3. 观察下方日志显示，如有updateGain值变化则表明雷达正常
        4. 完成测试后点击"停止监控"按钮"""
        
        ttk.Label(guide_frame, text=guide_text, justify="left", 
                 font=("Arial", 9)).pack(padx=10, pady=2)
        
        # 结果显示区域扩大高度比例
        result_frame = ttk.LabelFrame(parent, text="监控结果")
        result_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建文本框显示结果
        self.radar_logcat_text = tk.Text(result_frame, height=14, width=50, font=("Arial", 9))
        self.radar_logcat_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.radar_logcat_text, command=self.radar_logcat_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.radar_logcat_text.config(yscrollcommand=scrollbar.set)
        
        # 初始状态
        self.radar_logcat_text.insert("1.0", "点击\"开始监控\"按钮开始监控雷达传感器日志...\n")
        self.radar_logcat_text.config(state="disabled")

    def setup_aieq_guide(self, parent):
        """AIEQ操作指南设置"""
        # 说明
        ttk.Label(parent, text="通过AIEQ界面的Sweet Spot功能测试雷达传感器").pack(pady=5)
        
        # 指导信息
        guide_frame = ttk.LabelFrame(parent, text="操作步骤")
        guide_frame.pack(fill="both", expand=True, pady=10)
        
        guide_text = """
        1. 在设备上长按遥控器的静音键，打开AIEQ界面
        
        2. 在AIEQ界面中找到并点击"Sweet Spot"按钮
        
        3. Sweet Spot功能会根据雷达传感器检测用户位置并调整音效
        
        4. 测试方法：
           - 在Sweet Spot模式下播放音乐
           - 移动位置或用手遮挡雷达传感器区域
           - 观察声音效果是否有变化
           - 如有变化，则表明雷达传感器工作正常
        
        注意：此方法需要设备支持AIEQ功能和Sweet Spot特性
        """
        
        # 使用带滚动条的文本框显示指南
        guide_text_widget = tk.Text(guide_frame, height=15, width=50, wrap="word")
        guide_text_widget.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(guide_text_widget, command=guide_text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        guide_text_widget.config(yscrollcommand=scrollbar.set)
        
        # 插入指南文本
        guide_text_widget.insert("1.0", guide_text)
        guide_text_widget.config(state="disabled")
    
    def check_tty_devices(self):
        """检查TTY设备"""
        if not self.check_device_selected():
            return
        
        self.radar_status_var.set("正在检查TTY设备...")
        
        # 启用文本编辑
        self.tty_result_text.config(state="normal")
        self.tty_result_text.delete("1.0", tk.END)
        self.tty_result_text.insert("1.0", "正在检查TTY设备...\n")
        
        try:
            # 执行命令检查TTY设备
            cmd = self.get_adb_command("shell ls -la /dev/tty*")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"执行命令失败: {result.stderr}")
            
            # 获取所有TTY设备
            tty_devices = result.stdout.strip().split('\n')
            
            # 输出所有设备
            self.tty_result_text.insert(tk.END, "\n所有TTY设备:\n")
            self.tty_result_text.insert(tk.END, result.stdout)
            
            # 检查是否有ttyACM设备
            acm_devices = [device for device in tty_devices if 'ttyACM' in device]
            
            if acm_devices:
                self.tty_result_text.insert(tk.END, "\n\n检测到ttyACM设备:\n")
                for device in acm_devices:
                    self.tty_result_text.insert(tk.END, f"{device}\n")
                self.tty_result_text.insert(tk.END, "\n✅ 雷达传感器已连接，是否正常工作还需要进一步检查Logcat！\n")
                self.radar_status_var.set("检查完成: 已检测到雷达传感器")
            else:
                self.tty_result_text.insert(tk.END, "\n\n❌ 未检测到ttyACM设备，雷达传感器可能未连接或不工作\n")
                self.radar_status_var.set("检查完成: 未检测到雷达传感器")
        
        except Exception as e:
            self.tty_result_text.insert(tk.END, f"\n检查出错: {str(e)}\n")
            self.radar_status_var.set(f"检查出错: {str(e)}")
        
        # 禁用文本编辑
        self.tty_result_text.config(state="disabled")

    def start_radar_monitor(self):
        """开始监控雷达传感器logcat"""
        if not self.check_device_selected():
            return
        
        self.radar_status_var.set("正在开始监控雷达传感器日志...")
        
        # 启用文本编辑
        self.radar_logcat_text.config(state="normal")
        self.radar_logcat_text.delete("1.0", tk.END)
        self.radar_logcat_text.insert("1.0", "正在监控雷达传感器日志...\n")
        self.radar_logcat_text.insert(tk.END, "请用手或物体靠近/远离雷达传感器区域，观察updateGain值变化\n\n")
        self.radar_logcat_text.config(state="disabled")
        
        try:
            # 使用grep命令过滤updateGain日志
            cmd = self.get_adb_command("shell \"logcat | grep updateGain\"")
            
            # 启动日志进程
            self.radar_logcat_process = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            
            # 更新按钮状态
            self.start_radar_monitor_button.config(state="disabled")
            self.stop_radar_monitor_button.config(state="normal")
            
            # 启动线程读取输出
            self.radar_monitor_thread = threading.Thread(
                target=self._read_radar_logcat,
                daemon=True
            )
            self.radar_monitor_thread.start()
            
            self.radar_status_var.set("正在监控雷达传感器日志...")
        
        except Exception as e:
            self.radar_status_var.set(f"开始监控出错: {str(e)}")
            self.radar_logcat_text.config(state="normal")
            self.radar_logcat_text.insert(tk.END, f"开始监控出错: {str(e)}\n")
            self.radar_logcat_text.config(state="disabled")

    def _read_radar_logcat(self):
        """读取雷达传感器日志输出"""
        try:
            # 记录上一次的updateGain值
            last_gain = None
            gain_changes = 0
            
            while self.radar_logcat_process and self.radar_logcat_process.poll() is None:
                line = self.radar_logcat_process.stdout.readline()
                if not line:
                    continue
                
                # 将新行添加到文本框
                self.radar_logcat_text.config(state="normal")
                self.radar_logcat_text.insert(tk.END, line)
                self.radar_logcat_text.see(tk.END)
                self.radar_logcat_text.config(state="disabled")
                
                # 提取updateGain值
                match = re.search(r'updateGain.*?(\d+\.?\d*)', line)
                if match:
                    gain = float(match.group(1))
                    
                    # 检查值是否变化
                    if last_gain is not None and abs(gain - last_gain) > 0.01:
                        gain_changes += 1
                        self.radar_logcat_text.config(state="normal")
                        self.radar_logcat_text.insert(tk.END, f"检测到值变化: {last_gain} -> {gain}\n")
                        self.radar_logcat_text.see(tk.END)
                        self.radar_logcat_text.config(state="disabled")
                        
                        # 如果检测到值变化，在界面显示
                        if gain_changes == 1:
                            self.radar_logcat_text.config(state="normal")
                            self.radar_logcat_text.insert(tk.END, "\n✅ 检测到雷达传感器响应！\n")
                            self.radar_logcat_text.see(tk.END)
                            self.radar_logcat_text.config(state="disabled")
                            self.radar_status_var.set("监控中: 雷达传感器工作正常")
                    
                    last_gain = gain
        
        except Exception as e:
            self.root.after(0, lambda: self.radar_status_var.set(f"监控出错: {str(e)}"))

    def stop_radar_monitor(self):
        """停止监控雷达传感器logcat"""
        if not hasattr(self, 'radar_logcat_process') or self.radar_logcat_process is None:
            return
        
        try:
            # 终止日志进程
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /T /PID {self.radar_logcat_process.pid}", shell=True)
            else:
                self.radar_logcat_process.terminate()
            
            # 更新按钮状态
            self.start_radar_monitor_button.config(state="normal")
            self.stop_radar_monitor_button.config(state="disabled")
            
            # 更新状态
            self.radar_status_var.set("监控已停止")
            self.radar_logcat_text.config(state="normal")
            self.radar_logcat_text.insert(tk.END, "\n监控已停止\n")
            self.radar_logcat_text.see(tk.END)
            self.radar_logcat_text.config(state="disabled")
        
        except Exception as e:
            self.radar_status_var.set(f"停止监控出错: {str(e)}")
    
    def open_hal_folder(self):
        """打开HAL录音保存文件夹"""
        save_dir = self.hal_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "hal_dump")
        
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
            self.hal_status_var.set(f"打开文件夹出错: {str(e)}")
            self.update_info_text(f"打开文件夹出错: {str(e)}")
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
            
            # 按频率顺序排序文件
            sorted_files = self.sort_files_by_frequency(elephant_files)
            
            if sorted_files:
                self.sweep_file_combobox['values'] = sorted_files
                self.sweep_file_var.set(sorted_files[0])
                self.update_sweep_info(f"已加载 {len(sorted_files)} 个大象扫频文件")
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
            
            # 按频率顺序排序文件
            sorted_files = self.sort_files_by_frequency(custom_files)
            
            if sorted_files:
                self.sweep_file_combobox['values'] = sorted_files
                self.sweep_file_var.set(sorted_files[0])
                self.update_sweep_info(f"已加载 {len(sorted_files)} 个自定义扫频文件")
            else:
                self.update_sweep_info("未找到自定义扫频文件，请点击'添加文件'按钮添加")

    def sort_files_by_frequency(self, files):
        """按照频率排序文件（从低频到高频）"""
        # 定义频率顺序的正则表达式模式
        freq_patterns = [
            r'(\d+)[-_](\d+)hz', 
            r'(\d+)[-_](\d+)khz',
            r'(\d+)hz[-_](\d+)hz',
            r'(\d+)hz[-_](\d+)khz',
            r'(\d+)[-_](\d+)[k]?'  # 更通用的模式，如20_20k
        ]
        
        # 为文件创建排序键
        def get_sort_key(filename):
            filename_lower = filename.lower()
            
            # 特殊情况：如果是 custom 样式的文件，应该排在最前面
            if "custom" in filename_lower:
                return (20, 20000)
                
            # 尝试从文件名中提取频率信息
            for pattern in freq_patterns:
                match = re.search(pattern, filename_lower)
                if match:
                    start_freq = int(match.group(1))
                    end_freq = int(match.group(2))
                    
                    # 转换单位：如果是kHz，转换为Hz
                    if 'khz' in match.group(0) or 'k' in match.group(0):
                        if end_freq < 1000:
                            end_freq *= 1000
                        if start_freq < 1000 and end_freq >= 1000:
                            start_freq *= 1000
                    
                    return (start_freq, end_freq)
            
            # 尝试匹配单个频率数字
            single_freq_match = re.search(r'(\d+)(hz|khz|k)?', filename_lower)
            if single_freq_match:
                freq = int(single_freq_match.group(1))
                unit = single_freq_match.group(2) if single_freq_match.group(2) else ""
                
                if 'khz' in unit or 'k' in unit:
                    freq *= 1000
                    
                return (freq, freq)
            
            # 如果没有匹配的频率模式，使用文件名进行排序，但优先级最低
            return (999999, filename)
        
        # 按照起始频率和结束频率排序
        return sorted(files, key=get_sort_key)

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
            # 获取原始文件名和扩展名
            base_filename = os.path.basename(file)
            filename, ext = os.path.splitext(base_filename)
            filename_lower = filename.lower()
            
            # 检查是否是20-20kHz范围的扫频文件
            is_full_range = False
            
            # 检查常见的全频扫频文件命名模式
            if any(pattern in filename_lower for pattern in ["20hz-20khz", "20-20k", "20_20k", "20hz_20khz", "20to20k"]):
                is_full_range = True
            else:
                # 使用正则表达式检查是否是20Hz到20kHz的范围
                range_match = re.search(r'(\d+)[-_](\d+)([k]?hz)?', filename_lower)
                if range_match:
                    start_freq = int(range_match.group(1))
                    end_freq = int(range_match.group(2))
                    
                    # 如果有单位且是k或khz，转换为Hz
                    if range_match.group(3) and ('k' in range_match.group(3)):
                        if end_freq < 1000:  # 如果数字小于1000，认为是以k为单位
                            end_freq *= 1000
                    
                    # 检查是否接近20Hz-20kHz范围
                    if (start_freq == 20 or start_freq == 16) and (end_freq == 20000 or end_freq == 20 or end_freq == 22000):
                        is_full_range = True
            
            # 根据是否是全频扫频文件设置新文件名
            if is_full_range:
                new_filename = f"custom{ext}"
                self.update_sweep_info(f"检测到全频扫频文件: {base_filename}，将重命名为: {new_filename}")
            else:
                new_filename = base_filename
            
            dest_path = os.path.join(custom_dir, new_filename)
            
            try:
                shutil.copy2(file, dest_path)
                copied_files.append(new_filename)
            except Exception as e:
                self.update_sweep_info(f"复制文件 {new_filename} 失败: {str(e)}")
        
        if copied_files:
            self.update_sweep_info(f"已添加 {len(copied_files)} 个自定义扫频文件")
            
            # 更新文件列表
            self.update_sweep_file_options()
    
    def start_sweep_test(self):
        """开始扫频测试"""
        if not self.check_device_selected():
            return
        
        # 检查是否是批量测试
        if self.sweep_batch_var.get():
            self.start_batch_sweep_test()
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
            
            # 重启audioserver
            for _ in range(3):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
                time.sleep(0.5)
            
            # 获取时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 设置设备上的临时文件路径
            device_audio_path = f"/sdcard/{sweep_file}"
            
            # 推送音频文件到设备
            self.update_sweep_info(f"正在推送音频文件: {sweep_file}")
            push_cmd = self.get_adb_command(f"push \"{source_path}\" {device_audio_path}")
            subprocess.run(push_cmd, shell=True)
            
            # 设置录制文件名
            file_base_name = os.path.splitext(sweep_file)[0]  # 获取不带扩展名的文件名
            recording_filename = f"{file_base_name}_recording_{timestamp}.wav"
            device_recording_path = f"/sdcard/{recording_filename}"
            self.sweep_filename = recording_filename  # 保存文件名以便后续处理
            
            # 获取录制参数
            recording_device = self.sweep_recording_device_var.get().strip()
            recording_card = self.sweep_recording_card_var.get().strip()
            recording_channels = self.sweep_recording_channels_var.get().strip()
            recording_rate = self.sweep_recording_rate_var.get().strip()
            recording_bits = self.sweep_recording_bits_var.get().strip()
            recording_periods = self.sweep_recording_periods_var.get().strip()
            
            # 开始录制
            self.update_sweep_info("开始录制...")
            
            # 构建tinycap命令
            tinycap_cmd = f"shell tinycap {device_recording_path} -d {recording_device} -c {recording_channels} -r {recording_rate} -p {recording_periods}"
            tinycap_full_cmd = self.get_adb_command(tinycap_cmd)
            self.update_sweep_info(f"执行录音命令: {tinycap_full_cmd}")
            self.recording_process = subprocess.Popen(tinycap_full_cmd, shell=True)
            
            # 等待录制启动
            time.sleep(2)
            
            # 播放音频
            self.update_sweep_info("开始播放音频...")
            
            # 获取播放参数
            playback_device = self.sweep_playback_device_var.get().strip()
            playback_card = self.sweep_playback_card_var.get().strip()
            playback_channels = self.sweep_playback_channels_var.get().strip()
            playback_rate = self.sweep_playback_rate_var.get().strip()
            playback_bits = self.sweep_playback_bits_var.get().strip()
            
            # 构建tinyplay命令
            tinyplay_cmd = f"shell tinyplay {device_audio_path} -d {playback_device}"
            tinyplay_full_cmd = self.get_adb_command(tinyplay_cmd)
            self.update_sweep_info(f"执行播放命令: {tinyplay_full_cmd}")
            self.playback_process = subprocess.Popen(tinyplay_full_cmd, shell=True)
            
            # 启动监控线程
            self.sweep_monitor_thread = threading.Thread(
                target=self.monitor_sweep_test,
                args=(device_recording_path, save_dir, recording_filename, sweep_file),
                daemon=True
            )
            self.sweep_monitor_thread.start()
            
        except Exception as e:
            self.sweep_status_var.set(f"测试出错: {str(e)}")
            self.update_sweep_info(f"测试出错: {str(e)}")
            messagebox.showerror("错误", f"开始扫频测试时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")

    def monitor_sweep_test(self, device_recording_path, save_dir, recording_filename, sweep_file):
        """监控播放进程，在播放完成后自动停止录制"""
        try:
            # 等待播放进程结束
            if hasattr(self, 'playback_process') and self.playback_process:
                self.update_sweep_info("等待播放完成...")
                self.playback_process.wait()
                self.update_sweep_info("播放已完成")
            
            # 等待一段时间确保录制完整
            time.sleep(3)
            
            # 停止录制进程
            if hasattr(self, 'recording_process') and self.recording_process.poll() is None:
                self.update_sweep_info("正在停止录制...")
                # 使用killall命令停止tinycap
                kill_cmd = self.get_adb_command("shell killall tinycap")
                subprocess.run(kill_cmd, shell=True)
                self.update_sweep_info("已停止录制")
            
            # 拉取录音文件
            self.pull_sweep_recording()
            
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_sweep_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            
        except Exception as e:
            self.root.after(0, lambda: self.update_sweep_info(f"监控播放过程中出错: {str(e)}"))
            self.root.after(0, lambda: self.sweep_status_var.set("监控出错"))
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_sweep_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_sweep_button.config(state="disabled"))

    def start_batch_sweep_test(self):
        """启动批量扫频测试"""
        if not self.check_device_selected():
            return
        
        # 获取选择的扫频类型
        sweep_type = self.sweep_type_var.get()
        
        # 获取文件列表
        if sweep_type == "elephant":
            dir_path = os.path.join(os.getcwd(), "audio", "elephant")
        else:  # custom
            dir_path = os.path.join(os.getcwd(), "audio", "custom")
        
        if not os.path.exists(dir_path):
            messagebox.showerror("错误", f"扫频文件目录不存在: {dir_path}")
            return
        
        # 获取所有音频文件
        files = [f for f in os.listdir(dir_path) if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg'))]
        
        if not files:
            messagebox.showerror("错误", f"未找到任何音频文件")
            return
        
        # 如果文件数量很多，询问用户是否确定
        if len(files) > 10:
            if not messagebox.askyesno("确认", f"将对 {len(files)} 个音频文件进行批量测试，可能需要较长时间。\n\n确定要继续吗？"):
                return
        
        # 对文件按频率进行排序
        files = self.sort_files_by_frequency(files)
        
        # 获取保存路径
        save_dir = self.sweep_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "sweep_recordings")
        
        os.makedirs(save_dir, exist_ok=True)
        
        # 清空保存目录中的文件
        if messagebox.askyesno("确认", f"是否清空保存目录({save_dir})中的所有WAV文件？"):
            try:
                for file in os.listdir(save_dir):
                    if file.lower().endswith('.wav'):
                        os.remove(os.path.join(save_dir, file))
                self.update_sweep_info(f"已清空保存目录中的WAV文件")
            except Exception as e:
                self.update_sweep_info(f"清空目录出错: {str(e)}")
        
        # 获取测试间隔时间
        try:
            interval = float(self.batch_interval_var.get())
            if interval < 0:
                interval = 5
        except (ValueError, TypeError):
            interval = 5
        
        # 获取录制时长
        try:
            recording_duration = float(self.sweep_recording_duration_var.get())
            if recording_duration <= 0:
                recording_duration = interval  # 如果未设置录制时长，使用间隔时间
        except (ValueError, TypeError):
            recording_duration = interval
        
        # 禁用测试按钮
        self.start_sweep_button.config(state="disabled")
        self.stop_sweep_button.config(state="normal")
        
        # 在单独的线程中运行批量测试
        self.batch_thread = threading.Thread(
            target=self._run_batch_tests,
            args=(files, sweep_type, interval, recording_duration, save_dir),
            daemon=True
        )
        self.batch_thread.start()

    def _run_batch_tests(self, files, sweep_type, interval, recording_duration, save_dir):
        """在线程中运行批量测试"""
        try:
            self.sweep_status_var.set(f"开始批量测试 {len(files)} 个文件")
            self.update_sweep_info(f"开始批量测试 {len(files)} 个文件")
            self.update_sweep_info(f"录制时长: {recording_duration}秒, 测试间隔: {interval}秒")
            
            total_files = len(files)
            success_count = 0
            
            for i, file in enumerate(files):
                # 检查是否已请求停止测试
                if hasattr(self, 'stop_requested') and self.stop_requested:
                    self.update_sweep_info("批量测试已手动停止")
                    break
                
                # 更新状态
                self.update_sweep_info(f"===== 测试文件 {i+1}/{total_files}: {file} =====")
                self.sweep_status_var.set(f"测试 {i+1}/{total_files}: {file}")
                
                # 测试单个文件
                success = self._batch_test_single_file(file, sweep_type, recording_duration, save_dir)
                
                if success:
                    success_count += 1
                
                # 如果不是最后一个文件，等待指定的间隔时间
                if i < total_files - 1:
                    # 无需额外等待，因为每个测试已经消耗了recording_duration的时间
                    pass
            
            # 测试完成后
            msg = f"批量测试完成，成功: {success_count}/{total_files}"
            self.update_sweep_info(msg)
            self.sweep_status_var.set(msg)
            
            # 测试完成
            self.root.after(0, lambda: messagebox.showinfo("完成", 
                f"批量扫频测试已完成！\n\n共测试 {total_files} 个文件，成功 {success_count} 个。\n\n录音文件已保存至: {save_dir}"))
        
        except Exception as e:
            self.update_sweep_info(f"批量测试出错: {str(e)}")
            self.sweep_status_var.set("批量测试出错")
            self.root.after(0, lambda: messagebox.showerror("错误", f"批量测试过程中出错:\n{str(e)}"))
        
        finally:
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_sweep_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            
            # 清除停止标志
            if hasattr(self, 'stop_requested'):
                self.stop_requested = False

    def _batch_test_single_file(self, sweep_file, sweep_type, recording_duration, save_dir):
        """批量测试中测试单个扫频文件"""
        try:
            # 确定源文件路径
            if sweep_type == "elephant":
                source_path = os.path.join(os.getcwd(), "audio", "elephant", sweep_file)
            else:  # custom
                source_path = os.path.join(os.getcwd(), "audio", "custom", sweep_file)
            
            if not os.path.exists(source_path):
                self.update_sweep_info(f"文件不存在: {source_path}")
                return False
            
            # 获取时间戳
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 设置设备上的临时文件路径
            device_audio_path = f"/sdcard/{sweep_file}"
            
            # 推送音频文件到设备
            self.update_sweep_info(f"正在推送音频文件: {sweep_file}")
            push_cmd = self.get_adb_command(f"push \"{source_path}\" {device_audio_path}")
            result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.update_sweep_info(f"推送音频文件失败")
                return False
            
            # 设置录制文件名
            file_base_name = os.path.splitext(sweep_file)[0]  # 获取不带扩展名的文件名
            recording_filename = f"{file_base_name}_recording_{timestamp}.wav"
            device_recording_path = f"/sdcard/{recording_filename}"
            local_path = os.path.join(save_dir, recording_filename)
            
            # 重命名文件如果已存在
            count = 1
            while os.path.exists(local_path):
                recording_filename = f"{file_base_name}_recording_{timestamp}_{count}.wav"
                local_path = os.path.join(save_dir, recording_filename)
                count += 1
            
            # 获取录制参数
            recording_device = self.sweep_recording_device_var.get().strip()
            recording_channels = self.sweep_recording_channels_var.get().strip()
            recording_rate = self.sweep_recording_rate_var.get().strip()
            recording_periods = self.sweep_recording_periods_var.get().strip()
            
            # 为了确保设备就绪，先重启audioserver
            for _ in range(2):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
                time.sleep(0.5)
            
            # 开始录制
            self.update_sweep_info("开始录制...")
            tinycap_cmd = f"shell tinycap {device_recording_path} -d {recording_device} -c {recording_channels} -r {recording_rate} -p {recording_periods}"
            tinycap_full_cmd = self.get_adb_command(tinycap_cmd)
            self.update_sweep_info(f"执行录音命令: {tinycap_cmd}")
            recording_process = subprocess.Popen(tinycap_full_cmd, shell=True)
            
            # 等待录制启动
            time.sleep(1)
            
            # 播放音频
            self.update_sweep_info("开始播放音频...")
            tinyplay_cmd = f"shell tinyplay {device_audio_path} -d 0"
            tinyplay_full_cmd = self.get_adb_command(tinyplay_cmd)
            self.update_sweep_info(f"执行播放命令: {tinyplay_cmd}")
            playback_process = subprocess.Popen(tinyplay_full_cmd, shell=True)
            
            # 等待指定的录制时长
            self.update_sweep_info(f"录制中，将在 {recording_duration} 秒后停止...")
            time.sleep(recording_duration)
            
            # 停止播放和录制
            self.update_sweep_info("停止播放...")
            subprocess.run(self.get_adb_command("shell killall tinyplay"), shell=True)
            
            self.update_sweep_info("停止录制...")
            subprocess.run(self.get_adb_command("shell killall tinycap"), shell=True)
            
            # 等待进程结束
            try:
                playback_process.wait(timeout=2)
            except:
                pass
                
            try:
                recording_process.wait(timeout=2)
            except:
                pass
            
            # 拉取录制文件
            self.update_sweep_info(f"拉取录制文件到: {local_path}")
            pull_cmd = self.get_adb_command(f"pull {device_recording_path} \"{local_path}\"")
            pull_result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            # 清理设备上的临时文件
            subprocess.run(self.get_adb_command(f"shell rm {device_audio_path}"), shell=True)
            subprocess.run(self.get_adb_command(f"shell rm {device_recording_path}"), shell=True)
            
            # 检查文件是否存在且大小合适
            if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
                self.update_sweep_info(f"测试成功: {sweep_file}")
                return True
            else:
                self.update_sweep_info(f"测试失败: 录制文件不存在或太小")
                return False
                
        except Exception as e:
            self.update_sweep_info(f"测试 {sweep_file} 出错: {str(e)}")
            return False

    def stop_sweep_test(self, auto_pull=False):
        """停止扫频测试"""
        try:
            self.update_sweep_info("正在停止测试...")
            
            # 设置停止标志，用于批量测试
            self.stop_requested = True
            
            # 停止播放进程
            subprocess.run(self.get_adb_command("shell killall tinyplay"), shell=True)
                
            # 停止录制进程
            subprocess.run(self.get_adb_command("shell killall tinycap"), shell=True)
            
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

    def pull_sweep_recording(self):
        """拉取扫频录音文件 - 参考Loopback测试的拉取逻辑"""
        if not hasattr(self, 'sweep_filename'):
            self.update_sweep_info("没有找到需要拉取的录音文件")
            return
        
        try:
            self.update_sweep_info("检查设备上的录制文件，路径信息:")
            
            # 检查/sdcard目录结构
            self.update_sweep_info("查看/sdcard目录结构:")
            ls_cmd = self.get_adb_command("shell ls -la /sdcard/")
            ls_result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            if ls_result.returncode == 0:
                self.update_sweep_info(f"/sdcard目录内容:\n{ls_result.stdout}")
            
            # 检查录制文件是否存在
            device_recording_path = f"/sdcard/{self.sweep_filename}"
            self.update_sweep_info(f"检查录制文件: {device_recording_path}")
            check_cmd = self.get_adb_command(f"shell ls -la {device_recording_path}")
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if check_result.returncode == 0:
                file_info = check_result.stdout.strip()
                self.update_sweep_info(f"找到文件: {device_recording_path}\n信息: {file_info}")
                
                # 获取保存路径
                save_dir = self.sweep_save_path_var.get().strip()
                if not save_dir:
                    save_dir = os.path.join(os.getcwd(), "sweep_recordings")
                
                os.makedirs(save_dir, exist_ok=True)
                local_path = os.path.join(save_dir, self.sweep_filename)
                
                # 拉取文件到本地
                self.update_sweep_info(f"正在拉取录制文件到: {local_path}")
                pull_cmd = self.get_adb_command(f"pull {device_recording_path} \"{local_path}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"拉取文件失败: {result.stderr}")
                
                # 检查文件是否存在且大于0
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    self.update_sweep_info(f"扫频测试完成，文件已保存为: {local_path}")
                    self.sweep_status_var.set("测试完成")
                    
                    # 询问是否打开文件夹
                    if messagebox.askyesno("测试完成", f"扫频测试完成，文件已保存为:\n{local_path}\n\n是否打开文件夹？"):
                        self.open_sweep_folder()
                else:
                    self.update_sweep_info(f"错误: 拉取的文件为空或不存在")
                    self.sweep_status_var.set("拉取文件失败")
            else:
                self.update_sweep_info(f"错误: 设备上未找到录制文件 {device_recording_path}")
                self.sweep_status_var.set("未找到录制文件")
            
        except Exception as e:
            self.update_sweep_info(f"拉取录音文件出错: {str(e)}")
            self.sweep_status_var.set(f"拉取录音出错")
            messagebox.showerror("错误", f"拉取录音文件时出错:\n{str(e)}")
    
    def browse_loopback_save_path(self):
        """浏览并选择Loopback测试保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择Loopback测试保存路径",
            initialdir=self.loopback_save_path_var.get()
        )
        
        if folder_path:
            self.loopback_save_path_var.set(folder_path)
            self.status_var.set(f"已设置Loopback测试保存路径: {folder_path}")

    def open_loopback_folder(self):
        """打开Loopback测试保存文件夹"""
        save_dir = self.loopback_save_path_var.get().strip()
        if not save_dir:
            save_dir = os.path.join(os.getcwd(), "test")
        
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
            self.loopback_status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def stop_loopback_test(self):
        """停止Loopback测试"""
        if not hasattr(self, 'loopback_process') or self.loopback_process is None:
            return
        
        try:
            # 停止录音进程
            subprocess.run(self.get_adb_command("shell pkill -f tinycap"), shell=True)
            self.loopback_process.terminate()
            
            # 停止播放
            subprocess.run(self.get_adb_command("shell pkill -f tinyplay"), shell=True)
            
            # 更新状态
            self.status_var.set("录制已停止，准备保存...")
            self.loopback_status_var.set("录制已停止")
            
            # 等待确保文件写入完成
            time.sleep(3)
            
            # 恢复按钮状态
            self.start_loopback_button.config(state="normal")
            self.stop_loopback_button.config(state="disabled")
            
            # 检查录制文件是否存在
            check_cmd = self.get_adb_command(f"shell ls -la /sdcard/{self.loopback_filename}")
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            # 判断文件是否存在
            if check_result.returncode != 0:
                self.status_var.set(f"警告: 无法找到录音文件 /sdcard/{self.loopback_filename}")
                messagebox.showwarning("警告", f"无法找到录音文件: /sdcard/{self.loopback_filename}")
                return
            
            # 自动保存文件
            # 获取保存目录
            save_dir = self.loopback_save_path_var.get()
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 设置保存文件名
            channels = self.loopback_channel_var.get()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"test_{channels}ch_{timestamp}.wav"
            local_path = os.path.join(save_dir, filename)
            
            # 从设备拉取文件
            self.status_var.set("正在保存录音文件...")
            pull_cmd = self.get_adb_command(f"pull /sdcard/{self.loopback_filename} \"{local_path}\"")
            result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.status_var.set(f"拉取文件失败: {result.stderr}")
                messagebox.showerror("错误", f"拉取录音文件失败:\n{result.stderr}")
                return
            
            # 删除设备上的临时文件
            subprocess.run(self.get_adb_command(f"shell rm /sdcard/{self.loopback_filename}"), shell=True)
            
            # 检查文件是否保存成功
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                self.status_var.set(f"通道测试完成，文件已保存为: {os.path.basename(local_path)}")
                self.loopback_status_var.set(f"测试完成，已保存: {os.path.basename(local_path)}")
                
                # 询问是否打开文件夹
                if messagebox.askyesno("测试完成", f"通道测试完成，文件已保存为:\n{local_path}\n\n是否打开文件夹？"):
                    self.open_loopback_folder()
            else:
                self.status_var.set("文件保存失败或文件为空")
                self.loopback_status_var.set("保存失败")
                messagebox.showerror("错误", "文件保存失败或文件为空，请检查设备状态")
        
        except Exception as e:
            self.status_var.set(f"停止录音出错: {str(e)}")
            self.loopback_status_var.set("停止录音失败")
            messagebox.showerror("错误", f"停止通道录音时出错:\n{str(e)}")
            
            # 确保按钮状态恢复
            self.start_loopback_button.config(state="normal")
            self.stop_loopback_button.config(state="disabled")

    def open_containing_folder(self, file_path):
        """打开包含指定文件的文件夹"""
        folder_path = os.path.dirname(file_path)
        try:
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path])
            else:  # Linux
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            self.status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")
    
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
                time.sleep(0.5)
            
            # 开始录制 - 使用正确的参数格式
            # 重要：确保正确的录制文件名
            self.loopback_filename = f"test_{channels}ch.wav"
            
            # 使用完整的录制命令
            record_cmd = self.get_adb_command(f"shell tinycap /sdcard/{self.loopback_filename} -D 0 -d {device} -c {channels} -r {rate} -p 480 -b 16")
            
            # 开始录制进程
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
                play_cmd = self.get_adb_command(f"shell tinyplay {remote_audio_file} -D 0 -d 0")
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
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"测试出错: {str(e)}"))
            self.root.after(0, lambda: self.loopback_status_var.set("测试出错"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
            
            # 恢复按钮状态
            self.root.after(0, lambda: self.start_loopback_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_loopback_button.config(state="disabled"))

    def run_loopback_test(self):
        """运行Loopback或Ref通道测试"""
        if not self.check_device_selected():
            return
            
        device = self.loopback_device_var.get()
        channels = self.loopback_channel_var.get()
        rate = self.loopback_rate_var.get()
        audio_source = self.audio_source_var.get()
        
        # 检查自定义音频文件
        if audio_source == "custom" and not hasattr(self, 'selected_audio_file'):
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
    
    def add_hal_prop(self):
        """添加HAL录音属性，格式为 prop_name value"""
        prop_text = self.hal_prop_var.get().strip()
        if not prop_text:
            messagebox.showerror("错误", "请输入属性名称和值，格式为: 属性名 值")
            return
        
        # 分割属性名和值
        parts = prop_text.split()
        if len(parts) < 2:
            messagebox.showerror("错误", "格式错误，请输入属性名和值，例如: vendor.media.audiohal.vpp.dump 1")
            return
        
        prop_name = parts[0]
        prop_value = parts[1]
        
        # 检查是否已存在
        if prop_name in self.hal_props:
            messagebox.showwarning("警告", f"属性 '{prop_name}' 已存在")
            return
        
        # 添加到UI
        self.add_prop_to_ui(prop_name, prop_value)
        self.hal_prop_var.set("")  # 清空输入框
        self.hal_status_var.set(f"已添加属性: {prop_name} {prop_value}")

    def add_prop_to_ui(self, prop_name, prop_value="1"):
        """将属性添加到UI界面"""
        if prop_name in self.hal_props and hasattr(self.hal_props[prop_name], 'frame'):
            return  # 属性已存在
        
        # 创建属性行
        prop_frame = ttk.Frame(self.props_container)
        prop_frame.pack(fill="x", pady=1)
        
        # 创建复选框
        var = tk.BooleanVar(value=True)
        var.frame = prop_frame  # 保存对应的frame引用
        var.value = prop_value  # 保存属性值
        self.hal_props[prop_name] = var
        
        # 显示格式: [√] prop_name prop_value (中间是空格而不是等号)
        cb = ttk.Checkbutton(prop_frame, text=f"{prop_name} {prop_value}", variable=var, style="Small.TCheckbutton")
        cb.pack(side="left", padx=2, fill="x", expand=True)


    def add_logcat_prop(self):
        """添加日志属性"""
        prop_text = self.logcat_prop_var.get().strip()
        if not prop_text:
            messagebox.showerror("错误", "请输入属性名称和值，格式为: 属性名 值")
            return
        
        # 分割属性名和值
        parts = prop_text.split()
        if len(parts) < 2:
            messagebox.showerror("错误", "格式错误，请输入属性名和值，例如: vendor.media.audiohal.log 1")
            return
        
        prop_name = parts[0]
        prop_value = parts[1]
        
        # 检查是否已存在
        for prop in self.logcat_props_vars:
            if prop["name"] == prop_name:
                messagebox.showerror("错误", f"属性 {prop_name} 已存在")
                return
        
        # 添加到列表
        self.add_prop_to_list(prop_name, prop_value)
        
        # 清空输入框
        self.logcat_prop_var.set("")
        
        self.update_logcat_status(f"已添加属性: {prop_name}={prop_value}")

    def add_prop_to_list(self, prop_name, prop_value="1"):
        """将属性添加到列表显示"""
        # 创建属性框架
        prop_frame = ttk.Frame(self.logcat_props_frame)
        prop_frame.pack(fill="x", padx=2, pady=1)
        
        # 复选框
        var = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(prop_frame, variable=var, text="")
        check.pack(side="left", padx=1)
        
        # 属性名标签 - 使用更小的字体，显示为"属性名 属性值"
        prop_label = ttk.Label(prop_frame, text=f"{prop_name} {prop_value}", font=("Arial", 9))
        prop_label.pack(side="left", padx=2, fill="x", expand=True)
        
        # 保存属性信息
        self.logcat_props_vars.append({
            "name": prop_name,
            "var": var,
            "value": prop_value,
            "frame": prop_frame
        })
        
        # 更新Canvas滚动区域
        self.logcat_props_frame.update_idletasks()
        self.logcat_canvas.configure(scrollregion=self.logcat_canvas.bbox("all"))
    
    def update_logcat_status(self, message):
        """更新日志状态信息"""
        self.logcat_status_text.config(state="normal")
        self.logcat_status_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.logcat_status_text.see(tk.END)
        self.logcat_status_text.config(state="disabled")
    