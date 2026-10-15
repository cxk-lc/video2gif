# -*- coding: utf-8 -*-
"""转换核心的端到端测试：容器矩阵、参数数学、进度、取消与错误路径。

所有产物属性均用 Pillow 独立校验（不依赖 ffmpeg 自述）。
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image, ImageSequence

from videogif.core.converter import GifConverter, StageProgress
from videogif.core.errors import ConversionCancelled, VideoToolError, friendly_ffmpeg_error
from videogif.core.params import GifParams, apply_quality


def _open_gif(path: Path):
    im = Image.open(path)
    frames = getattr(im, "n_frames", 1) or 1
    durations = [f.info.get("duration") or 0 for f in ImageSequence.Iterator(im)]
    return im, frames, sum(durations)


def _make_params(video: Path, **kw) -> GifParams:
    base = dict(input_path=video, start=0.0, end=2.0, fps=12, width=320, height=None, speed=1.0, loop=0)
    base.update(kw)
    p = GifParams(**base)
    apply_quality(p, "中")
    return p


def test_convert_basic(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=0.2, end=1.7, fps=10, width=160)
    conv = GifConverter()
    work = tmp_path / "work_basic"
    result = conv.convert(p, work_dir=work)

    assert result.gif_path.exists() and result.gif_path.stat().st_size > 0
    im, frames, total_ms = _open_gif(result.gif_path)
    assert im.size == (160, 120)  # 高度按 320x240 比例自动
    assert abs(frames - 15) <= 1
    assert 1300 <= total_ms <= 1700
    assert im.info.get("loop") == 0  # 无限循环
    im.close()  # 释放句柄后再清理（Windows 文件锁语义）

    GifConverter.cleanup(work)
    assert not work.exists()


@pytest.mark.parametrize("fixture_name", ["avi_video", "mov_video"])
def test_convert_other_containers(request, fixture_name: str, tmp_path: Path) -> None:
    video = request.getfixturevalue(fixture_name)
    p = _make_params(video, start=0.0, end=1.0, fps=8, width=120)
    result = GifConverter().convert(p, work_dir=tmp_path / f"work_{fixture_name}")
    im, frames, total_ms = _open_gif(result.gif_path)
    assert im.size == (120, 90)
    assert abs(frames - 8) <= 1
    assert abs(total_ms - 1000) <= 150


def test_convert_speed_2x(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=0.0, end=2.0, fps=10, width=160, speed=2.0)
    result = GifConverter().convert(p, work_dir=tmp_path / "work_speed")
    im, frames, total_ms = _open_gif(result.gif_path)
    assert abs(frames - 10) <= 1
    assert abs(total_ms - 1000) <= 150


def test_convert_loop_count(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=0.0, end=1.0, fps=8, width=120, loop=3)
    result = GifConverter().convert(p, work_dir=tmp_path / "work_loop")
    im, _, _ = _open_gif(result.gif_path)
    assert im.info.get("loop") == 3


def test_convert_fixed_height(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=0.0, end=1.0, fps=8, width=200, height=100)
    result = GifConverter().convert(p, work_dir=tmp_path / "work_h")
    im, _, _ = _open_gif(result.gif_path)
    assert im.size == (200, 100)


def test_progress_monotonic(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=0.0, end=1.5, fps=10, width=160)
    events: list[StageProgress] = []
    result = GifConverter().convert(p, on_progress=events.append, work_dir=tmp_path / "work_prog")

    assert result.gif_path.exists()
    assert events, "应当收到进度回调"
    overalls = [e.overall for e in events]
    assert overalls[0] == pytest.approx(0.0, abs=0.01)
    assert overalls[-1] == pytest.approx(1.0, abs=0.01)
    assert all(b >= a - 1e-6 for a, b in zip(overalls, overalls[1:])), "进度不得回退"
    stages = {e.stage for e in events}
    assert stages == {"palette", "encode"}


def test_convert_cancel(big_video: Path, tmp_path: Path) -> None:
    p = _make_params(big_video, start=0.0, end=8.0, fps=25, width=800)
    cancel = threading.Event()
    timer = threading.Timer(0.9, cancel.set)
    timer.start()
    work = tmp_path / "work_cancel"
    try:
        with pytest.raises(ConversionCancelled):
            GifConverter().convert(p, cancel_event=cancel, work_dir=work)
    finally:
        timer.cancel()
    assert not work.exists(), "取消后应清理工作目录"


def test_convert_out_of_range(mp4_video: Path, tmp_path: Path) -> None:
    p = _make_params(mp4_video, start=10.0, end=12.0)  # 视频只有 2 秒
    with pytest.raises(VideoToolError) as ei:
        GifConverter().convert(p, work_dir=tmp_path / "work_bad")
    assert ei.value.user_msg
    assert not (tmp_path / "work_bad").exists()


def test_convert_missing_input(tmp_path: Path) -> None:
    p = _make_params(tmp_path / "nope.mp4")
    with pytest.raises(VideoToolError) as ei:
        GifConverter().convert(p, work_dir=tmp_path / "work_missing")
    assert "找不到文件" in ei.value.user_msg


def test_error_mapping() -> None:
    assert "无法识别" in friendly_ffmpeg_error("Invalid data found when processing input")[0]
    assert "不完整" in friendly_ffmpeg_error("moov atom not found")[0]
    assert "空间不足" in friendly_ffmpeg_error("No space left on device")[0]
    assert friendly_ffmpeg_error("something totally unknown")[0]
