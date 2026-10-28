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

## D10 · 配方是契约，不是新图层（S2-01）

- 问题：设计意图（“这一镜要把注意力带到拐点”）只存在于编导的自然语言里，渲染端与检查都不认它，
  于是每个镜头各写一套视觉，风格漂移且无法验证。
- 选择：
  1. `recipes.py` 登记 6 个已实现配方，每个写明用途、必需绑定（图层/序列/注释/单位/步骤/来源/主张）、
     事件、画幅、限制与检查项；`Scene.recipe` 让编导显式选择。
  2. `applicable()` 由内容推导适用性；`choose()` 用声明值或首个适用配方；`validate_scene_recipe()`
     对未实现/不适用的声明在渲染前报错；无配方场景只给警告（合法但记录）。
  3. `check_scene()` 做确定性验证：注释必须落在真实数据坐标附近、对照序列同单位、hero 存在、
     diagram 连线有效、纸面有 source_note、结论绑定 claim_ids。
  4. 配方与要求同时进入 `RENDERER_CAPABILITIES.recipes` 与 director 提示词，编导只从已实现集合中选择。
- 否：把每个配方做成新的 LayerKind（渲染端会膨胀且不可组合）；只写提示词不写检查（无法阻止未实现配方）。
- 证据：`tests/test_recipes.py`（10 项）。

## D11 · 先草片后成片，草片必须带真实声音（S2-09）

- 问题：旧 `preview` 只渲染 12 秒低清片段与代表帧，片尾与累积问题到最终编码才暴露；草片若无声，
  “带真实配音的整片”就只是说法。
- 选择：
  1. 渲染前新增 `precheck` 阶段：字幕阅读速度/闪现/空白页、动作极值、未登记素材、无效配方、
     长静止段是否写 `hold_reason`；有阻塞问题直接停止，不进入渲染。
  2. `render.mjs` 在最终编码前先渲染整条时间轴的 `animatic.mp4`（`animaticScale=0.35`，crf 30）。
  3. 渲染端只画画面，管线再用 ffmpeg 把该 cut 的真实混音 mux 进草片（copy 视频 + AAC 96k），
     所以草片听到的就是成片的声音。
  4. `compare_animatic()` 用 ffprobe 实测草片：必须有音轨、时长与时间轴一致、帧数与成片一致；
     不一致记为 `animatic.mismatch` 阻断。结论明确写“一致不等于已连续看听”。
  5. `sampling_plan()` 给每个抽帧点写理由（opening/event/motion-extreme/caption-change/ending），
     避免只看每镜完成帧。
- 否：只靠最终编码后抽帧（问题发现太晚）；草片不带声音（无法听出漏读、爆点、音乐压人声）。
- 证据：`tests/test_animatic.py`（11 项）、真实草片渲染与混音探针（A9）。

## D12 · 相机由 Python 计划驱动，TS 只做插值（S2-06）

- 问题：旧 `cameraFor` 只按镜头类型做 2–4% 的装饰推拉，并在每个 beat 轮换固定目标，
  与“这一句在讲哪个对象”无关。
- 选择：
  1. `camera.py` 用事件目标图层的**区域框**计算焦点（`scale/cx/cy`），先全局后聚焦，
     结束前 0.7 s 回到全局，避免结论被裁切。
  2. 缩放夹在 1.0–1.55，取景中心夹在 `[0.5/s, 1-0.5/s]`，不露出画面外的空白；横竖版分别求解。
  3. 只有 `reveal/emphasis/compare/transform` 且 target 真实存在的事件才产生焦点；
     主画面在竖版已占 93% 宽时，推近被判定为无意义并跳过。
  4. TS `cameraFromPlan` 只做关键帧插值：**关键帧保持到下一个关键帧前的过渡窗口**，
     过渡窗口 0.7 s。第一版实现从上一关键帧开始缓动，导致 0.7 s 后就停在下一个取景上
     （真实帧对照像素差 0.00），已修复。
  5. 字幕/页脚在相机变换之外绘制，不随内容缩放。
