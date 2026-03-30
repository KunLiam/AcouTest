#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 feature_config.py 读取 APP_VERSION、RELEASE_CHANNEL 与下载地址模板，按通道同步更新清单：
- RELEASE_CHANNEL="internal" 时仅写入 update_manifest_internal.json
- RELEASE_CHANNEL="public" 时仅写入 update_manifest_public.json（并同步 update_manifest.json 兼容旧链接）
notes 从 release_notes.txt 读取。
若配置了 WAKEUP_COUNT_APK_DOWNLOAD_URL_*（非空且为 http(s)），会写入清单字段 wakeup_count_apk_url，供客户端随 exe 一并更新 wakeup_count/AudioPlayer.apk。
"""
import json
import os
import re
import sys


def read_app_version(cfg_path: str) -> str:
    with open(cfg_path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^\s*APP_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("未在 feature_config.py 中找到 APP_VERSION")
    return m.group(1).strip()


def read_release_channel(cfg_path: str) -> str:
    ch = read_config_string(cfg_path, "RELEASE_CHANNEL", "internal").strip().lower()
    return ch if ch in ("internal", "public") else "internal"


def read_config_string(cfg_path: str, var_name: str, default: str = "") -> str:
    with open(cfg_path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf'^\s*{re.escape(var_name)}\s*=\s*"([^"]*)"', text, flags=re.MULTILINE)
    return m.group(1).strip() if m else default


def read_notes(root: str) -> list:
    notes_path = os.path.join(root, "release_notes.txt")
    notes = []
    if os.path.isfile(notes_path):
        with open(notes_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("-") or s.startswith("•"):
                    s = s[1:].strip()
                if s:
                    notes.append(s)
    return notes


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(root, "feature_config.py")
    if not os.path.isfile(cfg_path):
        print("[ERROR] 未找到 feature_config.py")
        return 1

    app_version = read_app_version(cfg_path)
    channel = read_release_channel(cfg_path)
    url_public_tpl = read_config_string(
        cfg_path, "DOWNLOAD_URL_PUBLIC",
        "https://github.com/KunLiam/AcouTest/releases/download/v{version}-public/AcouTest.v{version}.exe",
    )
    url_internal_tpl = read_config_string(
        cfg_path, "DOWNLOAD_URL_INTERNAL",
        "https://github.com/KunLiam/AcouTest/releases/download/v{version}/AcouTest.v{version}.exe",
    )
    apk_public_tpl = read_config_string(cfg_path, "WAKEUP_COUNT_APK_DOWNLOAD_URL_PUBLIC", "")
    apk_internal_tpl = read_config_string(cfg_path, "WAKEUP_COUNT_APK_DOWNLOAD_URL_INTERNAL", "")
    notes = read_notes(root)
    import time
    publish_date = time.strftime("%Y-%m-%d")

    base = {
        "latest_version": app_version,
        "publish_date": publish_date,
        "notes": notes,
    }
    manifest_public = {**base, "download_url": url_public_tpl.replace("{version}", app_version)}
    manifest_internal = {**base, "download_url": url_internal_tpl.replace("{version}", app_version)}
    apk_pub = apk_public_tpl.replace("{version}", app_version).strip()
    apk_int = apk_internal_tpl.replace("{version}", app_version).strip()
    if apk_pub.lower().startswith(("http://", "https://")):
        manifest_public["wakeup_count_apk_url"] = apk_pub
    if apk_int.lower().startswith(("http://", "https://")):
        manifest_internal["wakeup_count_apk_url"] = apk_int

    # 仅同步当前 RELEASE_CHANNEL 对应的清单
    if channel == "internal":
        path = os.path.join(root, "update_manifest_internal.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_internal, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写入 update_manifest_internal.json -> v{app_version}（通道: internal）")
    else:
        path = os.path.join(root, "update_manifest_public.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_public, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写入 update_manifest_public.json -> v{app_version}（通道: public）")
        # 兼容旧链接
        with open(os.path.join(root, "update_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_public, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已同步 update_manifest.json（与外部通道一致）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[ERROR] 同步失败: {e}")
        raise SystemExit(1)
