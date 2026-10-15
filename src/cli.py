#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头命令行工具（供自测 / 批量 / 排障使用，复用同一转换核心）。

用法示例：
    python src/cli.py probe  --input demo.mp4
    python src/cli.py convert --input demo.mp4 --start 0 --end 3 --fps 12 --width 480 --out demo.gif
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from videogif.core.converter import GifConverter, StageProgress  # noqa: E402
from videogif.core.errors import ConversionCancelled, VideoToolError  # noqa: E402
from videogif.core.params import (  # noqa: E402
    DEFAULT_QUALITY,
    QUALITY_PRESETS,
    GifParams,
    apply_quality,
    parse_time,
    validate_params,
)
from videogif.core.probe import probe_video  # noqa: E402


def _cmd_probe(args: argparse.Namespace) -> int:
    info = probe_video(args.input)
    print(f"文件：{info.path}")
    print(f"时长：{info.duration_text()}")
    print(f"分辨率：{info.resolution_text()}")
    print(f"原始帧率：{info.fps_text()}")
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    try:
        start = parse_time(args.start)
        end = parse_time(args.end) if args.end is not None else None
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    try:
        src = Path(args.input)
        if end is None:  # 未指定结束时间 -> 取整片
            info = probe_video(src)
            if info.duration is None:
                print("[参数错误] 无法读取视频时长，请显式指定 --end。", file=sys.stderr)
                return 2
            end = info.duration

        params = GifParams(
            input_path=src,
            start=start,
            end=end,
            fps=args.fps,
            width=args.width,
            height=args.height or None,
            speed=args.speed,
            loop=args.loop,
        )
        if args.colors is not None:
            params.colors = args.colors
            params.dither = QUALITY_PRESETS[args.quality][1] if args.quality else params.dither
        else:
            apply_quality(params, args.quality or DEFAULT_QUALITY)

        errors = validate_params(params, duration=None)
        if errors:
            print("[参数错误] " + "；".join(errors), file=sys.stderr)
            return 2

        out = Path(args.out) if args.out else src.with_suffix(".gif")
        last_bucket = {"v": -1}

        def on_progress(p: StageProgress) -> None:
            bucket = int(p.overall * 10)
            if bucket != last_bucket["v"]:
                last_bucket["v"] = bucket
                print(f"[进度] {p.overall * 100:5.1f}%  {p.stage_name}", flush=True)

        conv = GifConverter()
        import tempfile

        with tempfile.TemporaryDirectory(prefix="video2gif_cli_") as work:
            result = conv.convert(params, on_progress=on_progress, work_dir=Path(work))
            out.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copyfile(result.gif_path, out)

        size_kb = out.stat().st_size / 1024
        print(f"[完成] 已生成：{out}（{size_kb:.1f} KB，耗时 {result.elapsed:.2f}s）")
        return 0
    except ConversionCancelled:
        print("[取消] 转换已取消。", file=sys.stderr)
        return 3
    except VideoToolError as exc:
        print(f"[失败] {exc.full_text()}", file=sys.stderr)
        if exc.detail:
            print("—— 详情 ——", file=sys.stderr)
            print(exc.detail, file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="videogif", description="视频转 GIF 动图 · 命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("probe", help="读取视频信息")
    p1.add_argument("--input", required=True, help="视频文件路径")
    p1.set_defaults(func=_cmd_probe)

    p2 = sub.add_parser("convert", help="转换为 GIF")
    p2.add_argument("--input", required=True, help="视频文件路径")
    p2.add_argument("--start", default="0", help="起始时间（秒 / mm:ss / hh:mm:ss）")
    p2.add_argument("--end", default=None, help="结束时间；缺省为整片")
    p2.add_argument("--fps", type=int, default=12, help="输出帧率 1–30（默认 12）")
    p2.add_argument("--width", type=int, default=480, help="输出宽度（默认 480）")
    p2.add_argument("--height", type=int, default=0, help="输出高度；0=按比例自动")
    p2.add_argument("--speed", type=float, default=1.0, help="播放速度 0.25–4（默认 1）")
    p2.add_argument("--quality", choices=list(QUALITY_PRESETS), default=DEFAULT_QUALITY,
                    help="质量档位：高/中/低")
    p2.add_argument("--colors", type=int, default=None, help="颜色数 2–256（覆盖档位）")
    p2.add_argument("--loop", type=int, default=0, help="循环次数；0=无限循环")
    p2.add_argument("--out", default=None, help="输出 GIF 路径；缺省与输入同目录同名")
    p2.set_defaults(func=_cmd_convert)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
