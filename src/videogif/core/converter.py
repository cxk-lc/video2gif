# -*- coding: utf-8 -*-
"""转换核心：两遍调色板 GIF 转换，带实时进度、取消与错误映射。"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ConversionCancelled, VideoToolError, friendly_ffmpeg_error
from .ffmpeg_locator import ffmpeg_popen
from .params import GifParams

# 两遍转换的进度权重：调色板阶段占前 35%，编码阶段占后 65%
_PALETTE_WEIGHT = 0.35

_STAGE_NAMES = {
    "palette": "生成调色板",
    "encode": "编码 GIF",
}


@dataclass
class StageProgress:
    """一次进度回调携带的数据。"""

    stage: str  # "palette" | "encode"
    stage_ratio: float  # 当前阶段内进度 0..1
    overall: float  # 整体进度 0..1

    @property
    def stage_name(self) -> str:
        return _STAGE_NAMES.get(self.stage, self.stage)


@dataclass
class ConversionResult:
    """一次成功转换的产物信息。"""

    gif_path: Path
    work_dir: Path
    elapsed: float  # 秒


ProgressCallback = Callable[[StageProgress], None]


def _fmt_seconds(v: float) -> str:
    return f"{max(0.0, v):.3f}"


def _hhmmss_to_seconds(text: str) -> float:
    """解析 ffmpeg -progress 的 out_time=HH:MM:SS.mmmmmm。"""
    try:
        h, m, s = text.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0


class GifConverter:
    """把 GifParams 描述的任务转换为 GIF 文件。

    用法：
        conv = GifConverter()
        result = conv.convert(params, on_progress=cb, cancel_event=ev)
        # result.gif_path 即生成的 GIF；用完调用 GifConverter.cleanup(result.work_dir)
    """

    def convert(
        self,
        params: GifParams,
        *,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        work_dir: Path | None = None,
    ) -> ConversionResult:
        src = Path(params.input_path)
        if not src.exists():
            raise VideoToolError(f"找不到文件：{src.name}", hint="请确认文件未被移动或删除。")

        work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="video2gif_"))
        work.mkdir(parents=True, exist_ok=True)
        palette_path = work / "palette.png"
        gif_path = work / "output.gif"
        started = time.monotonic()

        expected = max(params.out_duration, 1e-6)

        def emit(stage: str, ratio: float) -> None:
            if on_progress is None:
                return
            ratio = min(1.0, max(0.0, ratio))
            weight = _PALETTE_WEIGHT if stage == "palette" else (1.0 - _PALETTE_WEIGHT)
            base = 0.0 if stage == "palette" else _PALETTE_WEIGHT
            on_progress(StageProgress(stage=stage, stage_ratio=ratio, overall=base + weight * ratio))

        try:
            filters = params.video_filters()

            # ── 第 1 遍：调色板 ──────────────────────────────────────
            args1 = [
                "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                "-ss", _fmt_seconds(params.start), "-t", _fmt_seconds(params.clip_duration),
                "-i", str(src),
                "-vf", f"{filters},palettegen=max_colors={params.colors}:stats_mode=diff",
                "-progress", "pipe:1", "-nostats",
                str(palette_path),
            ]
            self._run_ffmpeg(args1, stage="palette", expected_seconds=expected,
                             emit=emit, cancel_event=cancel_event)

            # ── 第 2 遍：编码 GIF ───────────────────────────────────
            filter_complex = (
                f"[0:v]{filters}[x];"
                f"[x][1:v]paletteuse=dither={params.dither}:diff_mode=rectangle"
            )
            args2 = [
                "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                "-ss", _fmt_seconds(params.start), "-t", _fmt_seconds(params.clip_duration),
                "-i", str(src),
                "-i", str(palette_path),
                "-filter_complex", filter_complex,
                "-loop", str(params.loop),
                "-progress", "pipe:1", "-nostats",
                str(gif_path),
            ]
            self._run_ffmpeg(args2, stage="encode", expected_seconds=expected,
                             emit=emit, cancel_event=cancel_event)

            if not gif_path.exists() or gif_path.stat().st_size == 0:
                raise VideoToolError(
                    "转换已结束，但没有生成有效的 GIF 文件。",
                    hint="请检查起止时间是否在视频范围内，或更换输出参数后重试。",
                )
            emit("encode", 1.0)
            return ConversionResult(gif_path=gif_path, work_dir=work, elapsed=time.monotonic() - started)

        except ConversionCancelled:
            self.cleanup(work)
            raise
        except VideoToolError:
            self.cleanup(work)
            raise
        except Exception as exc:  # 兜底：不允许未知异常泄漏到界面层
            self.cleanup(work)
            raise VideoToolError(
                "转换过程中出现未预期的错误。",
                hint="请重试；若反复出现，请更换文件或参数。",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

    # ── 内部：单遍转换执行器 ────────────────────────────────────────
    def _run_ffmpeg(
        self,
        args: list[str],
        *,
        stage: str,
        expected_seconds: float,
        emit: Callable[[str, float], None],
        cancel_event: threading.Event | None,
    ) -> None:
        proc = ffmpeg_popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        stderr_tail: deque[str] = deque(maxlen=120)

        def drain_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_tail.append(line.rstrip("\r\n"))

        drainer = threading.Thread(target=drain_stderr, daemon=True)
        drainer.start()

        emit(stage, 0.0)
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    self._terminate(proc)
                    raise ConversionCancelled()
                key, _, value = line.strip().partition("=")
                if key == "out_time":
                    emit(stage, _hhmmss_to_seconds(value) / expected_seconds)
                elif key == "progress" and value.strip() == "end":
                    emit(stage, 1.0)
        finally:
            proc.wait()
            drainer.join(timeout=2)

        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled()

        if proc.returncode != 0:
            raw = "\n".join(stderr_tail)
            msg, hint = friendly_ffmpeg_error(raw)
            raise VideoToolError(msg, hint=hint, detail=raw or f"ffmpeg 退出码：{proc.returncode}")
        emit(stage, 1.0)

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        """安全终止 ffmpeg：先 terminate，宽限 5 秒后强杀。"""
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass

    @staticmethod
    def cleanup(work_dir: Path | str | None) -> None:
        """清理转换工作目录（临时 GIF / 调色板等）。

        Windows 下文件句柄未完全释放时删除可能短暂失败，此处带一次重试兜底。
        """
        if not work_dir:
            return
        target = Path(work_dir)
        shutil.rmtree(str(target), ignore_errors=True)
        if target.exists():
            time.sleep(0.2)
            shutil.rmtree(str(target), ignore_errors=True)
