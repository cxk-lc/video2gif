# -*- coding: utf-8 -*-
"""参数解析、派生量与校验逻辑的单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from videogif.core.params import (
    GifParams,
    apply_quality,
    estimated_size_text,
    format_time,
    parse_time,
    validate_params,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0.0),
        ("5", 5.0),
        ("5.5", 5.5),
        ("1:23", 83.0),
        ("1:23.5", 83.5),
        ("01:02:03.250", 3723.25),
        ("1：23.5", 83.5),  # 全角冒号
        ("1:23,5", 83.5),  # 逗号小数
        (" 2:00 ", 120.0),
    ],
)
def test_parse_time_ok(text: str, expected: float) -> None:
    assert parse_time(text) == pytest.approx(expected)


@pytest.mark.parametrize("bad", ["", "  ", "abc", "1:2:3:4", "-5", "1:xx", "::", "1:2:x"])
def test_parse_time_bad(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_time(bad)


def test_format_time() -> None:
    assert format_time(0) == "00:00.00"
    assert format_time(83.5) == "01:23.50"
    assert format_time(3723.25) == "1:02:03.25"
    assert format_time(None) == ""


def _params(**kw) -> GifParams:
    base = dict(
        input_path=Path("x.mp4"),
        start=0.0,
        end=2.0,
        fps=12,
        width=320,
        height=None,
        speed=1.0,
        colors=128,
        dither="bayer:bayer_scale=4",
        loop=0,
    )
    base.update(kw)
    return GifParams(**base)


def test_derived_values() -> None:
    p = _params(start=0.5, end=2.5, speed=2.0, fps=10)
    assert p.clip_duration == pytest.approx(2.0)
    assert p.out_duration == pytest.approx(1.0)
    assert p.out_frames == 10


def test_validate_ok() -> None:
    assert validate_params(_params(), 2.0) == []
    assert validate_params(_params(), None) == []


def test_validate_end_not_after_start() -> None:
    errs = validate_params(_params(start=1.0, end=1.0), 2.0)
    assert any("结束时间" in e for e in errs)


def test_validate_out_of_range() -> None:
    assert any("帧率" in e for e in validate_params(_params(fps=0), 10.0))
    assert any("帧率" in e for e in validate_params(_params(fps=99), 10.0))
    assert any("宽度" in e for e in validate_params(_params(width=8), 10.0))
    assert any("高度" in e for e in validate_params(_params(height=1), 10.0))
    assert any("速度" in e for e in validate_params(_params(speed=9.0), 10.0))
    assert any("颜色" in e for e in validate_params(_params(colors=1), 10.0))
    assert any("循环" in e for e in validate_params(_params(loop=-1), 10.0))


def test_validate_duration_exceed() -> None:
    errs = validate_params(_params(start=3.0, end=4.0), 2.0)
    assert any("超出视频时长" in e for e in errs)


def test_validate_too_short() -> None:
    errs = validate_params(_params(fps=1, start=0.0, end=0.4), None)
    assert any("太短" in e for e in errs)


def test_validate_too_many_frames() -> None:
    errs = validate_params(_params(fps=30, start=0.0, end=300.0), None)
    assert any("帧数过多" in e for e in errs)


def test_estimated_size_text() -> None:
    text = estimated_size_text(_params(width=160), 320, 240)
    assert "预计输出" in text
    assert "160×120" in text
    assert "帧" in text


def test_quality_preset() -> None:
    p = _params()
    apply_quality(p, "高")
    assert p.colors == 256 and p.dither == "sierra2_4a"
    apply_quality(p, "低")
    assert p.colors == 64 and p.dither.startswith("bayer")


def test_video_filters_scale() -> None:
    assert "scale=160:-2" in _params(width=160, height=None).video_filters()
    assert "scale=160:90" in _params(width=160, height=90).video_filters()
    assert "fps=12" in _params(fps=12).video_filters()
    assert "setpts=(PTS-STARTPTS)/2" in _params(speed=2.0).video_filters()
