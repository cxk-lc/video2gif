# AGENTS.md

> 本文件是 AI 编程代理的项目值班手册。进入本项目开启新会话时，先读取本文件并遵守以下规则。>   
> 保持精简：高频规则放在这里，细节按需引用其他文档。

## 交付规则（必须遵守）

1. **每次改动后必须创建 Git commit**，保留可追踪的版本快照，便于随时回退。
2. **每次改动后必须编写或更新相关测试**，并在交付前确保所有测试与验收全部通过。

## 项目信息

- 项目名称：视频转GIF动图
- 技术栈：Python 3.13（conda 派生 venv，`.venv/`）+ tkinter/ttk + ffmpeg 内置二进制（`tools/ffmpeg/`）+ Pillow；测试用 pytest
- 运行命令：双击 `启动.bat`；或 `.venv\Scripts\python.exe src\main.py`（GUI）；无头转换 `.venv\Scripts\python.exe src\cli.py convert --input <视频> --start <秒> --end <秒> --out <out.gif>`
- 测试命令：`.venv\Scripts\python.exe -m pytest tests/ -v`
- 打包命令：`.venv\Scripts\python.exe tools\build_exe.py`（产物 `dist\视频转GIF动图.exe`，需先有 `tools/ffmpeg/ffmpeg.exe`）；推 `v*` 标签后由 GitHub Actions 自动构建并发布 Release
- 目录说明：
  - `docs/`：产品设计文档（product-design.md）、技术方案文档（tech-design.md）、人工验收清单（acceptance-checklist.md）
  - `src/core/`：转换核心（无 GUI 依赖，可独立测试）
  - `src/gui/`：tkinter 界面与 GIF 预览
  - `tools/ffmpeg/`：内置 ffmpeg 二进制（不入 Git，获取方式见 README）
  - `tests/`：pytest 测试（用 ffmpeg lavfi 合成测试视频，不依赖外部素材）

## 边界约定

- 不擅自扩大需求范围；"暂时不做"的功能清单见 `docs/product-design.md`。
- 遇到规格不明确的情况：先提问或停下，不要猜测后直接实现。
- 重大架构调整前，先给出方案并等待确认。
