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
import urllib.request
import urllib.error
import json
import tempfile

from ui_components import UIComponents
from devices_operations import DeviceOperations
from test_operations import TestOperations
from optional_deps import try_import_pygame
from output_paths import get_output_dir, DIR_MIC_TEST
from feature_config import (
    APP_VERSION,
    UPDATE_MANIFEST_URL,
    UPDATE_MANIFEST_URLS,
    UPDATE_MANIFEST_URL_PUBLIC,
    UPDATE_MANIFEST_URLS_PUBLIC,
    UPDATE_MANIFEST_URL_INTERNAL,
    UPDATE_MANIFEST_URLS_INTERNAL,
    RELEASE_CHANNEL,
    UPDATE_AUTO_CHECK,
)
from control_api import AcouTestControlApi
import updater_http

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
        self.control_api_conn_var = tk.StringVar(value="OpenClaw: 未连接")
        self._control_last_activity_ts = 0.0
        self._control_last_client_ip = ""
        self._control_request_count = 0
        self._openclaw_action_context = ""
        
        # 尝试初始化 pygame 混音器（失败不影响其它功能）
        self._init_pygame_mixer()
        
        # 创建界面
        self.create_widgets()
        
        # 检查ADB设备
        self.refresh_devices()

        # 定时后台刷新设备列表（换插 USB 后自动更新下拉框）；ACOUTEST_ADB_POLL_MS=0 可关闭
        self._adb_device_poll_stop = False
        try:
            self._adb_device_poll_ms = int(os.environ.get("ACOUTEST_ADB_POLL_MS", "2500"))
        except Exception:
            self._adb_device_poll_ms = 2500
        if self._adb_device_poll_ms > 0:
            self._schedule_adb_device_autopoll()

        # 键盘挂载：当应用获得焦点时，用电脑键盘通过 ADB 给设备输入
        self._setup_keyboard_adb_input()

        # 启动本地 HTTP 控制接口（供 OpenClaw 调用）
        self.control_api = None
        self._start_control_api()
        self._schedule_control_api_indicator_refresh()

        # 启动时异步检查更新（不阻塞主界面）
        self._update_dialog = None
        self.root.after(1200, self._check_update_on_startup)

        # 关闭窗口时，先停接口服务再退出
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        
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

    def _start_control_api(self):
        """启动本地控制接口服务。"""
        host = os.environ.get("ACOUTEST_API_HOST", "127.0.0.1")
        port_raw = os.environ.get("ACOUTEST_API_PORT", "8765")
        token = os.environ.get("ACOUTEST_API_TOKEN", "acoutest-local-token")
        try:
            port = int(port_raw)
        except Exception:
            port = 8765
        try:
            self.control_api = AcouTestControlApi(self, host=host, port=port, token=token)
            info = self.control_api.start()
            print(f"控制接口已启动: http://{info['host']}:{info['port']}  token={info['token_hint']}")
            try:
                self.status_var.set(f"控制接口已启动 {info['host']}:{info['port']}")
                self.control_api_conn_var.set(f"OpenClaw: 等待连接 ({info['host']}:{info['port']})")
            except Exception:
                pass
        except Exception as e:
            print(f"控制接口启动失败: {e}")
            try:
                self.control_api_conn_var.set("OpenClaw: 接口启动失败")
            except Exception:
                pass

    def on_control_api_activity(self, info):
        """由控制接口线程回调，记录 OpenClaw 请求活动。"""
        try:
            self._control_last_activity_ts = float((info or {}).get("ts") or time.time())
        except Exception:
            self._control_last_activity_ts = time.time()
        self._control_last_client_ip = str((info or {}).get("client_ip") or "")
        try:
            self._control_request_count = int((info or {}).get("request_count") or 0)
        except Exception:
            pass
        try:
            self.root.after(0, self._refresh_control_api_indicator)
        except Exception:
            pass

    def append_openclaw_log(self, message):
        """线程安全：追加一条 OpenClaw 日志到界面。"""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        try:
            if getattr(self, "root", None) and self.root.winfo_exists():
                self.root.after(0, lambda: self._append_openclaw_log_text(line))
        except Exception:
            pass

    def log_openclaw_adb(self, command):
        """记录由 OpenClaw 触发的 ADB 命令。"""
        action = (getattr(self, "_openclaw_action_context", "") or "").strip()
        prefix = f"[{action}] " if action else ""
        self.append_openclaw_log(f"{prefix}ADB: {command}")

    def _schedule_control_api_indicator_refresh(self):
        """每秒刷新 OpenClaw 连接状态文本。"""
        try:
            self._refresh_control_api_indicator()
        finally:
            if getattr(self, "root", None) and self.root.winfo_exists():
                self.root.after(1000, self._schedule_control_api_indicator_refresh)

    def _refresh_control_api_indicator(self):
        now = time.time()
        last_ts = float(getattr(self, "_control_last_activity_ts", 0.0) or 0.0)
        ip = (getattr(self, "_control_last_client_ip", "") or "").strip()
        cnt = int(getattr(self, "_control_request_count", 0) or 0)
        if last_ts <= 0:
            self.control_api_conn_var.set("OpenClaw: 未连接")
            return
        delta = max(0.0, now - last_ts)
        if delta <= 15.0:
            who = ip or "unknown"
            self.control_api_conn_var.set(f"OpenClaw: 已连接 ({who}, {delta:.1f}s前, #{cnt})")
        else:
            who = ip or "unknown"
            self.control_api_conn_var.set(f"OpenClaw: 未连接 (最近 {who}, {int(delta)}s前, #{cnt})")

    def _schedule_adb_device_autopoll(self):
        """定时在后台执行 adb devices，主线程更新下拉框，避免阻塞 UI。"""
        def tick():
            if getattr(self, "_adb_device_poll_stop", False):
                return
            ms = getattr(self, "_adb_device_poll_ms", 0) or 0
            if ms <= 0:
                return
            try:
                self.refresh_devices_async()
            except Exception:
                pass
            try:
                self.root.after(ms, tick)
            except Exception:
                pass

        ms = getattr(self, "_adb_device_poll_ms", 2500)
        try:
            self.root.after(ms, tick)
        except Exception:
            pass

    def _on_app_close(self):
        """应用关闭清理。"""
        self._adb_device_poll_stop = True
        try:
            if getattr(self, "control_api", None):
                self.control_api.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ========== 自动更新 ==========
    def _check_update_on_startup(self):
        """启动后自动检查更新（可通过环境变量关闭）。"""
        if not bool(UPDATE_AUTO_CHECK):
            return
        auto_flag = str(os.environ.get("ACOUTEST_UPDATE_AUTO_CHECK", "1")).strip().lower()
        if auto_flag in ("0", "false", "no", "off"):
            return
        self._check_update_async(manual=False)

    def _split_manifest_urls(self, value):
        out = []
        if isinstance(value, str):
            parts = [x.strip() for x in value.replace(";", ",").split(",")]
            out.extend([x for x in parts if x])
        elif isinstance(value, (list, tuple)):
            for x in value:
                s = str(x or "").strip()
                if s:
                    out.append(s)
        return out

    def _get_update_manifest_urls(self):
        """
        获取更新清单地址列表（按优先级）：
        1) 环境变量 ACOUTEST_UPDATE_MANIFEST_URL（覆盖通道）
        2) 按 RELEASE_CHANNEL 使用对应通道清单：public -> UPDATE_MANIFEST_URL_PUBLIC，internal -> UPDATE_MANIFEST_URL_INTERNAL
        3) 安装目录 update_config.json 中 manifest_url / manifest_urls
        4) 兼容：UPDATE_MANIFEST_URL / UPDATE_MANIFEST_URLS
        5) 安装目录 update_manifest.json（本地文件）
        """
        urls = []
        env_urls = str(os.environ.get("ACOUTEST_UPDATE_MANIFEST_URL", "")).strip()
        urls.extend(self._split_manifest_urls(env_urls))
        if not urls:
            channel = str(RELEASE_CHANNEL or "public").strip().lower()
            if channel == "internal":
                urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URL_INTERNAL))
                urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URLS_INTERNAL))
            else:
                urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URL_PUBLIC))
                urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URLS_PUBLIC))
        if not urls:
            urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URL))
            urls.extend(self._split_manifest_urls(UPDATE_MANIFEST_URLS))

        base_dir = self._get_runtime_base_dir()
        cfg_path = os.path.join(base_dir, "update_config.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f) or {}
                urls.extend(self._split_manifest_urls(cfg.get("manifest_url")))
                urls.extend(self._split_manifest_urls(cfg.get("manifest_urls")))
            except Exception:
                pass

        local_manifest = os.path.join(base_dir, "update_manifest.json")
        if os.path.isfile(local_manifest):
            urls.append(local_manifest)

        # 去重并保持顺序
        dedup = []
        seen = set()
        for u in urls:
            key = str(u).strip()
            if not key or key in seen:
                continue
            # 本地路径支持：若是相对路径，则按 exe 同目录解析
            if not key.lower().startswith(("http://", "https://")) and not os.path.isabs(key):
                key = os.path.join(base_dir, key)
            seen.add(key)
            dedup.append(key)
        return dedup

    def _parse_version_key(self, ver):
        nums = re.findall(r"\d+", str(ver or "0"))
        vals = [int(n) for n in nums[:4]]
        while len(vals) < 4:
            vals.append(0)
        return tuple(vals)

    def _fetch_update_manifest(self, manifest_url):
        """读取更新清单 JSON，支持 http(s) 和本地文件路径。"""
        if not manifest_url:
            return None
        raw = ""
        if manifest_url.lower().startswith(("http://", "https://")):
            req = urllib.request.Request(manifest_url, headers={"User-Agent": "AcouTest-Updater/1.0"})
            opener = updater_http.urlopen if manifest_url.lower().startswith("https://") else urllib.request.urlopen
            with opener(req, timeout=10) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                raw = resp.read().decode(charset, errors="replace")
        else:
            with open(manifest_url, "r", encoding="utf-8") as f:
                raw = f.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return data

    def _normalize_update_info(self, manifest):
        latest = str((manifest or {}).get("latest_version") or "").strip()
        if not latest:
            return None
        current = str(APP_VERSION).strip()
        if self._parse_version_key(latest) <= self._parse_version_key(current):
            return None

        notes = (manifest or {}).get("notes", "")
        if isinstance(notes, list):
            notes_text = "\n".join([f"• {str(x)}" for x in notes if str(x).strip()])
        else:
            notes_text = str(notes or "").strip()
        download_url = str((manifest or {}).get("download_url") or "").strip()
        if not download_url:
            return None
        apk_url = str((manifest or {}).get("wakeup_count_apk_url") or "").strip()
        if apk_url and not apk_url.lower().startswith(("http://", "https://")):
            apk_url = ""
        out = {
            "current_version": current,
            "latest_version": latest,
            "publish_date": str((manifest or {}).get("publish_date") or "").strip(),
            "notes": notes_text,
            "download_url": download_url,
        }
        if apk_url:
            out["wakeup_count_apk_url"] = apk_url
        return out

    def _check_update_async(self, manual=False):
        def _worker():
            try:
                manifest_urls = self._get_update_manifest_urls()
                if not manifest_urls:
                    if manual:
                        base_dir = self._get_runtime_base_dir()
                        cfg_path = os.path.join(base_dir, "update_config.json")
                        self.root.after(
                            0,
                            lambda b=base_dir, c=cfg_path: messagebox.showinfo(
                                "检查更新",
                                "未配置更新地址。\n\n"
                                "请设置以下任一项：\n"
                                "1) feature_config.py -> UPDATE_MANIFEST_URL / UPDATE_MANIFEST_URLS\n"
                                "2) 环境变量 ACOUTEST_UPDATE_MANIFEST_URL\n"
                                "3) 在安装目录放 update_config.json\n\n"
                                f"当前安装目录: {b}\n"
                                f"期望配置文件: {c}",
                            ),
                        )
                    return
                manifest = None
                last_err = ""
                tried = []
                for url in manifest_urls:
                    tried.append(url)
                    try:
                        manifest = self._fetch_update_manifest(url)
                        if isinstance(manifest, dict):
                            break
                    except Exception as e:
                        last_err = str(e)
                        continue
                if not isinstance(manifest, dict):
                    raise RuntimeError(
                        "所有更新源均不可用。\n\n"
                        f"尝试地址:\n- " + "\n- ".join(tried) + "\n\n"
                        f"最后错误: {last_err or '未知错误'}"
                    )
                info = self._normalize_update_info(manifest)
                if not info:
                    if manual:
                        apk_u = str((manifest or {}).get("wakeup_count_apk_url") or "").strip()
                        if apk_u and apk_u.lower().startswith(("http://", "https://")):
                            self.root.after(0, lambda u=apk_u: self._offer_sync_wakeup_apk_when_up_to_date(u))
                        else:
                            self.root.after(0, lambda: messagebox.showinfo("检查更新", f"当前已是最新版本（v{APP_VERSION}）。"))
                    return
                self.root.after(0, lambda i=info: self._show_update_dialog(i))
            except Exception as e:
                if manual:
                    self.root.after(0, lambda m=str(e): messagebox.showerror("检查更新失败", m))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_update_dialog(self, info):
        if self._update_dialog and self._update_dialog.winfo_exists():
            try:
                self._update_dialog.lift()
                self._update_dialog.focus_force()
            except Exception:
                pass
            return

        win = tk.Toplevel(self.root)
        self._update_dialog = win
        win.title("发现新版本")
        win.geometry("520x360")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self._close_update_dialog(w))
        self._apply_window_icon(win)

        top = tk.Frame(win, bg="#2d9cff", height=78)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="发现新版本", bg="#2d9cff", fg="white", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(top, text=f"v{info['latest_version']}", bg="#2d9cff", fg="white", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=16, pady=(0, 10))

        body = tk.Frame(win, bg="white")
        body.pack(fill="both", expand=True)
        date_text = info.get("publish_date") or time.strftime("%Y-%m-%d")
        tk.Label(body, text=f"发布日期：{date_text}", bg="white", fg="#333", anchor="w", font=("Microsoft YaHei UI", 10)).pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(body, text="更新说明", bg="white", fg="#111", anchor="w", font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x", padx=16, pady=(6, 4))

        foot = tk.Frame(body, bg="white")
        # 先固定底部按钮区，避免在小窗口或高 DPI 下被说明文本挤出可视范围
        foot.pack(side="bottom", fill="x", padx=16, pady=(6, 14))
        tk.Button(foot, text="稍后再说", width=10, command=lambda w=win: self._close_update_dialog(w)).pack(side="right")
        tk.Button(
            foot,
            text="立即更新",
            width=10,
            bg="#2d9cff",
            fg="white",
            command=lambda i=info: self._download_and_apply_update(i, win),
        ).pack(side="right", padx=(0, 10))

        notes_box = tk.Text(body, height=9, wrap="word", font=("Microsoft YaHei UI", 10), bg="white", bd=0)
        notes_box.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        notes_box.insert("1.0", info.get("notes") or "修复若干问题，优化使用体验。")
        notes_box.config(state="disabled")

    def _close_update_dialog(self, win=None):
        target = win or getattr(self, "_update_dialog", None)
        if not target:
            self._update_dialog = None
            return
        try:
            target.grab_release()
        except Exception:
            pass
        try:
            target.destroy()
        except Exception:
            pass
        finally:
            self._update_dialog = None

    def _offer_sync_wakeup_apk_when_up_to_date(self, apk_url):
        """
        已是最新版本时仍允许从清单里的 wakeup_count_apk_url 单独拉取 APK。
        典型场景：曾用不含 APK 同步逻辑的旧 exe 完成升级；或线上清单晚于首次升级才补上 apk 地址。
        """
        if not messagebox.askyesno(
            "检查更新",
            f"当前已是最新版本（v{APP_VERSION}）。\n\n"
            "在线清单提供了 AudioPlayer.apk 下载地址，是否下载到安装目录下的 wakeup_count 文件夹？\n\n"
            "若您刚升级 exe 后发现 APK 未更新，或需重新覆盖 APK，请选「是」。",
        ):
            return
        self._download_wakeup_count_apk_only(apk_url)

    def _download_wakeup_count_apk_only(self, apk_url):
        """仅下载清单中的设备端 APK 到 wakeup_count/AudioPlayer.apk（不升级 exe）。"""
        url = str(apk_url or "").strip()
        if not url:
            return
        prog = tk.Toplevel(self.root)
        prog.title("正在下载 AudioPlayer.apk")
        prog.geometry("420x120")
        prog.resizable(False, False)
        prog.transient(self.root)
        self._apply_window_icon(prog)
        tk.Label(prog, text="正在下载 AudioPlayer.apk，请稍候...", anchor="w").pack(fill="x", padx=14, pady=(14, 6))
        bar_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(prog, maximum=100, variable=bar_var).pack(fill="x", padx=14, pady=(0, 6))
        tip_var = tk.StringVar(value="0%")
        tk.Label(prog, textvariable=tip_var, anchor="w", fg="#666").pack(fill="x", padx=14)

        def _worker():
            tmp_dir = tempfile.mkdtemp(prefix="acoutest_apk_")
            apk_tmp = os.path.join(tmp_dir, "AudioPlayer.apk")
            try:

                def _prog(done, total):
                    if total > 0:
                        pct = max(0.0, min(100.0, (done * 100.0) / total))
                    else:
                        pct = 50.0
                    p = pct
                    self.root.after(0, lambda p=p: (bar_var.set(p), tip_var.set(f"{p:.0f}%")))

                self._updater_download_file(url, apk_tmp, timeout=120, progress_cb=_prog)

                def _finish():
                    try:
                        prog.destroy()
                    except Exception:
                        pass
                    try:
                        if not os.path.isfile(apk_tmp):
                            messagebox.showerror("下载失败", "临时文件无效，请检查网络与下载地址。")
                            return
                        install_dir = self._get_runtime_base_dir()
                        wc_dir = os.path.join(install_dir, "wakeup_count")
                        os.makedirs(wc_dir, exist_ok=True)
                        apk_dest = os.path.join(wc_dir, "AudioPlayer.apk")
                        shutil.copy2(apk_tmp, apk_dest)
                        messagebox.showinfo("AudioPlayer.apk", f"已保存：\n{apk_dest}")
                    except Exception as e:
                        messagebox.showerror("保存失败", str(e))
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

                self.root.after(0, _finish)
            except Exception as e:
                def _err():
                    try:
                        prog.destroy()
                    except Exception:
                        pass
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    messagebox.showerror(
                        "下载失败",
                        f"{e}\n\n地址：{url}{self._updater_ssl_error_hint(str(e))}",
                    )

                self.root.after(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    def _updater_ssl_error_hint(self, err_text: str) -> str:
        t = (err_text or "").lower()
        if "certificate" in t or "ssl" in t:
            return (
                "\n\n如为证书校验失败：① 请使用已打入 certifi 的新版安装包；② 公司代理需安装企业根证书；"
                "③ 排查时可设环境变量 ACOUTEST_UPDATE_SSL_INSECURE=1 后重启程序（跳过校验，有风险）。"
            )
        return ""

    def _updater_normalize_request_url(self, download_url):
        parsed = urllib.parse.urlparse(download_url)
        safe_path = urllib.parse.quote(parsed.path, safe="/-_.~()%")
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, safe_path, parsed.params, parsed.query, parsed.fragment)
        )

    def _updater_download_file(self, download_url, dest_path, timeout=120, progress_cb=None):
        """HTTP(S) 下载到本地文件；progress_cb(done_bytes, total_bytes_or_0) 可选。"""
        normalized_url = self._updater_normalize_request_url(download_url)
        req = urllib.request.Request(normalized_url, headers={"User-Agent": "AcouTest-Updater/1.0"})
        opener = updater_http.urlopen if normalized_url.lower().startswith("https://") else urllib.request.urlopen
        with opener(req, timeout=timeout) as resp, open(dest_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)

    def _download_and_apply_update(self, info, dialog):
        download_url = str((info or {}).get("download_url") or "").strip()
        if not download_url:
            messagebox.showerror("更新失败", "缺少下载地址 download_url")
            return

        apk_url = str((info or {}).get("wakeup_count_apk_url") or "").strip()

        prog = tk.Toplevel(self.root)
        prog.title("正在下载更新")
        prog.geometry("420x120")
        prog.resizable(False, False)
        prog.transient(self.root)
        self._apply_window_icon(prog)
        tk.Label(prog, text="正在下载新版本，请稍候...", anchor="w").pack(fill="x", padx=14, pady=(14, 6))
        bar_var = tk.DoubleVar(value=0.0)
        pb = ttk.Progressbar(prog, maximum=100, variable=bar_var)
        pb.pack(fill="x", padx=14, pady=(0, 6))
        tip_var = tk.StringVar(value="0%")
        tk.Label(prog, textvariable=tip_var, anchor="w", fg="#666").pack(fill="x", padx=14)

        def _worker():
            tmp_dir = tempfile.mkdtemp(prefix="acoutest_update_")
            apk_tmp = None
            apk_warn = None
            try:
                parsed = urllib.parse.urlparse(download_url)
                name = os.path.basename(parsed.path) or f"acoutest_update_{int(time.time())}.exe"
                pkg_path = os.path.join(tmp_dir, name)

                def _prog_exe(done, total):
                    if total > 0:
                        pct = max(0.0, min(85.0, (done * 85.0) / total))
                    else:
                        pct = 42.5
                    p = pct
                    self.root.after(0, lambda p=p: (bar_var.set(p), tip_var.set(f"主程序 {p:.0f}%")))

                self._updater_download_file(download_url, pkg_path, timeout=120, progress_cb=_prog_exe)

                if apk_url:
                    apk_tmp = os.path.join(tmp_dir, "AudioPlayer.apk")

                    def _prog_apk(done, total):
                        if total > 0:
                            pct = 85.0 + min(15.0, (done * 15.0) / total)
                        else:
                            pct = 92.5
                        p = pct
                        self.root.after(0, lambda p=p: (bar_var.set(p), tip_var.set(f"AudioPlayer.apk {p:.0f}%")))

                    try:
                        self._updater_download_file(apk_url, apk_tmp, timeout=120, progress_cb=_prog_apk)
                    except Exception as e:
                        apk_tmp = None
                        apk_warn = str(e)

                def _finish_download_ui():
                    bar_var.set(100.0)
                    tip_var.set("下载完成，准备保存到安装目录...")
                    self._save_downloaded_update_file(
                        pkg_path, dialog, prog, apk_tmp_path=apk_tmp, apk_download_warning=apk_warn
                    )

                self.root.after(0, _finish_download_ui)
            except urllib.error.HTTPError as e:
                def _on_http_error():
                    msg = (
                        f"下载失败：HTTP {e.code}\n\n"
                        f"下载地址：{download_url}\n\n"
                        "请检查：\n"
                        "1) 发布页直链是否可访问（无需安装 Git，普通浏览器能打开即可）\n"
                        "2) 文件名与链接是否完全一致（区分大小写）\n"
                        "3) 文件是否已发布、非草稿/非私有"
                    )
                    messagebox.showerror("更新失败", msg)
                self.root.after(0, _on_http_error)
                self.root.after(0, prog.destroy)
            except Exception as e:
                def _dl_err(m=str(e), u=download_url):
                    hint = self._updater_ssl_error_hint(m)
                    messagebox.showerror("更新失败", f"下载失败：{m}\n\n下载地址：{u}{hint}")

                self.root.after(0, _dl_err)
                self.root.after(0, prog.destroy)
        threading.Thread(target=_worker, daemon=True).start()

    def _save_downloaded_update_file(self, pkg_path, dialog, prog_win, apk_tmp_path=None, apk_download_warning=None):
        """将下载包保存到安装目录；可选把 AudioPlayer.apk 写入 wakeup_count。提示用户重启生效。"""
        try:
            install_dir = self._get_runtime_base_dir()
            is_frozen = bool(getattr(sys, "frozen", False))
            current_name = os.path.basename(sys.executable if is_frozen else sys.argv[0])
            base_name = os.path.basename(pkg_path) or "AcouTest_update.exe"
            stem, ext = os.path.splitext(base_name)
            ext = ext.lower()

            if ext == ".exe":
                if base_name.lower() == current_name.lower():
                    base_name = f"{stem}_new.exe"
                target_path = os.path.join(install_dir, base_name)
            else:
                if not ext:
                    base_name = f"{base_name}.exe"
                target_path = os.path.join(install_dir, base_name)

            shutil.copy2(pkg_path, target_path)

            apk_dest_line = ""
            if apk_tmp_path and os.path.isfile(apk_tmp_path):
                wc_dir = os.path.join(install_dir, "wakeup_count")
                os.makedirs(wc_dir, exist_ok=True)
                apk_dest = os.path.join(wc_dir, "AudioPlayer.apk")
                shutil.copy2(apk_tmp_path, apk_dest)
                apk_dest_line = f"\nwakeup_count\\AudioPlayer.apk 已更新：\n{apk_dest}\n"

            self._close_update_dialog(dialog)
            try:
                prog_win.destroy()
            except Exception:
                pass

            message = (
                "新版本已下载完成。\n\n"
                f"保存路径：{target_path}\n"
                f"{apk_dest_line}\n"
                "请关闭当前程序后，双击新的 exe 启动即可生效。"
            )
            if apk_download_warning:
                message += (
                    "\n\n注意：清单中配置了设备端 APK 更新，但本次下载失败，已保留旧版或缺失：\n"
                    + apk_download_warning
                )
            if messagebox.askyesno("更新下载完成", message + "\n\n是否现在打开所在文件夹？"):
                try:
                    if platform.system() == "Windows":
                        os.startfile(install_dir)
                    elif platform.system() == "Darwin":
                        subprocess.run(["open", install_dir])
                    else:
                        subprocess.run(["xdg-open", install_dir])
                except Exception:
                    pass
        except Exception as e:
            try:
                prog_win.destroy()
            except Exception:
                pass
            messagebox.showerror("安装失败", str(e))
        
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
                                           width=26, state="readonly", font=("Arial", 9))
        self.device_combobox.pack(side="left", padx=(0, 5))
        self.device_combobox.bind("<<ComboboxSelected>>", self.on_device_selected)
        # 打开下拉前先刷新设备列表，换设备后点一下设备框即可看到新设备，无需再点「刷新」
        def _refresh_before_dropdown(event=None):
            self.refresh_devices()
        self.device_combobox.bind("<Button-1>", _refresh_before_dropdown)
        self.device_combobox.bind("<Down>", _refresh_before_dropdown)
        
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

        claw_label = ttk.Label(status_bar, textvariable=self.control_api_conn_var, font=("Arial", 9), foreground="#666")
        claw_label.pack(side="right", padx=(0, 12))
        
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
