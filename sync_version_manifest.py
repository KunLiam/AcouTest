#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 feature_config.py 读取版本与下载地址模板，按 RELEASE_CHANNEL 同步更新清单：
- RELEASE_CHANNEL="internal" 时仅写入 update_manifest_internal.json
- RELEASE_CHANNEL="public" 时仅写入 update_manifest_public.json（并同步 update_manifest.json 兼容旧链接）
notes 从 release_notes.txt 读取。

APK 地址：WAKEUP_COUNT_APK_DOWNLOAD_URL_* 中的 {version} 替换为 AUDIOPLAYER_APK_VERSION
（未定义时回退为 APP_VERSION）。APK 与 exe 版本分离时，在 feature_config 里分别改 APP_VERSION 与 AUDIOPLAYER_APK_VERSION。
"""
import importlib.util
import json
import os
import sys
import time


def load_feature_config(root: str):
    cfg_path = os.path.join(root, "feature_config.py")
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(cfg_path)
    spec = importlib.util.spec_from_file_location("_acoutest_feature_config", cfg_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


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
    try:
        fc = load_feature_config(root)
    except Exception as e:
        print(f"[ERROR] 无法加载 feature_config.py: {e}")
        return 1

    app_version = str(getattr(fc, "APP_VERSION", "") or "").strip()
    if not app_version:
        print("[ERROR] feature_config.APP_VERSION 为空")
        return 1

    channel = str(getattr(fc, "RELEASE_CHANNEL", "internal") or "internal").strip().lower()
    if channel not in ("internal", "public"):
        channel = "internal"

    apk_version = str(getattr(fc, "AUDIOPLAYER_APK_VERSION", app_version) or app_version).strip() or app_version

    url_public_tpl = str(
        getattr(
            fc,
            "DOWNLOAD_URL_PUBLIC",
            "https://github.com/KunLiam/AcouTest/releases/download/v{version}-public/AcouTest.v{version}.exe",
        )
        or ""
    )
    url_internal_tpl = str(
        getattr(
            fc,
            "DOWNLOAD_URL_INTERNAL",
            "https://github.com/KunLiam/AcouTest/releases/download/v{version}/AcouTest.v{version}.exe",
        )
        or ""
    )
    apk_public_tpl = str(getattr(fc, "WAKEUP_COUNT_APK_DOWNLOAD_URL_PUBLIC", "") or "")
    apk_internal_tpl = str(getattr(fc, "WAKEUP_COUNT_APK_DOWNLOAD_URL_INTERNAL", "") or "")

    notes = read_notes(root)
    publish_date = time.strftime("%Y-%m-%d")

    base = {
        "latest_version": app_version,
        "publish_date": publish_date,
        "notes": notes,
    }
    manifest_public = {**base, "download_url": url_public_tpl.replace("{version}", app_version)}
    manifest_internal = {**base, "download_url": url_internal_tpl.replace("{version}", app_version)}
    apk_pub = apk_public_tpl.replace("{version}", apk_version).strip()
    apk_int = apk_internal_tpl.replace("{version}", apk_version).strip()
    if apk_pub.lower().startswith(("http://", "https://")):
        manifest_public["wakeup_count_apk_url"] = apk_pub
    if apk_int.lower().startswith(("http://", "https://")):
        manifest_internal["wakeup_count_apk_url"] = apk_int

    if channel == "internal":
        path = os.path.join(root, "update_manifest_internal.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_internal, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写入 update_manifest_internal.json -> v{app_version}（通道: internal）")
        if apk_int:
            print(f"     wakeup_count_apk_url -> v{apk_version} ({apk_int})")
    else:
        path = os.path.join(root, "update_manifest_public.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_public, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写入 update_manifest_public.json -> v{app_version}（通道: public）")
        if apk_pub:
            print(f"     wakeup_count_apk_url -> v{apk_version} ({apk_pub})")
        with open(os.path.join(root, "update_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_public, f, ensure_ascii=False, indent=2)
        print("[OK] 已同步 update_manifest.json（与外部通道一致）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[ERROR] 同步失败: {e}")
        raise SystemExit(1)
