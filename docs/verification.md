# 验证记录

## 2026-10-26 · V1

任务级说明见 [V1 执行记录](v1-execution.md)，跨题材结论见 [V1 验收](v1-evaluation.md)，
改动前基线见 [V1 基线](v1-baseline.md)，最终状态见 [V1 报告](v1-report.md)。

### 自动化检查

```text
pytest -q                            → 111 passed（含 1 项真实渲染 slow 测试）
pytest -q -m "not slow"              → 110 passed, 1 deselected（CI 用这一条）
pytest tests/test_render_smoke.py -q → 1 passed（真实 Remotion + Chrome，横竖 10 张静帧）
ruff check src tests                 → All checks passed
npm --prefix studio run typecheck    → 通过
```

覆盖：Scene DSL 正反向契约（非法参数、`NaN`、路径/URL 注入、超长文本、超量数据）、
节拍与真实词语边界解析（含"片段不在旁白中"必须提前失败）、区域不越界/不重叠/不压字幕、
每镜必须有真实画面图层、旁白与图表趋势/矩阵断言一致性、来源抓取 SSRF 与失败缓存过期、
音频长静音与配乐过响、可选 ASR 边界、brief 意图隔离、旧数据库迁移、阶段指标、
mock provider 契约、真实渲染静帧互不相同、预览不入交付、局部修订不改无关镜头、
缓存脚本在契约变更后重新生成、`--reuse-script` 不重新调用编导、素材库授权与失效、
选题候选与能力门槛。

### 真实模型 + 真实 TTS + 真实渲染（三个题材，标题驱动）

| 任务 | 主题 | 横版 / 竖版 | 技术检查 | 视觉审片 |
|---|---|---|---|---|
| VID-000002 | 矩阵为什么能让整个空间旋转？ | 242.6 s / 64.8 s | 11 项全通过 | `passed=true`，1 条非阻断 warning |
| VID-000003 | 一条网络消息如何从我的电脑到达服务器？ | 218.9 s / 67.2 s | 11 项全通过 | `passed=true`，无 issue |
| VID-000004 | 梯度下降为什么能让模型逐步减少错误？ | 242.6 s / 69.5 s | 11 项全通过 | `passed=true`，无 issue |

三者各 **17 个交付文件**（横竖 MP4、封面、字幕、`原声`/`混音` MP3、发布文案、交付审计、
脚本、研究、质检、溯源、manifest），`creation_mode=title-driven-codex-agents`，
`published=false`。manifest 校验通过。

音频机器指标：混音/原声能量比峰值 1.20–1.25（阈值 1.6）；长静音检查 `ok`；
三个真实成片 `asr_checked=false`（未开启 ASR）。

### 真实 ASR 实测（mock 剧本任务 VID-000008）

`faster-whisper` 1.2.1，`small` int8，本机 CPU：长版覆盖率 **0.949**、短版 **0.942**，
`missing` 为空，`technical.<cut>.asr_checked = true`。转写出现近音字
（"梯度"→"T度"、"步长"→"不常"、"摆动"→"百动"），因此覆盖率只作下限信号。
成本：模型首次加载约 139 s，40 s 旁白转写约 8 s，进程内缓存复用；默认关闭。

### 成本与缓存（mock 演示，40 s + 15 s 双画幅）

| 阶段 | 首次 | 命中缓存 |
|---|---:|---:|
| research | 0.02 s（mock）/ 92.4 s（真实 Codex） | 0 s |
| script | 0.06 s（mock）/ 610.7 s（真实 Codex） | 0 s |
| sound | 23.4 s | 0.15–0.2 s |
| assets | 0.2 s | 0.1 s |
| render | 90.5 s | 整体 `cut_cached`，未重新编码 |
| check | 84.0 s | — |

按 cut 复用实测：相同 `render-spec.json` 重跑只输出 `cut_cached`（long / short）。
`revise` 的 `sound` 阶段 0.2 s（语音缓存全命中）。
**内存/CPU 峰值未测量**，标为未知。

### 验证边界（必须与上面的结论一起读）

- **人工完整观看与实听未执行**：三个真实交付包的 `human_review` 均为
  `{watched_full_video: false, listened_audio: false}`，没有 1–5 分人工评分。
- mock provider 的剧本来自 `tests/fixtures/demo/*.json`，质检报告写 `mock-provider`，
  不作为模型创作能力证据。
- 每个真实题材只做一条，未验证同题多次的稳定性。
- 未上传到任何平台，没有播放量或受欢迎结论。
- 局部修订仍重渲染整条 cut；纯渲染器修复可用 `--reuse-script` 复用已审脚本。
- 字体容量按字符数估算，未做真实字体测量与专门裁切回归测试。

---

## 2026-10-25 · 首版（0.1.0，V1 之前）

- 22 项 pytest 通过，Ruff、TypeScript 与 skill 格式检查通过。
- Edge TTS 连通实测成功（3.672 秒，10 条词语边界）。
- 七类画面组件完成独立渲染连通测试，测试产物未进入待上传目录。
- 真实标题验收《矩阵，如何改变我们看到的世界》（VID-000001）：长版 10 镜 928 字、
  短版 4 镜 266 字；横版 209.9 s / 竖版 62.8 s，11 项技术检查与抽帧审片通过；
  首轮审片曾拒绝（矩阵排版与"两列"讲解不符），修正后重渲染复核通过。
- 验证边界：未执行 ASR、未人工实听、未完整观看；未发布，无播放数据。
