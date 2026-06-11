"""生成 AcouTest 图标：Tk PNG / Windows ICO / macOS ICNS（透明边距，Dock 圆角正常）。"""
from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

LOGO_DIR = "logo"
# macOS 应用图标圆角半径 ≈ 边长 22.37%（Big Sur+ squircle 近似）
MAC_ICON_CORNER_RATIO = 0.2237
MAC_ICON_CONTENT_RATIO = 0.68
MAC_ICONSET_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def find_logo_source() -> str:
    """优先使用带透明通道的源图，避免误用白底 Tk PNG。"""
    if not os.path.isdir(LOGO_DIR):
        raise FileNotFoundError("logo 目录不存在")

    preferred = [
        os.path.join(LOGO_DIR, "AcouTest_source.png"),
        os.path.join(LOGO_DIR, "AcouTest_icon.png"),
    ]
    for path in preferred:
        if os.path.isfile(path):
            return path

    skip_names = {"AcouTest.png"}
    extras = sorted(glob.glob(os.path.join(LOGO_DIR, "*.png")))
    for path in extras:
        if os.path.basename(path) not in skip_names:
            return path

    fallback = os.path.join(LOGO_DIR, "AcouTest.png")
    if os.path.isfile(fallback):
        return fallback

    jpg_files = glob.glob(os.path.join(LOGO_DIR, "*.jpg")) + glob.glob(os.path.join(LOGO_DIR, "*.jpeg"))
    if jpg_files:
        return jpg_files[0]

    raise FileNotFoundError("logo 目录中没有可用的 PNG/JPG 源图")


def load_logo_rgba(source_path: str | None = None) -> Image.Image:
    source_path = source_path or find_logo_source()
    img = Image.open(source_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def build_macos_dock_icon(
    img: Image.Image,
    canvas_size: int = 1024,
    bg_rgba: tuple = (255, 255, 255, 255),
) -> Image.Image:
    """生成 macOS Dock 风格图标：圆角矩形底 + 居中 logo（与系统其他图标一致）。"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    radius = max(8, int(canvas_size * MAC_ICON_CORNER_RATIO))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [0, 0, canvas_size - 1, canvas_size - 1],
        radius=radius,
        fill=bg_rgba,
    )

    content_max = max(64, int(canvas_size * MAC_ICON_CONTENT_RATIO))
    content = img.copy()
    content.thumbnail((content_max, content_max), Image.LANCZOS)
    x = (canvas_size - content.width) // 2
    y = (canvas_size - content.height) // 2
    canvas.paste(content, (x, y), content)
    return canvas


def prepare_app_icon_rgba(
    img: Image.Image,
    canvas_size: int = 1024,
    content_scale: float = 0.82,
) -> Image.Image:
    """macOS / Windows 通用：圆角 Dock 风格图标。"""
    _ = content_scale
    return build_macos_dock_icon(img, canvas_size=canvas_size)


def save_tk_png(app_icon: Image.Image, png_path: str, max_side: int = 512) -> None:
    """Tk/macOS Tcl 兼容：8-bit RGB + 白底，尺寸不宜过大。"""
    tk_img = Image.new("RGB", app_icon.size, (255, 255, 255))
    tk_img.paste(app_icon, mask=app_icon.split()[3])
    if max(tk_img.size) > max_side:
        tk_img = tk_img.copy()
        tk_img.thumbnail((max_side, max_side), Image.LANCZOS)
    tk_img.save(png_path, format="PNG", optimize=False)


def save_ico(app_icon: Image.Image, ico_path: str) -> None:
    resized_images = [app_icon.resize(size, Image.LANCZOS) for size in ICO_SIZES]
    resized_images[0].save(
        ico_path,
        format="ICO",
        sizes=ICO_SIZES,
        append_images=resized_images[1:],
    )


def build_icns_from_rgba(
    app_icon: Image.Image,
    icns_path: str,
    iconset_dir: str | None = None,
) -> bool:
    """用 iconutil 生成 macOS .icns（需在 macOS 上运行）。"""
    if platform.system() != "Darwin":
        return False

    if app_icon.size != (1024, 1024):
        app_icon = app_icon.resize((1024, 1024), Image.LANCZOS)

    iconset = iconset_dir or os.path.join(LOGO_DIR, "AcouTest.iconset")
    if os.path.isdir(iconset):
        shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset, exist_ok=True)

    for name, px in MAC_ICONSET_SIZES.items():
        resized = app_icon.resize((px, px), Image.LANCZOS)
        resized.save(os.path.join(iconset, name), format="PNG")

    os.makedirs(os.path.dirname(icns_path) or ".", exist_ok=True)
    result = subprocess.run(
        ["iconutil", "-c", "icns", iconset, "-o", icns_path],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(iconset, ignore_errors=True)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        print(f"[convert_icon] iconutil 失败: {err}")
        return False
    return os.path.isfile(icns_path)


def convert_all(source_path: str | None = None) -> dict:
    os.makedirs(LOGO_DIR, exist_ok=True)
    source = source_path or find_logo_source()
    print(f"找到图片: {source}")

    raw = load_logo_rgba(source)
    print(f"原始图片尺寸: {raw.width}x{raw.height}")

    app_icon = prepare_app_icon_rgba(raw, canvas_size=1024, content_scale=0.82)

    icon_png = os.path.join(LOGO_DIR, "AcouTest_icon.png")
    app_icon.save(icon_png, format="PNG")
    print(f"已保存 macOS 图标源 PNG: {icon_png} (1024x1024 RGBA)")

    tk_png = os.path.join(LOGO_DIR, "AcouTest.png")
    save_tk_png(app_icon, tk_png, max_side=512)
    print(f"已保存 Tk 兼容 PNG: {tk_png}")

    ico_path = os.path.join(LOGO_DIR, "AcouTest.ico")
    save_ico(app_icon, ico_path)
    print(f"已保存 ICO: {ico_path}")

    icns_path = os.path.join(LOGO_DIR, "AcouTest.icns")
    icns_ok = build_icns_from_rgba(app_icon, icns_path)
    if icns_ok:
        kb = os.path.getsize(icns_path) / 1024
        print(f"已保存 macOS ICNS: {icns_path} ({kb:.1f} KB)")
    else:
        print("未生成 ICNS（非 macOS 或 iconutil 不可用；在 Mac 上打包时会自动重试）")

    return {
        "source": source,
        "icon_png": icon_png,
        "tk_png": tk_png,
        "ico": ico_path,
        "icns": icns_path if icns_ok else "",
    }


if __name__ == "__main__":
    try:
        print("开始转换图标...")
        convert_all()
        print("图标转换完成。")
    except Exception as exc:
        print(f"转换图标时出错: {exc}")
        sys.exit(1)
