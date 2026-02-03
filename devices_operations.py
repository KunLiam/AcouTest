import subprocess
import threading
import time
import platform
import tkinter as tk
from tkinter import ttk, messagebox

class DeviceOperations:
    def __init__(self, parent):
        self.parent = parent
    
    def refresh_devices(self):
        """刷新设备列表"""
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.device_combobox['values'] = []
                self.device_var.set("")
                self.selected_device = None
                self.update_device_status_color("red")
                self.root.after(0, lambda: self.device_status_var.set("ADB命令失败或无设备"))
                return
            
            lines = result.stdout.strip().split('\n')
            devices = []
            online_devices = []
            
            for line in lines[1:]:
                if line.strip() and '\t' in line:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0]
                        status = parts[1]
                        devices.append(device_id)
                        if status == 'device':  # 只有状态为'device'的才是真正在线的设备
                            online_devices.append(device_id)
            
            self.device_combobox['values'] = devices
            
            if online_devices:
                # 如果有在线设备，优先保持当前选择（如果仍在线），否则选择第一个在线设备
                current_selection = self.device_var.get()
                if current_selection in online_devices:
                    self.device_var.set(current_selection)
                    self.selected_device = current_selection
                else:
                    self.device_var.set(online_devices[0])
                    self.selected_device = online_devices[0]
                
                self.update_device_status_color("green")
                self.root.after(0, lambda: self.device_status_var.set(f"已连接: {self.selected_device}"))
            elif devices:
                # 有设备但都不在线
                self.device_var.set(devices[0])
                self.selected_device = None
                self.update_device_status_color("orange")
                self.root.after(0, lambda: self.device_status_var.set(f"设备 {devices[0]} 离线/未授权"))
            else:
                # 没有设备
                self.device_var.set("")
                self.selected_device = None
                self.update_device_status_color("red")
                self.root.after(0, lambda: self.device_status_var.set("未检测到设备"))
            
            print(f"刷新设备完成 - 在线设备: {online_devices}, 选中设备: {self.selected_device}")
            
        except Exception as e:
            self.device_combobox['values'] = []
            self.device_var.set("")
            self.selected_device = None
            self.update_device_status_color("red")
            self.root.after(0, lambda: self.device_status_var.set(f"刷新出错: {str(e)}"))
            print(f"刷新设备时出错: {str(e)}")
    
    def on_device_selected(self, event=None):
        """设备选择事件处理"""
        selected_device = self.device_var.get()
        print(f"用户选择设备: {selected_device}")
        
        if selected_device:
            # 检查选择的设备是否在线
            try:
                result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]
                    device_online = False
                    
                    for line in lines:
                        if line.strip():
                            parts = line.strip().split('\t')
                            if len(parts) >= 2:
                                device_id = parts[0]
                                status = parts[1]
                                if device_id == selected_device and status == 'device':
                                    device_online = True
                                    break
                    
                    if device_online:
                        self.selected_device = selected_device
                        self.update_device_status_color("green")
                        self.root.after(0, lambda: self.device_status_var.set(f"已连接: {selected_device}"))
                        print(f"设备 {selected_device} 在线，已更新 selected_device")
                    else:
                        self.selected_device = None
                        self.update_device_status_color("orange")
                        self.root.after(0, lambda: self.device_status_var.set(f"设备 {selected_device} 离线/未授权"))
                        print(f"设备 {selected_device} 不在线，selected_device 设为 None")
                else:
                    self.selected_device = None
                    self.update_device_status_color("red")
                    self.root.after(0, lambda: self.device_status_var.set("ADB命令失败"))
            except Exception as e:
                self.selected_device = None
                self.update_device_status_color("red")
                self.root.after(0, lambda: self.device_status_var.set(f"检查设备状态出错: {str(e)}"))
                print(f"检查设备状态时出错: {e}")
        else:
            self.selected_device = None
            self.update_device_status_color("red")
            self.root.after(0, lambda: self.device_status_var.set("未选择设备"))
    
    def get_adb_command(self, cmd):
        """获取完整的ADB命令"""
        if self.selected_device:
            return f"adb -s {self.selected_device} {cmd}"
        else:
            return f"adb {cmd}"

    def execute_adb_command(self, cmd, capture_output=True):
        """执行ADB命令并返回结果"""
        full_cmd = self.get_adb_command(cmd)
        
        try:
            # 在Windows上使用CREATE_NO_WINDOW标志隐藏命令行窗口
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
                
                # 使用CREATE_NO_WINDOW标志
                CREATE_NO_WINDOW = 0x08000000
                
                result = subprocess.run(
                    full_cmd, 
                    shell=True, 
                    capture_output=capture_output, 
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                    startupinfo=startupinfo
                )
            else:
                # 非Windows平台使用标准方式
                result = subprocess.run(full_cmd, shell=True, capture_output=capture_output, text=True)
            
            return result
        except Exception as e:
            print(f"执行ADB命令出错: {str(e)}")
            return None
    
    def check_device_selected(self):
        """检查是否选择了设备并确保其在线"""
        print("=== 开始检查设备选择状态 ===")
        
        try:
            # 检查UI组件是否存在
            if not hasattr(self, 'device_combobox'):
                print("错误: device_combobox 不存在")
                return False
            
            current_device_id = self.device_combobox.get()
            print(f"当前UI选择的设备ID: '{current_device_id}'")
            print(f"当前stored selected_device: '{getattr(self, 'selected_device', 'UNDEFINED')}'")
            
            # 检查是否有选择设备
            if not current_device_id or current_device_id.strip() == "":
                print("错误: UI中没有选择任何设备")
                self.root.after(0, lambda: self.device_status_var.set("未选择设备"))
                self.root.after(0, lambda: self.update_device_status_color("red"))
                return False
            
            # 实时检查设备在线状态
            try:
                print("执行 adb devices 命令检查设备状态...")
                result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
                print(f"adb devices 返回码: {result.returncode}")
                print(f"adb devices 输出:\n{result.stdout}")
                
                if result.returncode != 0:
                    print(f"adb devices 命令失败: {result.stderr}")
                    self.root.after(0, lambda: self.device_status_var.set("ADB命令失败"))
                    self.root.after(0, lambda: self.update_device_status_color("red"))
                    return False
                
                # 解析设备列表
                lines = result.stdout.strip().split('\n')[1:]  # 跳过标题行
                device_found_and_online = False
                
                for line in lines:
                    if line.strip():
                        parts = line.strip().split('\t')
                        if len(parts) >= 2:
                            device_id = parts[0]
                            status = parts[1]
                            print(f"发现设备: {device_id}, 状态: {status}")
                            
                            if device_id == current_device_id:
                                if status == 'device':
                                    device_found_and_online = True
                                    print(f"✓ 设备 {current_device_id} 找到且在线")
                                    break
                                else:
                                    print(f"✗ 设备 {current_device_id} 找到但状态为: {status}")
                                    self.root.after(0, lambda s=status: self.device_status_var.set(f"设备状态: {s}"))
                                    self.root.after(0, lambda: self.update_device_status_color("orange"))
                                    return False
                
                if device_found_and_online:
                    # 确保 selected_device 与UI选择同步
                    self.selected_device = current_device_id
                    print(f"✓ 设备检查通过，selected_device 已更新为: {self.selected_device}")
                    self.root.after(0, lambda: self.device_status_var.set(f"设备 {current_device_id} 在线"))
                    self.root.after(0, lambda: self.update_device_status_color("green"))
                    return True
                else:
                    print(f"✗ 设备 {current_device_id} 未在设备列表中找到")
                    self.root.after(0, lambda: self.device_status_var.set(f"设备 {current_device_id} 未找到"))
                    self.root.after(0, lambda: self.update_device_status_color("red"))
                    return False
                    
            except subprocess.TimeoutExpired:
                print("adb devices 命令超时")
                self.root.after(0, lambda: self.device_status_var.set("ADB命令超时"))
                self.root.after(0, lambda: self.update_device_status_color("red"))
                return False
            except FileNotFoundError:
                print("错误: 找不到 adb 命令")
                self.root.after(0, lambda: self.device_status_var.set("ADB未安装"))
                self.root.after(0, lambda: self.update_device_status_color("red"))
                return False
            except Exception as e:
                print(f"检查设备在线状态时出错: {e}")
                import traceback
                traceback.print_exc()
                self.root.after(0, lambda: self.device_status_var.set(f"检查出错: {str(e)}"))
                self.root.after(0, lambda: self.update_device_status_color("red"))
                return False
                
        except Exception as e:
            print(f"检查设备选择状态时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
        from tkinter import ttk
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

    def update_device_dropdown(self):
        """更新设备下拉菜单"""
        if hasattr(self, 'device_combobox'):
            # 清空当前值
            self.device_combobox.set("")
            
            if self.devices:
                # 设置新的下拉菜单值
                self.device_combobox['values'] = self.devices
                
                # 自动选择第一个设备
                self.device_combobox.current(0)
                self.selected_device = self.devices[0]
                self.device_status_var.set(f"已选择设备: {self.selected_device}")
                self.update_device_status_color("green")
            else:
                # 如果没有设备，清空下拉菜单
                self.device_combobox['values'] = []
                self.selected_device = None
                self.device_status_var.set("未检测到设备")
                self.update_device_status_color("red")
                
    def update_device_status_color(self, color):
        """更新设备状态颜色"""
        try:
            # 查找设备状态标签并更新颜色
            for widget in self.parent.root.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(widget, ttk.Frame):
                            for subchild in child.winfo_children():
                                if hasattr(subchild, 'configure') and hasattr(subchild, 'cget'):
                                    try:
                                        if 'background' in subchild.configure():
                                            subchild.configure(background=color)
                                    except:
                                        pass
        except Exception:
            pass

    def check_adb_environment(self):
        """检查ADB环境"""
        try:
            # 检查ADB是否在PATH中
            result = subprocess.run("where adb" if platform.system() == "Windows" else "which adb", 
                                  shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                adb_path = result.stdout.strip()
                print(f"ADB路径: {adb_path}")
                return True
            else:
                print("ADB不在系统PATH中")
                return False
        except Exception as e:
            print(f"检查ADB环境出错: {str(e)}")
            return False