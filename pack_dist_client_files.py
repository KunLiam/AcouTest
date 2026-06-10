# -*- coding: utf-8 -*-
"""
供 Packager.bat / Packager.sh 调用：写入 dist 内客户辅助文件。

- dist/output/README.txt
- dist/启动测试工具.bat（Windows）
- dist/启动测试工具.command（macOS）
- dist/AcouTest.vX.app（macOS：程序本体内置在 .app/Contents/MacOS/）
"""
from __future__ import annotations

import platform
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path

import feature_config

README = """声测大师(AcouTest) 测试数据目录
========================================

本目录下各子目录用途：

  logcat/           Logcat 抓取文件
  screenshots/      设备截图
  mic_test/         麦克风测试录音
  sweep_recordings/ 扫频测试录音
  airtightness/     气密性测试录音（堵mic/不堵mic）
  loopback/         Loopback/Ref 测试录音
  hal_dump/         HAL 录音拉取
  hal_custom/       自定义 HAL 录音拉取
"""


def _resolve_launch_target(dist: Path, app_base: str, exe_name: str) -> tuple[str, str, str]:
    """
    返回 (相对路径, 平台, 启动方式)。
    launch_mode: exec = 直接运行二进制；open = open xxx.app
    """
    app_bundle = dist / f"{app_base}.app"
    embedded_exe = app_bundle / "Contents" / "MacOS" / app_base
    onedir_folder = dist / app_base
    onedir_exe = onedir_folder / app_base
    if platform.system() == "Windows":
        onedir_exe = onedir_folder / exe_name
    onefile_bin = dist / app_base

    if platform.system() == "Windows":
        if onedir_exe.is_file():
            return f"{app_base}\\{exe_name}", "windows", "exec"
        return exe_name, "windows", "exec"

    if embedded_exe.is_file():
        return f"{app_base}.app", "macos", "open"
    if onedir_exe.is_file():
        return f"{app_base}/{app_base}", "macos", "exec"
    if app_bundle.is_dir():
        return f"{app_base}.app", "macos", "open"
    if onefile_bin.is_file():
        return app_base, "macos", "exec"
    return f"{app_base}/{app_base}", "macos", "exec"


def _write_windows_launcher(dist: Path, launch_rel: str) -> None:
    launcher = dist / "启动测试工具.bat"
    lines = [
        "@echo off",
        "chcp 65001 > nul",
        'cd /d "%~dp0"',
        "echo 正在启动声测大师(AcouTest)...",
        f'start "" "{launch_rel}"',
    ]
    bat_body = "\r\n".join(lines) + "\r\n"
    try:
        launcher.write_bytes(bat_body.encode("gbk"))
    except LookupError:
        launcher.write_text(bat_body, encoding="utf-8")