- 否：让模型直接给相机坐标（无法验证是否指向真实对象）；用 `useFrame` 实时动画（不可 seek）。
- 证据：`tests/test_camera.py`（8 项）、`tests/test_camera_render.py`（真实帧差 8.86）。

## D13 · 参数只走注册函数，数字与几何同源（S2-05）

- 问题：模型可以同时写“series=[0.9,0.7…]”和“标签：误差降到 0.4”，两者没有任何约束，
  画面与旁白可能各说一套。
- 选择：
  1. `parameters.py` 只登记 3 个函数（iteration / linear-transform / projection），参数范围写死；
     不做通用表达式执行器。
  2. `Scene.function` + `parameters` 由程序计算，结果写入规范化场景的 `computed`。
  3. `validate_scene_parameters()` 拒绝两类不一致：series/矩阵与计算结果不同；标签与注释里的
     数字不在计算结果集合内（容差 1e-3 相对）。
  4. 函数与参数进入 `RENDERER_CAPABILITIES.parameter_functions` 与编导提示词。
- 否：允许模型自写 Python/TS 表达式（不可审查、不可复现）；只做“数值检查”而不约束几何
  （曲线仍可能与数字不符）。
- 证据：`tests/test_parameters.py`（15 项）。

## D14 · 修复按缺陷路由，并有独立轮次预算（S3-01）

- 问题：旧逻辑只有“重写全部镜头”和“按 scene_id 局部重写”两种，缺陷类型不影响失效范围；
  排版问题也可能触发重配音，事实问题可能与排版问题混在一轮里互相覆盖。
- 选择：
  1. `repair.py` 定义 9 类缺陷，每类固定 operations / invalidates / rechecks / must_not 与轮次上限。
  2. 分类按**信号计分**（每类若干正则，命中多者胜，平局按固定顺序），不用“首个匹配”。
  3. 视觉审片被拒时：所有阻断项都是 `model`/`source` 且可修复 → 视为编辑性缺陷，写反馈并进入路由修复；
     只要有一项是技术性硬失败（解码、音轨、尺寸）→ 直接失败，不浪费修复轮次。
  4. 修复只删除该缺陷 invalidates 的阶段标记，其余阶段命中缓存；`invalidated` 事件记入 ledger。
  5. 轮次用尽时抛“修复轮次已用尽”并保留原因，不无限重试。
  6. `_keep_untouched_scenes` 之后再加 `scope_violations()` 兜底，范围外镜头被改动即中止。
- 否：按 finding 文本直接整片重写（会反复破坏已通过的内容）；只按轮次计数不看缺陷类型（排版与事实
  共用预算，先耗尽者挡住后者）。
- 证据：`tests/test_repair_routing.py`（18 项）。

## D15 · 转场用叠加而非扣除，缓存键含邻镜（S3-02）

- 问题：如果改用 `TransitionSeries`，重叠帧会缩短总时长——60+60 帧重叠 15 帧只剩 105 帧，
  而旁白是按 120 帧编排的，后面全片错位。另一侧，单镜缓存如果只看本镜内容，邻镜的转场、
  J-cut、共享对象变化会让缓存命中过期结果。
- 选择：
  1. `TRANSITION_POLICY` 明确 `mode=overlay`：转场叠加在相邻镜头各自完整帧数之上，
     `composition.frames` 必须等于 `sum(scene.frames)`；组装检查会拒绝被扣除的时间轴。
  2. `scene_key()` 覆盖内容 + 环境（fps/voice/theme/fonts/policy）+ **前后邻镜**
     （转场类型、shared subject_id、末条字幕），邻镜变化会失效本镜。
  3. `changed_scenes()` 把变更镜头扩展到其邻镜，写入 `scene-changes.json`，让“改了哪一镜、
     重做了哪些镜”可解释。
  4. `verify_cached_file()` 用 hash 判断缓存有效性，半文件/篡改不命中；配音缓存已有
     `timing_matches_audio` 自检。
  5. 编码后再核对：时长、fps、音轨、声道、接点黑帧（`verify_assembly`）。
