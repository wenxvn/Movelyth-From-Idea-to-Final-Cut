# V1 基线（改动前）

> **历史记录（V1 基线，2026-10-25）**：本文件记录当时的条件、结果与未完成项。当前状态与能力边界见 [optimization/execution.md](optimization/execution.md) 与 [optimization/capabilities.md](optimization/capabilities.md)，最新验证数字见 [verification.md](verification.md)。

记录时间：2026-10-25。基线提交：`963b1aa2d05f7ab5025f67bf7af4fe3fd7defebe`
（`main`，工作区干净，与 `origin/main` 一致）。

## 环境

| 项 | 值 |
|---|---|
| Python / Node | 3.11.9 / v24.12.0 |
| Remotion / React / TypeScript | 4.0.538 / 19.2.3 / 5.9.3 |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| FFmpeg / ffprobe | imageio-ffmpeg 7.1 / Remotion compositor |
| pydantic / numpy / Pillow | 2.13.4 / 2.4.4 / 12.2.0 |
| edge-tts | 7.3.1（联网实测：41 字中文 → 23 条词语边界） |

## 改动前的自动化检查

```text
pytest -q            → 22 passed
ruff check src tests → All checks passed
npm --prefix studio run typecheck → 通过
```

## 已有成片（VID-000001，矩阵主题）

| 版本 | 时长 | 画幅 | 帧率 | 码率 | 大小 |
|---|---:|---|---:|---:|---:|
| B站横版 | 209.9 s | 1920×1080 | 30 | 870 kbps | 22.8 MB |
| 抖音竖版 | 62.8 s | 1080×1920 | 30 | 930 kbps | 7.3 MB |

11 项技术检查通过；`audio_listened=false`、`asr_checked=false`、
`full_motion_aesthetic_review=false`。本次只做**抽帧**，没有重新完整观看或实听。

改动前的视觉基线（从编码成片抽帧，640/360 px 宽）在 `docs/baseline/v0/`：
每镜一张固定构图、左侧标题+标签、右侧一个程序动画、底部字幕；七类动画参数基本固定
（网络恒为 14 节点、波形恒为 3 条谐波）。这是 V1 要解决的**产品质量瓶颈**。

## 当时的环境阻塞（后续已解决）

`shutil.which("codex")` 返回 `None`：`%APPDATA%\npm` 的 `@openai/codex@0.163.0` 缺
`@openai/codex-win32-x64` 可选依赖；`AppData\Local\[OI]\Codex\bin\codex.exe`（0.130.0-alpha.5）
的默认模型不被 ChatGPT 账号支持，且需代理。

后续在一个**临时目录**安装完整的 `@openai/codex@0.163.0`，通过 `MOVELYTH_CODEX` 指向它并设置
`HTTPS_PROXY`，真实角色调用成功。该路径只在环境变量里，未写进仓库配置，也未索取或提交任何密钥。
Codex 账号有额度上限，期间两次触发 `You've hit your usage limit`。

## 其它约束

- 没有付费模型/音乐/生视频服务；没有上传到 B站/抖音；没有播放数据。
- 本机内存有限（历史记录出现过 1.45 GB 渲染进程与内存不足），继续单渲染并发。
