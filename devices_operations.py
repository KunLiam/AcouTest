import subprocess
import threading
import time
import platform
import tkinter as tk
from tkinter import messagebox

class DeviceOperations:
    def __init__(self, parent):
        self.parent = parent
    
    def refresh_devices(self):
        """刷新设备列表"""
        try:
            # 使用新方法执行ADB命令
            result = self.execute_adb_command("devices")
            
            if result and result.returncode == 0:
                # 解析设备列表
                lines = result.stdout.strip().split('\n')
                self.devices = []
                
                for line in lines[1:]:  # 跳过第一行 "List of devices attached"
                    if line.strip():
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            device_id = parts[0].strip()
                            self.devices.append(device_id)
                
                # 更新设备下拉菜单
                self.update_device_dropdown()
                
                # 更新设备状态
                if self.devices:
                    self.device_status_var.set(f"检测到 {len(self.devices)} 个设备")
                else:
                    self.device_status_var.set("未检测到设备")
            else:
                self.device_status_var.set("检查设备失败")
                self.devices = []
                self.update_device_dropdown()
        except Exception as e:
            self.device_status_var.set(f"检查设备出错: {str(e)}")
            self.devices = []
            self.update_device_dropdown()
    
    def on_device_selected(self, event=None):
        """设备选择事件处理"""
        if not self.devices:  # 如果没有设备，直接返回
            return
            
        selected_index = self.device_combobox.current()
        if selected_index >= 0 and selected_index < len(self.devices):
            self.selected_device = self.devices[selected_index]  # 直接使用设备ID
            self.status_var.set(f"已连接到设备: {self.selected_device}")
            self.device_status_var.set(f"已选择设备: {self.selected_device}")
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
        """检查是否已选择设备"""
        if not self.selected_device:
            # 自动刷新设备列表而不是显示错误消息
            self.refresh_devices()
            if not self.selected_device:
                self.status_var.set("请先选择一个设备")
                return False
        return True
    
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
        """更新设备状态标签的颜色"""
        # 查找设备状态标签并更新颜色
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.ttk.Label) and hasattr(widget, 'cget') and widget.cget("textvariable") == str(self.device_status_var):
                widget.configure(foreground=color)
                return