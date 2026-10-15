# -*- coding: utf-8 -*-
"""无头自检：合成测试视频 → 探测 → 转换 → 校验 GIF 产物。

供 `python src/main.py --selftest` 与排障使用；不依赖 GUI。
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .core.converter import GifConverter
from .core.ffmpeg_locator import ffmpeg_popen
from .core.params import GifParams, apply_quality
from .core.probe import probe_video


def _gen_test_video(path: Path, seconds: float = 2.0) -> None:
    args = [
        "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=30",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
    ]
    proc = ffmpeg_popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = proc.communicate(timeout=60)
    if proc.returncode != 0:
        raise RuntimeError((err or b"").decode("utf-8", "replace")[-2000:])


def run_selftest() -> bool:
    checks: list[tuple[str, bool, str]] = []

    tmp = Path(tempfile.mkdtemp(prefix="video2gif_selftest_"))
    try:
        video = tmp / "selftest.mp4"
        _gen_test_video(video, seconds=2.0)
        checks.append(("生成测试视频", video.exists() and video.stat().st_size > 0, str(video.stat().st_size) + " bytes"))

        info = probe_video(video)
        ok = (
            info.width == 320
            and info.height == 240
            and info.duration is not None
            and abs(info.duration - 2.0) < 0.2
        )
        checks.append(("探测视频信息", ok, info.summary()))

        params = GifParams(input_path=video, start=0.2, end=1.7, fps=10, width=160)
        apply_quality(params, "中")
        conv = GifConverter()
        result = conv.convert(params, work_dir=tmp / "work")

        from PIL import Image, ImageSequence  # 延迟导入：仅自检时使用

        im = Image.open(result.gif_path)
        frames = im.n_frames
        durs = [f.info.get("duration") or 0 for f in ImageSequence.Iterator(im)]
        total_ms = sum(durs)
        ok = (
            im.size == (160, 120)
            and abs(frames - 15) <= 1
            and im.info.get("loop") == 0
            and abs(total_ms - 1500) <= 150
        )
        checks.append(
            ("转换并校验 GIF", ok, f"size={im.size} frames={frames} total={total_ms}ms loop={im.info.get('loop')}")
        )
        im.close()  # 释放文件句柄，确保后续可清理临时目录（Windows 文件锁语义）
        conv.cleanup(result.work_dir)
    except Exception as exc:  # noqa: BLE001 - 自检需要把一切异常变为 FAIL
        checks.append(("自检执行", False, f"{type(exc).__name__}: {exc}"))
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print("=" * 52)
    print("视频转GIF动图 · 自检结果")
    print("=" * 52)
    all_ok = True
    for name, ok, note in checks:
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}：{note}")
    print("=" * 52)
    print("自检" + ("通过 ✔" if all_ok else "未通过 ✘"))
    return all_ok
