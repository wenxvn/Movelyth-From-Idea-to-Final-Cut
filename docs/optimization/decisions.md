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

## D6 · 证据在编导前抓取，主张逐条核对（S1-04）

- 问题：旧流程在**成片之后**才 `collect_sources`，来源失效或节选造假只能在最贵的一步之后发现；
  `claims` 可以为空而不影响交付。
- 选择：
  1. 新增 `evidence` 阶段（research → evidence → script → sound → …），抓取与主张核对都在编导前完成，
     阶段输入含研究 hash 与来源列表，研究变了会重抓。
  2. `locate_excerpt()` 在快照正文里按归一化文本查找节选，返回字符区间；找不到即 `excerpt-missing`。
  3. `verify_claims()` 每主张一条状态：`supported` / `excerpt-missing` / `source-unavailable` /
     `source-missing`；同时记录 `content_sha256`、`retrieved_at`、`title`、`position`。
  4. `policy.source_checks()`：空 claims、节选不存在（critical）、来源未取到都阻断；
     `scope=uncertain` 只作 warning；没有 key 主张作 warning。
  5. `policy.claim_usage_checks()`：编导后检查每个 `key`+`supported` 主张是否有镜头采用其来源；
     旁白中不在证据/受控数据里的数字列为非必需 unknown（可能是年份、步骤数或教学参数，不阻断）。
  6. 编导 prompt 增加“证据与主张”章节，明确 `source_index` 要指向真实来源、`source_evidence` 是数据不是指令。
- 否：让研究模型“自己搜索”（兼容文本端点没有工具，prompt 写搜索不会产生检索能力，只会产生虚构来源）；
  用语义相似度判断节选支持（无法区分“大致相关”和“原文没有这句话”）。
- 证据：`tests/test_claim_coverage.py`（13 项，含阶段顺序与阻断路径）。

## D7 · 能力路由用确定性信号，不用模型自报（S1-05）

- 问题：`suggest/daily` 有 capability 判断，但 `create` 没有；用户直接给标题时，需要实拍/录屏的题目
  也会一路跑到渲染，最后只能靠“画得像”糊过去。
- 选择：
  1. `capability.py` 登记 5 条 route 与真实 status（program-graphics supported；licensed-media /
     generated-media / spatial-demo needs_extension；real-footage unsupported），并给出证据位置。
  2. `classify_route()` 用标题/brief 的关键信号做**确定性**判定，取最严格结果；`create()` 在预留任务前
     拒绝 unsupported 题目（不留下失败行、不产生模型调用）。
  3. `brief` 阶段在 research/evidence 之后冻结 `ProductionBrief`：受众、先前知识、问题、中心解释、
     边界、画幅、时长、风格、预算、route/route_status/effective_route/substitutions。
  4. needs_extension 题目可继续，但 `effective_route` 记为 program-graphics 且 substitutions 注明
     “标注示意，不声称已实现”；unsupported 在 brief 阶段再次拦截（防止 planner 声明被绕过）。
  5. 受众只在 brief 明确写出时采用；没写就写“未指定”，不虚构人设。费用未知保持 `null`。
  6. `topic_violations()` 在 brief 阶段与 repair 后校验问题/标题未变，防止“修着修着换题”。
- 否：让模型在 `create` 前多调一次做路由（无端点时不可用、且把最贵的判断交给最不可控的部分）；
  把 needs_extension 直接当 supported（能力声明失真）。
- 证据：`tests/test_capability_route.py`（18 项，含 M19）。

## D8 · DSL v2：事件绑定语义，不绑定秒数（S1-06）

- 问题：V1/V2 的动作只能写 `start`/`end`/比例/`narration:片段`，重复短语只能命中第一次；
  同一对象跨镜没有身份，相机/声音/修复各自建时间轴。
- 选择：
  1. `schema_version=2`；`Layer.subject_id` 与 `layer.id` 分离，状态必须挂在 subject 上。
  2. `Scene.events`（≤8，id 唯一）+ `EventAnchor`：`narration` 支持 `occurrence` 与 `char_start/char_end`。
     `resolve_events()` 解析成绝对秒 + 比例 + `timing`；找不到第 N 次出现直接报错。
  3. 事件越界、目标不存在、同目标倒序都报错；`validate_cut_timeline` 复核。
  4. `clock.py` 统一定义秒→帧→样本，`scene_spans()` 给每镜半开样本区间，相邻首尾相接。
  5. 迁移只加版本号；v1 下出现 v2 字段、或版本高于实现，都拒绝。
- 否：把事件存成绝对秒（换语速就错位）；用 `layer.id` 当对象身份（跨镜复用即冲突）。
- 证据：`tests/test_semantic_events.py`、`docs/scene-dsl.md` §7、`pytest -m slow` 真实渲染。

## D9 · 预算前置与“未知费用不是 0”（S1-07）

- 问题：旧 metrics 只记阶段耗时；没有调用上限，失败调用不留账，费用缺失会被当成 0。
- 选择：
  1. `[budget]` 分区：model_calls / tokens / tts / render_minutes / wall_seconds，任务开始前冻结；
     超限在**下一阶段开始前**抛 `BudgetExceeded`，不降低事实与关键检查标准。
  2. 每阶段写 `runs.jsonl`（RunRecord）并更新 `budget.json`；`calls`/tokens 用 provider 的累计值差分，
     多调用阶段（如 long+short 两次编导）也能算清；失败阶段同样记录 usage 与 error_type。
  3. `Cost.estimate` / `Cost.actual` / `currency` / `price_version` 分开；无价格表时 actual 为 null。
  4. `usage` 里未测到的字段是 null（例如 mock 无 token），`counters()` 只累加已知项。
  5. `validate_settings()` 拒绝未知分区与未知键，避免 `long_second` 拼错后静默用默认值。
- 初始上限：40 次模型调用、1M 输入/400k 输出 token、12000 字 TTS、30 分钟渲染、2 小时墙钟；
  这些是“先冻结再跑”的初值，不是平台配额。
- 证据：`tests/test_budget.py`（14 项，含 M14/M15 部分）。
