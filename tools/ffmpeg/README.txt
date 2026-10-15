ffmpeg.exe 来源与许可说明
========================

- 来源：imageio-ffmpeg PyPI 包内置二进制（文件名 ffmpeg-win-x86_64-v7.1.exe，
  构建来自 https://www.gyan.dev/ffmpeg/builds/ 的 essentials build）
- 版本：ffmpeg 7.1
- 许可：FFmpeg 本体遵循 GPL/LGPL 许可（本构建为 GPL 版）。本工具仅以
  外部程序方式调用该二进制进行视频解码与 GIF 编码，未对其做任何修改；
  随附分发时请遵循其许可要求。
- 说明：该 .exe 体积较大（约 87 MB），不纳入 Git 版本库。
  克隆/复制项目后，可通过以下任一方式重新获取：
    1) .venv\Scripts\python.exe tools\get_ffmpeg.py   （从 venv 内的 imageio-ffmpeg 复制）
    2) 自行从 https://www.gyan.dev/ffmpeg/builds/ 下载并放入本目录（命名为 ffmpeg.exe）
