import queue
import subprocess
import threading
import time
import os
import platform
import shutil
import sys
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import re

from optional_deps import try_import_pygame
from output_paths import (
    OUTPUT_ROOT,
    get_output_dir,
    ensure_output_dir,
    DIR_LOGCAT,
    DIR_SCREENSHOTS,
    DIR_MIC_TEST,
    DIR_SWEEP_RECORDINGS,
    DIR_HAL_DUMP,
    DIR_HAL_CUSTOM,
)

class TestOperations:
    def __init__(self, parent):
        self.parent = parent

    def _get_pygame(self):
        """
        获取 pygame 模块（按需导入）。

        - 启动时不导入 pygame，避免在部分 PyInstaller + numpy 环境下崩溃。
        - 仅当用户使用“本地播放”相关功能时才尝试导入/初始化。
        """
        # AudioTestTool 会尽量初始化，但这里仍做兜底
        if hasattr(self, "_pygame") and self._pygame is not None:
            return self._pygame

        pg, err = try_import_pygame()
        self._pygame = pg
        self._pygame_error = err
        if not pg:
            return None

        try:
            if not pg.mixer.get_init():
                pg.mixer.init()
        except Exception as e:
            self._pygame = None
            self._pygame_error = f"{type(e).__name__}: {e}"
            return None

        return self._pygame
    def start_mic_test(self):
        """开始麦克风测试"""
        print("=== 开始麦克风测试 ===")
        
        # 详细调试信息
        print(f"DEBUG: hasattr(self, 'device_combobox'): {hasattr(self, 'device_combobox')}")
        if hasattr(self, 'device_combobox'):
            print(f"DEBUG: device_combobox.get(): '{self.device_combobox.get()}'")
        
        print(f"DEBUG: hasattr(self, 'device_var'): {hasattr(self, 'device_var')}")
        if hasattr(self, 'device_var'):
            print(f"DEBUG: device_var.get(): '{self.device_var.get()}'")
        
        print(f"DEBUG: hasattr(self, 'selected_device'): {hasattr(self, 'selected_device')}")
        print(f"DEBUG: selected_device value: '{getattr(self, 'selected_device', 'UNDEFINED')}'")
        
        # 直接测试 adb devices 命令
        try:
            import subprocess
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
            print(f"DEBUG: adb devices 返回码: {result.returncode}")
            print(f"DEBUG: adb devices 输出:\n{result.stdout}")
            if result.stderr:
                print(f"DEBUG: adb devices 错误: {result.stderr}")
        except Exception as e:
            print(f"DEBUG: adb devices 执行失败: {e}")
        
        # 防止重复启动
        if getattr(self, '_starting_mic_test', False):
            print("麦克风测试已在启动中，跳过")
            return
        
        if getattr(self, 'mic_is_testing', False):
            print("麦克风测试已在进行中")
            self.root.after(0, lambda: self.mic_info_var.set("麦克风测试进行中..."))
            return
        
        self._starting_mic_test = True
        
        try:
            # 检查设备选择
            print("检查设备选择状态...")
            if not self.check_device_selected():
                print("设备检查失败，终止麦克风测试")
                self.root.after(0, lambda: self.mic_info_var.set("请先选择设备"))
                return
            
            print("设备检查通过，继续麦克风测试...")
            
            # 获取测试参数
            try:
                mic_count_raw = (self.mic_count_var.get() or "").strip()
                mic_count = int(mic_count_raw or "1")
                if mic_count <= 0:
                    raise ValueError("mic_count must be > 0")
                pcm_device = self.pcm_device_var.get() or "0"
                # tinycap 的 -d 是声卡/设备ID，来自麦克风测试设置区，不是ADB设备序列号
                device_id = (self.device_id_var.get() if hasattr(self, "device_id_var") else "").strip() or "0"
                rate_raw = (self.rate_var.get() or "").strip()
                rate = int(rate_raw or "48000")
                if rate <= 0:
                    raise ValueError("rate must be > 0")
                
                print(f"测试参数 - 麦克风数量: {mic_count}, PCM设备: {pcm_device}, 设备ID: {device_id}, 采样率: {rate}")
                
            except ValueError as e:
                print(f"参数解析错误: {e}")
                self.root.after(0, lambda: self.mic_info_var.set("参数格式错误：麦克风数量/采样率需为正整数"))
                return
            
            # 设置保存路径
            local_save_path = self.mic_save_path_var.get() or get_output_dir(DIR_MIC_TEST)
            if not os.path.exists(local_save_path):
                os.makedirs(local_save_path)
                print(f"创建本地保存目录: {local_save_path}")
            
            device_path = "/data/local/tmp"
            
            # 更新UI状态
            self.root.after(0, lambda: self.mic_info_var.set("正在启动麦克风测试..."))
            
            # 启动测试线程
            self.mic_is_testing = True
            # 注意：_mic_thread_running 只应该在线程内部置 True，
            # 否则线程会误判为“重复运行”并直接退出
            self._mic_thread_running = False

            # 更新按钮状态：开始不可点、停止可点（保持你截图里的绿/红配色）
            def _set_buttons_running():
                if hasattr(self, 'start_mic_button'):
                    self.start_mic_button.config(state="disabled")
                if hasattr(self, 'stop_mic_button'):
                    self.stop_mic_button.config(state="normal")
            self.root.after(0, _set_buttons_running)
            
            test_thread = threading.Thread(
                target=self._mic_test_thread,
                args=(mic_count, pcm_device, device_id, rate, device_path, local_save_path),
                daemon=True
            )
            test_thread.start()
            print("麦克风测试线程已启动")
            
        except Exception as e:
            print(f"启动麦克风测试时出错: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: self.mic_info_var.set(f"启动失败: {str(e)}"))

            # 启动失败：回滚按钮状态
            self.mic_is_testing = False
            self._mic_thread_running = False
            def _set_buttons_idle():
                if hasattr(self, 'start_mic_button'):
                    self.start_mic_button.config(state="normal")
                if hasattr(self, 'stop_mic_button'):
                    self.stop_mic_button.config(state="disabled")
            self.root.after(0, _set_buttons_idle)
        finally:
            self._starting_mic_test = False

    def _mic_test_thread(self, mic_count, pcm_device, device_id, rate, device_path, local_save_path):
        """麦克风测试线程"""
        print(f"=== 麦克风测试线程启动 ===")
        print(f"参数: mic_count={mic_count}, pcm_device={pcm_device}, device_id={device_id}, rate={rate}")
        print(f"设备路径: {device_path}, 本地路径: {local_save_path}")
        
        def safe_update_ui(message):
            """安全更新UI"""
            try:
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, lambda: self.mic_info_var.set(message))
            except Exception as e:
                print(f"UI更新失败: {e}")
        
        try:
            # 防止重复运行
            if hasattr(self, '_mic_thread_running') and self._mic_thread_running:
                print("检测到线程重复运行，退出")
                return
            self._mic_thread_running = True
            
            safe_update_ui("正在获取root权限...")
            
            # 获取root权限
            print("执行 adb root...")
            root_cmd = self.get_adb_command("root")
            result = subprocess.run(root_cmd, shell=True, capture_output=True, text=True, timeout=10)
            print(f"adb root 结果: 返回码={result.returncode}")
            if result.stdout:
                print(f"adb root 输出: {result.stdout.strip()}")
            if result.stderr:
                print(f"adb root 错误: {result.stderr.strip()}")
            
            # 等待root权限生效
            import time
            time.sleep(2)
            
            safe_update_ui("正在创建设备目录...")
            
            # 创建设备目录
            mkdir_cmd = self.get_adb_command(f"shell mkdir -p {device_path}")
            print(f"执行创建目录命令: {mkdir_cmd}")
            result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True, timeout=10)
            print(f"mkdir 结果: 返回码={result.returncode}")
            if result.returncode != 0:
                error_msg = f"创建设备目录失败: {result.stderr.strip() if result.stderr else '未知错误'}"
                print(error_msg)
                safe_update_ui(error_msg)
                return
            
            # 生成录制文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.mic_filename = f"mic_test_{mic_count}ch_{timestamp}.wav"
            full_device_path = f"{device_path}/{self.mic_filename}"
            
            print(f"录制文件: {self.mic_filename}")
            safe_update_ui(f"开始录制: {self.mic_filename}")
            
            # 构建录制命令
            tinycap_cmd = f"shell tinycap {full_device_path} -D {pcm_device} -d {device_id} -c {mic_count} -r {rate}"
            full_cmd = self.get_adb_command(tinycap_cmd)
            
            print(f"执行录制命令: {full_cmd}")
            
            # 启动录制进程
            self.mic_process = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            print(f"录制进程已启动，PID: {self.mic_process.pid}")
            safe_update_ui("录制中...请对着麦克风说话")
            
            # 检查进程是否正常启动
            time.sleep(3)
            if self.mic_process.poll() is not None:
                # 进程已退出
                stdout, stderr = self.mic_process.communicate()
                error_msg = f"录制进程启动失败: {stderr.strip() if stderr else stdout.strip()}"
                print(error_msg)
                safe_update_ui(error_msg)
                return
            
            print("录制进程正在运行")
            safe_update_ui("录制中... (点击停止录制结束)")
            
            # 保持线程运行，直到被停止
            while self.mic_process.poll() is None and self.mic_is_testing:
                time.sleep(1)
            
            print("录制线程结束")
            
        except Exception as e:
            error_msg = f"录制过程出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            safe_update_ui(error_msg)
            
        finally:
            # 清理状态
            self._mic_thread_running = False
            print("线程清理完成")

    def stop_mic_test(self):
        """停止麦克风测试"""
        print("=== 停止麦克风测试 ===")
        
        try:
            # 设置停止标志
            self.mic_is_testing = False
            self._mic_thread_running = False
            self.mic_info_var.set("正在停止录制...")
            
            # 终止录制进程
            if hasattr(self, 'mic_process') and self.mic_process:
                print(f"终止录制进程 PID: {self.mic_process.pid}")
                
                # 在设备上杀死tinycap进程
                kill_cmd = self.get_adb_command("shell pkill -f tinycap")
                print(f"执行杀死进程命令: {kill_cmd}")
                subprocess.run(kill_cmd, shell=True, timeout=5)
                
                # 终止本地进程
                try:
                    self.mic_process.terminate()
                    self.mic_process.wait(timeout=5)
                except:
                    self.mic_process.kill()
                
                print("录制进程已终止")
            
            # 拉取录制文件
            if hasattr(self, 'mic_filename') and self.mic_filename:
                device_file = f"/data/local/tmp/{self.mic_filename}"
                local_file = os.path.join(self.mic_save_path_var.get(), self.mic_filename)
                
                print(f"拉取文件: {device_file} -> {local_file}")
                self.mic_info_var.set("正在保存录制文件...")
                
                pull_cmd = self.get_adb_command(f"pull {device_file} {local_file}")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0 and os.path.exists(local_file):
                    file_size = os.path.getsize(local_file)
                    print(f"文件保存成功: {local_file} ({file_size} bytes)")
                    self.mic_info_var.set(f"录制完成，文件已保存: {self.mic_filename}")

                    # 自动打开录音文件所在文件夹（用户要求：录制完成后自动打开）
                    try:
                        save_dir = os.path.dirname(os.path.abspath(local_file))
                        if platform.system() == "Windows":
                            os.startfile(save_dir)
                        elif platform.system() == "Darwin":
                            subprocess.run(["open", save_dir])
                        else:
                            subprocess.run(["xdg-open", save_dir])
                    except Exception as e:
                        print(f"自动打开文件夹失败: {e}")
                    
                    # 清理设备上的临时文件
                    rm_cmd = self.get_adb_command(f"shell rm {device_file}")
                    subprocess.run(rm_cmd, shell=True, timeout=5)
                else:
                    error_msg = f"文件保存失败: {result.stderr.strip() if result.stderr else '未知错误'}"
                    print(error_msg)
                    self.mic_info_var.set(error_msg)
            
        except Exception as e:
            error_msg = f"停止录制时出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            self.mic_info_var.set(error_msg)
            
        finally:
            # 恢复按钮状态
            if hasattr(self, 'start_mic_button'):
                self.start_mic_button.config(state="normal")
            if hasattr(self, 'stop_mic_button'):
                self.stop_mic_button.config(state="disabled")
            
            # 清理变量
            self.mic_process = None
            self.mic_filename = None
            
            print("停止录制完成")

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
                # 默认测试音频：用户自备（不再自动生成/不再内置）
                audio_file = os.path.join("audio", "Nums_7dot1_16_48000.wav")
                if not os.path.exists(audio_file):
                    msg = (
                        "默认测试音频不存在：audio/Nums_7dot1_16_48000.wav\n\n"
                        "请把对应的测试音频放到 audio 目录，或切换为“自定义音频”。"
                    )
                    self.root.after(0, lambda: messagebox.showerror("缺少音频文件", msg))
                    self.root.after(0, lambda: self.start_loopback_button.config(state="normal"))
                    self.root.after(0, lambda: self.stop_loopback_button.config(state="disabled"))
                    return
                subprocess.run(self.get_adb_command(f"push \"{audio_file}\" /sdcard/test_audio.wav"), shell=True)
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
                play_cmd = self.get_adb_command(f"shell tinyplay {remote_audio_file}")
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
                initialdir=OUTPUT_ROOT,
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
            # 获取所有选中的属性
            enabled_props = []
            for prop, var in self.hal_props.items():
                if var.get():
                    value = var.value if hasattr(var, 'value') else "1"
                    enabled_props.append((prop, value))
            
            if not enabled_props:
                messagebox.showwarning("警告", "请至少选择一个录音属性")
                return
            
            # 更新状态
            self.hal_status_var.set("正在开始录音...")
            self.hal_recording_status_var.set("正在开始...")
            
            # 禁用开始按钮，启用停止按钮
            self.start_hal_button.config(state="disabled")
            self.stop_hal_button.config(state="normal")
            
            # 设置所有选中的属性
            for prop, value in enabled_props:
                set_cmd = self.get_adb_command(f"shell setprop {prop} {value}")
                result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"设置属性 {prop} 失败: {result.stderr}")
                self.update_info_text(f"已设置: {prop}={value}")
            
            # 记录开始时间
            start_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self.hal_start_time_var.set(start_time)
            
            # 更新状态
            self.hal_status_var.set("录音已开始")
            self.hal_recording_status_var.set("录音中")
            
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
            
            # 禁用所有录音属性
            for prop, var in self.hal_props.items():
                if var.get():
                    set_cmd = self.get_adb_command(f"shell setprop {prop} 0")
                    result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)
                    self.update_info_text(f"已关闭: {prop}=0")
            
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
    
    def take_screenshot(self):
        """截取屏幕截图 - 修复递归调用问题"""
        if not self.check_device_selected():
            return
    
        try:
            # 更新状态
            if hasattr(self, 'screenshot_status_var'):
                self.screenshot_status_var.set("正在截取屏幕...")
            
            # 获取保存路径
            save_dir = get_output_dir(DIR_SCREENSHOTS)
            if hasattr(self, 'screenshot_save_path_var'):
                save_dir = self.screenshot_save_path_var.get().strip()
                if not save_dir:
                    save_dir = get_output_dir(DIR_SCREENSHOTS)
            
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            local_path = os.path.join(save_dir, filename)
            
            # 执行截图命令
            cmd = self.get_adb_command("exec-out screencap -p")
            result = subprocess.run(cmd, shell=True, capture_output=True)
            
            if result.returncode != 0:
                raise Exception(f"截图命令执行失败")
            
            # 保存截图数据
            with open(local_path, 'wb') as f:
                f.write(result.stdout)
            
            # 检查文件是否保存成功
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                success_msg = f"截图成功保存: {filename}"
                if hasattr(self, 'screenshot_status_var'):
                    self.screenshot_status_var.set("截图完成")
                if hasattr(self, 'update_screenshot_info'):
                    self.update_screenshot_info(success_msg)
                    self.update_screenshot_info(f"文件路径: {local_path}")
                
                # 询问是否打开文件夹
                if messagebox.askyesno("截图完成", f"截图已保存为:\n{local_path}\n\n是否打开文件夹？"):
                    self.open_screenshot_folder()
            else:
                raise Exception("截图文件保存失败或文件为空")
            
        except Exception as e:
            error_msg = f"截图出错: {str(e)}"
            if hasattr(self, 'screenshot_status_var'):
                self.screenshot_status_var.set(error_msg)
            if hasattr(self, 'update_screenshot_info'):
                self.update_screenshot_info(error_msg)
            messagebox.showerror("错误", f"截图时出错:\n{str(e)}")

    def open_screenshot_folder(self):
        """打开截图保存文件夹"""
        save_dir = get_output_dir(DIR_SCREENSHOTS)
        if hasattr(self, 'screenshot_save_path_var'):
            save_dir = self.screenshot_save_path_var.get().strip()
            if not save_dir:
                save_dir = get_output_dir(DIR_SCREENSHOTS)
        
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
            error_msg = f"打开文件夹出错: {str(e)}"
            if hasattr(self, 'screenshot_status_var'):
                self.screenshot_status_var.set(error_msg)
            if hasattr(self, 'update_screenshot_info'):
                self.update_screenshot_info(error_msg)
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
                save_dir = get_output_dir(DIR_SWEEP_RECORDINGS)
            
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
            recording_periods = "256"  # 默认周期大小
            
            # 开始录制 - 使用提供的tinycap命令格式
            self.update_sweep_info("开始录制...")
            self.sweep_status_var.set("正在录制...")
            
            # 使用参数构建tinycap命令
            tinycap_cmd = f"shell \"tinycap {device_recording_path} -D 0 -d {recording_device} -r {recording_rate} -c {recording_channels} -p {recording_periods}\""
            tinycap_full_cmd = self.get_adb_command(tinycap_cmd)
            self.update_sweep_info(f"执行录音命令: {tinycap_full_cmd}")
            self.recording_process = subprocess.Popen(tinycap_full_cmd, shell=True)
            
            # 等待录制启动
            time.sleep(2)
            
            # 播放音频 - 使用提供的tinyplay命令格式
            self.update_sweep_info("开始播放音频...")
            
            # 使用参数构建tinyplay命令
            tinyplay_cmd = f"shell tinyplay {device_audio_path} -d 0 -D 0 -r {recording_rate} -c {recording_channels} -b {recording_bits}"
            tinyplay_full_cmd = self.get_adb_command(tinyplay_cmd)
            self.update_sweep_info(f"执行播放命令: {tinyplay_full_cmd}")
            self.playback_process = subprocess.Popen(tinyplay_full_cmd, shell=True)
            
            # 启动监控线程
            self.sweep_monitor_thread = threading.Thread(
                target=self.monitor_sweep_test, 
                args=(device_recording_path, save_dir, recording_filename, sweep_file, float(self.sweep_recording_duration_var.get()), device_audio_path)
            )
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
            if hasattr(self, 'playback_process') and self.playback_process.poll() is None:
                # 使用killall命令停止tinyplay
                kill_cmd = self.get_adb_command("shell killall tinyplay")
                subprocess.run(kill_cmd, shell=True)
                
                # 等待进程结束
                for i in range(5):
                    if self.playback_process.poll() is not None:
                        break
                    time.sleep(0.5)
                
                self.update_sweep_info("已停止播放")
            
            # 停止录制进程
            if hasattr(self, 'recording_process') and self.recording_process.poll() is None:
                # 使用killall命令停止tinycap
                kill_cmd = self.get_adb_command("shell killall tinycap")
                subprocess.run(kill_cmd, shell=True)
                
                # 等待进程结束
                for i in range(5):
                    if self.recording_process.poll() is not None:
                        break
                    time.sleep(0.5)
                
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
            if hasattr(self, 'playback_process'):
                self.update_sweep_info("等待播放完成...")
                self.playback_process.wait()
                self.update_sweep_info("播放已完成")
            
            # 等待一段时间确保录制完整
            time.sleep(5)
            
            # 检查设备上的可用录制文件
            self.update_sweep_info("检查设备上的录制文件，路径信息:")
            
            # 检查/sdcard目录结构
            self.update_sweep_info("查看/sdcard目录结构:")
            ls_cmd = self.get_adb_command("shell ls -la /sdcard/")
            ls_result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            if ls_result.returncode == 0:
                self.update_sweep_info(f"/sdcard目录内容:\n{ls_result.stdout}")
            
            # 检查录制文件是否存在
            self.update_sweep_info(f"检查录制文件: {device_recording_path}")
            check_cmd = self.get_adb_command(f"shell ls -la {device_recording_path}")
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if check_result.returncode == 0:
                file_info = check_result.stdout.strip()
                self.update_sweep_info(f"找到文件: {device_recording_path}\n信息: {file_info}")
                
                # 检查文件大小
                size_match = re.search(r'\s(\d+)\s', file_info)
                if size_match:
                    size = int(size_match.group(1))
                    if size > 1000:  # 只选择大于1KB的文件
                        self.update_sweep_info(f"文件大小正常: {size/1024:.2f} KB")
                        
                        # 拉取文件到本地
                        self.update_sweep_info(f"正在拉取录制文件: {device_recording_path}")
                        local_path = os.path.join(save_dir, recording_filename)
                        
                        pull_cmd = self.get_adb_command(f"pull {device_recording_path} \"{local_path}\"")
                        result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                        
                        if result.returncode != 0:
                            self.update_sweep_info(f"拉取录制文件失败: {result.stderr}")
                        else:
                            self.update_sweep_info(f"文件成功拉取并保存到: {local_path}")
                            
                            # 删除设备上的临时文件
                            self.update_sweep_info("正在清理临时文件...")
                            rm_cmd = self.get_adb_command(f"shell rm {device_recording_path}")
                            subprocess.run(rm_cmd, shell=True)
                            
                            rm_audio_cmd = self.get_adb_command(f"shell rm {device_audio_path}")
                            subprocess.run(rm_audio_cmd, shell=True)
                            
                            self.sweep_status_var.set("测试完成")
                            self.update_sweep_info(f"扫频测试完成，录制文件已保存到: {local_path}")
                    else:
                        self.update_sweep_info(f"警告: 文件太小: {size/1024:.2f} KB")
                else:
                    self.update_sweep_info(f"警告: 无法确定文件大小")
            else:
                self.update_sweep_info(f"错误: 文件 {device_recording_path} 不存在")
                
                # 尝试查找其他可能的录音文件
                self.update_sweep_info("尝试查找其他可能的录音文件...")
                find_cmd = self.get_adb_command("shell find /sdcard -name \"*.wav\" -mmin -5")
                find_result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
                
                if find_result.stdout.strip():
                    found_files = find_result.stdout.strip().split("\n")
                    self.update_sweep_info(f"找到 {len(found_files)} 个最近创建的WAV文件")
                    
                    # 尝试拉取第一个文件
                    if found_files:
                        alt_file = found_files[0]
                        self.update_sweep_info(f"尝试拉取替代文件: {alt_file}")
                        
                        alt_local_path = os.path.join(save_dir, recording_filename)
                        alt_pull_cmd = self.get_adb_command(f"pull {alt_file} \"{alt_local_path}\"")
                        alt_result = subprocess.run(alt_pull_cmd, shell=True, capture_output=True, text=True)
                        
                        if alt_result.returncode == 0:
                            self.update_sweep_info(f"成功拉取替代文件到: {alt_local_path}")
                            
                            # 删除设备上的临时文件
                            subprocess.run(self.get_adb_command(f"shell rm {alt_file}"), shell=True)
                            subprocess.run(self.get_adb_command(f"shell rm {device_audio_path}"), shell=True)
                            
                            self.sweep_status_var.set("测试完成")
                        else:
                            self.update_sweep_info(f"拉取替代文件失败: {alt_result.stderr}")
                else:
                    self.update_sweep_info("未找到任何最近创建的WAV文件")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")
            
        except Exception as e:
            self.update_sweep_info(f"监控测试过程中出错: {str(e)}")
            self.sweep_status_var.set(f"监控出错")
            # 确保按钮状态恢复
            self.root.after(0, lambda: self.start_sweep_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_sweep_button.config(state="disabled"))

    def open_sweep_folder(self):
        """打开扫频测试保存文件夹"""
        save_dir = self.sweep_save_path_var.get().strip()
        if not save_dir:
            save_dir = get_output_dir(DIR_SWEEP_RECORDINGS)
        
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

    def pause_local_audio(self):
        """暂停本地音频播放"""
        try:
            pg = self._get_pygame()
            if not pg:
                messagebox.showwarning("提示", f"本地播放不可用（pygame 初始化失败）\n{getattr(self, '_pygame_error', '')}")
                return
            pg.mixer.music.pause()
            
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
                pg = self._get_pygame()
                if pg and pg.mixer.get_init() and pg.mixer.music.get_busy():
                    pg.mixer.music.stop()
                    self.playback_status_var.set("已停止")
                    self.status_var.set("就绪")
        except Exception:
            # 忽略停止过程中的错误
            pass
    
    def update_volume(self, *args):
        """更新音频播放音量"""
        try:
            pg = self._get_pygame()
            if pg and pg.mixer.get_init() and pg.mixer.music.get_busy():
                pg.mixer.music.set_volume(self.volume_var.get())
        except Exception:
            # 忽略音量调整过程中的错误
            pass
    
    def update_playback_progress(self):
        """更新播放进度"""
        pg = self._get_pygame()
        if not pg:
            return
        if pg.mixer.music.get_busy():
            # 获取音频长度（这需要额外的库支持，如mutagen）
            # 这里简化处理，假设进度线性增长
            current_pos = pg.mixer.music.get_pos() / 1000  # 转换为秒
            
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

    
    def create_default_test_audio(self):
        """创建默认测试音频文件"""
        try:
            # 不再自动生成音频：仅检查默认文件是否存在
            audio_file = os.path.join("audio", "Nums_7dot1_16_48000.wav")
            if os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                return audio_file
            return None
            
        except Exception as e:
            print(f"创建默认测试音频失败: {str(e)}")
            return None

    
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
        debug_info = "声测大师(AcouTest)调试信息\n"
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
                initialdir=OUTPUT_ROOT,
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
            pg = self._get_pygame()
            if not pg:
                return
            while pg.mixer.get_init() and pg.mixer.music.get_busy():
                time.sleep(0.5)
            
            # 播放结束
            if pg.mixer.get_init() and not pg.mixer.music.get_busy():
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
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.speech.dump 1"), shell=True)
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
            subprocess.run(self.get_adb_command("shell setprop vendor.media.audiohal.speech.dump 0"), shell=True)
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
            base_save_dir = filedialog.askdirectory(title="选择保存目录", initialdir=OUTPUT_ROOT)
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
        
        # 清空当前列表和UI
        for prop, var in list(self.hal_props.items()):
            if hasattr(var, 'frame'):
                var.frame.destroy()
        self.hal_props.clear()
        
        # 添加默认属性
        default_props = [
            "vendor.media.audiohal.vpp.dump 1",
            "vendor.media.audiohal.speech.dump 1",
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
        
        self.hal_status_var.set("已重置为默认属性")

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
            save_dir = filedialog.askdirectory(title="选择保存目录", initialdir=OUTPUT_ROOT)
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

    def remove_prop_from_ui(self, prop, frame):
        """从UI界面移除属性"""
        if prop in self.hal_props:
            del self.hal_props[prop]
        frame.destroy()
        self.hal_status_var.set(f"已删除属性: {prop}")

    def add_hal_prop(self):
        """添加HAL录音属性，格式为 prop_name value"""
        prop_text = self.hal_prop_var.get().strip()
        if not prop_text:
            messagebox.showwarning("警告", "请输入属性名称和值，格式为: 属性名 值")
            return
        
        # 分割属性名和值
        parts = prop_text.split()
        prop_name = parts[0]
        prop_value = parts[1] if len(parts) > 1 else "1"
        
        # 检查是否已存在
        if prop_name in self.hal_props:
            messagebox.showwarning("警告", f"属性 '{prop_name}' 已存在")
            return
        
        # 添加到UI
        self.add_prop_to_ui(prop_name, prop_value)
        self.hal_prop_var.set("")  # 清空输入框
        self.hal_status_var.set(f"已添加属性: {prop_name} {prop_value}")

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
        """停止HAL录音并自动拉取文件（耗时操作在后台线程，避免界面卡顿与重复点击）"""
        if not self.check_device_selected():
            return
        if getattr(self, "_hal_stopping", False):
            return  # 防止重复点击
        self._hal_stopping = True

        # 立即更新 UI：禁用停止按钮、显示“正在停止”
        self.hal_status_var.set("正在停止录音...")
        self.hal_recording_status_var.set("正在停止...")
        self.stop_hal_button.config(state="disabled")

        start_hal_button = self.start_hal_button
        stop_hal_button = self.stop_hal_button

        def _worker():
            try:
                # 取消定时器（如果存在）
                if hasattr(self, 'hal_timer') and self.hal_timer:
                    try:
                        self.hal_timer.cancel()
                    except Exception:
                        pass
                    self.hal_timer = None

                # 获取所有属性并禁用
                all_props = list(self.hal_props.keys())
                self._safe_update_info("正在关闭录音属性...")
                for prop in all_props:
                    set_cmd = self.get_adb_command(f"shell setprop {prop} 0")
                    subprocess.run(set_cmd, shell=True)
                self._safe_update_info("属性已关闭，等待文件写入...")
                time.sleep(1)

                # 记录结束时间与持续时间
                end_time = time.strftime("%Y-%m-%d %H:%M:%S")
                start_time = getattr(self, "hal_start_time_var", None) and self.hal_start_time_var.get() or "-"
                if start_time != "-":
                    duration = self.calculate_duration(start_time, end_time)
                else:
                    duration = "未知"
                self._safe_update_info(f"录音已停止，持续时间: {duration}")
                self._safe_set_hal_status("正在拉取录音文件...")

                # 自动拉取（内部会通过 _safe_update_info 更新进度）
                self._auto_pull_hal_files_impl()

                self._safe_finish_stop_hal(
                    start_hal_button, stop_hal_button,
                    getattr(self, "_hal_pull_final_status", "就绪"),
                    "已停止"
                )
            except Exception as e:
                self._safe_update_info(f"停止/拉取出错: {str(e)}")
                self._safe_finish_stop_hal(
                    start_hal_button, stop_hal_button,
                    f"停止录音出错: {str(e)}",
                    "停止失败"
                )
                root = self._get_root()
                if root:
                    root.after(0, lambda: messagebox.showerror("错误", f"停止录音时出错:\n{str(e)}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _auto_pull_hal_files_impl(self):
        """自动拉取HAL录音文件（在后台线程中调用，通过 _safe_update_info 更新录音信息与进度）"""
        if not self.check_device_selected():
            return

        directory = (getattr(self, "hal_dir_var", None) and self.hal_dir_var.get() or "").strip()
        if not directory:
            self._safe_update_info("错误: 录音目录未设置")
            setattr(self, "_hal_pull_final_status", "错误: 录音目录未设置")
            return

        base_save_dir = (getattr(self, "hal_save_path_var", None) and self.hal_save_path_var.get() or "").strip()
        if not base_save_dir:
            base_save_dir = ensure_output_dir(DIR_HAL_DUMP)
            root = self._get_root()
            if root and getattr(self, "hal_save_path_var", None):
                root.after(0, lambda: self.hal_save_path_var.set(base_save_dir))

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(base_save_dir, f"hal_dump_{timestamp}")

        try:
            self._safe_set_hal_status("正在拉取录音文件...")
            self._safe_update_info("正在获取设备上的文件列表...")
            os.makedirs(save_dir, exist_ok=True)

            ls_cmd = self.get_adb_command(f"shell ls -la {directory}")
            result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"获取文件列表失败: {result.stderr}")

            lines = result.stdout.strip().split('\n')
            files_to_pull = []
            for line in lines:
                if line.endswith('.pcm') or line.endswith('.raw'):
                    parts = line.split()
                    if len(parts) >= 8:
                        files_to_pull.append(parts[-1])

            if not files_to_pull:
                self._safe_update_info("未找到录音文件")
                self._safe_set_hal_status("未找到录音文件")
                setattr(self, "_hal_pull_final_status", "未找到录音文件")
                return

            total = len(files_to_pull)
            self._safe_update_info(f"找到 {total} 个录音文件，开始拉取...")
            success_count = 0

            for idx, filename in enumerate(files_to_pull, 1):
                self._safe_update_info(f"正在拉取 ({idx}/{total}): {filename}")
                self._safe_set_hal_status(f"正在拉取 ({idx}/{total})...")

                pull_cmd = self.get_adb_command(f"pull {directory}/{filename} \"{os.path.join(save_dir, filename)}\"")
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    success_count += 1
                else:
                    self._safe_update_info(f"拉取失败: {filename}")

            if success_count > 0:
                msg = f"成功拉取 {success_count} 个录音文件到:\n{save_dir}"
                self._safe_set_hal_status(f"成功拉取 {success_count} 个文件")
                self._safe_update_info(msg)
                setattr(self, "_hal_pull_final_status", f"成功拉取 {success_count} 个录音文件到 {save_dir}")

                def _open_dir():
                    try:
                        if platform.system() == "Windows":
                            os.startfile(save_dir)
                        elif platform.system() == "Darwin":
                            subprocess.run(["open", save_dir])
                        else:
                            subprocess.run(["xdg-open", save_dir])
                    except Exception:
                        pass
                root = self._get_root()
                if root:
                    root.after(0, _open_dir)
            else:
                self._safe_set_hal_status("未成功拉取任何文件")
                self._safe_update_info("未成功拉取任何文件")
                setattr(self, "_hal_pull_final_status", "未成功拉取任何文件")

        except Exception as e:
            self._safe_set_hal_status(f"拉取文件出错: {str(e)}")
            self._safe_update_info(f"拉取文件出错: {str(e)}")
            setattr(self, "_hal_pull_final_status", f"拉取文件出错: {str(e)}")

    def auto_pull_hal_files(self):
        """自动拉取HAL录音文件（主线程可直接调用，内部会区分线程并安全更新UI）"""
        self._auto_pull_hal_files_impl()

    def _get_root(self):
        """获取主窗口，用于在主线程调度 UI 更新"""
        root = getattr(self, "root", None)
        if root is not None and root.winfo_exists():
            return root
        parent = getattr(self, "parent", None)
        if parent is not None and parent.winfo_exists():
            return parent.winfo_toplevel()
        return None

    def _safe_update_info(self, message):
        """线程安全：在录音信息区域追加内容（若在子线程则投递到主线程）"""
        def _do():
            if getattr(self, "hal_info_text", None) and self.hal_info_text.winfo_exists():
                self.update_info_text(message)
        root = self._get_root()
        if root is None:
            return
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            root.after(0, _do)

    def _safe_set_hal_status(self, text):
        """线程安全：设置底部 HAL 状态文字"""
        def _do():
            if getattr(self, "hal_status_var", None):
                self.hal_status_var.set(text)
        root = self._get_root()
        if root is None:
            return
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            root.after(0, _do)

    def _safe_finish_stop_hal(self, start_btn, stop_btn, status_msg, recording_status_msg):
        """线程安全：停止录音流程结束后恢复按钮和状态"""
        def _do():
            if start_btn and start_btn.winfo_exists():
                start_btn.config(state="normal")
            if stop_btn and stop_btn.winfo_exists():
                stop_btn.config(state="disabled")
            if getattr(self, "hal_status_var", None):
                self.hal_status_var.set(status_msg)
            if getattr(self, "hal_recording_status_var", None):
                self.hal_recording_status_var.set(recording_status_msg)
            setattr(self, "_hal_stopping", False)
        root = self._get_root()
        if root is not None:
            root.after(0, _do)

    def update_info_text(self, message):
        """更新信息文本框（仅在主线程调用，子线程请用 _safe_update_info）"""
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
       
    def check_default_audio_file(self):
        """检查默认音频文件是否存在"""
        default_audio_path = os.path.join(os.getcwd(), "audio", "speaker", "speaker_default.wav")
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
                shutil.copy(file_path, os.path.join(speaker_dir, "speaker_default.wav"))
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
                audio_file = os.path.join(os.getcwd(), "audio", "speaker", "speaker_default.wav")
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

    def resize_logcat_props_frame(self, event):
        """调整属性列表框架大小"""
        # 预留一点点边距，避免内容贴边/被视觉上“遮挡”
        try:
            width = max(1, int(event.width) - 2)
        except Exception:
            width = event.width
        self.logcat_canvas.itemconfig(self.logcat_canvas_window, width=width)

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
        """启用logcat调试"""
        # 直接检查设备，避免递归调用
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择设备")
            return
        
        try:
            self.update_logcat_status("正在放开日志打印...")
            
            # 修复属性访问问题
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的调试值
                    debug_value = "1"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            debug_value = default_prop["debug_value"]
                            break
                    
                    # 直接构建adb命令，避免递归调用
                    device_id = self.device_var.get()
                    if device_id:
                        cmd = f"adb -s {device_id} shell setprop {prop['name']} {debug_value}"
                    else:
                        cmd = f"adb shell setprop {prop['name']} {debug_value}"
                    
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
        """禁用logcat调试"""
        # 直接检查设备，避免递归调用
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择设备")
            return
        
        try:
            self.update_logcat_status("正在关闭日志打印...")
            
            # 恢复属性默认值
            for prop in self.logcat_props_vars:
                if prop["var"].get():
                    # 查找对应的默认值
                    default_value = "0"  # 默认值
                    for default_prop in self.logcat_props:
                        if default_prop["name"] == prop["name"]:
                            default_value = default_prop["default_value"]
                            break
                    
                    # 直接构建adb命令
                    device_id = self.device_var.get()
                    if device_id:
                        cmd = f"adb -s {device_id} shell setprop {prop['name']} {default_value}"
                    else:
                        cmd = f"adb shell setprop {prop['name']} {default_value}"
                    
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        raise Exception(f"恢复属性 {prop['name']} 失败: {result.stderr}")
                    
                    self.update_logcat_status(f"已恢复: {prop['name']}={default_value}")
            
            # 更新按钮状态
            self.enable_debug_button.config(state="normal")
            self.disable_debug_button.config(state="disabled")
            
            self.update_logcat_status("日志打印已关闭")
            
        except Exception as e:
            self.update_logcat_status(f"关闭日志打印出错: {str(e)}")
            messagebox.showerror("错误", f"关闭日志打印时出错:\n{str(e)}")

    def start_logcat_capture(self):
        """开始抓取 logcat 日志。不要求先选设备：可直接点「开始抓取」，后台会先等任意设备上线再开始抓取（适合 reboot 后抓开机日志）。"""
        device_id = (self.device_var.get() or "").strip() if hasattr(self, "device_var") else ""
        try:
            save_dir = self.logcat_save_path_var.get().strip()
            if not save_dir:
                save_dir = ensure_output_dir(DIR_LOGCAT)
            else:
                os.makedirs(save_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"audio_logcat_{timestamp}.txt"
            logcat_file_path = os.path.join(save_dir, filename)
            filter_spec = (self.logcat_filter_var.get() or "").strip() if hasattr(self, "logcat_filter_var") else ""
            if not filter_spec:
                filter_spec = "*:V"

            if hasattr(self, "start_capture_button"):
                self.start_capture_button.config(state="disabled")
            if hasattr(self, "stop_capture_button"):
                self.stop_capture_button.config(state="normal")
            self.logcat_process = None
            self.logcat_file = None
            self.logcat_wait_process = None
            self._logcat_wait_cancelled = False
            self.logcat_file_path = logcat_file_path

            def _run_wait_then_capture():
                try:
                    self.root.after(0, lambda: self.update_logcat_status("等待设备连接...（检测到设备后自动开始抓取，可抓开机日志）"))
                    # 未选设备时等任意设备；已选时等指定设备
                    if device_id:
                        wait_argv = ["adb", "-s", device_id, "wait-for-device"]
                    else:
                        wait_argv = ["adb", "wait-for-device"]
                    wait_proc = subprocess.Popen(wait_argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                    self.logcat_wait_process = wait_proc
                    wait_proc.wait()
                    self.logcat_wait_process = None
                    if getattr(self, "_logcat_wait_cancelled", True):
                        self.root.after(0, self._logcat_capture_aborted)
                        return
                    # 设备已上线：若之前未指定设备，取当前第一个在线设备
                    use_serial = device_id
                    if not use_serial:
                        r = subprocess.run(
                            ["adb", "devices"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if r.returncode == 0 and r.stdout:
                            for line in r.stdout.strip().splitlines()[1:]:
                                parts = line.strip().split()
                                if len(parts) >= 2 and parts[1] == "device":
                                    use_serial = parts[0]
                                    break
                        if not use_serial:
                            self.root.after(0, lambda: self.update_logcat_status("未检测到在线设备，无法开始抓取"))
                            self.root.after(0, self._logcat_capture_aborted)
                            return
                    argv = ["adb", "-s", use_serial, "logcat", "-v", "threadtime", filter_spec]

                    def _start_logcat():
                        try:
                            self.logcat_file = open(
                                logcat_file_path, "w", encoding="utf-8", errors="replace", buffering=1
                            )
                            self.logcat_process = subprocess.Popen(
                                argv,
                                shell=False,
                                stdout=self.logcat_file,
                                stderr=subprocess.PIPE,
                                text=True,
                            )
                            self.update_logcat_status(f"正在抓取日志到: {filename}")
                            try:
                                auto_stop_s = int(
                                    (self.logcat_auto_stop_var.get() if hasattr(self, "logcat_auto_stop_var") else "0") or "0"
                                )
                            except Exception:
                                auto_stop_s = 0
                            if auto_stop_s > 0:
                                self.root.after(auto_stop_s * 1000, self.stop_logcat_capture)
                        except Exception as e:
                            self.update_logcat_status(f"开始抓取日志出错: {str(e)}")
                            messagebox.showerror("错误", f"设备已连接，但启动 logcat 时出错:\n{str(e)}")
                            self._logcat_capture_aborted()
                    self.root.after(0, _start_logcat)
                except Exception as e:
                    if not getattr(self, "_logcat_wait_cancelled", True):
                        self.root.after(0, lambda: self.update_logcat_status(f"等待设备时出错: {str(e)}"))
                        self.root.after(0, self._logcat_capture_aborted)
            threading.Thread(target=_run_wait_then_capture, daemon=True).start()
        except Exception as e:
            self.update_logcat_status(f"开始抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"开始抓取日志时出错:\n{str(e)}")
            if hasattr(self, "start_capture_button"):
                self.start_capture_button.config(state="normal")
            if hasattr(self, "stop_capture_button"):
                self.stop_capture_button.config(state="disabled")

    def _logcat_capture_aborted(self):
        """等待设备被取消或失败时恢复按钮状态"""
        self.logcat_wait_process = None
        self._logcat_wait_cancelled = True
        if hasattr(self, "start_capture_button"):
            self.start_capture_button.config(state="normal")
        if hasattr(self, "stop_capture_button"):
            self.stop_capture_button.config(state="disabled")
        self.update_logcat_status("就绪")

    def stop_logcat_capture(self):
        """停止抓取日志（若正在等待设备则取消等待；若已在抓取则停止 logcat 进程）"""
        try:
            # 若正在“等待设备连接”，取消等待
            wait_proc = getattr(self, "logcat_wait_process", None)
            if wait_proc is not None and wait_proc.poll() is None:
                self._logcat_wait_cancelled = True
                if platform.system() == "Windows":
                    subprocess.run(f"taskkill /F /T /PID {wait_proc.pid}", shell=True)
                else:
                    import signal
                    try:
                        os.kill(wait_proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                self.logcat_wait_process = None
                self.update_logcat_status("已取消等待设备")
                if hasattr(self, "start_capture_button"):
                    self.start_capture_button.config(state="normal")
                if hasattr(self, "stop_capture_button"):
                    self.stop_capture_button.config(state="disabled")
                return

            if not hasattr(self, "logcat_process") or self.logcat_process is None:
                return

            self.update_logcat_status("正在停止抓取日志...")

            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /T /PID {self.logcat_process.pid}", shell=True)
            else:
                import signal
                os.kill(self.logcat_process.pid, signal.SIGTERM)
                try:
                    self.logcat_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.kill(self.logcat_process.pid, signal.SIGKILL)

            if hasattr(self, "logcat_file") and self.logcat_file:
                try:
                    self.logcat_file.close()
                except Exception:
                    pass
                self.logcat_file = None
            self.logcat_process = None
            self.logcat_running = False

            if hasattr(self, "start_capture_button"):
                self.start_capture_button.config(state="normal")
            if hasattr(self, "stop_capture_button"):
                self.stop_capture_button.config(state="disabled")
            self.update_logcat_status("日志抓取已停止")

            if messagebox.askyesno("完成", "日志抓取已完成，是否打开日志文件夹？"):
                self.open_logcat_folder()
        except Exception as e:
            self.update_logcat_status(f"停止抓取日志出错: {str(e)}")
            messagebox.showerror("错误", f"停止抓取日志时出错:\n{str(e)}")

    def open_logcat_folder(self):
        """打开日志保存文件夹"""
        save_dir = self.logcat_save_path_var.get().strip()
        if not save_dir:
            save_dir = get_output_dir(DIR_LOGCAT)
    
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

    def _parse_logcat_level(self, line):
        """从 threadtime 格式行解析级别：01-02 16:06:24.385  1234  5678 I Tag: msg"""
        parts = line.split(None, 5)
        if len(parts) >= 5 and len(parts[4]) == 1 and parts[4] in "VDIWEF":
            return parts[4]
        for c in "FEWIDV":
            if f" {c} " in line or (" " + c + "\t") in line:
                return c
        return "V"

    def _level_priority(self, c):
        """V=0, D=1, I=2, W=3, E=4, F=5"""
        return {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5}.get(c, 0)

    def clear_logcat_viewer(self):
        """清空日志查看器内容"""
        if not getattr(self, "logcat_viewer_text", None) or not self.logcat_viewer_text.winfo_exists():
            return
        self.logcat_viewer_text.config(state="normal")
        self.logcat_viewer_text.delete("1.0", tk.END)
        self.logcat_viewer_text.config(state="disabled")
        self.logcat_viewer_total_count = 0
        self.logcat_viewer_displayed_count = 0
        if hasattr(self, "logcat_viewer_total_var"):
            self.logcat_viewer_total_var.set("总计:0")
        if hasattr(self, "logcat_viewer_displayed_var"):
            self.logcat_viewer_displayed_var.set("显示:0")

    def toggle_logcat_viewer_pause(self):
        """暂停/继续日志查看器显示"""
        self.logcat_viewer_paused = not getattr(self, "logcat_viewer_paused", False)
        if hasattr(self, "logcat_viewer_pause_btn") and self.logcat_viewer_pause_btn.winfo_exists():
            self.logcat_viewer_pause_btn.config(text="继续" if self.logcat_viewer_paused else "暂停")

    def start_logcat_viewer(self):
        """开始实时查看 logcat（独立于抓取到文件）"""
        if not self.check_device_selected():
            return
        if getattr(self, "logcat_viewer_process", None) and self.logcat_viewer_process is not None and self.logcat_viewer_process.poll() is None:
            return
        try:
            device_id = (self.device_var.get() or "").strip()
            argv = ["adb"]
            if device_id:
                argv.extend(["-s", device_id])
            argv.extend(["logcat", "-v", "threadtime", "*:V"])
            self._viewer_queue = queue.Queue()
            self.logcat_viewer_stop = False
            self.logcat_viewer_process = subprocess.Popen(
                argv,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            time.sleep(0.2)
            if self.logcat_viewer_process.poll() is not None:
                out = ""
                try:
                    if self.logcat_viewer_process.stdout:
                        out = (self.logcat_viewer_process.stdout.read() or "").strip()
                except Exception:
                    pass
                self.logcat_viewer_process = None
                self.update_logcat_status("日志查看器启动失败，请检查设备连接与 adb")
                messagebox.showerror("错误", out or "adb logcat 进程已退出")
                return
            if hasattr(self, "logcat_viewer_start_btn"):
                self.logcat_viewer_start_btn.config(state="disabled")
            if hasattr(self, "logcat_viewer_stop_btn"):
                self.logcat_viewer_stop_btn.config(state="normal")
            if hasattr(self, "logcat_viewer_state_var"):
                self.logcat_viewer_state_var.set("运行中")
            self.update_logcat_status("日志查看器已启动，实时显示中")
            self.logcat_viewer_thread = threading.Thread(target=self._read_logcat_viewer, daemon=True)
            self.logcat_viewer_thread.start()
            self._schedule_process_logcat_viewer_queue()
        except Exception as e:
            self.update_logcat_status(f"启动日志查看器出错: {str(e)}")
            messagebox.showerror("错误", f"启动日志查看器时出错:\n{str(e)}")

    def stop_logcat_viewer(self):
        """停止日志查看器"""
        self.logcat_viewer_stop = True
        if getattr(self, "logcat_viewer_process", None) and self.logcat_viewer_process is not None and self.logcat_viewer_process.poll() is None:
            try:
                if platform.system() == "Windows":
                    subprocess.run(f"taskkill /F /T /PID {self.logcat_viewer_process.pid}", shell=True)
                else:
                    self.logcat_viewer_process.terminate()
            except Exception:
                pass
            self.logcat_viewer_process = None
        if hasattr(self, "logcat_viewer_start_btn"):
            self.logcat_viewer_start_btn.config(state="normal")
        if hasattr(self, "logcat_viewer_stop_btn"):
            self.logcat_viewer_stop_btn.config(state="disabled")
        if hasattr(self, "logcat_viewer_state_var"):
            self.logcat_viewer_state_var.set("已停止")
        if hasattr(self, "logcat_viewer_pause_btn") and self.logcat_viewer_pause_btn.winfo_exists():
            self.logcat_viewer_paused = False
            self.logcat_viewer_pause_btn.config(text="暂停")
        self.update_logcat_status("日志查看器已停止")

    def _read_logcat_viewer(self):
        """后台线程：读取 logcat 输出并放入队列"""
        try:
            proc = getattr(self, "logcat_viewer_process", None)
            if not proc or not getattr(proc, "stdout", None):
                return
            for line in proc.stdout:
                if getattr(self, "logcat_viewer_stop", True):
                    break
                if not line:
                    continue
                level = self._parse_logcat_level(line)
                q = getattr(self, "_viewer_queue", None)
                if q is not None:
                    try:
                        q.put_nowait((line.rstrip("\n\r"), level))
                    except queue.Full:
                        pass
        except Exception:
            pass
        finally:
            self.logcat_viewer_process = None
            root = getattr(self, "root", None)
            if root and root.winfo_exists():
                root.after(0, self._logcat_viewer_ended)

    def _logcat_viewer_ended(self):
        """查看器进程结束后的 UI 恢复"""
        self.logcat_viewer_stop = True
        self.logcat_viewer_process = None
        if hasattr(self, "logcat_viewer_start_btn") and self.logcat_viewer_start_btn.winfo_exists():
            self.logcat_viewer_start_btn.config(state="normal")
        if hasattr(self, "logcat_viewer_stop_btn") and self.logcat_viewer_stop_btn.winfo_exists():
            self.logcat_viewer_stop_btn.config(state="disabled")
        if hasattr(self, "logcat_viewer_state_var"):
            self.logcat_viewer_state_var.set("已停止")

    def _schedule_process_logcat_viewer_queue(self):
        """定时从队列取数据并刷新查看器（主线程）"""
        if getattr(self, "logcat_viewer_stop", True):
            return
        self._process_logcat_viewer_queue()
        root = getattr(self, "root", None)
        if root and root.winfo_exists() and not getattr(self, "logcat_viewer_stop", True):
            root.after(80, self._schedule_process_logcat_viewer_queue)

    def _process_logcat_viewer_queue(self):
        """从队列取行并追加到查看器（应用过滤、级别、暂停、自动滚动）"""
        q = getattr(self, "_viewer_queue", None)
        if q is None:
            return
        keyword = (getattr(self, "logcat_viewer_filter_var", None) and self.logcat_viewer_filter_var.get() or "").strip().lower()
        level_sel = (getattr(self, "logcat_viewer_level_var", None) and self.logcat_viewer_level_var.get() or "V").upper()
        level_pri = self._level_priority(level_sel)
        auto_scroll = getattr(self, "logcat_viewer_auto_scroll_var", None) and self.logcat_viewer_auto_scroll_var.get()
        paused = getattr(self, "logcat_viewer_paused", False)
        max_lines = getattr(self, "_logcat_viewer_max_lines", 5000)
        txt = getattr(self, "logcat_viewer_text", None)
        if not txt or not txt.winfo_exists():
            return
        added = 0
        try:
            while True:
                try:
                    line, level = q.get_nowait()
                except queue.Empty:
                    break
                self.logcat_viewer_total_count = getattr(self, "logcat_viewer_total_count", 0) + 1
                if keyword and keyword not in line.lower():
                    continue
                if self._level_priority(level) < level_pri:
                    continue
                if paused:
                    continue
                self.logcat_viewer_displayed_count = getattr(self, "logcat_viewer_displayed_count", 0) + 1
                tag = f"level_{level.lower()}" if level.lower() in "vdiwef" else "level_i"
                txt.config(state="normal")
                txt.insert(tk.END, line + "\n", tag)
                n = int(txt.index("end-1c").split(".")[0])
                if n > max_lines:
                    txt.delete("1.0", "2.0")
                if auto_scroll:
                    txt.see(tk.END)
                txt.config(state="disabled")
                added += 1
        except Exception:
            pass
        if hasattr(self, "logcat_viewer_total_var"):
            self.logcat_viewer_total_var.set(f"总计:{getattr(self, 'logcat_viewer_total_count', 0)}")
        if hasattr(self, "logcat_viewer_displayed_var"):
            self.logcat_viewer_displayed_var.set(f"显示:{getattr(self, 'logcat_viewer_displayed_count', 0)}")

    def browse_logcat_save_path(self):
        """浏览并选择日志保存路径"""
        folder_path = filedialog.askdirectory(
            title="选择日志保存路径",
            initialdir=self.logcat_save_path_var.get()
        )
        
        if folder_path:
            self.logcat_save_path_var.set(folder_path)
            self.update_logcat_status(f"已设置日志保存路径: {folder_path}")

    def open_test_folder(self):
        """打开测试数据根目录（output）"""
        out_dir = OUTPUT_ROOT
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(out_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", out_dir])
            else:  # Linux
                subprocess.run(["xdg-open", out_dir])
        except Exception as e:
            self.status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def run_multichannel_test(self):
        """运行多声道测试"""
        if not self.check_device_selected():
            return
        
        rate = self.multi_rate_var.get()
        bit = self.multi_bit_var.get()
        preset = (getattr(self, "multichannel_preset_var", None) and self.multichannel_preset_var.get() or "").strip() or "7.1"
        
        self.status_var.set("正在执行多声道测试...")
        
        # 在新线程中运行测试，避免GUI冻结
        threading.Thread(target=self._multichannel_test_thread, 
                        args=(rate, bit, preset), 
                        daemon=True).start()

    def _multichannel_test_thread(self, rate, bit, preset):
        try:
            # 准备工作
            subprocess.run(self.get_adb_command("root"), shell=True)
            # 多声道测试音频：7.1/2.1/2.0 使用 audio/channel/ 下对应文件
            name_map = {"7.1": "Nums_7dot1_16_48000.wav", "2.1": "Nums_2dot1_16_48000.wav", "2.0": "Nums_2dot0_16_48000.wav"}
            audio_name = name_map.get(preset, "Nums_7dot1_16_48000.wav")
            base_dir = getattr(self, "_get_runtime_base_dir", lambda: os.getcwd())()
            audio_file = os.path.join(base_dir, "audio", "channel", audio_name)
            if not os.path.exists(audio_file):
                msg = (
                    f"多声道测试音频不存在：audio/channel/{audio_name}\n\n"
                    "请将对应音频放到 audio/channel 目录后再开始测试。"
                )
                self.root.after(0, lambda: messagebox.showerror("缺少音频文件", msg))
                return
            subprocess.run(self.get_adb_command(f"push \"{audio_file}\" /sdcard/{audio_name}"), shell=True)
            
            # 重启audioserver
            for _ in range(3):
                subprocess.run(self.get_adb_command("shell killall audioserver"), shell=True)
            
            # 播放音频
            self.root.after(0, lambda: self.status_var.set("正在播放多声道音频..."))
            play_cmd = self.get_adb_command(f"shell tinyplay /sdcard/{audio_name} -r {rate} -b {bit}")
            
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
        # 直接检查设备，避免递归调用
        if not self.device_var.get():
            messagebox.showwarning("警告", "请先选择设备")
            return
        
        if not hasattr(self, 'local_audio_file') or not os.path.exists(self.local_audio_file):
            messagebox.showerror("错误", "请先选择音频文件")
            return
        
        # 获取播放方式
        playback_mode = self.playback_mode_var.get()
        
        try:
            # 停止当前播放
            self.stop_local_audio()
            
            # 获取文件类型
            _, ext = os.path.splitext(self.local_audio_file)
            ext = ext.lower()
            
            # 记录调试信息
            self.debug_info = f"文件: {self.local_audio_file}\n类型: {ext}\n播放方式: {playback_mode}"
            print(self.debug_info)
            
            # 通过Android设备播放
            if playback_mode == "device":
                self.playback_status_var.set("正在准备通过Android设备播放...")
                
                # 构建adb命令
                device_id = self.device_var.get()
                if device_id:
                    mkdir_cmd = f"adb -s {device_id} shell mkdir -p /sdcard/HPlayerFiles"
                else:
                    mkdir_cmd = "adb shell mkdir -p /sdcard/HPlayerFiles"
                
                subprocess.run(mkdir_cmd, shell=True)
                
                # 推送文件到设备
                self.status_var.set("正在推送文件到Android设备...")
                file_basename = os.path.basename(self.local_audio_file)
                remote_path = f"/sdcard/HPlayerFiles/{file_basename}"
                
                if device_id:
                    push_cmd = f"adb -s {device_id} push \"{self.local_audio_file}\" \"{remote_path}\""
                else:
                    push_cmd = f"adb push \"{self.local_audio_file}\" \"{remote_path}\""
                
                result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
                if "error" in result.stderr.lower():
                    raise Exception(f"推送文件失败: {result.stderr}")
                
                # 播放文件
                if device_id:
                    play_cmd = f"adb -s {device_id} shell am start -a android.intent.action.VIEW -d file://{remote_path}"
                else:
                    play_cmd = f"adb shell am start -a android.intent.action.VIEW -d file://{remote_path}"
                
                subprocess.run(play_cmd, shell=True)
                
                self.playback_status_var.set(f"已在设备上播放: {file_basename}")
            
            # 本地播放
            else:
                self._start_local_playback()
            
        except Exception as e:
            self.status_var.set(f"播放出错: {str(e)}")
            messagebox.showerror("错误", f"播放时出错:\n{str(e)}")

    def add_prop_to_ui(self, prop, value="1"):
        """将新的录音属性添加到UI，格式为 prop value"""
        # 解析属性和值
        prop_parts = prop.split()
        prop_name = prop_parts[0] if len(prop_parts) > 0 else prop
        prop_value = prop_parts[1] if len(prop_parts) > 1 else value
        
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
        
        # 显示格式: [√] prop_name value
        cb = ttk.Checkbutton(prop_frame, text=f"{prop_name} {prop_value}", variable=var, style="Small.TCheckbutton")
        cb.pack(side="left", padx=2, fill="x", expand=True)

    def adapt_remote_controller(self):
        """重新适配设备的遥控器 - 修复功能失效问题"""
        if not self.check_device_selected():
            return
        
        try:
            # 更新状态
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set("正在适配遥控器...")
            
            # 直接执行遥控器适配命令
            pairing_cmd = self.get_adb_command("shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS")
            result = subprocess.run(pairing_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"适配命令执行失败: {result.stderr}")
            
            # 简单更新状态
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set("遥控器适配已启动")
            
        except Exception as e:
            error_msg = f"适配遥控器失败: {str(e)}"
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set(error_msg)
            messagebox.showerror("错误", f"适配遥控器时出错:\n{str(e)}")

    def send_keycode(self, keycode):
        """发送遥控器按键 - 修复功能失效问题"""
        if not self.check_device_selected():
            return
        
        try:
            # 更新状态
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set(f"正在发送按键: {keycode}")
            
            # 发送按键命令
            cmd = self.get_adb_command(f"shell input keyevent KEYCODE_{keycode}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"发送按键失败: {result.stderr}")
            
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set(f"已发送按键: {keycode}")
            
        except Exception as e:
            error_msg = f"发送按键出错: {str(e)}"
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set(error_msg)
            messagebox.showerror("错误", f"发送按键时出错:\n{str(e)}")

    def send_custom_keycode(self):
        """发送自定义按键代码"""
        keycode = self.custom_key_var.get().strip()
        if not keycode:
            messagebox.showwarning("警告", "请输入按键代码")
            return
        
        self.send_keycode(keycode)

    def remove_paired_remote(self):
        """移除已配对的遥控器"""
        if not self.check_device_selected():
            return
        
        try:
            self.status_var.set("正在打开遥控器设置...")
            
            # 打开遥控器设置页面的命令
            settings_cmd = self.get_adb_command("shell am start -n com.android.tv.settings/.accessories.AccessoryFragment")
            subprocess.run(settings_cmd, shell=True)
            
            # 提示用户
            self.remote_status_var.set("已打开设置界面，请选择移除遥控器")
            messagebox.showinfo("移除遥控器", "已打开遥控器设置界面\n\n请在设备屏幕上找到并选择要移除的遥控器，然后点击'移除'或'忘记'选项。\n\n移除完成后，可以使用'开始适配遥控器'按钮重新配对。")
            
        except Exception as e:
            self.status_var.set(f"打开遥控器设置失败: {str(e)}")
            messagebox.showerror("错误", f"打开遥控器设置时出错:\n{str(e)}")

    def setup_logcat_tab(self, parent):
        # ... 现有代码 ...
        
        # 初始状态信息
        self.update_logcat_status("就绪")
        
        # 添加这个函数调用来清理现有的删除按钮
        self.root.after(100, self.clean_existing_delete_buttons)

    def clean_existing_delete_buttons(self):
        """清理现有属性列表中的删除按钮"""
        try:
            for prop in self.logcat_props_vars:
                if "frame" in prop:
                    # 在每个属性框架中查找删除按钮并移除
                    for child in prop["frame"].winfo_children():
                        if isinstance(child, ttk.Button) and child.cget("text") == "×":
                            child.destroy()
        except Exception as e:
            print(f"清理删除按钮时出错: {str(e)}")

    def test_button_click(self):
        """测试按钮点击是否正常"""
        print("=== 测试按钮点击方法被调用 ===")
        try:
            if hasattr(self, 'mic_info_var'):
                self.mic_info_var.set("按钮点击测试成功！")
            else:
                print("mic_info_var 不存在")
            
            # 显示一个消息框确认
            from tkinter import messagebox
            messagebox.showinfo("测试", "按钮点击功能正常！")
            
        except Exception as e:
            print(f"测试按钮点击出错: {e}")
            import traceback
            traceback.print_exc()