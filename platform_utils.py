"""跨平台工具：文件管理器、本机 wav 播放、子进程终止、无控制台 subprocess 等。"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
from typing import List, Optional
IS_WINDOWS = platform.system() == "Windows"
IS_DARWIN = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def get_ui_font() -> str:
    if IS_WINDOWS:
        return "Microsoft YaHei UI"
    if IS_DARWIN:
        return "PingFang SC"
    return "Arial"


def get_runtime_base_dir(fallback_dir: Optional[str] = None) -> str:
    """
    PyInstaller 运行时基准目录。
    macOS .app / onedir 均指向 dist 根（与 audio、output、wakeup_count 同级）。
    """
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        if IS_DARWIN and "/Contents/MacOS/" in exe:
            app_bundle = os.path.dirname(os.path.dirname(os.path.dirname(exe)))
            dist_root = os.path.dirname(app_bundle)
            if app_bundle.endswith(".app") and os.path.isdir(dist_root):
                return dist_root
        cur = os.path.dirname(exe)
        for _ in range(5):
            if os.path.isdir(os.path.join(cur, "output")) or os.path.isdir(os.path.join(cur, "audio")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.path.dirname(exe)
    if fallback_dir:
        return os.path.dirname(os.path.abspath(fallback_dir))
    return os.getcwd()


def bootstrap_frozen_runtime_cwd() -> None:
    """打包后启动时切换到 dist 根目录，避免 Finder 打开 .app 时 cwd 为 / 导致路径错乱。"""
    if not getattr(sys, "frozen", False):
        return
    try:
        os.chdir(get_runtime_base_dir())
    except OSError:
        pass


def load_tk_photoimage(master, path: str):
    """加载窗口图标/图片（macOS 系统 Tk 对 PNG 支持差，优先走 Pillow）。"""
    import tkinter as tk

    path = os.path.abspath(path)
    try:
        from PIL import Image, ImageTk

        pil = Image.open(path)
        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGBA")
        max_side = 512
        if max(pil.size) > max_side:
            pil.thumbnail((max_side, max_side), Image.LANCZOS)
        return ImageTk.PhotoImage(pil, master=master)
    except Exception:
        return tk.PhotoImage(file=path, master=master)


def configure_macos_frozen_tk_env() -> None:
    """PyInstaller 在 macOS 使用系统 Tcl/Tk 时不收集脚本；手动补齐环境变量。"""
    if not IS_DARWIN or not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return
    for env_name, folder in (("TCL_LIBRARY", "_tcl_data"), ("TK_LIBRARY", "_tk_data")):
        path = os.path.join(meipass, folder)
        if os.path.isdir(path):
            os.environ[env_name] = path


def configure_macos_ttk_style(style, root) -> None:
    """
    macOS 上 ttk 需使用可绘制主题；打包后优先 classic/alt，源码运行优先 clam。
    """
    if not IS_DARWIN:
        return
    frozen = getattr(sys, "frozen", False)
    themes = ("classic", "alt", "default", "clam", "aqua") if frozen else ("clam", "alt", "default", "aqua")
    try:
        for theme in themes:
            if theme in style.theme_names():
                if style.theme_use() != theme:
                    style.theme_use(theme)
                break
    except Exception:
        pass
    try:
        bg = "#ffffff"
        tab_bg = "#e5e5e5"
        root.configure(bg=bg)
        style.configure(".", background=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground="#111111")
        style.configure("TLabelframe", background=bg)
        style.configure("TLabelframe.Label", background=bg, foreground="#111111")
        style.configure("TNotebook", background=bg, borderwidth=1)
        style.configure("TNotebook.Tab", padding=(12, 6), background=tab_bg)
        style.map("TNotebook.Tab", background=[("selected", bg), ("active", "#f5f5f5")])
    except Exception:
        pass


def safe_show_tk_window(root) -> bool:
    """初始化完成后安全显示主窗口；若窗口已被销毁则返回 False。"""
    if root is None:
        return False
    try:
        if not root.winfo_exists():
            return False
        root.update_idletasks()
        root.update()
        root.lift()
        root.focus_force()
        return True
    except Exception:
        return False


def schedule_macos_ui_repaint(root, style=None, attempts: int = 6) -> None:
    """macOS 打包后偶发 ttk 首帧不绘制，分次刷新。"""
    if not IS_DARWIN or root is None:
        return

    def _tick(left: int = attempts) -> None:
        if left <= 0 or not root.winfo_exists():
            return
        try:
            if style is not None:
                configure_macos_ttk_style(style, root)
            root.update_idletasks()
            root.update()
        except Exception:
            return
        root.after(150, lambda: _tick(left - 1))

    root.after(0, _tick)


def open_path(path: str) -> None:
    """在系统默认应用中打开文件，或在文件管理器中打开目录。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_DARWIN:
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def open_folder(folder: str) -> None:
    """打开文件夹（不存在则创建）。"""
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    open_path(folder)


def subprocess_no_window_kwargs() -> dict:
    """Windows 下隐藏 subprocess 控制台窗口；其它平台返回空 dict。"""
    if not IS_WINDOWS:
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": startupinfo,
    }


