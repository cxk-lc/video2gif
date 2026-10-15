# -*- coding: utf-8 -*-
"""pytest 公共 fixture：路径注入 + 用 ffmpeg 合成测试素材（不依赖外部文件）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from videogif.core.ffmpeg_locator import ffmpeg_popen  # noqa: E402


def gen_video(
    path: Path,
    *,
    size: str = "320x240",
    duration: float = 2.0,
    rate: int = 30,
    vcodec: str = "libx264",
) -> Path:
    """用 lavfi testsrc 生成一段测试视频。"""
    args = [
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate={rate}",
        "-pix_fmt", "yuv420p", "-c:v", vcodec, str(path),
    ]
    proc = ffmpeg_popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = proc.communicate(timeout=180)
    if proc.returncode != 0:
        raise RuntimeError((err or b"").decode("utf-8", "replace"))
    return path


def gen_audio(path: Path, *, duration: float = 1.0) -> Path:
    """生成一段纯音频文件（用于错误路径测试）。"""
    args = [
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "aac", str(path),
    ]
    proc = ffmpeg_popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = proc.communicate(timeout=120)
    if proc.returncode != 0:
        raise RuntimeError((err or b"").decode("utf-8", "replace"))
    return path


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> Path:
    """会话级素材目录：MP4 / AVI / MOV 三容器 + 长视频。"""
    d = tmp_path_factory.mktemp("media")
    gen_video(d / "clip.mp4")
    gen_video(d / "clip.avi", vcodec="mpeg4")
    gen_video(d / "clip.mov")
    gen_video(d / "big.mp4", size="960x540", duration=8.0, rate=30)
    return d


@pytest.fixture(scope="session")
def mp4_video(media: Path) -> Path:
    return media / "clip.mp4"


@pytest.fixture(scope="session")
def avi_video(media: Path) -> Path:
    return media / "clip.avi"


@pytest.fixture(scope="session")
def mov_video(media: Path) -> Path:
    return media / "clip.mov"


@pytest.fixture(scope="session")
def big_video(media: Path) -> Path:
    return media / "big.mp4"
