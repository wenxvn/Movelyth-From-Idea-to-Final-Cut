# 验证记录

## 2026-10-25 · V1（Scene DSL、声画节拍、预览、安全、音频质检）

详细任务记录见 [V1 执行记录](v1-execution.md)，跨题材验收见 [V1 验收](v1-evaluation.md)，
V1 前的基线见 [V1 基线](v1-baseline.md)。

### 自动化检查

```text
.\.venv\Scripts\python.exe -m pytest -q                      → 72 passed, 1 deselected（默认跳过真实渲染）
.\.venv\Scripts\python.exe -m pytest -q -m "not slow"        → 72 passed
.\.venv\Scripts\python.exe -m pytest tests/test_render_smoke.py -q  → 1 passed（真实 Remotion 渲染，横竖 8 张静帧）
.\.venv\Scripts\python.exe -m ruff check src tests           → All checks passed!
npm.cmd --prefix studio run typecheck                        → 通过
```

覆盖范围新增：Scene DSL 正反向契约（非法参数、`NaN`、路径/URL 注入、超长文本、超量数据）、
节拍与真实词语边界解析、区域不越界与不压字幕、旁白与图表趋势/矩阵断言一致性、
来源抓取 SSRF 与失败缓存过期、音频长静音与配乐过响、可选 ASR 边界、brief 意图隔离、
旧数据库迁移、阶段指标、mock provider 契约、真实渲染静帧互不相同、预览不入交付、
局部修订不改无关镜头。

### 真实渲染 / 真实 TTS 证据（mock 剧本，非真实模型创作）

使用 `tests/fixtures/demo/movelyth-demo.toml`（`provider = "mock"`，时长缩短为 40s/15s）：

| 任务 | 命令 | 结果 |
|---|---|---|
| VID-000002 | `create "梯度下降为什么能让模型逐步减少错误？"` | `ready`，横版 41.0 s / 竖版 17.0 s，11 项技术检查全通过 |
| VID-000003 | 同题 `--preview --new` | `previewed`，`storyboard.json` + 12.0 s / 960×540 预览片段 |
| VID-000004 | `revise VID-000002 --notes …` | `ready`，`sound` 阶段 0.2 s（语音全命中缓存，首次为 23.4 s） |

阶段耗时（`workspace/v1-demo/metrics.csv`）：research 0.02 s、script 0.06 s、sound 23.43 s、
assets 0.22 s、render 90.49 s、check 84.03 s（首次，40s+15s 双画幅，1080p）。
第二次同题生产（VID-000002）sound 0.15 s、render 107.63 s、check 73.38 s。
带 brief 的生产（VID-000005/000006）流程相同，`制作溯源.json` 记录 `brief_used: true` 与
`brief_hash`。

按 cut 复用已实测：用 VID-000005 的既有 `render-result.json` 与相同 `render-spec.json`
重跑渲染器，日志只输出 `cut_cached`（long / short），未重新编码。`revise` 的 `sound`
阶段 0.2 s（语音缓存全命中）。

音频机器指标：长版混音/原声能量比峰值 1.196、均值 0.889；短版 1.157 / 0.875（阈值 1.6）。
VID-000008 开启本地 ASR（`faster-whisper` 1.2.1，`small` int8）：长版字符覆盖率 **0.949**、
短版 **0.942**，`missing` 为空，`asr_checked = true`。转写中出现近音字（"梯度"→"T度"、
"步长"→"不常"、"摆动"→"百动"），因此覆盖率只作为下限信号，不代表发音正确。

### 验证边界（必须与上面的结论一起读）

- **真实 Codex 成片**：VID-000002（矩阵）、VID-000003（网络消息）、VID-000004（梯度下降）
  三个题材的双画幅成片均通过全部技术检查与独立视觉审片。
- mock provider 的剧本来自 `tests/fixtures/demo/*.json`，**不能**作为模型创作能力证据；
  质检报告里 `creation_mode` 会写 `mock-provider`。
- 没有人工完整观看、没有实听、没有人工 1–5 分评分；`质检报告.json` 的
  `human_review` 保持 `false`。
- ASR 只在显式开启时执行（默认关闭，因为首次加载模型约 2 分钟）；未开启时报告写 `disabled`。
- 未上传到任何平台，没有播放量或受欢迎结论。
- 真实 Codex 制作：VID-000002（矩阵）、VID-000003（网络消息）、VID-000004（梯度下降）
  三个题材的双画幅成片全部通过技术检查与独立视觉审片。
- 局部修订仍重渲染整条 cut（见 `docs/architecture.md`）；纯渲染器修复可用 `--reuse-script`
  复用已审脚本，不重新消耗编导额度。

---

## 2026-10-25 · 首版（0.1.0，V1 之前）

- 22 项 pytest 通过，Ruff、TypeScript 与 skill 格式检查通过。
- 环境：Windows，Python 3.11.9，Node 24.12.0，Remotion 4.0.538，Chrome，imageio-ffmpeg 7.1
  以及 Remotion 提供的 ffprobe。
- Edge TTS 连通实测成功，测试音频 3.672 秒，获取 10 条词语边界。
- 七类画面组件已完成独立渲染连通测试；测试产物没有进入待上传目录。

### 真实标题验收（已通过）

标题：《矩阵，如何改变我们看到的世界》，任务 VID-000001。

- 从标题调用真实 Codex 研究、编导及独立审稿，未导入人工写好的脚本。
- 长版 10 镜、928 字；短版 4 镜、266 字，已通过脚本审稿。
- 所有镜头真实配音完成，时间轴按 PCM 样本和词语边界生成。
- 首轮渲染观察到内存压力，已保存失败/恢复记录，收紧自身线程、缓存和并发；缓存阶段成功复用。
- 完整横竖版已通过最终文件检查与独立抽帧审片，交付状态 ready。
- 首轮最终审片拒绝：矩阵单行四数排版与"两列"的讲解不符，审片上下文也缺研究来源正文。
  已改为明确 2×2 排版，抓取来源证据并保留可用性/内容 hash；修正后的横竖版预览通过独立审片。

| 版本 | 实际文件时长 | 画幅 | 帧率 | 采样峰值 | 技术与抽帧审片 |
|---|---:|---|---:|---:|---|
| B站横版 | 209.9 秒 | 1920×1080 | 30fps | -1.9 dBFS | 通过 |
| 抖音竖版 | 62.8 秒 | 1080×1920 | 30fps | -2.0 dBFS | 通过 |

两版 H.264/AAC、完整解码、画幅、帧率、音量、时间轴一致性、允许时长范围及时间采样运动检查均通过。
审片用图直接从最终编码 MP4 提取。成片与交付副本 SHA-256 一致，manifest 校验通过。

本机交付路径：`delivery/待上传/VID-000001_矩阵，如何改变我们看到的世界/r001/`。
再次运行 `生成视频.ps1` 并输入同题，返回同一编号、同一路径和 `reused=true`。

默认硬时长范围为横版 120–300 秒、竖版 45–90 秒；180/60 秒为参考目标。来源证据 4 项，
其中 3 项抓取成功，Georgia Tech 因证书验证失败不可用；核心主张由其余一手来源节选支持，
该限制如实保存在审片 warnings 中。

### 验证边界

已执行的技术检查不代表人工听过音轨或观看完整视频。首版未执行 ASR。外部数据、工具宣传及
示例效果不作为本项目实测结果。没有发布到平台，所以没有播放量或受欢迎结论。
