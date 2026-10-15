#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视频转 GIF 动图 · 程序入口（GUI）。

用法：
    python src/main.py                    # 打开界面
    python src/main.py --open demo.mp4    # 打开界面并预载视频
    python src/main.py --selftest         # 无头自检（不打开界面）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _ensure_std_streams() -> None:
    """pythonw 启动时 stdout/stderr 为 None，兜底到 devnull，避免 print 崩溃。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _enable_dpi_awareness() -> None:
    """开启进程 DPI 感知，避免高分屏下界面模糊。"""
    if os.name != "nt":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _ensure_std_streams()
    parser = argparse.ArgumentParser(prog="视频转GIF动图", description="把视频片段转换为可循环播放的 GIF 动图")
    parser.add_argument("--open", metavar="视频文件", default=None, help="启动后直接载入该视频")
    parser.add_argument("--selftest", action="store_true", help="运行无头自检后退出（不打开界面）")
    args = parser.parse_args(argv)

    if args.selftest:
        from videogif.selftest import run_selftest

        return 0 if run_selftest() else 1

    _enable_dpi_awareness()
    from videogif.gui.app import run_app

    return run_app(initial_file=args.open)


if __name__ == "__main__":
    sys.exit(main())
