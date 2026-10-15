#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取 ffmpeg 二进制到 tools/ffmpeg/ffmpeg.exe。

优先从项目 venv 已安装的 imageio-ffmpeg 包复制；缺失时给出安装提示。
用法: .venv\\Scripts\\python.exe tools\\get_ffmpeg.py
"""
import shutil
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent / "ffmpeg" / "ffmpeg.exe"


def main() -> int:
    if DEST.exists():
        print(f"已存在: {DEST}（如需更新请先删除该文件）")
        return 0
    try:
        import imageio_ffmpeg
    except ImportError:
        print("未找到 imageio-ffmpeg，请先运行: .venv\\Scripts\\pip install imageio-ffmpeg")
        return 1
    src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, DEST)
    print(f"已复制: {src} -> {DEST}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
