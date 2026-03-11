import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import struct
import math
import wave
from array import array
import threading
import time
import subprocess
import platform
import re
import shutil
import shlex
import cmath
import datetime
import sys
import ctypes
from ctypes import c_int, c_char_p, c_void_p, POINTER, c_char
import tempfile
import textwrap

from output_paths import (
    OUTPUT_ROOT,
    get_output_dir,
    ensure_output_dir,
    DIR_LOGCAT,
    DIR_SCREENSHOTS,
    DIR_MIC_TEST,
    DIR_SWEEP_RECORDINGS,
    DIR_AIRTIGHTNESS,
    DIR_HAL_DUMP,
    DIR_HAL_CUSTOM,
    DIR_LOOPBACK,
)

# 功能开关：未找到 feature_config 或出错时默认全部显示
try:
    from feature_config import is_main_tab_enabled, is_sub_tab_enabled, APP_VERSION
except Exception:
    def is_main_tab_enabled(_name):
        return True
    def is_sub_tab_enabled(_main, _sub):
        return True
    APP_VERSION = "1.6"


def fix_wav_header_after_tinycap(file_path, channels, sample_rate, bits_per_sample):
    """
    修正由 tinycap 在被外部 kill 时未回写或写错的 WAV 头。
    tinycap 被 terminate 后可能只留下空白/错误的 fmt，导致编辑器报「未知格式」或损坏。
    直接重写完整的 44 字节 PCM WAV 头（含格式与长度），保证任何播放器/编辑器都能正确打开。
    """
    try:
        ch = int(channels)
        rate = int(sample_rate)
        bits = int(bits_per_sample)
    except (TypeError, ValueError):
        return False
    if ch <= 0 or rate <= 0 or bits not in (16, 24, 32):
        return False
    size = os.path.getsize(file_path)
    header_size = 44
    if size <= header_size:
        return False
    data_sz = size - header_size
    riff_sz = size - 8
    byte_rate = rate * ch * (bits // 8)
    block_align = ch * (bits // 8)
    # 完整 PCM WAV 头 44 字节，避免设备端头不完整导致「未知格式」
    header = (
        b"RIFF" +
        struct.pack("<I", riff_sz) +
        b"WAVE" +
        b"fmt " +
        struct.pack("<I", 16) +           # fmt chunk size
        struct.pack("<H", 1) +            # audio format = PCM
        struct.pack("<H", ch) +
        struct.pack("<I", rate) +
        struct.pack("<I", byte_rate) +
        struct.pack("<H", block_align) +
        struct.pack("<H", bits) +
        b"data" +
        struct.pack("<I", data_sz)
    )
    assert len(header) == 44, "WAV header must be 44 bytes"
    with open(file_path, "r+b") as f:
        f.write(header)
    return True


class LogcatViewerWindow(tk.Toplevel):
    """独立弹窗：日志查看器 (Logcat Viewer)，表格显示、实时滚动、过滤、级别、暂停"""

    LEVEL_PRI = {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5}
    MAX_ROWS = 8000
    MAX_PROCESS_PER_TICK = 300  # 每轮最多处理条数，避免界面卡顿

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("日志查看器 (Logcat Viewer)")
        self.geometry("1000x580")
        self.minsize(800, 400)

        self._process = None
        self._stop = False
        self._paused = False
        self._queue = queue.Queue()
        self._total_count = 0
        self._displayed_count = 0
        self._after_id = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus_set()

    def _build_ui(self):
        # 工具栏
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Filter:").pack(side="left", padx=(0, 4))
        self._filter_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self._filter_var, width=18).pack(side="left", padx=(0, 8))

        ttk.Label(toolbar, text="级别:").pack(side="left", padx=(0, 4))
        self._level_var = tk.StringVar(value="V")
        level_combo = ttk.Combobox(toolbar, textvariable=self._level_var, values=["V", "D", "I", "W", "E", "F"], width=6, state="readonly")
        level_combo.pack(side="left", padx=(0, 8))

        self._auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="自动滚动", variable=self._auto_scroll_var).pack(side="left", padx=(0, 8))

        self._pause_btn = ttk.Button(toolbar, text="暂停", width=6, command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=(0, 8))

        ttk.Button(toolbar, text="清空", width=6, command=self._clear).pack(side="left", padx=(0, 8))

        self._start_btn = ttk.Button(toolbar, text="开始查看", width=8, command=self._start)
        self._start_btn.pack(side="left", padx=(0, 6))
        self._stop_btn = ttk.Button(toolbar, text="停止查看", width=8, command=self._stop_viewer, state="disabled")
        self._stop_btn.pack(side="left")

        # 表格区域
        table_frame = ttk.Frame(self, padding=5)
        table_frame.pack(fill="both", expand=True)

        columns = ("时间", "PID", "TID", "级别", "标签", "包名", "消息")
        self._tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=22, selectmode="extended")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        for col in columns:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=140 if col == "时间" else (60 if col in ("PID", "TID", "级别") else (100 if col in ("标签", "包名") else 400)))
        self._tree.column("消息", width=400)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(side="left", fill="both", expand=True)

        self._tree.tag_configure("level_v", foreground="#666666")
        self._tree.tag_configure("level_d", foreground="#0066cc")
        self._tree.tag_configure("level_i", foreground="#000000")
        self._tree.tag_configure("level_w", foreground="#b8860b")
        self._tree.tag_configure("level_e", foreground="#cc0000")
        self._tree.tag_configure("level_f", foreground="#cc0000")

        # 状态栏
        status_frame = ttk.Frame(self, padding=5)
        status_frame.pack(fill="x")
        self._total_var = tk.StringVar(value="总计:0")
        self._displayed_var = tk.StringVar(value="显示:0")
        self._state_var = tk.StringVar(value="已停止（点击「开始查看」可实时刷新）")
        ttk.Label(status_frame, textvariable=self._total_var).pack(side="left", padx=(0, 16))
        ttk.Label(status_frame, textvariable=self._displayed_var).pack(side="left", padx=(0, 16))
        ttk.Label(status_frame, textvariable=self._state_var).pack(side="left")

    @staticmethod
    def _parse_threadtime(line):
        """解析 logcat 行，兼容 threadtime 及 [n Ttid] [tag] 等格式 -> (time, pid, tid, level, tag, pkg, msg)"""
        line = line.rstrip("\n\r")
        if not line:
            return ("", "", "", "V", "", "", "")
        parts = line.split(None, 5)
        # 标准 threadtime: MM-DD HH:MM:SS.mmm  pid  tid  L  Tag: msg
        if len(parts) >= 6 and len(parts[4]) == 1 and parts[4] in "VDIWEF":
            date, tim, pid, tid, level, rest = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            time_str = f"{date} {tim}"
            tag, msg = "", rest
            if ": " in rest:
                tag, _, msg = rest.partition(": ")
            return (time_str, pid, tid, level, tag, "", msg)
        # 兼容 [level Ttid] [tag] 或仅有时间+消息等格式
        time_str = ""
        pid_str = ""
        tid_str = ""
        level = "V"
        tag = ""
        msg = line
        if len(parts) >= 2 and re.match(r"^\d{2}-\d{2}$", parts[0]) and re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}", parts[1]):
            time_str = f"{parts[0]} {parts[1]}"
            msg = parts[5] if len(parts) > 5 else (" ".join(parts[2:]) if len(parts) > 2 else line)
        # 从整行提取级别：[0]-[5] 或 [V]/[D]/[I]/[W]/[E]/[F] 或空格+单字母
        for m in re.finditer(r"\[([0-5VDIWEF])\]", line):
            c = m.group(1)
            if c in "VDIWEF":
                level = c
                break
            if c in "012345":
                level = "VDIWEF"[int(c)]
                break
        for m in re.finditer(r"\s([VDIWEF])\s", line):
            level = m.group(1)
            break
        # TID: T 后跟数字，如 T484
        tid_m = re.search(r"\bT(\d+)\b", line)
        if tid_m:
            tid_str = tid_m.group(1)
        # PID: 时间后的第一组纯数字（且不是 T 后的）
        if len(parts) >= 4 and parts[2].isdigit():
            pid_str = parts[2]
        if len(parts) >= 4 and parts[3].isdigit():
            tid_str = tid_str or parts[3]
        # 标签：方括号内非 [数字 T...] 的如 [led]
        for tag_m in re.finditer(r"\[\s*([^\]\s]+)\s*\]", line):
            s = tag_m.group(1).strip()
            if s and not re.match(r"^[0-5VDIWEF]$", s) and "T" not in s:
                tag = s[:32]
                break
        if ": " in line and not tag:
            p = line.split(": ", 1)
            if len(p) == 2:
                tag = (p[0].strip().split()[-1] or "")[:32]
        return (time_str or (line[:23] if len(line) >= 23 else line), pid_str, tid_str, level, tag, "", msg if msg else line)

    def _level_priority(self, c):
        return self.LEVEL_PRI.get(c, 0)

    def _clear(self):
        for i in self._tree.get_children():
            self._tree.delete(i)
        self._total_count = 0
        self._displayed_count = 0
        self._total_var.set("总计:0")
        self._displayed_var.set("显示:0")

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_btn.config(text="继续" if self._paused else "暂停")

    def _on_close(self):
        self._stop_viewer()
        if self._after_id:
            self.after_cancel(self._after_id)
        self.destroy()

    def _start(self):
        try:
            if self._process is not None and self._process.poll() is None:
                return
            # 安全获取设备 ID，不依赖 check_device_selected 的弹窗（避免被主窗口挡住）
            device_var = getattr(self.app, "device_var", None)
            device_id = (device_var.get().strip() if device_var else "") or ""
            argv = ["adb"]
            if device_id:
                argv.extend(["-s", device_id])
            argv.extend(["logcat", "-v", "threadtime", "*:V"])
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True, "bufsize": 1}
            # Windows 下用 shell 启动，避免 adb 子进程被立即关闭
            if platform.system() == "Windows":
                cmd_str = subprocess.list2cmdline(argv)
                kwargs["shell"] = True
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                self._process = subprocess.Popen(cmd_str, **kwargs)
            else:
                kwargs["shell"] = False
                self._process = subprocess.Popen(argv, **kwargs)
            time.sleep(0.3)
            if self._process.poll() is not None:
                err = "adb logcat 已退出，请检查：1) 是否已选择设备 2) 设备是否连接 3) ADB 是否可用"
                self._process = None
                messagebox.showerror("错误", err, parent=self)
                return
            self._stop = False
            self._queue = queue.Queue()
            self._start_btn.config(state="disabled")
            self._stop_btn.config(state="normal")
            self._state_var.set("运行中")
            threading.Thread(target=self._read_thread, daemon=True).start()
            self._schedule_process()
        except FileNotFoundError:
            messagebox.showerror("错误", "未找到 adb 命令，请确保 ADB 已安装并在 PATH 中", parent=self)
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {str(e)}", parent=self)

    def _stop_viewer(self):
        self._stop = True
        if self._process and self._process.poll() is None:
            try:
                if platform.system() == "Windows":
                    subprocess.run(f"taskkill /F /T /PID {self._process.pid}", shell=True)
                else:
                    self._process.terminate()
            except Exception:
                pass
            self._process = None
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._state_var.set("已停止（点击「开始查看」可实时刷新）")
        self._paused = False
        self._pause_btn.config(text="暂停")

    def _read_thread(self):
        exit_code = None
        try:
            if not self._process or not getattr(self._process, "stdout", None):
                return
            for line in self._process.stdout:
                if self._stop:
                    break
                if line:
                    try:
                        self._queue.put_nowait(line)
                    except queue.Full:
                        pass
        except Exception:
            pass
        finally:
            if self._process is not None:
                try:
                    exit_code = self._process.poll()
                except Exception:
                    exit_code = -1
                self._process = None
            self._reader_exit_code = exit_code
            if self.winfo_exists():
                self.after(0, self._on_reader_ended)

    def _on_reader_ended(self):
        self._stop = True
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._state_var.set("已停止（点击「开始查看」可实时刷新）")
        # 若非用户点击停止且进程异常退出，提示可能原因
        code = getattr(self, "_reader_exit_code", None)
        if code is not None and code != 0 and self.winfo_exists():
            msg = (
                "logcat 进程已意外退出（退出码: {}）。\n\n"
                "常见原因：\n"
                "1) 设备未连接或未选中 — 请在主界面选择设备\n"
                "2) 设备未授权 USB 调试 — 请在设备上点「允许」\n"
                "3) ADB 版本或权限问题 — 可尝试重启 ADB 或插拔 USB\n\n"
                "请检查后再次点击「开始查看」。"
            ).format(code)
            self.after(100, lambda: messagebox.showwarning("日志查看器", msg, parent=self))

    def _schedule_process(self):
        if self._stop or not self.winfo_exists():
            return
        self._process_queue()
        if not self._stop and self.winfo_exists():
            self._after_id = self.after(80, self._schedule_process)

    def _process_queue(self):
        keyword = (self._filter_var.get() or "").strip().lower()
        level_sel = (self._level_var.get() or "V").upper()
        level_pri = self._level_priority(level_sel)
        processed = 0
        try:
            while processed < self.MAX_PROCESS_PER_TICK:
                try:
                    line = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._total_count += 1
                time_str, pid, tid, level, tag, pkg, msg = self._parse_threadtime(line)
                if keyword and keyword not in (time_str + pid + tid + level + tag + pkg + msg).lower():
                    continue
                if self._level_priority(level) < level_pri:
                    continue
                if self._paused:
                    continue
                self._displayed_count += 1
                tag_name = f"level_{level.lower()}" if level.lower() in "vdiwef" else "level_i"
                self._tree.insert("", "end", values=(time_str, pid, tid, level, tag, pkg, msg), tags=(tag_name,))
                processed += 1
            # 超出最大行数时批量删除旧行，保证持续实时刷新
            children = self._tree.get_children()
            if len(children) > self.MAX_ROWS:
                to_remove = min(len(children) - self.MAX_ROWS, 500)
                for _ in range(to_remove):
                    c = self._tree.get_children()
                    if not c:
                        break
                    self._tree.delete(c[0])
            if self._auto_scroll_var.get():
                children = self._tree.get_children()
                if children:
                    self._tree.see(children[-1])
        except Exception:
            pass
        self._total_var.set(f"总计:{self._total_count}")
        self._displayed_var.set(f"显示:{self._displayed_count}")


class UIComponents:
    def __init__(self, parent):
        self.parent = parent
    
    def create_main_ui(self, parent):
        """创建主界面UI - 改进的分类标签页设计"""
        # 创建主选项卡控件
        self.main_notebook = ttk.Notebook(parent)
        self.main_notebook.pack(fill="both", expand=True)
        
        # 1. 硬件测试大类（首页）
        if is_main_tab_enabled("硬件测试"):
            hardware_frame = ttk.Frame(self.main_notebook)
            self.main_notebook.add(hardware_frame, text="硬件测试")
            self.setup_hardware_tab(hardware_frame)

        # 2. 声学测试大类
        if is_main_tab_enabled("声学测试"):
            acoustic_frame = ttk.Frame(self.main_notebook)
            self.main_notebook.add(acoustic_frame, text="声学测试")
            self.setup_acoustic_tab(acoustic_frame)

        # 3. 音频调试大类
        if is_main_tab_enabled("音频调试"):
            debug_frame = ttk.Frame(self.main_notebook)
            self.main_notebook.add(debug_frame, text="音频调试")
            self.setup_debug_tab(debug_frame)

        # 4. 常用功能大类
        if is_main_tab_enabled("常用功能"):
            common_frame = ttk.Frame(self.main_notebook)
            self.main_notebook.add(common_frame, text="常用功能")
            self.setup_common_tab(common_frame)

        # 5. 烧大象key（U盘/设备key相关）
        if is_main_tab_enabled("烧大象key"):
            keyburn_frame = ttk.Frame(self.main_notebook)
            self.main_notebook.add(keyburn_frame, text="烧大象key")
            self.setup_keyburn_tab(keyburn_frame)

        return self.main_notebook

    def show_software_info(self):
        """弹出软件信息窗口：版本号、作者、邮箱及功能简要说明"""
        root = getattr(self, "root", self.parent)
        win = tk.Toplevel(root)
        win.title("软件信息")
        win.geometry("480x420")
        win.resizable(True, True)
        win.transient(root)
        win.grab_set()
        # 与主窗口一致的图标（AcouTest logo）
        try:
            base_dir = self._get_runtime_base_dir()
            png_paths = [
                os.path.join(base_dir, "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(getattr(sys, "_MEIPASS", ""), "logo", "AcouTest.png") if getattr(sys, "frozen", False) else None,
            ]
            for path in png_paths:
                if path and os.path.exists(path):
                    try:
                        icon_img = tk.PhotoImage(file=path)
                        win.iconphoto(True, icon_img)
                        win._icon_image = icon_img  # 保持引用，避免被回收
                        break
                    except Exception:
                        pass
            if platform.system() == "Windows":
                ico_paths = [
                    os.path.join(base_dir, "logo", "AcouTest.ico"),
                    os.path.join("logo", "AcouTest.ico"),
                ]
                for ico_path in ico_paths:
                    if os.path.exists(ico_path):
                        try:
                            win.iconbitmap(ico_path)
                            break
                        except Exception:
                            pass
        except Exception:
            pass
        f = ttk.Frame(win, padding=15)
        f.pack(fill="both", expand=True)
        # 版本号、作者、邮箱（标签与具体信息同一行横向展示）
        info_frame = ttk.Frame(f)
        info_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(info_frame, text="版本号:", font=("Arial", 10)).grid(row=0, column=0, sticky="w")
        ttk.Label(info_frame, text=f"v{APP_VERSION}", font=("Arial", 10), foreground="#0066cc").grid(row=0, column=1, sticky="w", padx=(8, 0))

        ttk.Label(info_frame, text="作者:", font=("Arial", 10)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(info_frame, text="liangk", font=("Arial", 10), foreground="#0066cc").grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))

        ttk.Label(info_frame, text="邮箱:", font=("Arial", 10)).grid(row=2, column=0, sticky="w", pady=(4, 0))
        email_text = "807946809@qq.com"
        email_lbl = ttk.Label(info_frame, text=email_text, font=("Arial", 10), foreground="#0066cc", cursor="hand2")
        email_lbl.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        try:
            import webbrowser
            email_lbl.bind("<Button-1>", lambda e: webbrowser.open("mailto:" + email_text))
        except Exception:
            pass
        info_frame.grid_columnconfigure(1, weight=1)
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=8)

        # 检查更新按钮放在“功能说明”上方
        top_btn_frame = ttk.Frame(f)
        top_btn_frame.pack(fill="x", pady=(0, 6))
        if hasattr(self, "_check_update_async"):
            tk.Button(
                top_btn_frame,
                text="检查更新",
                width=8,
                command=lambda: self._check_update_async(manual=True),
            ).pack(side="left")

        # 功能说明（可滚动）
        ttk.Label(f, text="功能说明", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 4))
        desc_frame = ttk.Frame(f)
        desc_frame.pack(fill="both", expand=True, pady=4)
        scrollbar = ttk.Scrollbar(desc_frame)
        scrollbar.pack(side="right", fill="y")
        txt = tk.Text(desc_frame, wrap="word", font=("Arial", 9), height=12, yscrollcommand=scrollbar.set, state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=txt.yview)
        desc = (
            "声测大师(AcouTest) 面向 Android 设备的音频测试与远程控制，支持 ADB，便于设备管理与调试。\n\n"
            "【硬件测试】\n"
            "• 麦克风测试：多麦录音与参数配置\n"
            "• 雷达检查：雷达相关日志监测\n"
            "• 喇叭测试：默认/自定义音频播放验证\n"
            "• 多声道测试：7.1/2.1/2.0 音频播放验证\n\n"
            "【声学测试】\n"
            "• 气密性测试：堵mic/不堵mic双阶段录制、自动命名、频谱对比\n"
            "• 震音测试：震音播放与听感结果记录\n"
            "• 扫频测试：扫频文件播放录制、批量测试、波形查看\n\n"
            "【音频调试】\n"
            "• Loopback和Ref测试：回路与参考通道测试\n"
            "• HAL录音：HAL 录音与拉取\n"
            "• Logcat日志：日志抓取与查看\n"
            "• 唤醒监测：Google语音助手唤醒监测\n"
            "• 系统指令：常用dumpsys/tinymix 及自定义 shell指令\n\n"
            "【常用功能】\n"
            "• 遥控器：常用遥控器按键模拟\n"
            "• 截图功能：设备截图\n"
            "• OpenClaw：HTTP接口控制与连接状态日志\n"
            "• 账号登录：账号密码输入辅助\n\n"
            "【烧大象key】\n"
            "• u盘烧key\n"
            "• sn烧key"
        )
        txt.config(state="normal")
        txt.insert("1.0", desc)
        txt.config(state="disabled")

    def setup_keyburn_tab(self, parent):
        """设置烧大象key标签页"""
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        if is_sub_tab_enabled("烧大象key", "u盘烧key"):
            ukey_frame = ttk.Frame(nb)
            nb.add(ukey_frame, text="u盘烧key")
            self.setup_ukey_burn_tab(ukey_frame)

        if is_sub_tab_enabled("烧大象key", "sn烧key"):
            sn_frame = ttk.Frame(nb)
            nb.add(sn_frame, text="sn烧key")
            self.setup_sn_key_burn_tab(sn_frame)

    def _get_runtime_base_dir(self) -> str:
        """返回运行时基准目录（支持 PyInstaller onefile）"""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _apply_window_icon(self, win):
        """给弹窗统一设置与主程序一致的图标（优先 exe 同级资源）。"""
        try:
            base_dir = self._get_runtime_base_dir()
            png_paths = [
                os.path.join(base_dir, "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(getattr(sys, "_MEIPASS", ""), "logo", "AcouTest.png") if getattr(sys, "frozen", False) else None,
            ]
            for path in png_paths:
                if path and os.path.exists(path):
                    try:
                        icon_img = tk.PhotoImage(file=path)
                        win.iconphoto(True, icon_img)
                        win._icon_image = icon_img
                        break
                    except Exception:
                        pass

            if platform.system() == "Windows":
                ico_paths = [
                    os.path.join(base_dir, "logo", "AcouTest.ico"),
                    os.path.join("logo", "AcouTest.ico"),
                ]
                for ico_path in ico_paths:
                    if os.path.exists(ico_path):
                        try:
                            win.iconbitmap(ico_path)
                            break
                        except Exception:
                            pass
        except Exception:
            pass

    @staticmethod
    def _bind_mousewheel_to_canvas(widget, canvas):
        """为 widget 及其子控件绑定鼠标滚轮，使 canvas 可滚轮滚动（Windows: MouseWheel, Linux: Button-4/5）"""
        def _on_mousewheel(event):
            try:
                if hasattr(event, "delta"):
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-3, "units")
                elif event.num == 5:
                    canvas.yview_scroll(3, "units")
            except Exception:
                pass
        try:
            widget.bind("<MouseWheel>", _on_mousewheel)
        except Exception:
            pass
        try:
            widget.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
            widget.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))
        except Exception:
            pass
        for child in widget.winfo_children():
            UIComponents._bind_mousewheel_to_canvas(child, canvas)

    def _find_elevoc_src_dir(self) -> str:
        """
        在多个可能位置查找 elevoc_ukey 目录（避免 dist 运行时找不到资源）。
        优先顺序：
        1) exe 同级 / 源码同级
        2) 当前工作目录
        3) base_dir 上一级（开发/打包脚本可能从不同目录启动）
        """
        base_dir = self._get_runtime_base_dir()
        candidates = [
            os.path.join(base_dir, "elevoc_ukey"),
            os.path.join(os.getcwd(), "elevoc_ukey"),
            os.path.join(os.path.dirname(base_dir), "elevoc_ukey"),
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
        raise FileNotFoundError(
            "找不到 elevoc_ukey 目录。\n\n"
            "请确认已把 elevoc_ukey 放在以下任一位置：\n"
            + "\n".join(f"- {p}" for p in candidates)
            + "\n\n"
            "如果你运行的是 dist\\声测大师(AcouTest).exe：请用更新后的 Packager.bat 重新打包，"
            "它会自动把 elevoc_ukey 复制到 dist\\elevoc_ukey。"
        )

    def _prepare_elevoc_workdir(self) -> str:
        """
        准备 elevoc_ukey 工作目录：
        - DLL 可能只支持 ANSI 路径，中文路径会导致 init 失败
        - 这里复制一份到 TEMP 下的纯英文目录，确保 DLL 可读写 uuidSet / usb_info_0 / elevoc_log.txt
        """
        src_dir = self._find_elevoc_src_dir()

        dst_dir = os.path.join(tempfile.gettempdir(), "elevoc_ukey_runtime")
        os.makedirs(dst_dir, exist_ok=True)

        # 只复制必要文件，避免每次全量拷贝
        need_files = ["soft_encryption.dll", "uuidSet", "usb_info_0", "elevoc_log.txt", "README.md"]
        for name in need_files:
            src = os.path.join(src_dir, name)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, os.path.join(dst_dir, name))
                except Exception:
                    pass

        # 返回运行目录，同时把 src_dir 记录下来用于后续同步日志
        self._elevoc_src_dir = src_dir
        return dst_dir

    def _check_elevockey_support(self, serial: str, timeout_s: int = 10):
        """检查设备 unifykeys 是否支持 elevockey：执行 cat /sys/class/unifykeys/list，看是否包含 elevockey 节点。
        返回 (supported: bool, stdout: str)。调用前请先 adb root（本方法内部会执行）。"""
        if not (serial or "").strip():
            return False, ""
        subprocess.run(["adb", "-s", serial, "root"], capture_output=True, text=True, timeout=15)
        r = subprocess.run(
            ["adb", "-s", serial, "shell", "cat /sys/class/unifykeys/list"],
            capture_output=True, text=True, timeout=timeout_s,
        )
        out = (r.stdout or "") + (r.stderr or "")
        supported = "elevockey" in out
        return supported, out

    def _read_device_elevockey(self, serial: str, timeout_s: int = 15) -> tuple:
        """读取设备当前已烧录的 elevockey 值。
        返回 (current_key: str, error: str)。若未烧录或读为空则 current_key 为空；若执行失败则 error 非空。"""
        if not (serial or "").strip():
            return "", "请先选择设备"
        subprocess.run(["adb", "-s", serial, "root"], capture_output=True, text=True, timeout=15)
        r = subprocess.run(
            ["adb", "-s", serial, "shell", "echo elevockey > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read"],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if r.returncode == 0:
            return (r.stdout or "").strip(), ""
        r2 = subprocess.run(
            ["adb", "-s", serial, "shell", "su", "-c", "echo elevockey > /sys/class/unifykeys/name; cat /sys/class/unifykeys/read"],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if r2.returncode == 0:
            return (r2.stdout or "").strip(), ""
        return "", (r2.stderr or r.stderr or "读取 elevockey 失败").strip()

    def _sync_elevoc_log_to_src(self):
        """把 TEMP 运行目录里的 elevoc_log.txt 同步回 elevoc_ukey 源目录（方便用户在 dist 里查看）。"""
        try:
            st = getattr(self, "_elevoc_state", None)
            if not st:
                return
            workdir = st.get("workdir") or ""
            src_dir = st.get("src_dir") or getattr(self, "_elevoc_src_dir", "")
            if not workdir or not src_dir:
                return
            src = os.path.join(workdir, "elevoc_log.txt")
            dst = os.path.join(src_dir, "elevoc_log.txt")
            if os.path.exists(src):
                shutil.copy2(src, dst)
        except Exception:
            # 同步失败不影响主流程
            pass

    def _elevoc_init(self):
        """
        初始化 elevoc DLL（只初始化一次）。
        返回一个 dict：{dll, workdir, last_uuid(bytes), last_key(str)}
        """
        if getattr(self, "_elevoc_state", None):
            return self._elevoc_state

        workdir = self._prepare_elevoc_workdir()
        src_dir = getattr(self, "_elevoc_src_dir", "")
        dll_path = os.path.join(workdir, "soft_encryption.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"找不到 DLL：{dll_path}")

        elevoc_dll = ctypes.CDLL(dll_path)

        # 函数签名（与 elevoc_ukey/test.py 保持一致）
        elevoc_dll.elevoc_soft_encryption_init.argtypes = [c_char_p, c_void_p]
        elevoc_dll.elevoc_soft_encryption_init.restype = c_int
        elevoc_dll.elevoc_generate_license.argtypes = [c_void_p, c_int, POINTER(c_char)]
        elevoc_dll.elevoc_generate_license.restype = c_int
        elevoc_dll.elevoc_get_license_number.argtypes = []
        elevoc_dll.elevoc_get_license_number.restype = c_int
        elevoc_dll.elevoc_soft_encryption_destory.argtypes = []
        elevoc_dll.elevoc_soft_encryption_destory.restype = None

        # 传给 DLL：用本地编码（更兼容只支持 ANSI 路径的 DLL）
        log_dir_bytes = workdir.encode("mbcs", errors="ignore")
        ret = elevoc_dll.elevoc_soft_encryption_init(log_dir_bytes, None)
        if ret != 0:
            # 未插 U 盘或鉴权失败时常见 ret=-1；提示用户插 U 盘并参考文档
            _doc_url = "https://seirobotics.feishu.cn/wiki/Ih2ww3snDilkDykX5tgcehJDnnf?from=from_copylink"
            raise RuntimeError(
                "请先插入 U 盘 Key 后重试。\n\n"
                f"烧key方法详细步骤见文档：{_doc_url}\n\n"
                f"返回码: {ret}"
            )

        self._elevoc_state = {
            "dll": elevoc_dll,
            "workdir": workdir,
            "src_dir": src_dir,
            "last_uuid": b"",
            "last_key": "",
        }
        return self._elevoc_state

    @staticmethod
    def _bytes_to_hexstr(data: bytes) -> str:
        return "".join(f"{b:02X}" for b in data)

    def setup_ukey_burn_tab(self, parent):
        """u盘烧key（集成 elevoc_ukey 核心能力，不依赖 PyQt5）"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)

        header = ttk.LabelFrame(frame, text="说明")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text=(
                "流程：读取设备 SN → 调用 soft_encryption.dll 生成 license → 写回 unifykeys(elevockey)。\n"
                "提示：该 DLL 可能不支持中文路径，本工具会自动在临时英文目录运行所需文件。"
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", padx=10, pady=8)

        # 按钮区：分两行，避免窗口稍窄时按钮文字被遮挡/省略
        btn_bar = ttk.Frame(frame)
        btn_bar.pack(fill="x", pady=(0, 8))

        row1 = ttk.Frame(btn_bar)
        row1.pack(fill="x")
        status_var = tk.StringVar(value="就绪")
        ttk.Label(row1, textvariable=status_var).pack(side="left")

        # 单行按钮：从右往左依次排（保持最右侧对齐），顺序：UUID | 烧Key | 检查key | key剩余 | 打开日志 | 打开目录
        btn_check = ttk.Button(row1, text="检查key", style="Small.TButton", width=8)
        btn_remain = ttk.Button(row1, text="key剩余", style="Small.TButton", width=8)
        btn_burn = ttk.Button(row1, text="烧大象Key", style="Small.TButton", width=8)
        btn_uuid = ttk.Button(row1, text="读SN", style="Small.TButton", width=8)
        btn_open = ttk.Button(row1, text="打开目录", style="Small.TButton", width=10)
        btn_open_log = ttk.Button(row1, text="打开日志", style="Small.TButton", width=10)

        # pack(side="right") 时先 pack 的在最右侧，故先 pack 打开目录/打开日志，再 key剩余/检查key/烧Key/UUID（key剩余在检查key右边）
        btn_open.pack(side="right")
        btn_open_log.pack(side="right", padx=(6, 0))
        btn_remain.pack(side="right", padx=(6, 0))
        btn_check.pack(side="right", padx=(6, 0))
        btn_burn.pack(side="right", padx=(6, 0))
        btn_uuid.pack(side="right", padx=(6, 0))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill="both", expand=True)
        # 允许自动换行，长 key 不再“看不到”
        txt = tk.Text(text_frame, wrap="word", font=("Consolas", 9))
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.config(state="disabled")

        def _append(s: str):
            txt.config(state="normal")
            txt.insert("end", s)
            txt.see("end")
            txt.config(state="disabled")

        def _adb(serial: str, shell_cmd: str, timeout_s: int = 20):
            # shell_cmd 作为单个参数给 adb shell，避免 Windows shell 解析问题
            return subprocess.run(
                ["adb", "-s", serial, "shell", shell_cmd],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )

        def _adb_root(serial: str, timeout_s: int = 15):
            return subprocess.run(["adb", "-s", serial, "root"], capture_output=True, text=True, timeout=timeout_s)

        def _adb_su(serial: str, cmd: str, timeout_s: int = 20):
            # su -c：适配 user build / 需要 su 权限场景
            return subprocess.run(
                ["adb", "-s", serial, "shell", "su", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )

        def _read_unify_usid(serial: str) -> str:
            """
            读取 unifykeys usid（UUID/SN）。
            - 先 adb root + 直接访问 /sys/class/unifykeys
            - 如果失败/为空，再 fallback 到 su -c
            """
            _adb_root(serial)
            # 先单独 set name，再读回（比 && 更稳）
            _adb(serial, "echo usid > /sys/class/unifykeys/name", timeout_s=10)
            time.sleep(0.15)
            r = _adb(serial, "cat /sys/class/unifykeys/read", timeout_s=10)
            uuid = (r.stdout or "").strip()
            if uuid:
                return uuid

            # fallback：su -c 一把做完
            r2 = _adb_su(serial, "echo usid > /sys/class/unifykeys/name; cat /sys/class/unifykeys/read", timeout_s=10)
            uuid2 = (r2.stdout or "").strip()
            if uuid2:
                return uuid2

            # 仍失败：拼错误信息，方便定位
            err = (r.stderr or "").strip()
            err2 = (r2.stderr or "").strip()
            raise RuntimeError(
                "获取SN失败：unifykeys/read 无输出。\n"
                "可能原因：\n"
                "1) 设备未 root / 无 su 权限\n"
                "2) /sys/class/unifykeys 不存在或权限受限\n"
                "3) usid key 未配置\n\n"
                f"[adb shell stderr]\n{err}\n\n[su -c stderr]\n{err2}".strip()
            )

        def _get_serial() -> str:
            try:
                return (self.device_var.get() or "").strip()
            except Exception:
                return ""

        def _open_folder():
            try:
                p = self._find_elevoc_src_dir()
            except Exception as e:
                messagebox.showerror("错误", str(e))
                return
            try:
                os.startfile(p)  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("错误", f"打开目录失败：{type(e).__name__}: {e}")

        def _open_log():
            # 不依赖 DLL 初始化：直接找 elevoc_log.txt（先运行时目录，再 elevoc_ukey 源目录）
            cand = []
            workdir = os.path.join(tempfile.gettempdir(), "elevoc_ukey_runtime")
            cand.append(os.path.join(workdir, "elevoc_log.txt"))
            try:
                src_dir = self._find_elevoc_src_dir()
                cand.append(os.path.join(src_dir, "elevoc_log.txt"))
            except Exception:
                pass
            p = None
            for path in cand:
                if os.path.isfile(path):
                    p = path
                    break
            if not p:
                messagebox.showinfo("打开日志", "未找到 elevoc_log.txt。\n可检查：\n1) " + workdir + "\n2) elevoc_ukey 目录下是否有该文件。")
                return
            try:
                os.startfile(p)  # type: ignore[attr-defined]
            except Exception as e:
                messagebox.showerror("错误", f"打开日志失败：{type(e).__name__}: {e}")

        def _run_in_thread(fn):
            def worker():
                try:
                    self.root.after(0, lambda: status_var.set("运行中..."))
                    fn()
                    self.root.after(0, lambda: status_var.set("完成"))
                except Exception as e:
                    self.root.after(0, lambda: status_var.set("失败"))
                    self.root.after(0, lambda: _append(f"\n[ERROR] {type(e).__name__}: {e}\n"))
            threading.Thread(target=worker, daemon=True).start()

        def _wrap_long(s: str, width: int = 64) -> str:
            s = (s or "").strip()
            if not s:
                return ""
            return "\n".join(textwrap.wrap(s, width=width, break_long_words=True, drop_whitespace=False))

        def do_get_uuid():
            serial = _get_serial()
            if not serial:
                messagebox.showerror("错误", "请先选择设备")
                return
            # 读SN 只依赖 unifykeys 的 usid，不依赖 elevockey，也不应先依赖 DLL
            _append("\n=== 获取SN ===\n")
            try:
                uuid = _read_unify_usid(serial)
            except Exception as e:
                _append(f"unifykeys usid 读取失败: {e}\n")
                # 尝试显示设备序列号，便于排查
                try:
                    r = subprocess.run(["adb", "-s", serial, "get-serialno"], capture_output=True, text=True, timeout=10)
                    if r.returncode == 0 and (r.stdout or "").strip():
                        _append(f"设备序列号(adb): {(r.stdout or '').strip()}（仅作参考，烧key 需 unifykeys 的 usid）\n")
                except Exception:
                    pass
                # 尝试列出 unifykeys，便于确认设备是否有该节点
                try:
                    r2 = _adb(serial, "cat /sys/class/unifykeys/list 2>&1", timeout_s=5)
                    out = (r2.stdout or "") + (r2.stderr or "")
                    if out.strip():
                        _append("当前设备 unifykeys/list 输出（前 500 字符）:\n")
                        _append(out.strip()[:500] + ("\n..." if len(out.strip()) > 500 else "") + "\n")
                except Exception:
                    pass
                _append("建议：请确认设备已 adb root、/sys/class/unifykeys 存在且含 usid 节点；部分机型需 su 权限。\n")
                raise
            _append(f"SN(usid): {uuid} | length: {len(uuid)}\n")
            try:
                st = self._elevoc_init()
                st["last_uuid"] = uuid.encode("utf-8", errors="ignore")
                try:
                    count = st["dll"].elevoc_get_license_number()
                except Exception:
                    count = -1
                _append(f"License count: {count}\n")
                self._sync_elevoc_log_to_src()
            except Exception as e:
                err_msg = str(e).strip().split("\n")[0][:80]
                _append(f"（{err_msg}烧key 前需再次读SN）\n")

        def do_show_license_count():
            """查看 U 盘中的 key 剩余数量（需已插 U 盘并授权）。"""
            _append("\n=== 查看 U 盘 Key 剩余数量 ===\n")
            try:
                st = self._elevoc_init()
                count = st["dll"].elevoc_get_license_number()
                _append(f"U 盘剩余 key 数量: {count}\n")
                self._sync_elevoc_log_to_src()
                msg = f"当前 U 盘剩余 key 数量：{count}" if count >= 0 else "无法获取（请确认 U 盘已插入且已授权）"
                self.root.after(0, lambda: messagebox.showinfo("U盘Key剩余数量", msg))
            except Exception as e:
                _append(f"获取失败: {e}\n")
                self.root.after(0, lambda: messagebox.showerror("U盘Key剩余数量", f"获取失败：{e}\n请确认 U 盘已插入且 elevoc_ukey 目录与 DLL 可用。"))

        def do_burn():
            serial = _get_serial()
            if not serial:
                messagebox.showerror("错误", "请先选择设备")
                return
            supported, _ = self._check_elevockey_support(serial)
            if not supported:
                _append("\n不支持：设备 unifykeys 列表中无 elevockey 节点，无法烧key。\n")
                messagebox.showerror("不支持烧key", "设备不支持 elevockey。请先确认设备上 cat /sys/class/unifykeys/list 中含有 elevockey 节点后再操作。")
                return
            # 设备已有 key 时弹窗确认，避免误覆盖
            current_key, _ = self._read_device_elevockey(serial)
            if (current_key or "").strip():
                if not messagebox.askyesno("确认烧录", "当前设备已有 key，是否确认覆盖烧录？\n（选择「否」将取消本次烧录）"):
                    _append("\n用户取消烧录（设备已有 key）。\n")
                    return
            st = self._elevoc_init()
            dll = st["dll"]
            uuid_bytes: bytes = st.get("last_uuid") or b""
            if not uuid_bytes:
                raise RuntimeError("请先点击“获取SN”")

            LICENSE_DATA_LEN = 192
            license_dat = (c_char * LICENSE_DATA_LEN)()
            ret = dll.elevoc_generate_license(uuid_bytes, len(uuid_bytes), license_dat)
            if ret != 0:
                raise RuntimeError(f"Generate license fail (ret={ret})")

            license_hex = self._bytes_to_hexstr(bytes(license_dat))
            st["last_key"] = license_hex
            _append("\n=== 生成并写入License(烧key) ===\n")
            _append("license:\n")
            _append(_wrap_long(license_hex) + "\n")

            # 写回 unifykeys：先 adb root，失败再 su -c
            _adb_root(serial)
            r = _adb(serial, f"echo elevockey > /sys/class/unifykeys/name && echo {license_hex} > /sys/class/unifykeys/write", timeout_s=20)
            if r.returncode != 0:
                r2 = _adb_su(serial, f"echo elevockey > /sys/class/unifykeys/name; echo {license_hex} > /sys/class/unifykeys/write", timeout_s=20)
                if r2.returncode != 0:
                    raise RuntimeError((r2.stderr or r.stderr or "写入失败").strip())
            _append("写入成功。\n")
            self._sync_elevoc_log_to_src()

        def do_check():
            serial = _get_serial()
            if not serial:
                messagebox.showerror("错误", "请先选择设备")
                return
            supported, _ = self._check_elevockey_support(serial)
            if not supported:
                _append("\n不支持：设备 unifykeys 列表中无 elevockey 节点。\n")
                messagebox.showerror("不支持", "设备不支持 elevockey。请先确认 cat /sys/class/unifykeys/list 中含有 elevockey 节点。")
                return
            st = self._elevoc_init()
            expected = (st.get("last_key") or "").strip()
            _append("\n=== 检查License ===\n")
            _adb_root(serial)
            r = _adb(serial, "echo elevockey > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read", timeout_s=20)
            got = (r.stdout or "").strip()
            if (r.returncode != 0) or (not got):
                r2 = _adb_su(serial, "echo elevockey > /sys/class/unifykeys/name; cat /sys/class/unifykeys/read", timeout_s=20)
                if r2.returncode == 0:
                    got = (r2.stdout or "").strip()
                else:
                    raise RuntimeError((r2.stderr or r.stderr or "读取失败").strip())
            if not got:
                _append("License status: NO DATA\n")
                return
            if expected:
                _append("Expected:\n")
                _append(_wrap_long(expected) + "\n")
                _append("Got:\n")
                _append(_wrap_long(got) + "\n")
                _append("Result  : OK\n" if got == expected else "Result  : MISMATCH\n")
            else:
                _append("Got:\n")
                _append(_wrap_long(got) + "\n")
                _append("Result  : DATA FOUND（未生成过 expected，仅展示读取值）\n")
            self._sync_elevoc_log_to_src()

        btn_open.config(command=_open_folder)
        btn_open_log.config(command=_open_log)
        btn_uuid.config(command=lambda: _run_in_thread(do_get_uuid))
        btn_burn.config(command=lambda: _run_in_thread(do_burn))
        btn_check.config(command=lambda: _run_in_thread(do_check))
        btn_remain.config(command=lambda: _run_in_thread(do_show_license_count))

    def setup_sn_key_burn_tab(self, parent):
        """sn烧key：按 sn烧key.bat 的逻辑集成（写入 unifykeys:elevockey）"""
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        frame = ttk.Frame(nb, padding=10)
        nb.add(frame, text="烧elevockey")

        sn_edit_frame = ttk.Frame(nb, padding=10)
        nb.add(sn_edit_frame, text="重写设备SN")

        header = ttk.LabelFrame(frame, text="说明")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text=(
                "功能：检查设备 unifykeys 是否支持 elevockey，并可新增/替换 elevockey。\n"
                "流程：adb root → 检查 list → 读取当前值 → 输入新 elevockey → 写入 → 读回校验。"
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", padx=10, pady=8)

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 8))

        status_var = tk.StringVar(value="就绪")
        ttk.Label(top, textvariable=status_var).pack(side="left")

        # SN 展示（自动获取并填入）
        sn_var = tk.StringVar(value="")
        ttk.Label(top, text="设备SN:").pack(side="left", padx=(12, 6))
        sn_entry = ttk.Entry(top, textvariable=sn_var, width=24, state="readonly")
        sn_entry.pack(side="left")

        # 操作按钮
        btn_get_sn = ttk.Button(top, text="获取SN", style="Small.TButton")
        btn_support = ttk.Button(top, text="检查支持", style="Small.TButton")
        btn_read = ttk.Button(top, text="读取当前key", style="Small.TButton")
        btn_get_sn.pack(side="right")
        btn_support.pack(side="right", padx=(6, 0))
        btn_read.pack(side="right", padx=(6, 0))

        key_frame = ttk.LabelFrame(frame, text="写入 elevockey")
        key_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(key_frame, text="elevockey:").pack(side="left", padx=(10, 6), pady=8)
        key_var = tk.StringVar(value="")
        key_entry = ttk.Entry(key_frame, textvariable=key_var)
        key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        btn_burn = ttk.Button(key_frame, text="写入/替换(烧key)", style="Small.TButton")
        btn_burn.pack(side="right", padx=(0, 10), pady=8)

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill="both", expand=True)
        txt = tk.Text(text_frame, wrap="none", font=("Consolas", 9))
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)
        txt.config(state="disabled")

        UNIFY_KEY_NAME_PATH = "/sys/class/unifykeys/name"
        UNIFY_KEY_READ_PATH = "/sys/class/unifykeys/read"
        UNIFY_KEY_WRITE_PATH = "/sys/class/unifykeys/write"
        UNIFY_KEY_LIST_PATH = "/sys/class/unifykeys/list"
        ELEVOC_KEY_NAME = "elevockey"

        def _append(s: str):
            txt.config(state="normal")
            txt.insert("end", s)
            txt.see("end")
            txt.config(state="disabled")

        def _serial() -> str:
            try:
                return (self.device_var.get() or "").strip()
            except Exception:
                return ""

        def _run(argv, timeout_s=15):
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)

        def _adb_shell(serial: str, cmd: str, timeout_s=15):
            # cmd 作为单个参数传给 adb shell，避免 Windows shell 解析问题
            return _run(["adb", "-s", serial, "shell", cmd], timeout_s=timeout_s)

        def _adb_root(serial: str):
            return _run(["adb", "-s", serial, "root"], timeout_s=15)

        def _ensure_device() -> str:
            if hasattr(self, "check_device_selected") and not self.check_device_selected():
                return ""
            serial = _serial()
            if not serial:
                messagebox.showerror("错误", "请先选择设备")
                return ""
            return serial

        def _do_get_sn():
            serial = _ensure_device()
            if not serial:
                return
            _append("\n=== 获取SN ===\n")
            r = _run(["adb", "-s", serial, "get-serialno"], timeout_s=10)
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "adb get-serialno 失败")
            sn = (r.stdout or "").strip()
            sn_var.set(sn)
            _append(f"SN: {sn}\n")

        def _auto_fill_sn_quiet():
            """自动填充 SN：不弹窗、不写日志（避免干扰）"""
            serial = _serial()
            if not serial:
                return
            try:
                r = _run(["adb", "-s", serial, "get-serialno"], timeout_s=10)
                if r.returncode == 0:
                    sn = (r.stdout or "").strip()
                    if sn:
                        sn_var.set(sn)
            except Exception:
                pass

        def _do_check_support():
            serial = _ensure_device()
            if not serial:
                return
            _append("\n=== 检查驱动DTS是否支持 elevockey ===\n")
            _append("$ adb root\n")
            _adb_root(serial)
            r = _adb_shell(serial, f"cat {UNIFY_KEY_LIST_PATH}", timeout_s=10)
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "读取 unifykeys list 失败")
            out = r.stdout or ""
            if ELEVOC_KEY_NAME in out:
                _append("支持：驱动DTS支持【elevockey】\n")
            else:
                _append("不支持：驱动DTS不支持【elevockey】\n")
                raise RuntimeError("驱动DTS不支持 elevockey")

        def _do_read_current():
            serial = _ensure_device()
            if not serial:
                return
            supported, _ = self._check_elevockey_support(serial)
            if not supported:
                _append("\n不支持：设备 unifykeys 列表中无 elevockey 节点，无法读取。\n")
                messagebox.showerror("不支持", "设备不支持 elevockey。请先点击「检查支持」确认 cat /sys/class/unifykeys/list 中含有 elevockey 节点。")
                return
            _append("\n=== 读取当前 elevockey ===\n")
            _append("$ adb root\n")
            _adb_root(serial)
            r = _adb_shell(serial, f"echo {ELEVOC_KEY_NAME} > {UNIFY_KEY_NAME_PATH} && cat {UNIFY_KEY_READ_PATH}", timeout_s=10)
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "读取 elevockey 失败")
            val = (r.stdout or "").strip()
            if val:
                _append(f"已烧录 elevockey: {val}\n")
            else:
                _append("未烧录 elevockey（read 为空）\n")

        def _do_burn():
            serial = _ensure_device()
            if not serial:
                return
            key = (key_var.get() or "").strip()
            if not key:
                messagebox.showerror("错误", "请输入 elevockey")
                return
            # 设备已有 key 时弹窗确认，避免误覆盖
            current_key, _ = self._read_device_elevockey(serial)
            if (current_key or "").strip():
                if not messagebox.askyesno("确认烧录", "当前设备已有 key，是否确认覆盖烧录？\n（选择「否」将取消本次烧录）"):
                    _append("\n用户取消烧录（设备已有 key）。\n")
                    return

            if not messagebox.askyesno("确认", "确认新增或替换 elevockey？"):
                _append("\n用户取消操作。\n")
                return

            _append("\n=== 写入 elevockey ===\n")
            supported, _ = self._check_elevockey_support(serial)
            if not supported:
                _append("不支持：设备 unifykeys 列表中无 elevockey 节点，无法烧录。\n")
                raise RuntimeError("设备不支持 elevockey，请先确认 cat /sys/class/unifykeys/list 中含有 elevockey 节点。")

            if not messagebox.askyesno("再次确认", "请确认 elevockey 内容正确，确定开始烧录？"):
                _append("\n用户取消操作。\n")
                return

            _append("$ adb root\n")
            _adb_root(serial)
            _append("正在烧录...\n")
            r = _adb_shell(serial, f"echo {ELEVOC_KEY_NAME} > {UNIFY_KEY_NAME_PATH} && echo {key} > {UNIFY_KEY_WRITE_PATH}", timeout_s=10)
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "写入失败")
            _append("烧录完成，开始校验...\n")

            r = _adb_shell(serial, f"echo {ELEVOC_KEY_NAME} > {UNIFY_KEY_NAME_PATH} && cat {UNIFY_KEY_READ_PATH}", timeout_s=10)
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "读取校验失败")
            val = (r.stdout or "").strip()
            if val:
                _append(f"烧录成功，【elevockey】: {val}\n")
            else:
                raise RuntimeError("烧录失败：读回为空")

        def _run_in_thread(fn):
            def worker():
                try:
                    self.root.after(0, lambda: status_var.set("运行中..."))
                    fn()
                    self.root.after(0, lambda: status_var.set("完成"))
                except Exception as e:
                    self.root.after(0, lambda: status_var.set("失败"))
                    self.root.after(0, lambda: _append(f"\n[ERROR] {type(e).__name__}: {e}\n"))
            threading.Thread(target=worker, daemon=True).start()

        btn_get_sn.config(command=lambda: _run_in_thread(_do_get_sn))
        btn_support.config(command=lambda: _run_in_thread(_do_check_support))
        btn_read.config(command=lambda: _run_in_thread(_do_read_current))
        btn_burn.config(command=lambda: _run_in_thread(_do_burn))

        # 初次进入自动填一次
        try:
            self.root.after(300, lambda: _auto_fill_sn_quiet())
        except Exception:
            pass

        # 设备切换时自动刷新（做简单 debounce）
        try:
            _sn_timer = {"id": None}
            def _on_device_change(*_a):
                try:
                    if _sn_timer["id"] is not None:
                        self.root.after_cancel(_sn_timer["id"])
                except Exception:
                    pass
                try:
                    _sn_timer["id"] = self.root.after(300, _auto_fill_sn_quiet)
                except Exception:
                    pass

            if hasattr(self, "device_var") and isinstance(self.device_var, tk.StringVar):
                self.device_var.trace_add("write", _on_device_change)
        except Exception:
            pass

        # -------------------- 修改设备SN（usid） --------------------
        edit_header = ttk.LabelFrame(sn_edit_frame, text="说明")
        edit_header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            edit_header,
            text=(
                "常用方式：adb shell → su → echo usid > name → echo <SN> > write → cat read → reboot\n"
                "注意：需要 su 权限（或可 adb root 的 userdebug）。"
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", padx=10, pady=8)

        # 这里如果把输入框/勾选框/按钮都塞一行，窗口稍窄时按钮会被挤成“...”
        # 改为两行：第一行参数，第二行按钮，保证不遮挡文字。
        edit_top = ttk.Frame(sn_edit_frame)
        edit_top.pack(fill="x", pady=(0, 8))

        row_a = ttk.Frame(edit_top)
        row_a.pack(fill="x", pady=(0, 6))
        edit_status = tk.StringVar(value="就绪")
        ttk.Label(row_a, textvariable=edit_status).pack(side="left")

        ttk.Label(row_a, text="新SN:").pack(side="left", padx=(12, 6))
        new_sn_var = tk.StringVar()
        new_sn_entry = ttk.Entry(row_a, textvariable=new_sn_var, width=28)
        new_sn_entry.pack(side="left")

        reboot_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_a, text="写完后重启", variable=reboot_var).pack(side="left", padx=(12, 0))

        row_b = ttk.Frame(edit_top)
        row_b.pack(fill="x")
        btn_read_usid = ttk.Button(row_b, text="读取当前SN(usid)", style="Small.TButton", width=16)
        btn_write_usid = ttk.Button(row_b, text="写入SN(usid)", style="Small.TButton", width=14)
        btn_reboot = ttk.Button(row_b, text="重启设备", style="Small.TButton", width=10)
        btn_reboot.pack(side="right")
        btn_write_usid.pack(side="right", padx=(6, 0))
        btn_read_usid.pack(side="right", padx=(6, 0))

        edit_text_frame = ttk.Frame(sn_edit_frame)
        edit_text_frame.pack(fill="both", expand=True)
        edit_txt = tk.Text(edit_text_frame, wrap="none", font=("Consolas", 9))
        edit_vsb = ttk.Scrollbar(edit_text_frame, orient="vertical", command=edit_txt.yview)
        edit_hsb = ttk.Scrollbar(edit_text_frame, orient="horizontal", command=edit_txt.xview)
        edit_txt.configure(yscrollcommand=edit_vsb.set, xscrollcommand=edit_hsb.set)
        edit_vsb.pack(side="right", fill="y")
        edit_hsb.pack(side="bottom", fill="x")
        edit_txt.pack(side="left", fill="both", expand=True)
        edit_txt.config(state="disabled")

        def _eappend(s: str):
            edit_txt.config(state="normal")
            edit_txt.insert("end", s)
            edit_txt.see("end")
            edit_txt.config(state="disabled")

        def _adb_su(serial: str, cmd: str, timeout_s=15):
            return subprocess.run(["adb", "-s", serial, "shell", "su", "-c", cmd], capture_output=True, text=True, timeout=timeout_s)

        def _adb_root(serial: str, timeout_s=15):
            return subprocess.run(["adb", "-s", serial, "root"], capture_output=True, text=True, timeout=timeout_s)

        def _adb_shell(serial: str, cmd: str, timeout_s=15):
            return subprocess.run(["adb", "-s", serial, "shell", cmd], capture_output=True, text=True, timeout=timeout_s)

        def _ensure_serial() -> str:
            if hasattr(self, "check_device_selected") and not self.check_device_selected():
                return ""
            s = _serial()
            if not s:
                messagebox.showerror("错误", "请先选择设备")
                return ""
            return s

        def _validate_sn(val: str) -> str:
            v = (val or "").strip()
            if not v:
                raise ValueError("请输入SN")
            # 避免 shell 注入/转义问题：SN 通常是字母数字，必要时你再告诉我规则我放宽
            if not re.match(r"^[0-9A-Za-z._\\-]+$", v):
                raise ValueError("SN 仅允许字母数字及 . _ - 字符（避免转义问题）")
            return v

        def _read_usid():
            serial = _ensure_serial()
            if not serial:
                return
            _eappend("\n=== 读取当前SN(usid) ===\n")
            _adb_root(serial)
            r = _adb_shell(serial, "echo usid > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read", timeout_s=10)
            out = (r.stdout or "").strip()
            if not out:
                r2 = _adb_su(serial, "echo usid > /sys/class/unifykeys/name; cat /sys/class/unifykeys/read", timeout_s=10)
                out = (r2.stdout or "").strip()
                if not out:
                    raise RuntimeError((r2.stderr or r.stderr or "读取失败").strip())
            _eappend(f"usid: {out}\n")

        def _write_usid():
            serial = _ensure_serial()
            if not serial:
                return
            sn_new = _validate_sn(new_sn_var.get())
            if not messagebox.askyesno("确认", f"确认写入新的 usid/SN？\n\n{sn_new}"):
                _eappend("\n用户取消操作。\n")
                return
            _eappend("\n=== 写入SN(usid) ===\n")
            _adb_root(serial)

            # 先尝试直接写（root），不行再 su
            r = _adb_shell(serial, f"echo usid > /sys/class/unifykeys/name && echo {sn_new} > /sys/class/unifykeys/write && cat /sys/class/unifykeys/read", timeout_s=10)
            out = (r.stdout or "").strip()
            if not out:
                r2 = _adb_su(serial, f"echo usid > /sys/class/unifykeys/name; echo {sn_new} > /sys/class/unifykeys/write; cat /sys/class/unifykeys/read", timeout_s=10)
                out = (r2.stdout or "").strip()
                if not out:
                    raise RuntimeError((r2.stderr or r.stderr or "写入失败").strip())

            _eappend(f"读回: {out}\n")
            if out != sn_new:
                _eappend("警告：读回值与写入值不一致，请检查设备实现。\n")

            if reboot_var.get():
                _eappend("执行重启...\n")
                subprocess.run(["adb", "-s", serial, "reboot"], capture_output=True, text=True)

        def _do_reboot():
            serial = _ensure_serial()
            if not serial:
                return
            _eappend("\n=== 重启设备 ===\n")
            subprocess.run(["adb", "-s", serial, "reboot"], capture_output=True, text=True)

        def _run2(fn):
            def worker():
                try:
                    self.root.after(0, lambda: edit_status.set("运行中..."))
                    fn()
                    self.root.after(0, lambda: edit_status.set("完成"))
                except Exception as e:
                    self.root.after(0, lambda: edit_status.set("失败"))
                    self.root.after(0, lambda: _eappend(f"\n[ERROR] {type(e).__name__}: {e}\n"))
            threading.Thread(target=worker, daemon=True).start()

        btn_read_usid.config(command=lambda: _run2(_read_usid))
        btn_write_usid.config(command=lambda: _run2(_write_usid))
        btn_reboot.config(command=lambda: _run2(_do_reboot))
    
    def setup_acoustic_tab(self, parent):
        """设置声学测试标签页"""
        # 创建子标签页
        acoustic_notebook = ttk.Notebook(parent)
        acoustic_notebook.pack(fill="both", expand=True, padx=10, pady=10)

        if is_sub_tab_enabled("声学测试", "气密性测试"):
            airtight_frame = ttk.Frame(acoustic_notebook)
            acoustic_notebook.add(airtight_frame, text="气密性测试")
            self.setup_airtightness_tab(airtight_frame)

        if is_sub_tab_enabled("声学测试", "震音测试"):
            jitter_frame = ttk.Frame(acoustic_notebook)
            acoustic_notebook.add(jitter_frame, text="震音测试")
            self.setup_jitter_tab(jitter_frame)

        if is_sub_tab_enabled("声学测试", "扫频测试"):
            sweep_frame = ttk.Frame(acoustic_notebook)
            acoustic_notebook.add(sweep_frame, text="扫频测试")
            self.setup_sweep_tab(sweep_frame)

    def setup_hardware_tab(self, parent):
        """设置硬件测试标签页"""
        # 创建子标签页
        hardware_notebook = ttk.Notebook(parent)
        hardware_notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        if is_sub_tab_enabled("硬件测试", "麦克风测试"):
            mic_frame = ttk.Frame(hardware_notebook)
            hardware_notebook.add(mic_frame, text="麦克风测试")
            self.setup_mic_tab(mic_frame)

        if is_sub_tab_enabled("硬件测试", "雷达检查"):
            radar_frame = ttk.Frame(hardware_notebook)
            hardware_notebook.add(radar_frame, text="雷达检查")
            self.setup_radar_tab(radar_frame)

        if is_sub_tab_enabled("硬件测试", "喇叭测试"):
            speaker_frame = ttk.Frame(hardware_notebook)
            hardware_notebook.add(speaker_frame, text="喇叭测试")
            self.setup_speaker_tab(speaker_frame)

        if is_sub_tab_enabled("硬件测试", "多声道测试"):
            multichannel_frame = ttk.Frame(hardware_notebook)
            hardware_notebook.add(multichannel_frame, text="多声道测试")
            self.setup_multichannel_tab(multichannel_frame)

    def setup_debug_tab(self, parent):
        """设置音频调试标签页"""
        # 创建子标签页
        debug_notebook = ttk.Notebook(parent)
        debug_notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        if is_sub_tab_enabled("音频调试", "Loopback和Ref测试"):
            loopback_frame = ttk.Frame(debug_notebook)
            debug_notebook.add(loopback_frame, text="Loopback和Ref测试")
            self.setup_loopback_tab(loopback_frame)

        if is_sub_tab_enabled("音频调试", "HAL录音"):
            hal_frame = ttk.Frame(debug_notebook)
            debug_notebook.add(hal_frame, text="HAL录音")
            self.setup_hal_recording_tab(hal_frame)

        if is_sub_tab_enabled("音频调试", "Logcat日志"):
            logcat_frame = ttk.Frame(debug_notebook)
            debug_notebook.add(logcat_frame, text="Logcat日志")
            self.setup_logcat_tab(logcat_frame)

        if is_sub_tab_enabled("音频调试", "唤醒监测"):
            hotword_frame = ttk.Frame(debug_notebook)
            debug_notebook.add(hotword_frame, text="唤醒监测")
            self.setup_hotword_monitor_tab(hotword_frame)

        if is_sub_tab_enabled("音频调试", "系统指令"):
            syscmd_frame = ttk.Frame(debug_notebook)
            debug_notebook.add(syscmd_frame, text="系统指令")
            self.setup_system_cmd_tab(syscmd_frame)

    def setup_common_tab(self, parent):
        """设置常用功能标签页"""
        # 创建子标签页
        common_notebook = ttk.Notebook(parent)
        common_notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        if is_sub_tab_enabled("常用功能", "遥控器"):
            remote_frame = ttk.Frame(common_notebook)
            common_notebook.add(remote_frame, text="遥控器")
            self.setup_remote_tab(remote_frame)

        if is_sub_tab_enabled("常用功能", "本地播放"):
            playback_frame = ttk.Frame(common_notebook)
            common_notebook.add(playback_frame, text="本地播放")
            self.setup_local_playback_tab(playback_frame)

        if is_sub_tab_enabled("常用功能", "截图功能"):
            screenshot_frame = ttk.Frame(common_notebook)
            common_notebook.add(screenshot_frame, text="截图功能")
            self.setup_screenshot_tab(screenshot_frame)

        if is_sub_tab_enabled("常用功能", "账号登录"):
            account_login_frame = ttk.Frame(common_notebook)
            common_notebook.add(account_login_frame, text="账号登录")
            self.setup_account_login_tab(account_login_frame)

        if is_sub_tab_enabled("常用功能", "OpenClaw"):
            openclaw_frame = ttk.Frame(common_notebook)
            common_notebook.add(openclaw_frame, text="OpenClaw")
            self.setup_openclaw_tab(openclaw_frame)

    def setup_openclaw_tab(self, parent):
        """OpenClaw 对接状态与日志面板。"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.LabelFrame(frame, text="连接状态")
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, textvariable=getattr(self, "control_api_conn_var", tk.StringVar(value="OpenClaw: 未连接")),
                  font=("Arial", 10, "bold")).pack(anchor="w", padx=8, pady=(6, 2))

        api_host = "127.0.0.1"
        api_port = "8765"
        try:
            if getattr(self, "control_api", None) and getattr(self.control_api, "actual_port", None):
                api_host = str(getattr(self.control_api, "host", api_host))
                api_port = str(getattr(self.control_api, "actual_port", api_port))
        except Exception:
            pass
        info_txt = (
            f"接口地址: http://{api_host}:{api_port}\n"
            "请求头: X-Api-Token: acoutest-local-token"
        )
        ttk.Label(top, text=info_txt, justify="left", foreground="#666").pack(anchor="w", padx=8, pady=(0, 8))

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Button(bar, text="清空日志", style="Small.TButton", command=lambda: self._clear_openclaw_log_text()).pack(side="left")

        log_frame = ttk.LabelFrame(frame, text="OpenClaw 操作日志（含相关 ADB 命令）")
        log_frame.pack(fill="both", expand=True)
        self.openclaw_log_text = tk.Text(log_frame, height=14, font=("Consolas", 9), wrap="word", state="disabled")
        y = ttk.Scrollbar(log_frame, orient="vertical", command=self.openclaw_log_text.yview)
        self.openclaw_log_text.configure(yscrollcommand=y.set)
        self.openclaw_log_text.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")
        self._append_openclaw_log_text("OpenClaw 面板已就绪，等待连接。")

    def _append_openclaw_log_text(self, line):
        txt = getattr(self, "openclaw_log_text", None)
        if not txt or not txt.winfo_exists():
            return
        try:
            txt.config(state="normal")
            txt.insert("end", f"{line}\n")
            txt.see("end")
            txt.config(state="disabled")
        except Exception:
            pass

    def _clear_openclaw_log_text(self):
        txt = getattr(self, "openclaw_log_text", None)
        if not txt or not txt.winfo_exists():
            return
        try:
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.config(state="disabled")
        except Exception:
            pass

    def setup_acoustic_category(self, parent):
        """设置声学测试分类"""
        # 说明文字
        desc_label = ttk.Label(parent, text="音频频率响应和声学特性测试", 
                              font=("Arial", 9), foreground="gray")
        desc_label.pack(pady=(0, 10))
        
        # 扫频测试按钮
        sweep_button = ttk.Button(parent, text="扫频测试", 
                                 command=self.open_sweep_window,
                                 width=20)
        sweep_button.pack(pady=5, fill="x")
        
        # 添加扫频测试说明
        sweep_desc = ttk.Label(parent, text="• 播放扫频音频并录制回环信号\n• 支持批量测试多个频率文件\n• 可自定义播放和录制参数", 
                              font=("Arial", 8), foreground="gray", justify="left")
        sweep_desc.pack(pady=(2, 10), anchor="w")
    
    def setup_hardware_category(self, parent):
        """设置硬件测试分类"""
        # 说明文字
        desc_label = ttk.Label(parent, text="设备硬件功能检测和测试", 
                              font=("Arial", 9), foreground="gray")
        desc_label.pack(pady=(0, 10))
        
        # 麦克风测试
        mic_button = ttk.Button(parent, text="麦克风测试", 
                               command=self.open_mic_window,
                               width=20)
        mic_button.pack(pady=2, fill="x")
        
        # 雷达检查
        radar_button = ttk.Button(parent, text="雷达检查", 
                                 command=self.open_radar_window,
                                 width=20)
        radar_button.pack(pady=2, fill="x")
        
        # 喇叭测试
        speaker_button = ttk.Button(parent, text="喇叭测试", 
                                   command=self.open_speaker_window,
                                   width=20)
        speaker_button.pack(pady=2, fill="x")
        
        # 多声道测试
        multichannel_button = ttk.Button(parent, text="多声道测试", 
                                        command=self.open_multichannel_window,
                                        width=20)
        multichannel_button.pack(pady=2, fill="x")
    
    def setup_debug_category(self, parent):
        """设置音频调试分类"""
        # 说明文字
        desc_label = ttk.Label(parent, text="音频系统调试和日志分析", 
                              font=("Arial", 9), foreground="gray")
        desc_label.pack(pady=(0, 10))
        
        # Loopback和Ref测试
        loopback_button = ttk.Button(parent, text="Loopback和Ref测试", 
                                    command=self.open_loopback_window,
                                    width=20)
        loopback_button.pack(pady=2, fill="x")
        
        # HAL录音
        hal_button = ttk.Button(parent, text="HAL录音", 
                               command=self.open_hal_window,
                               width=20)
        hal_button.pack(pady=2, fill="x")
        
        # Logcat日志
        logcat_button = ttk.Button(parent, text="Logcat日志", 
                                  command=self.open_logcat_window,
                                  width=20)
        logcat_button.pack(pady=2, fill="x")
    
    def setup_common_category(self, parent):
        """设置常用功能分类"""
        # 说明文字
        desc_label = ttk.Label(parent, text="日常使用的便民功能", 
                              font=("Arial", 9), foreground="gray")
        desc_label.pack(pady=(0, 10))
        
        # 遥控器
        remote_button = ttk.Button(parent, text="遥控器", 
                                  command=self.open_remote_window,
                                  width=20)
        remote_button.pack(pady=2, fill="x")
        
        # 本地播放
        playback_button = ttk.Button(parent, text="本地播放", 
                                    command=self.open_playback_window,
                                    width=20)
        playback_button.pack(pady=2, fill="x")
        
        # 截图功能
        screenshot_button = ttk.Button(parent, text="截图功能", 
                                      command=self.open_screenshot_window,
                                      width=20)
        screenshot_button.pack(pady=2, fill="x")
    
    # 以下是各个功能窗口的打开方法
    def open_sweep_window(self):
        """打开扫频测试窗口"""
        self.create_function_window("扫频测试", self.setup_sweep_tab)
    
    def open_mic_window(self):
        """打开麦克风测试窗口"""
        self.create_function_window("麦克风测试", self.setup_mic_tab)
    
    def open_radar_window(self):
        """打开雷达检查窗口"""
        self.create_function_window("雷达检查", self.setup_radar_tab)
    
    def open_speaker_window(self):
        """打开喇叭测试窗口"""
        self.create_function_window("喇叭测试", self.setup_speaker_tab)
    
    def open_multichannel_window(self):
        """打开多声道测试窗口"""
        self.create_function_window("多声道测试", self.setup_multichannel_tab)
    
    def open_loopback_window(self):
        """打开Loopback和Ref测试窗口"""
        self.create_function_window("Loopback和Ref测试", self.setup_loopback_tab)
    
    def open_hal_window(self):
        """打开HAL录音窗口"""
        self.create_function_window("HAL录音", self.setup_hal_recording_tab)
    
    def open_logcat_window(self):
        """打开Logcat日志窗口"""
        self.create_function_window("Logcat日志", self.setup_logcat_tab)
    
    def open_playback_window(self):
        """打开本地播放窗口"""
        self.create_function_window("本地播放", self.setup_local_playback_tab)
    
    def open_screenshot_window(self):
        """打开截图功能窗口"""
        self.create_function_window("截图功能", self.setup_screenshot_tab)
    
    def open_remote_window(self):
        """打开遥控器窗口"""
        self.create_function_window("遥控器", self.setup_remote_tab)
    
    def create_function_window(self, title, setup_func):
        """创建功能窗口的通用方法"""
        # 创建新窗口
        # 这里的 parent 是 Tk root，不是业务对象；新窗口直接挂在 root 上即可
        window = tk.Toplevel(getattr(self, "root", self.parent))
        window.title(title)
        window.geometry("900x700")

        # 鼠标进入窗口时自动获得焦点（配合“键盘挂载”体验更好）
        try:
            window.bind("<Enter>", lambda e: window.focus_set(), add=True)
        except Exception:
            pass
        
        # 设置窗口图标（如果存在）
        try:
            if os.path.exists("logo/AcouTest.ico"):
                window.iconbitmap("logo/AcouTest.ico")
        except:
            pass
        
        # 创建主框架
        main_frame = ttk.Frame(window, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # 说明：本项目采用 mixin（AudioTestTool 继承 UIComponents/DeviceOperations/TestOperations），
        # setup_func 绑定的 self 就是主应用实例，因此无需再创建“handler”桥接对象。
        setup_func(main_frame)
    
    def setup_loopback_tab(self, parent):
        """设置Loopback和Ref测试标签页"""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        
        # 删除标题说明，直接开始参数设置
        # title_label = ttk.Label(frame, text="播放音频并同时录制通道音频", font=("Arial", 11, "bold"))
        # title_label.pack(pady=(10, 0))
        # subtitle_label = ttk.Label(frame, text="用于验证音频回路和参考信号", font=("Arial", 9))
        # subtitle_label.pack(pady=(0, 10))
        
        # 默认音频按声道选择：7.1 / 2.1 / 2.0 使用 audio/channel/ 下对应文件；自定义不变
        self.audio_source_var = tk.StringVar(value="7.1")
        
        # 创建设置区域 - 减少上边距
        settings_frame = ttk.LabelFrame(frame, text="参数设置")
        settings_frame.pack(fill="x", padx=20, pady=(5, 10))
        
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
        
        # 播放设备ID（tinyplay -d）
        ttk.Label(grid_frame, text="播放设备ID(-d):").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.loopback_play_device_var = tk.StringVar(value="0")
        self.loopback_play_device_combo = ttk.Combobox(
            grid_frame,
            textvariable=self.loopback_play_device_var,
            values=["0", "1"],
            width=8,
            state="normal",
        )
        self.loopback_play_device_combo.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(
            grid_frame,
            text="读取alsaPORT播放设备",
            width=18,
            style="Small.TButton",
            command=self._refresh_loopback_playback_devices,
        ).grid(row=3, column=2, sticky="w", padx=5, pady=5)
        
        # 添加保存路径设置
        ttk.Label(grid_frame, text="保存路径:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
        self.loopback_save_path_var = tk.StringVar(value=get_output_dir(DIR_LOOPBACK))
        path_frame = ttk.Frame(grid_frame)
        path_frame.grid(row=4, column=1, columnspan=3, sticky="w", padx=5, pady=5)
        
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
        
        # 默认音频按声道选择：7.1 / 2.1 / 2.0（使用 audio/channel/ 下对应文件）
        source_frame = ttk.Frame(audio_frame)
        source_frame.pack(fill="x", padx=10, pady=5)
        ttk.Radiobutton(source_frame, text="7.1", variable=self.audio_source_var, value="7.1").pack(side="left", padx=(10, 16), pady=2)
        ttk.Radiobutton(source_frame, text="2.1", variable=self.audio_source_var, value="2.1").pack(side="left", padx=(0, 16), pady=2)
        ttk.Radiobutton(source_frame, text="2.0", variable=self.audio_source_var, value="2.0").pack(side="left", padx=(0, 16), pady=2)

        # 当前选中的默认音频路径显示 + 打开位置（随 7.1/2.1/2.0 切换更新）
        def _loopback_default_audio_path(preset):
            name = {"7.1": "Nums_7dot1_16_48000.wav", "2.1": "Nums_2dot1_16_48000.wav", "2.0": "Nums_2dot0_16_48000.wav"}.get(preset, "Nums_7dot1_16_48000.wav")
            return os.path.join(self._get_runtime_base_dir(), "audio", "channel", name)
        self._loopback_default_audio_path_fn = _loopback_default_audio_path
        self.default_loopback_audio_path_var = tk.StringVar(value=_loopback_default_audio_path("7.1"))

        def _on_loopback_source_change(*args):
            v = (self.audio_source_var.get() or "").strip()
            if v in ("7.1", "2.1", "2.0"):
                self.default_loopback_audio_path_var.set(_loopback_default_audio_path(v))
        self.audio_source_var.trace_add("write", _on_loopback_source_change)

        default_path_frame = ttk.Frame(audio_frame)
        default_path_frame.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(default_path_frame, text="默认音频路径:", font=("Arial", 9)).pack(side="left", padx=(10, 6))
        default_path_entry = ttk.Entry(default_path_frame, textvariable=self.default_loopback_audio_path_var)
        default_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        default_path_entry.config(state="readonly")

        def _open_loopback_default_folder():
            p = self.default_loopback_audio_path_var.get()
            if p:
                self.open_containing_folder(p)
        open_default_folder_btn = ttk.Button(
            default_path_frame,
            text="打开位置",
            style="Small.TButton",
            command=_open_loopback_default_folder,
            width=8,
        )
        open_default_folder_btn.pack(side="left", padx=(0, 10))
        
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

        self.view_loopback_waveform_button = ttk.Button(
            button_frame,
            text="查看录音波形",
            command=self.show_latest_loopback_waveform,
            width=15,
            state="disabled",
        )
        self.view_loopback_waveform_button.pack(side="left", padx=20)
        
        # 状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=10)
        
        self.loopback_status_var = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.loopback_status_var, font=("Arial", 10)).pack(anchor="center", pady=10)
    
    def _query_alsaport_playback_indexes(self, device_id=""):
        """读取 /proc/asound/pcm，返回可用于 tinyplay -d 的设备索引列表。"""
        # 先尝试提权，避免读取 /proc/asound/pcm 时出现 Permission denied
        try:
            if device_id:
                subprocess.run(f"adb -s {device_id} root", shell=True, capture_output=True, text=True, timeout=10)
            else:
                subprocess.run("adb root", shell=True, capture_output=True, text=True, timeout=10)
            time.sleep(0.6)
        except Exception:
            pass
        if device_id:
            cmd = f"adb -s {device_id} shell cat /proc/asound/pcm"
        else:
            cmd = "adb shell cat /proc/asound/pcm"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            return [], (result.stderr or result.stdout or "读取失败").strip()
        lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
        preferred = []
        fallback = []
        for ln in lines:
            m = re.match(r"^(\d+)-(\d+):\s*(.*)$", ln)
            if not m:
                continue
            card, pcm, desc = m.group(1), m.group(2), m.group(3)
            if "playback" not in desc.lower():
                continue
            item = (pcm, f"{pcm} (card{card}) {desc}")
            if "alsaport-pcm" in desc.lower():
                preferred.append(item)
            else:
                fallback.append(item)
        chosen = preferred or fallback
        values = []
        detail = []
        seen = set()
        for pcm, txt in chosen:
            if pcm in seen:
                continue
            seen.add(pcm)
            values.append(pcm)
            detail.append(txt)
        return values, ("\n".join(detail) if detail else "未找到可用 playback 设备")

    def _query_playback_card_device_pairs(self, device_id=""):
        """读取 /proc/asound/pcm，返回可用播放 (card, pcm) 列表（优先 alsaPORT-pcm）。"""
        if device_id:
            cmd = f"adb -s {device_id} shell cat /proc/asound/pcm"
        else:
            cmd = "adb shell cat /proc/asound/pcm"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            return []
        lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
        preferred = []
        fallback = []
        for ln in lines:
            m = re.match(r"^(\d+)-(\d+):\s*(.*)$", ln)
            if not m:
                continue
            card, pcm, desc = m.group(1), m.group(2), m.group(3)
            if "playback" not in desc.lower():
                continue
            item = (card, pcm, desc)
            if "alsaport-pcm" in desc.lower():
                preferred.append(item)
            else:
                fallback.append(item)
        ordered = preferred or fallback
        out = []
        seen = set()
        for card, pcm, _desc in ordered:
            key = f"{card}:{pcm}"
            if key in seen:
                continue
            seen.add(key)
            out.append((card, pcm))
        return out
    
    def _refresh_loopback_playback_devices(self):
        """读取当前设备的 alsaPORT 播放设备索引并更新 Loopback 播放设备下拉。"""
        if not self.check_device_selected():
            return
        device_id = (getattr(self, "device_var", None) and self.device_var.get() or "").strip()
        values, detail = self._query_alsaport_playback_indexes(device_id)
        if values:
            if hasattr(self, "loopback_play_device_combo") and self.loopback_play_device_combo.winfo_exists():
                self.loopback_play_device_combo["values"] = values
            cur = (getattr(self, "loopback_play_device_var", None) and self.loopback_play_device_var.get() or "").strip()
            if cur not in values:
                self.loopback_play_device_var.set(values[0])
            self.loopback_status_var.set(f"已读取播放设备: {', '.join(values)}")
        else:
            self.loopback_status_var.set("未读取到播放设备，保留当前手动输入")
        messagebox.showinfo("Loopback播放设备", detail)
    
    def setup_mic_tab(self, parent):
        """设置麦克风测试标签页"""
        print("开始设置麦克风测试标签页")
        
        # 确保所有必要的变量都已初始化
        if not hasattr(self, 'mic_count_var') or self.mic_count_var is None:
            self.mic_count_var = tk.StringVar(value="4")
            print("初始化 mic_count_var")
        
        if not hasattr(self, 'pcm_device_var') or self.pcm_device_var is None:
            self.pcm_device_var = tk.StringVar(value="0")
            print("初始化 pcm_device_var")
        
        if not hasattr(self, 'device_id_var') or self.device_id_var is None:
            self.device_id_var = tk.StringVar(value="3")
            print("初始化 device_id_var")
        
        if not hasattr(self, 'rate_var') or self.rate_var is None:
            self.rate_var = tk.StringVar(value="16000")
            print("初始化 rate_var")
        
        if not hasattr(self, 'mic_save_path_var') or self.mic_save_path_var is None:
            self.mic_save_path_var = tk.StringVar(value=get_output_dir(DIR_MIC_TEST))
            print("初始化 mic_save_path_var")
        
        if not hasattr(self, 'mic_info_var') or self.mic_info_var is None:
            self.mic_info_var = tk.StringVar(value="准备就绪")
            print("初始化 mic_info_var")
        
        # 创建主框架（使用 ttk：更现代、字体/间距可统一、按钮默认灰色）
        main_frame = ttk.Frame(parent, padding=(16, 16))
        main_frame.pack(fill="both", expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="麦克风测试", style="Header.TLabel")
        title_label.pack(pady=(0, 12))
        
        # 测试设置框架
        settings_frame = ttk.LabelFrame(main_frame, text="测试设置", padding=(12, 8))
        settings_frame.pack(fill="x", pady=(0, 14))
        
        # 创建设置项
        # 麦克风数量
        mic_count_frame = ttk.Frame(settings_frame)
        mic_count_frame.pack(fill="x", pady=6)
        
        ttk.Label(mic_count_frame, text="麦克风数量:").pack(side="left")
        # 允许：下拉选择 + 手动输入（不改变UI布局/配色）
        def _validate_positive_int_input(proposed_value: str) -> bool:
            """只允许输入数字（允许为空，便于用户删除后重新输入）"""
            return proposed_value == "" or proposed_value.isdigit()

        mic_count_combo = ttk.Combobox(
            mic_count_frame,
            textvariable=self.mic_count_var,
            values=["1", "2", "3", "4", "5", "6", "7", "8"],
            state="normal",  # 可输入
            width=10,
            validate="key",
            validatecommand=(parent.register(_validate_positive_int_input), "%P"),
        )
        mic_count_combo.pack(side="left", padx=(10, 0))
        
        # PCM设备
        pcm_frame = ttk.Frame(settings_frame)
        pcm_frame.pack(fill="x", pady=6)
        
        ttk.Label(pcm_frame, text="PCM设备(-D):").pack(side="left")
        pcm_entry = ttk.Entry(pcm_frame, textvariable=self.pcm_device_var, width=15)
        pcm_entry.pack(side="left", padx=(10, 0))
        
        # 设备ID
        device_id_frame = ttk.Frame(settings_frame)
        device_id_frame.pack(fill="x", pady=6)
        
        ttk.Label(device_id_frame, text="设备ID(-d):").pack(side="left")
        device_id_entry = ttk.Entry(device_id_frame, textvariable=self.device_id_var, width=15)
        device_id_entry.pack(side="left", padx=(10, 0))
        
        # 采样率
        rate_frame = ttk.Frame(settings_frame)
        rate_frame.pack(fill="x", pady=6)
        
        ttk.Label(rate_frame, text="采样率(-r):").pack(side="left")
        # 允许：下拉选择 + 手动输入（仅数字）
        def _validate_rate_input(proposed_value: str) -> bool:
            return proposed_value == "" or proposed_value.isdigit()

        rate_combo = ttk.Combobox(
            rate_frame,
            textvariable=self.rate_var,
            values=["8000", "16000", "44100", "48000"],
            state="normal",
            width=12,
            validate="key",
            validatecommand=(parent.register(_validate_rate_input), "%P"),
        )
        rate_combo.pack(side="left", padx=(10, 0))
        
        # 控制按钮框架
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(pady=12)
        
        # 开始测试按钮
        def on_start_click():
            print("开始按钮被点击")
            try:
                if hasattr(self, 'start_mic_test'):
                    print("找到 start_mic_test 方法，准备调用")
                    self.start_mic_test()
                else:
                    print("错误：找不到 start_mic_test 方法")
                    print(f"可用方法: {[method for method in dir(self) if 'mic' in method.lower()]}")
            except Exception as e:
                print(f"调用 start_mic_test 出错: {e}")
                import traceback
                traceback.print_exc()
        
        self.start_mic_button = ttk.Button(
            control_frame, 
            text="开始麦克风测试", 
            command=on_start_click,
            width=16
        )
        self.start_mic_button.pack(side="left", padx=(0, 10))
        
        # 停止测试按钮
        def on_stop_click():
            print("停止按钮被点击")
            try:
                if hasattr(self, 'stop_mic_test'):
                    print("找到 stop_mic_test 方法，准备调用")
                    self.stop_mic_test()
                else:
                    print("错误：找不到 stop_mic_test 方法")
            except Exception as e:
                print(f"调用 stop_mic_test 出错: {e}")
                import traceback
                traceback.print_exc()
        
        self.stop_mic_button = ttk.Button(
            control_frame, 
            text="停止录制", 
            command=on_stop_click,
            width=16,
            state="disabled"
        )
        self.stop_mic_button.pack(side="left", padx=10)
        
        self.view_mic_waveform_button = ttk.Button(
            control_frame,
            text="查看录音波形",
            command=self.show_latest_mic_waveform,
            width=16,
            state="disabled",
        )
        self.view_mic_waveform_button.pack(side="left", padx=10)
        
        # 状态显示框架
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(status_frame, text="状态", style="Header.TLabel").pack()
        
        # 状态信息显示
        info_label = ttk.Label(status_frame, textvariable=self.mic_info_var, style="Muted.TLabel")
        info_label.pack(pady=(6, 0))
        
        print("麦克风测试UI创建完成")
    
    def show_latest_mic_waveform(self):
        """查看最近一次麦克风录音的波形（若无缓存路径则从保存目录找最新 wav）。"""
        latest = self._resolve_latest_wav_path(
            latest_attr_name="latest_mic_recording_path",
            save_dir=(getattr(self, "mic_save_path_var", None) and self.mic_save_path_var.get() or "").strip(),
        )
        if not latest:
            messagebox.showwarning("提示", "暂无可查看的录音文件，请先完成一次麦克风录制。")
            return
        latest_path = latest
        self.latest_mic_recording_path = latest_path
        self.open_audio_waveform_viewer(latest_path, title="麦克风录音波形")

    def _resolve_latest_wav_path(self, latest_attr_name, save_dir):
        """优先用缓存路径，否则从保存目录中取最新 WAV。"""
        latest = getattr(self, latest_attr_name, "")
        if latest and os.path.isfile(latest):
            return latest
        if not save_dir or not os.path.isdir(save_dir):
            return ""
        wav_files = []
        for name in os.listdir(save_dir):
            if name.lower().endswith(".wav"):
                p = os.path.join(save_dir, name)
                try:
                    wav_files.append((os.path.getmtime(p), p))
                except Exception:
                    pass
        if not wav_files:
            return ""
        wav_files.sort(key=lambda x: x[0], reverse=True)
        return wav_files[0][1]

    def show_latest_loopback_waveform(self):
        """查看最近一次 Loopback/Ref 录音波形。"""
        save_dir = (getattr(self, "loopback_save_path_var", None) and self.loopback_save_path_var.get() or "").strip()
        latest = self._resolve_latest_wav_path("latest_loopback_recording_path", save_dir)
        if not latest:
            messagebox.showwarning("提示", "暂无可查看的 Loopback/Ref 录音文件，请先完成一次录制。")
            return
        self.latest_loopback_recording_path = latest
        self.open_audio_waveform_viewer(latest, title="Loopback/Ref 录音波形")

    def show_latest_sweep_waveform(self):
        """查看最近一次扫频录音波形。"""
        save_dir = (getattr(self, "sweep_save_path_var", None) and self.sweep_save_path_var.get() or "").strip()
        latest = self._resolve_latest_wav_path("latest_sweep_recording_path", save_dir)
        if not latest:
            messagebox.showwarning("提示", "暂无可查看的扫频录音文件，请先完成一次扫频录制。")
            return
        self.latest_sweep_recording_path = latest
        self.open_audio_waveform_viewer(latest, title="扫频录音波形")
    
    def _extract_wav_samples(self, raw_bytes, sample_width):
        """将 WAV 原始字节转为 int 样本数组（支持 8/16/24/32bit PCM）。"""
        if sample_width == 1:
            vals = array("B")
            vals.frombytes(raw_bytes)
            return [v - 128 for v in vals]
        if sample_width == 2:
            vals = array("h")
            vals.frombytes(raw_bytes)
            if sys.byteorder != "little":
                vals.byteswap()
            return list(vals)
        if sample_width == 4:
            vals = array("i")
            vals.frombytes(raw_bytes)
            if sys.byteorder != "little":
                vals.byteswap()
            return list(vals)
        if sample_width == 3:
            out = []
            mv = memoryview(raw_bytes)
            for i in range(0, len(raw_bytes), 3):
                b0 = mv[i]
                b1 = mv[i + 1]
                b2 = mv[i + 2]
                v = b0 | (b1 << 8) | (b2 << 16)
                if v & 0x800000:
                    v -= 0x1000000
                out.append(v)
            return out
        raise ValueError(f"暂不支持的采样位宽: {sample_width * 8}bit")
    
    def _build_wave_envelope(self, samples, channels, total_frames, points, full_scale):
        """把交错多通道样本压缩为按像素显示的 min/max 包络。"""
        points = max(200, min(points, total_frames))
        per_channel = [[(0.0, 0.0)] * points for _ in range(channels)]
        # 使用真实 full-scale 归一化（dBFS）：确保与 Adobe 的幅度标尺一致。
        # 例如 16bit -> 32767, 24bit -> 8388607。
        scale = float(max(1, int(full_scale)))
        for x in range(points):
            # 按总帧比例映射每个像素桶，避免整除分块导致尾段帧遗漏。
            # 这能保证 [0, total_frames) 全区间都被覆盖，时间轴与波形长度严格对应。
            start = int((x * total_frames) / float(points))
            end = int(((x + 1) * total_frames) / float(points))
            if end <= start:
                end = start + 1
            end = min(total_frames, end)
            if start >= end:
                continue
            for ch in range(channels):
                local_min = 1.0
                local_max = -1.0
                idx = start * channels + ch
                for _ in range(start, end):
                    v = samples[idx] / scale
                    if v < local_min:
                        local_min = v
                    if v > local_max:
                        local_max = v
                    idx += channels
                per_channel[ch][x] = (local_min, local_max)
        return per_channel, points
    
    def _guess_wave_params(self, file_path):
        """从文件名/界面参数推断通道数、采样率、位宽（用于损坏头修复）。"""
        channels = 4
        rate = 16000
        bits = 16
        try:
            m = re.search(r"_(\d+)ch_", os.path.basename(file_path))
            if m:
                channels = max(1, int(m.group(1)))
            elif hasattr(self, "mic_count_var") and self.mic_count_var.get():
                channels = max(1, int(self.mic_count_var.get()))
        except Exception:
            pass
        try:
            if hasattr(self, "rate_var") and self.rate_var.get():
                rate = max(1, int(self.rate_var.get()))
        except Exception:
            pass
        return channels, rate, bits
    
    def _repair_wave_for_view(self, file_path):
        """
        修复无法直接解析的录音文件用于波形查看：
        - 若非 RIFF，按“原始 PCM”补 WAV 头；
        - 若 RIFF 头损坏，丢弃前 44 字节后按 PCM 重打包。
        返回修复后的临时 wav 路径。
        """
        channels, rate, bits = self._guess_wave_params(file_path)
        sample_width = max(1, bits // 8)
        with open(file_path, "rb") as f:
            raw = f.read()
        if not raw:
            raise ValueError("文件为空，无法解析")
        if len(raw) >= 4 and raw[:4] == b"RIFF":
            payload = raw[44:] if len(raw) > 44 else b""
        else:
            payload = raw
        frame_bytes = channels * sample_width
        usable = (len(payload) // frame_bytes) * frame_bytes
        if usable <= 0:
            raise ValueError("音频数据长度不足，无法按当前通道/位宽修复")
        payload = payload[:usable]
        fixed_name = f"acoutest_wavefix_{int(time.time()*1000)}_{os.path.basename(file_path)}"
        fixed_path = os.path.join(tempfile.gettempdir(), fixed_name)
        with wave.open(fixed_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(payload)
        return fixed_path
    
    def open_audio_waveform_viewer(self, file_path, title="音频波形", on_selection_changed=None):
        """弹出窗口显示 WAV 波形（多通道分轨显示）。"""
        if not os.path.isfile(file_path):
            messagebox.showerror("错误", f"文件不存在：\n{file_path}")
            return
        display_path = file_path
        repaired_note = ""
        try:
            with wave.open(display_path, "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                total_frames = wf.getnframes()
                raw = wf.readframes(total_frames)
        except Exception:
            try:
                display_path = self._repair_wave_for_view(file_path)
                repaired_note = "（原文件头异常，已自动修复后显示）"
                with wave.open(display_path, "rb") as wf:
                    channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    sample_rate = wf.getframerate()
                    total_frames = wf.getnframes()
                    raw = wf.readframes(total_frames)
            except Exception as e:
                messagebox.showerror("错误", f"解析音频波形失败：\n{e}")
                return
        try:
            if total_frames <= 0:
                raise ValueError("音频帧数为 0")
            samples = self._extract_wav_samples(raw, sample_width)
            bits = sample_width * 8
            full_scale_map = {8: 127, 16: 32767, 24: 8388607, 32: 2147483647}
            full_scale = full_scale_map.get(bits, (2 ** (bits - 1)) - 1)
            peak_abs = max((abs(v) for v in samples), default=0)
            if peak_abs <= 0:
                peak_dbfs_text = "-inf"
            else:
                peak_dbfs_text = f"{20.0 * math.log10(peak_abs / float(max(1, full_scale))):.1f} dBFS"
            # 提高基础包络分辨率，支持更细粒度缩放观察
            target_points = min(50000, max(4000, total_frames // 2))
            env, points = self._build_wave_envelope(samples, channels, total_frames, points=target_points, full_scale=full_scale)
        except Exception as e:
            messagebox.showerror("错误", f"解析音频波形失败：\n{e}")
            return
        # 播放兼容层：pygame 对 >2 声道 WAV 兼容较差，自动下混为 2 声道用于播放。
        # 注意：仅影响“播放源”，波形显示仍使用原始多通道数据。
        playback_channels = channels
        playback_samples = samples
        playback_base_path = display_path
        playback_note = ""
        if channels > 2:
            downmixed = []
            for fidx in range(total_frames):
                base = fidx * channels
                left = samples[base]
                right = samples[base + 1] if channels > 1 else left
                downmixed.append(left)
                downmixed.append(right)
            playback_channels = 2
            playback_samples = downmixed
            playback_base_path = ""  # 下混后需生成临时播放文件
            playback_note = f"（播放兼容：原始 {channels} 声道已下混为 2 声道，波形显示保持原始通道）"
        win = tk.Toplevel(getattr(self, "root", None) or getattr(self, "parent", None) or self)
        win.title(f"{title} - {os.path.basename(file_path)}")
        win.geometry("1040x620")
        # 与主窗口一致的图标（AcouTest logo）
        try:
            base_dir = self._get_runtime_base_dir()
            png_paths = [
                os.path.join(base_dir, "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(getattr(sys, "_MEIPASS", ""), "logo", "AcouTest.png") if getattr(sys, "frozen", False) else None,
            ]
            for path in png_paths:
                if path and os.path.exists(path):
                    try:
                        icon_img = tk.PhotoImage(file=path)
                        win.iconphoto(True, icon_img)
                        win._icon_image = icon_img
                        break
                    except Exception:
                        pass
            if platform.system() == "Windows":
                ico_paths = [
                    os.path.join(base_dir, "logo", "AcouTest.ico"),
                    os.path.join("logo", "AcouTest.ico"),
                ]
                for ico_path in ico_paths:
                    if os.path.exists(ico_path):
                        try:
                            win.iconbitmap(ico_path)
                            break
                        except Exception:
                            pass
        except Exception:
            pass
        info = (
            f"文件: {file_path}\n"
            f"采样率: {sample_rate} Hz    通道数: {channels}    位宽: {sample_width * 8} bit    "
            f"时长: {total_frames / float(sample_rate):.2f} s    峰值: {peak_dbfs_text}"
        )
        if repaired_note:
            info += f"\n{repaired_note}"
        if playback_note:
            info += f"\n{playback_note}"
        ttk.Label(win, text=info, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(8, 4))
        
        hint_var = tk.StringVar(value="操作：鼠标左键拖动选择区间；单击设光标；右键清除选区；Ctrl + 滚轮缩放时间轴")
        ttk.Label(win, textvariable=hint_var, foreground="#666").pack(anchor="w", padx=10, pady=(0, 4))
        
        # 操作条：缩放 / dB增益 / 播放控制（类似 Adobe 的常用操作）
        toolbar = ttk.Frame(win)
        toolbar.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(toolbar, text="振幅缩放:", font=("Arial", 9)).pack(side="left")
        btn_zoom_out = ttk.Button(toolbar, text="-", width=3)
        btn_zoom_out.pack(side="left", padx=(4, 2))
        btn_zoom_in = ttk.Button(toolbar, text="+", width=3)
        btn_zoom_in.pack(side="left", padx=2)
        btn_zoom_reset = ttk.Button(toolbar, text="1x", width=6)
        btn_zoom_reset.pack(side="left", padx=(2, 10))
        ttk.Label(toolbar, text="增益(dB):", font=("Arial", 9)).pack(side="left")
        btn_gain_down = ttk.Button(toolbar, text="-", width=3)
        btn_gain_down.pack(side="left", padx=(4, 2))
        btn_gain_up = ttk.Button(toolbar, text="+", width=3)
        btn_gain_up.pack(side="left", padx=2)
        btn_gain_reset = ttk.Button(toolbar, text="0dB", width=6)
        btn_gain_reset.pack(side="left", padx=(2, 10))
        wave_play_btn = ttk.Button(toolbar, text="播放", width=6)
        wave_play_btn.pack(side="left", padx=(8, 2))
        wave_pause_btn = ttk.Button(toolbar, text="暂停", width=6)
        wave_pause_btn.pack(side="left", padx=2)
        wave_stop_btn = ttk.Button(toolbar, text="停止", width=6)
        wave_stop_btn.pack(side="left", padx=2)
        
        canvas_wrap = ttk.Frame(win)
        canvas_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        wave_row = ttk.Frame(canvas_wrap)
        wave_row.pack(side="top", fill="both", expand=True)
        hscroll = ttk.Scrollbar(canvas_wrap, orient="horizontal")
        hscroll.pack(side="bottom", fill="x")
        canvas = tk.Canvas(wave_row, bg="#101010", height=520, highlightthickness=0, xscrollcommand=hscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        db_canvas = tk.Canvas(wave_row, bg="#0f1510", width=74, height=520, highlightthickness=1, highlightbackground="#2a2a2a")
        db_canvas.pack(side="right", fill="y")
        
        state = {
            "zoom": None,
            "total_width": 0,
            "render_job": None,
            "wave_tag": None,
            "db_tag": None,
            "gain_db": 0.0,
            # 振幅按钮的离散档位（Adobe 风格）：每点一次按固定 dB 步进
            "amp_db": 0.0,
            "amp_scale": 1.0,
            "is_playing": False,
            "is_paused": False,
            "cursor_time": 0.0,
            "playback_time": 0.0,
            "play_start_offset": 0.0,
            "play_end_time": 0.0,
            "progress_job": None,
            "playback_latency_s": 0.0,
            "clock_anchor_time": 0.0,
            "clock_anchor_perf": 0.0,
            "first_valid_pos_seen": False,
            "start_grace_until_perf": 0.0,
            "click_dragged": False,
            "is_dragging": False,
            "last_drag_render_perf": 0.0,
            "click_start_x": 0,
            "select_anchor_t": 0.0,
            "sel_start_t": None,
            "sel_end_t": None,
            "selection_active": False,
            "resume_from_cursor": False,
            "left_px": 10,
            "draw_points": 1,
            "tracks_top": 34,
            "tracks_bottom": 540,
            "gain_play_path": "",
            "gain_play_db": None,
            "gain_play_seg": None,
            "drag_overlay_tag": "wave_drag_overlay",
            "cursor_line_id": None,
            "progress_line_id": None,
        }
        total_duration = total_frames / float(sample_rate)

        def _set_play_clock(anchor_time):
            """用高精度时钟建立播放时间锚点（秒）。"""
            state["clock_anchor_time"] = max(0.0, float(anchor_time))
            state["clock_anchor_perf"] = time.perf_counter()

        def _get_clock_time():
            anchor = float(state.get("clock_anchor_time", 0.0))
            anchor_perf = float(state.get("clock_anchor_perf", 0.0))
            if anchor_perf <= 0.0:
                return anchor
            return anchor + max(0.0, time.perf_counter() - anchor_perf)
        
        def format_hms(seconds):
            """格式化时间显示：h:mm:ss.mmm / mm:ss.mmm / s.mmm。"""
            seconds = max(0.0, float(seconds))
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = seconds % 60.0
            if h > 0:
                return f"{h}:{m:02d}:{s:06.3f}"
            if m > 0:
                return f"{m:02d}:{s:06.3f}"
            return f"{s:.3f}s"
        
        def choose_time_step(visible_sec):
            """根据可见时长选取合适的时间网格步长。"""
            candidates = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60]
            target_lines = 10.0
            target = max(visible_sec / target_lines, 0.001)
            for step in candidates:
                if step >= target:
                    return step
            return 120.0

        def _x_to_time(x_canvas):
            left_px = state.get("left_px", 10)
            draw_pts = max(1, int(state.get("draw_points", 1)))
            if x_canvas <= left_px:
                return 0.0
            t = ((x_canvas - left_px) / float(draw_pts)) * total_duration
            return max(0.0, min(total_duration, t))

        def _time_to_x(t):
            left_px = state.get("left_px", 10)
            draw_pts = max(1, int(state.get("draw_points", 1)))
            tt = max(0.0, min(total_duration, float(t)))
            return left_px + int((tt / max(1e-9, total_duration)) * draw_pts)

        def _emit_selection_change():
            cb = on_selection_changed
            if not callable(cb):
                return
            try:
                sel_s = state.get("sel_start_t", None)
                sel_e = state.get("sel_end_t", None)
                if state.get("selection_active", False) and sel_s is not None and sel_e is not None and abs(sel_e - sel_s) >= 0.01:
                    cb(min(sel_s, sel_e), max(sel_s, sel_e))
                else:
                    cb(None, None)
            except Exception:
                pass
        
        def render():
            state["render_job"] = None
            win.update_idletasks()
            view_w = max(600, canvas.winfo_width() - 20)
            height = max(300, canvas.winfo_height() - 20)
            left = 10
            top = 10
            ruler_h = 24
            tracks_top = top + ruler_h
            track_h = max(60, (height - ruler_h) // channels)
            if state["zoom"] is None:
                fit_zoom = view_w / float(max(1, points))
                state["zoom"] = max(0.01, min(64.0, fit_zoom))
            draw_points = max(view_w, int(points * state["zoom"]))
            # 关键修复：当窗口放大导致 draw_points > points*zoom 时，
            # 采样映射必须使用“实际渲染缩放比”，否则会把有效波形挤到左侧并造成时轴错位。
            effective_zoom = draw_points / float(max(1, points))
            state["total_width"] = draw_points
            state["left_px"] = left
            state["draw_points"] = draw_points
            state["effective_zoom"] = effective_zoom
            state["tracks_top"] = tracks_top
            state["tracks_bottom"] = tracks_top + track_h * channels
            xview = canvas.xview()
            if not xview:
                xview = (0.0, min(1.0, view_w / float(max(1, draw_points))))
            vis_l = int(max(0.0, min(1.0, xview[0])) * draw_points)
            vis_r = int(max(0.0, min(1.0, xview[1])) * draw_points)
            if vis_r <= vis_l:
                vis_l, vis_r = 0, min(draw_points, view_w)
            # 拖拽选区时降低渲染范围，提升交互流畅度；松手后恢复完整边界
            margin = 60 if state.get("is_dragging", False) else 160
            draw_l = max(0, vis_l - margin)
            draw_r = min(draw_points, vis_r + margin)
            
            # 双图层重绘：先画新层，再删旧层，避免 Ctrl+滚轮时闪黑
            new_wave_tag = f"wave_{time.time_ns()}"
            new_db_tag = f"db_{time.time_ns()}"
            wc = {
                "rect": lambda *a, **k: canvas.create_rectangle(*a, tags=(new_wave_tag,), **k),
                "line": lambda *a, **k: canvas.create_line(*a, tags=(new_wave_tag,), **k),
                "text": lambda *a, **k: canvas.create_text(*a, tags=(new_wave_tag,), **k),
            }
            dc = {
                "rect": lambda *a, **k: db_canvas.create_rectangle(*a, tags=(new_db_tag,), **k),
                "line": lambda *a, **k: db_canvas.create_line(*a, tags=(new_db_tag,), **k),
                "text": lambda *a, **k: db_canvas.create_text(*a, tags=(new_db_tag,), **k),
            }
            
            wc["rect"](0, 0, left + draw_points + 20, tracks_top + track_h * channels + 10, outline="", fill="#101010")
            wc["rect"](left, top, left + draw_points, top + ruler_h, outline="#303030", fill="#171717")

            # 选区高亮（类似 Adobe 的时间段选择）
            sel_s = state.get("sel_start_t", None)
            sel_e = state.get("sel_end_t", None)
            if sel_s is not None and sel_e is not None and abs(sel_e - sel_s) > 1e-6:
                sx = _time_to_x(min(sel_s, sel_e))
                ex = _time_to_x(max(sel_s, sel_e))
                if ex > sx:
                    wc["rect"](sx, top, ex, tracks_top + track_h * channels, outline="", fill="#d8d8d8", stipple="gray25")
                    wc["line"](sx, top, sx, tracks_top + track_h * channels, fill="#b04040")
                    wc["line"](ex, top, ex, tracks_top + track_h * channels, fill="#b04040")
            
            # 时间轴网格（HMS）
            vis_start_t = (vis_l / float(max(1, draw_points))) * total_duration
            vis_end_t = (vis_r / float(max(1, draw_points))) * total_duration
            vis_sec = max(0.001, vis_end_t - vis_start_t)
            time_step = choose_time_step(vis_sec)
            first_tick = (int(vis_start_t / time_step) * time_step)
            if first_tick < vis_start_t:
                first_tick += time_step
            t = first_tick
            while t <= vis_end_t + 1e-9:
                x = left + int((t / max(1e-9, total_duration)) * draw_points)
                wc["line"](x, top + ruler_h, x, tracks_top + track_h * channels, fill="#1f2f1f")
                wc["line"](x, top + ruler_h - 7, x, top + ruler_h, fill="#8a8a8a")
                wc["text"](x + 2, top + 2, anchor="nw", fill="#bfbfbf", text=format_hms(t), font=("Consolas", 8))
                t += time_step
            wc["text"](left + 4, top + ruler_h - 2, anchor="sw", fill="#8a8a8a", text="HMS", font=("Consolas", 8))
            
            # dBFS 背景刻度固定：无论振幅缩放/增益如何，背景网格和右侧标尺都保持不变
            db_levels = [-3, -6, -9, -12, -15]
            min_label_gap = 10
            for ch in range(channels):
                y0 = tracks_top + ch * track_h
                y1 = y0 + track_h - 8
                center = (y0 + y1) / 2.0
                base_amp = max(8.0, (y1 - y0) * 0.45)
                gain_scale = 10 ** (state["gain_db"] / 20.0)
                wave_amp = base_amp * gain_scale * state["amp_scale"]
                wc["rect"](left + draw_l, y0, left + draw_r, y1, outline="#303030")
                wc["line"](left + draw_l, center, left + draw_r, center, fill="#2a2a2a")
                wc["text"](left + 4, y0 + 10, anchor="w", fill="#A0A0A0", text=f"CH{ch + 1}", font=("Consolas", 9))
                
                # dB 网格线（固定背景）
                for db in db_levels:
                    ratio = 10 ** (db / 20.0)
                    y_up = center - base_amp * ratio
                    y_dn = center + base_amp * ratio
                    wc["line"](left + draw_l, y_up, left + draw_r, y_up, fill="#244224")
                    wc["line"](left + draw_l, y_dn, left + draw_r, y_dn, fill="#244224")
                wc["line"](left + draw_l, center, left + draw_r, center, fill="#2f6f2f")
                
                color = "#3ECF8E" if ch % 2 == 0 else "#56B6F7"
                for i in range(draw_l, draw_r):
                    # 关键修复：缩小时按区间取包络，避免“只取单点”导致波形发黑/看不见
                    zoom_for_sampling = max(1e-9, float(state.get("effective_zoom", state["zoom"])))
                    src_start = int(i / zoom_for_sampling)
                    src_end = int((i + 1) / zoom_for_sampling)
                    if src_end <= src_start:
                        src_end = src_start + 1
                    src_start = max(0, min(points - 1, src_start))
                    src_end = max(src_start + 1, min(points, src_end))
                    if src_end - src_start == 1:
                        vmin, vmax = env[ch][src_start]
                    else:
                        vmin = 1.0
                        vmax = -1.0
                        seg = env[ch]
                        for k in range(src_start, src_end):
                            a, b = seg[k]
                            if a < vmin:
                                vmin = a
                            if b > vmax:
                                vmax = b
                    x = left + i
                    y_min = center - vmax * wave_amp
                    y_max = center - vmin * wave_amp
                    # 每个通道独立裁剪：振幅再大也不允许越过本通道边界
                    y_min = max(y0 + 1, min(y1 - 1, y_min))
                    y_max = max(y0 + 1, min(y1 - 1, y_max))
                    wc["line"](x, y_min, x, y_max, fill=color)
            
            canvas.config(scrollregion=(0, 0, left + draw_points + 20, tracks_top + track_h * channels + 10))
            
            # 固定右侧 dB 面板（不随横向滚动变化）
            db_w = max(60, db_canvas.winfo_width())
            dc["rect"](0, 0, db_w, tracks_top + track_h * channels + 10, outline="", fill="#0f1510")
            dc["rect"](0, top, db_w, top + ruler_h, outline="#303030", fill="#171717")
            dc["text"](db_w // 2, top + ruler_h - 2, anchor="s", fill="#6ea56e", text="dBFS", font=("Consolas", 8))
            for ch in range(channels):
                y0 = tracks_top + ch * track_h
                y1 = y0 + track_h - 8
                center = (y0 + y1) / 2.0
                base_amp = max(8.0, (y1 - y0) * 0.45)
                dc["rect"](0, y0, db_w, y1, outline="#2a2a2a")
                last_label_y = None
                # 右侧 dB 文本随振幅缩放/增益联动：
                # 与 Adobe 观感一致：
                # - 振幅放大(amp_scale 增大) -> 标签应变得更“负”
                # - 振幅缩小(amp_scale 减小) -> 标签应变得更“正”
                # 因此使用负号偏移；增益正值也按同方向处理（更“负”）
                db_offset = -(float(state.get("amp_db", 0.0)) + float(state.get("gain_db", 0.0)))
                for db in db_levels:
                    ratio = 10 ** (db / 20.0)
                    y_up = center - base_amp * ratio
                    y_dn = center + base_amp * ratio
                    dc["line"](0, y_up, db_w, y_up, fill="#244224")
                    dc["line"](0, y_dn, db_w, y_dn, fill="#244224")
                    if last_label_y is None or abs(y_up - last_label_y) >= min_label_gap:
                        # 不再强行截断到 0 dB，避免大振幅时右侧刻度全部显示为 0
                        shown_db = db + db_offset
                        db_text = f"{shown_db:+.0f}"
                        dc["text"](db_w - 4, y_up, anchor="e", fill="#8fcf8f", text=db_text, font=("Consolas", 8))
                        dc["text"](db_w - 4, y_dn, anchor="e", fill="#8fcf8f", text=db_text, font=("Consolas", 8))
                        last_label_y = y_up
                dc["text"](db_w - 4, center, anchor="e", fill="#8fcf8f", text="-inf", font=("Consolas", 8))
                dc["text"](4, y0 + 2, anchor="w", fill="#6ea56e", text=f"CH{ch+1}", font=("Consolas", 8))
            
            # 新层画完再替换旧层，避免闪烁
            old_wave = state.get("wave_tag")
            old_db = state.get("db_tag")
            if old_wave:
                canvas.delete(old_wave)
            if old_db:
                db_canvas.delete(old_db)
            state["wave_tag"] = new_wave_tag
            state["db_tag"] = new_db_tag
            _update_playhead_overlay()
            hint_var.set(
                f"操作：左键拖动选区/单击设光标/右键清选区；Ctrl+滚轮缩放（当前 {state['zoom']:.2f}x）"
                f"；振幅 {state['amp_scale']:.2f}x({state['amp_db']:+.1f}dB)；增益 {state['gain_db']:+.1f} dB"
            )
        
        def request_render(delay=1):
            if state["render_job"] is not None:
                try:
                    win.after_cancel(state["render_job"])
                except Exception:
                    pass
            state["render_job"] = win.after(delay, render)

        def _clear_drag_overlay():
            try:
                canvas.delete(state.get("drag_overlay_tag", "wave_drag_overlay"))
            except Exception:
                pass

        def _draw_drag_overlay():
            """拖拽中仅更新轻量选区层，避免整图重绘造成卡顿。"""
            _clear_drag_overlay()
            if not (state.get("is_dragging", False) or state.get("selection_active", False)):
                return
            sel_s = state.get("sel_start_t", None)
            sel_e = state.get("sel_end_t", None)
            if sel_s is None or sel_e is None:
                return
            sx = _time_to_x(min(sel_s, sel_e))
            ex = _time_to_x(max(sel_s, sel_e))
            if ex <= sx:
                return
            top = 10
            tracks_top = int(state.get("tracks_top", 34))
            tracks_bottom = int(state.get("tracks_bottom", tracks_top + 1))
            canvas.create_rectangle(
                sx, top, ex, tracks_bottom,
                outline="", fill="#d8d8d8", stipple="gray25",
                tags=(state.get("drag_overlay_tag", "wave_drag_overlay"),),
            )
            canvas.create_line(
                sx, top, sx, tracks_bottom,
                fill="#b04040",
                tags=(state.get("drag_overlay_tag", "wave_drag_overlay"),),
            )
            canvas.create_line(
                ex, top, ex, tracks_bottom,
                fill="#b04040",
                tags=(state.get("drag_overlay_tag", "wave_drag_overlay"),),
            )

        def _update_playhead_overlay():
            """轻量更新光标线/播放线，避免整图重绘造成卡顿与不同步。"""
            if total_duration <= 0:
                return
            left_px = int(state.get("left_px", 10))
            draw_pts = max(1, int(state.get("draw_points", 1)))
            top = 10
            bottom = int(state.get("tracks_bottom", state.get("tracks_top", 34) + 1))
            cx = left_px + int((max(0.0, min(total_duration, state.get("cursor_time", 0.0))) / total_duration) * draw_pts)
            px = left_px + int((max(0.0, min(total_duration, state.get("playback_time", 0.0))) / total_duration) * draw_pts)
            try:
                if not state.get("cursor_line_id"):
                    state["cursor_line_id"] = canvas.create_line(cx, top, cx, bottom, fill="#f0c040")
                else:
                    canvas.coords(state["cursor_line_id"], cx, top, cx, bottom)
                if not state.get("progress_line_id"):
                    state["progress_line_id"] = canvas.create_line(px, top, px, bottom, fill="#ff4444")
                else:
                    canvas.coords(state["progress_line_id"], px, top, px, bottom)
                canvas.tag_raise(state["cursor_line_id"])
                canvas.tag_raise(state["progress_line_id"])
                # 播放线应在选区遮罩之上，避免被遮住看起来“卡住”
                if state.get("drag_overlay_tag"):
                    canvas.tag_raise(state.get("drag_overlay_tag"))
                    canvas.tag_raise(state["progress_line_id"])
            except Exception:
                pass
        
        def on_drag_start(event):
            state["click_dragged"] = False
            state["is_dragging"] = True
            state["click_start_x"] = event.x
            anchor_t = _x_to_time(canvas.canvasx(event.x))
            state["select_anchor_t"] = anchor_t
            state["sel_start_t"] = anchor_t
            state["sel_end_t"] = anchor_t
            state["selection_active"] = True
            _draw_drag_overlay()
        
        def on_drag_move(event):
            if abs(event.x - state.get("click_start_x", event.x)) > 4:
                state["click_dragged"] = True
            cur_t = _x_to_time(canvas.canvasx(event.x))
            state["sel_start_t"] = min(state.get("select_anchor_t", cur_t), cur_t)
            state["sel_end_t"] = max(state.get("select_anchor_t", cur_t), cur_t)
            # 拖拽中仅更新轻量选区层，避免每个鼠标事件都触发高成本重绘
            now = time.perf_counter()
            last = float(state.get("last_drag_render_perf", 0.0) or 0.0)
            if (now - last) >= 0.03:  # 约 33 FPS
                state["last_drag_render_perf"] = now
                _draw_drag_overlay()
        
        def on_click_release(event):
            state["is_dragging"] = False
            # 点击（非拖动）时设置播放起点
            if state.get("click_dragged", False):
                sel_s = state.get("sel_start_t", None)
                sel_e = state.get("sel_end_t", None)
                if sel_s is not None and sel_e is not None and (sel_e - sel_s) >= 0.01:
                    state["selection_active"] = True
                    state["cursor_time"] = sel_s
                    if not state.get("is_playing", False):
                        state["playback_time"] = sel_s
                    _draw_drag_overlay()
                    _update_playhead_overlay()
                    _emit_selection_change()
                else:
                    state["sel_start_t"] = None
                    state["sel_end_t"] = None
                    state["selection_active"] = False
                    _clear_drag_overlay()
                    _emit_selection_change()
                request_render(0)
                return
            t = _x_to_time(canvas.canvasx(event.x))
            # 单击：清除选区，只保留光标
            _clear_drag_overlay()
            state["sel_start_t"] = None
            state["sel_end_t"] = None
            state["selection_active"] = False
            state["cursor_time"] = t
            if not state.get("is_playing", False):
                state["playback_time"] = t
            _update_playhead_overlay()
            _emit_selection_change()
            request_render(1)

        def clear_selection(_event=None):
            state["is_dragging"] = False
            _clear_drag_overlay()
            state["sel_start_t"] = None
            state["sel_end_t"] = None
            state["selection_active"] = False
            _update_playhead_overlay()
            _emit_selection_change()
            request_render(1)
        
        def on_ctrl_wheel(event=None, direction=None):
            if direction is None:
                if event is None:
                    return
                direction = 1 if getattr(event, "delta", 0) > 0 else -1
            old_zoom = state["zoom"]
            new_zoom = old_zoom * (1.2 if direction > 0 else (1 / 1.2))
            new_zoom = max(0.01, min(64.0, new_zoom))
            if abs(new_zoom - old_zoom) < 1e-6:
                return
            xview = canvas.xview()
            center = (xview[0] + xview[1]) / 2.0 if xview else 0.0
            state["zoom"] = new_zoom
            span = max(1e-6, (xview[1] - xview[0]) if xview else 1.0)
            span = min(1.0, max(1e-6, span * (old_zoom / new_zoom)))
            new_left = max(0.0, min(1.0 - span, center - span / 2.0))
            canvas.xview_moveto(new_left)
            request_render(8)
        
        def zoom_step(direction):
            # 工具条“缩放”按用户期望改为振幅缩放；时间缩放保留 Ctrl+滚轮
            # 每次固定 6 dB 步进：右侧 dB 全体平移更符合你给出的实际规律
            step_db = 6.0
            state["amp_db"] = max(-36.0, min(72.0, state.get("amp_db", 0.0) + (step_db if direction > 0 else -step_db)))
            state["amp_scale"] = 10 ** (state["amp_db"] / 20.0)
            request_render(1)
        
        def zoom_reset():
            state["amp_db"] = 0.0
            state["amp_scale"] = 1.0
            request_render(1)
        
        def gain_step(direction):
            state["gain_db"] = max(-24.0, min(24.0, state["gain_db"] + (1.5 * direction)))
            request_render(1)
            _restart_playback_with_current_gain()
        
        def gain_reset():
            state["gain_db"] = 0.0
            request_render(1)
            _restart_playback_with_current_gain()
        
        def _get_pg():
            getter = getattr(self, "_get_pygame", None)
            if callable(getter):
                try:
                    return getter()
                except Exception:
                    return None
            return None
        
        def _samples_to_bytes(vals, sw):
            """将整数样本写回 PCM 字节流（支持 8/16/24/32bit）。"""
            bits_local = sw * 8
            max_v = (1 << (bits_local - 1)) - 1
            min_v = -(1 << (bits_local - 1))
            if sw == 1:
                out = bytearray()
                for v in vals:
                    vv = max(min_v, min(max_v, int(v)))
                    out.append(max(0, min(255, vv + 128)))
                return bytes(out)
            if sw == 2:
                arr = array("h", (max(min_v, min(max_v, int(v))) for v in vals))
                if sys.byteorder != "little":
                    arr.byteswap()
                return arr.tobytes()
            if sw == 4:
                arr = array("i", (max(min_v, min(max_v, int(v))) for v in vals))
                if sys.byteorder != "little":
                    arr.byteswap()
                return arr.tobytes()
            if sw == 3:
                out = bytearray()
                for v in vals:
                    vv = max(min_v, min(max_v, int(v)))
                    if vv < 0:
                        vv += 1 << 24
                    out.extend((vv & 0xFF, (vv >> 8) & 0xFF, (vv >> 16) & 0xFF))
                return bytes(out)
            raise ValueError(f"不支持的样本位宽: {sw}")
        
        def _build_gain_playback_file(gdb):
            """按当前增益与播放区间生成可播放文件。"""
            rounded = round(gdb, 2)
            seg_start = int(max(0, min(total_frames, round(float(state.get("play_seg_start_frame", 0) or 0)))))
            seg_end = int(max(seg_start + 1, min(total_frames, round(float(state.get("play_seg_end_frame", total_frames) or total_frames)))))
            seg_key = (seg_start, seg_end, playback_channels)
            # 只有“无需下混 + 无增益 + 全段播放”时可直接用原文件
            if (
                abs(gdb) < 0.05 and
                playback_base_path and
                seg_start <= 0 and
                seg_end >= total_frames and
                os.path.exists(playback_base_path)
            ):
                return playback_base_path
            if (
                state.get("gain_play_path")
                and state.get("gain_play_db") == rounded
                and state.get("gain_play_seg") == seg_key
                and os.path.exists(state["gain_play_path"])
            ):
                return state["gain_play_path"]
            gain_factor = 10 ** (gdb / 20.0)
            bits_local = sample_width * 8
            max_v = (1 << (bits_local - 1)) - 1
            min_v = -(1 << (bits_local - 1))
            boosted = []
            ch = max(1, int(playback_channels))
            for fi in range(seg_start, seg_end):
                base = fi * ch
                for ci in range(ch):
                    v = playback_samples[base + ci]
                    vv = int(round(v * gain_factor))
                    if vv > max_v:
                        vv = max_v
                    elif vv < min_v:
                        vv = min_v
                    boosted.append(vv)
            pcm_bytes = _samples_to_bytes(boosted, sample_width)
            if state.get("gain_play_path"):
                try:
                    os.remove(state["gain_play_path"])
                except Exception:
                    pass
            temp_name = f"acoutest_gainplay_{int(time.time()*1000)}.wav"
            temp_path = os.path.join(tempfile.gettempdir(), temp_name)
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(playback_channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
            state["gain_play_path"] = temp_path
            state["gain_play_db"] = rounded
            state["gain_play_seg"] = seg_key
            return temp_path
        
        def play_audio():
            pg = _get_pg()
            if not pg:
                messagebox.showwarning("播放不可用", "当前环境未启用音频播放依赖（pygame）。")
                return
            try:
                if state["is_paused"]:
                    pg.mixer.music.unpause()
                    state["is_paused"] = False
                    state["is_playing"] = True
                    _set_play_clock(state.get("playback_time", 0.0))
                    _schedule_progress()
                    return
                sel_s = state.get("sel_start_t", None)
                sel_e = state.get("sel_end_t", None)
                use_selection = (
                    (not state.get("resume_from_cursor", False))
                    and sel_s is not None and sel_e is not None and (sel_e - sel_s) >= 0.01
                )
                if use_selection:
                    start_at = max(0.0, min(total_duration, min(sel_s, sel_e)))
                    play_end = max(0.0, min(total_duration, max(sel_s, sel_e)))
                else:
                    start_at = max(0.0, min(total_duration, state.get("cursor_time", 0.0)))
                    if (
                        sel_s is not None and sel_e is not None and
                        min(sel_s, sel_e) <= start_at <= max(sel_s, sel_e)
                    ):
                        play_end = max(sel_s, sel_e)
                    else:
                        play_end = total_duration
                if play_end <= start_at + 1e-4:
                    play_end = min(total_duration, start_at + 0.01)
                state["resume_from_cursor"] = False
                state["play_seg_start_frame"] = int(max(0, min(total_frames, round(start_at * sample_rate))))
                state["play_seg_end_frame"] = int(max(state["play_seg_start_frame"] + 1, min(total_frames, round(play_end * sample_rate))))
                play_source = _build_gain_playback_file(state.get("gain_db", 0.0))
                pg.mixer.music.load(play_source)
                pg.mixer.music.play()
                state["play_start_offset"] = start_at
                state["play_end_time"] = max(start_at, play_end)
                state["playback_time"] = start_at
                state["is_playing"] = True
                state["is_paused"] = False
                state["first_valid_pos_seen"] = False
                state["start_grace_until_perf"] = time.perf_counter() + 1.0
                _set_play_clock(start_at)
                wave_pause_btn.config(text="暂停")
                _schedule_progress()
            except Exception as e:
                messagebox.showerror("播放失败", f"播放音频失败：\n{e}")
        
        def _restart_playback_with_current_gain():
            """播放中调整增益时，从当前进度无缝重启播放到新增益版本。"""
            if not state.get("is_playing", False):
                return
            pg = _get_pg()
            if not pg:
                return
            cur_t = state.get("playback_time", 0.0)
            try:
                pg.mixer.music.stop()
            except Exception:
                pass
            state["is_playing"] = False
            state["is_paused"] = False
            state["cursor_time"] = cur_t
            state["resume_from_cursor"] = True
            wave_pause_btn.config(text="暂停")
            play_audio()
        
        def pause_resume_audio():
            pg = _get_pg()
            if not pg:
                return
            try:
                if state["is_playing"] and not state["is_paused"]:
                    state["playback_time"] = max(0.0, min(total_duration, _get_clock_time()))
                    pg.mixer.music.pause()
                    state["is_paused"] = True
                    wave_pause_btn.config(text="继续")
                elif state["is_paused"]:
                    pg.mixer.music.unpause()
                    state["is_paused"] = False
                    _set_play_clock(state.get("playback_time", 0.0))
                    wave_pause_btn.config(text="暂停")
                    _schedule_progress()
            except Exception:
                pass
        
        def stop_audio():
            pg = _get_pg()
            if not pg:
                return
            try:
                pg.mixer.music.stop()
            except Exception:
                pass
            state["is_playing"] = False
            state["is_paused"] = False
            state["playback_time"] = state.get("cursor_time", 0.0)
            state["play_end_time"] = state.get("playback_time", 0.0)
            try:
                wave_pause_btn.config(text="暂停")
            except Exception:
                pass
            if state.get("progress_job") is not None:
                try:
                    win.after_cancel(state["progress_job"])
                except Exception:
                    pass
                state["progress_job"] = None
            _update_playhead_overlay()
            request_render(1)
        
        def _schedule_progress():
            if state.get("progress_job") is not None:
                try:
                    win.after_cancel(state["progress_job"])
                except Exception:
                    pass
            state["progress_job"] = win.after(30, _update_progress)
        
        def _update_progress():
            state["progress_job"] = None
            if not state.get("is_playing", False) or state.get("is_paused", False):
                return
            pg = _get_pg()
            if not pg:
                return
            # 拖拽选区时暂停高成本重绘，避免“松手后延迟显示选区”。
            if state.get("is_dragging", False):
                _schedule_progress()
                return
            now_perf = time.perf_counter()
            try:
                pos_ms = pg.mixer.music.get_pos()
            except Exception:
                pos_ms = -1
            try:
                is_busy = bool(pg.mixer.music.get_busy())
            except Exception:
                is_busy = False
            if pos_ms >= 0:
                # 以播放器返回位置为主，避免“界面时钟超前于真实声音”。
                state["first_valid_pos_seen"] = True
                latency_s = max(0.0, float(state.get("playback_latency_s", 0.0) or 0.0))
                audible_pos_s = max(0.0, (pos_ms / 1000.0) - latency_s)
                state["playback_time"] = max(
                    0.0,
                    min(total_duration, state.get("play_start_offset", 0.0) + audible_pos_s)
                )
                _set_play_clock(state["playback_time"])
            elif is_busy and state.get("first_valid_pos_seen", False):
                # 极短暂拿不到位置时，用最近锚点平滑补间，避免光标停住抖动。
                state["playback_time"] = max(0.0, min(total_duration, _get_clock_time()))
            elif (not is_busy) and now_perf >= float(state.get("start_grace_until_perf", 0.0)):
                state["is_playing"] = False
                state["is_paused"] = False
                try:
                    wave_pause_btn.config(text="暂停")
                except Exception:
                    pass
                request_render(1)
                return
            if state["playback_time"] >= max(state.get("play_start_offset", 0.0), state.get("play_end_time", total_duration)) - 0.02:
                state["cursor_time"] = max(state.get("play_start_offset", 0.0), state.get("play_end_time", total_duration))
                state["playback_time"] = state["cursor_time"]
                stop_audio()
                return
            _update_playhead_overlay()
            _schedule_progress()
        
        def on_scroll(*args):
            canvas.xview(*args)
            request_render(1)
        
        hscroll.config(command=on_scroll)
        
        canvas.bind("<ButtonPress-1>", on_drag_start)
        canvas.bind("<B1-Motion>", on_drag_move)
        canvas.bind("<Control-MouseWheel>", on_ctrl_wheel)
        canvas.bind("<Control-Button-4>", lambda e: on_ctrl_wheel(direction=1))
        canvas.bind("<Control-Button-5>", lambda e: on_ctrl_wheel(direction=-1))
        canvas.bind("<ButtonRelease-1>", on_click_release)
        canvas.bind("<Button-3>", clear_selection)
        canvas.bind("<Configure>", lambda _e: request_render(1))
        db_canvas.bind("<Configure>", lambda _e: request_render(1))
        
        btn_zoom_in.config(command=lambda: zoom_step(+1))
        btn_zoom_out.config(command=lambda: zoom_step(-1))
        btn_zoom_reset.config(command=zoom_reset)
        btn_gain_up.config(command=lambda: gain_step(+1))
        btn_gain_down.config(command=lambda: gain_step(-1))
        btn_gain_reset.config(command=gain_reset)
        wave_play_btn.config(command=play_audio)
        wave_pause_btn.config(command=pause_resume_audio)
        wave_stop_btn.config(command=stop_audio)
        
        def _on_wave_win_close():
            stop_audio()
            if state.get("gain_play_path"):
                try:
                    os.remove(state["gain_play_path"])
                except Exception:
                    pass
            try:
                win.destroy()
            except Exception:
                pass
        win.protocol("WM_DELETE_WINDOW", _on_wave_win_close)
        
        render()
    
    def setup_multichannel_tab(self, parent):
        """设置多声道测试选项卡（7.1/2.1/2.0 使用 audio/channel/ 下对应默认音频）"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(frame, 
                        text="播放多声道测试音频\n用于验证多声道音频输出")
        desc.pack(pady=10)
        
        # 声道选择：7.1 / 2.1 / 2.0（与 Loopback 一致，使用 audio/channel/ 下对应文件）
        source_frame = ttk.Frame(frame)
        source_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(source_frame, text="声道:", font=("Arial", 9)).pack(side="left", padx=(0, 8))
        self.multichannel_preset_var = tk.StringVar(value="7.1")
        ttk.Radiobutton(source_frame, text="7.1", variable=self.multichannel_preset_var, value="7.1").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(source_frame, text="2.1", variable=self.multichannel_preset_var, value="2.1").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(source_frame, text="2.0", variable=self.multichannel_preset_var, value="2.0").pack(side="left", padx=(0, 12))
        
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
        
        # 播放设备ID（tinyplay -d）
        play_dev_frame = ttk.Frame(params_frame)
        play_dev_frame.pack(fill="x", pady=5)
        ttk.Label(play_dev_frame, text="播放设备ID(-d):").pack(side="left", padx=5)
        self.multichannel_play_device_var = tk.StringVar(value="0")
        self.multichannel_play_device_combo = ttk.Combobox(
            play_dev_frame,
            textvariable=self.multichannel_play_device_var,
            values=["0", "1"],
            width=8,
            state="normal",
        )
        self.multichannel_play_device_combo.pack(side="left", padx=5)
        ttk.Button(
            play_dev_frame,
            text="读取alsaPORT播放设备",
            style="Small.TButton",
            command=self._refresh_multichannel_playback_devices,
            width=18,
        ).pack(side="left", padx=(8, 0))
        
        # 开始按钮
        start_button = ttk.Button(frame, text="开始多声道测试", 
                                command=self.run_multichannel_test)
        start_button.pack(pady=20)
    
    def _refresh_multichannel_playback_devices(self):
        """读取当前设备的 alsaPORT 播放设备索引并更新多声道播放设备下拉。"""
        if not self.check_device_selected():
            return
        device_id = (getattr(self, "device_var", None) and self.device_var.get() or "").strip()
        values, detail = self._query_alsaport_playback_indexes(device_id)
        if values:
            if hasattr(self, "multichannel_play_device_combo") and self.multichannel_play_device_combo.winfo_exists():
                self.multichannel_play_device_combo["values"] = values
            cur = (getattr(self, "multichannel_play_device_var", None) and self.multichannel_play_device_var.get() or "").strip()
            if cur not in values:
                self.multichannel_play_device_var.set(values[0])
            self.status_var.set(f"多声道播放设备: {', '.join(values)}")
        else:
            self.status_var.set("未读取到多声道播放设备，保留当前手动输入")
        messagebox.showinfo("多声道播放设备", detail)
    
    def setup_jitter_tab(self, parent):
        """震音测试：播放指定音频（tinyplay），人工判断通过/不通过"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="播放指定音频进行震音测试（tinyplay）。\n请根据听感人工判断测试是否通过。",
            justify=tk.LEFT,
        )
        desc.pack(anchor="w", pady=(0, 10))
        
        # 测试音频路径（默认 audio/sound/80-1KHz-20S(-3dB).wav）
        default_jitter_audio = os.path.join(
            self._get_runtime_base_dir(),
            "audio", "sound", "80-1KHz-20S(-3dB).wav"
        )
        path_frame = ttk.LabelFrame(frame, text="测试音频")
        path_frame.pack(fill="x", pady=8)
        self.jitter_audio_path_var = tk.StringVar(value=default_jitter_audio)
        path_entry = ttk.Entry(path_frame, textvariable=self.jitter_audio_path_var, width=60)
        path_entry.pack(side="left", fill="x", expand=True, padx=8, pady=6)
        ttk.Button(path_frame, text="浏览", command=self._browse_jitter_audio, width=6, style="Small.TButton").pack(side="left", padx=(0, 4), pady=6)
        ttk.Button(
            path_frame, text="打开位置",
            command=lambda: self.open_containing_folder(self.jitter_audio_path_var.get()),
            width=8, style="Small.TButton"
        ).pack(side="left", padx=(0, 8), pady=6)
        
        # 操作按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=10)
        self.jitter_start_btn = ttk.Button(btn_frame, text="开始震音测试", command=self.run_jitter_test, width=14)
        self.jitter_start_btn.pack(side="left", padx=(0, 8))
        self.jitter_stop_btn = ttk.Button(btn_frame, text="停止播放", command=self.stop_jitter_test, width=10, state="disabled")
        self.jitter_stop_btn.pack(side="left", padx=(0, 8))
        
        # 人工判断（播放结束后显示）
        result_frame = ttk.LabelFrame(frame, text="人工判断测试结果")
        result_frame.pack(fill="x", pady=10)
        self.jitter_result_var = tk.StringVar(value="请先完成震音测试播放后，根据听感点击下方按钮。")
        ttk.Label(result_frame, textvariable=self.jitter_result_var, wraplength=500, justify=tk.LEFT).pack(anchor="w", padx=8, pady=(6, 4))
        judge_frame = ttk.Frame(result_frame)
        judge_frame.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(judge_frame, text="通过", command=self._jitter_judge_pass, width=8).pack(side="left", padx=(0, 8))
        ttk.Button(judge_frame, text="不通过", command=self._jitter_judge_fail, width=8).pack(side="left", padx=(0, 8))
        
        # 状态
        self.jitter_status_var = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.jitter_status_var, font=("Arial", 9)).pack(anchor="w", pady=6)
        
        # 过程日志（显示播放过程）
        log_frame = ttk.LabelFrame(frame, text="震音测试日志")
        log_frame.pack(fill="both", expand=True, pady=(2, 0))
        self.jitter_log_text = tk.Text(log_frame, height=8, wrap="word", font=("Consolas", 9), state="disabled")
        jitter_log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.jitter_log_text.yview)
        self.jitter_log_text.configure(yscrollcommand=jitter_log_scroll.set)
        self.jitter_log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        jitter_log_scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self._append_jitter_log("就绪，点击“开始震音测试”后将显示音量与播放日志。")
    
    def _browse_jitter_audio(self):
        """浏览并选择震音测试音频文件（不依赖默认文件名或打包是否复制）"""
        initial_dir = self.jitter_audio_path_var.get()
        if initial_dir and os.path.isdir(os.path.dirname(initial_dir)):
            initial_dir = os.path.dirname(initial_dir)
        else:
            initial_dir = os.path.join(self._get_runtime_base_dir(), "audio", "sound")
        if not os.path.isdir(initial_dir):
            initial_dir = self._get_runtime_base_dir()
        path = filedialog.askopenfilename(
            title="选择震音测试音频",
            initialdir=initial_dir,
            filetypes=[("WAV 文件", "*.wav"), ("所有文件", "*.*")],
        )
        if path:
            self.jitter_audio_path_var.set(path)
            self.jitter_status_var.set("已选择: " + os.path.basename(path))
            self._append_jitter_log(f"已选择测试音频: {path}")
    
    def _append_jitter_log(self, message):
        """线程安全：在震音测试日志区域追加一行日志"""
        root = getattr(self, "root", None) or getattr(self, "parent", None)
        if root is None:
            return
        def _do():
            txt = getattr(self, "jitter_log_text", None)
            if not txt or not txt.winfo_exists():
                return
            txt.config(state="normal")
            txt.insert("end", f"{message}\n")
            try:
                total_lines = int(txt.index("end-1c").split(".")[0])
                if total_lines > 500:
                    txt.delete("1.0", "2.0")
            except Exception:
                pass
            txt.see("end")
            txt.config(state="disabled")
        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            root.after(0, _do)

    def _adb_run_for_device(self, device_id, cmd, timeout=15):
        if device_id:
            full = f"adb -s {device_id} {cmd}"
        else:
            full = f"adb {cmd}"
        return subprocess.run(full, shell=True, capture_output=True, text=True, timeout=timeout)

    def _release_audioserver_for_tinyplay(self, device_id, max_rounds=6, wait_s=0.35):
        """
        释放 audioserver 对播放设备的占用（适配部分机型需多次 killall 才能 tinyplay 成功）。
        返回：(rounds_used, released)
        """
        rounds_used = 0
        released = False
        for i in range(max_rounds):
            rounds_used = i + 1
            self._adb_run_for_device(device_id, "shell killall audioserver", timeout=5)
            time.sleep(wait_s)
            # 若系统仍拉起 audioserver，继续尝试；若已无进程，认为释放成功
            pid_res = self._adb_run_for_device(device_id, "shell pidof audioserver", timeout=5)
            pid_txt = ((pid_res.stdout or "") + (pid_res.stderr or "")).strip()
            if pid_res.returncode != 0 or not pid_txt:
                released = True
                break
        return rounds_used, released
    
    def _jitter_judge_pass(self):
        """震音测试人工判定：通过"""
        self.jitter_result_var.set("测试结果：通过")
        self.jitter_status_var.set("震音测试已判定为通过")
        self._append_jitter_log("人工判定结果: 通过")
        messagebox.showinfo("震音测试", "已记录：通过")
    
    def _jitter_judge_fail(self):
        """震音测试人工判定：不通过"""
        self.jitter_result_var.set("测试结果：不通过")
        self.jitter_status_var.set("震音测试已判定为不通过")
        self._append_jitter_log("人工判定结果: 不通过")
        messagebox.showinfo("震音测试", "已记录：不通过")
    
    def run_jitter_test(self):
        """开始震音测试：推送并播放音频"""
        if not self.check_device_selected():
            return
        path = (self.jitter_audio_path_var.get() or "").strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(
                "错误",
                f"测试音频文件不存在：\n{path}\n\n请点击「浏览」选择本机上的震音测试音频文件（如 80-1KHz-20S(-3dB).wav），或将该文件放到 audio/sound 目录后重试。"
            )
            return
        device_id = (getattr(self, "device_var", None) and self.device_var.get() or "").strip()
        self.jitter_start_btn.config(state="disabled")
        self.jitter_stop_btn.config(state="normal")
        self.jitter_status_var.set("正在准备震音测试...")
        self.jitter_result_var.set("请先完成震音测试播放后，根据听感点击下方按钮。")
        if hasattr(self, "jitter_log_text") and self.jitter_log_text.winfo_exists():
            self.jitter_log_text.config(state="normal")
            self.jitter_log_text.delete("1.0", "end")
            self.jitter_log_text.config(state="disabled")
        self._append_jitter_log(f"开始测试，设备: {device_id or '默认设备'}")
        self._append_jitter_log(f"测试音频: {path}")
        self._append_jitter_log("播放方式: tinyplay")
        threading.Thread(
            target=self._jitter_test_thread,
            args=(path, device_id),
            daemon=True,
        ).start()
    
    def _jitter_test_thread(self, path, device_id):
        """震音测试后台：推送播放"""
        try:
            root = getattr(self, "root", None) or getattr(self, "parent", None)
            root.after(0, lambda: self.jitter_status_var.set("正在准备播放环境..."))

            # 2. 推送到设备
            remote_name = "jitter_test_audio.wav"
            if device_id:
                push_result = subprocess.run(
                    f"adb -s {device_id} push \"{path}\" /sdcard/{remote_name}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                push_result = subprocess.run(
                    f"adb push \"{path}\" /sdcard/{remote_name}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            if push_result.returncode != 0:
                raise RuntimeError(f"推送音频失败: {(push_result.stderr or push_result.stdout or '').strip()}")
            self._append_jitter_log("音频推送成功，准备播放...")
            
            # 3. 与扫频测试保持一致：播放前清理占用并重启 audioserver
            self._append_jitter_log("播放参数: 固定卡0 / 设备0")

            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinyplay", shell=True, capture_output=True)
                rounds, released = self._release_audioserver_for_tinyplay(device_id)
                self._append_jitter_log(
                    f"释放 audioserver 占用: 已尝试 {rounds} 次，状态={'已释放' if released else '未确认'}"
                )
                adb_prefix = f"adb -s {device_id} shell "
            else:
                subprocess.run("adb shell killall tinyplay", shell=True, capture_output=True)
                rounds, released = self._release_audioserver_for_tinyplay(device_id)
                self._append_jitter_log(
                    f"释放 audioserver 占用: 已尝试 {rounds} 次，状态={'已释放' if released else '未确认'}"
                )
                adb_prefix = "adb shell "

            # 用户要求固定播放参数：仅卡0/设备0
            play_cmds = [
                f"{adb_prefix}tinyplay /sdcard/{remote_name} -D 0 -d 0",
            ]
            
            root.after(0, lambda: self.jitter_status_var.set("正在播放测试音频..."))

            self._jitter_device_id = device_id
            self.jitter_play_process = None

            last_err = ""
            for cmd in play_cmds:
                # 在同一条 shell 中连续释放 audioserver 后立刻 tinyplay，贴近手工命令成功路径
                inline_cmd = (
                    f"{adb_prefix}\"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"{cmd.replace(adb_prefix, '')}\""
                )
                self._append_jitter_log(f"尝试播放命令: {inline_cmd}")
                proc = subprocess.Popen(inline_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                time.sleep(1.0)
                if proc.poll() is None:
                    self.jitter_play_process = proc
                    self._append_jitter_log("tinyplay 已启动。")
                    break
                try:
                    out, err = proc.communicate(timeout=1)
                except Exception:
                    out, err = ("", "")
                last_err = (err or out or "").strip()
                if last_err:
                    self._append_jitter_log(f"该命令启动失败: {last_err[:200]}")
            if self.jitter_play_process is None:
                raise RuntimeError(f"播放失败（tinyplay）: {last_err[:220]}")
            root.after(0, lambda: self.jitter_status_var.set("正在播放震音测试音频，请根据听感判断。"))
            self.jitter_play_process.wait()
            self.jitter_play_process = None
            
            if root and root.winfo_exists():
                root.after(0, self._jitter_test_finished)
        except Exception as e:
            root = getattr(self, "root", None) or getattr(self, "parent", None)
            if root and root.winfo_exists():
                root.after(0, lambda: self._jitter_test_error(str(e)))
    
    def _jitter_test_finished(self):
        """震音测试播放结束：恢复 UI，提示人工判断"""
        self.jitter_play_process = None
        self.jitter_start_btn.config(state="normal")
        self.jitter_stop_btn.config(state="disabled")
        self.jitter_status_var.set("播放已结束。请根据听感点击「通过」或「不通过」。")
        self.jitter_result_var.set("播放已结束，请根据听感点击「通过」或「不通过」。")
        self._append_jitter_log("播放结束。")
    
    def _jitter_test_error(self, err_msg):
        """震音测试出错"""
        self.jitter_play_process = None
        self.jitter_start_btn.config(state="normal")
        self.jitter_stop_btn.config(state="disabled")
        self.jitter_status_var.set(f"震音测试出错: {err_msg}")
        self._append_jitter_log(f"测试出错: {err_msg}")
        messagebox.showerror("错误", f"震音测试出错:\n{err_msg}")
    
    def stop_jitter_test(self):
        """停止震音测试播放并恢复音量"""
        device_id = getattr(self, "_jitter_device_id", "")
        try:
            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinyplay", shell=True, capture_output=True, timeout=5)
            else:
                subprocess.run("adb shell killall tinyplay", shell=True, capture_output=True, timeout=5)
        except Exception:
            pass
        if getattr(self, "jitter_play_process", None):
            self.jitter_play_process = None
        if hasattr(self, "jitter_start_btn") and self.jitter_start_btn.winfo_exists():
            self.jitter_start_btn.config(state="normal")
        if hasattr(self, "jitter_stop_btn") and self.jitter_stop_btn.winfo_exists():
            self.jitter_stop_btn.config(state="disabled")
        if hasattr(self, "jitter_status_var"):
            self.jitter_status_var.set("已停止播放。")
        if hasattr(self, "jitter_result_var"):
            self.jitter_result_var.set("请先完成震音测试播放后，根据听感点击下方按钮。")
        self._append_jitter_log("已手动停止播放。")
    
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
    
    def setup_sweep_tab(self, parent, handler=None):
        """设置扫频测试标签页"""
        # 如果没有传递handler，使用当前应用实例（self）
        # 注意：self.parent 是 Tk root，不包含设备变量/ADB方法，不能作为业务handler使用
        if handler is None:
            handler = self
        
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)
        
        # 扫频类型选择
        type_frame = ttk.Frame(frame)
        type_frame.pack(fill="x", pady=5)
        
        ttk.Label(type_frame, text="扫频类型:").pack(side="left")
        
        self.sweep_type_var = tk.StringVar(value="elephant")
        ttk.Radiobutton(type_frame, text="大象扫频文件", variable=self.sweep_type_var, 
                       value="elephant", command=lambda: self.update_sweep_file_options(handler)).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(type_frame, text="自定义扫频文件", variable=self.sweep_type_var, 
                       value="custom", command=lambda: self.update_sweep_file_options(handler)).pack(side="left", padx=(10, 0))
        
        # 文件选择
        file_frame = ttk.Frame(frame)
        file_frame.pack(fill="x", pady=5)
        
        ttk.Label(file_frame, text="扫频文件:").pack(side="left")
        
        self.sweep_file_var = tk.StringVar()
        self.sweep_file_combobox = ttk.Combobox(file_frame, textvariable=self.sweep_file_var, 
                                           width=50)
        self.sweep_file_combobox.pack(side="left", padx=(10, 5))
        
        self.add_custom_sweep_button = ttk.Button(file_frame, text="添加文件", 
                                             command=lambda: self.add_custom_sweep_file(handler))
        self.add_custom_sweep_button.pack(side="left", padx=5)
        
        # 录制设置
        record_frame = ttk.LabelFrame(frame, text="录制设置")
        record_frame.pack(fill="x", pady=5)
        
        record_line1 = ttk.Frame(record_frame)
        record_line1.pack(fill="x", padx=10, pady=2)
        
        ttk.Label(record_line1, text="设备:", font=("Arial", 8)).pack(side="left")
        self.record_device_var = tk.StringVar(value="0")  # 修正为设备0
        ttk.Combobox(record_line1, textvariable=self.record_device_var, 
                    values=["0", "1", "2", "3"], width=5).pack(side="left", padx=(5, 10))
        
        ttk.Label(record_line1, text="卡号:", font=("Arial", 8)).pack(side="left")
        self.record_card_var = tk.StringVar(value="3")  # 修正为卡3
        ttk.Combobox(record_line1, textvariable=self.record_card_var, 
                    values=["0", "1", "2", "3"], width=5).pack(side="left", padx=(5, 10))
        
        ttk.Label(record_line1, text="通道:", font=("Arial", 8)).pack(side="left")
        self.record_channels_var = tk.StringVar(value="4")
        ttk.Combobox(record_line1, textvariable=self.record_channels_var, 
                    values=["1", "2", "4", "8"], width=5).pack(side="left", padx=(5, 10))
        
        ttk.Label(record_line1, text="采样率:", font=("Arial", 8)).pack(side="left")
        self.record_rate_var = tk.StringVar(value="16000")
        ttk.Combobox(record_line1, textvariable=self.record_rate_var, 
                    values=["8000", "16000", "44100", "48000"], width=8).pack(side="left", padx=5)
        
        ttk.Label(record_line1, text="位深:", font=("Arial", 8)).pack(side="left")
        self.record_bits_var = tk.StringVar(value="16")
        ttk.Combobox(record_line1, textvariable=self.record_bits_var, 
                    values=["16", "24", "32"], width=4).pack(side="left", padx=(5, 10))
        
        # 播放设置
        play_frame = ttk.LabelFrame(frame, text="播放设置")
        play_frame.pack(fill="x", pady=5)
        
        play_line1 = ttk.Frame(play_frame)
        play_line1.pack(fill="x", padx=10, pady=2)
        
        ttk.Label(play_line1, text="设备:", font=("Arial", 8)).pack(side="left")
        self.play_device_var = tk.StringVar(value="0")  # 播放设备0
        ttk.Combobox(play_line1, textvariable=self.play_device_var, 
                    values=["0", "1", "2", "3"], width=5).pack(side="left", padx=(5, 10))
        
        ttk.Label(play_line1, text="卡号:", font=("Arial", 8)).pack(side="left")
        self.play_card_var = tk.StringVar(value="0")  # 播放卡0
        ttk.Combobox(play_line1, textvariable=self.play_card_var, 
                    values=["0", "1", "2", "3"], width=5).pack(side="left", padx=5)
        
        # 测试设置
        test_frame = ttk.LabelFrame(frame, text="测试设置")
        test_frame.pack(fill="x", pady=5)
        
        test_line1 = ttk.Frame(test_frame)
        test_line1.pack(fill="x", padx=10, pady=2)
        
        ttk.Label(test_line1, text="录制时长(秒):").pack(side="left")
        self.sweep_duration_var = tk.StringVar(value="15")
        ttk.Entry(test_line1, textvariable=self.sweep_duration_var, width=5).pack(side="left", padx=(5, 15))
        
        # 批量测试选项
        self.batch_test_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(test_line1, text="批量测试", variable=self.batch_test_var).pack(side="left", padx=(0, 15))
        
        ttk.Label(test_line1, text="间隔时间(秒):").pack(side="left")
        self.batch_interval_var = tk.StringVar(value="2")
        ttk.Entry(test_line1, textvariable=self.batch_interval_var, width=5).pack(side="left", padx=5)
        
        # 控制按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x", pady=10)
        
        self.start_sweep_button = ttk.Button(button_frame, text="开始扫频测试", 
                                        command=lambda: self.start_sweep_test(handler))
        self.start_sweep_button.pack(side="left", padx=5)
        
        self.stop_sweep_button = ttk.Button(button_frame, text="停止测试", 
                                       command=lambda: self.stop_sweep_test(handler), state="disabled")
        self.stop_sweep_button.pack(side="left", padx=5)

        self.view_sweep_waveform_button = ttk.Button(
            button_frame,
            text="查看录音波形",
            command=self.show_latest_sweep_waveform,
            state="disabled",
        )
        self.view_sweep_waveform_button.pack(side="left", padx=5)
        
        ttk.Button(button_frame, text="打开文件夹", 
                  command=self.open_sweep_folder).pack(side="left", padx=5)
        
        ttk.Button(button_frame, text="浏览保存路径", 
                  command=self.browse_sweep_save_path).pack(side="left", padx=5)
        
        # 保存路径
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill="x", pady=5)
        
        ttk.Label(path_frame, text="保存路径:").pack(side="left")
        self.sweep_save_path_var = tk.StringVar(value=get_output_dir(DIR_SWEEP_RECORDINGS))
        ttk.Entry(path_frame, textvariable=self.sweep_save_path_var, width=60).pack(side="left", padx=(10, 0), fill="x", expand=True)
        
        # 状态和信息显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="both", expand=True, pady=5)
        
        # 状态标签
        self.sweep_status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.sweep_status_var, font=("Arial", 10, "bold")).pack(anchor="w")
        
        # 信息文本框
        info_frame = ttk.LabelFrame(status_frame, text="测试信息")
        info_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        self.sweep_info_text = tk.Text(info_frame, height=10, wrap="word")
        scrollbar = ttk.Scrollbar(info_frame, command=self.sweep_info_text.yview)
        self.sweep_info_text.config(yscrollcommand=scrollbar.set)
        
        self.sweep_info_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 初始化文件选项
        self.update_sweep_file_options(handler)
    
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
        # 录音属性列表支持鼠标滚轮滚动
        self._bind_mousewheel_to_canvas(props_canvas, props_canvas)
        self._bind_mousewheel_to_canvas(self.props_container, props_canvas)

        # 添加默认属性
        self.hal_props = {}  # 存储属性和对应的变量
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
        
        # 默认保存到 output/hal_dump
        default_save_path = ensure_output_dir(DIR_HAL_DUMP)
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
            "vendor.media.audiohal.speech.dump",
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
        self.custom_save_path_var = tk.StringVar(value=get_output_dir(DIR_HAL_CUSTOM))
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
        
        # 默认保存到 output/screenshots
        default_save_path = ensure_output_dir(DIR_SCREENSHOTS)
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
    
    def setup_account_login_tab(self, parent):
        """设置账号登录小类：预设账号或手动添加的自定义账号，执行「输入账号 -> 点 Next -> 输入密码」"""
        # 外层：上方可滚动区域 + 底部固定「设备登录操作」，避免按钮被遮挡
        outer = ttk.Frame(parent, padding=10)
        outer.pack(fill="both", expand=True)
        
        # 可滚动内容区（选择账号、详情、添加新账号）
        scroll_container = ttk.Frame(outer)
        scroll_container.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_container, highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)
        
        frame = ttk.Frame(canvas)
        canvas_frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")
        def _on_frame_configure(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_frame_id, width=e.width)
        frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        desc = ttk.Label(
            frame,
            text="请先在设备上打开对应应用的登录页，光标放在账号输入框内。\n操作：点击「输入账号」→ 在设备上手动点击 Next → 再点击「输入密码」。",
            font=("Arial", 9),
            foreground="gray",
            justify="left",
            wraplength=480,
        )
        desc.pack(pady=(0, 10))
        
        # 预设 + 自定义 统一用下拉选择
        if not hasattr(self, "_custom_accounts"):
            self._custom_accounts = []  # [{"name": str, "email": str, "password": str}, ...]
        
        account_frame = ttk.LabelFrame(frame, text="选择账号", padding=8)
        account_frame.pack(fill="x", pady=4)
        
        self._account_preset_labels = ["Google 账号", "Netflix 账号", "ART 账号"]
        self._account_preset_keys = ["google", "netflix", "art"]
        self.account_login_var = tk.StringVar(value=self._account_preset_labels[0])
        
        def refresh_account_combo():
            vals = list(self._account_preset_labels) + [a["name"] for a in self._custom_accounts]
            self._account_combo["values"] = vals
            if vals and self.account_login_var.get() not in vals:
                self.account_login_var.set(vals[0])
        
        ttk.Label(account_frame, text="账号:", font=("Arial", 9)).pack(side="left", padx=(0, 5))
        self._account_combo = ttk.Combobox(
            account_frame,
            textvariable=self.account_login_var,
            values=self._account_preset_labels + [a["name"] for a in self._custom_accounts],
            width=28,
            state="readonly",
        )
        self._account_combo.pack(side="left", padx=2, pady=2)
        
        # 当前选中账号的详情（查看/编辑）
        detail_frame = ttk.LabelFrame(frame, text="当前账号详情（可查看与修改）", padding=8)
        detail_frame.pack(fill="x", pady=4)
        
        row1 = ttk.Frame(detail_frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="名称:", width=6, font=("Arial", 9)).pack(side="left", padx=(0, 2))
        self._custom_name_var = tk.StringVar()
        self._custom_name_entry = ttk.Entry(row1, textvariable=self._custom_name_var, width=20)
        self._custom_name_entry.pack(side="left", padx=2)
        ttk.Label(row1, text="邮箱:", width=6, font=("Arial", 9)).pack(side="left", padx=(10, 2))
        self._custom_email_var = tk.StringVar()
        self._custom_email_entry = ttk.Entry(row1, textvariable=self._custom_email_var, width=28)
        self._custom_email_entry.pack(side="left", padx=2)
        
        row2 = ttk.Frame(detail_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="密码:", width=6, font=("Arial", 9)).pack(side="left", padx=(0, 2))
        self._custom_password_var = tk.StringVar()
        self._custom_password_entry = ttk.Entry(row2, textvariable=self._custom_password_var, width=20, show="*")
        self._custom_password_entry.pack(side="left", padx=2)
        self._show_password_var = tk.BooleanVar(value=False)
        def toggle_show_password():
            if self._show_password_var.get():
                self._custom_password_entry.configure(show="")
            else:
                self._custom_password_entry.configure(show="*")
        ttk.Checkbutton(row2, text="显示密码", variable=self._show_password_var, command=toggle_show_password).pack(side="left", padx=(10, 0))
        ttk.Frame(row2, width=1).pack(side="left", fill="x", expand=True)
        
        def on_account_selected(event=None):
            """选择账号时填充详情区，预设只读、自定义可编辑"""
            sel = (self.account_login_var.get() or "").strip()
            if not sel:
                self._custom_name_var.set("")
                self._custom_email_var.set("")
                self._custom_password_var.set("")
                self._custom_name_entry.config(state="normal")
                self._custom_email_entry.config(state="normal")
                self._custom_password_entry.config(state="normal")
                if hasattr(self, "_btn_save_account"):
                    self._btn_save_account.pack_forget()
                return
            email, password = self._get_selected_account_credentials()
            self._custom_name_var.set(sel)
            self._custom_email_var.set(email or "")
            self._custom_password_var.set(password or "")
            if sel in self._account_preset_labels:
                self._custom_name_entry.config(state="disabled")
                self._custom_email_entry.config(state="disabled")
                self._custom_password_entry.config(state="disabled")
                if hasattr(self, "_btn_save_account"):
                    self._btn_save_account.pack_forget()
            else:
                self._custom_name_entry.config(state="normal")
                self._custom_email_entry.config(state="normal")
                self._custom_password_entry.config(state="normal")
                if hasattr(self, "_btn_save_account"):
                    self._btn_save_account.pack(side="right", padx=(8, 0))
        
        self._account_combo.bind("<<ComboboxSelected>>", on_account_selected)
        
        def save_custom_account():
            sel = (self.account_login_var.get() or "").strip()
            if sel in self._account_preset_labels:
                messagebox.showinfo("保存", "预设账号不可修改")
                return
            new_name = (self._custom_name_var.get() or "").strip()
            email = (self._custom_email_var.get() or "").strip()
            password = (self._custom_password_var.get() or "").strip()
            if not new_name:
                messagebox.showwarning("保存", "名称不能为空")
                return
            if not email:
                messagebox.showwarning("保存", "邮箱不能为空")
                return
            if not password:
                messagebox.showwarning("保存", "密码不能为空")
                return
            if new_name in self._account_preset_labels:
                messagebox.showwarning("保存", "名称不能与预设账号相同")
                return
            for a in self._custom_accounts:
                if a["name"] == sel:
                    if new_name != sel and any(a2["name"] == new_name for a2 in self._custom_accounts if a2 != a):
                        messagebox.showwarning("保存", "该名称已被其他账号使用")
                        return
                    a["name"] = new_name
                    a["email"] = email
                    a["password"] = password
                    refresh_account_combo()
                    self.account_login_var.set(new_name)
                    messagebox.showinfo("保存", f"已保存「{new_name}」的修改")
                    return
            messagebox.showwarning("保存", "未找到当前选中的自定义账号")
        self._btn_save_account = ttk.Button(row2, text="保存修改", command=save_custom_account, width=10)
        # 初始不显示，选择自定义账号时由 on_account_selected 显示
        
        # 手动添加账号（新增账号）
        custom_frame = ttk.LabelFrame(frame, text="手动添加新账号", padding=8)
        custom_frame.pack(fill="x", pady=6)
        
        add_row1 = ttk.Frame(custom_frame)
        add_row1.pack(fill="x", pady=2)
        ttk.Label(add_row1, text="名称:", width=6, font=("Arial", 9)).pack(side="left", padx=(0, 2))
        self._add_name_var = tk.StringVar()
        ttk.Entry(add_row1, textvariable=self._add_name_var, width=20).pack(side="left", padx=2)
        ttk.Label(add_row1, text="邮箱:", width=6, font=("Arial", 9)).pack(side="left", padx=(10, 2))
        self._add_email_var = tk.StringVar()
        ttk.Entry(add_row1, textvariable=self._add_email_var, width=28).pack(side="left", padx=2)
        
        add_row2 = ttk.Frame(custom_frame)
        add_row2.pack(fill="x", pady=2)
        ttk.Label(add_row2, text="密码:", width=6, font=("Arial", 9)).pack(side="left", padx=(0, 2))
        self._add_password_var = tk.StringVar()
        ttk.Entry(add_row2, textvariable=self._add_password_var, width=20, show="*").pack(side="left", padx=2)
        
        def add_custom_account():
            name = (self._add_name_var.get() or "").strip()
            email = (self._add_email_var.get() or "").strip()
            password = (self._add_password_var.get() or "").strip()
            if not name:
                messagebox.showwarning("添加账号", "请填写名称（用于在列表中区分）")
                return
            if not email:
                messagebox.showwarning("添加账号", "请填写邮箱")
                return
            if not password:
                messagebox.showwarning("添加账号", "请填写密码")
                return
            if name in self._account_preset_labels:
                messagebox.showwarning("添加账号", "该名称与预设账号冲突，请换一个名称")
                return
            for a in self._custom_accounts:
                if a["name"] == name:
                    messagebox.showwarning("添加账号", "已存在同名账号，请换一个名称或删除后重加")
                    return
            self._custom_accounts.append({"name": name, "email": email, "password": password})
            refresh_account_combo()
            self.account_login_var.set(name)
            self._add_name_var.set("")
            self._add_email_var.set("")
            self._add_password_var.set("")
            on_account_selected()
            messagebox.showinfo("添加账号", f"已添加「{name}」，可在上方选择后执行登录。")
        
        def remove_custom_account():
            sel = self.account_login_var.get().strip()
            if sel in self._account_preset_labels:
                messagebox.showinfo("删除账号", "预设账号不可删除")
                return
            for i, a in enumerate(self._custom_accounts):
                if a["name"] == sel:
                    self._custom_accounts.pop(i)
                    refresh_account_combo()
                    if self._account_combo["values"]:
                        self.account_login_var.set(self._account_combo["values"][0])
                    on_account_selected()
                    messagebox.showinfo("删除账号", f"已删除「{sel}」")
                    return
            messagebox.showinfo("删除账号", "请先在上方选择要删除的自定义账号")
        
        add_btn_row = ttk.Frame(custom_frame)
        add_btn_row.pack(fill="x", pady=5)
        ttk.Frame(add_btn_row, width=1).pack(side="left", fill="x", expand=True)  # 占位，把按钮推到右侧
        btn_add = ttk.Button(add_btn_row, text="添加", command=add_custom_account, width=8)
        btn_add.pack(side="right", padx=(8, 0), pady=0)
        ttk.Button(add_btn_row, text="删除选中", command=remove_custom_account, width=10).pack(side="right", padx=2, pady=0)
        
        # 初始化：显示当前选中账号的详情
        on_account_selected()
        
        # 底部固定区域：设备登录操作（始终可见，不被上方内容遮挡）
        bottom_bar = ttk.Frame(outer)
        bottom_bar.pack(side="bottom", fill="x", pady=(10, 0))
        action_frame = ttk.LabelFrame(bottom_bar, text="设备登录操作", padding=10)
        action_frame.pack(fill="x")
        action_btn_row = ttk.Frame(action_frame)
        action_btn_row.pack(fill="x")
        ttk.Button(action_btn_row, text="输入账号", command=self._do_account_login_email_only, width=12).pack(side="left", padx=(0, 8))
        ttk.Button(action_btn_row, text="输入密码", command=self._do_account_login_password_only, width=12).pack(side="left", padx=0)
        
        self.account_login_status_var = tk.StringVar(value="")
        ttk.Label(bottom_bar, textvariable=self.account_login_status_var, font=("Arial", 9), foreground="gray").pack(pady=4)
    
    def _get_selected_account_credentials(self):
        """返回当前选中账号的 (email, password)，若无效返回 (None, None)。"""
        ACCOUNT_LOGINS = {
            "google": ("sei2020atv@gmail.com", "A26613121"),
            "netflix": ("tester_mediateam@netflix.com", "deD2@icE"),
            "art": ("sei2021art@gmail.com", "cTC77kMw"),
        }
        sel = (self.account_login_var.get() or "").strip()
        if sel in self._account_preset_labels:
            idx = self._account_preset_labels.index(sel)
            key = self._account_preset_keys[idx]
            return ACCOUNT_LOGINS[key]
        for a in getattr(self, "_custom_accounts", []):
            if a["name"] == sel:
                return a["email"], a["password"]
        return None, None
    
    def _do_account_login_email_only(self):
        """只向当前焦点输入账号，不发送任何按键（避免设备误把 keyevent 当成字符产生 11）。"""
        if not self.check_device_selected():
            return
        email, _ = self._get_selected_account_credentials()
        if not email:
            self.account_login_status_var.set("未选择有效账号")
            return
        device_id = (self.device_var.get() or "").strip() if hasattr(self, "device_var") else ""
        if device_id:
            subprocess.run(["adb", "-s", device_id, "shell", "input", "text", email], capture_output=True)
        else:
            subprocess.run(["adb", "shell", "input", "text", email], capture_output=True)
        self.account_login_status_var.set("已输入账号，请在设备上手动点击 Next，再点击「输入密码」。")
    
    def _do_account_login_password_only(self):
        """只向当前焦点输入密码，不发送任何按键（避免设备误把 keyevent 当成字符产生 1）。"""
        if not self.check_device_selected():
            return
        _, password = self._get_selected_account_credentials()
        if not password:
            self.account_login_status_var.set("未选择有效账号")
            return
        device_id = (self.device_var.get() or "").strip() if hasattr(self, "device_var") else ""
        if device_id:
            subprocess.run(["adb", "-s", device_id, "shell", "input", "text", password], capture_output=True)
        else:
            subprocess.run(["adb", "shell", "input", "text", password], capture_output=True)
        self.account_login_status_var.set("已输入密码，请在设备上手动点击登录/确认。")
    
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

        # 默认音频路径显示（让用户清楚“默认音频放哪里/当前路径是什么”）
        default_audio_path = os.path.join(os.getcwd(), "audio", "speaker", "speaker_default.wav")
        self.default_speaker_audio_path_var = tk.StringVar(value=default_audio_path)

        default_path_frame = ttk.Frame(audio_frame)
        default_path_frame.pack(fill="x", padx=10, pady=(0, 5))

        ttk.Label(default_path_frame, text="默认音频路径:", font=("Arial", 9)).pack(side="left", padx=(5, 5))
        default_path_entry = ttk.Entry(default_path_frame, textvariable=self.default_speaker_audio_path_var)
        default_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        default_path_entry.config(state="readonly")

        # 打开所在文件夹
        open_default_folder_btn = ttk.Button(
            default_path_frame,
            text="打开位置",
            style="Small.TButton",
            command=lambda p=default_audio_path: self.open_containing_folder(p),
            width=8,
        )
        open_default_folder_btn.pack(side="left", padx=(0, 5))
        
        # 添加默认音频文件按钮
        self.add_default_audio_button = ttk.Button(default_status_frame, text="添加默认音频文件", 
                                                command=self.add_default_audio_file,
                                                style="Small.TButton")
        self.add_default_audio_button.pack(side="left", padx=5)
        if os.path.exists(os.path.join(os.getcwd(), "audio", "speaker", "speaker_default.wav")):
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
        frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 删除标题，直接开始布局
        # ttk.Label(frame, text="音频日志控制", style="Header.TLabel").pack(pady=10)
        
        # 左右分栏布局（左：属性管理；右：日志控制/日志信息）
        main_frame = ttk.Frame(frame)
        main_frame.pack(fill="both", expand=True, padx=6, pady=5)
        
        # 左侧属性管理区域（略加宽，避免长属性被遮挡/截断）
        left_frame = ttk.Frame(main_frame, width=320)
        left_frame.pack(side="left", fill="both", padx=(2, 2), pady=5)
        left_frame.pack_propagate(False)  # 防止子组件改变frame大小
        
        # 右侧日志控制区域
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(2, 2), pady=5)
        
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
        
        # 属性列表区域 - 使用Canvas和Scrollbar（滚动条尽量窄，避免“遮挡/挤压”属性文本）
        canvas_frame = ttk.Frame(props_frame)
        canvas_frame.pack(fill="both", expand=True, padx=3, pady=5)
        
        # 创建Canvas和Scrollbar，调整Scrollbar样式使其更明显
        self.logcat_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        # 注意：部分 Tk/ttk 版本的 ttk.Scrollbar 不支持 width 这个 widget option（打包时会报 unknown option "-width"）
        # 这里不传 width，尽量通过 style/padding 控制视觉宽度。
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.logcat_canvas.yview)
        
        # 配置滚动条样式使其更加明显
        self.style = ttk.Style()
        self.style.configure(
            "Logcat.Vertical.TScrollbar",
            background="#bbbbbb",
            troughcolor="#dddddd",
            arrowcolor="#555555",
            bordercolor="#999999",
        )
        scrollbar.configure(style="Logcat.Vertical.TScrollbar")
        
        self.logcat_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y", padx=(2, 0))
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
        
        self.logcat_save_path_var = tk.StringVar(value=get_output_dir(DIR_LOGCAT))
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
        
        # 操作按钮：两行用 grid 对齐，上下列对齐、间距一致
        btn_container = ttk.Frame(control_frame)
        btn_container.pack(fill="x", padx=5, pady=5)
        # 第一行：放开打印、停止打印、实时logcat（在停止打印右边，打开文件夹上方）
        self.enable_debug_button = ttk.Button(btn_container, text="放开打印",
                                            command=self.enable_logcat_debug,
                                            style="Small.TButton", width=8)
        self.enable_debug_button.grid(row=0, column=0, padx=(0, 6), pady=(0, 4), sticky="w")
        self.disable_debug_button = ttk.Button(btn_container, text="停止打印",
                                             command=self.disable_logcat_debug,
                                             style="Small.TButton", width=8)
        self.disable_debug_button.grid(row=0, column=1, padx=(0, 6), pady=(0, 4), sticky="w")
        self.disable_debug_button.config(state="disabled")
        open_viewer_button = ttk.Button(
            btn_container,
            text="实时logcat",
            command=self.open_logcat_viewer_window,
            style="Small.TButton",
            width=11,
        )
        open_viewer_button.grid(row=0, column=2, padx=(0, 6), pady=(0, 4), sticky="w")

        # 第二行：开始抓取、停止抓取、打开文件夹
        self.start_capture_button = ttk.Button(btn_container, text="开始抓取",
                                             command=self.start_logcat_capture,
                                             style="Small.TButton", width=8)
        self.start_capture_button.grid(row=1, column=0, padx=(0, 6), pady=(0, 0), sticky="w")
        self.stop_capture_button = ttk.Button(btn_container, text="停止抓取",
                                            command=self.stop_logcat_capture,
                                            style="Small.TButton", width=8)
        self.stop_capture_button.grid(row=1, column=1, padx=(0, 6), pady=(0, 0), sticky="w")
        self.stop_capture_button.config(state="disabled")
        open_folder_button = ttk.Button(
            btn_container,
            text="打开文件夹",
            command=self.open_logcat_folder,
            style="Small.TButton",
            width=9,
        )
        open_folder_button.grid(row=1, column=2, padx=(0, 0), pady=(0, 0), sticky="w")

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

    def open_logcat_viewer_window(self):
        """打开独立弹窗「日志查看器 (Logcat Viewer)」"""
        root = getattr(self, "root", None) or getattr(self, "parent", None)
        if root and root.winfo_exists():
            LogcatViewerWindow(root, self)

    def setup_hotword_monitor_tab(self, parent):
        """唤醒监测：过滤 logcat 中 Detected hotword，统计唤醒次数，支持重置"""
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        # 说明
        desc = ttk.Label(
            frame,
            text="监测设备 logcat：\nB款仅监测「Detected hotword」每条约 1 次；\nA款仅监测「LIBAS_HOTWORD_DETECTION_RECEIVED」；\n开始监测前会清空设备 log 缓冲，只统计本次唤醒。",
            style="Muted.TLabel",
            justify=tk.LEFT,
        )
        desc.pack(anchor="w", pady=(0, 10))
        
        # 唤醒次数显示
        count_frame = ttk.LabelFrame(frame, text="唤醒次数")
        count_frame.pack(fill="x", pady=5)
        self.hotword_count_var = tk.StringVar(value="0")
        self.hotword_count_label = ttk.Label(count_frame, textvariable=self.hotword_count_var, font=("Arial", 24))
        self.hotword_count_label.pack(pady=15, padx=20)
        
        # 按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=10)
        self.hotword_start_btn = ttk.Button(btn_frame, text="开始监测", command=self.start_hotword_monitor)
        self.hotword_start_btn.pack(side="left", padx=5)
        self.hotword_stop_btn = ttk.Button(btn_frame, text="停止监测", command=self.stop_hotword_monitor, state="disabled")
        self.hotword_stop_btn.pack(side="left", padx=5)
        ttk.Button(btn_frame, text="重置计数", command=self.reset_hotword_count).pack(side="left", padx=5)
        
        # 可选：唤醒后发送系统返回键（相当于遥控器返回键）
        self.hotword_send_back_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="唤醒后发送返回键（勾选后，每次检测到唤醒会向设备发送 KEYCODE_BACK）", variable=self.hotword_send_back_var).pack(anchor="w", pady=(5, 0))
        
        # 最近唤醒日志（只读）
        log_frame = ttk.LabelFrame(frame, text="最近唤醒日志（B款 Detected hotword / A款 LIBAS_HOTWORD_DETECTION_RECEIVED）")
        log_frame.pack(fill="both", expand=True, pady=5)
        self.hotword_log_text = tk.Text(log_frame, height=12, font=("Consolas", 9), state="disabled")
        vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.hotword_log_text.yview)
        self.hotword_log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.hotword_log_text.pack(side="left", fill="both", expand=True)
        
        # 进程/线程/计数（用于监测逻辑）
        self.hotword_count = 0
        self.hotword_monitor_process = None
        self.hotword_monitor_stop = False
        self.hotword_monitor_thread = None
        self._hotword_log_max_lines = 200
        self._hotword_last_detected_time = 0.0  # 用于同一唤醒只计一次（去重时间窗）
        self._hotword_debounce_seconds = 1.5   # 此时间内只计 1 次

    def start_hotword_monitor(self):
        """开始唤醒监测：先清空设备 log 缓冲再拉 logcat，只统计「Detected hotword」一次/唤醒"""
        if not self.check_device_selected():
            # 明确提示用户，避免“点了没反应”的困惑
            root = getattr(self, "root", None)
            if root and root.winfo_exists():
                root.after(0, lambda: messagebox.showwarning(
                    "无法开始监测",
                    "请先在顶部选择设备并确保设备已通过 USB 连接且状态为「设备 xxx 在线」。"
                ))
            return
        device_id = (getattr(self, "selected_device", None) or "").strip() or (self.device_var.get() or "").strip()
        if not device_id:
            messagebox.showwarning("无法开始监测", "未获取到设备号，请重新选择设备后重试。")
            return
        self.hotword_monitor_stop = False
        self._hotword_ui_buffer = []
        self._hotword_ui_flush_scheduled = False
        self.hotword_count = 0
        self._hotword_last_detected_time = 0.0
        self._hotword_monitor_start_time = time.time()  # 启动后前 1 秒内忽略，避免旧缓冲被计入
        if hasattr(self, "hotword_count_var"):
            self.hotword_count_var.set("0")
        if hasattr(self, "hotword_log_text") and self.hotword_log_text.winfo_exists():
            self.hotword_log_text.config(state="normal")
            self.hotword_log_text.delete("1.0", "end")
            self.hotword_log_text.config(state="disabled")
        try:
            clear_argv = ["adb", "-s", device_id, "logcat", "-c"]
            subprocess.run(clear_argv, shell=False, capture_output=True, timeout=5)
            argv = ["adb", "-s", device_id, "logcat", "-v", "threadtime", "*:I"]
            # 与日志查看器一致：Windows 下用 shell + CREATE_NO_WINDOW 启动，避免 adb 子进程被立即关闭（当时 patch 里只有 LogcatViewer 做了该处理，唤醒监测未做，会导致“没有任何反应”）
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
                "encoding": "utf-8",
                "errors": "replace",
            }
            if platform.system() == "Windows":
                cmd_str = subprocess.list2cmdline(argv)
                kwargs["shell"] = True
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                self.hotword_monitor_process = subprocess.Popen(cmd_str, **kwargs)
            else:
                kwargs["shell"] = False
                self.hotword_monitor_process = subprocess.Popen(argv, **kwargs)
            time.sleep(0.3)
            if self.hotword_monitor_process.poll() is not None:
                out = ""
                try:
                    if self.hotword_monitor_process.stdout:
                        out = (self.hotword_monitor_process.stdout.read() or "").strip()
                except Exception:
                    pass
                self.hotword_monitor_process = None
                messagebox.showerror("错误", out or "adb logcat 进程已退出，请检查设备连接与 adb")
                return
            self.hotword_start_btn.config(state="disabled")
            self.hotword_stop_btn.config(state="normal")
            if hasattr(self, "status_var"):
                self.status_var.set("唤醒监测已启动，请对着设备说唤醒词")
            self.hotword_monitor_thread = threading.Thread(target=self._read_hotword_logcat, daemon=True)
            self.hotword_monitor_thread.start()
        except Exception as e:
            messagebox.showerror("错误", f"启动唤醒监测失败: {str(e)}")

    def stop_hotword_monitor(self):
        """停止唤醒监测"""
        self.hotword_monitor_stop = True
        if self.hotword_monitor_process and self.hotword_monitor_process.poll() is None:
            try:
                if platform.system() == "Windows":
                    subprocess.run(f"taskkill /F /T /PID {self.hotword_monitor_process.pid}", shell=True)
                else:
                    self.hotword_monitor_process.terminate()
            except Exception:
                pass
            self.hotword_monitor_process = None
        if hasattr(self, "status_var"):
            self.status_var.set("就绪")
        if hasattr(self, "hotword_start_btn") and self.hotword_start_btn.winfo_exists():
            self.hotword_start_btn.config(state="normal")
        if hasattr(self, "hotword_stop_btn") and self.hotword_stop_btn.winfo_exists():
            self.hotword_stop_btn.config(state="disabled")

    def reset_hotword_count(self):
        """重置唤醒次数为 0"""
        self.hotword_count = 0
        if hasattr(self, "hotword_count_var"):
            self.hotword_count_var.set("0")
        if hasattr(self, "hotword_log_text") and self.hotword_log_text.winfo_exists():
            self.hotword_log_text.config(state="normal")
            self.hotword_log_text.delete("1.0", "end")
            self.hotword_log_text.config(state="disabled")

    def _read_hotword_logcat(self):
        """B款: 仅监测 Detected hotword，每条计 1 次（时间窗去重）；A款: 仅监测 LIBAS_HOTWORD_DETECTION_RECEIVED，每条计 0.5（每唤醒 2 条，显示数量除以 2）"""
        keyword_b = "Detected hotword"
        keyword_a = "LIBAS_HOTWORD_DETECTION_RECEIVED"
        root = getattr(self, "root", None) or getattr(self, "parent", None)

        def _ui_append(display_count, line_text):
            """线程安全：缓冲计数与日志，批量刷新（约 100ms），避免卡顿"""
            try:
                buf = getattr(self, "_hotword_ui_buffer", None)
                if buf is None:
                    self._hotword_ui_buffer = []
                    buf = self._hotword_ui_buffer
                buf.append((display_count, line_text))
            except Exception:
                return
            if getattr(self, "_hotword_ui_flush_scheduled", False):
                return
            self._hotword_ui_flush_scheduled = True

            def _flush():
                try:
                    buf = getattr(self, "_hotword_ui_buffer", None) or []
                    self._hotword_ui_buffer = []
                    self._hotword_ui_flush_scheduled = False
                    if not buf or not root or not root.winfo_exists():
                        return
                    last_count = buf[-1][0] if buf else 0
                    if hasattr(self, "hotword_count_var"):
                        self.hotword_count_var.set(str(int(round(last_count))))
                    if hasattr(self, "hotword_log_text") and self.hotword_log_text.winfo_exists():
                        self.hotword_log_text.config(state="normal")
                        for _, s in buf:
                            self.hotword_log_text.insert("end", s + "\n")
                        n = int(self.hotword_log_text.index("end-1c").split(".")[0])
                        if n > getattr(self, "_hotword_log_max_lines", 200):
                            self.hotword_log_text.delete("1.0", "2.0")
                        self.hotword_log_text.see("end")
                        self.hotword_log_text.config(state="disabled")
                except Exception:
                    try:
                        self._hotword_ui_flush_scheduled = False
                    except Exception:
                        pass

            root.after(100, _flush)

        try:
            if not self.hotword_monitor_process or not getattr(self.hotword_monitor_process, "stdout", None):
                if root and root.winfo_exists():
                    root.after(0, lambda: self._hotword_monitor_ended())
                return
            # 与雷达一致：用 for line in process.stdout 实时迭代，不用 iter(readline, "")
            for line in self.hotword_monitor_process.stdout:
                if self.hotword_monitor_stop:
                    break
                if not self.hotword_monitor_process or self.hotword_monitor_process.poll() is not None:
                    break
                if not line:
                    continue
                is_b = keyword_b in line
                is_a = keyword_a in line
                if not is_b and not is_a:
                    continue
                now = time.time()
                if now - getattr(self, "_hotword_monitor_start_time", 0) < 1.0:
                    continue
                if is_b:
                    # B款: 每条计 1，时间窗去重
                    debounce = getattr(self, "_hotword_debounce_seconds", 1.5)
                    if now - getattr(self, "_hotword_last_detected_time", 0) < debounce:
                        continue
                    self._hotword_last_detected_time = now
                    self.hotword_count += 1.0
                else:
                    # A款: 每条计 0.5（每次唤醒 2 条，显示数量除以 2）
                    self.hotword_count += 0.5
                _ui_append(self.hotword_count, line.strip())
                # 可选：唤醒后发送系统返回键
                if getattr(self, "hotword_send_back_var", None) and self.hotword_send_back_var.get():
                    try:
                        cmd = getattr(self, "get_adb_command", lambda c: f"adb {c}")("shell input keyevent KEYCODE_BACK")
                        subprocess.run(cmd, shell=True, timeout=3, capture_output=True)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if not self.hotword_monitor_stop and root and root.winfo_exists():
                root.after(0, self._hotword_monitor_ended)
            self.hotword_monitor_process = None

    def _hotword_monitor_ended(self):
        """监测进程已结束：仅恢复 UI"""
        if hasattr(self, "status_var"):
            self.status_var.set("就绪")
        if hasattr(self, "hotword_start_btn") and self.hotword_start_btn.winfo_exists():
            self.hotword_start_btn.config(state="normal")
        if hasattr(self, "hotword_stop_btn") and self.hotword_stop_btn.winfo_exists():
            self.hotword_stop_btn.config(state="disabled")
        self.hotword_monitor_process = None

    def setup_system_cmd_tab(self, parent):
        """系统指令（独立子标签页）：整体可滚动，避免被固定界面遮住"""
        # 外层：Canvas + 垂直滚动条，使整个系统指令界面可滚动
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        self._syscmd_main_canvas = tk.Canvas(container, highlightthickness=0)
        syscmd_main_vsb = ttk.Scrollbar(container, orient="vertical", command=self._syscmd_main_canvas.yview)
        inner = ttk.Frame(self._syscmd_main_canvas, padding=10)
        inner.bind("<Configure>", lambda e: self._syscmd_main_canvas.configure(scrollregion=self._syscmd_main_canvas.bbox("all")))
        self._syscmd_main_canvas_window = self._syscmd_main_canvas.create_window((0, 0), window=inner, anchor="nw")
        self._syscmd_main_canvas.configure(yscrollcommand=syscmd_main_vsb.set)

        def _on_syscmd_canvas_configure(event):
            self._syscmd_main_canvas.itemconfig(self._syscmd_main_canvas_window, width=event.width)

        self._syscmd_main_canvas.bind("<Configure>", _on_syscmd_canvas_configure)
        syscmd_main_vsb.pack(side="right", fill="y")
        self._syscmd_main_canvas.pack(side="left", fill="both", expand=True)
        # 鼠标在系统指令面板上时滚轮可滚动
        def _on_mousewheel(event):
            self._syscmd_main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._syscmd_main_canvas.bind("<MouseWheel>", _on_mousewheel)
        # Linux 使用 Button-4/5
        self._syscmd_main_canvas.bind("<Button-4>", lambda e: self._syscmd_main_canvas.yview_scroll(-3, "units"))
        self._syscmd_main_canvas.bind("<Button-5>", lambda e: self._syscmd_main_canvas.yview_scroll(3, "units"))
        self._setup_system_cmd_panel(inner)
        # 内层及所有子控件也绑定滚轮，鼠标在面板任意位置滚轮即可滚动
        self._bind_mousewheel_to_canvas(inner, self._syscmd_main_canvas)

    def _setup_system_cmd_panel(self, parent):
        """系统指令面板内容（预设指令 + 自定义指令），置于可滚动容器内"""
        lf = ttk.LabelFrame(parent, text="系统指令")
        lf.pack(fill="x", padx=5, pady=5)

        tip = ttk.Label(lf, text="点击按钮获取设备信息（弹窗支持 Ctrl+F 搜索/刷新/保存）", style="Muted.TLabel")
        tip.pack(anchor="w", padx=8, pady=(6, 6))

        btns = ttk.Frame(lf)
        btns.pack(fill="x", padx=8, pady=(0, 8))

        # 预设指令；cmd 为 None 表示打开设备解锁弹窗，否则为 adb/shell 指令
        commands = [
            ("dumpsys media.audio_policy", "dumpsys media.audio_policy"),
            ("dumpsys media.audio_flinger", "dumpsys media.audio_flinger"),
            ("dumpsys audio", "dumpsys audio"),
            ("tinymix", "tinymix"),
            ("getprop", "getprop"),
            ("getprop ro.build.fingerprint", "getprop ro.build.fingerprint"),
            ("dumpsys input", "dumpsys input"),
            ("Bootloader 解锁 + root/remount", None),
        ]

        for i, (label, cmd) in enumerate(commands):
            r, c = divmod(i, 1)
            if cmd is None:
                b = ttk.Button(btns, text=label, style="Small.TButton", command=self.open_device_unlock_window)
            else:
                b = ttk.Button(
                    btns,
                    text=label,
                    style="Small.TButton",
                    command=lambda _label=label, _cmd=cmd: self.open_system_cmd_window(_label, _cmd),
                )
            b.grid(row=r, column=c, sticky="ew", pady=4)
            btns.grid_columnconfigure(c, weight=1)

        # 自定义指令：放在预设指令与设备解锁之间，添加后立即可见
        custom_lf = ttk.LabelFrame(lf, text="自定义指令（可新增/删除）")
        custom_lf.pack(fill="x", padx=8, pady=(0, 8))

        if not hasattr(self, "_syscmd_custom_list") or self._syscmd_custom_list is None:
            self._syscmd_custom_list = []

        self._syscmd_custom_var = getattr(self, "_syscmd_custom_var", tk.StringVar())
        row1 = ttk.Frame(custom_lf)
        row1.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(row1, text="指令:").pack(side="left")
        entry = ttk.Entry(row1, textvariable=self._syscmd_custom_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 12))
        ttk.Button(row1, text="添加", style="Small.TButton", width=6, command=self._syscmd_add_custom).pack(side="left", padx=(0, 4))
        ttk.Button(row1, text="运行", style="Small.TButton", width=6, command=lambda: self._syscmd_run_custom((self._syscmd_custom_var.get() or "").strip())).pack(side="left", padx=(0, 4))

        # 已添加的指令：可滚动区域，按钮竖向排列，添加后立即可见
        if not hasattr(self, "_syscmd_custom_buttons"):
            self._syscmd_custom_buttons = []
        btns_lf = ttk.LabelFrame(custom_lf, text="已添加的指令（点击按钮直接运行）")
        btns_lf.pack(fill="x", padx=8, pady=(4, 4))
        # 固定高度 + 垂直滚动条，内层 Frame 放按钮
        self._syscmd_canvas = tk.Canvas(btns_lf, highlightthickness=0)
        syscmd_btn_scroll = ttk.Scrollbar(btns_lf, orient="vertical", command=self._syscmd_canvas.yview)
        self._syscmd_custom_btns_frame = ttk.Frame(self._syscmd_canvas)
        self._syscmd_custom_btns_frame.bind(
            "<Configure>",
            lambda e: self._syscmd_canvas.configure(scrollregion=self._syscmd_canvas.bbox("all")),
        )
        self._syscmd_canvas_window = self._syscmd_canvas.create_window((0, 0), window=self._syscmd_custom_btns_frame, anchor="nw")
        self._syscmd_canvas.configure(yscrollcommand=syscmd_btn_scroll.set)

        def _on_canvas_configure(event):
            self._syscmd_canvas.itemconfig(self._syscmd_canvas_window, width=event.width)

        self._syscmd_canvas.bind("<Configure>", _on_canvas_configure)
        syscmd_btn_scroll.pack(side="right", fill="y")
        self._syscmd_canvas.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self._syscmd_canvas.configure(height=88)
        self._syscmd_empty_lbl = ttk.Label(self._syscmd_custom_btns_frame, text="（添加后此处会显示指令按钮）", style="Muted.TLabel")
        self._syscmd_empty_lbl.pack(anchor="w")
        for cmd in self._syscmd_custom_list:
            self._syscmd_empty_lbl.pack_forget()
            self._syscmd_add_custom_button(cmd)
        if self._syscmd_custom_list:
            self._syscmd_empty_lbl.pack_forget()

        list_lf = ttk.LabelFrame(custom_lf, text="已添加的指令列表（选中后点「运行选中」或「删除选中」）")
        list_lf.pack(fill="x", padx=8, pady=(4, 4))
        list_inner = ttk.Frame(list_lf)
        list_inner.pack(fill="x", padx=4, pady=4)
        self._syscmd_listbox = tk.Listbox(list_inner, height=4, font=("Consolas", 9), selectmode="single")
        syscmd_scroll = ttk.Scrollbar(list_inner, orient="vertical", command=self._syscmd_listbox.yview)
        self._syscmd_listbox.configure(yscrollcommand=syscmd_scroll.set)
        syscmd_scroll.pack(side="right", fill="y")
        self._syscmd_listbox.pack(side="left", fill="both", expand=True)
        for cmd in self._syscmd_custom_list:
            self._syscmd_listbox.insert(tk.END, cmd)

        btn_row = ttk.Frame(custom_lf)
        btn_row.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Button(btn_row, text="运行选中", style="Small.TButton", width=8, command=self._syscmd_run_selected).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="删除选中", style="Small.TButton", width=8, command=self._syscmd_delete_selected).pack(side="left", padx=(0, 6))

    def _syscmd_add_custom_button(self, cmd: str):
        """为一条自定义指令在可滚动区内创建一个可点击按钮"""
        frame = getattr(self, "_syscmd_custom_btns_frame", None)
        if frame is None or not frame.winfo_exists():
            return
        btn = ttk.Button(
            frame,
            text=(cmd[:48] + "…") if len(cmd) > 48 else cmd,
            style="Small.TButton",
            command=lambda _c=cmd: self._syscmd_run_one(_c),
        )
        btn.pack(side="top", fill="x", padx=2, pady=2)
        if not hasattr(self, "_syscmd_custom_buttons"):
            self._syscmd_custom_buttons = []
        self._syscmd_custom_buttons.append(btn)
        canvas = getattr(self, "_syscmd_canvas", None)
        if canvas and canvas.winfo_exists():
            try:
                canvas.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

    def _syscmd_add_custom(self):
        """将当前输入框内容添加到自定义指令列表，并同步到 Listbox 与按钮区"""
        try:
            cmd = (self._syscmd_custom_var.get() or "").strip()
        except Exception:
            cmd = ""
        if not cmd:
            messagebox.showinfo("提示", "请输入要添加的指令内容")
            return
        if not hasattr(self, "_syscmd_custom_list"):
            self._syscmd_custom_list = []
        self._syscmd_custom_list.append(cmd)
        self._syscmd_custom_var.set("")
        lb = getattr(self, "_syscmd_listbox", None)
        if lb is not None and lb.winfo_exists():
            lb.insert(tk.END, cmd)
            lb.see(tk.END)
        empty_lbl = getattr(self, "_syscmd_empty_lbl", None)
        if empty_lbl and empty_lbl.winfo_exists():
            empty_lbl.pack_forget()
        self._syscmd_add_custom_button(cmd)
        try:
            c = getattr(self, "_syscmd_canvas", None)
            if c and c.winfo_exists():
                c.yview_moveto(1.0)
            root = getattr(self, "root", None)
            if root and root.winfo_exists():
                root.update_idletasks()
        except Exception:
            pass

    def _syscmd_run_selected(self):
        """运行列表中选中的一条指令（直接执行不弹窗）"""
        lb = getattr(self, "_syscmd_listbox", None)
        if lb is None or not lb.winfo_exists():
            messagebox.showinfo("提示", "请先在列表中选中一条指令")
            return
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中一条指令")
            return
        idx = int(sel[0])
        lst = getattr(self, "_syscmd_custom_list", None) or []
        if idx < len(lst):
            self._syscmd_run_one(lst[idx])

    def _syscmd_delete_selected(self):
        """删除列表中选中的一条指令（同时移除对应按钮）"""
        lb = getattr(self, "_syscmd_listbox", None)
        if lb is None or not lb.winfo_exists():
            messagebox.showinfo("提示", "请先在列表中选中要删除的指令")
            return
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中要删除的指令")
            return
        idx = int(sel[0])
        if not hasattr(self, "_syscmd_custom_list") or idx >= len(self._syscmd_custom_list):
            return
        self._syscmd_custom_list.pop(idx)
        lb.delete(idx)
        btns = getattr(self, "_syscmd_custom_buttons", None)
        if btns and idx < len(btns):
            w = btns.pop(idx)
            if w.winfo_exists():
                w.destroy()
        if not (getattr(self, "_syscmd_custom_list", None) or []):
            empty_lbl = getattr(self, "_syscmd_empty_lbl", None)
            if empty_lbl and empty_lbl.winfo_exists():
                empty_lbl.pack(anchor="w")

    def _syscmd_run_custom(self, cmd: str):
        """运行输入框中的指令，直接执行不弹窗"""
        cmd = (cmd or "").strip()
        if not cmd:
            messagebox.showinfo("提示", "请输入要执行的指令")
            return
        self._syscmd_run_one(cmd)

    def _syscmd_run_one(self, cmd: str):
        """在设备上执行一条指令，后台运行不弹窗（与快捷应用「运行」一致）"""
        cmd = (cmd or "").strip()
        if not cmd:
            return
        if hasattr(self, "check_device_selected") and not self.check_device_selected():
            return
        serial = (getattr(self, "device_var", None) and self.device_var.get() or "").strip()
        if not serial:
            messagebox.showerror("错误", "请先选择设备")
            return

        def _run():
            try:
                subprocess.run(
                    ["adb", "-s", serial, "shell"] + shlex.split(cmd),
                    capture_output=True,
                    text=True,
                )
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("执行失败", str(e)))
                return
            self.root.after(0, lambda: messagebox.showinfo("已执行", f"指令已发送：{cmd[:50]}{'...' if len(cmd) > 50 else ''}"))

        threading.Thread(target=_run, daemon=True).start()

    def open_system_cmd_window(self, title: str, shell_cmd: str):
        """打开系统指令结果弹窗并执行"""
        shell_cmd = (shell_cmd or "").strip()
        if not shell_cmd:
            messagebox.showerror("错误", "请输入要执行的系统指令（例如：dumpsys media.audio）")
            return

        # 设备检查：复用现有逻辑
        if hasattr(self, "check_device_selected") and not self.check_device_selected():
            return

        serial = ""
        try:
            serial = (self.device_var.get() or "").strip()
        except Exception:
            serial = ""
        if not serial:
            messagebox.showerror("错误", "请先选择设备")
            return

        win = tk.Toplevel(self.root)
        win.title(f"{title} 结果")
        win.geometry("980x720")
        # 与主窗口一致的图标（声测大师 logo）
        try:
            base_dir = self._get_runtime_base_dir()
            for path in [
                os.path.join(base_dir, "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(getattr(sys, "_MEIPASS", ""), "logo", "AcouTest.png") if getattr(sys, "frozen", False) else None,
            ]:
                if path and os.path.exists(path):
                    try:
                        icon_img = tk.PhotoImage(file=path)
                        win.iconphoto(True, icon_img)
                        win._icon_image = icon_img
                        break
                    except Exception:
                        pass
            if platform.system() == "Windows":
                for ico_path in [os.path.join(base_dir, "logo", "AcouTest.ico"), os.path.join("logo", "AcouTest.ico")]:
                    if ico_path and os.path.exists(ico_path):
                        try:
                            win.iconbitmap(ico_path)
                            break
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            win.bind("<Enter>", lambda e: win.focus_set(), add=True)
        except Exception:
            pass

        topbar = ttk.Frame(win)
        topbar.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(topbar, text=f"命令：{shell_cmd}", style="Muted.TLabel").pack(side="left", fill="x", expand=True)

        # 控件：刷新/保存
        btn_refresh = ttk.Button(topbar, text="刷新", style="Small.TButton")
        btn_refresh.pack(side="right", padx=(6, 0))
        btn_save = ttk.Button(topbar, text="保存", style="Small.TButton")
        btn_save.pack(side="right", padx=(6, 0))

        # 搜索栏（Ctrl+F 呼出）
        findbar = ttk.Frame(win)
        findbar.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(findbar, text="查找：").pack(side="left")
        find_var = tk.StringVar()
        find_entry = ttk.Entry(findbar, textvariable=find_var, width=30)
        find_entry.pack(side="left", padx=(6, 6))
        btn_find_next = ttk.Button(findbar, text="下一个", style="Small.TButton", width=7)
        btn_find_next.pack(side="left")
        hint = ttk.Label(findbar, text="（支持 Ctrl+F 搜索内容）", style="Muted.TLabel")
        hint.pack(side="left", padx=(8, 0))

        # 文本区
        text_frame = ttk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        txt = tk.Text(text_frame, wrap="none", font=("Consolas", 9))
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)

        txt.tag_configure("hit", background="#ffe58a")
        txt.tag_configure("hit_cur", background="#ffd666")

        state = {"last_output": "", "last_cmd": shell_cmd, "last_title": title, "cur_index": "1.0"}

        def _set_text(content: str):
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", content or "")
            txt.config(state="disabled")
            state["last_output"] = content or ""
            state["cur_index"] = "1.0"

        def _run_cmd_async():
            btn_refresh.config(state="disabled")
            btn_save.config(state="disabled")
            _set_text("正在执行...\n")

            def worker():
                try:
                    # shell=False：避免 Windows 下 %xx/%s 被 cmd.exe 展开导致 input/text 类命令异常
                    result = subprocess.run(
                        ["adb", "-s", serial, "shell"] + shlex.split(state["last_cmd"]),
                        capture_output=True,
                        text=True,
                    )
                    out = (result.stdout or "")
                    err = (result.stderr or "")
                    if result.returncode != 0 and err:
                        out = out + ("\n\n[stderr]\n" + err)
                    elif err:
                        out = out + ("\n\n[stderr]\n" + err)
                except Exception as e:
                    out = f"执行失败：{type(e).__name__}: {e}"

                self.root.after(0, lambda: (_set_text(out), btn_refresh.config(state="normal"), btn_save.config(state="normal")))

            threading.Thread(target=worker, daemon=True).start()

        def _highlight_all(needle: str):
            txt.config(state="normal")
            txt.tag_remove("hit", "1.0", "end")
            txt.tag_remove("hit_cur", "1.0", "end")
            if not needle:
                txt.config(state="disabled")
                return
            start = "1.0"
            while True:
                pos = txt.search(needle, start, stopindex="end", nocase=True)
                if not pos:
                    break
                end = f"{pos}+{len(needle)}c"
                txt.tag_add("hit", pos, end)
                start = end
            txt.config(state="disabled")

        def _find_next():
            needle = (find_var.get() or "").strip()
            if not needle:
                return
            _highlight_all(needle)
            txt.config(state="normal")
            pos = txt.search(needle, state["cur_index"], stopindex="end", nocase=True)
            if not pos:
                pos = txt.search(needle, "1.0", stopindex="end", nocase=True)
            if pos:
                end = f"{pos}+{len(needle)}c"
                txt.tag_remove("hit_cur", "1.0", "end")
                txt.tag_add("hit_cur", pos, end)
                txt.see(pos)
                state["cur_index"] = end
            txt.config(state="disabled")

        def _on_ctrl_f(_e=None):
            try:
                find_entry.focus_set()
                find_entry.selection_range(0, "end")
            except Exception:
                pass
            return "break"

        win.bind("<Control-f>", _on_ctrl_f, add=True)
        win.bind("<Control-F>", _on_ctrl_f, add=True)
        btn_find_next.config(command=_find_next)
        find_entry.bind("<Return>", lambda e: (_find_next(), "break"), add=True)
        find_entry.bind("<KeyRelease>", lambda e: _highlight_all((find_var.get() or "").strip()), add=True)

        def _save():
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"{state['last_title']}_{ts}.txt".replace(" ", "_")
            path = filedialog.asksaveasfilename(
                title="保存输出",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text", "*.txt"), ("All", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(state["last_output"] or "")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{type(e).__name__}: {e}")

        btn_refresh.config(command=_run_cmd_async)
        btn_save.config(command=_save)

        # 运行一次
        _run_cmd_async()

    def open_device_unlock_window(self):
        """
        设备解锁序列（按用户给定步骤）：
        1) adb reboot bootloader
        2) fastboot flashing unlock  (通常需要在设备端确认，且可能清除数据)
        3) fastboot reboot
        4) adb root  & adb remount
        5) adb reboot
        """
        # 设备检查：复用现有逻辑
        if hasattr(self, "check_device_selected") and not self.check_device_selected():
            return

        try:
            serial = (self.device_var.get() or "").strip()
        except Exception:
            serial = ""
        if not serial:
            messagebox.showerror("错误", "请先选择设备")
            return

        win = tk.Toplevel(self.root)
        win.title("设备解锁（Bootloader）/root&remount")
        win.geometry("980x720")
        try:
            base_dir = self._get_runtime_base_dir()
            for path in [
                os.path.join(base_dir, "logo", "AcouTest.png"),
                os.path.join("logo", "AcouTest.png"),
                os.path.join(getattr(sys, "_MEIPASS", ""), "logo", "AcouTest.png") if getattr(sys, "frozen", False) else None,
            ]:
                if path and os.path.exists(path):
                    try:
                        icon_img = tk.PhotoImage(file=path)
                        win.iconphoto(True, icon_img)
                        win._icon_image = icon_img
                        break
                    except Exception:
                        pass
            if platform.system() == "Windows":
                for ico_path in [os.path.join(base_dir, "logo", "AcouTest.ico"), os.path.join("logo", "AcouTest.ico")]:
                    if ico_path and os.path.exists(ico_path):
                        try:
                            win.iconbitmap(ico_path)
                            break
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            win.bind("<Enter>", lambda e: win.focus_set(), add=True)
        except Exception:
            pass

        header = ttk.LabelFrame(win, text="重要提示")
        header.pack(fill="x", padx=10, pady=(10, 8))
        warn = (
            "此操作通常会触发【解锁 Bootloader】，很多设备会【清除全部用户数据】。\n"
            "并且 fastboot flashing unlock 需要你在设备端确认。\n"
            "确认你已经备份数据，并理解风险后再执行。"
        )
        ttk.Label(header, text=warn, foreground="#b00020").pack(anchor="w", padx=10, pady=8)

        steps = ttk.LabelFrame(win, text="将依次执行的命令")
        steps.pack(fill="x", padx=10, pady=(0, 8))
        cmd_lines = [
            "adb reboot bootloader",
            "fastboot flashing unlock",
            "fastboot reboot",
            "adb root",
            "adb remount",
            "adb reboot",
        ]
        ttk.Label(steps, text="\n".join(cmd_lines), style="Muted.TLabel").pack(anchor="w", padx=10, pady=8)

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=(0, 8))
        status_var = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=status_var).pack(side="left")
        btn_run = ttk.Button(bar, text="一键执行", style="Small.TButton")
        btn_stop = ttk.Button(bar, text="停止", style="Small.TButton")
        btn_save = ttk.Button(bar, text="保存日志", style="Small.TButton")
        btn_save.pack(side="right")
        btn_stop.pack(side="right", padx=(6, 0))
        btn_run.pack(side="right", padx=(6, 0))

        text_frame = ttk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        txt = tk.Text(text_frame, wrap="none", font=("Consolas", 9))
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)

        stop_event = threading.Event()
        state = {"log": ""}  # 保存最新日志用于保存

        def _append(s: str):
            state["log"] += s
            txt.config(state="normal")
            txt.insert("end", s)
            txt.see("end")
            txt.config(state="disabled")

        def _run_proc(argv, wait_label: str):
            """可中断执行一个进程，返回 (returncode, stdout, stderr)"""
            status_var.set(wait_label)
            _append(f"\n$ {' '.join(argv)}\n")
            try:
                p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            except Exception as e:
                return 127, "", f"{type(e).__name__}: {e}"

            out_chunks = []
            err_chunks = []
            while True:
                if stop_event.is_set():
                    try:
                        p.terminate()
                    except Exception:
                        pass
                    return 130, "".join(out_chunks), "".join(err_chunks) + "\n[stopped]\n"
                try:
                    o, e = p.communicate(timeout=0.2)
                    out_chunks.append(o or "")
                    err_chunks.append(e or "")
                    break
                except subprocess.TimeoutExpired:
                    continue
                except Exception as ex:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                    return 1, "".join(out_chunks), "".join(err_chunks) + f"\n[{type(ex).__name__}: {ex}]\n"

            return p.returncode, "".join(out_chunks), "".join(err_chunks)

        def _wait_fastboot(timeout_s=60):
            """等待设备进入 fastboot"""
            start = time.time()
            while time.time() - start < timeout_s and not stop_event.is_set():
                rc, out, err = _run_proc(["fastboot", "devices"], "等待 fastboot 设备...")
                if rc == 0 and out.strip():
                    return True
                time.sleep(1)
            return False

        def _wait_adb(timeout_s=120):
            """等待 adb 设备上线"""
            start = time.time()
            while time.time() - start < timeout_s and not stop_event.is_set():
                rc, out, err = _run_proc(["adb", "-s", serial, "get-state"], "等待 adb 设备上线...")
                if rc == 0 and ("device" in (out or "") or "device" in (err or "")):
                    return True
                time.sleep(1)
            return False

        def _worker():
            btn_run.config(state="disabled")
            btn_stop.config(state="normal")
            btn_save.config(state="disabled")
            stop_event.clear()
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.config(state="disabled")
            state["log"] = ""

            def done(msg: str):
                status_var.set(msg)
                btn_run.config(state="normal")
                btn_stop.config(state="disabled")
                btn_save.config(state="normal")

            if not messagebox.askyesno("危险操作确认", "该流程可能会清除设备数据，确定继续吗？"):
                done("已取消")
                return

            _append(f"开始时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # 1) adb reboot bootloader
            rc, out, err = _run_proc(["adb", "-s", serial, "reboot", "bootloader"], "重启到 bootloader...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")
            if rc != 0:
                done(f"失败：adb reboot bootloader（rc={rc}）")
                return

            # 等待 fastboot
            if not _wait_fastboot(timeout_s=90):
                done("失败：未检测到 fastboot 设备")
                return

            # 2) fastboot flashing unlock（需要用户在设备端确认）
            _append("\n注意：下一步需要在设备端确认解锁（可能清数据）。\n")
            rc, out, err = _run_proc(["fastboot", "flashing", "unlock"], "执行 fastboot flashing unlock（等待设备确认）...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")
            if rc != 0:
                done(f"失败：fastboot flashing unlock（rc={rc}）")
                return

            # 3) fastboot reboot
            rc, out, err = _run_proc(["fastboot", "reboot"], "fastboot reboot...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")
            if rc != 0:
                done(f"失败：fastboot reboot（rc={rc}）")
                return

            # 等待 adb
            if not _wait_adb(timeout_s=180):
                done("失败：设备未重新上线（adb）")
                return

            # 4) adb root & adb remount
            rc, out, err = _run_proc(["adb", "-s", serial, "root"], "adb root...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")

            rc, out, err = _run_proc(["adb", "-s", serial, "remount"], "adb remount...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")

            # 5) adb reboot
            rc, out, err = _run_proc(["adb", "-s", serial, "reboot"], "adb reboot...")
            _append(out)
            if err:
                _append("\n[stderr]\n" + err + "\n")

            done("完成（请等待设备重启）")

        def _start():
            threading.Thread(target=_worker, daemon=True).start()

        def _stop():
            stop_event.set()
            status_var.set("正在停止...")

        def _save():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"unlock_sequence_{ts}.txt"
            path = filedialog.asksaveasfilename(
                title="保存日志",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text", "*.txt"), ("All", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(state["log"] or "")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{type(e).__name__}: {e}")

        btn_run.config(command=_start)
        btn_stop.config(command=_stop)
        btn_save.config(command=_save)
        btn_stop.config(state="disabled")

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
        check.pack(side="left", padx=(0, 2))
        
        # 属性名标签 - 使用更小的字体，显示为"属性名 属性值"
        prop_label = ttk.Label(prop_frame, text=f"{prop_name} {prop_value}", font=("Arial", 9))
        prop_label.pack(side="left", padx=(0, 2), fill="x", expand=True)
        
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
        # width 为最小显示字符数；fill+expand 让框占满「设备:」与「刷新」之间的空间，长序列号可完整显示
        self.device_combobox = ttk.Combobox(select_frame, textvariable=self.device_var, width=28)
        self.device_combobox.pack(side="left", fill="x", expand=True, padx=5)
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
            self.remote_status_var.set("正在适配遥控器...")
            
            # 直接执行遥控器适配命令
            pairing_cmd = self.get_adb_command("shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS")
            result = subprocess.run(pairing_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"适配命令执行失败: {result.stderr}")
            
            # 简单更新状态
            self.remote_status_var.set("遥控器适配已启动")
            
        except Exception as e:
            error_msg = f"适配遥控器失败: {str(e)}"
            self.remote_status_var.set(error_msg)
            messagebox.showerror("错误", f"适配遥控器时出错:\n{str(e)}")
    
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
        
        # 固定布局：不使用滚动（按你的要求“固定居中就 OK”）
        self.remote_content_frame = ttk.Frame(remote_frame)
        self.remote_content_frame.pack(fill="x", expand=False)
        
        # 遥控器按键区域：整体居中（避免右侧留白过大）
        # 做法：三列布局 [弹性空白 | 内容 | 弹性空白]
        center_wrap = ttk.Frame(self.remote_content_frame)
        center_wrap.pack(fill="x", pady=10)
        center_wrap.grid_columnconfigure(0, weight=1)
        center_wrap.grid_columnconfigure(1, weight=0)
        center_wrap.grid_columnconfigure(2, weight=1)

        controls_frame = ttk.Frame(center_wrap)
        controls_frame.grid(row=0, column=1)

        # 1. 方向键和确认键部分（左侧）
        direction_frame = ttk.Frame(controls_frame)
        direction_frame.grid(row=0, column=0, padx=20, pady=0)
        
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
        
        # 设置按钮：直接打开系统设置（更符合你的使用习惯）
        # am start -n com.android.tv.settings/.MainSettings
        settings_button = ttk.Button(
            direction_frame,
            text="设置",
            command=lambda: self.launch_quick_action("系统设置", ("shell", "am start -n com.android.tv.settings/.MainSettings")),
            width=8,
            style="Remote.TButton",
        )
        settings_button.grid(row=3, column=1, pady=8)
        
        # 2. 音量和返回/配对按钮（右侧）
        volume_frame = ttk.Frame(controls_frame)
        volume_frame.grid(row=0, column=1, padx=20, pady=0)
        
        # 音量增加
        vol_up_button = ttk.Button(volume_frame, text="Vol+", 
                                  command=lambda: self.send_keycode("VOLUME_UP"), 
                                  width=8, style="Remote.TButton")
        vol_up_button.grid(row=0, column=0, padx=5, pady=5)
        
        # 返回按钮
        back_button = ttk.Button(volume_frame, text="返回", 
                                command=lambda: self.send_keycode("BACK"), 
                                width=8, style="Remote.TButton")
        back_button.grid(row=0, column=1, padx=5, pady=5)
        
        # 音量减少
        vol_down_button = ttk.Button(volume_frame, text="Vol-", 
                                    command=lambda: self.send_keycode("VOLUME_DOWN"), 
                                    width=8, style="Remote.TButton")
        vol_down_button.grid(row=1, column=0, padx=5, pady=5)
        
        # 配对遥控器
        pair_button = ttk.Button(volume_frame, text="配对遥控", 
                               command=self.adapt_remote_controller, 
                               width=8, style="Remote.TButton")
        pair_button.grid(row=1, column=1, padx=5, pady=5)

        # 3) 快捷应用：一键打开常用 App（YouTube/Netflix 等）
        # 说明：这里可能会被用户不断新增自定义项，如果不做滚动就会把后面的内容“顶出去”
        # 处理：仅让“快捷应用内容区”可滚动；上面的遥控器区域保持固定居中，不影响整体布局。
        quick_frame = ttk.LabelFrame(frame, text="快捷应用")
        quick_frame.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(
            quick_frame,
            text="点击按钮后会在设备上启动对应应用（前提：ADB已连接；部分应用需已安装）。",
            style="Muted.TLabel" if "Muted.TLabel" in ttk.Style().theme_names() else "TLabel",
        ).pack(anchor="w", padx=10, pady=(6, 4))

        quick_canvas_wrap = ttk.Frame(quick_frame)
        quick_canvas_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        quick_canvas = tk.Canvas(quick_canvas_wrap, height=220, highlightthickness=0, bd=0)
        quick_vsb = ttk.Scrollbar(quick_canvas_wrap, orient="vertical", command=quick_canvas.yview)
        quick_canvas.configure(yscrollcommand=quick_vsb.set)

        quick_canvas.pack(side="left", fill="both", expand=True)
        quick_vsb.pack(side="right", fill="y")

        quick_content = ttk.Frame(quick_canvas)
        quick_window_id = quick_canvas.create_window((0, 0), window=quick_content, anchor="nw")

        def _quick_on_content_configure(_e=None):
            try:
                quick_canvas.configure(scrollregion=quick_canvas.bbox("all"))
            except Exception:
                pass

        def _quick_on_canvas_configure(e):
            # 让内部内容宽度跟随 canvas，避免按钮区被压缩
            try:
                quick_canvas.itemconfigure(quick_window_id, width=e.width)
            except Exception:
                pass

        quick_content.bind("<Configure>", _quick_on_content_configure, add=True)
        quick_canvas.bind("<Configure>", _quick_on_canvas_configure, add=True)

        # 鼠标滚轮滚动（仅在鼠标位于该区域时生效）
        def _quick_on_mousewheel(e):
            try:
                # Windows: e.delta 通常为 120 的倍数
                quick_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
            return "break"

        def _bind_wheel(_e=None):
            try:
                quick_canvas.bind_all("<MouseWheel>", _quick_on_mousewheel, add=True)
            except Exception:
                pass

        def _unbind_wheel(_e=None):
            try:
                quick_canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass

        quick_canvas.bind("<Enter>", _bind_wheel, add=True)
        quick_canvas.bind("<Leave>", _unbind_wheel, add=True)

        apps_grid = ttk.Frame(quick_content)
        apps_grid.pack(fill="x", pady=(0, 6))

        # 内置快捷项（按你的要求：Prime Video 用 am start -n；）
        builtin_quick_apps = [
            ("YouTube", ("package", ["com.google.android.youtube.tv", "com.google.android.youtube"])),
            ("Netflix", ("package", ["com.netflix.ninja", "com.netflix.mediaclient"])),
            ("Prime Video", ("shell", "am start -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity")),
            ("HPlayer", ("activity", "com.nes.seihplayer/.ui.MainActivity")),
            ("Humming EQ", ("activity", "com.nes.sound/.component.activity.AllPanelActivity")),
        ]

        # 自定义快捷项：名称 + 打开指令，可新增/删除（仅运行期保存）
        if not hasattr(self, "_custom_quick_apps") or self._custom_quick_apps is None:
            self._custom_quick_apps = []  # list[dict{name:str, cmd:str}]

        custom_add_frame = ttk.LabelFrame(quick_content, text="自定义快捷（可新增/删除）")
        custom_add_frame.pack(fill="x", pady=(0, 8))

        custom_name_var = tk.StringVar()
        custom_cmd_var = tk.StringVar()

        row1 = ttk.Frame(custom_add_frame)
        row1.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(row1, text="名称:").pack(side="left")
        ttk.Entry(row1, textvariable=custom_name_var, width=16).pack(side="left", padx=(6, 12))
        ttk.Label(row1, text="打开指令:").pack(side="left")
        ttk.Entry(row1, textvariable=custom_cmd_var).pack(side="left", padx=(6, 6), fill="x", expand=True)

        custom_list_frame = ttk.Frame(custom_add_frame)
        custom_list_frame.pack(fill="x", padx=8, pady=(0, 6))

        def _delete_custom(index: int):
            try:
                self._custom_quick_apps.pop(index)
            except Exception:
                pass
            _render_quick_apps()

        def _render_quick_apps():
            # 清空按钮区
            for w in apps_grid.winfo_children():
                w.destroy()

            items = list(builtin_quick_apps)
            for item in self._custom_quick_apps:
                items.append((item["name"], ("shell", item["cmd"])))

            cols = 3
            for i, (label, spec) in enumerate(items):
                r, c = divmod(i, cols)
                btn = ttk.Button(
                    apps_grid,
                    text=label,
                    command=lambda _spec=spec, _label=label: self.launch_quick_action(_label, _spec),
                    style="Small.TButton",
                    width=14,
                )
                btn.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
                apps_grid.grid_columnconfigure(c, weight=1)

            # 刷新自定义列表
            for w in custom_list_frame.winfo_children():
                w.destroy()
            if not self._custom_quick_apps:
                ttk.Label(custom_list_frame, text="（暂无自定义快捷）", style="Muted.TLabel").pack(anchor="w")
            else:
                for idx, item in enumerate(list(self._custom_quick_apps)):
                    row = ttk.Frame(custom_list_frame)
                    row.pack(fill="x", pady=2)
                    ttk.Label(row, text=item["name"], width=14).pack(side="left")
                    ttk.Label(row, text=item["cmd"], style="Muted.TLabel").pack(side="left", fill="x", expand=True)
                    ttk.Button(row, text="删除", style="Small.TButton", width=6, command=lambda i=idx: _delete_custom(i)).pack(side="right")

        def _add_custom():
            name = (custom_name_var.get() or "").strip()
            cmd = (custom_cmd_var.get() or "").strip()
            if not name:
                messagebox.showerror("错误", "请输入快捷名称")
                return
            if not cmd:
                messagebox.showerror("错误", "请输入打开指令（例如：am start -n 包名/Activity）")
                return
            self._custom_quick_apps.append({"name": name, "cmd": cmd})
            custom_name_var.set("")
            custom_cmd_var.set("")
            _render_quick_apps()

        ttk.Button(row1, text="添加", style="Small.TButton", width=6, command=_add_custom).pack(side="right")

        hint = "提示：指令填写 adb shell 里的内容即可（会自动加 shell），例如：am start -n 包名/Activity"
        ttk.Label(custom_add_frame, text=hint, style="Muted.TLabel").pack(anchor="w", padx=8, pady=(0, 6))

        _render_quick_apps()
        
        # 状态显示
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="x", pady=5)
        
        status_label = ttk.Label(status_frame, textvariable=self.remote_status_var)
        status_label.pack(side="left")
        
        # 添加说明图示
        instruction_frame = ttk.LabelFrame(frame, text="配对说明")
        instruction_frame.pack(fill="both", expand=True, pady=10)
        
        instruction_text = tk.Text(instruction_frame, height=6, wrap="word")
        instruction_text.pack(fill="both", expand=True, padx=5, pady=5)
        instruction_text.insert("1.0", "配对步骤：\n"
                              + "1. 确保遥控器有电池并处于待配对状态\n"
                              + "2. 点击\"配对遥控\"按钮\n"
                              + "3. 长按遥控器上的\"返回\"和\"主页\"键直到LED闪烁\n"
                              + "4. 等待配对完成\n\n"
                              + "注意：如果遥控器已经配对，请先在设备设置中删除旧的配对记录")
        instruction_text.config(state="disabled")

    def setup_radar_tab(self, parent, handler=None):
        """设置雷达检查选项卡"""
        # handler 必须是“业务对象”（拥有 device_var / check_device_selected 等），不能是 Tk root
        if handler is None:
            handler = self
        
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
        self.setup_tty_check(tty_frame, handler)
        
        # 方法2: logcat监控
        logcat_frame = ttk.Frame(notebook, padding=10)
        notebook.add(logcat_frame, text="Logcat监控")
        self.setup_radar_logcat(logcat_frame, handler)
        
        # 方法3: AIEQ操作指南
        aieq_frame = ttk.Frame(notebook, padding=10)
        notebook.add(aieq_frame, text="AIEQ操作指南")
        self.setup_aieq_guide(aieq_frame)
        
        # 状态显示
        self.radar_status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.radar_status_var)
        status_label.pack(pady=5)

    def setup_tty_check(self, parent, handler):
        """TTY设备检查设置"""
        # 说明
        ttk.Label(parent, text="检查设备中是否存在ttyACM设备，存在则表明有雷达节点，是否工作还需要进一步检查").pack(pady=5)
        
        # 操作区域
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", pady=10)
        
        check_button = ttk.Button(action_frame, text="检查TTY设备", 
                                command=lambda: self.check_tty_devices(handler), width=15, style="Small.TButton")
        check_button.pack(side="left", padx=5)
        
        # 结果显示区域
        result_frame = ttk.LabelFrame(parent, text="检查结果")
        result_frame.pack(fill="both", expand=True, pady=10)
        
        # 创建文本框显示结果
        self.tty_result_text = tk.Text(result_frame, height=10, width=50)
        self.tty_result_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 初始状态
        self.tty_result_text.insert("1.0", "点击\"检查TTY设备\"按钮开始检查...\n")
        self.tty_result_text.config(state="disabled")

    def setup_radar_logcat(self, parent, handler):
        """Logcat监控设置"""
        # 说明部分减小高度
        ttk.Label(parent, text="监控logcat日志并过滤关键词（默认updateGain），遮挡雷达传感器时应该有数值变化", 
                 font=("Arial", 9)).pack(pady=2)
        
        # 指导信息框减小高度
        guide_frame = ttk.LabelFrame(parent, text="测试步骤")
        guide_frame.pack(fill="x", pady=5)
        
        guide_text = """    1. 点击"开始监控"按钮启动日志监控
        2. 用手或物体靠近/远离雷达传感器区域
        3. 观察下方日志显示，如有关键词相关值变化则表明雷达正常
        4. 完成测试后点击"停止监控"按钮"""
        
        ttk.Label(guide_frame, text=guide_text, justify="left", 
                 font=("Arial", 9)).pack(padx=10, pady=2)
        
        # 操作区域减小高度
        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", pady=5)

        # 关键词过滤（可修改，适配不同平台日志关键词）
        ttk.Label(action_frame, text="关键词:", font=("Arial", 9)).pack(side="left", padx=(5, 2))
        if not hasattr(self, "radar_keyword_var") or self.radar_keyword_var is None:
            self.radar_keyword_var = tk.StringVar(value="updateGain")
        keyword_entry = ttk.Entry(action_frame, textvariable=self.radar_keyword_var, width=16, font=("Arial", 9))
        keyword_entry.pack(side="left", padx=(0, 10))
        
        self.start_radar_monitor_button = ttk.Button(action_frame, text="开始监控", 
                                                   command=lambda: self.start_radar_monitor(handler), width=15,
                                                   style="Small.TButton")
        self.start_radar_monitor_button.pack(side="left", padx=5)
        
        self.stop_radar_monitor_button = ttk.Button(action_frame, text="停止监控", 
                                                  command=lambda: self.stop_radar_monitor(handler), width=15, 
                                                  state="disabled", style="Small.TButton")
        self.stop_radar_monitor_button.pack(side="left", padx=5)
        
        # 结果显示区域扩大高度比例
        result_frame = ttk.LabelFrame(parent, text="监控结果")
        result_frame.pack(fill="both", expand=True, pady=5)
        
        # 创建文本框显示结果
        self.radar_logcat_text = tk.Text(result_frame, height=14, width=50, font=("Arial", 9))
        self.radar_logcat_text.pack(fill="both", expand=True, padx=5, pady=5)
        
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
    
    def check_tty_devices(self, handler=None):
        """检查TTY设备"""
        # 使用传入的handler或默认的parent
        if handler is None:
            handler = self
        
        if not handler.check_device_selected():
            return
        
        self.radar_status_var.set("正在检查TTY设备...")
        
        # 启用文本编辑
        self.tty_result_text.config(state="normal")
        self.tty_result_text.delete("1.0", tk.END)
        self.tty_result_text.insert("1.0", "正在检查TTY设备...\n")
        
        try:
            # 直接构建adb命令，避免递归调用
            device_id = handler.device_var.get() if hasattr(handler, 'device_var') else ""
            if device_id:
                cmd = f"adb -s {device_id} shell ls -la /dev/tty*"
            else:
                cmd = "adb shell ls -la /dev/tty*"
            
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
                self.tty_result_text.insert(tk.END, "\n✅ 雷达传感器已连接，是否正常工作还需要先打开AIEQ操作打开Sweet Sport，然后再检查Logcat！\n")
                self.radar_status_var.set("检查完成: 已检测到雷达传感器")
            else:
                self.tty_result_text.insert(tk.END, "\n\n❌ 未检测到ttyACM设备，雷达传感器可能未连接或不工作\n")
                self.radar_status_var.set("检查完成: 未检测到雷达传感器")
        
        except Exception as e:
            self.tty_result_text.insert(tk.END, f"\n检查出错: {str(e)}\n")
            self.radar_status_var.set(f"检查出错: {str(e)}")
        
        # 禁用文本编辑
        self.tty_result_text.config(state="disabled")

    def start_radar_monitor(self, handler=None):
        """开始监控雷达传感器logcat"""
        if handler is None:
            handler = self
        
        if not handler.check_device_selected():
            return
        
        self.radar_status_var.set("正在开始监控雷达传感器日志...")
        
        # 启用文本编辑
        self.radar_logcat_text.config(state="normal")
        self.radar_logcat_text.delete("1.0", tk.END)
        self.radar_logcat_text.insert("1.0", "正在监控雷达传感器日志...\n")
        self.radar_logcat_text.insert(tk.END, "请用手或物体靠近/远离雷达传感器区域，观察updateGain值变化\n\n")
        self.radar_logcat_text.config(state="disabled")

        # UI 追加内容的缓冲（避免高频 after 导致卡顿/“看起来不再更新”）
        self._radar_ui_buffer = []
        self._radar_ui_flush_scheduled = False
        self._radar_lines_seen = 0
        self._radar_last_line_ts = time.time()
        self._radar_heartbeat_running = False
        
        try:
            # 说明：
            # - 之前用 “logcat | grep/findstr” 在 Windows 上有时会因为管道缓冲导致看起来“到一定量就不更新”
            # - 这里改用 logcat 自带过滤（命令层过滤 TAG），再在 Python 里按关键词过滤/解析
            # - updateGain 常见于 audio_hw_hal_primary / audio_tvsdx_process
            cmd = (
                handler.get_adb_command("logcat -v time -s audio_hw_hal_primary:I audio_tvsdx_process:I *:S")
                if hasattr(handler, "get_adb_command")
                else "adb logcat -v time -s audio_hw_hal_primary:I audio_tvsdx_process:I *:S"
            )
            
            # 启动日志进程
            self.radar_logcat_process = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )

            # 如果进程启动后立刻退出，尽快把错误显示出来
            try:
                time.sleep(0.2)
            except Exception:
                pass
            if self.radar_logcat_process.poll() is not None:
                out = ""
                try:
                    if self.radar_logcat_process.stdout:
                        out = (self.radar_logcat_process.stdout.read() or "").strip()
                except Exception:
                    out = ""
                raise Exception(out or "adb logcat 进程启动失败（无输出），请检查 ADB/设备连接/权限")
            
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

            # 心跳：每 2 秒更新一次状态，提示“是否还在运行/多久没收到新日志”
            self._radar_heartbeat_running = True

            def _heartbeat():
                try:
                    if not getattr(self, "_radar_heartbeat_running", False):
                        return
                    proc = getattr(self, "radar_logcat_process", None)
                    alive = proc is not None and proc.poll() is None
                    now = time.time()
                    last = getattr(self, "_radar_last_line_ts", now)
                    gap = int(now - last)
                    seen = int(getattr(self, "_radar_lines_seen", 0))
                    if alive:
                        if gap >= 10:
                            self.radar_status_var.set(f"监控中：已捕获 {seen} 行（已 {gap}s 无新日志）")
                        else:
                            self.radar_status_var.set(f"监控中：已捕获 {seen} 行")
                    else:
                        self.radar_status_var.set("监控已停止（进程退出）")
                        self._radar_heartbeat_running = False
                        return
                except Exception:
                    pass
                getattr(self, "root", self.parent).after(2000, _heartbeat)

            getattr(self, "root", self.parent).after(2000, _heartbeat)
        
        except Exception as e:
            self.radar_status_var.set(f"开始监控出错: {str(e)}")
            self.radar_logcat_text.config(state="normal")
            self.radar_logcat_text.insert(tk.END, f"开始监控出错: {str(e)}\n")
            self.radar_logcat_text.config(state="disabled")
            try:
                self.start_radar_monitor_button.config(state="normal")
                self.stop_radar_monitor_button.config(state="disabled")
            except Exception:
                pass

    def _read_radar_logcat(self):
        """读取雷达传感器日志输出"""
        try:
            # 记录上一次的updateGain值
            last_gain = None
            gain_changes = 0
            
            keyword = None
            if hasattr(self, "radar_keyword_var"):
                keyword = (self.radar_keyword_var.get() or "").strip()
            keyword_lower = keyword.lower() if keyword else None

            def _ui_append(text_to_add: str) -> None:
                """
                线程安全地追加文本到 UI（带缓冲、批量刷新）。

                之前每行都 after(0) 会造成 UI 消息队列堆积，日志多了之后表现为“到一定量就不检测/不刷新”。
                """
                try:
                    if not hasattr(self, "_radar_ui_buffer") or self._radar_ui_buffer is None:
                        self._radar_ui_buffer = []
                    if not hasattr(self, "_radar_ui_flush_scheduled"):
                        self._radar_ui_flush_scheduled = False
                    self._radar_ui_buffer.append(text_to_add)
                except Exception:
                    return

                if getattr(self, "_radar_ui_flush_scheduled", False):
                    return

                self._radar_ui_flush_scheduled = True

                def _flush():
                    try:
                        buf = getattr(self, "_radar_ui_buffer", None) or []
                        self._radar_ui_buffer = []
                        self._radar_ui_flush_scheduled = False

                        if not buf:
                            return

                        chunk = "".join(buf)
                        self.radar_logcat_text.config(state="normal")
                        self.radar_logcat_text.insert(tk.END, chunk)
                        self.radar_logcat_text.see(tk.END)

                        # 控制文本框大小：只保留最后 N 行，防止越跑越卡
                        max_lines = 2000
                        try:
                            total_lines = int(self.radar_logcat_text.index("end-1c").split(".")[0])
                            if total_lines > max_lines:
                                # 删除最前面的多余行（保留 max_lines 行）
                                delete_to = f"{total_lines - max_lines}.0"
                                self.radar_logcat_text.delete("1.0", delete_to)
                        except Exception:
                            pass

                        self.radar_logcat_text.config(state="disabled")
                    except Exception:
                        try:
                            self._radar_ui_flush_scheduled = False
                        except Exception:
                            pass

                # 100ms 批量刷新一次，既不卡也能实时看到变化
                getattr(self, "root", self.parent).after(100, _flush)

            # 如果 stdout 不存在，说明进程没正常起来
            if not self.radar_logcat_process or not getattr(self.radar_logcat_process, "stdout", None):
                _ui_append("监控进程未正常启动（stdout 为空）\n")
                return

            # 用迭代方式读取，避免 readline 在某些平台/缓冲模式下卡死
            for line in self.radar_logcat_process.stdout:
                if not self.radar_logcat_process or self.radar_logcat_process.poll() is not None:
                    break
                if not line:
                    continue

                # 本地过滤关键词（忽略大小写）；关键词为空则显示全部
                if keyword_lower and keyword_lower not in line.lower():
                    continue

                # 记录心跳信息（只对“匹配后的行”计数）
                try:
                    self._radar_lines_seen = int(getattr(self, "_radar_lines_seen", 0)) + 1
                    self._radar_last_line_ts = time.time()
                except Exception:
                    pass
                
                # 将新行添加到文本框
                _ui_append(line)
                
                # 尝试提取数值（如果日志里包含类似 updateGain xxx 12.34）
                # 关键词不同也尽量匹配 “关键词 ... 数字”
                if keyword:
                    # 支持负数：updateGain=-21
                    pattern = rf'{re.escape(keyword)}.*?(-?\d+\.?\d*)'
                else:
                    pattern = r'(-?\d+\.?\d*)'
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    # UI 展示用正数（符合你给的示例：-21 显示为 21）
                    gain = abs(float(match.group(1)))
                    
                    # 检查值是否变化
                    if last_gain is not None and abs(gain - last_gain) > 0.01:
                        gain_changes += 1
                        _ui_append(f"检测到值变化: {last_gain} -> {gain}\n")
                        
                        # 如果检测到值变化，在界面显示
                        if gain_changes == 1:
                            _ui_append("\n✅ 检测到雷达传感器响应！\n")
                            getattr(self, "root", self.parent).after(0, lambda: self.radar_status_var.set("监控中: 雷达传感器工作正常"))
                    
                    last_gain = gain
        
        except Exception as e:
            getattr(self, "root", self.parent).after(0, lambda: self.radar_status_var.set(f"监控出错: {str(e)}"))

    def stop_radar_monitor(self, handler=None):
        """停止监控雷达传感器logcat"""
        if not hasattr(self, 'radar_logcat_process') or self.radar_logcat_process is None:
            return
        
        try:
            # 停止心跳
            self._radar_heartbeat_running = False

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
            save_dir = get_output_dir(DIR_HAL_DUMP)
        
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

    def setup_airtightness_tab(self, parent):
        """设置气密性测试标签页（堵mic/不堵mic）"""
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill="both", expand=True)

        test_frame = ttk.LabelFrame(frame, text="测试设置（固定脚本）")
        test_frame.pack(fill="x", pady=5)

        line1 = ttk.Frame(test_frame)
        line1.pack(fill="x", padx=10, pady=4)
        ttk.Label(line1, text="录制时长(秒):").pack(side="left")
        self.airtight_duration_var = tk.StringVar(value="15")
        ttk.Entry(line1, textvariable=self.airtight_duration_var, width=6).pack(side="left", padx=(6, 18))
        ttk.Label(line1, text="固定录制参数: 设备0 / 卡3 / 通道4 / 采样率16000 / 位深16").pack(side="left")

        line2 = ttk.Frame(test_frame)
        line2.pack(fill="x", padx=10, pady=4)
        ttk.Label(line2, text="播放文件:").grid(row=0, column=0, sticky="w")
        self.airtight_play_file_var = tk.StringVar(value="")
        self.airtight_play_file_combo = ttk.Combobox(
            line2,
            textvariable=self.airtight_play_file_var,
            width=34,
            state="readonly",
        )
        self.airtight_play_file_combo.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        self.airtight_play_file_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_airtight_play_file_combo_selected())
        ttk.Button(
            line2,
            text="刷新",
            width=6,
            style="Small.TButton",
            command=self.refresh_airtight_play_files,
        ).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(
            line2,
            text="浏览",
            width=6,
            style="Small.TButton",
            command=self.browse_airtight_play_file,
        ).grid(row=0, column=3)
        line2.grid_columnconfigure(1, weight=1)

        path_frame = ttk.Frame(frame)
        path_frame.pack(fill="x", pady=5)
        ttk.Label(path_frame, text="保存路径:").pack(side="left")
        self.airtight_save_path_var = tk.StringVar(value=get_output_dir(DIR_AIRTIGHTNESS))
        ttk.Entry(path_frame, textvariable=self.airtight_save_path_var, width=52).pack(side="left", padx=(8, 0), fill="x", expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=8)
        btn_row1 = ttk.Frame(btn_frame)
        btn_row1.pack(fill="x", pady=(0, 4))
        btn_row2 = ttk.Frame(btn_frame)
        btn_row2.pack(fill="x")
        self.start_airtight_button = ttk.Button(
            btn_row1, text="开始测试", width=9, style="Small.TButton", command=self.start_airtightness_test
        )
        self.start_airtight_button.pack(side="left", padx=5)
        self.stop_airtight_button = ttk.Button(
            btn_row1,
            text="停止测试",
            width=9,
            style="Small.TButton",
            command=self.stop_airtightness_test,
            state="disabled",
        )
        self.stop_airtight_button.pack(side="left", padx=5)
        self.view_airtight_du_button = ttk.Button(
            btn_row1,
            text="堵mic波形",
            width=10,
            style="Small.TButton",
            command=lambda: self.show_latest_airtight_waveform("du_mic"),
            state="disabled",
        )
        self.view_airtight_du_button.pack(side="left", padx=5)
        self.view_airtight_open_button = ttk.Button(
            btn_row1,
            text="不堵mic波形",
            width=11,
            style="Small.TButton",
            command=lambda: self.show_latest_airtight_waveform("open_mic"),
            state="disabled",
        )
        self.view_airtight_open_button.pack(side="left", padx=5)
        self.view_airtight_compare_button = ttk.Button(
            btn_row1,
            text="对比波形",
            width=9,
            style="Small.TButton",
            command=self.show_airtight_compare_waveforms,
            state="disabled",
        )
        self.view_airtight_compare_button.pack(side="left", padx=5)
        ttk.Button(
            btn_row1, text="打开文件夹", width=9, style="Small.TButton", command=self.open_airtight_folder
        ).pack(side="left", padx=5)

        status_frame = ttk.Frame(frame)
        status_frame.pack(fill="both", expand=True, pady=5)
        self.airtight_status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.airtight_status_var, font=("Arial", 10, "bold")).pack(anchor="w")

        info_box = ttk.LabelFrame(status_frame, text="测试信息")
        info_box.pack(fill="both", expand=True, pady=(6, 0))
        self.airtight_info_text = tk.Text(info_box, height=6, wrap="word")
        self.airtight_info_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.airtight_info_text.insert("end", "点击【开始测试】后会先让你选择堵mic/不堵mic。\n")
        self.airtight_info_text.config(state="disabled")

        manual_box = ttk.LabelFrame(frame, text="手动对比文件（无需先测）")
        manual_box.pack(fill="x", pady=(0, 5), before=status_frame)
        manual_row1 = ttk.Frame(manual_box)
        manual_row1.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(manual_row1, text="堵mic文件:").pack(side="left")
        self.airtight_du_manual_path_var = tk.StringVar(value="")
        ttk.Entry(manual_row1, textvariable=self.airtight_du_manual_path_var, width=58).pack(side="left", padx=(6, 6), fill="x", expand=True)
        ttk.Button(
            manual_row1,
            text="浏览",
            width=6,
            style="Small.TButton",
            command=lambda: self.browse_airtight_compare_file("du_mic"),
        ).pack(side="left")

        manual_row2 = ttk.Frame(manual_box)
        manual_row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(manual_row2, text="不堵mic文件:").pack(side="left")
        self.airtight_open_manual_path_var = tk.StringVar(value="")
        ttk.Entry(manual_row2, textvariable=self.airtight_open_manual_path_var, width=58).pack(side="left", padx=(6, 6), fill="x", expand=True)
        ttk.Button(
            manual_row2,
            text="浏览",
            width=6,
            style="Small.TButton",
            command=lambda: self.browse_airtight_compare_file("open_mic"),
        ).pack(side="left")

        self._airtight_test_running = False
        self._airtight_stop_requested = False
        self._airtight_record_proc = None
        self._airtight_play_proc = None
        self.latest_airtight_du_path = ""
        self.latest_airtight_open_path = ""
        self._airtight_play_file_map = {}
        self._airtight_play_file_manual_path = ""
        self.refresh_airtight_play_files()

    def _append_airtight_info(self, message):
        if not hasattr(self, "airtight_info_text"):
            return
        try:
            self.airtight_info_text.config(state="normal")
            self.airtight_info_text.insert("end", f"{message}\n")
            self.airtight_info_text.see("end")
            self.airtight_info_text.config(state="disabled")
        except Exception:
            pass

    def browse_airtight_save_path(self):
        base_dir = self.airtight_save_path_var.get().strip() or get_output_dir(DIR_AIRTIGHTNESS)
        selected = filedialog.askdirectory(title="选择气密性测试保存目录", initialdir=base_dir)
        if selected:
            self.airtight_save_path_var.set(selected)

    def refresh_airtight_play_files(self):
        """刷新气密性测试可选播放文件列表（audio/elephant 与 audio/custom）。"""
        file_map = {}
        candidates = []
        base_dir = self._get_runtime_base_dir()
        for folder, tag in (("elephant", "大象"), ("custom", "自定义")):
            for root in (
                os.path.join(base_dir, "audio", folder),
                os.path.join(os.getcwd(), "audio", folder),
            ):
                if not os.path.isdir(root):
                    continue
                for name in os.listdir(root):
                    if not name.lower().endswith(".wav"):
                        continue
                    full = os.path.join(root, name)
                    label = f"[{tag}] {name}"
                    file_map[label] = full
                    candidates.append(label)
        candidates = sorted(set(candidates))
        self._airtight_play_file_map = file_map
        if hasattr(self, "airtight_play_file_combo"):
            self.airtight_play_file_combo["values"] = candidates
        # 若已手动选择文件，优先显示手动条目
        if getattr(self, "_airtight_play_file_manual_path", ""):
            manual = self._airtight_play_file_manual_path
            self.airtight_play_file_var.set(f"[手动] {os.path.basename(manual)}")
            return
        # 默认选 sweep_speech_48k.wav
        preferred = ""
        for label in candidates:
            if label.lower().endswith("sweep_speech_48k.wav"):
                preferred = label
                break
        if preferred:
            self.airtight_play_file_var.set(preferred)
        elif candidates and not self.airtight_play_file_var.get().strip():
            self.airtight_play_file_var.set(candidates[0])

    def browse_airtight_play_file(self):
        file_path = filedialog.askopenfilename(
            title="选择气密性播放文件",
            filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")],
        )
        if not file_path:
            return
        self._airtight_play_file_manual_path = file_path
        self.airtight_play_file_var.set(f"[手动] {os.path.basename(file_path)}")
        self._append_airtight_info(f"已选择手动播放文件: {file_path}")

    def _on_airtight_play_file_combo_selected(self):
        """下拉选择后，取消手动文件覆盖。"""
        self._airtight_play_file_manual_path = ""

    def _resolve_airtight_play_source(self):
        manual = getattr(self, "_airtight_play_file_manual_path", "")
        if manual and os.path.isfile(manual):
            return manual, os.path.basename(manual)
        selected_label = (self.airtight_play_file_var.get() or "").strip()
        mapped = (self._airtight_play_file_map or {}).get(selected_label)
        if mapped and os.path.isfile(mapped):
            return mapped, os.path.basename(mapped)
        fallback = self._find_airtight_source_file()
        if fallback:
            return fallback, os.path.basename(fallback)
        return "", ""

    def _refresh_airtight_compare_buttons(self):
        du_ok = bool(self.latest_airtight_du_path and os.path.exists(self.latest_airtight_du_path))
        open_ok = bool(self.latest_airtight_open_path and os.path.exists(self.latest_airtight_open_path))
        try:
            self.view_airtight_du_button.config(state="normal" if du_ok else "disabled")
            self.view_airtight_open_button.config(state="normal" if open_ok else "disabled")
            self.view_airtight_compare_button.config(state="normal" if (du_ok and open_ok) else "disabled")
        except Exception:
            pass

    def browse_airtight_compare_file(self, mode):
        file_path = filedialog.askopenfilename(
            title="选择气密性对比录音文件",
            filetypes=[("WAV文件", "*.wav"), ("所有文件", "*.*")],
        )
        if not file_path:
            return
        mode = "du_mic" if mode == "du_mic" else "open_mic"
        if mode == "du_mic":
            self.airtight_du_manual_path_var.set(file_path)
            self.latest_airtight_du_path = file_path
            self._append_airtight_info(f"已手动指定堵mic文件: {file_path}")
        else:
            self.airtight_open_manual_path_var.set(file_path)
            self.latest_airtight_open_path = file_path
            self._append_airtight_info(f"已手动指定不堵mic文件: {file_path}")
        self._refresh_airtight_compare_buttons()

    def open_airtight_folder(self):
        save_dir = self.airtight_save_path_var.get().strip() or get_output_dir(DIR_AIRTIGHTNESS)
        os.makedirs(save_dir, exist_ok=True)
        try:
            if platform.system() == "Windows":
                os.startfile(save_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", save_dir])
            else:
                subprocess.run(["xdg-open", save_dir])
        except Exception as e:
            self.airtight_status_var.set(f"打开文件夹失败: {e}")
            messagebox.showerror("错误", f"打开文件夹失败:\n{e}")

    def _find_airtight_source_file(self):
        base = self._get_runtime_base_dir()
        candidates = [
            os.path.join(base, "audio", "elephant", "sweep_speech_48k.wav"),
            os.path.join(base, "audio", "custom", "sweep_speech_48k.wav"),
            os.path.join(os.getcwd(), "audio", "elephant", "sweep_speech_48k.wav"),
            os.path.join(os.getcwd(), "audio", "custom", "sweep_speech_48k.wav"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return ""

    def start_airtightness_test(self):
        if self._airtight_test_running:
            messagebox.showwarning("提示", "气密性测试正在运行，请先停止或等待完成。")
            return
        if not self.check_device_selected():
            return

        choice = messagebox.askyesnocancel(
            "选择测试模式",
            "请选择本次测试模式：\n\n是：不堵mic测试（建议先做）\n否：堵mic测试\n取消：不开始",
        )
        if choice is None:
            return
        mode = "open_mic" if choice else "du_mic"
        self._launch_airtightness_mode(mode)

    def _launch_airtightness_mode(self, mode):
        if self._airtight_test_running:
            messagebox.showwarning("提示", "气密性测试正在运行，请先停止或等待完成。")
            return
        mode = "du_mic" if mode == "du_mic" else "open_mic"
        mode_label = "堵mic" if mode == "du_mic" else "不堵mic"

        if mode == "du_mic":
            messagebox.showinfo("堵mic测试提醒", "请先使用橡皮泥堵住麦克风孔，再点击确定开始测试。")
        else:
            messagebox.showinfo("不堵mic测试提醒", "请确认已去掉橡皮泥（麦克风孔不堵），再点击确定开始测试。")

        save_dir = self.airtight_save_path_var.get().strip() or ensure_output_dir(DIR_AIRTIGHTNESS)
        os.makedirs(save_dir, exist_ok=True)
        self.airtight_save_path_var.set(save_dir)

        source_file, source_name = self._resolve_airtight_play_source()
        if not source_file:
            messagebox.showerror("错误", "未找到可用播放文件，请先在“播放文件”选择或手动浏览 WAV 文件。")
            return

        self._airtight_stop_requested = False
        self._airtight_test_running = True
        self.start_airtight_button.config(state="disabled")
        self.stop_airtight_button.config(state="normal")
        self.airtight_status_var.set(f"正在测试: {mode_label}")
        self._append_airtight_info(f"=== 开始{mode_label}测试 ===")
        self._append_airtight_info(f"播放文件: {source_name}")

        threading.Thread(
            target=self._run_airtightness_test,
            args=(mode, mode_label, source_file, source_name, save_dir),
            daemon=True,
        ).start()

    def stop_airtightness_test(self):
        if not self._airtight_test_running:
            return
        self._airtight_stop_requested = True
        self.airtight_status_var.set("正在停止气密性测试...")
        self._append_airtight_info("收到停止指令，正在终止录制/播放...")
        try:
            # 直接复用扫频测试的停止逻辑，确保 tinyplay/tinycap 清理一致
            self.stop_sweep_test()
        except Exception:
            pass

    def _terminate_airtight_processes(self):
        for proc_name in ("_airtight_play_proc", "_airtight_record_proc"):
            proc = getattr(self, proc_name, None)
            if not proc:
                continue
            try:
                proc.terminate()
            except Exception:
                pass
            setattr(self, proc_name, None)
        try:
            subprocess.run(self.get_adb_command('shell su -c "killall tinyplay"'), shell=True, capture_output=True, text=True)
            subprocess.run(self.get_adb_command('shell su -c "killall tinycap"'), shell=True, capture_output=True, text=True)
        except Exception:
            pass

    def _run_airtightness_test(self, mode, mode_label, source_file, source_name, save_dir):
        ui = getattr(self, "root", self.parent)
        success_mode = None
        device_id = ""

        def ui_log(msg):
            ui.after(0, lambda m=msg: self._append_airtight_info(m))

        old_settings = {
            "record_device": self.record_device_var.get(),
            "record_card": self.record_card_var.get(),
            "record_channels": self.record_channels_var.get(),
            "record_rate": self.record_rate_var.get(),
            "record_bits": self.record_bits_var.get(),
            "duration": self.sweep_duration_var.get(),
        }

        try:
            # 固定脚本参数：与扫频测试共用同一执行通道，避免两套逻辑不一致
            self.record_device_var.set("0")
            self.record_card_var.set("3")
            self.record_channels_var.set("4")
            self.record_rate_var.set("16000")
            self.record_bits_var.set("16")
            self.sweep_duration_var.set(self.airtight_duration_var.get())

            if hasattr(self, "device_var"):
                device_id = str(self.device_var.get() or "").strip()
            if not device_id:
                device_id = str(getattr(self, "selected_device", "") or "").strip()

            sweep_file = (source_name or "sweep_speech_48k.wav").strip()
            ui_log(f"模式: {mode_label}，开始调用扫频测试执行接口（固定文件 {sweep_file}）...")
            try:
                ui_log(
                    f"本次播放参数沿用扫频设置: 设备{self.play_device_var.get()} / 卡{self.play_card_var.get()}"
                )
            except Exception:
                pass
            # 与扫频入口完全一致的前置准备（清理 tiny 进程 + 重启 audioserver）
            self._prepare_sweep_runtime_environment(device_id, log_fn=ui_log)

            ok = self._run_sweep_test(source_file, sweep_file, save_dir, device_id)
            if not ok:
                raise RuntimeError("扫频执行接口返回失败")
            if not bool(getattr(self, "_last_sweep_play_started", False)):
                raise RuntimeError("播放未成功启动（本次仅录制成功）。请检查播放设备/卡号或设备音频权限。")

            generated_path = str(getattr(self, "latest_sweep_recording_path", "") or "").strip()
            if not generated_path or not os.path.exists(generated_path):
                raise RuntimeError("扫频执行完成，但未找到录音输出文件")

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            final_name = f"airtight_{mode}_{timestamp}_sweep_speech_48k.wav"
            final_path = os.path.join(save_dir, final_name)
            if os.path.abspath(generated_path) != os.path.abspath(final_path):
                os.replace(generated_path, final_path)

            if mode == "du_mic":
                self.latest_airtight_du_path = final_path
            else:
                self.latest_airtight_open_path = final_path
            ui.after(0, self._refresh_airtight_compare_buttons)

            ui.after(0, lambda: self.airtight_status_var.set(f"{mode_label}测试完成"))
            ui_log(f"保存完成: {final_path}")
            ui_log(f"保存目录: {save_dir}")
            success_mode = mode
        except Exception as e:
            err = str(e).strip() or "未知错误"
            ui.after(0, lambda m=err: self.airtight_status_var.set(f"测试失败: {m}"))
            ui_log(f"测试失败: {err}")
        finally:
            # 恢复扫频参数，避免影响用户在扫频页的原始设置
            try:
                self.record_device_var.set(old_settings["record_device"])
                self.record_card_var.set(old_settings["record_card"])
                self.record_channels_var.set(old_settings["record_channels"])
                self.record_rate_var.set(old_settings["record_rate"])
                self.record_bits_var.set(old_settings["record_bits"])
                self.sweep_duration_var.set(old_settings["duration"])
            except Exception:
                pass

            self._airtight_test_running = False
            self._airtight_stop_requested = False
            ui.after(0, lambda: self.start_airtight_button.config(state="normal"))
            ui.after(0, lambda: self.stop_airtight_button.config(state="disabled"))
            if success_mode:
                ui.after(0, lambda m=success_mode, d=save_dir: self._show_airtight_finish_dialog(m, d))

    def _show_airtight_finish_dialog(self, mode, save_dir):
        mode = "du_mic" if mode == "du_mic" else "open_mic"
        mode_label = "堵mic" if mode == "du_mic" else "不堵mic"
        win = tk.Toplevel(getattr(self, "root", self.parent))
        win.title("气密性测试完成")
        win.geometry("460x170")
        win.resizable(False, False)
        win.transient(getattr(self, "root", self.parent))
        win.grab_set()
        self._apply_window_icon(win)

        if mode == "open_mic":
            message = (
                f"{mode_label}测试完成。\n\n"
                "下一步请使用橡皮泥堵住麦克风孔后继续堵mic测试。"
            )
        else:
            message = (
                f"{mode_label}测试完成。\n\n"
                "可继续进行频谱对比查看。"
            )
        ttk.Label(win, text=message, justify="left").pack(fill="x", padx=20, pady=(20, 12))
        ttk.Label(win, text=f"保存目录: {save_dir}", foreground="#555").pack(fill="x", padx=20, pady=(0, 14))

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=20, pady=(0, 16))

        def on_open_folder():
            try:
                self.open_airtight_folder()
            except Exception:
                pass

        def on_continue():
            win.destroy()
            if mode == "open_mic":
                self._launch_airtightness_mode("du_mic")
            else:
                if self.latest_airtight_du_path and self.latest_airtight_open_path:
                    self.show_airtight_compare_waveforms()

        tk.Button(btns, text="打开文件夹", width=14, command=on_open_folder).pack(side="left", padx=(0, 8))
        tk.Button(btns, text="继续下一步测试", width=14, command=on_continue).pack(side="left")
        tk.Button(btns, text="关闭", width=12, command=win.destroy).pack(side="right")

    def show_latest_airtight_waveform(self, mode):
        mode = "du_mic" if mode == "du_mic" else "open_mic"
        target_path = self.latest_airtight_du_path if mode == "du_mic" else self.latest_airtight_open_path
        mode_label = "堵mic" if mode == "du_mic" else "不堵mic"
        if target_path and os.path.exists(target_path):
            self.open_audio_waveform_viewer(target_path)
            return

        save_dir = self.airtight_save_path_var.get().strip() or get_output_dir(DIR_AIRTIGHTNESS)
        if not os.path.isdir(save_dir):
            messagebox.showwarning("提示", f"未找到{mode_label}录音目录：{save_dir}")
            return
        prefix = f"airtight_{mode}_"
        files = [
            os.path.join(save_dir, name)
            for name in os.listdir(save_dir)
            if name.startswith(prefix) and name.lower().endswith(".wav")
        ]
        if not files:
            messagebox.showwarning("提示", f"未找到{mode_label}录音文件。")
            return
        latest = max(files, key=lambda p: os.path.getmtime(p))
        if mode == "du_mic":
            self.latest_airtight_du_path = latest
        else:
            self.latest_airtight_open_path = latest
        self.open_audio_waveform_viewer(latest)

    def show_airtight_compare_waveforms(self):
        du_path = self.latest_airtight_du_path
        open_path = self.latest_airtight_open_path
        if not du_path or not os.path.exists(du_path):
            messagebox.showwarning("提示", "请先完成并保存堵mic测试录音。")
            return
        if not open_path or not os.path.exists(open_path):
            messagebox.showwarning("提示", "请先完成并保存不堵mic测试录音。")
            return
        self.open_airtight_spectrum_compare_viewer(du_path, open_path)

    def _read_wav_channel_samples(self, file_path, channel_index, start_s=None, end_s=None):
        with wave.open(file_path, "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            total_frames = wf.getnframes()
            if channels <= 0 or total_frames <= 0:
                raise ValueError("WAV 文件为空")
            if channel_index < 0 or channel_index >= channels:
                raise ValueError(f"通道索引越界: {channel_index + 1}/{channels}")
            total_duration = total_frames / float(sample_rate)
            s0 = 0.0 if start_s is None else max(0.0, float(start_s))
            s1 = total_duration if end_s is None else max(0.0, float(end_s))
            if s1 <= s0:
                raise ValueError("时间段无效：结束时间必须大于开始时间")
            s0 = min(s0, total_duration)
            s1 = min(s1, total_duration)
            start_frame = int(s0 * sample_rate)
            frame_count = max(1, int((s1 - s0) * sample_rate))

            wf.setpos(start_frame)
            raw = wf.readframes(frame_count)

        values = []
        if sample_width == 1:
            values = [b - 128 for b in raw]
            full_scale = 128.0
        elif sample_width == 2:
            arr = array("h")
            arr.frombytes(raw)
            values = arr.tolist()
            full_scale = 32768.0
        elif sample_width == 3:
            out = []
            for i in range(0, len(raw) - 2, 3):
                v = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
                if v & 0x800000:
                    v -= 0x1000000
                out.append(v)
            values = out
            full_scale = 8388608.0
        elif sample_width == 4:
            arr = array("i")
            arr.frombytes(raw)
            values = arr.tolist()
            full_scale = 2147483648.0
        else:
            raise ValueError(f"暂不支持位宽: {sample_width * 8}bit")

        if not values:
            raise ValueError("音频数据读取失败")

        channel_samples = []
        for i in range(channel_index, len(values), channels):
            channel_samples.append(float(values[i]) / full_scale)
        if len(channel_samples) < 256:
            raise ValueError("有效采样点太少，无法进行频谱分析")
        return channel_samples, sample_rate, channels

    def _fft_complex(self, vec):
        n = len(vec)
        j = 0
        for i in range(1, n):
            bit = n >> 1
            while j & bit:
                j ^= bit
                bit >>= 1
            j ^= bit
            if i < j:
                vec[i], vec[j] = vec[j], vec[i]

        size = 2
        while size <= n:
            half = size // 2
            wm = cmath.exp(complex(0.0, -2.0 * math.pi / size))
            for k in range(0, n, size):
                w = 1.0 + 0.0j
                for m in range(half):
                    u = vec[k + m]
                    t = w * vec[k + m + half]
                    vec[k + m] = u + t
                    vec[k + m + half] = u - t
                    w *= wm
            size <<= 1

    def _compute_channel_spectrum(self, file_path, channel_index, start_s=None, end_s=None):
        samples, sample_rate, channels = self._read_wav_channel_samples(
            file_path,
            channel_index,
            start_s=start_s,
            end_s=end_s,
        )
        if len(samples) < 512:
            raise ValueError("可用于频谱分析的数据不足")

        # 去直流分量，减少低频偏置影响
        mean_val = sum(samples) / len(samples)
        samples = [v - mean_val for v in samples]

        # Welch 参数：行业常见做法（Hann + 50% overlap + 功率平均）
        n = 1
        max_n = min(32768, len(samples))
        while (n << 1) <= max_n:
            n <<= 1
        if n < 512:
            n = 512
        if n > len(samples):
            n = 1
            while (n << 1) <= len(samples):
                n <<= 1
        if n < 256:
            raise ValueError("可用于FFT的数据不足")

        step = max(1, n // 2)  # 50% overlap
        window = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (n - 1)) for i in range(n)]
        sum_w2 = max(1e-18, sum(w * w for w in window))
        cg = max(1e-12, sum(window) / n)  # coherent gain（幅度校正）
        half = n // 2
        df = sample_rate / n

        acc_psd = [0.0] * (half + 1)
        acc_amp2 = [0.0] * (half + 1)
        max_amp = [0.0] * (half + 1)
        seg_count = 0

        for start in range(0, len(samples) - n + 1, step):
            seg = samples[start:start + n]
            vec = [complex(seg[i] * window[i], 0.0) for i in range(n)]
            self._fft_complex(vec)

            for k in range(0, half + 1):
                mag = abs(vec[k])
                one_side_factor = 1.0 if (k == 0 or (k == half and n % 2 == 0)) else 2.0

                # 单边 PSD（dB/Hz 基础）：Pxx = factor * |X|^2 / (Fs * sum(w^2))
                psd = (one_side_factor * (mag * mag)) / (sample_rate * sum_w2)
                acc_psd[k] += psd
                # 单边幅度谱（dBFS）：A ~= factor * |X| / (N * CG)
                amp = (one_side_factor * mag) / (n * cg)
                acc_amp2[k] += (amp * amp)
                if amp > max_amp[k]:
                    max_amp[k] = amp

            seg_count += 1

        if seg_count <= 0:
            raise ValueError("频谱分段失败")

        avg_psd = [v / seg_count for v in acc_psd]
        # 幅度 RMS 平均用于统计；显示曲线采用“选区扫描峰值包络”（更接近 Adobe 扫描选区观感）
        avg_amp = [math.sqrt(v / seg_count) for v in acc_amp2]
        freqs = []
        dbs = []
        raw_freqs = []
        raw_mags = []
        raw_psd = []
        eps = 1e-20
        # 跳过 DC（k=0），避免直流附近主导视觉；保留 Nyquist 前全部
        for k in range(1, half):
            f = k * df
            p = avg_psd[k]
            a = max(max_amp[k], 1e-12)
            db = 20.0 * math.log10(a)
            freqs.append(f)
            dbs.append(db)
            raw_freqs.append(f)
            raw_mags.append(max(avg_amp[k], 1e-12))
            raw_psd.append(max(p, eps))

        # 降采样到最多约 1200 点，提升绘制性能（保留峰值特征）
        if len(freqs) > 1200:
            step_ds = int(math.ceil(len(freqs) / 1200.0))
            f2, d2 = [], []
            for i in range(0, len(freqs), step_ds):
                f_slice = freqs[i:i + step_ds]
                d_slice = dbs[i:i + step_ds]
                if not f_slice:
                    continue
                f2.append(sum(f_slice) / len(f_slice))
                d2.append(sum(d_slice) / len(d_slice))
            freqs, dbs = f2, d2

        # 仅用于显示的轻量平滑，减少毛刺感；不影响 raw_* 原始统计
        dbs = self._smooth_display_db_curve(dbs, passes=2)
        return {
            "sample_rate": sample_rate,
            "channels": channels,
            "freqs": freqs,
            "dbs": dbs,
            "raw_freqs": raw_freqs,
            "raw_mags": raw_mags,
            "raw_psd": raw_psd,
        }

    def _compute_band_energy_db(self, spec, f_low=300.0, f_high=3000.0):
        freqs = spec.get("raw_freqs") or []
        psd = spec.get("raw_psd") or []
        if freqs and psd and len(freqs) == len(psd):
            # 行业标准：频段能量 = ∫ PSD(f) df（离散化为 sum(PSD * df)）
            if len(freqs) >= 2:
                df = max(1e-12, freqs[1] - freqs[0])
            else:
                sr = float(spec.get("sample_rate") or 1.0)
                df = sr / max(1.0, 2.0 * max(1.0, len(freqs)))
            band_energy = 0.0
            for f, p in zip(freqs, psd):
                if f_low <= f <= f_high:
                    band_energy += float(p) * df
            if band_energy <= 0.0:
                return None
            return 10.0 * math.log10(max(band_energy, 1e-20))

        # 兼容旧数据格式
        mags = spec.get("raw_mags")
        if mags is None:
            mags = [10.0 ** (d / 20.0) for d in (spec.get("dbs") or [])]
            freqs = spec.get("raw_freqs") or spec.get("freqs") or []
        total_power = 0.0
        count = 0
        for f, m in zip(freqs, mags):
            if f_low <= f <= f_high:
                total_power += (float(m) * float(m))
                count += 1
        if count <= 0:
            return None
        return 10.0 * math.log10(max(total_power / count, 1e-20))

    def _compute_average_spectrum_db(self, spec, f_low=0.0, f_high=None):
        """计算频谱平均电平（基于 PSD 均值，返回 dB）。"""
        freqs = spec.get("raw_freqs") or []
        psd = spec.get("raw_psd") or []
        if not freqs or not psd or len(freqs) != len(psd):
            return None
        if f_high is None:
            f_high = float(spec.get("sample_rate") or 0.0) / 2.0
        s = 0.0
        c = 0
        for f, p in zip(freqs, psd):
            if f_low <= f <= f_high:
                s += float(p)
                c += 1
        if c <= 0:
            return None
        return 10.0 * math.log10(max(s / c, 1e-20))

    def _smooth_display_db_curve(self, dbs, passes=2):
        """仅用于显示曲线的平滑，避免频谱视觉过毛。"""
        if not dbs or len(dbs) < 5:
            return dbs
        vals = list(dbs)
        for _ in range(max(1, int(passes))):
            src = vals
            dst = [src[0], src[1]]
            for i in range(2, len(src) - 2):
                # 5点加权平滑：1,2,3,2,1
                v = (
                    src[i - 2]
                    + 2.0 * src[i - 1]
                    + 3.0 * src[i]
                    + 2.0 * src[i + 1]
                    + src[i + 2]
                ) / 9.0
                dst.append(v)
            dst.extend([src[-2], src[-1]])
            vals = dst
        return vals

    def _save_canvas_snapshot(self, canvas, default_path):
        """保存 Canvas 图像：优先 PostScript 转 PNG；失败时保存为 PS。"""
        try:
            save_path = filedialog.asksaveasfilename(
                title="保存频谱对比图",
                initialfile=os.path.basename(default_path),
                initialdir=os.path.dirname(default_path),
                defaultextension=".png",
                filetypes=[("PNG 图片", "*.png"), ("PostScript", "*.ps")],
            )
            if not save_path:
                return ""
            ext = os.path.splitext(save_path)[1].lower()
            if ext == ".ps":
                canvas.postscript(file=save_path, colormode="color")
                return save_path

            # 先尝试从 Canvas PostScript 直接转 PNG（不受窗口遮挡影响）
            try:
                import tempfile
                from PIL import Image  # type: ignore
                ps_data = canvas.postscript(colormode="color")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ps") as tmp:
                    tmp.write(ps_data.encode("utf-8", errors="ignore"))
                    tmp_ps = tmp.name
                try:
                    with Image.open(tmp_ps) as img:
                        img.save(save_path, format="PNG")
                    return save_path
                finally:
                    try:
                        os.remove(tmp_ps)
                    except Exception:
                        pass
            except Exception:
                pass

            # 最后兜底：保存为 PS（即使用户填的是 .png）
            fallback = os.path.splitext(save_path)[0] + ".ps"
            canvas.postscript(file=fallback, colormode="color")
            return fallback
        except Exception:
            return ""

    def _export_airtight_compare_png(
        self,
        save_path,
        ch_text,
        spec1,
        spec2,
        freq_max,
        db_min,
        db_max,
        du_range,
        open_range,
        avg_text,
    ):
        """基于频谱数据直接绘制 PNG，不依赖屏幕截图，避免窗口遮挡污染。"""
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        w, h = 1600, 900
        left, right = 82, 24
        top, bottom = 28, 66
        pw = w - left - right
        ph = h - top - bottom

        img = Image.new("RGB", (w, h), "#101216")
        draw = ImageDraw.Draw(img)

        # Windows 下优先使用常见中文字体，避免导出文字乱码
        font_candidates = [
            r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
            r"C:\Windows\Fonts\msyhbd.ttc",    # 微软雅黑粗体
            r"C:\Windows\Fonts\simhei.ttf",    # 黑体
            r"C:\Windows\Fonts\simsun.ttc",    # 宋体
        ]

        def _load_font(size, bold=False):
            for fp in font_candidates:
                try:
                    if bold and fp.lower().endswith("msyh.ttc"):
                        continue
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    continue
            return ImageFont.load_default()

        font_axis = _load_font(14)
        font_title = _load_font(20, bold=True)
        font_meta = _load_font(18, bold=True)
        font_footer = _load_font(15)

        # 网格
        major_hz = 500 if freq_max <= 10000 else 1000
        minor_hz = max(100, major_hz // 2)
        hz = 0
        while hz <= int(freq_max):
            x = left + (hz / freq_max) * pw
            is_major = (hz % major_hz == 0)
            draw.line((x, top, x, top + ph), fill="#263626" if is_major else "#1b271b", width=1)
            if is_major:
                label = f"{int(hz)}" if hz < 1000 else f"{hz/1000:.1f}k"
                draw.text((x - 12, top + ph + 14), label, fill="#aeb8c2", font=font_axis)
            hz += minor_hz

        db = int(db_max)
        while db >= int(db_min):
            y = top + ((db_max - db) / (db_max - db_min)) * ph
            is_major = (db % 10 == 0)
            draw.line((left, y, left + pw, y), fill="#263626" if is_major else "#1b271b", width=1)
            draw.text((left - 34, y - 7), f"{db}", fill="#aeb8c2", font=font_axis)
            db -= 5

        draw.rectangle((left, top, left + pw, top + ph), outline="#3a3a3a", width=1)
        draw.text((left + 2, top - 22), f"{ch_text} 频谱对比", fill="#d8dde5", font=font_title)
        draw.text((left + pw - 60, top - 22), "dBFS", fill="#d8dde5", font=font_axis)

        def _curve_points(spec):
            points = []
            for f, d in zip(spec.get("freqs") or [], spec.get("dbs") or []):
                if f <= 0 or f > freq_max:
                    continue
                x = left + (f / freq_max) * pw
                y = top + ((db_max - max(db_min, min(db_max, d))) / (db_max - db_min)) * ph
                points.append((x, y))
            return points

        p1 = _curve_points(spec1)
        p2 = _curve_points(spec2)
        if len(p1) >= 2:
            draw.line(p1, fill="#ff4040", width=2)
        if len(p2) >= 2:
            draw.line(p2, fill="#4aa3ff", width=2)

        draw.text((left + pw - 420, top + 8), avg_text, fill="#ffd166", font=font_meta)
        footer = (
            f"当前通道: {ch_text} | 频率范围: 0 ~ {int(freq_max)} Hz | 红=堵mic 蓝=不堵mic | "
            f"堵mic选段: {du_range[0]:.2f}s~{du_range[1]:.2f}s | 不堵mic选段: {open_range[0]:.2f}s~{open_range[1]:.2f}s"
        )
        draw.text((left, h - 30), footer, fill="#d8dde5", font=font_footer)
        img.save(save_path, format="PNG")

    def open_airtight_spectrum_compare_viewer(self, du_path, open_path):
        win = tk.Toplevel(getattr(self, "root", self.parent))
        win.title("气密性频谱对比（堵mic vs 不堵mic）")
        win.geometry("1180x760")
        win.minsize(980, 620)
        self._apply_window_icon(win)

        header = ttk.Frame(win, padding=8)
        header.pack(fill="x")
        ttk.Label(header, text=f"堵mic文件: {os.path.basename(du_path)}", foreground="#b33").pack(anchor="w")
        ttk.Label(header, text=f"不堵mic文件: {os.path.basename(open_path)}", foreground="#228").pack(anchor="w")

        try:
            with wave.open(du_path, "rb") as wf1, wave.open(open_path, "rb") as wf2:
                max_ch = min(max(1, wf1.getnchannels()), max(1, wf2.getnchannels()))
                du_dur = wf1.getnframes() / float(max(1, wf1.getframerate()))
                open_dur = wf2.getnframes() / float(max(1, wf2.getframerate()))
        except Exception as e:
            messagebox.showerror("错误", f"读取录音通道信息失败:\n{e}")
            win.destroy()
            return

        ctrl = ttk.Frame(win, padding=(8, 4))
        ctrl.pack(fill="x")
        ttk.Label(ctrl, text="对比通道:").pack(side="left")
        ch_values = [f"CH{i}" for i in range(1, max_ch + 1)]
        channel_var = tk.StringVar(value=ch_values[0])
        channel_combo = ttk.Combobox(ctrl, state="readonly", width=8, textvariable=channel_var, values=ch_values)
        channel_combo.pack(side="left", padx=(6, 12))
        ttk.Label(ctrl, text="红色=堵mic，蓝色=不堵mic").pack(side="left")

        range_frame = ttk.Frame(win, padding=(8, 0))
        range_frame.pack(fill="x")
        ttk.Label(range_frame, text="堵mic选段(s):").pack(side="left")
        du_start_var = tk.StringVar(value="0.00")
        du_end_var = tk.StringVar(value=f"{du_dur:.2f}")
        ttk.Entry(range_frame, textvariable=du_start_var, width=8).pack(side="left", padx=(6, 2))
        ttk.Label(range_frame, text="~").pack(side="left")
        ttk.Entry(range_frame, textvariable=du_end_var, width=8).pack(side="left", padx=(2, 12))

        ttk.Label(range_frame, text="不堵mic选段(s):").pack(side="left")
        open_start_var = tk.StringVar(value="0.00")
        open_end_var = tk.StringVar(value=f"{open_dur:.2f}")
        ttk.Entry(range_frame, textvariable=open_start_var, width=8).pack(side="left", padx=(6, 2))
        ttk.Label(range_frame, text="~").pack(side="left")
        ttk.Entry(range_frame, textvariable=open_end_var, width=8).pack(side="left", padx=(2, 12))

        canvas = tk.Canvas(win, bg="#101216", highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=8, pady=8)

        status_var = tk.StringVar(value="就绪")
        ttk.Label(win, textvariable=status_var, anchor="w").pack(fill="x", padx=10, pady=(0, 8))
        avg_db_var = tk.StringVar(value="平均dB: --")
        ttk.Label(win, textvariable=avg_db_var, anchor="w", foreground="#ffd166", font=("Arial", 10, "bold")).pack(fill="x", padx=10, pady=(0, 8))

        cache = {}

        def _draw_curve(spec, color, left, top, width, height, freq_max, db_min, db_max):
            pts = []
            for f, d in zip(spec["freqs"], spec["dbs"]):
                if f <= 0 or f > freq_max:
                    continue
                x = left + (f / freq_max) * width
                y = top + ((db_max - max(db_min, min(db_max, d))) / (db_max - db_min)) * height
                pts.extend((x, y))
            if len(pts) >= 4:
                # 细线+轻微平滑插值，视觉更接近 Adobe
                canvas.create_line(*pts, fill=color, width=1, smooth=True, splinesteps=8)

        def _parse_range(start_var, end_var, total_dur, name):
            try:
                s0 = float((start_var.get() or "0").strip())
                s1 = float((end_var.get() or f"{total_dur}").strip())
            except Exception:
                raise ValueError(f"{name}时间段格式错误，请输入数字秒数")
            if s0 < 0:
                s0 = 0.0
            if s1 > total_dur:
                s1 = total_dur
            if s1 <= s0:
                raise ValueError(f"{name}时间段无效：结束时间必须大于开始时间")
            if (s1 - s0) < 0.2:
                raise ValueError(f"{name}时间段太短，至少 0.2 秒")
            return (round(s0, 3), round(s1, 3))

        def _get_current_specs():
            ch_text = channel_var.get().strip().upper()
            try:
                ch_idx = max(0, int(ch_text.replace("CH", "")) - 1)
            except Exception:
                ch_idx = 0

            try:
                du_range = _parse_range(du_start_var, du_end_var, du_dur, "堵mic")
                open_range = _parse_range(open_start_var, open_end_var, open_dur, "不堵mic")
            except Exception as e:
                status_var.set(str(e))
                return

            key1 = (du_path, ch_idx, du_range[0], du_range[1])
            key2 = (open_path, ch_idx, open_range[0], open_range[1])
            if key1 not in cache:
                cache[key1] = self._compute_channel_spectrum(du_path, ch_idx, du_range[0], du_range[1])
            if key2 not in cache:
                cache[key2] = self._compute_channel_spectrum(open_path, ch_idx, open_range[0], open_range[1])
            spec1 = cache[key1]
            spec2 = cache[key2]
            return ch_text, du_range, open_range, spec1, spec2

        def render():
            canvas.delete("all")
            try:
                ch_text, du_range, open_range, spec1, spec2 = _get_current_specs()
            except Exception as e:
                status_var.set(f"频谱分析失败: {e}")
                return

            w = max(400, canvas.winfo_width())
            h = max(260, canvas.winfo_height())
            left, right = 62, 24
            top, bottom = 20, 42
            pw = max(200, w - left - right)
            ph = max(120, h - top - bottom)
            db_min, db_max = -125.0, 0.0
            freq_max = min(spec1["sample_rate"], spec2["sample_rate"]) / 2.0
            freq_max = max(1000.0, freq_max)

            # 背景网格
            major_hz = 500 if freq_max <= 10000 else 1000
            minor_hz = max(100, major_hz // 2)
            hz = 0
            while hz <= int(freq_max):
                x = left + (hz / freq_max) * pw
                is_major = (hz % major_hz == 0)
                canvas.create_line(x, top, x, top + ph, fill="#263626" if is_major else "#1b271b")
                if is_major:
                    label = f"{int(hz)}" if hz < 1000 else f"{hz/1000:.1f}k"
                    canvas.create_text(x, top + ph + 16, text=label, fill="#aeb8c2", font=("Arial", 9))
                hz += minor_hz

            db = int(db_max)
            while db >= int(db_min):
                y = top + ((db_max - db) / (db_max - db_min)) * ph
                is_major = (db % 10 == 0)
                canvas.create_line(left, y, left + pw, y, fill="#263626" if is_major else "#1b271b")
                canvas.create_text(left - 8, y, text=f"{db}", fill="#aeb8c2", font=("Arial", 9), anchor="e")
                db -= 5

            canvas.create_rectangle(left, top, left + pw, top + ph, outline="#3a3a3a")
            canvas.create_text(left + 2, top - 6, text=f"{ch_text} 频谱对比", fill="#d8dde5", anchor="sw", font=("Arial", 10, "bold"))
            canvas.create_text(left + pw - 2, top - 6, text="dBFS", fill="#d8dde5", anchor="se", font=("Arial", 9))

            _draw_curve(spec1, "#ff4040", left, top, pw, ph, freq_max, db_min, db_max)
            _draw_curve(spec2, "#4aa3ff", left, top, pw, ph, freq_max, db_min, db_max)

            # 这里的平均 dB 使用“当前选段”的频谱结果计算（非整段文件）
            du_avg_db = self._compute_average_spectrum_db(spec1, 0.0, freq_max)
            open_avg_db = self._compute_average_spectrum_db(spec2, 0.0, freq_max)
            if du_avg_db is None or open_avg_db is None:
                avg_db_var.set("平均dB: 数据不足")
                avg_text = "平均dB(选段全频): N/A"
            else:
                delta_db = du_avg_db - open_avg_db
                avg_db_var.set(
                    f"平均dB(选段全频): 堵mic={du_avg_db:.2f} dB, 不堵mic={open_avg_db:.2f} dB, 差值(堵-不堵)={delta_db:+.2f} dB"
                )
                avg_text = f"平均dB(选段全频) Δ(堵-不堵): {delta_db:+.2f} dB"
            canvas.create_text(left + pw - 4, top + 14, text=avg_text, fill="#ffd166", anchor="ne", font=("Arial", 10, "bold"))

            status_var.set(
                f"当前通道: {ch_text} | 频率范围: 0 ~ {int(freq_max)} Hz | 红=堵mic 蓝=不堵mic | "
                f"堵mic选段: {du_range[0]:.2f}s~{du_range[1]:.2f}s | 不堵mic选段: {open_range[0]:.2f}s~{open_range[1]:.2f}s"
            )

        def save_compare_image():
            ch_text = channel_var.get().strip().upper() or "CH1"
            ts = time.strftime("%Y%m%d_%H%M%S")
            base_name = f"airtight_compare_{ch_text}_{ts}.png"
            default_dir = self.airtight_save_path_var.get().strip() or get_output_dir(DIR_AIRTIGHTNESS)
            os.makedirs(default_dir, exist_ok=True)
            default_path = os.path.join(default_dir, base_name)
            save_path = filedialog.asksaveasfilename(
                title="保存频谱对比图",
                initialfile=os.path.basename(default_path),
                initialdir=os.path.dirname(default_path),
                defaultextension=".png",
                filetypes=[("PNG 图片", "*.png"), ("PostScript", "*.ps")],
            )
            if not save_path:
                status_var.set("保存已取消")
                return
            ext = os.path.splitext(save_path)[1].lower()
            if ext == ".ps":
                try:
                    canvas.postscript(file=save_path, colormode="color")
                    status_var.set(f"已保存对比图: {save_path}")
                except Exception as e:
                    status_var.set(f"保存失败: {e}")
                return
            try:
                ch_text, du_range, open_range, spec1, spec2 = _get_current_specs()
                freq_max = min(spec1["sample_rate"], spec2["sample_rate"]) / 2.0
                freq_max = max(1000.0, freq_max)
                db_min, db_max = -125.0, 0.0
                du_avg_db = self._compute_average_spectrum_db(spec1, 0.0, freq_max)
                open_avg_db = self._compute_average_spectrum_db(spec2, 0.0, freq_max)
                if du_avg_db is None or open_avg_db is None:
                    avg_text = "平均dB(选段全频): N/A"
                else:
                    avg_text = f"平均dB(选段全频) Δ(堵-不堵): {du_avg_db - open_avg_db:+.2f} dB"
                self._export_airtight_compare_png(
                    save_path,
                    ch_text,
                    spec1,
                    spec2,
                    freq_max,
                    db_min,
                    db_max,
                    du_range,
                    open_range,
                    avg_text,
                )
                status_var.set(f"已保存对比图: {save_path}")
            except Exception as e:
                status_var.set(f"保存失败: {e}")

        def _on_waveform_selection(which, start_s, end_s):
            # 波形窗口框选后自动回填到对比窗口
            if start_s is None or end_s is None:
                return
            s0 = max(0.0, float(start_s))
            s1 = max(s0, float(end_s))
            if which == "du":
                du_start_var.set(f"{s0:.2f}")
                du_end_var.set(f"{s1:.2f}")
            else:
                open_start_var.set(f"{s0:.2f}")
                open_end_var.set(f"{s1:.2f}")
            render()

        channel_combo.bind("<<ComboboxSelected>>", lambda _e: render())
        canvas.bind("<Configure>", lambda _e: render())
        ttk.Button(range_frame, text="应用选段", command=render).pack(side="left", padx=(6, 0))
        def _set_full_range():
            du_start_var.set("0.00")
            du_end_var.set(f"{du_dur:.2f}")
            open_start_var.set("0.00")
            open_end_var.set(f"{open_dur:.2f}")
            render()
        ttk.Button(range_frame, text="全段", command=_set_full_range).pack(side="left", padx=(6, 0))
        ttk.Button(range_frame, text="保存对比图", command=save_compare_image).pack(side="left", padx=(12, 0))
        ttk.Button(
            ctrl,
            text="打开堵mic波形(框选回填)",
            command=lambda: self.open_audio_waveform_viewer(
                du_path,
                title="堵mic波形",
                on_selection_changed=lambda s, e: _on_waveform_selection("du", s, e),
            ),
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            ctrl,
            text="打开不堵mic波形(框选回填)",
            command=lambda: self.open_audio_waveform_viewer(
                open_path,
                title="不堵mic波形",
                on_selection_changed=lambda s, e: _on_waveform_selection("open", s, e),
            ),
        ).pack(side="right")
        render()
    
    def update_sweep_file_options(self, handler):
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
                preferred_file = "sweep_speech_48k.wav"
                if preferred_file in sorted_files:
                    self.sweep_file_var.set(preferred_file)
                else:
                    self.sweep_file_var.set(sorted_files[0])
                if hasattr(self, 'update_sweep_info'):
                    self.update_sweep_info(f"已加载 {len(sorted_files)} 个大象扫频文件")
            else:
                if hasattr(self, 'update_sweep_info'):
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
                if hasattr(self, 'update_sweep_info'):
                    self.update_sweep_info(f"已加载 {len(sorted_files)} 个自定义扫频文件")
            else:
                if hasattr(self, 'update_sweep_info'):
                    self.update_sweep_info("未找到自定义扫频文件，请点击'添加文件'按钮添加")

    def add_custom_sweep_file(self, handler):
        """添加自定义扫频文件"""
        # 导入必要的模块
        import shutil
        from tkinter import filedialog, messagebox
        
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
        copied_count = 0
        for file in files:
            base_filename = os.path.basename(file)
            dest_path = os.path.join(custom_dir, base_filename)
            
            try:
                shutil.copy2(file, dest_path)
                copied_count += 1
            except Exception as e:
                messagebox.showerror("错误", f"复制文件 {base_filename} 失败: {str(e)}")
        
        if copied_count > 0:
            self.update_sweep_info(f"已添加 {copied_count} 个文件到自定义扫频文件夹")
            # 更新文件列表
            self.update_sweep_file_options(handler)
        else:
            self.update_sweep_info("没有成功添加任何文件")

    def _prepare_sweep_runtime_environment(self, device_id="", log_fn=None):
        """统一的播放/录制前环境准备：清理残留 tiny 进程并重启 audioserver。"""
        import time
        import subprocess

        def _log(msg):
            if callable(log_fn):
                try:
                    log_fn(msg)
                except Exception:
                    pass

        _log("准备测试环境：清理残留 tinyplay/tinycap ...")
        if device_id:
            subprocess.run(f"adb -s {device_id} shell pkill tinyplay", shell=True, capture_output=True)
            subprocess.run(f"adb -s {device_id} shell pkill tinycap", shell=True, capture_output=True)
        else:
            subprocess.run("adb shell pkill tinyplay", shell=True, capture_output=True)
            subprocess.run("adb shell pkill tinycap", shell=True, capture_output=True)

        time.sleep(0.5)
        _log("准备测试环境：重启 audioserver ...")
        for _ in range(3):
            if device_id:
                cmd = f"adb -s {device_id} shell killall audioserver"
            else:
                cmd = "adb shell killall audioserver"
            subprocess.run(cmd, shell=True, capture_output=True)
            time.sleep(0.5)
    
    def start_sweep_test(self, handler=None):
        """启动扫频测试"""
        if handler is None:
            handler = self.parent
        
        if not handler.check_device_selected():
            return
        
        # 检查是否是批量测试
        if self.batch_test_var.get():  # 修复变量名
            self.start_batch_sweep_test(handler)
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
            
            # 直接构建adb命令，避免递归调用
            device_id = handler.device_var.get() if hasattr(handler, 'device_var') else ""
            
            # 导入必要的模块
            import threading
            # 与气密性测试共用相同准备逻辑，保证播放链路一致
            self._prepare_sweep_runtime_environment(device_id, log_fn=self.update_sweep_info)
            
            # 启动测试线程
            self.sweep_test_thread = threading.Thread(
                target=self._run_sweep_test,
                args=(source_path, sweep_file, save_dir, device_id),
                daemon=True
            )
            self.sweep_test_thread.start()
            
        except Exception as e:
            self.sweep_status_var.set(f"测试出错: {str(e)}")
            self.update_sweep_info(f"测试出错: {str(e)}")
            messagebox.showerror("错误", f"开始扫频测试时出错:\n{str(e)}")
            
            # 恢复按钮状态
            self.start_sweep_button.config(state="normal")
            self.stop_sweep_button.config(state="disabled")

    def _run_sweep_test(self, source_path, sweep_file, save_dir, device_id):
        """执行单个扫频测试"""
        self._last_sweep_play_started = False
        try:
            # 获取录制参数（录制时长为数值，用于后续比较与等待）
            try:
                recording_duration = float(str(self.sweep_duration_var.get()).strip())
            except (ValueError, TypeError):
                raise Exception("录制时长(秒) 请输入有效数字")
            if recording_duration <= 0:
                raise Exception("录制时长(秒) 必须大于 0")
            
            # 从界面获取录制参数
            record_device = self.record_device_var.get()  # 录制设备
            record_card = self.record_card_var.get()      # 卡号
            channels = self.record_channels_var.get()     # 通道数
            sample_rate = self.record_rate_var.get()      # 采样率
            bit_depth = self.record_bits_var.get()        # 位深
            
            # 播放参数固定：设备0 / 卡0（按当前项目默认机型）
            play_device = "0"
            play_card = "0"
            
            # 生成录制文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(sweep_file)[0]
            recording_filename = f"{base_name}_{timestamp}.wav"
            
            # 设备上的录制路径
            device_recording_path = f"/sdcard/{recording_filename}"
            device_audio_path = f"/sdcard/{sweep_file}"
            
            # 确保设备上的目录存在
            if device_id:
                mkdir_cmd = f"adb -s {device_id} shell mkdir -p /sdcard"
            else:
                mkdir_cmd = "adb shell mkdir -p /sdcard"
            subprocess.run(mkdir_cmd, shell=True)
            
            # 推送音频文件到设备（本地文件必须存在）
            if not os.path.isfile(source_path):
                raise Exception(f"本地音频文件不存在: {source_path}")
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"正在推送音频文件: {sweep_file}"))
            # 设备路径统一加引号，避免 shell 解析问题；本地路径已用双引号包裹
            device_audio_path_quoted = f'"{device_audio_path}"'
            if device_id:
                push_cmd = f"adb -s {device_id} push \"{source_path}\" {device_audio_path_quoted}"
            else:
                push_cmd = f"adb push \"{source_path}\" {device_audio_path_quoted}"
            push_result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
            if push_result.returncode != 0:
                err_msg = (push_result.stderr or push_result.stdout or "未知错误").strip()
                raise Exception(f"推送音频文件失败: {err_msg}")
            # 部分环境 adb 返回 0 但实际未推送成功，用输出二次判断（如 "0 files pushed"）
            push_out = (push_result.stdout or "") + (push_result.stderr or "")
            if re.search(r"0\s+files?\s+pushed", push_out):
                raise Exception(f"推送可能未成功（adb 显示 0 file(s) pushed），请检查设备存储与权限。输出: {push_out.strip()}")
            
            # 推送后验证：用 ls -l 确认文件存在且可读，并显示大小
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("验证设备上的文件..."))
            if device_id:
                ls_cmd = f"adb -s {device_id} shell ls -l \"{device_audio_path}\""
            else:
                ls_cmd = f"adb shell ls -l \"{device_audio_path}\""
            ls_result = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
            if ls_result.returncode != 0:
                raise Exception(f"推送后验证失败：设备上未找到 {device_audio_path}，请检查 adb 连接与存储权限后再试。")
            ls_out = (ls_result.stdout or "").strip()
            if "No such file" in ls_out or not ls_out:
                raise Exception(f"推送后验证失败：设备上未找到 {device_audio_path}。ls 输出: {ls_out or '(空)'}")
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("sdcard 下文件已就绪，继续后续步骤。"))
            
            # 开始录制
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"开始录制音频，时长: {recording_duration}秒"))
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"录制参数: 设备{record_device} 卡{record_card} {channels}通道 {sample_rate}Hz {bit_depth}bit"))
            
            # 录制命令：仅使用界面设置的 设备/卡号/通道/采样率/位深（-D -d -c -r -b）
            if device_id:
                record_cmd = f"adb -s {device_id} shell tinycap {device_recording_path} -D {record_device} -d {record_card} -c {channels} -r {sample_rate} -b {bit_depth}"
            else:
                record_cmd = f"adb shell tinycap {device_recording_path} -D {record_device} -d {record_card} -c {channels} -r {sample_rate} -b {bit_depth}"
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"启动录制命令: {record_cmd}"))
            
            if device_id:
                killall_cmd = f"adb -s {device_id} shell killall audioserver"
                root_cmd = f"adb -s {device_id} root"
                pkill_play = f"adb -s {device_id} shell pkill tinyplay"
                pkill_cap = f"adb -s {device_id} shell pkill tinycap"
            else:
                killall_cmd = "adb shell killall audioserver"
                root_cmd = "adb root"
                pkill_play = "adb shell pkill tinyplay"
                pkill_cap = "adb shell pkill tinycap"
            # 先结束上次可能残留的播放/录制进程，再 root 和重启 audioserver，避免第二次无声音
            subprocess.run(pkill_play, shell=True, capture_output=True)
            subprocess.run(pkill_cap, shell=True, capture_output=True)
            time.sleep(0.5)
            # 获取 root 并重启 audioserver，以便 tinyplay/tinycap 能打开设备
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("获取 root 并重启 audioserver..."))
            subprocess.run(root_cmd, shell=True, capture_output=True, text=True)
            time.sleep(2)
            subprocess.run(killall_cmd, shell=True)
            time.sleep(3)
            
            play_process = None
            adb_prefix = f"adb -s {device_id} shell " if device_id else "adb shell "
            play_used_desc = f"设备{play_device} 卡{play_card}"
            active_play_cmd = f"{adb_prefix}tinyplay {device_audio_path_quoted} -D {play_device} -d {play_card}"

            def _is_tinyplay_running_on_device():
                try:
                    if device_id:
                        pid_cmd = f"adb -s {device_id} shell pidof tinyplay"
                    else:
                        pid_cmd = "adb shell pidof tinyplay"
                    rr = subprocess.run(pid_cmd, shell=True, capture_output=True, text=True, timeout=5)
                    pid_txt = ((rr.stdout or "") + (rr.stderr or "")).strip()
                    return rr.returncode == 0 and bool(pid_txt)
                except Exception:
                    return False

            def _restart_playback_after_audio_restart(base_play_cmd, desc):
                """audioserver 重启后，按原播放参数重新拉起 tinyplay。"""
                if not base_play_cmd:
                    return None, "无可用播放命令"
                inner = base_play_cmd.replace(adb_prefix, "", 1)
                inline = (
                    f"{adb_prefix}\"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"{inner}\""
                )
                proc = subprocess.Popen(inline, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                time.sleep(0.8)
                if proc.poll() is None:
                    # 额外校验：设备侧 tinyplay 进程必须真实存在，避免“主机侧进程存活但设备未播放”的假成功
                    if _is_tinyplay_running_on_device():
                        return proc, ""
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    return None, f"播放重启失败（{desc}）: 设备侧未检测到 tinyplay 进程"
                try:
                    _, stderr = proc.communicate(timeout=1)
                    err = (stderr.decode() if isinstance(stderr, bytes) else (stderr or "")).strip()
                except Exception:
                    err = "进程已退出"
                return None, f"播放重启失败（{desc}）: {err or '未知错误'}"
            # 固定参数下最多重试 3 次（处理偶发 PCM 占用）
            last_play_err = ""
            for i in range(3):
                attempt = i + 1
                getattr(self, "root", self.parent).after(
                    0,
                    lambda a=attempt, d=play_used_desc: self.update_sweep_info(f"启动播放: {sweep_file}（{d}，第{a}次）"),
                )
                inner_cmd = active_play_cmd.replace(adb_prefix, "", 1)
                inline_cmd = (
                    f"{adb_prefix}\"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"killall audioserver; sleep 0.35; "
                    f"{inner_cmd}\""
                )
                proc = subprocess.Popen(inline_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                time.sleep(1.2)
                if proc.poll() is None and _is_tinyplay_running_on_device():
                    play_process = proc
                    self._last_sweep_play_started = True
                    getattr(self, "root", self.parent).after(0, lambda d=play_used_desc: self.update_sweep_info(f"播放已启动（{d}），正在启动录制..."))
                    break
                try:
                    _, stderr = proc.communicate(timeout=1)
                    err_text = (stderr.decode() if stderr and isinstance(stderr, bytes) else (stderr or "")).strip() or "进程已退出"
                except Exception:
                    err_text = "进程已退出"
                if proc.poll() is None and not _is_tinyplay_running_on_device():
                    err_text = "设备侧未检测到 tinyplay 进程（疑似被系统抢占）"
                last_play_err = err_text
                getattr(self, "root", self.parent).after(
                    0,
                    lambda msg=err_text, d=play_used_desc: self.update_sweep_info(f"播放尝试失败（{d}）: {msg}"),
                )
                try:
                    proc.terminate()
                except Exception:
                    pass
                time.sleep(0.3)
            if play_process is None:
                raise Exception(f"播放失败：固定参数（设备{play_device} 卡{play_card}）启动失败。{last_play_err}")
            
            # 播放已启动时多等一会再开录制，减少「Device or resource busy」
            if play_process is not None:
                getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("播放已稳定，1.2 秒后启动录制..."))
                time.sleep(1.2)
            
            # 使用界面设置的录制参数单次启动；失败时重启 audioserver 再重试
            record_started_ok = False
            record_failed_msg = ""
            record_process = None
            try:
                record_process = subprocess.Popen(record_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(0.5)
                if record_process.poll() is not None:
                    stdout, stderr = record_process.communicate()
                    err_text = (stderr.decode() if stderr and isinstance(stderr, bytes) else (stderr or "")).strip() if stderr else ""
                    getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("录制失败，正在重启audioserver(第1次)..."))
                    subprocess.run(killall_cmd, shell=True)
                    time.sleep(2)
                    if play_process is not None and active_play_cmd:
                        restarted_proc, restart_err = _restart_playback_after_audio_restart(active_play_cmd, play_used_desc or "原参数")
                        if restarted_proc is not None:
                            play_process = restarted_proc
                            getattr(self, "root", self.parent).after(0, lambda d=(play_used_desc or "原参数"): self.update_sweep_info(f"audioserver 重启后已恢复播放（{d}）"))
                        elif restart_err:
                            getattr(self, "root", self.parent).after(0, lambda m=restart_err: self.update_sweep_info(m))
                    record_process = subprocess.Popen(record_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    time.sleep(0.5)
                if record_process.poll() is not None:
                    stdout, stderr = record_process.communicate()
                    err_text = (stderr.decode() if isinstance(stderr, bytes) else (stderr or "")).strip() if stderr else ""
                    if "Permission denied" in err_text or "Unable to open PCM" in err_text:
                        getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("仍失败，正在重启audioserver(第2、3次)..."))
                        subprocess.run(killall_cmd, shell=True)
                        time.sleep(1)
                        subprocess.run(killall_cmd, shell=True)
                        time.sleep(2)
                        if play_process is not None and active_play_cmd:
                            restarted_proc, restart_err = _restart_playback_after_audio_restart(active_play_cmd, play_used_desc or "原参数")
                            if restarted_proc is not None:
                                play_process = restarted_proc
                                getattr(self, "root", self.parent).after(0, lambda d=(play_used_desc or "原参数"): self.update_sweep_info(f"audioserver 重启后已恢复播放（{d}）"))
                            elif restart_err:
                                getattr(self, "root", self.parent).after(0, lambda m=restart_err: self.update_sweep_info(m))
                        record_process = subprocess.Popen(record_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        time.sleep(0.5)
                    if record_process.poll() is not None:
                        stdout, stderr = record_process.communicate()
                        err_text = (stderr.decode() if isinstance(stderr, bytes) else (stderr or "")).strip() if stderr else ""
                        _hint = "\n\n建议：本机 tinycap 需要权限才能打开 PCM 设备。可尝试：1) 先执行 adb root 后再进行扫频测试；2) 检查录制设置中的「设备/卡号」是否为当前设备实际可用的 PCM 编号（如 0/1/2 等）。"
                        record_started_ok = False
                        record_failed_msg = f"录制命令启动失败: {err_text}{_hint}"
                    else:
                        record_started_ok = True
                else:
                    record_started_ok = True
            except Exception as e:
                record_started_ok = False
                record_failed_msg = str(e)
                record_process = None
            
            if record_started_ok and record_process is not None:
                getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("录制已启动，与播放同时进行中..."))
                # 等待录制完成（recording_duration 已转为 float）
                remaining_time = float(recording_duration)
                while remaining_time > 0 and record_process.poll() is None:
                    getattr(self, "root", self.parent).after(0, lambda t=remaining_time: self.update_sweep_info(f"等待录制完成，剩余: {t:.1f} 秒"))
                    time.sleep(0.5)
                    remaining_time -= 0.5
                
                # 停止录制
                if record_process.poll() is None:
                    getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("正在停止录制..."))
                    record_process.terminate()
                    try:
                        record_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        record_process.kill()
                
                # 检查录制结果并拉取
                getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("检查录制文件..."))
                local_file_path = os.path.join(save_dir, recording_filename)
                getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"正在拉取录制文件到本地..."))
                if device_id:
                    pull_cmd = f"adb -s {device_id} pull {device_recording_path} \"{local_file_path}\""
                else:
                    pull_cmd = f"adb pull {device_recording_path} \"{local_file_path}\""
                pull_result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                if pull_result.returncode != 0:
                    raise Exception(f"拉取录制文件失败: {pull_result.stderr}")
                
                # 验证本地文件并修正 WAV 头（tinycap 被 terminate 时不会回写 data_sz，导致时长/波形显示为空）
                if os.path.exists(local_file_path):
                    if fix_wav_header_after_tinycap(local_file_path, channels, sample_rate, bit_depth):
                        getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info("已修正录制文件 WAV 头，时长与波形可正常显示。"))
                    local_file_size = os.path.getsize(local_file_path)
                    self.latest_sweep_recording_path = local_file_path
                    if hasattr(self, "view_sweep_waveform_button") and self.view_sweep_waveform_button:
                        try:
                            getattr(self, "root", self.parent).after(0, lambda: self.view_sweep_waveform_button.config(state="normal"))
                        except Exception:
                            pass
                    getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"✓ 测试完成: {recording_filename} ({local_file_size} bytes)"))
                    getattr(self, "root", self.parent).after(0, lambda: self.sweep_status_var.set("测试完成"))
                else:
                    raise Exception("本地录制文件不存在")
                
                # 清理设备上的临时文件
                if device_id:
                    cleanup_cmd = f"adb -s {device_id} shell rm {device_recording_path} {device_audio_path}"
                else:
                    cleanup_cmd = f"adb shell rm {device_recording_path} {device_audio_path}"
                subprocess.run(cleanup_cmd, shell=True)
            else:
                # 录制未成功，但播放已执行；结束设备上的 tinyplay/tinycap，避免占用导致下次无声音
                if device_id:
                    subprocess.run(f"adb -s {device_id} shell pkill tinyplay", shell=True, capture_output=True)
                    subprocess.run(f"adb -s {device_id} shell pkill tinycap", shell=True, capture_output=True)
                else:
                    subprocess.run("adb shell pkill tinyplay", shell=True, capture_output=True)
                    subprocess.run("adb shell pkill tinycap", shell=True, capture_output=True)
                getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"录制未成功，无录音文件；播放已完成。{record_failed_msg}"))
                getattr(self, "root", self.parent).after(0, lambda: self.sweep_status_var.set("播放完成(录制未成功)"))
                if device_id:
                    cleanup_cmd = f"adb -s {device_id} shell rm -f {device_audio_path_quoted}"
                else:
                    cleanup_cmd = f"adb shell rm -f {device_audio_path_quoted}"
                subprocess.run(cleanup_cmd, shell=True)
            
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_sweep_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            
            return True
                
        except Exception as e:
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"✗ 测试失败: {str(e)}"))
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_sweep_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            return False

    def stop_sweep_test(self, handler=None):
        """停止扫频测试"""
        try:
            # 停止批量测试
            if hasattr(self, 'batch_testing') and self.batch_testing:
                self.batch_testing = False
                self.update_sweep_info("正在停止批量测试...")
            
            # 停止当前播放
            device_id = self.device_var.get() if hasattr(self, "device_var") else ""
            if device_id:
                stop_cmd = f"adb -s {device_id} shell am force-stop com.android.music"
            else:
                stop_cmd = "adb shell am force-stop com.android.music"
            subprocess.run(stop_cmd, shell=True)
            
            # 尝试停止其他可能的音频播放器
            players = ["com.google.android.music", "com.android.mediacenter", "com.miui.player"]
            for player in players:
                if device_id:
                    stop_cmd = f"adb -s {device_id} shell am force-stop {player}"
                else:
                    stop_cmd = f"adb shell am force-stop {player}"
                subprocess.run(stop_cmd, shell=True)
                
            # 停止可能正在运行的录制与播放进程
            if device_id:
                subprocess.run(f"adb -s {device_id} shell pkill tinycap", shell=True)
                subprocess.run(f"adb -s {device_id} shell pkill tinyplay", shell=True)
            else:
                subprocess.run("adb shell pkill tinycap", shell=True)
                subprocess.run("adb shell pkill tinyplay", shell=True)
            
            # 更新UI状态
            if hasattr(self, 'start_sweep_button'):
                self.start_sweep_button.config(state="normal")
            if hasattr(self, 'stop_sweep_button'):
                self.stop_sweep_button.config(state="disabled")
            if hasattr(self, 'start_batch_button'):
                self.start_batch_button.config(state="normal")
            if hasattr(self, 'stop_batch_button'):
                self.stop_batch_button.config(state="disabled")
            
            self.update_sweep_info("已停止扫频测试")
            
        except Exception as e:
            self.update_sweep_info(f"停止测试时出错: {str(e)}")
            messagebox.showerror("错误", f"停止测试时出错:\n{str(e)}")

    def pull_sweep_recording(self, device_id=None):
        """拉取扫频录音文件"""
        if not hasattr(self, 'sweep_filename'):
            self.update_sweep_info("没有找到需要拉取的录音文件")
            return
        
        try:
            # 检查录制文件是否存在
            device_recording_path = f"/sdcard/{self.sweep_filename}"
            self.update_sweep_info(f"检查录制文件: {device_recording_path}")
            
            if device_id:
                check_cmd = f"adb -s {device_id} shell ls -la {device_recording_path}"
            else:
                check_cmd = f"adb shell ls -la {device_recording_path}"
            
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if check_result.returncode == 0:
                file_info = check_result.stdout.strip()
                self.update_sweep_info(f"找到文件: {device_recording_path}\n信息: {file_info}")
                
                # 获取保存路径
                save_dir = self.sweep_save_path_var.get().strip()
                if not save_dir:
                    save_dir = get_output_dir(DIR_SWEEP_RECORDINGS)
                
                os.makedirs(save_dir, exist_ok=True)
                local_path = os.path.join(save_dir, self.sweep_filename)
                
                # 拉取文件到本地
                self.update_sweep_info(f"正在拉取录制文件到: {local_path}")
                if device_id:
                    pull_cmd = f"adb -s {device_id} pull {device_recording_path} \"{local_path}\""
                else:
                    pull_cmd = f"adb pull {device_recording_path} \"{local_path}\""
                
                result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"拉取文件失败: {result.stderr}")
                
                # 检查文件是否存在且大于0
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    self.update_sweep_info(f"扫频测试完成，文件已保存为: {local_path}")
                    self.sweep_status_var.set("测试完成")
                    self.latest_sweep_recording_path = local_path
                    if hasattr(self, "view_sweep_waveform_button") and self.view_sweep_waveform_button:
                        try:
                            self.view_sweep_waveform_button.config(state="normal")
                        except Exception:
                            pass
                    
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
            save_dir = OUTPUT_ROOT
        
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
                self.latest_loopback_recording_path = local_path
                if hasattr(self, "view_loopback_waveform_button") and self.view_loopback_waveform_button:
                    try:
                        self.view_loopback_waveform_button.config(state="normal")
                    except Exception:
                        pass
                
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
        """打开包含指定文件的文件夹；若目录不存在则先创建再打开，便于用户放入缺失的音频等"""
        if not (file_path and isinstance(file_path, str)):
            file_path = ""
        folder_path = os.path.dirname(file_path)
        try:
            if not folder_path:
                messagebox.showinfo("打开位置", "路径为空，无法打开。")
                return
            if not os.path.isdir(folder_path):
                try:
                    os.makedirs(folder_path, exist_ok=True)
                except Exception as mkdir_e:
                    messagebox.showerror("错误", f"目录不存在且无法创建：\n{folder_path}\n\n{mkdir_e}")
                    return
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path])
            else:  # Linux
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            self.status_var.set(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")
    
    def _loopback_test_thread(self, device, play_device, channels, rate, audio_source, device_id):
        try:
            # 规范化参数（避免空字符串导致命令异常）
            device = (str(device).strip() or "0")
            play_device = (str(play_device).strip() or "0")
            channels = (str(channels).strip() or "2")
            rate = (str(rate).strip() or "48000")

            # 准备工作
            if device_id:
                subprocess.run(f"adb -s {device_id} root", shell=True)
            else:
                subprocess.run("adb root", shell=True)
            
            # 根据选择的音频源处理：7.1/2.1/2.0 使用 audio/channel/ 下对应文件，custom 使用用户选择文件
            if audio_source in ("7.1", "2.1", "2.0"):
                name_map = {"7.1": "Nums_7dot1_16_48000.wav", "2.1": "Nums_2dot1_16_48000.wav", "2.0": "Nums_2dot0_16_48000.wav"}
                audio_name = name_map[audio_source]
                base_dir = getattr(self, "_get_runtime_base_dir", lambda: os.getcwd())()
                audio_file = os.path.join(base_dir, "audio", "channel", audio_name)
                if not os.path.exists(audio_file):
                    msg = (
                        f"默认测试音频不存在：audio/channel/{audio_name}\n\n"
                        "请将对应音频放到 audio/channel 目录，或使用「自定义音频」。"
                    )
                    getattr(self, "root", self.parent).after(0, lambda: messagebox.showerror("缺少音频文件", msg))
                    getattr(self, "root", self.parent).after(0, lambda: self.start_loopback_button.config(state="normal"))
                    getattr(self, "root", self.parent).after(0, lambda: self.stop_loopback_button.config(state="disabled"))
                    return
                if device_id:
                    subprocess.run(f"adb -s {device_id} push \"{audio_file}\" /sdcard/test_audio.wav", shell=True)
                else:
                    subprocess.run(f"adb push \"{audio_file}\" /sdcard/test_audio.wav", shell=True)
                remote_audio_file = "/sdcard/test_audio.wav"
            else:
                # 使用自定义音频文件
                if not getattr(self, "selected_audio_file", None):
                    getattr(self, "root", self.parent).after(0, lambda: messagebox.showerror("错误", "请先选择自定义音频文件"))
                    getattr(self, "root", self.parent).after(0, lambda: self.start_loopback_button.config(state="normal"))
                    getattr(self, "root", self.parent).after(0, lambda: self.stop_loopback_button.config(state="disabled"))
                    return
                if not os.path.exists(self.selected_audio_file):
                    getattr(self, "root", self.parent).after(0, lambda: messagebox.showerror("错误", f"自定义音频文件不存在:\n{self.selected_audio_file}"))
                    getattr(self, "root", self.parent).after(0, lambda: self.start_loopback_button.config(state="normal"))
                    getattr(self, "root", self.parent).after(0, lambda: self.stop_loopback_button.config(state="disabled"))
                    return
                # 获取文件扩展名
                _, ext = os.path.splitext(self.selected_audio_file)
                remote_filename = f"test_audio{ext}"
                
                getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set("正在推送自定义音频文件到设备..."))
                if device_id:
                    subprocess.run(f"adb -s {device_id} push \"{self.selected_audio_file}\" /sdcard/{remote_filename}", shell=True)
                else:
                    subprocess.run(f"adb push \"{self.selected_audio_file}\" /sdcard/{remote_filename}", shell=True)
                remote_audio_file = f"/sdcard/{remote_filename}"
            
            # 重启audioserver
            for _ in range(3):
                if device_id:
                    subprocess.run(f"adb -s {device_id} shell killall audioserver", shell=True)
                else:
                    subprocess.run("adb shell killall audioserver", shell=True)
                time.sleep(0.5)
            
            # 开始录制 - 使用正确的参数格式
            # 重要：确保正确的录制文件名
            self.loopback_filename = f"test_{channels}ch.wav"
            
            # 使用完整的录制命令
            if device_id:
                record_cmd = f"adb -s {device_id} shell tinycap /sdcard/{self.loopback_filename} -D 0 -d {device} -c {channels} -r {rate} -p 480 -b 16"
            else:
                record_cmd = f"adb shell tinycap /sdcard/{self.loopback_filename} -D 0 -d {device} -c {channels} -r {rate} -p 480 -b 16"
            
            # 开始录制进程
            self.loopback_process = subprocess.Popen(record_cmd, shell=True)
            
            # 更新状态
            getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set("正在录制通道音频..."))
            
            # 等待录制启动
            time.sleep(2)
            
            # 播放音频
            getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set("正在播放音频..."))
            
            # 根据文件类型选择播放方式
            if remote_audio_file.endswith('.wav'):
                # 使用 tinyplay 播放 WAV
                # 关键修复：优先“像多声道测试一样”不指定 -D/-d，让系统走默认输出（这是你多声道能播的原因）
                # 失败再回退到显式指定（有些设备需要）
                if device_id:
                    candidates = [
                        f"adb -s {device_id} shell tinyplay {remote_audio_file} -d {play_device}",
                        f"adb -s {device_id} shell tinyplay {remote_audio_file} -D 0 -d {play_device}",
                        f"adb -s {device_id} shell tinyplay {remote_audio_file}",
                        f"adb -s {device_id} shell tinyplay {remote_audio_file} -D 0 -d 0",
                    ]
                else:
                    candidates = [
                        f"adb shell tinyplay {remote_audio_file} -d {play_device}",
                        f"adb shell tinyplay {remote_audio_file} -D 0 -d {play_device}",
                        f"adb shell tinyplay {remote_audio_file}",
                        f"adb shell tinyplay {remote_audio_file} -D 0 -d 0",
                    ]

                last_err = ""
                for idx, play_cmd in enumerate(candidates, start=1):
                    getattr(self, "root", self.parent).after(0, lambda c=play_cmd, i=idx: self.loopback_status_var.set(f"正在播放音频...（方案{i}）"))
                    r = subprocess.run(play_cmd, shell=True, capture_output=True, text=True)
                    if r.returncode == 0:
                        last_err = ""
                        break
                    last_err = (r.stderr or r.stdout or "").strip()

                if last_err:
                    getattr(self, "root", self.parent).after(
                        0,
                        lambda: self.loopback_status_var.set(f"播放失败（tinyplay）: {last_err[:160]}"),
                    )
            else:
                # 对于其他格式，尝试使用系统媒体播放器
                if device_id:
                    play_cmd = f"adb -s {device_id} shell am start -a android.intent.action.VIEW -d file://{remote_audio_file} -t audio/*"
                else:
                    play_cmd = f"adb shell am start -a android.intent.action.VIEW -d file://{remote_audio_file} -t audio/*"
                subprocess.run(play_cmd, shell=True)
                
                # 等待一段时间让音频播放完成
                getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set("正在播放音频，请等待..."))
                time.sleep(30)  # 假设音频不超过30秒
            
            # 更新状态
            getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set("音频播放完成，录制继续进行中..."))
            
        except Exception as e:
            getattr(self, "root", self.parent).after(0, lambda: self.loopback_status_var.set(f"测试出错: {str(e)}"))
            messagebox.showerror("错误", f"测试过程中出现错误:\n{str(e)}")
            
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_loopback_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_loopback_button.config(state="disabled"))

    def run_loopback_test(self):
        """运行Loopback或Ref通道测试"""
        if not self.check_device_selected():
            return
            
        device = self.loopback_device_var.get()
        play_device = (getattr(self, "loopback_play_device_var", None) and self.loopback_play_device_var.get() or "0").strip() or "0"
        channels = self.loopback_channel_var.get()
        rate = self.loopback_rate_var.get()
        audio_source = self.audio_source_var.get()
        
        # 检查自定义音频文件
        if audio_source == "custom" and not getattr(self, 'selected_audio_file', None):
            messagebox.showerror("错误", "请先选择自定义音频文件")
            return
        
        self.loopback_status_var.set("正在执行通道测试...")
        
        # 禁用开始按钮，启用停止按钮
        self.start_loopback_button.config(state="disabled")
        self.stop_loopback_button.config(state="normal")
        
        # 获取设备ID
        device_id = self.device_var.get() if hasattr(self, 'device_var') else ""
        
        # 在新线程中运行测试，避免GUI冻结
        self.loopback_thread = threading.Thread(target=self._loopback_test_thread, 
                                          args=(device, play_device, channels, rate, audio_source, device_id), 
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
        # 兼容两种输入：
        # - add_prop_to_ui("vendor.xxx.prop", "1")
        # - add_prop_to_ui("vendor.xxx.prop 1")
        try:
            if isinstance(prop_name, str) and (" " in prop_name) and (prop_value == "1" or prop_value is None):
                parts = prop_name.split()
                if len(parts) >= 2:
                    prop_name, prop_value = parts[0], parts[1]
                else:
                    prop_name, prop_value = parts[0], "1"
        except Exception:
            pass

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
    
    # 需要添加这些方法的引用，确保各个功能窗口能正常工作
    def check_device_selected(self):
        """检查是否选择了设备"""
        # UIComponents 不应覆盖 DeviceOperations 的真实实现；这里委托给父类
        try:
            return super().check_device_selected()
        except Exception:
            # 兜底：至少保证不会因为 UI mixin 覆盖导致直接崩溃
            return hasattr(self, 'device_var') and bool(self.device_var.get().strip())
    
    def get_adb_command(self, cmd):
        """获取ADB命令"""
        # UIComponents 不应覆盖 DeviceOperations 的真实实现；这里委托给父类
        try:
            return super().get_adb_command(cmd)
        except Exception:
            return f"adb {cmd}"
    
    def take_screenshot(self):
        """截取屏幕截图"""
        if not self.check_device_selected():
            return
        
        try:
            self.screenshot_status_var.set("正在截取屏幕...")
            self.update_screenshot_info("正在截取屏幕...")
            
            # 获取保存路径
            save_dir = self.screenshot_save_path_var.get().strip()
            if not save_dir:
                save_dir = get_output_dir(DIR_SCREENSHOTS)
            
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            local_path = os.path.join(save_dir, filename)
            
            # 直接构建adb命令，避免递归调用
            device_id = self.device_var.get() if hasattr(self, 'device_var') else ""
            if device_id:
                cmd = f"adb -s {device_id} exec-out screencap -p"
            else:
                cmd = "adb exec-out screencap -p"
            
            result = subprocess.run(cmd, shell=True, capture_output=True)
            
            if result.returncode != 0:
                raise Exception(f"截图命令执行失败: {result.stderr.decode() if result.stderr else '未知错误'}")
            
            # 保存截图数据
            with open(local_path, 'wb') as f:
                f.write(result.stdout)
            
            # 检查文件是否保存成功
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                self.update_screenshot_info(f"截图成功保存: {filename}")
                self.update_screenshot_info(f"文件路径: {local_path}")
                self.screenshot_status_var.set("截图完成")
                
                # 询问是否打开文件夹
                if messagebox.askyesno("截图完成", f"截图已保存为:\n{local_path}\n\n是否打开文件夹？"):
                    self.open_screenshot_folder()
            else:
                raise Exception("截图文件保存失败或文件为空")
            
        except Exception as e:
            error_msg = f"截图出错: {str(e)}"
            self.screenshot_status_var.set(error_msg)
            self.update_screenshot_info(error_msg)
            messagebox.showerror("错误", f"截图时出错:\n{str(e)}")

    def open_screenshot_folder(self):
        """打开截图保存文件夹"""
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
            self.screenshot_status_var.set(f"打开文件夹出错: {str(e)}")
            self.update_screenshot_info(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("错误", f"打开文件夹时出错:\n{str(e)}")

    def send_keycode(self, keycode):
        """发送遥控器按键"""
        if not self.check_device_selected():
            return
        
        try:
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set(f"正在发送按键: {keycode}")
            
            # 直接构建adb命令，避免递归调用
            device_id = self.parent.device_var.get() if hasattr(self.parent, 'device_var') else ""
            if device_id:
                cmd = f"adb -s {device_id} shell input keyevent KEYCODE_{keycode}"
            else:
                cmd = f"adb shell input keyevent KEYCODE_{keycode}"
            
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

    def launch_quick_action(self, label: str, spec):
        """
        快捷应用/动作统一入口：
        - ("package", [pkg1, pkg2, ...])：用 monkey 启动（不依赖 Activity）
        - ("activity", "pkg/.Activity")：用 am start -n 精确启动
        - ("shell", "am start -n ...")：直接执行 shell 指令（会自动补全为 adb shell）
        """
        if not self.check_device_selected():
            return

        try:
            kind = spec[0]
            payload = spec[1]

            if hasattr(self, "remote_status_var"):
                self.remote_status_var.set(f"正在执行: {label} ...")

            if kind == "activity":
                component = str(payload).strip()
                cmd = self.get_adb_command(f"shell am start -n {component}")
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if r.returncode != 0:
                    raise Exception((r.stderr or r.stdout or "").strip() or "am start 失败")
                if hasattr(self, "remote_status_var"):
                    self.remote_status_var.set(f"已启动: {label}")
                return

            if kind == "shell":
                raw = str(payload or "").strip()
                if not raw:
                    raise Exception("shell 指令为空")
                # 允许用户输入 "shell xxx" 或直接 "am start -n ..."
                if raw.startswith("adb "):
                    # 用户提供了完整 adb 命令：直接执行（不自动补 -s）
                    cmd = raw
                else:
                    raw_shell = raw if raw.startswith("shell ") else f"shell {raw}"
                    cmd = self.get_adb_command(raw_shell)
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if r.returncode != 0:
                    raise Exception((r.stderr or r.stdout or "").strip() or f"执行失败: {cmd}")
                if hasattr(self, "remote_status_var"):
                    self.remote_status_var.set(f"已执行: {label}")
                return

            # kind == "package"
            package_candidates = payload or []
            last_err = ""
            for pkg in package_candidates:
                pkg = (pkg or "").strip()
                if not pkg:
                    continue
                cmd = self.get_adb_command(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
                if r.returncode == 0 and ("No activities found" not in out) and ("Error" not in out):
                    if hasattr(self, "remote_status_var"):
                        self.remote_status_var.set(f"已启动: {label}（{pkg}）")
                    return
                last_err = out or f"returncode={r.returncode}"

            if hasattr(self, "remote_status_var"):
                self.remote_status_var.set(f"启动失败: {label}")
            messagebox.showerror(
                "启动失败",
                f"无法启动 {label}。\n\n"
                f"尝试的包名：{', '.join(package_candidates)}\n\n"
                f"最后一次输出：\n{last_err[:600]}",
            )

        except Exception as e:
            if hasattr(self, "remote_status_var"):
                self.remote_status_var.set(f"执行失败: {label}")
            messagebox.showerror("错误", f"执行 {label} 时出错:\n{str(e)}")

    def adapt_remote_controller(self):
        """重新适配设备的遥控器"""
        if not self.check_device_selected():
            return
        
        try:
            if hasattr(self, 'remote_status_var'):
                self.remote_status_var.set("正在适配遥控器...")
            
            # 直接构建adb命令，避免递归调用
            device_id = self.device_var.get() if hasattr(self, 'device_var') else ""
            if device_id:
                cmd = f"adb -s {device_id} shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS"
            else:
                cmd = "adb shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS"
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
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

    def update_sweep_info(self, message):
        """更新扫频测试信息"""
        if hasattr(self, 'sweep_info_text'):
            self.sweep_info_text.config(state="normal")
            self.sweep_info_text.insert("end", message + "\n")
            self.sweep_info_text.see("end")  # 滚动到底部
            self.sweep_info_text.config(state="disabled")

    def start_batch_sweep_test(self, handler=None):
        """启动批量扫频测试"""
        if handler is None:
            handler = self.parent
        
        if not handler.check_device_selected():
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
            save_dir = get_output_dir(DIR_SWEEP_RECORDINGS)
        
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
        
        # 获取设备ID
        device_id = handler.device_var.get() if hasattr(handler, 'device_var') else ""
        
        # 在单独的线程中运行批量测试
        self.batch_thread = threading.Thread(
            target=self._run_batch_tests,
            args=(files, sweep_type, interval, recording_duration, save_dir, device_id),
            daemon=True
        )
        self.batch_thread.start()

    def _run_batch_tests(self, files, sweep_type, interval, recording_duration, save_dir, device_id):
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
                success = self._batch_test_single_file(file, sweep_type, recording_duration, save_dir, device_id)
                
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
            getattr(self, "root", self.parent).after(0, lambda: messagebox.showinfo("完成", 
                f"批量扫频测试已完成！\n\n共测试 {total_files} 个文件，成功 {success_count} 个。\n\n录音文件已保存至: {save_dir}"))
        
        except Exception as e:
            self.update_sweep_info(f"批量测试出错: {str(e)}")
            self.sweep_status_var.set("批量测试出错")
            getattr(self, "root", self.parent).after(0, lambda: messagebox.showerror("错误", f"批量测试过程中出错:\n{str(e)}"))
        
        finally:
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_sweep_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            
            # 清除停止标志
            if hasattr(self, 'stop_requested'):
                self.stop_requested = False

    def _batch_test_single_file(self, sweep_file, sweep_type, recording_duration, save_dir, device_id):
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
            if device_id:
                push_cmd = f"adb -s {device_id} push \"{source_path}\" {device_audio_path}"
            else:
                push_cmd = f"adb push \"{source_path}\" {device_audio_path}"
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
                if device_id:
                    subprocess.run(f"adb -s {device_id} shell killall audioserver", shell=True)
                else:
                    subprocess.run("adb shell killall audioserver", shell=True)
                time.sleep(0.5)
            
            # 开始录制
            self.update_sweep_info("开始录制...")
            if device_id:
                tinycap_cmd = f"adb -s {device_id} shell tinycap {device_recording_path} -d {recording_device} -c {recording_channels} -r {recording_rate} -p {recording_periods}"
            else:
                tinycap_cmd = f"adb shell tinycap {device_recording_path} -d {recording_device} -c {recording_channels} -r {recording_rate} -p {recording_periods}"
            
            self.update_sweep_info(f"执行录音命令: {tinycap_cmd}")
            recording_process = subprocess.Popen(tinycap_cmd, shell=True)
            
            # 等待录制启动
            time.sleep(1)
            
            # 播放音频
            self.update_sweep_info("开始播放音频...")
            if device_id:
                tinyplay_cmd = f"adb -s {device_id} shell tinyplay {device_audio_path} -d 0"
            else:
                tinyplay_cmd = f"adb shell tinyplay {device_audio_path} -d 0"
            
            self.update_sweep_info(f"执行播放命令: {tinyplay_cmd}")
            playback_process = subprocess.Popen(tinyplay_cmd, shell=True)
            
            # 等待指定的录制时长
            self.update_sweep_info(f"录制中，将在 {recording_duration} 秒后停止...")
            time.sleep(recording_duration)
            
            # 停止播放和录制
            self.update_sweep_info("停止播放...")
            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinyplay", shell=True)
            else:
                subprocess.run("adb shell killall tinyplay", shell=True)
            
            self.update_sweep_info("停止录制...")
            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinycap", shell=True)
            else:
                subprocess.run("adb shell killall tinycap", shell=True)
            
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
            if device_id:
                pull_cmd = f"adb -s {device_id} pull {device_recording_path} \"{local_path}\""
            else:
                pull_cmd = f"adb pull {device_recording_path} \"{local_path}\""
            pull_result = subprocess.run(pull_cmd, shell=True, capture_output=True, text=True)
            
            # 清理设备上的临时文件
            if device_id:
                subprocess.run(f"adb -s {device_id} shell rm {device_audio_path}", shell=True)
                subprocess.run(f"adb -s {device_id} shell rm {device_recording_path}", shell=True)
            else:
                subprocess.run(f"adb shell rm {device_audio_path}", shell=True)
                subprocess.run(f"adb shell rm {device_recording_path}", shell=True)
            
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
                # 直接构建adb命令，避免递归调用
                device_id = self.device_var.get() if hasattr(self, 'device_var') else ""
                if device_id:
                    kill_cmd = f"adb -s {device_id} shell killall tinycap"
                else:
                    kill_cmd = "adb shell killall tinycap"
                subprocess.run(kill_cmd, shell=True)
                self.update_sweep_info("已停止录制")
            
            # 拉取录音文件
            self.pull_sweep_recording()
            
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_sweep_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_sweep_button.config(state="disabled"))
            
        except Exception as e:
            getattr(self, "root", self.parent).after(0, lambda: self.update_sweep_info(f"监控播放过程中出错: {str(e)}"))
            getattr(self, "root", self.parent).after(0, lambda: self.sweep_status_var.set("监控出错"))
            # 恢复按钮状态
            getattr(self, "root", self.parent).after(0, lambda: self.start_sweep_button.config(state="normal"))
            getattr(self, "root", self.parent).after(0, lambda: self.stop_sweep_button.config(state="disabled"))

    def stop_sweep_test(self, handler=None):
        """停止扫频测试"""
        try:
            self.update_sweep_info("正在停止测试...")
            
            # 设置停止标志，用于批量测试
            self.stop_requested = True
            
            # 直接构建adb命令，避免递归调用
            device_id = self.device_var.get() if hasattr(self, 'device_var') else ""
            
            # 停止播放进程
            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinyplay", shell=True)
            else:
                subprocess.run("adb shell killall tinyplay", shell=True)
                
            # 停止录制进程
            if device_id:
                subprocess.run(f"adb -s {device_id} shell killall tinycap", shell=True)
            else:
                subprocess.run("adb shell killall tinycap", shell=True)
            
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

    def browse_sweep_save_path(self):
        """浏览扫频测试保存路径"""
        folder = filedialog.askdirectory(initialdir=self.sweep_save_path_var.get())
        if folder:
            self.sweep_save_path_var.set(folder)
            self.update_sweep_info(f"已设置保存路径: {folder}")

    def browse_audio_file(self):
        """浏览音频文件"""
        file_types = [
            ('音频文件', '*.wav;*.mp3;*.flac;*.ogg;*.m4a'),
            ('WAV文件', '*.wav'),
            ('MP3文件', '*.mp3'),
            ('FLAC文件', '*.flac'),
            ('OGG文件', '*.ogg'),
            ('M4A文件', '*.m4a'),
            ('所有文件', '*.*')
        ]
        
        file = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=file_types
        )
        
        if file:
            self.file_path_var.set(file)
            self.selected_audio_file = file

    def play_local_audio(self):
        """播放本地音频"""
        # 直接委托给 TestOperations（避免错误地使用 self.parent=Tk root）
        try:
            return super().play_local_audio()
        except Exception as e:
            messagebox.showerror("错误", f"播放失败:\n{str(e)}")

    def start_hal_recording(self):
        """开始HAL录音"""
        try:
            return super().start_hal_recording()
        except Exception as e:
            messagebox.showerror("错误", f"开始HAL录音失败:\n{str(e)}")

    def stop_hal_recording(self):
        """停止HAL录音"""
        try:
            return super().stop_hal_recording()
        except Exception as e:
            messagebox.showerror("错误", f"停止HAL录音失败:\n{str(e)}")
    
    def check_audio_devices(self, handler=None):
        """检查可用的音频设备"""
        if handler is None:
            handler = self.parent
        
        if not handler.check_device_selected():
            return
        
        try:
            device_id = handler.device_var.get() if hasattr(handler, 'device_var') else ""
            
            self.update_sweep_info("正在检查可用的音频设备...")
            
            # 检查录制设备
            if device_id:
                check_cmd = f"adb -s {device_id} shell find /proc/asound -name 'pcm*c' -type f"
            else:
                check_cmd = "adb shell find /proc/asound -name 'pcm*c' -type f"
            
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                capture_devices = result.stdout.strip().split('\n')
                capture_info = "可用录制设备:\n"
                for device in capture_devices:
                    if device.strip():
                        # 解析设备信息 /proc/asound/card0/pcm0c/info
                        parts = device.split('/')
                        if len(parts) >= 5:
                            card = parts[3].replace('card', '')
                            pcm = parts[4].replace('pcm', '').replace('c', '')
                            capture_info += f"  卡{card} 设备{pcm}\n"
            else:
                capture_info = "无法获取录制设备信息\n"
            
            # 检查播放设备
            if device_id:
                play_cmd = f"adb -s {device_id} shell find /proc/asound -name 'pcm*p' -type f"
            else:
                play_cmd = "adb shell find /proc/asound -name 'pcm*p' -type f"
            
            play_result = subprocess.run(play_cmd, shell=True, capture_output=True, text=True)
            
            if play_result.returncode == 0:
                playback_devices = play_result.stdout.strip().split('\n')
                playback_info = "可用播放设备:\n"
                for device in playback_devices:
                    if device.strip():
                        # 解析设备信息
                        parts = device.split('/')
                        if len(parts) >= 5:
                            card = parts[3].replace('card', '')
                            pcm = parts[4].replace('pcm', '').replace('p', '')
                            playback_info += f"  卡{card} 设备{pcm}\n"
            else:
                playback_info = "无法获取播放设备信息\n"
            
            # 显示设备信息
            device_info = capture_info + "\n" + playback_info
            self.update_sweep_info(device_info)
            
            # 弹出详细信息窗口
            messagebox.showinfo("音频设备信息", device_info)
            
        except Exception as e:
            self.update_sweep_info(f"检查音频设备失败: {str(e)}")
    