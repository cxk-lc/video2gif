# -*- coding: utf-8 -*-
"""GIF 预览控件：Pillow 逐帧循环播放，按显示尺寸降采样。

内存策略：
- 帧数少（且缓存字节数在预算内）→ 预解码全部帧缓存为 PhotoImage，播放最顺滑；
- 帧数多 → 关闭帧缓存，每帧按需解码，避免内存膨胀。
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageSequence, ImageTk

_CACHE_BYTES_BUDGET = 120 * 1024 * 1024  # 预览帧缓存内存预算
_MAX_CACHE_FRAMES = 400
_PLACEHOLDER = "转换完成后在此预览"
_BG = "#f7f8fa"
_FG = "#9aa0a6"


class GifPreview(ttk.Frame):
    """一个自适应大小的 GIF 播放器。"""

    def __init__(self, master, max_w: int = 620, max_h: int = 300, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.max_w = max_w
        self.max_h = max_h

        self.label = tk.Label(
            self,
            text=_PLACEHOLDER,
            background=_BG,
            foreground=_FG,
            anchor="center",
            relief="solid",
            borderwidth=1,
            width=1,
            height=1,
        )
        self.label.pack(fill="both", expand=True)

        self._frames: list[ImageTk.PhotoImage] = []
        self._durations: list[int] = []
        self._img_obj: Image.Image | None = None
        self._lazy = False
        self._idx = 0
        self._job: str | None = None
        self._cur_photo: ImageTk.PhotoImage | None = None
        self._tw = self._th = 0

    # ── 对外接口 ─────────────────────────────────────────────
    def load(self, path: str | Path) -> tuple[int, int, int, float]:
        """载入并开始循环播放；返回 (帧数, 原始宽, 原始高, 总时长秒)。"""
        self.stop()
        self.clear()
        im = Image.open(path)
        n = getattr(im, "n_frames", 1) or 1
        w, h = im.size

        scale = min(self.max_w / w, self.max_h / h, 1.0) if w and h else 1.0
        scale = max(scale, 0.05)
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
        self._tw, self._th = tw, th

        per_frame_bytes = tw * th * 4
        cache_limit = max(1, min(_MAX_CACHE_FRAMES, _CACHE_BYTES_BUDGET // max(1, per_frame_bytes)))
        self._lazy = n > cache_limit

        self._frames = []
        self._durations = []
        total_ms = 0

        if self._lazy:
            self._img_obj = im
            for frame in ImageSequence.Iterator(im):
                d = int(frame.info.get("duration") or 0) or 100
                self._durations.append(d)
                total_ms += d
        else:
            for frame in ImageSequence.Iterator(im):
                d = int(frame.info.get("duration") or 0) or 100
                self._durations.append(d)
                total_ms += d
                small = frame.convert("RGBA").resize((tw, th), Image.Resampling.LANCZOS)
                self._frames.append(ImageTk.PhotoImage(small))
            # 帧已全部转换为 PhotoImage 副本，可安全释放文件句柄
            # （Windows 下不释放会导致临时 GIF 无法删除）
            try:
                im.close()
            except Exception:
                pass

        self._idx = 0
        self._show_current()
        self.play()
        return n, w, h, total_ms / 1000.0

    def play(self) -> None:
        if self._job is not None:
            return
        if not self._durations:
            return
        self._idx = 0
        self._tick()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def clear(self) -> None:
        self.stop()
        self._frames = []
        self._durations = []
        if self._img_obj is not None:
            try:
                self._img_obj.close()  # 释放文件句柄（Windows 下不释放会导致文件无法删除）
            except Exception:
                pass
        self._img_obj = None
        self._cur_photo = None
        self._lazy = False
        self._idx = 0
        self.label.configure(image="", text=_PLACEHOLDER, width=1, height=1)

    # ── 内部 ────────────────────────────────────────────────
    def _show_current(self) -> None:
        if self._lazy and self._img_obj is not None:
            self._img_obj.seek(self._idx)
            frame = self._img_obj.convert("RGBA").resize(
                (self._tw, self._th), Image.Resampling.LANCZOS
            )
            self._cur_photo = ImageTk.PhotoImage(frame)
            self.label.configure(image=self._cur_photo, text="")
        elif self._frames:
            self.label.configure(image=self._frames[self._idx % len(self._frames)], text="")

    def _tick(self) -> None:
        n = len(self._durations)
        if n == 0:
            self._job = None
            return
        self._show_current()
        delay = self._durations[self._idx % n]
        self._idx = (self._idx + 1) % n
        self._job = self.after(max(20, delay), self._tick)
