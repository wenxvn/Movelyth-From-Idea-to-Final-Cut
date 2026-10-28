# 决定记录（第二版提纲）

每项记录：问题、选择、被否方案、可追溯证据。改动与提纲冲突时，先改这里再改代码。

## D1 · 时区无效时不再静默回退（S1-01，2026-10-28）

- 问题：`now()` 在 `MOVELYTH_TZ` 无效或缺少 tzdata 时静默返回 `+08:00`，用户以为设了 UTC 其实没有。
- 选择：`resolve_timezone()` 抛 `TimezoneError`；未设置环境变量仍表示文档默认 `Asia/Shanghai`；
  `tzdata` 列入依赖（Windows 无系统时区库）；`doctor` 把无效时区记为 reason 并让 `ready_for_generation=false`。
- 否：继续回退 + 写 warning。回退后的时间戳会污染台账排序，且 warning 在 CLI 输出里会被忽略。
- 证据：`tests/test_util.py`、`tests/test_doctor.py`。

## D2 · ffprobe 定位与 CI 依赖顺序（S1-01）

- 问题：CI 先跑 pytest 再 `npm ci`，而 ffprobe 回退依赖 `studio/node_modules/@remotion/compositor-*`；
  干净检出上媒体验证会失败。旧错误只提“请先 npm ci”，不列已检查路径。
- 选择：`ffprobe_candidates()` 按 环境变量 → PATH → compositor 解析；错误信息列出全部已检查位置；
  CI 先安装渲染器并显式验证 `ffmpeg/ffprobe` 可解析；新增 Linux 逻辑作业（不装渲染器）。
- 否：把 ffprobe 也打进 Python 依赖（imageio-ffmpeg 不含 ffprobe）；用 ffmpeg 反推时长（精度与字段都不等价）。
- 证据：`tests/test_doctor.py`、`.github/workflows/ci.yml`。

## D3 · 轴读数降级必须有确定性证据（S1-02）

- 问题：旧 `downgrade_axis_readings()` 只要 finding 里出现“刻度/axis”就降级，导致真实缺陷（单位错、轴交换）
  也可能被降级；但完全不降级又会因为视觉模型读不准 25px 刻度而反复重渲染。
- 选择：`charts.py` 在 Python 侧镜像渲染器的 1-2-5 刻度算法（`tests/test_charts.py` 用 node 执行
  `ChartLayer.tsx` 的真实源码做 parity 校验），把“该场景实际显示的刻度标签”作为证据：
  | finding 内容 | 处置 |
  | --- | --- |
  | 纯标签读数，数字与生成刻度一致 | `unknown`（非必需）+ 证据 `generated-tick-labels` → warning |
  | 纯标签读数，数字不在生成刻度里 | 同上 + 证据说明“刻度由程序生成，claimed 不在其中” |
  | 涉及数据/数值/单位/趋势/轴互换/缺轴变量 | 阻断（`claim-about-data-or-units`） |
  | 同时报告空白/遮挡/缺字/裁切等结构问题 | 阻断 |
  | 没有数字且无可核对刻度 | `unknown`（非必需），记录“无确定性证据” |
- 否：保留关键词降级（不可追溯）；全部按 strict（视觉模型噪声导致无限重渲染）。
- 迁移：`downgrade_axis_readings = true/false` 仍可读作 `deterministic/strict` 的别名；
  新键 `axis_reading_policy` 优先，非法取值直接报错。

## D4 · 交付决定集中到 policy（S1-02）

- 问题：交付与否由 pipeline 内多处 `if` 分散决定，`passed=true` 可以覆盖 factual finding。
- 选择：`policy.py` 定义 `CheckResult`（status/severity/required/repairable/evidence）与 `ReleaseDecision`；
  `decide()` 规则：任一 critical/major `fail` → `blocked`；任一必需项 `unknown` → `needs_review`；
  其余（含 minor fail、非必需 unknown、not_applicable）→ `ready`。原始审查与规范化结果都落盘。
- 严重性/必需项表：
  | 检查 | 严重性 | 必需 |
  | --- | --- | --- |
  | full_decode / not_black | critical | 是 |
  | dimensions / duration / requested_duration_range / audible / loudness | major | 是 |
  | h264 / aac / fps / no_clipping / true_peak | minor | 是 |
  | moving_picture | minor | 否（解释性静止段可接受） |
  | 语音内容核对（ASR 启用时） | major | 是；未启用 → not_applicable |
  | 静音检测 | major | 启用时是 |
  | 侧链/ducking | minor | 否 |
  | 模型 factual finding | critical | 是 |
  | 模型 visual_defect / audio_defect / visual_mismatch（未降级） | major | 是 |
  | 模型 warning finding | minor | 否 |
  | 布局软警告 / 比例估计字幕时间 | minor | 否 |
- 否：单一总分/加权分数。总分会让一个 critical 缺陷被十个 pass 抵消。
- 证据：`tests/test_release_policy.py`、`tests/test_release_gate.py`（含 M01 注入）。

## D5 · 交付包由组成清单与决定共同授权（S1-03）

- 问题：旧 `manifest_valid()` 只校验“列出的文件 hash 未变”。只要文件没动，旧 revision 的审查、
  缺人声的混音、或换了声音却没进最终视频的包都可能继续算 ready。
- 选择：
  1. 交付时生成 `组成清单.json`：episode/revision/creation_mode/policy/schema/renderer/settings_hash、
     研究/脚本/质检/决定 hash、每 cut 的时长/帧数/时间轴 hash/字幕 hash/人声/mix/render 指纹、
     以及包内每个文件名的 hash（`delivered`）。
  2. `manifest.json` 记录 `composition_hash = fingerprint(组成清单)`。
  3. `交付决定.json` 随包交付；校验时要求 `decision == ready`、策略版本一致、决定输入里的
     episode/revision 与本包一致、决定文件 hash 与组成清单登记的一致。
  4. 给 `job` 时额外比对工作区 `audio/<cut>/narration.wav|mix.wav`：交付后重新生成过音频即判失效
     （文件已不在则记为 `unverified`，不误判失效）。
  5. 暂存目录先删除再重建，完成后原子 `rename`；不留下“看起来完整”的半包。
- 否：把组成信息只写进 `制作溯源.json`（那是给人看的说明，不是可校验契约）；把绝对路径写进包
  （换机器即失效，且泄露开发路径）。
- 证据：`tests/test_composition.py`（6 项，含 M12 注入）、`tests/test_workflow.py`。
