# 技术方案文档 · 视频转GIF动图

> 版本：v0.1 ｜ 日期：2026-10-15 ｜ 状态：已确认（关键选型经用户确认：桌面 tkinter；其余为工程实现选择）  
> 原则：只锁定技术栈与架构大方向，细节在实现中校准——过早写满细节，会把未验证的猜测包装成约束。

## 1. 技术栈

| 层面     | 选型                                                   | 理由                                                                                   |
| ------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 语言     | Python 3.13.2                                        | 使用本机 conda Python 派生的项目专用 venv（本机隔离 Python 不含 tkinter，无法跑 GUI；已实测 venv 内 tkinter 可用） |
| GUI    | tkinter / ttk（标准库）                                   | 零额外依赖、原生 Windows 控件、启动快、原生「选择/保存」对话框                                                 |
| 转换引擎   | ffmpeg 静态二进制（内置 `tools/ffmpeg/`，取自 imageio-ffmpeg 包） | GIF 高质量两遍调色板转换的事实标准；随项目携带、免安装、不污染系统                                                  |
| GIF 预览 | Pillow (PIL)                                         | 解析 GIF 帧序列驱动预览动画 + 降采样显示                                                             |
| 测试     | pytest                                               | 参数单测 + 用 lavfi 合成测试视频做端到端转换验证                                                        |
| 版本管理   | Git（main 分支）                                         | 护栏：每个改动一个 commit，随时可回退                                                               |

## 2. 架构方向

分三层，界面与转换核心解耦（核心可无 GUI 独立测试）：

1. **转换核心 `src/core/`（无 GUI 依赖）**
   - `ffmpeg_locator.py`：定位 ffmpeg（项目 `tools/ffmpeg/` → imageio-ffmpeg 包内 → PATH）；统一子进程调用（列表传参不经 shell、隐藏控制台窗口）；
   - `probe.py`：解析 ffmpeg 输出获取时长 / 分辨率 / 原始帧率（正则容错）；
   - `params.py`：转换参数模型 + 校验（时间输入支持 `秒` / `mm:ss.ms` / `hh:mm:ss.ms`）；生成「预估时长 / 帧数」；
   - `converter.py`：两遍调色板转换，逐行解析 `-progress pipe:1` 输出计算进度（调色板 0–35%、编码 35–100%）；支持取消（终止子进程）、错误捕获、临时目录清理；
   - `errors.py`：ffmpeg 原始报错 → 中文用户文案映射（损坏/权限/参数/磁盘等），保留原始详情供「详情」查看。
2. **界面层 `src/gui/`（tkinter）**
   - `app.py` 主窗口：参数面板、进度条、状态栏、按钮状态机（空闲 / 转换中 / 完成）；后台线程 + 队列刷新 UI，保证窗口不卡死；
   - `preview.py`：GIF 预览控件，Pillow 逐帧播放；按显示尺寸降采样缓存，帧数过多时自动关闭缓存防止内存膨胀。
3. **入口层**
   - `src/main.py`：GUI 入口（`pythonw` 无控制台启动；兼容 pythonw 下 stdout/stderr 为 None）；支持 `--open <文件>` 预加载（也便于自动化测试）；
   - `src/cli.py`：无头转换命令行（供自测 / 批量 / 排障，复用同一核心）。

关键转换链路（两遍法）：

```
第1遍 调色板: ffmpeg -ss S -t D -i IN -vf "setpts=(PTS-STARTPTS)/speed,fps=F,scale=W:H,palettegen=max_colors=C:stats_mode=diff" palette.png
第2遍 编码:   ffmpeg -ss S -t D -i IN -i palette.png -filter_complex "[0:v]同上[x];[x][1:v]paletteuse=dither=…:diff_mode=rectangle" -loop N out.gif
```

## 3. 备选方案与取舍记录

| 候选方案                      | 优点                 | 缺点                           | 结论                            |
| ------------------------- | ------------------ | ---------------------------- | ----------------------------- |
| tkinter 桌面窗口              | 原生、无依赖、启动快、原生文件对话框 | 界面样式朴素                       | 采用                            |
| 本地网页版（Flask + 浏览器）        | 视觉更丰富、自动化测试容易      | 多一层服务进程；保存走浏览器下载，不符合「本地软件」习惯 | 备选（用户已选桌面版）                   |
| OpenCV 抽帧 + Pillow 合成 GIF | 无 ffmpeg 依赖        | 慢一个数量级、颜色量化质量差、内存占用高         | 否决                            |
| 依赖系统已装 ffmpeg             | 项目体积小              | 本机未安装、用户环境不确定、易出环境问题         | 否决（改为内置二进制）                   |
| 单遍 GIF 默认调色板              | 转换快                | 颜色抖动明显、画质差                   | 否决（用两遍 palettegen/paletteuse） |

## 4. 已知风险

- **ffmpeg 二进制体积**（约 30–80 MB）随项目携带：不入 Git（`.gitignore`），提供获取脚本，README 说明来源与许可证（GPL）。
- **进度解析兼容性**：不同 ffmpeg 版本的 `-progress` 字段略有差异 → 以 `out_time=` 计算比例，用多种容器视频实测。
- **大 GIF 预览内存**：预览按显示尺寸降采样；帧数超阈值自动关闭帧缓存（每循环重解码），避免内存膨胀。
- **Windows 编码与路径**：全链路 `pathlib` + 子进程列表参数，不经 shell；中文/空格路径列为测试用例。
- **pythonw 下标准流为空**：入口层做空流兜底，防止 `print` 抛异常导致崩溃。
- **高 DPI 缩放**：开启进程 DPI 感知并按屏幕缩放设置 tk 比例，避免高分屏下界面模糊/错位。

## 5. 运行与测试方式

- 运行命令：双击 `启动.bat`；或 `.venv\Scripts\python.exe src\main.py`
- 无头转换：`.venv\Scripts\python.exe src\cli.py convert --input in.mp4 --start 0 --end 3 --out out.gif`
- 测试命令：`.venv\Scripts\python.exe -m pytest tests/ -v`
- 验证工具（AI 自测所需）：pytest 端到端 + 本机 GUI 截图（ctypes 屏幕截图）+ Pillow 校验 GIF 产物属性

> 填写后请同步更新 `AGENTS.md` 的"项目信息"一节。（已同步）
