# -*- coding: utf-8 -*-
"""视频信息探测：解析 ffmpeg 输出获取时长 / 分辨率 / 原始帧率。"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import VideoToolError, friendly_ffmpeg_error
from .ffmpeg_locator import ffmpeg_popen

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_STREAM_RE = re.compile(r"Stream #\d+:\d+.*")
_SIZE_RE = re.compile(r"(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"([\d.]+)\s*fps")
_TBR_RE = re.compile(r"([\d.]+)\s*tbr")

_PROBE_TIMEOUT = 30  # 秒


@dataclass
class VideoInfo:
    path: Path
    duration: float | None  # 秒；None = 未知
    width: int | None
    height: int | None
    fps: float | None

    def duration_text(self) -> str:
        from .params import format_time

        return format_time(self.duration) if self.duration is not None else "未知"

    def resolution_text(self) -> str:
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return "未知"

    def fps_text(self) -> str:
        if self.fps is None:
            return "未知"
        return f"{self.fps:g} fps"

    def summary(self) -> str:
        return f"时长 {self.duration_text()} ｜ {self.resolution_text()} ｜ {self.fps_text()}"


def _parse_duration(text: str) -> float | None:
    m = _DURATION_RE.search(text)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _parse_video_stream(text: str) -> tuple[int | None, int | None, float | None]:
    """在 ffmpeg 输出里找到第一条真实视频流，返回 (宽, 高, 原始fps)。"""
    for line in text.splitlines():
        if "Video:" not in line or not _STREAM_RE.search(line):
            continue
        if "(attached pic)" in line:  # 封面图等伪视频流，跳过
            continue
        size = _SIZE_RE.search(line)
        width = int(size.group(1)) if size else None
        height = int(size.group(2)) if size else None
        fps = None
        m = _FPS_RE.search(line)
        if m:
            fps = float(m.group(1))
        else:
            m = _TBR_RE.search(line)
            if m:
                fps = float(m.group(1))
        return width, height, fps
    return None, None, None


def probe_video(path: str | Path) -> VideoInfo:
    """读取视频基础信息；文件不存在/非视频/损坏时抛出 VideoToolError。"""
    p = Path(path)
    if not p.exists():
        raise VideoToolError(f"找不到文件：{p.name}", hint="请确认文件存在且未被移动。")
    if p.is_dir():
        raise VideoToolError("所选路径是一个文件夹，而不是视频文件。")

    args = ["-hide_banner", "-nostdin", "-i", str(p)]
    try:
        proc = ffmpeg_popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = proc.communicate(timeout=_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise VideoToolError(
            "读取视频信息超时。",
            hint="文件可能位于慢速磁盘/网络位置，或文件异常，请重试或更换文件。",
        ) from None

    text = (err or b"").decode("utf-8", "replace")
    width, height, fps = _parse_video_stream(text)
    if width is None:
        msg, hint = friendly_ffmpeg_error(text)
        if "无法识别" in msg or "不完整" in msg:
            raise VideoToolError(msg, hint=hint, detail=text[-4000:])
        raise VideoToolError(
            "该文件不包含视频画面。",
            hint="请选择包含画面的视频文件（MP4 / AVI / MOV 等）。",
            detail=text[-4000:],
        )

    if p.suffix.lower() in (".gif",):
        raise VideoToolError(
            "这是一个 GIF 动图文件，不是视频。",
            hint="请选择 MP4 / AVI / MOV 等视频文件。",
            detail=text[-4000:],
        )

    return VideoInfo(path=p, duration=_parse_duration(text), width=width, height=height, fps=fps)
