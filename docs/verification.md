# 验证记录

## 2026-10-27 · V2 工艺层（同一脚本的受控对照）

```text
pytest -q                            → 195 passed（含真实 Remotion 静帧 slow 测试）
ruff check src tests                 → All checks passed
npm --prefix studio run typecheck    → 通过（tsc --noEmit 无输出）
movelyth check --film workspace/ab/film-004-v2.json   → passed=true，2 条节奏警告
```

### 对照设置

本机**没有 `codex` 可执行文件**，所以没有重跑模型。改用已审脚本做受控对照：

- 输入：`workspace/VID-000004/film.json` + `research.json`（V1 交付时通过审片的脚本）。
- 机械修复：`workspace/ab/make_film.py` 只重排 `l2` 两个重叠节点（65 单位）、
  补齐 `transition`/`camera`/`cues` 默认方向；文字、图层类型、时长逐字不变。
- 运行：`MOVELYTH_CONFIG=workspace/ab/movelyth-ab.toml`，
  `movelyth create "…" --new --import-film workspace/ab/film-004-v2.json --import-research …`。
- 审片角色：`provider = "mock"`（预设通过），因此 `质检报告.json` 的
  `provider` 是 `mock`；**这不是真实 Codex 审片，也没有 AI 看过新画面**。
  画面结论来自本机逐帧抽检（见 `docs/v2-evaluation/`）。

### 产物

| 任务 | 内容 | 结果 |
|---|---|---|
| VID-000006/007/008/009/010/011/012/013/014/015 | 同一脚本的迭代重渲染（每次修一个真实缺陷后重跑） | 最终 `VID-000015` |
| VID-000015 | 横版 231.5 s / 竖版 65.2 s | 13 项技术检查全通过 |

关键指标（`workspace/VID-000015/quality.json`）：

- 响度 -14.3 LUFS，真峰值 -1.1 dBTP。
- 混音/原声最大比 1.196（横）/ 1.154（竖），阈值 1.6。
- `frozen_scenes: []`（无 ≥5 s 冻结镜头）；每镜静止采样占比 0–29%。
- `pacing`：9 镜 24.5–28.2 s，`uniform_shots: 9`，转场 5 种，音效 9 个。
- `sound_design`：2.33 音效/分钟，配乐 RMS -30.5 dBFS，动态范围 20.3 dB，`prosody: sentence`。

### 本轮由抽帧/测量暴露并修复的缺陷

| 缺陷 | 证据 | 修复 |
|---|---|---|
| wipe 转场整镜空白 | 成片 26 s 处只有字幕 | 转场包装层补 `position:absolute`（原先 `clipPath` 把 0 高元素裁空） |
| 转场时旧画面提前消失 | `tr-26.jpg` 是新画面浮在背景上 | 双层合成：旧镜保留到交接完成 |
| 两套标题在接缝处重叠 | 帧 782 两个标题叠在一起 | wipe 改羽化遮罩、旧镜同步淡出 |
| `draw` 开始前整图空白 | 26.15 s 只剩一个节点框 | 结构化图形预揭示 45%；柱状图改为从基线生长 |
| 柱值标签被遮罩裁掉 | 帧 4560 顶部 25 不可见 | 柱内标签 + 类别半槽留白 + 揭示遮罩覆盖全画布 |
| 图表刻度非整 | `0.76 / 2.0 / 3.24` | 1-2-5 取整 |
| 常量序列画成假数据线 | "当前点 L=5" 变成一条水平线压住图例 | 识别为参考线/标记点 |
| 单位向量只有几十像素 | 帧 5300 箭头几乎看不见 | 按内容与区域宽高比缩放 viewBox |
| 竖版 bottom 区 34 px | 导入脚本被判"公式放不下" | 重排竖版栅格（bottom 84 px） |
| 首帧标题与图表争位 | 早前版本标题压住数据 | 标题/标签改为同一列流式排版 |

### 未验证 / 限制

- **没有真实模型参与本轮**：新 prompt 的采纳率（`transition`/`camera`/`emphasis`/`cues`）
  完全未验证；也可能因为字段变多而更容易触发修复循环。
- **没有人工观看与实听**：我只能抽帧与测信号。`human_review` 仍为
  `{watched_full_video: false, listened_audio: false}`。
- 节奏仍均匀（9 镜 24.5–28.2 s），属脚本层面问题，渲染器无法修正。
- 转场时长固定 0.4–0.5 s，未按内容自适应。

---

## 2026-10-27 · 通用 provider 与真实弱模型验收

```text
pytest -q                            → 181 passed（含 1 项真实渲染 slow 测试）
pytest -q -m "not slow"              → 180 passed, 1 deselected
ruff check src tests                 → All checks passed
npm --prefix studio run typecheck    → 通过
```

### 真实 DeepSeek 端到端（不是模拟）

