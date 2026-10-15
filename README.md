# 视频转 GIF 动图

一个 Windows 本地桌面小工具：把常见视频（MP4 / AVI / MOV 等）的指定片段，按自定义帧率、尺寸、速度与质量参数，转换为**可循环播放的 GIF 动图**——先预览，满意后再保存到本地。

![python](https://img.shields.io/badge/Python-3.13-blue) 技术栈：Python + tkinter / ttk + ffmpeg（内置）

---

## 快速开始

**本机（已配置好环境）**：双击根目录的 `启动.bat` 即可。

**首次在新环境部署**（需要已有 Python 3.11+ 且包含 tkinter）：

```bat
:: 1. 创建虚拟环境（若基础 Python 含 tkinter，venv 中即自动可用）
python -m venv .venv

:: 2. 安装依赖
.venv\Scripts\pip install -r requirements.txt

:: 3. 获取内置转换引擎 ffmpeg
.venv\Scripts\python.exe tools\get_ffmpeg.py

:: 4. 启动
启动.bat
```

---

## 使用说明

1. 点「**选择视频…**」导入视频，软件自动读取出**时长 / 分辨率 / 原始帧率**，并把起止时间填为整片；
2. 设置参数（见下表），下方会实时显示**输出预估**（时长 / 帧数 / 尺寸）；
3. 点「**开始转换**」，进度条实时显示两个阶段：生成调色板 → 编码 GIF；随时可点「取消」；
4. 转换完成后在「预览」区**自动循环播放**生成的动图；
5. 满意后点「**保存到…**」选择位置保存；也可点「打开所在文件夹」直达文件。

| 参数 | 说明 | 默认 |
|---|---|---|
| 起始 / 结束时间 | 要截取的片段；支持 `秒`（`5.5`）、`mm:ss`（`1:23.5`）、`hh:mm:ss.ms` | 整片 |
| 输出帧率 | 1–30 fps，越大越流畅、文件越大 | 12 fps |
| 输出宽度 | 输出画面宽度（像素），高度默认按原比例自动 | 原宽 |
| 播放速度 | 0.25×–4×，2× 即两倍速播放 | 1× |
| 质量档位 | 高 / 中 / 低，映射调色板颜色数（256 / 128 / 64）与抖动方式 | 中 |
| 颜色数 | 2–256，可覆盖档位微调；越少文件越小、色带越明显 | 128 |
| 循环次数 | 0 = 无限循环 | 0（无限） |

**小贴士**：GIF 体积 ≈ 时长 × 帧率 × 尺寸 × 颜色数。想让文件更小：缩短片段、降帧率（8–12 够用）、把宽度压到 480 左右。

---

## 命令行工具（可选）

无头转换，适合批量或排障：

```bat
.venv\Scripts\python.exe src\cli.py probe   --input demo.mp4
.venv\Scripts\python.exe src\cli.py convert --input demo.mp4 --start 0 --end 3 --fps 12 --width 480 --out demo.gif
```

## 自检

```bat
.venv\Scripts\python.exe src\main.py --selftest
```

自动完成：合成测试视频 → 探测信息 → 转换 GIF → 校验产物（尺寸 / 帧数 / 时长 / 循环标志）。

## 运行测试

```bat
.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## 常见问题

| 现象 | 处理 |
|---|---|
| 双击 `启动.bat` 没反应 | 在终端运行 `.venv\Scripts\python.exe src\main.py` 查看报错；多为依赖或 ffmpeg 缺失，重跑上文部署步骤 |
| 提示「文件无法识别 / 已损坏」 | 确认该文件能在播放器中正常播放；损坏或未下载完成的文件无法转换 |
| 提示「未找到转换引擎 ffmpeg」 | 运行 `.venv\Scripts\python.exe tools\get_ffmpeg.py` |
| 转换失败 | 错误框内点「复制详情」查看 ffmpeg 原始报错；常见原因是时间段超范围或输出尺寸过大 |
| 生成的 GIF 颜色有噪点 | 提高质量档位（颜色数 256 + 高），或降低输出尺寸 |
| 输出文件太大 | 缩短片段 / 降低帧率 / 减小宽度 / 降低颜色数 |
| 想彻底卸载 | 直接删除本目录即可；软件不写注册表、不改系统 PATH，临时文件位于 `%TEMP%\video2gif_*`（退出即清理） |

## 技术说明

- **转换引擎**：内置 ffmpeg 7.1（约 87 MB，不纳入 Git），来源与许可见 `tools/ffmpeg/README.txt`；采用两遍调色板（palettegen + paletteuse）保证 GIF 画质。
- **目录结构**：
  - `src/videogif/core/`：转换核心（探测 / 参数 / 转换 / 错误映射，无 GUI 依赖）
  - `src/videogif/gui/`：tkinter 界面与 GIF 预览
  - `src/cli.py`、`src/main.py`：命令行与 GUI 入口
  - `tests/`：pytest 测试（自动合成测试视频，不依赖外部素材）
  - `docs/`：产品设计文档与技术方案文档
- **隐私**：全程本地处理，不联网、不上传任何数据。
