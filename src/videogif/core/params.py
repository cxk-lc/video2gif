# -*- coding: utf-8 -*-
"""转换参数模型、时间解析与校验。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 质量档位 -> (颜色数, 抖动方式)
QUALITY_PRESETS: dict[str, tuple[int, str]] = {
    "高": (256, "sierra2_4a"),
    "中": (128, "bayer:bayer_scale=4"),
    "低": (64, "bayer:bayer_scale=5"),
}
DEFAULT_QUALITY = "中"

FPS_MIN, FPS_MAX = 1, 30
WIDTH_MIN, WIDTH_MAX = 16, 4096
SPEED_MIN, SPEED_MAX = 0.25, 4.0
COLORS_MIN, COLORS_MAX = 2, 256
LOOP_MAX = 1000
# 输出帧数保护：超过上限直接拒绝，超过提示阈值给出提示
OUT_FRAMES_HARD_MAX = 5000
OUT_FRAMES_SOFT_MAX = 600

_TIME_RE = re.compile(r"^\d+(?:\.\d+)?$")


def parse_time(text: str) -> float:
    """解析时间输入：支持 `秒`、`mm:ss(.ms)`、`hh:mm:ss(.ms)`，返回秒数。

    容忍全角冒号/逗号与首尾空格；非法输入抛出 ValueError（中文消息）。
    """
    if text is None:
        raise ValueError("时间不能为空")
    t = str(text).strip().replace("：", ":").replace("，", ".").replace(",", ".")
    if not t:
        raise ValueError("时间不能为空，可填秒数（如 5.5）或 mm:ss（如 00:05.5）")
    parts = t.split(":")
    if len(parts) > 3:
        raise ValueError("时间格式无法识别，可填 秒 / mm:ss / hh:mm:ss")
    nums: list[float] = []
    for part in parts:
        part = part.strip()
        if not _TIME_RE.match(part):
            raise ValueError("时间格式无法识别，可填 秒 / mm:ss / hh:mm:ss")
        nums.append(float(part))
    if any(n < 0 for n in nums):
        raise ValueError("时间不能为负数")
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def format_time(seconds: float | None) -> str:
    """格式化为 mm:ss.dd（超过 1 小时为 h:mm:ss.dd）。"""
    if seconds is None:
        return ""
    if seconds < 0:
        seconds = 0.0
    minutes, sec = divmod(float(seconds), 60.0)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:02d}:{sec:05.2f}"


@dataclass
class GifParams:
    """一次 GIF 转换的完整参数（时间均为原片时间轴上的秒数）。"""

    input_path: Path
    start: float = 0.0
    end: float = 0.0
    fps: int = 12
    width: int = 480
    height: int | None = None  # None = 按原比例自动
    speed: float = 1.0
    colors: int = 128
    dither: str = "bayer:bayer_scale=4"
    loop: int = 0  # 0 = 无限循环

    # ---- 派生量 ----
    @property
    def clip_duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def out_duration(self) -> float:
        """输出 GIF 的时长（秒）。"""
        return self.clip_duration / self.speed if self.speed > 0 else 0.0

    @property
    def out_frames(self) -> int:
        return max(1, round(self.out_duration * self.fps))

    def video_filters(self) -> str:
        """构造与两遍转换共用的视频滤镜链（不含 palettegen/paletteuse）。"""
        h = str(self.height) if self.height else "-2"
        speed = f"{self.speed:g}"
        return (
            f"setpts=(PTS-STARTPTS)/{speed},"
            f"fps={self.fps},"
            f"setsar=1,"
            f"scale={self.width}:{h}:flags=lanczos"
        )


def apply_quality(params: GifParams, quality: str) -> None:
    """按档位设置颜色数与抖动方式。"""
    colors, dither = QUALITY_PRESETS.get(quality, QUALITY_PRESETS[DEFAULT_QUALITY])
    params.colors = colors
    params.dither = dither


def estimated_size_text(params: GifParams, src_width: int | None, src_height: int | None) -> str:
    """人话版预估信息（用于界面提示）。"""
    out_h: int | None = params.height
    if out_h is None and src_width and src_height:
        out_h = max(1, round(params.width * src_height / src_width))
    size_text = f"{params.width}×{out_h}" if out_h else f"宽 {params.width}"
    text = f"预计输出：{params.out_duration:.1f} 秒 ｜ {params.out_frames} 帧 ｜ {size_text}"
    notes: list[str] = []
    if params.out_frames > OUT_FRAMES_SOFT_MAX:
        notes.append("帧数较多，转换与预览会较慢")
    if src_width and params.width > src_width:
        notes.append("宽度超过原始尺寸，画面将被放大")
    if notes:
        text += "（" + "；".join(notes) + "）"
    return text


def validate_params(params: GifParams, duration: float | None) -> list[str]:
    """校验参数，返回中文错误消息列表（空列表 = 通过）。"""
    errors: list[str] = []

    if params.end <= params.start:
        errors.append("结束时间必须大于起始时间。")
    if duration is not None:
        if params.start >= duration:
            errors.append(f"起始时间超出视频时长（视频共 {format_time(duration)}）。")
        elif params.end > duration + 0.05:
            errors.append(f"结束时间超出视频时长（视频共 {format_time(duration)}）。")
    if not (FPS_MIN <= params.fps <= FPS_MAX):
        errors.append(f"帧率需在 {FPS_MIN}–{FPS_MAX} 之间。")
    if not (WIDTH_MIN <= params.width <= WIDTH_MAX):
        errors.append(f"输出宽度需在 {WIDTH_MIN}–{WIDTH_MAX} 像素之间。")
    if params.height is not None and not (WIDTH_MIN <= params.height <= WIDTH_MAX):
        errors.append(f"输出高度需在 {WIDTH_MIN}–{WIDTH_MAX} 像素之间。")
    if not (SPEED_MIN <= params.speed <= SPEED_MAX):
        errors.append(f"播放速度需在 {SPEED_MIN}×–{SPEED_MAX}× 之间。")
    if not (COLORS_MIN <= params.colors <= COLORS_MAX):
        errors.append(f"颜色数需在 {COLORS_MIN}–{COLORS_MAX} 之间。")
    if not (0 <= params.loop <= LOOP_MAX):
        errors.append(f"循环次数需在 0–{LOOP_MAX} 之间（0 = 无限循环）。")
    if not errors:
        if params.out_duration * params.fps < 1:
            errors.append("截取的时间段太短：按当前帧率至少需要生成 1 帧，请缩短帧率或放长时间段。")
        elif params.out_frames > OUT_FRAMES_HARD_MAX:
            errors.append(
                f"输出帧数过多（约 {params.out_frames} 帧）：请缩短时间段、降低帧率或提高播放速度。"
            )
    return errors