| 阶段 | 结果 |
|---|---|
| `movelyth probe` | `reachable=true`、`json_output=true`、`vision=true`（真实图片问答返回"深黑色背景"） |
| research | 通过 |
| script | 通过（多轮契约修复后收敛，最佳草稿 1 项待修） |
| sound | 通过（真实 Edge TTS，含一条损坏缓存的自动重合成） |
| render | 通过（横版 + 竖版真实 Remotion 渲染） |
| check | 横版 152.9s / -14.4 LUFS / -1.2 dBTP，竖版 62.8s / -14.4 LUFS / -1.4 dBTP，13 项检查全通过 |
| visual-review | **拒收**（真实内容缺陷，见下） |

`json_schema` 在 DeepSeek 官方端点返回 400（`This response_format type is unavailable now`），
自动降级到 `json_object` 成功；该模式按进程记忆，后续调用不再重试。

### 真实抽帧暴露的缺陷（已修复并复验）

| 缺陷 | 证据 | 修复 |
|---|---|---|
| 公式折行 | `L＝(4＋16)÷4＝5` 渲染成两行，第二行只有 `＝5` | math 层单行收缩 + 高度检查；重新渲染确认单行 |
| 公式被裁切 | `side` 区（高 55px）只显示 `-1 + (-1)×(-1)` 上半截 | 计入渲染器 14px 内边距；重新渲染确认完整 |
| diagram 节点重叠 | `(-1)×(-1)=-1` 画成 `(-1)×(` | 节点宽度校验与 TSX 公式一致 |
| 柱状图柱子重叠 | 同 x 两系列完全叠在一起，标签压成一块 | 并排分组渲染 |
| 零值柱不可见 | `0.0` 柱高为零，"0 对 -2"只剩一根柱 | 画可见基准线；重新渲染确认 `0.0` 可读 |

### 未通过的部分

VID-000005 未产出交付包。审片拒收理由（已逐条核对抽帧确认为真）：
l5 与 l6 是同一论证重复、l1 数轴未标 -3/0/+3、部分推导链在画面上不闭合。
这些是内容与编排缺陷，需要更强模型重新生成脚本；程序侧的检查与修复闭环本身已验证通过。

### 边界

- `deepseek-flash` 在 8 镜结构里反复犯同类契约错误，12 轮修复仍卡在 1 项；`deepseek-v4-pro` 同样
  未能收敛到 0 项。弱模型可用，但需要更多轮次，且内容质量明显低于 Codex。
- 视觉模型（DeepSeek）对中文细节与坐标刻度的读数不可靠：同一张图两次审片给出不同刻度数字，
  因此纯刻度类 finding 已降级为 warning。

## 2026-10-26 · 借鉴 references 的质检与排版改进

改动：两遍响度归一（-14 LUFS / -1.5 dBTP）、逐镜运动分析、发音与字幕分离、
`textfit.py` 中文断行与字幕分页、`key_terms` 术语核对。

```text
pytest -q                            → 125 passed（含 1 项真实渲染 slow 测试）
pytest -q -m "not slow"              → 124 passed, 1 deselected
pytest tests/test_render_smoke.py -q → 1 passed
ruff check src tests                 → All checks passed
npm --prefix studio run typecheck    → 通过
```

新增 14 项测试：断行/禁则/孤行/拉丁词不拆、字幕页不产生两字残页、发音替换后字幕仍显示原文
（含替换长度变化）、`key_terms` 接受别名/标记丢失/未开 ASR 时不检查、两遍响度实测达标、
静音混音退回动态模式、静帧检测与整帧漂移检测（真实 ffmpeg 编码文件）。

### 真实数据验证

- **真实成片重放**（`workspace/VID-000004` 的 silent 渲染 + 混音，重跑 `check_action` 的全部新代码）：
  横竖版 13 项技术检查全通过，响度 **-14.4 LUFS / -1.1 与 -1.3 dBTP**，运动分析 `ok`、
  无静帧误报，交付审计文本正确生成。旧实现为 -16.8 / -16.9 LUFS。
- **326 个真实 TTS 边界用例**（`workspace/voice-cache` 下全部 `timing.json`）：字幕全部走
  `tts-word-boundaries`，页时间单调、不越界，零失败。
- **真实 TTS 端到端**（联网 edge-tts，`speech_replace = {"熵": "商", "行列式": "hang lie shi"}`）：
  配音实际读作「商」「hang lie shi」，字幕仍显示「熵」「行列式」，两页时间 0.10–1.94 / 2.24–4.54 s，
  模式为真实词语边界而非估算。旧实现会把替换文本直接写进字幕。
- **真实 film.json 离线校验**（`movelyth check`）：通过，0 errors、0 warnings。
- 旧交付包未改动，`manifest_valid` 与 `delivery/` 下 4 条任务不受影响。

未做的验证：新流程尚未跑一条完整的真实标题驱动成片（需要 Codex 调用与联网 TTS）；
`key_terms` 在真实 ASR 开启时未验证（当前 `asr_enabled = false`，报告如实写 `not-run`）。

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
