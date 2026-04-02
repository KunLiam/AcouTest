# -*- coding: utf-8 -*-
"""
设备侧 Audio Player Demo APK 的 adb 调用（与文档 Intent 一致）。

气密性 / 震音测试用 APK 播放可走系统音量；录制仍由 tinycap。
"""
from __future__ import annotations

import subprocess
import time
from typing import List, Optional

try:
    import feature_config as _fc
except Exception:  # pragma: no cover
    _fc = None


def _cfg(name: str, default: str) -> str:
    if _fc is None:
        return default
    return str(getattr(_fc, name, default) or default).strip()


def _cfg_bool(name: str, default: bool) -> bool:
    if _fc is None:
        return default
    return bool(getattr(_fc, name, default))


def use_apk_for_airtightness_and_jitter() -> bool:
    return _cfg_bool("USE_AUDIO_PLAYER_APK_FOR_AIRTIGHTNESS_AND_JITTER", False)


def adb_base(device_id: Optional[str]) -> List[str]:
    s = (device_id or "").strip()
    return ["adb", "-s", s] if s else ["adb"]


def run_play(device_id: Optional[str], extra_track: str) -> subprocess.CompletedProcess:
    action = _cfg("AUDIO_PLAYER_ACTION_PLAY", "com.player.demo.PLAY")
    component = _cfg("AUDIO_PLAYER_COMPONENT", "com.player.demo/.MainActivity")
    extra_key = _cfg("AUDIO_PLAYER_EXTRA_TRACK", "com.player.demo.EXTRA_TRACK")
    cmd = adb_base(device_id) + [
        "shell",
        "am",
        "start",
        "-a",
        action,
        "-n",
        component,
        "--es",
        extra_key,
        extra_track,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def run_replay(device_id: Optional[str], extra_track: str) -> subprocess.CompletedProcess:
    """与 PLAY 相同参数，动作为 REPLAY（用于 PAUSE 后从头重播，避免再次 PLAY 被当作续播）。"""
    action = _cfg("AUDIO_PLAYER_ACTION_REPLAY", "com.player.demo.REPLAY")
    component = _cfg("AUDIO_PLAYER_COMPONENT", "com.player.demo/.MainActivity")
    extra_key = _cfg("AUDIO_PLAYER_EXTRA_TRACK", "com.player.demo.EXTRA_TRACK")
    cmd = adb_base(device_id) + [
        "shell",
        "am",
        "start",
        "-a",
        action,
        "-n",
        component,
        "--es",
        extra_key,
        extra_track,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def run_play_from_start(device_id: Optional[str], extra_track: str) -> subprocess.CompletedProcess:
    """
    每次测试从头播放：优先 REPLAY（带 EXTRA_TRACK）；失败则 force-stop 包后再 PLAY（冷启动/未支持 REPLAY 时）。
    """
    rr = run_replay(device_id, extra_track)
    if rr.returncode == 0:
        return rr
    try:
        subprocess.run(
            adb_base(device_id) + ["shell", "am", "force-stop", "com.player.demo"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        pass
    time.sleep(0.35)
    return run_play(device_id, extra_track)


def run_pause(device_id: Optional[str]) -> None:
    action = _cfg("AUDIO_PLAYER_ACTION_PAUSE", "com.player.demo.PAUSE")
    component = _cfg("AUDIO_PLAYER_COMPONENT", "com.player.demo/.MainActivity")
    cmd = adb_base(device_id) + ["shell", "am", "start", "-a", action, "-n", component]
    subprocess.run(cmd, capture_output=True, text=True, timeout=15)