def terminate_process(pid: int, tree: bool = False) -> None:
    """终止子进程；Windows 可选 taskkill /T。"""
    if pid <= 0:
        return
    if IS_WINDOWS:
        flag = "/T" if tree else ""
        subprocess.run(
            f"taskkill /F {flag} /PID {pid}".strip(),
            shell=True,
            **subprocess_no_window_kwargs(),
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def find_python_cmd() -> Optional[List[str]]:
    """返回可用于启动脚本的 Python 命令。"""
    if IS_DARWIN or IS_LINUX:
        candidates = [["python3"], ["python"]]
    else:
        candidates = [["python"], ["py", "-3"], ["py"]]
    kw = {"capture_output": True, "text": True, "timeout": 8}
    kw.update(subprocess_no_window_kwargs())
    for cmd in candidates:
        try:
            result = subprocess.run(cmd + ["-c", "import sys; print(sys.version)"], **kw)
            if result.returncode == 0:
                return cmd
        except Exception:
            pass
    return None


_adb_executable_cache: Optional[str] = None


def augment_path_for_gui_app() -> None:
    """macOS 从 .app 启动时 PATH 常不含 Homebrew，补全常见工具目录。"""
    if IS_WINDOWS:
        return
    extra = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        os.path.join(os.path.expanduser("~"), "android-sdk", "platform-tools"),
        os.path.join(os.path.expanduser("~"), "Library", "Android", "sdk", "platform-tools"),
    ]
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if android_home:
        extra.insert(0, os.path.join(android_home, "platform-tools"))
    cur = os.environ.get("PATH", "")
    parts = cur.split(os.pathsep) if cur else []
    prefix = []
    for d in extra:
        if d and os.path.isdir(d) and d not in parts:
            prefix.append(d)
    if prefix:
        os.environ["PATH"] = os.pathsep.join(prefix + parts)


def resolve_adb_executable() -> str:
    """
    定位 adb 可执行文件。
    GUI 应用（尤其 macOS .app）的 PATH 往往不含 /opt/homebrew/bin，直接调用 adb 会失败。
    """
    global _adb_executable_cache
    if _adb_executable_cache:
        return _adb_executable_cache

    candidates: List[str] = []
    for key in ("ACOUTEST_ADB", "ADB"):
        val = os.environ.get(key, "").strip()
        if val:
            candidates.append(val)

    found = shutil.which("adb")
    if found:
        candidates.append(found)

    home = os.path.expanduser("~")
    sdk_roots = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        os.path.join(home, "Library", "Android", "sdk"),
        os.path.join(home, "android-sdk"),
        os.path.join(home, "Android", "Sdk"),
    ]
    for root in sdk_roots:
        if root:
            candidates.append(os.path.join(root, "platform-tools", "adb"))

    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        candidates.append(os.path.join(d, "adb"))

    seen = set()
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        path = os.path.abspath(os.path.expanduser(raw))
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _adb_executable_cache = path
            return path

    _adb_executable_cache = "adb"
    return _adb_executable_cache


def quote_shell_arg(path: str) -> str:
    """shell=True 时对可执行路径加引号。"""
    if not path or " " not in path:
        return path
    return f'"{path}"'


def local_wav_player_cmd(wav_path: str) -> Optional[List[str]]:
    """
    返回播放 wav 的命令行；Windows 返回 None（由 winsound 处理）。
    macOS 使用 afplay；Linux 优先 aplay。
    """
    wav_path = os.path.abspath(wav_path)
    if IS_WINDOWS:
        return None
    if IS_DARWIN:
        return ["afplay", wav_path]
    if shutil.which("aplay"):
        return ["aplay", "-q", wav_path]
    if shutil.which("afplay"):
        return ["afplay", wav_path]
    raise RuntimeError("未找到本机 wav 播放器（macOS 需 afplay，Linux 需 aplay）。")


def play_local_wav_blocking(wav_path: str, timeout: Optional[float] = None) -> None:
    """阻塞播放本地 wav。"""
    if IS_WINDOWS:
        import winsound

        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        return
    cmd = local_wav_player_cmd(wav_path)
    assert cmd is not None
    subprocess.run(cmd, timeout=timeout, capture_output=True)


def popen_local_wav(wav_path: str) -> subprocess.Popen:
    """非阻塞启动本地 wav 播放子进程（非 Windows）。"""
    cmd = local_wav_player_cmd(wav_path)
    assert cmd is not None
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_local_wav_playback(proc: Optional[subprocess.Popen] = None) -> None:
    """停止 winsound 或 afplay/aplay 子进程。"""
    if IS_WINDOWS:
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass


def elevoc_supported() -> bool:
    """elevoc soft_encryption.dll 仅 Windows 可用。"""
    return IS_WINDOWS


def elevoc_platform_error() -> str:
    return (
        "「烧大象 key / U 盘烧 key」依赖 Windows 版 soft_encryption.dll，"
        "当前系统为 macOS/Linux，无法在本地生成 license。\n\n"
        "请在 Windows 电脑上使用该功能，或改用「sn烧key」中仅依赖 adb 写入 unifykeys 的流程（若设备支持）。"
    )
