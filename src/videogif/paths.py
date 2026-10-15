# -*- coding: utf-8 -*-
"""随包资源定位（兼容源码运行与 PyInstaller 冻结运行）。"""
from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path | None:
    """返回 assets/ 目录下资源文件的绝对路径；找不到返回 None。"""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / name)
        candidates.append(Path(sys.executable).resolve().parent / "assets" / name)
    else:
        candidates.append(Path(__file__).resolve().parents[2] / "assets" / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
