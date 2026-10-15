#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包免环境 exe（PyInstaller onefile）。

用法: .venv\\Scripts\\python.exe tools\\build_exe.py

产物: dist/视频转GIF动图.exe
  - 内嵌 Python 运行时、tkinter、Pillow 与 ffmpeg 转换引擎（约百 MB 级，属正常）
  - 冻结态由 src/videogif/core/ffmpeg_locator.py 从 sys._MEIPASS 定位内嵌 ffmpeg
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "tools" / "ffmpeg" / "ffmpeg.exe"
ICON = ROOT / "assets" / "app.ico"
APP_NAME = "视频转GIF动图"
EXE_PATH = ROOT / "dist" / f"{APP_NAME}.exe"


def main() -> int:
    if not FFMPEG.exists():
        print("[x] 缺少内置 ffmpeg，请先运行: .venv\\Scripts\\python.exe tools\\get_ffmpeg.py")
        return 1

    sep = ";" if sys.platform == "win32" else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", APP_NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyi"),
        "--specpath", str(ROOT / "build" / "pyi"),
        # 内嵌转换引擎（避免依赖系统 ffmpeg）
        "--add-binary", f"{FFMPEG}{sep}tools/ffmpeg",
        # 明确排除：本 pip 包里含第二份 87MB 二进制，且冻结态不需要它
        "--exclude-module", "imageio_ffmpeg",
        "--exclude-module", "pytest",
    ]
    if ICON.exists():
        args += ["--icon", str(ICON), "--add-data", f"{ICON}{sep}assets"]

    # conda Python 的 C 扩展依赖散落在 Library\bin，PyInstaller 无法自动收集：
    #   _ctypes.pyd  -> ffi.dll
    #   _tkinter.pyd -> tcl86t.dll / tk86t.dll
    # （二者依赖的 VCRUNTIME140 / zlib 已被自动收集）非 conda 环境（如 CI 的 python.org
    # 版本）目录不存在则自动跳过，不影响构建。
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    for dll_name in ("ffi.dll", "tcl86t.dll", "tk86t.dll"):
        dll = conda_bin / dll_name
        if dll.exists():
            args += ["--add-binary", f"{dll}{sep}."]

    args.append(str(ROOT / "src" / "main.py"))

    print("[build] PyInstaller 开始构建（首次约 2~5 分钟）…")
    proc = subprocess.run(args, cwd=str(ROOT))
    ok = proc.returncode == 0 and EXE_PATH.exists()
    if ok:
        size_mb = EXE_PATH.stat().st_size / 1024 / 1024
        print(f"[build] 成功：{EXE_PATH}（{size_mb:.1f} MB）")
        return 0
    print("[build] 失败，请检查上方输出。")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
