# -*- coding: utf-8 -*-
"""
PyInstaller --exclude-module 列表（Packager.sh / Packager.bat 共用）。
目标：在不影响功能的前提下减小体积。
"""
from __future__ import annotations

import platform
import sys

# 未使用的 PIL 编解码插件（保留 PNG/JPEG/GIF 等常用格式）
_PIL_UNUSED = (
    "PIL.BlpImagePlugin",
    "PIL.BufrStubImagePlugin",
    "PIL.CurImagePlugin",
    "PIL.DcxImagePlugin",
    "PIL.DdsImagePlugin",
    "PIL.EpsImagePlugin",
    "PIL.FitsImagePlugin",
    "PIL.FliImagePlugin",
    "PIL.FpxImagePlugin",
    "PIL.FtexImagePlugin",
    "PIL.GbrImagePlugin",
    "PIL.GribStubImagePlugin",
    "PIL.Hdf5StubImagePlugin",
    "PIL.ImImagePlugin",
    "PIL.ImtImagePlugin",
    "PIL.IptcImagePlugin",
    "PIL.McIdasImagePlugin",
    "PIL.MicImagePlugin",
    "PIL.MpegImagePlugin",
    "PIL.MspImagePlugin",
    "PIL.PalmImagePlugin",
    "PIL.PcdImagePlugin",
    "PIL.PcxImagePlugin",
    "PIL.PdfImagePlugin",
    "PIL.PixarImagePlugin",
    "PIL.PsdImagePlugin",
    "PIL.SgiImagePlugin",
    "PIL.SpiderImagePlugin",
    "PIL.SunImagePlugin",
    "PIL.TgaImagePlugin",
    "PIL.WalImageFile",
    "PIL.WmfImagePlugin",
    "PIL.XVThumbImagePlugin",
    "PIL.XbmImagePlugin",
    "PIL.XpmImagePlugin",
)

# 标准库中 GUI 工具不需要的模块
_STDLIB_TRIM = (
    "unittest",
    "test",
    "pydoc",
    "tkinter.test",
)


def get_exclude_modules(for_darwin: bool | None = None) -> list[str]:
    if for_darwin is None:
        for_darwin = platform.system() == "Darwin"
    mods = ["numpy", *_PIL_UNUSED, *_STDLIB_TRIM]
    # macOS：语料生成改用系统 ffmpeg（brew install ffmpeg），不内置 47MB 的 imageio_ffmpeg
    if for_darwin:
        mods.append("imageio_ffmpeg")
    return mods


def pyinstaller_exclude_argv(for_darwin: bool | None = None) -> list[str]:
    argv: list[str] = []
    for name in get_exclude_modules(for_darwin):
        argv.extend(["--exclude-module", name])
    return argv


if __name__ == "__main__":
    # 供 shell 展开：python pack_pyinstaller_excludes.py
    print(" ".join(pyinstaller_exclude_argv()), end="")
