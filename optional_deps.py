"""
可选依赖加载器

背景：
- 本项目的“本地播放”依赖 pygame。
- 但 pygame 在导入时会尝试导入 numpy（来自 pygame.sndarray）。
- 在部分 CPU / 打包环境（PyInstaller）中，numpy 可能在导入阶段崩溃：
  RuntimeError: CPU dispatcher tracer already initlized

策略：
- 其它功能不应因为本地播放不可用而无法启动。
- 因此把 pygame 的导入改为“按需 + 捕获异常”，并在失败时优雅降级。
"""

from __future__ import annotations

from typing import Optional, Tuple, Any

_CACHED_PYGAME: Optional[Any] = None
_CACHED_PYGAME_ERR: Optional[str] = None
_PYGAME_CHECKED: bool = False


def try_import_pygame() -> Tuple[Optional[Any], Optional[str]]:
    """
    尝试导入 pygame。
    - 成功：返回 (pygame_module, None)
    - 失败：返回 (None, error_message)
    说明：会缓存结果，避免重复导入/重复报错。
    """
    global _CACHED_PYGAME, _CACHED_PYGAME_ERR, _PYGAME_CHECKED

    if _PYGAME_CHECKED:
        return _CACHED_PYGAME, _CACHED_PYGAME_ERR

    _PYGAME_CHECKED = True
    try:
        import pygame  # type: ignore

        _CACHED_PYGAME = pygame
        _CACHED_PYGAME_ERR = None
        return _CACHED_PYGAME, None
    except Exception as e:
        _CACHED_PYGAME = None
        _CACHED_PYGAME_ERR = f"{type(e).__name__}: {e}"
        return None, _CACHED_PYGAME_ERR


