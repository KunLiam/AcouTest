# -*- coding: utf-8 -*-
"""
检查更新 / 下载安装包用的 HTTPS：优先使用 certifi 的 CA 包，避免 PyInstaller 与部分 Windows
环境「找不到颁发者」导致 CERTIFICATE_VERIFY_FAILED。

环境变量（可选）：
- ACOUTEST_UPDATE_SSL_INSECURE=1：校验仍失败时跳过证书验证（仅建议在受信内网或排查时使用）。
"""
from __future__ import annotations

import os
import ssl
import urllib.request


def _env_ssl_insecure() -> bool:
    v = str(os.environ.get("ACOUTEST_UPDATE_SSL_INSECURE", "")).strip().lower()
    return v in ("1", "true", "yes", "on")


def _context_certifi() -> ssl.SSLContext | None:
    try:
        import certifi

        ca = certifi.where()
        if ca and os.path.isfile(ca):
            return ssl.create_default_context(cafile=ca)
    except Exception:
        pass
    return None


def urlopen(request: urllib.request.Request, timeout: float | int):
    """
    与 urllib.request.urlopen 相同用法，但使用更稳妥的 SSL 上下文。
    """
    ctx_certifi = _context_certifi()
    if ctx_certifi is not None:
        try:
            return urllib.request.urlopen(request, timeout=timeout, context=ctx_certifi)
        except ssl.SSLError:
            if _env_ssl_insecure():
                return urllib.request.urlopen(
                    request, timeout=timeout, context=ssl._create_unverified_context()
                )
            raise

    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except ssl.SSLError:
        if _env_ssl_insecure():
            return urllib.request.urlopen(
                request, timeout=timeout, context=ssl._create_unverified_context()
            )
        raise
