# -*- coding: utf-8 -*-
"""
测试生成数据的统一输出目录配置。

所有测试产生的文件（logcat、截图、录音、HAL 拉取等）默认保存在同一根目录 output/ 下，
按类型分子目录，便于查找和管理。用户可在各功能界面修改保存路径。
"""

import os

# 测试数据根目录（与项目根目录同级，名称简洁）
OUTPUT_ROOT = os.path.join(os.getcwd(), "output")

# 子目录名称（相对 OUTPUT_ROOT）
DIR_LOGCAT = "logcat"           # Logcat 抓取
DIR_SCREENSHOTS = "screenshots" # 截图
DIR_MIC_TEST = "mic_test"       # 麦克风测试录音
DIR_SWEEP_RECORDINGS = "sweep_recordings"  # 扫频录音
DIR_LOOPBACK = "loopback"       # Loopback/Ref 测试录音
DIR_HAL_DUMP = "hal_dump"       # HAL 录音拉取
DIR_HAL_CUSTOM = "hal_custom"   # 自定义 HAL 录音拉取


def get_output_dir(subdir: str) -> str:
    """返回 output 下某子目录的绝对路径，不创建目录。"""
    return os.path.join(OUTPUT_ROOT, subdir)


def ensure_output_dir(subdir: str) -> str:
    """返回 output 下某子目录的绝对路径，若不存在则创建。"""
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    _ensure_output_readme()
    path = get_output_dir(subdir)
    os.makedirs(path, exist_ok=True)
    return path


def _ensure_output_readme():
    """若 output 根目录下尚无 README.txt，则写入说明（仅执行一次）。"""
    readme = os.path.join(OUTPUT_ROOT, "README.txt")
    if os.path.exists(readme):
        return
    try:
        with open(readme, "w", encoding="utf-8") as f:
            f.write("声测大师(AcouTest) 测试数据目录\n")
            f.write("=" * 40 + "\n\n")
            f.write("本目录下各子目录用途：\n\n")
            f.write("  logcat/          Logcat 抓取文件\n")
            f.write("  screenshots/     设备截图\n")
            f.write("  mic_test/        麦克风测试录音\n")
            f.write("  sweep_recordings/ 扫频测试录音\n")
            f.write("  loopback/        Loopback/Ref 测试录音\n")
            f.write("  hal_dump/        HAL 录音拉取\n")
            f.write("  hal_custom/      自定义 HAL 录音拉取\n")
    except Exception:
        pass
