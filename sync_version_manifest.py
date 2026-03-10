#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 feature_config.py 读取 APP_VERSION，并同步到 update_manifest.json：
1) latest_version
2) download_url 中的 tag 版本与文件名版本（_vX.Y.Z.exe）
3) notes（从 release_notes.txt 读取）
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


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(root, "feature_config.py")
    manifest_path = os.path.join(root, "update_manifest.json")

    if not os.path.isfile(manifest_path):
        print("[WARN] 未找到 update_manifest.json，跳过同步。")
        return 0

    app_version = read_app_version(cfg_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError("update_manifest.json 格式无效")

    changed = False
    if str(data.get("latest_version") or "") != app_version:
        data["latest_version"] = app_version
        changed = True

    url = str(data.get("download_url") or "").strip()
    if url:
        new_url = re.sub(
            r"(/releases/download/)v\d+(?:\.\d+){0,3}(/)",
            rf"\1v{app_version}\2",
            url,
            flags=re.IGNORECASE,
        )
        # 文件名中的版本号：兼容 AcouTest_v1.8.4.exe / AcouTest.v1.8.4.exe / AcouTest-v1.8.4.exe
        new_url = re.sub(
            r"([._-])v\d+(?:\.\d+){0,3}(\.exe)",
            rf"\1v{app_version}\2",
            new_url,
            flags=re.IGNORECASE,
        )
        if new_url != url:
            data["download_url"] = new_url
            changed = True

    # notes 同步：读取根目录 release_notes.txt（每行一条，支持 - 或 • 开头）
    notes_path = os.path.join(root, "release_notes.txt")
    if os.path.isfile(notes_path):
        notes = []
        with open(notes_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("-") or s.startswith("•"):
                    s = s[1:].strip()
                if s:
                    notes.append(s)
        if notes and notes != (data.get("notes") or []):
            data["notes"] = notes
            changed = True

    if changed:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已同步 update_manifest.json -> v{app_version}（含 notes）")
    else:
        print(f"[OK] 无需同步，当前已是 v{app_version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[ERROR] 同步失败: {e}")
        raise SystemExit(1)
