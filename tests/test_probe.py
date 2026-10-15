# -*- coding: utf-8 -*-
"""视频探测的测试：三种容器 + 错误路径。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from conftest import gen_audio

from videogif.core.errors import VideoToolError
from videogif.core.probe import probe_video


def _assert_basic(info) -> None:
    assert info.width == 320
    assert info.height == 240
    assert info.duration is not None and abs(info.duration - 2.0) < 0.25
    assert info.fps is not None and abs(info.fps - 30) < 1.0
    assert "320×240" in info.summary()


def test_probe_mp4(mp4_video: Path) -> None:
    _assert_basic(probe_video(mp4_video))


def test_probe_avi(avi_video: Path) -> None:
    _assert_basic(probe_video(avi_video))


def test_probe_mov(mov_video: Path) -> None:
    _assert_basic(probe_video(mov_video))


def test_probe_missing_file(tmp_path: Path) -> None:
    with pytest.raises(VideoToolError) as ei:
        probe_video(tmp_path / "不存在.mp4")
    assert "找不到文件" in ei.value.user_msg


def test_probe_directory(tmp_path: Path) -> None:
    with pytest.raises(VideoToolError) as ei:
        probe_video(tmp_path)
    assert "文件夹" in ei.value.user_msg


def test_probe_corrupt_file(tmp_path: Path) -> None:
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"this is definitely not a valid video file " * 20)
    with pytest.raises(VideoToolError) as ei:
        probe_video(bad)
    assert ("无法识别" in ei.value.user_msg) or ("不完整" in ei.value.user_msg)


def test_probe_audio_only(tmp_path: Path) -> None:
    audio = gen_audio(tmp_path / "sine.m4a")
    with pytest.raises(VideoToolError) as ei:
        probe_video(audio)
    assert "不包含视频画面" in ei.value.user_msg


def test_probe_gif_input(tmp_path: Path) -> None:
    gif = tmp_path / "anim.gif"
    frames = [Image.new("RGB", (32, 32), (i * 30, 0, 0)) for i in range(4)]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    with pytest.raises(VideoToolError) as ei:
        probe_video(gif)
    assert "动图" in ei.value.user_msg
