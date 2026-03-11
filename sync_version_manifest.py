#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 feature_config.py 读取 APP_VERSION 与下载地址模板，同步双通道更新清单：
- update_manifest_public.json（外部包，download_url 指向 AcouTest.v{version}.exe）
- update_manifest_internal.json（内部包，download_url 指向 AcouTest.v{version}.internal.exe）
notes 从 release_notes.txt 读取。
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
    url_public_tpl = read_config_string(
        cfg_path, "DOWNLOAD_URL_PUBLIC",
        "https://github.com/KunLiam/AcouTest/releases/download/v{version}-public/AcouTest.v{version}.exe",
    )
    url_internal_tpl = read_config_string(
        cfg_path, "DOWNLOAD_URL_INTERNAL",
        "https://github.com/KunLiam/AcouTest/releases/download/v{version}/AcouTest.v{version}.exe",
    )
    notes = read_notes(root)
    publish_date = ""
    try:
        with open(os.path.join(root, "update_manifest.json"), "r", encoding="utf-8") as f:
            d = json.load(f)
            publish_date = str(d.get("publish_date") or "").strip()
    except Exception:
        pass
    if not publish_date:
        import time
        publish_date = time.strftime("%Y-%m-%d")

    base = {
        "latest_version": app_version,
        "publish_date": publish_date,
        "notes": notes,
    }
    manifest_public = {**base, "download_url": url_public_tpl.replace("{version}", app_version)}
    manifest_internal = {**base, "download_url": url_internal_tpl.replace("{version}", app_version)}

    for name, data in (
        ("update_manifest_public.json", manifest_public),
        ("update_manifest_internal.json", manifest_internal),
    ):
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写入 {name} -> v{app_version}")

    # 兼容：保留 update_manifest.json 与外部通道一致，便于旧链接
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
