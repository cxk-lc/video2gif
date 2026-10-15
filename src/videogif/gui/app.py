# -*- coding: utf-8 -*-
"""主窗口：文件选择、参数设置、转换、进度、预览与保存。

线程模型：所有耗时操作（探测 / 转换）在工作线程执行，通过队列把事件
投递回主线程，由 `after` 轮询消费——保证窗口全程不卡死。
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..core.converter import ConversionResult, GifConverter
from ..core.errors import ConversionCancelled, VideoToolError
from ..core.params import (
    COLORS_MAX,
    COLORS_MIN,
    DEFAULT_QUALITY,
    FPS_MAX,
    FPS_MIN,
    LOOP_MAX,
    QUALITY_PRESETS,
    SPEED_MAX,
    SPEED_MIN,
    WIDTH_MAX,
    WIDTH_MIN,
    GifParams,
    estimated_size_text,
    format_time,
    parse_time,
    validate_params,
)
from ..core.probe import VideoInfo, probe_video
from .preview import GifPreview

VIDEO_FILE_TYPES = [
    ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.webm *.flv *.m4v *.mpg *.mpeg *.ts *.3gp *.rmvb"),
    ("所有文件", "*.*"),
]

STATE_IDLE = "idle"
STATE_PROBING = "probing"
STATE_CONVERTING = "converting"
STATE_DONE = "done"

_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]+')
_DIM_FG = "#666666"
_ACCENT_FG = "#0a66c2"
_ERROR_FG = "#c0392b"


def _elide_middle(text: str, limit: int = 72) -> str:
    if len(text) <= limit:
        return text
    half = max(1, (limit - 1) // 2)
    return text[:half] + "…" + text[-(limit - 1 - half):]


def _setup_fonts(root: tk.Tk) -> None:
    """优先使用微软雅黑，保证中文显示统一。"""
    try:
        import tkinter.font as tkfont

        available = set(tkfont.families(root))
        family = next((f for f in ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei") if f in available), None)
        if not family:
            return
        for name in (
            "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
            "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
        ):
            try:
                tkfont.nametofont(name).configure(family=family)
            except Exception:
                pass
    except Exception:
        pass


def _setup_dpi_scaling(root: tk.Tk) -> None:
    """按屏幕 DPI 设置 tk 缩放，避免高分屏下字体/控件过小。"""
    try:
        dpi = float(root.winfo_fpixels("1i"))
        if dpi > 0 and abs(dpi - 72.0) > 1.0:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass


class ErrorDialog(tk.Toplevel):
    """带「复制详情」的只读错误对话框。"""

    def __init__(self, master: tk.Misc, title: str, message: str) -> None:
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(True, True)
        self._message = message

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, font=("", 11, "bold")).pack(anchor="w")

        text = tk.Text(frame, wrap="word", width=78, height=self._estimate_text_height(message))
        text.pack(fill="both", expand=True, pady=(8, 8))
        text.insert("1.0", message)
        text.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self._btn_copy = ttk.Button(buttons, text="复制详情", command=self._copy)
        self._btn_copy.pack(side="left")
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right")

        self.update_idletasks()
        self._center_over(master)
        self.grab_set()
        self.focus_set()

    @staticmethod
    def _estimate_text_height(message: str, per_line: int = 36) -> int:
        """按消息长度粗略估算文本框高度（限 5–18 行），避免短消息撑出大空白。"""
        lines = 0
        for raw in message.splitlines() or [""]:
            lines += max(1, (len(raw) + per_line - 1) // per_line)
        return min(18, max(5, lines + 1))

    def _center_over(self, master: tk.Misc) -> None:
        try:
            w, h = self.winfo_width(), self.winfo_height()
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            x = mx + max(0, (mw - w) // 2)
            y = my + max(0, (mh - h) // 3)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self._message)
            self._btn_copy.configure(text="已复制 ✓")
        except Exception:
            pass


class GifApp:
    """应用主窗口控制器。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("视频转 GIF 动图")
        root.minsize(880, 700)

        # ── 状态 ──────────────────────────────────────────────
        self.state = STATE_IDLE
        self.file_path: Path | None = None
        self._info: VideoInfo | None = None
        self._result: ConversionResult | None = None
        self._last_saved: Path | None = None
        self._last_params: GifParams | None = None
        self._cancel_event: threading.Event | None = None
        self._worker: threading.Thread | None = None
        self._q: queue.Queue[tuple[str, object]] = queue.Queue()
        self._converted_sig: str | None = None

        # ── 变量 ──────────────────────────────────────────────
        self.file_name_var = tk.StringVar(value="（尚未选择文件）")
        self.file_info_var = tk.StringVar(value="")
        self.start_var = tk.StringVar(value="0")
        self.end_var = tk.StringVar(value="")
        self.fps_var = tk.StringVar(value="12")
        self.width_var = tk.StringVar(value="480")
        self.height_auto_var = tk.BooleanVar(value=True)
        self.height_var = tk.StringVar(value="")
        self.speed_var = tk.StringVar(value="1.0")
        self.quality_var = tk.StringVar(value=DEFAULT_QUALITY)
        self.colors_var = tk.StringVar(value=str(QUALITY_PRESETS[DEFAULT_QUALITY][0]))
        self.loop_var = tk.StringVar(value="0")
        self.estimate_var = tk.StringVar(value="选择视频并设置参数后，这里会显示输出预估。")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.stage_var = tk.StringVar(value="就绪")
        self.preview_info_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="请先选择要转换的视频文件。")

        self._build_ui()
        self._bind_traces()
        self._refresh_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll_queue)

    # ══════════════════ 界面构建 ══════════════════
    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        # ① 选择视频
        sec1 = ttk.LabelFrame(main, text=" ① 选择视频 ", padding=(10, 8))
        sec1.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        sec1.columnconfigure(1, weight=1)
        self.btn_choose = ttk.Button(sec1, text="选择视频…", command=self._choose_file, width=12)
        self.btn_choose.grid(row=0, column=0, rowspan=2, padx=(0, 12), pady=2, sticky="ns")
        ttk.Label(sec1, textvariable=self.file_name_var, font=("", 10, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(sec1, textvariable=self.file_info_var, foreground=_DIM_FG).grid(row=1, column=1, sticky="w", pady=(2, 0))

        # ② 转换参数
        sec2 = ttk.LabelFrame(main, text=" ② 转换参数 ", padding=(10, 10))
        sec2.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        pad = {"padx": (0, 8), "pady": 4}

        ttk.Label(sec2, text="起始时间").grid(row=0, column=0, sticky="e", **pad)
        self.e_start = ttk.Entry(sec2, textvariable=self.start_var, width=12)
        self.e_start.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(sec2, text="结束时间").grid(row=0, column=2, sticky="e", **pad)
        self.e_end = ttk.Entry(sec2, textvariable=self.end_var, width=12)
        self.e_end.grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(sec2, text="支持 秒 / mm:ss / hh:mm:ss", foreground=_DIM_FG).grid(
            row=0, column=4, columnspan=4, sticky="w", **pad
        )

        ttk.Label(sec2, text="输出帧率").grid(row=1, column=0, sticky="e", **pad)
        frame_fps = ttk.Frame(sec2)
        frame_fps.grid(row=1, column=1, sticky="w", **pad)
        self.s_fps = ttk.Spinbox(frame_fps, from_=FPS_MIN, to=FPS_MAX, textvariable=self.fps_var, width=5)
        self.s_fps.pack(side="left")
        ttk.Label(frame_fps, text=" fps").pack(side="left")

        ttk.Label(sec2, text="输出宽度").grid(row=1, column=2, sticky="e", **pad)
        frame_w = ttk.Frame(sec2)
        frame_w.grid(row=1, column=3, sticky="w", **pad)
        self.s_width = ttk.Spinbox(frame_w, from_=WIDTH_MIN, to=WIDTH_MAX, increment=2, textvariable=self.width_var, width=7)
        self.s_width.pack(side="left")
        ttk.Label(frame_w, text=" px").pack(side="left")

        ttk.Label(sec2, text="输出高度").grid(row=1, column=4, sticky="e", **pad)
        frame_h = ttk.Frame(sec2)
        frame_h.grid(row=1, column=5, sticky="w", **pad)
        self.s_height = ttk.Spinbox(frame_h, from_=WIDTH_MIN, to=WIDTH_MAX, increment=2, textvariable=self.height_var, width=7, state="disabled")
        self.s_height.pack(side="left")
        ttk.Label(frame_h, text=" px").pack(side="left")
        self.cb_height_auto = ttk.Checkbutton(frame_h, text="等比自动", variable=self.height_auto_var, command=self._on_height_auto_toggle)
        self.cb_height_auto.pack(side="left", padx=(8, 0))

        ttk.Label(sec2, text="播放速度").grid(row=2, column=0, sticky="e", **pad)
        frame_speed = ttk.Frame(sec2)
        frame_speed.grid(row=2, column=1, sticky="w", **pad)
        self.s_speed = ttk.Spinbox(frame_speed, from_=SPEED_MIN, to=SPEED_MAX, increment=0.25, textvariable=self.speed_var, width=5, format="%.2f")
        self.s_speed.pack(side="left")
        ttk.Label(frame_speed, text=" ×").pack(side="left")

        ttk.Label(sec2, text="质量档位").grid(row=2, column=2, sticky="e", **pad)
        self.cb_quality = ttk.Combobox(sec2, textvariable=self.quality_var, values=list(QUALITY_PRESETS), state="readonly", width=6)
        self.cb_quality.grid(row=2, column=3, sticky="w", **pad)

        ttk.Label(sec2, text="颜色数").grid(row=2, column=4, sticky="e", **pad)
        frame_colors = ttk.Frame(sec2)
        frame_colors.grid(row=2, column=5, sticky="w", **pad)
        self.s_colors = ttk.Spinbox(frame_colors, from_=COLORS_MIN, to=COLORS_MAX, increment=8, textvariable=self.colors_var, width=6)
        self.s_colors.pack(side="left")

        ttk.Label(sec2, text="循环次数").grid(row=2, column=6, sticky="e", **pad)
        frame_loop = ttk.Frame(sec2)
        frame_loop.grid(row=2, column=7, sticky="w", **pad)
        self.s_loop = ttk.Spinbox(frame_loop, from_=0, to=LOOP_MAX, textvariable=self.loop_var, width=6)
        self.s_loop.pack(side="left")
        ttk.Label(frame_loop, text=" 次（0＝无限）").pack(side="left")

        self.lbl_estimate = ttk.Label(sec2, textvariable=self.estimate_var, foreground=_ACCENT_FG, wraplength=820, justify="left")
        self.lbl_estimate.grid(row=3, column=0, columnspan=8, sticky="w", pady=(10, 0))

        # 操作按钮
        sec3 = ttk.Frame(main)
        sec3.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.btn_start = ttk.Button(sec3, text="开始转换", command=self._start_convert, width=16)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(sec3, text="取消", command=self._cancel_convert, width=8, state="disabled")
        self.btn_cancel.pack(side="left", padx=(8, 0))
        self.btn_reveal = ttk.Button(sec3, text="打开所在文件夹", command=self._reveal, width=16, state="disabled")
        self.btn_reveal.pack(side="right")
        self.btn_save = ttk.Button(sec3, text="保存到…", command=self._save_gif, width=12, state="disabled")
        self.btn_save.pack(side="right", padx=(0, 8))

        # 进度
        sec4 = ttk.Frame(main)
        sec4.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        sec4.columnconfigure(0, weight=1)
        self.pbar = ttk.Progressbar(sec4, variable=self.progress_var, maximum=100.0)
        self.pbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(sec4, textvariable=self.stage_var, width=30, anchor="w").grid(row=0, column=1, padx=(12, 0))

        # ③ 预览与保存
        sec5 = ttk.LabelFrame(main, text=" ③ 预览 ", padding=(10, 8))
        sec5.grid(row=4, column=0, sticky="nsew", pady=(0, 6))
        main.rowconfigure(4, weight=1)
        # 先 pack 底部信息行，再让预览区填充剩余空间：避免空间不足时信息行被裁剪
        ttk.Label(sec5, textvariable=self.preview_info_var, foreground=_DIM_FG).pack(
            side="bottom", anchor="w", pady=(6, 0)
        )
        self.preview = GifPreview(sec5, max_w=680, max_h=280)
        self.preview.pack(fill="both", expand=True)

        # 状态栏
        self.lbl_status = ttk.Label(main, textvariable=self.status_var, anchor="w")
        self.lbl_status.grid(row=5, column=0, sticky="ew")

    def _bind_traces(self) -> None:
        for var in (
            self.start_var, self.end_var, self.fps_var, self.width_var, self.height_var,
            self.speed_var, self.colors_var, self.loop_var,
        ):
            var.trace_add("write", self._on_param_change)
        self.quality_var.trace_add("write", self._on_quality_change)
        self.cb_quality.bind("<<ComboboxSelected>>", lambda _e: self._on_quality_selected())

    # ══════════════════ 参数与预估 ══════════════════
    @staticmethod
    def _read_number(var: tk.StringVar, label: str, cast=float):
        text = str(var.get()).strip()
        try:
            value = float(text)
        except Exception:
            raise ValueError(f"「{label}」需要填写数字。") from None
        return int(round(value)) if cast is int else value

    def _collect_params(self, require_file: bool) -> GifParams | None:
        """从界面控件收集参数；解析失败抛 ValueError（中文消息）。"""
        if self.file_path is None:
            if require_file:
                raise ValueError("请先选择视频文件。")
            return None
        start = parse_time(self.start_var.get())
        end_text = self.end_var.get().strip()
        if end_text:
            end = parse_time(end_text)
        elif self._info is not None and self._info.duration is not None:
            end = self._info.duration
        else:
            end = 0.0
        params = GifParams(
            input_path=self.file_path,
            start=start,
            end=end,
            fps=self._read_number(self.fps_var, "输出帧率", int),
            width=self._read_number(self.width_var, "输出宽度", int),
            height=None if self.height_auto_var.get() else self._read_number(self.height_var, "输出高度", int),
            speed=self._read_number(self.speed_var, "播放速度", float),
            colors=self._read_number(self.colors_var, "颜色数", int),
            loop=self._read_number(self.loop_var, "循环次数", int),
        )
        params.dither = QUALITY_PRESETS.get(self.quality_var.get(), QUALITY_PRESETS[DEFAULT_QUALITY])[1]
        return params

    def _params_signature(self) -> str | None:
        try:
            params = self._collect_params(require_file=False)
        except ValueError:
            return None
        if params is None:
            return None
        return "|".join(
            str(v) for v in (
                params.input_path, params.start, params.end, params.fps, params.width,
                params.height, params.speed, params.colors, params.dither, params.loop,
            )
        )

    def _on_param_change(self, *_args) -> None:
        self._update_estimate()
        if self.state == STATE_DONE and self._converted_sig is not None:
            if self._params_signature() != self._converted_sig:
                self._set_status("参数已修改：请重新点击「开始转换」以应用（当前预览/可保存的是上一次结果）。")

    def _on_quality_change(self, *_args) -> None:
        # 档位联动颜色数（用户仍可随后手动微调颜色数）
        preset = QUALITY_PRESETS.get(self.quality_var.get())
        if preset:
            self.colors_var.set(str(preset[0]))

    def _on_quality_selected(self) -> None:
        self._update_estimate()

    def _on_height_auto_toggle(self) -> None:
        self._refresh_widgets()
        self._update_estimate()

    def _update_estimate(self) -> None:
        if self.state == STATE_CONVERTING:
            return
        try:
            params = self._collect_params(require_file=False)
        except ValueError:
            self.estimate_var.set("当前输入无法解析，请检查时间/数字格式。")
            return
        if params is None:
            self.estimate_var.set("选择视频并设置参数后，这里会显示输出预估。")
            return
        src_w = self._info.width if self._info else None
        src_h = self._info.height if self._info else None
        self.estimate_var.set(estimated_size_text(params, src_w, src_h))

    # ══════════════════ 状态刷新 ══════════════════
    def _refresh_widgets(self) -> None:
        busy = self.state in (STATE_CONVERTING, STATE_PROBING)
        normal = "disabled" if busy else "normal"

        for w in (self.btn_choose, self.e_start, self.e_end, self.s_fps, self.s_width,
                  self.s_speed, self.s_colors, self.s_loop, self.cb_height_auto):
            w.configure(state=normal)
        self.s_height.configure(state=("disabled" if (busy or self.height_auto_var.get()) else "normal"))
        self.cb_quality.configure(state=("disabled" if busy else "readonly"))

        has_file = self._info is not None
        self.btn_start.configure(state=("normal" if (has_file and not busy) else "disabled"))
        self.btn_cancel.configure(state=("normal" if self.state == STATE_CONVERTING else "disabled"))
        self.btn_save.configure(state=("normal" if (self._result is not None and not busy) else "disabled"))
        can_reveal = (self._last_saved is not None and self._last_saved.exists()) or self._result is not None
        self.btn_reveal.configure(state=("normal" if (can_reveal and not busy) else "disabled"))

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.lbl_status.configure(foreground=_ERROR_FG if error else "")

    # ══════════════════ 文件载入 ══════════════════
    def _choose_file(self) -> None:
        if self.state in (STATE_CONVERTING, STATE_PROBING):
            return
        path = filedialog.askopenfilename(title="选择视频文件", filetypes=VIDEO_FILE_TYPES)
        if path:
            self.load_file(path)

    def load_file(self, path: str | Path) -> None:
        p = Path(path)
        self.file_path = p
        self.file_name_var.set(_elide_middle(str(p)))
        self.file_info_var.set("正在读取视频信息…")
        self._info = None
        self._dispose_result()
        self.state = STATE_PROBING
        self._set_status("正在读取视频信息…")
        self._refresh_widgets()

        def work() -> None:
            try:
                self._q.put(("probe_ok", probe_video(p)))
            except VideoToolError as exc:
                self._q.put(("probe_err", exc))
            except Exception as exc:  # 兜底
                self._q.put(("probe_err", VideoToolError(
                    "读取视频信息时出现未预期的错误。", hint="请更换文件后重试。",
                    detail=f"{type(exc).__name__}: {exc}",
                )))

        threading.Thread(target=work, daemon=True).start()

    def _on_probe_ok(self, info: VideoInfo) -> None:
        self._info = info
        self.file_info_var.set(info.summary())
        self.start_var.set("0")
        self.end_var.set(format_time(info.duration) if info.duration is not None else "")
        if info.width:
            self.width_var.set(str(info.width))
        self.state = STATE_IDLE
        self._set_status(f"已载入视频：{info.path.name}。设置参数后点击「开始转换」。")
        self._update_estimate()
        self._refresh_widgets()

    def _on_probe_err(self, exc: VideoToolError) -> None:
        self._info = None
        self.file_path = None
        self.file_name_var.set("（尚未选择文件）")
        self.file_info_var.set("")
        self.state = STATE_IDLE
        self._set_status("读取视频信息失败。", error=True)
        self._update_estimate()
        self._refresh_widgets()
        ErrorDialog(self.root, "无法读取视频", exc.full_text())

    # ══════════════════ 转换 ══════════════════
    def _start_convert(self) -> None:
        if self.state not in (STATE_IDLE, STATE_DONE):
            return
        try:
            params = self._collect_params(require_file=True)
        except ValueError as exc:
            messagebox.showwarning("参数有误", str(exc), parent=self.root)
            return
        assert params is not None
        duration = self._info.duration if self._info else None
        errors = validate_params(params, duration)
        if errors:
            messagebox.showwarning("参数有误", "\n".join("· " + e for e in errors), parent=self.root)
            return

        self._dispose_result()
        self._last_params = params
        self._cancel_event = threading.Event()
        self.state = STATE_CONVERTING
        self.progress_var.set(0.0)
        self.stage_var.set("准备中…")
        self._set_status("开始转换…")
        self._refresh_widgets()

        cancel_event = self._cancel_event

        def work() -> None:
            converter = GifConverter()
            try:
                result = converter.convert(
                    params,
                    on_progress=lambda p: self._q.put(("conv_progress", p)),
                    cancel_event=cancel_event,
                )
                self._q.put(("conv_ok", result))
            except ConversionCancelled:
                self._q.put(("conv_cancelled", None))
            except VideoToolError as exc:
                self._q.put(("conv_err", exc))
            except Exception as exc:  # 兜底：未知异常也必须回到界面
                self._q.put(("conv_err", VideoToolError(
                    "转换过程中出现未预期的错误。", hint="请重试；若反复出现请更换文件或参数。",
                    detail=f"{type(exc).__name__}: {exc}",
                )))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _cancel_convert(self) -> None:
        if self.state == STATE_CONVERTING and self._cancel_event is not None:
            self._cancel_event.set()
            self.btn_cancel.configure(state="disabled")
            self._set_status("正在取消…")

    def _on_conv_progress(self, payload) -> None:
        overall = float(getattr(payload, "overall", 0.0))
        stage_ratio = float(getattr(payload, "stage_ratio", 0.0))
        stage_name = getattr(payload, "stage_name", "")
        self.progress_var.set(overall * 100.0)
        self.stage_var.set(f"{stage_name} {stage_ratio * 100:.0f}%")

    def _on_conv_ok(self, result: ConversionResult) -> None:
        self._result = result
        self.state = STATE_DONE
        self.progress_var.set(100.0)
        self.stage_var.set("完成")
        try:
            frames, w, h, dur = self.preview.load(result.gif_path)
            size_kb = result.gif_path.stat().st_size / 1024.0
            size_txt = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
            self.preview_info_var.set(f"{w}×{h} ｜ {frames} 帧 ｜ {dur:.2f} 秒 ｜ {size_txt}")
        except Exception as exc:  # 预览失败不影响产物
            self.preview_info_var.set("（预览加载失败）")
            self._set_status(f"转换完成，但预览加载失败：{exc}", error=True)
        self._converted_sig = self._params_signature()
        self._set_status("转换完成：可预览效果，满意后点击「保存到…」保存 GIF。")
        self._refresh_widgets()

    def _on_conv_err(self, exc: VideoToolError) -> None:
        self.state = STATE_IDLE
        self.progress_var.set(0.0)
        self.stage_var.set("失败")
        self._set_status("转换失败，请根据提示调整后重试。", error=True)
        self._refresh_widgets()
        ErrorDialog(self.root, "转换失败", exc.full_text())

    def _on_conv_cancelled(self) -> None:
        self.state = STATE_IDLE
        self.progress_var.set(0.0)
        self.stage_var.set("已取消")
        self._set_status("已取消转换。可调整参数后重新开始。")
        self._refresh_widgets()

    # ══════════════════ 保存与展示 ══════════════════
    def _default_save_name(self) -> str:
        stem = self._info.path.stem if self._info else "output"
        p = self._last_params
        if p is None:
            return f"{stem}_动图.gif"
        parts = [stem, f"{p.start:g}-{p.end:g}s", f"{p.fps}fps"]
        if abs(p.speed - 1.0) > 1e-9:
            parts.append(f"{p.speed:g}x")
        parts.append("动图")
        return _ILLEGAL_CHARS.sub("_", "_".join(parts)) + ".gif"

    def _save_gif(self) -> None:
        if self._result is None:
            return
        initial_dir = str(self._info.path.parent) if self._info else None
        dest = filedialog.asksaveasfilename(
            title="保存 GIF 动图",
            defaultextension=".gif",
            initialfile=self._default_save_name(),
            initialdir=initial_dir,
            filetypes=[("GIF 动图", "*.gif"), ("所有文件", "*.*")],
        )
        if not dest:
            return
        try:
            shutil.copyfile(self._result.gif_path, dest)
        except Exception as exc:
            ErrorDialog(self.root, "保存失败", VideoToolError(
                "无法保存到所选位置。",
                hint="请检查目标文件夹是否存在、是否有写入权限，或更换保存位置。",
                detail=f"{type(exc).__name__}: {exc}",
            ).full_text())
            return
        self._last_saved = Path(dest)
        self._set_status(f"已保存：{dest}")
        self._refresh_widgets()
        messagebox.showinfo("保存成功", f"GIF 已保存到：\n{dest}", parent=self.root)

    def _reveal(self) -> None:
        target: Path | None = None
        if self._last_saved is not None and self._last_saved.exists():
            target = self._last_saved
        elif self._result is not None:
            target = self._result.gif_path
        if target is None:
            return
        try:
            subprocess.Popen(["explorer", "/select,", str(target)])
        except Exception:
            try:
                os.startfile(str(target.parent))
            except Exception:
                self._set_status("无法打开所在文件夹。", error=True)

    def _dispose_result(self) -> None:
        # 先释放预览对文件句柄的占用，再删临时目录（Windows 文件锁语义）
        self.preview.clear()
        if self._result is not None:
            GifConverter.cleanup(self._result.work_dir)
            self._result = None
        self.preview_info_var.set("")

    # ══════════════════ 事件循环与退出 ══════════════════
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "probe_ok":
                    self._on_probe_ok(payload)  # type: ignore[arg-type]
                elif kind == "probe_err":
                    self._on_probe_err(payload)  # type: ignore[arg-type]
                elif kind == "conv_progress":
                    self._on_conv_progress(payload)
                elif kind == "conv_ok":
                    self._on_conv_ok(payload)  # type: ignore[arg-type]
                elif kind == "conv_err":
                    self._on_conv_err(payload)  # type: ignore[arg-type]
                elif kind == "conv_cancelled":
                    self._on_conv_cancelled()
        except queue.Empty:
            pass
        self.root.after(60, self._poll_queue)

    def _on_close(self) -> None:
        if self.state == STATE_CONVERTING:
            if not messagebox.askyesno("正在转换", "转换尚未完成，确定要退出吗？", parent=self.root):
                return
            if self._cancel_event is not None:
                self._cancel_event.set()
            if self._worker is not None and self._worker.is_alive():
                self._worker.join(timeout=3.0)
        self.preview.stop()
        self._dispose_result()
        self.root.destroy()


def run_app(initial_file: str | None = None) -> int:
    """创建并运行主窗口。"""
    root = tk.Tk()
    _setup_dpi_scaling(root)
    _setup_fonts(root)
    app = GifApp(root)
    if initial_file:
        root.after(150, lambda: app.load_file(initial_file))
    root.mainloop()
    return 0
