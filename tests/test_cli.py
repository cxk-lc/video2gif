# -*- coding: utf-8 -*-
"""命令行入口（src/cli.py）的端到端测试：真实子进程调用。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "cli.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def test_cli_probe(mp4_video: Path) -> None:
    r = _run("probe", "--input", str(mp4_video))
    assert r.returncode == 0, r.stderr
    assert "分辨率" in r.stdout and "320×240" in r.stdout
    assert "时长" in r.stdout


def test_cli_convert(mp4_video: Path, tmp_path: Path) -> None:
    out = tmp_path / "cli_out.gif"
    r = _run(
        "convert", "--input", str(mp4_video),
        "--start", "0.2", "--end", "1.2",
        "--fps", "8", "--width", "120",
        "--out", str(out),
    )
    assert r.returncode == 0, r.stderr
    assert out.exists() and out.stat().st_size > 0
    assert "[完成]" in r.stdout
    assert "[进度]" in r.stdout
    im = Image.open(out)
    assert im.size == (120, 90)
    assert abs((im.n_frames) - 8) <= 1


def test_cli_bad_params(mp4_video: Path) -> None:
    r = _run("convert", "--input", str(mp4_video), "--start", "5", "--end", "1")
    assert r.returncode == 2
    assert "参数错误" in r.stderr


def test_cli_missing_file(tmp_path: Path) -> None:
    r = _run("convert", "--input", str(tmp_path / "nope.mp4"), "--end", "1")
    assert r.returncode == 2
    assert "找不到文件" in r.stderr
