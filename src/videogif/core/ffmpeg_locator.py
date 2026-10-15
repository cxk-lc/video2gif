# -*- coding: utf-8 -*-
"""ffmpeg 二进制定位与统一的子进程调用约定。

定位优先级：
  1. 项目内置 tools/ffmpeg/ffmpeg.exe（随项目分发，推荐）
  2. imageio-ffmpeg 包内置二进制（pip 安装时提供）
  3. 系统 PATH 中的 ffmpeg
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import VideoToolError

# 本文件位于 <项目根>/src/videogif/core/ffmpeg_locator.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_EXE_NAME = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_cached: Path | None = None


def _candidates():
    yield PROJECT_ROOT / "tools" / "ffmpeg" / _EXE_NAME
    try:
        import imageio_ffmpeg  # type: ignore

        yield Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        yield Path(found)


def find_ffmpeg(refresh: bool = False) -> Path:
    """返回可用的 ffmpeg 可执行文件路径；找不到时抛出 VideoToolError。"""
    global _cached
    if _cached is not None and not refresh and _cached.exists():
        return _cached
    for cand in _candidates():
        if cand is not None and cand.exists():
            _cached = cand
            return cand
    raise VideoToolError(
        "未找到转换引擎 ffmpeg。",
        hint="请通过 tools\\get_ffmpeg.py 重新获取内置转换引擎（步骤见 README.md）。",
    )


def ffmpeg_popen(args, **kwargs) -> subprocess.Popen:
    """以统一约定启动 ffmpeg 子进程：列表传参（不经 shell）、隐藏控制台窗口。"""
    exe = find_ffmpeg()
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if os.name == "nt":
        kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.Popen([str(exe), *args], **kwargs)
