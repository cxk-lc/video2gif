# -*- coding: utf-8 -*-
"""错误类型与 ffmpeg 报错 → 中文用户文案映射。"""
from __future__ import annotations


class VideoToolError(Exception):
    """带用户可读文案的业务异常。

    user_msg: 一句话中文说明（直接展示给用户）
    hint:     处理建议（可为空）
    detail:   原始报错/技术细节（供「详情」查看）
    """

    def __init__(self, user_msg: str, hint: str = "", detail: str = "") -> None:
        super().__init__(user_msg)
        self.user_msg = user_msg
        self.hint = hint or ""
        self.detail = detail or ""

    def full_text(self) -> str:
        parts = [self.user_msg]
        if self.hint:
            parts.append(f"建议：{self.hint}")
        return "\n".join(parts)


class ConversionCancelled(Exception):
    """用户主动取消转换（非错误）。"""


# (匹配片段, 中文消息, 处理建议)
_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("Invalid data found when processing input",),
        "文件无法识别：可能不是视频文件，或文件已损坏。",
        "请确认所选文件能在播放器中正常播放后重试。",
    ),
    (
        ("moov atom not found",),
        "视频文件不完整（缺失关键数据）。",
        "文件可能未下载完成或已损坏，请更换文件。",
    ),
    (
        ("No such file or directory",),
        "找不到指定的文件。",
        "请确认文件未被移动或删除后重试。",
    ),
    (
        ("Permission denied",),
        "没有权限访问该文件或目录。",
        "请检查文件权限，或更换输出位置后重试。",
    ),
    (
        ("No space left on device",),
        "磁盘空间不足。",
        "请清理目标磁盘空间后重试。",
    ),
    (
        ("does not contain any stream", "Output file is empty"),
        "未生成任何画面：截取的时间段内没有有效帧。",
        "请检查起始/结束时间是否在视频时长范围内。",
    ),
    (
        ("Error while opening encoder", "Cannot load nvcuda", "Error initializing output stream"),
        "GIF 编码失败。",
        "请尝试减小输出尺寸或降低帧率后重试。",
    ),
    (
        ("Invalid argument",),
        "参数无效。",
        "请检查分辨率、帧率、时间等参数是否合理。",
    ),
    (
        ("Conversion failed",),
        "转换失败。",
        "请展开「详情」查看具体报错信息。",
    ),
]


def friendly_ffmpeg_error(raw: str) -> tuple[str, str]:
    """将 ffmpeg 原始输出映射为 (中文消息, 处理建议)。"""
    text = raw or ""
    for needles, msg, hint in _RULES:
        if any(n in text for n in needles):
            return msg, hint
    return "转换失败：转换引擎返回了错误。", "请展开「详情」查看具体报错信息，或更换文件重试。"