def _write_mac_launcher(dist: Path, launch_rel: str, launch_mode: str, app_bundle_name: str | None = None) -> None:
    launcher = dist / "启动测试工具.command"
    if app_bundle_name and (dist / app_bundle_name).is_dir():
        body = f'''#!/bin/bash
cd "$(dirname "$0")"
echo "正在启动声测大师(AcouTest)..."
open "./{app_bundle_name}"
exit 0
'''
    elif launch_mode == "open":
        body = f'''#!/bin/bash
cd "$(dirname "$0")"
echo "正在启动声测大师(AcouTest)..."
open "{launch_rel}"
'''
    else:
        body = f'''#!/bin/bash
cd "$(dirname "$0")"
echo "正在启动声测大师(AcouTest)..."
nohup "./{launch_rel}" > /dev/null 2>&1 &
disown
exit 0
'''
    launcher.write_text(body, encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_app_icon(root: Path, resources_dir: Path) -> None:
    """复制 .icns 到 .app/Resources；若无 icns 则在 macOS 上从 PNG 生成。"""
    logo_dir = root / "logo"
    icns_src = logo_dir / "AcouTest.icns"
    icns_dst = resources_dir / "AppIcon.icns"
    if icns_src.is_file():
        shutil.copy2(icns_src, icns_dst)
        return
    if platform.system() != "Darwin":
        return
    png = logo_dir / "AcouTest.png"
    if not png.is_file():
        return
    iconset = resources_dir / "AppIcon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    size_map = {
        "icon_16x16.png": 16,
        "icon_32x32.png": 32,
        "icon_128x128.png": 128,
        "icon_256x256.png": 256,
        "icon_512x512.png": 512,
    }
    for name, px in size_map.items():
        subprocess.run(
            ["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / name)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns_dst)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if iconset.exists():
        shutil.rmtree(iconset, ignore_errors=True)


def _slim_macos_frameworks(frameworks_dir: Path) -> None:
    """打包后剔除无用资源（勿 strip 动态库，否则会破坏签名导致双击闪退）。"""
    if platform.system() != "Darwin" or not frameworks_dir.is_dir():
        return
    pygame_dir = frameworks_dir / "pygame"
    if pygame_dir.is_dir():
        for name in ("pygame_icon_mac.bmp", "pygame_icon.bmp", "pygame_icon.icns"):
            p = pygame_dir / name
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass


def _write_info_plist(plist_path: Path, app_base: str, ver: str) -> None:
    data = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": "声测大师(AcouTest)",
        "CFBundleExecutable": app_base,
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": f"com.acoutest.{app_base.lower().replace('.', '-')}",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "AcouTest",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": str(ver),
        "CFBundleVersion": str(ver),
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
    }
    with plist_path.open("wb") as fp:
        plistlib.dump(data, fp)


def _create_macos_app_bundle(dist: Path, root: Path, app_base: str, ver: str) -> str | None:
    """
    将 PyInstaller onedir 产物打入 dist/AcouTest.vX.app/Contents/MacOS/，
    客户只需 .app；audio/output 等资源仍放在与 .app 同级的 dist 目录（由你打包 zip 时一并提供）。
    """
    onedir_folder = dist / app_base
    onedir_exe = onedir_folder / app_base
    if not onedir_exe.is_file():
        return None
    if platform.system() != "Darwin":
        return None

    app_name = f"{app_base}.app"
    app_path = dist / app_name
    if app_path.exists():
        shutil.rmtree(app_path)

    macos_dir = app_path / "Contents" / "MacOS"
    frameworks_dir = app_path / "Contents" / "Frameworks"
    resources_dir = app_path / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    # macOS .app 规范：可执行文件在 MacOS/，Python 与依赖在 Frameworks/
    # （若整包塞进 MacOS/_internal，双击会因找不到 Frameworks/Python 而静默失败）
    exe_dest = macos_dir / app_base
    shutil.copy2(onedir_exe, exe_dest)
    exe_dest.chmod(exe_dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    internal = onedir_folder / "_internal"
    if internal.is_dir():
        for item in internal.iterdir():
            dest = frameworks_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if item.is_dir():
                shutil.copytree(item, dest, symlinks=True)
            else:
                shutil.copy2(item, dest)
    else:
        for item in onedir_folder.iterdir():
            if item.name == app_base:
                continue
            dest = frameworks_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, symlinks=True)
            else:
                shutil.copy2(item, dest)

    _write_info_plist(app_path / "Contents" / "Info.plist", app_base, ver)
    _copy_app_icon(root, resources_dir)
    _slim_macos_frameworks(frameworks_dir)

    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    shutil.rmtree(onedir_folder)
    print(f"[pack_dist] embedded onedir into {app_name}/Contents/MacOS/ (removed dist/{app_base}/)")
    return app_name


def _write_mac_readme(dist: Path, app_bundle_name: str | None) -> None:
    readme = dist / "Mac使用说明.txt"
    if app_bundle_name:
        open_hint = f"双击「{app_bundle_name}」（Finder 种类为「应用程序」）"
    else:
        open_hint = "双击「启动测试工具.command」"
    readme.write_text(
        f"""声测大师(AcouTest) — macOS 使用说明
========================================

【推荐打开方式】
  {open_hint}

【备选方式】
  双击「启动测试工具.command」

【目录说明】
  程序本体已内置在上述 .app 中，无需单独的 AcouTest.v* 文件夹。

  请保持以下资源文件夹与 .app 放在同一目录（交付 zip 时请一并解压）：
    audio/          测试音频
    logo/           图标（可选，程序内已带一份）
    output/         测试数据输出（运行后自动写入）
    elevoc_ukey/    烧 key 相关（若有）
    wakeup_count/   唤醒监测相关（若有）

  首次打开若提示「无法验证开发者」，请：
  系统设置 → 隐私与安全性 → 仍要打开

  语料生成需要本机已安装 ffmpeg（一次性）：
    brew install ffmpeg

  U盘烧 key 功能仅支持 Windows，Mac 上其它功能可正常使用。
""",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    ver = getattr(feature_config, "APP_VERSION", "1.0")
    app_base = f"AcouTest.v{ver}"
    is_windows = platform.system() == "Windows"
    exe_name = f"{app_base}.exe" if is_windows else app_base
    dist = root / "dist"

    out_readme = dist / "output" / "README.txt"
    out_readme.parent.mkdir(parents=True, exist_ok=True)
    out_readme.write_text(README, encoding="utf-8")

    launch_rel, plat, launch_mode = _resolve_launch_target(dist, app_base, exe_name)
    app_bundle_name = None
    if plat == "windows":
        _write_windows_launcher(dist, launch_rel)
    else:
        app_bundle_name = _create_macos_app_bundle(dist, root, app_base, ver)
        if not app_bundle_name:
            print(f"[pack_dist] WARN: could not build embedded .app (missing dist/{app_base}/{app_base})")
        launch_rel, plat, launch_mode = _resolve_launch_target(dist, app_base, exe_name)
        _write_mac_launcher(dist, launch_rel, launch_mode, app_bundle_name)
        _write_mac_readme(dist, app_bundle_name)
        if app_bundle_name:
            print(f"[pack_dist] macOS app: dist/{app_bundle_name}")


if __name__ == "__main__":
    main()