- 否：逐镜渲染成独立 mp4 再拼接（会引入二次编码与接点丢帧，且当前 Remotion 单次渲染已稳定）。
- 证据：`tests/test_cache_assembly.py`（15 项，含真实编码探针）。

## D16 · 素材按“镜头需求”匹配，裁切由程序验证（S3-03）

- 问题：旧素材库只能按 id 引用，`assets.py` 没有任何检索/匹配/裁切；一张图是否“对”完全靠人工。
- 选择：
  1. `AssetRequest` 描述镜头需求：主体、动作、情境、构图、时长、画幅、真实性（evidence/atmosphere/
     illustration）、授权要求、禁止含义。
  2. 素材登记增加可选元数据（subject/action/setting/tags/focus/subject_box/authenticity）；
     没有元数据的素材仍可显式引用，但不能参与匹配。
  3. `candidates()` 打分并给出理由；`rejected()` 处理硬拒绝（失效、授权缺失、禁止含义、证据要求）。
  4. `choose()` 只接受 score ≥ 2 的候选：授权干净但无关的图**不当作替代素材**，宁可返回“没有可用素材”。
  5. `plan_crop()` 按目标画幅计算裁切矩形，必须包含主体框；只有真正的裁切才会因“主体太小”被拒
     （源图本身就是全画幅时不拒绝）。SVG 不猜尺寸，按 contain。
  6. 管线在 `cut_props` 阶段把裁切写进 image 图层（`crop`/`crop_source`），渲染端据此 `object-fit: cover`
     + `object-position`；决策写入 `asset-decisions.json`。
- 否：联网抓图（E 部分未接入，需预算/许可/边界）；用关键词命中直接当匹配（同词不同义会把示意图当证据）。
- 证据：`tests/test_asset_plan.py`（15 项，含真实 PNG 裁切与竖版拒绝）。

## D17 · 语音后端与核对分离，等价读法只折叠形式（S2-02）

- 问题：语音参数混在 `[studio]`，缓存键不含适配器；配音核对只有字符覆盖率与术语，
  数字量级/正负号变化不会被发现（覆盖率仍可能很高）。
- 选择：
  1. 新增 `[speech]` 分区（backend/voice/model/rate/pitch/volume/granularity/boundary_policy/
     supported_controls/fallback_voice），缺省继承 studio，旧配置不变。
  2. 后端不支持的控制项直接报错，不静默忽略。
  3. `SpeechResult` 记录真实 samples/seconds/voice/model/granularity/边界来源/字符数/用量；
     无真实边界时标 `estimated`，不冒充 native。
  4. `cache_key()` 含读法、后端、音色、granularity 与版本；换后端不会复用旧音频。
  5. `reading_units()` 抽取带符号与单位的数字、否定词、术语与公式；`verify_reading()` 用
     **独立转写**核对，按位置配对比较符号与位数。
  6. `canonical_reading()` 只折叠形式（中文数字、零点五、负），**不折叠符号与量级**。
  7. `policy.audio_checks()`：符号/量级改变 → critical 阻断；未命中的术语/否定 → 非必需 unknown
     提示复听。
- 否：用字符覆盖率代替内容核对（0.5→5 覆盖率仍然很高）；把 ASR 结果当作发音正确性的证明。
- 证据：`tests/test_speech.py`（20 项）。

## D18 · 字体要“真的量过”，字幕要与 SRT 同源（S2-04）

- 问题：原来的字体检查只看文件是否存在；文字宽度用字符数估算（`text_capacity`），
  与真实渲染差 10% 以上；SRT 与内嵌字幕各自生成，无法证明一致。
