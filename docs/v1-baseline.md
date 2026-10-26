# V1 基线记录（P0-01）

记录时间：2026-10-25（本机 Windows）。
基线提交：`963b1aa2d05f7ab5025f67bf7af4fe3fd7defebe`（`main`，工作区干净，与 `origin/main` 一致）。
V1 开始前已确认远端无更新（`git status` → `nothing to commit, working tree clean`）。

## 1. 环境

| 项 | 值 |
|---|---|
| Python | 3.11.9（项目 `.venv`） |
| Node | v24.12.0 |
| npm | 随 Node 安装 |
| Remotion | 4.0.538（bundler / renderer / cli 一致） |
| React | 19.2.3 |
| TypeScript | 5.9.3 |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| FFmpeg | imageio-ffmpeg 7.1 |
| ffprobe | `studio/node_modules/@remotion/compositor-win32-x64-msvc/ffprobe.exe` |
| pydantic / numpy / Pillow | 2.13.4 / 2.4.4 / 12.2.0 |
| edge-tts | 7.3.1（联网实测可用：41 字中文返回 23 条词语边界） |
| Codex CLI | **本机 PATH 中没有可用的 `codex`**（见 §4） |

## 2. 基线自动化检查（V1 改动前）

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # 22 passed in 8.46s
.\.venv\Scripts\python.exe -m ruff check src tests  # All checks passed!
npm.cmd --prefix studio run typecheck            # tsc --noEmit 通过
```

## 3. 已有成片（VID-000001，矩阵主题）

交付目录在**本机**存在且 manifest 校验通过：

```text
delivery/待上传/VID-000001_矩阵，如何改变我们看到的世界/r001/
```

| 版本 | 时长 | 画幅 | 帧率 | 码率 | 大小 |
|---|---:|---|---:|---:|---:|
| B站横版 | 209.9 s | 1920×1080 | 30 | 870 kbps | 22.8 MB |
| 抖音竖版 | 62.8 s | 1080×1920 | 30 | 930 kbps | 7.3 MB |

`质检报告.json` 记录的 11 项技术检查全部通过；`audio_listened=false`、`asr_checked=false`、
`full_motion_aesthetic_review=false`。本次 V1 只对该文件做了**抽帧**（见 `docs/baseline/v0/`），
**没有**重新完整观看或实听，因此不据此声明观感结论。

V1 前视觉基线截图（从编码成片抽帧，640px / 360px 宽）：

```text
docs/baseline/v0/long-12.jpg   docs/baseline/v0/long-80.jpg   docs/baseline/v0/long-150.jpg
docs/baseline/v0/short-8.jpg   docs/baseline/v0/short-30.jpg  docs/baseline/v0/short-50.jpg
```

这些截图反映 V1 之前的结构性特征：每镜一张固定构图、左侧标题+标签、右侧一个程序动画、
底部字幕；七类动画的参数基本固定（网络恒为 14 个节点、波形恒为 3 条谐波）。

## 4. 已知限制与阻塞（不隐藏）

- **Codex 最初不可用，后已修复**：`shutil.which("codex")` 返回 `None`；`%APPDATA%\npm` 下
  `codex.cmd` 的 `@openai/codex@0.163.0` 缺少 `@openai/codex-win32-x64` 可选依赖，直接运行报
  `Missing optional dependency`；`C:\Users\10556\AppData\Local\[OI]\Codex\bin\codex.exe`
  （0.130.0-alpha.5）的默认模型 `gpt-6.1-sol` 不被 ChatGPT 账号支持，且需代理。
  后续在一个**临时目录**安装 `@openai/codex@0.163.0`（含 win32 二进制），通过
  `MOVELYTH_CODEX` 指向它、并设置 `HTTPS_PROXY=http://127.0.0.1:7897`，真实角色调用成功。
  该路径只存在于环境变量中，没有写进仓库配置，也没有索取或提交任何密钥。
- 因此本轮的真实成片证据来自真实 Codex（研究/编导/审稿）+ 真实 Edge TTS + 真实 Remotion：
  VID-000002（矩阵）、VID-000003（网络消息）。mock provider 的产物单独标注为
  `mock-provider`，绝不写成"真实模型创作"。
- Codex 账号有额度上限，期间两次触发 `You've hit your usage limit`，第 3 个题材因此未完成。
- 没有付费模型/音乐/生视频服务；没有上传到 B站/抖音；没有播放数据。
- 本机内存有限（历史记录中曾出现 1.45 GB 渲染进程与内存不足），继续单渲染并发。

## 5. 阶段耗时与产物（V1 演示，见 `docs/v1-execution.md`）

演示任务使用 `tests/fixtures/demo/movelyth-demo.toml`（mock provider + 缩短时长 40s/15s）。
完整阶段耗时、缓存命中与产物大小记录在 `workspace/v1-demo/metrics.csv`（不提交 Git）。
