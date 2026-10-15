#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（一次性工具，产物已入库；需要调整设计时重跑）。

用法: .venv\\Scripts\\python.exe tools\\make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_ICO = ROOT / "assets" / "app.ico"
SIZE = 256

# 配色（与界面提示色一致）
BLUE_TOP = (59, 130, 246)     # #3b82f6
BLUE_BOTTOM = (29, 78, 216)   # #1d4ed8
WHITE = (255, 255, 255, 255)


def build_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # 1) 圆角方形 + 纵向渐变背景
    gradient = Image.new("RGBA", (SIZE, SIZE))
    gd = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(BLUE_TOP, BLUE_BOTTOM)) + (255,)
        gd.line([(0, y), (SIZE, y)], fill=color)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((6, 6, SIZE - 6, SIZE - 6), radius=58, fill=255)
    img.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # 2) 白色圆角描边（“画面框”意象）
    d.rounded_rectangle((52, 52, 204, 204), radius=26, outline=WHITE, width=13)

    # 3) 中央白色播放三角（GIF 播放意象）
    d.polygon([(106, 86), (106, 170), (178, 128)], fill=WHITE)

    return img


def main() -> int:
    img = build_icon()
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        OUT_ICO,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    # 预览图（不入库，仅开发查看）
    preview = ROOT / "tests" / "_artifacts" / "app_icon_preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    img.save(preview)
    print(f"已生成: {OUT_ICO}")
    print(f"预览:   {preview}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