- 选择：
  1. `fonts.py` 按主题栈顺序加载真实字体，报告实际使用的文件与家族名；
     用 fontTools 的 cmap 判断缺字（PIL 会把缺字画成空白/tofu，不能作为依据）；
     fontTools 不可用时把覆盖率标为 `unknown`，不冒充“全覆盖”。
  2. 提供真实宽度度量（`measure`/`text_width_ratio`），供字幕与文本层检查使用。
  3. `captions_qc.cue_report()` 检查阅读速度（横 9 / 竖 8 字/秒）、最短显示、交叠、缺字、
     宽度占安全区比例、行数；阈值按目标画幅配置。
  4. `collision_report()` 用区域几何检查字幕带/页脚与内容区域是否重叠。
  5. `srt_matches_cues()` 比较交付 SRT 与 cue 文本，篡改可被发现。
  6. 三者进入 precheck（阻断）与质检报告（记录）。
- 否：继续用字符数估算宽度（会把 46px 的 30 字塞进 520px 的注释框）；
  只依赖浏览器渲染后的人工检查（问题发现太晚）。
- 证据：`tests/test_captions_qc.py`（14 项，含真实字体与缺字检测）。

## D19 · 混音必须能分轨审计，人声在人声轨上判（S2-03）

- 问题：`soundtrack()` 只返回立体声混音，无法证明“人声缺失”或“音乐压人声”，也无法复听单个音轨；
  事件是否真的落在时间点上只能靠听。
- 选择：
  1. `soundtrack_stems()` 返回混音 + 分轨（voice_dry/voice/music/arp/sfx/room/duck），
     `write_stems()` 落盘为 WAV 并写 `stems.json`。
  2. `mix.voice_presence()` 在人声轨上判“有没有人声”，绝不用混音能量代替（M04）。
  3. `onset_report()` 在音效轨上测事件处能量相对基线的变化：只证明“这一刻有声音”，
     不证明音色/语义正确（报告里写明）。
  4. `tail_report()` 抓被截断的尾音，`ducking_report()` 抓侧链抽吸，`stem_balance()` 抓装饰轨盖过人声。
  5. `policy.mix_checks()`：人声缺失 → critical 阻断；分轨失衡 → major 阻断；
     事件未测到/抽吸 → 非必需 unknown 提示复听。
  6. 检查在编码前完成，避免“混音坏了才发现”。
- 否：只用响度与峰值判断混音（-14 LUFS 的混音可以完全没有声音）；
  用混音能量判断人声（音乐会把静音填满）。
- 证据：`tests/test_mix.py`（16 项，含真实 `prepare_cut` 分轨落盘）。

## D20 · 形变只在同拓扑时成立，对象身份跨镜可查（S2-07）

- 问题：v1/v2 的 `morph` 只是淡入淡出；参考项目里的“morph 示例”常是圆角变化，不是任意几何形变。
  共享对象在跨镜时没有身份约束，换色/改叫法不会被发现。
- 选择：
  1. `Action.morph_mode`（默认 `crossfade` 保留旧语义）+ `target_points`；`morph_plan()` 只在
     shape 图层、顶点数相同、2–32 个顶点时才判为 `geometry`，否则给出具体拒绝理由。
  2. `resolve_actions` 把 morph_mode/target_points 带进 `actions_resolved`；
     渲染端 `morphPointsFor()` 做顶点线性插值（smoothstep），关键帧可 seek、可重复。
  3. `continuity_report()` 按 `subject_id` 汇总跨镜出现：颜色、叫法、before/after 状态必须连贯，
     不连贯写为脚本警告（不阻断，避免误伤合理重命名）。
  4. `formula_correspondence()` 只统计符号保留，明确“不检查等价性”。
- 否：实现通用 morph 库（Remotion 无内置；圆角变化不是几何形变）；让模型直接给目标坐标做任意形变
  （无法保证不自交、不可审查）。
- 证据：`tests/test_continuity.py`（12 项，含真实帧对照）。
