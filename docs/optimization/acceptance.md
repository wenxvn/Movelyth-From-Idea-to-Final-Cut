# 验收与证据索引（第二版提纲）

记录每次工作包完成时的**命令、输入、结果与媒体位置**。真实运行产物留在 git 忽略目录
（`workspace/`、`delivery*/`），本文件只保存可复核的索引与结论。
每节的测试项数会随提交变化，最新数字只在 [verification.md](../verification.md) 维护，本文件不再重复。

验证层级：V1 离线逻辑 / V2 小型真实媒体 / V3 导入脚本制作 / V4 真实题目制作 / V5 实际看听。

## A1 · S1-01 基线、CI、工具与时区（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| Ruff | `python -m ruff check src tests` | All checks passed | V1 |
| TypeScript | `npm --prefix studio run typecheck` | 无错误 | V1 |
| 契约同步 | `write_renderer_contracts` + `git diff -- studio/src/generated` | 无差异 | V1 |
| CLI | `movelyth --help` / `schema` / `doctor` | 可运行，doctor 输出可解析 JSON | V1 |
| 工具表 | `doctor` | ffmpeg 7.1（imageio-ffmpeg）、ffprobe n7.1（Remotion compositor）、Chrome 156.0.8078.48、4 个中文字体 | V1 |
| 时区 | `MOVELYTH_TZ` 未设 / `UTC` / `Not/AZone` | `+08:00` / `+00:00` / 明确 `TimezoneError`（不再静默 +08:00） | V1 |
| 缺 ffprobe | `ffprobe_candidates()` 只含不存在路径 | `RuntimeError` 列出已检查位置与 `npm ci --prefix studio` | V1 |
| 媒体验证 | 2 秒 1920×1080 h264+aac 合成片 → `verify_video` | `passed: true`（10 项检查全通过） | V2 |

**未验证**：远程 Windows/Linux CI 尚未运行（本轮未推送）；`doctor` 的 TTS 连通性未探测（按设计）。

## A2 · S1-02 Review 一致性、轴读数与交付策略（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 刻度镜像 parity | `tests/test_charts.py` 用 node 执行 `ChartLayer.tsx` 的真实 `niceStep/niceDomain/format` 源码 | 8 组输入（含 0.0004–0.003 与常量序列）域/步长/标签完全一致 | V1 |
| M01 一致性 | reviewer `passed=true` + factual finding | 规范化后 `passed=false`；pipeline 抛 `成片检查未通过`，交付目录无 mp4，ledger 非 ready | V1（离线 pipeline） |
| M02 单位/轴错 | “纵轴刻度显示 0.76，但数据点标的是 5” | 不降级：`fail/major`，证据 `claim-about-data-or-units` | V1 |
| 结构性缺陷 | “纵轴刻度被裁切，标签缺字” | 不降级：`fail/major` | V1 |
| 确定性降级 | “纵轴刻度显示 0.4 与 0.8…”（场景实际刻度 0.2/0.4/0.6/0.8/1.0） | 降级为 warning，证据记录生成标签；整片仍 ready | V1（离线 pipeline） |
| 无证据轴疑点 | “纵轴刻度好像不太对” | `unknown` 且非必需 → 不阻断，但留痕 | V1 |
| 交付决定 | 每次 check 阶段 | `release-decision.json`：decision/policy_version/blocking/warnings/passed/inputs | V1 |
| 旧配置兼容 | `downgrade_axis_readings=true/false` | 分别等价 `deterministic/strict`；非法值报错 | V1 |

**未验证**：真实视觉模型的 finding 分布（本机无模型端点）；因此“降级率”与“误降级率”暂无实测数字。

## A3 · S1-03 组成表与 revision 交付完整性（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 组成清单 | 离线 pipeline 交付 | `组成清单.json` 含 episode/revision/creation_mode/policy/schema/renderer/settings_hash、研究/脚本/质检/决定 hash、每 cut 的 seconds/frames/timeline_hash/captions_hash/voice/mix/render_fingerprint | V1 |
| 路径卫生 | 读取 `组成清单.json` 原文 | 不含工作区绝对路径与反斜杠（voice/mix 为 `audio/<cut>/*.wav` 相对路径） | V1 |
| M12 篡改视频 | 改写 `*_横版.mp4` | `manifest_report` 报“文件已改动”；`produce` 抛“已交付文件缺失或发生变化”；用户文件未被覆盖 | V1 |
| 旧 revision 决定 | 把 `交付决定.json` 的 `inputs.revision` 改成下一版 | 拒绝，原因含“其他 revision” | V1 |
| 缺少决定 | 删除 `交付决定.json` | 拒绝，原因含“交付决定” | V1 |
| 音频重生成 | 改写 `audio/long/mix.wav` | 拒绝，原因含“交付后被重新生成”（新声音未进入最终视频） | V1 |
| 中断暂存 | 预置 `.staging/…/r001/遗留文件.txt` 再交付 | 暂存被清空重建；交付包不含遗留文件；`manifest.files` 不含它；暂存目录完成后不存在 | V1 |
| 平台 AI 说明 | `发布文案.md` | 含 AI 说明草稿与“仍需你本人勾选确认”，不声称已完成平台声明 | V1 |

**未验证**：真实编码后视频/音轨与组成清单的一致性（离线 pipeline 使用桩），在 S2-09 与 S3-02 补真实媒体证据。

## A4 · S1-04 来源前移与关键主张覆盖（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 阶段顺序 | 离线 pipeline 记录调用顺序 | `evidence` 在 `director` 之前；编导 prompt 含 `claim_coverage` 与 `source_evidence` 正文节选 | V1 |
| 节选定位 | `locate_excerpt` | 空白/大小写归一后可定位并返回字符区间；不在正文中返回 `None` | V1 |
| 证据不成立 | 快照正文不含 claim 节选 | `claim-coverage.json` 为 `excerpt-missing`；交付决定 `blocked`（critical）；不进入渲染 | V1（离线 pipeline） |
| 来源未取到 | 快照 `status=unavailable` | `source-unavailable`，不冒充已读 | V1 |
| 空主张 | `claims=[]` | `source.research.no-claims` 阻断 | V1 |
| 不确定主张 | `scope=uncertain` | 非必需 unknown → warning，不阻断 | V1 |
| 关键主张未进镜头 | 关键主张来源未被任何镜头 `source_index` 引用 | `fail/major`，阻断 | V1 |
| 旁白新数字 | 旁白出现证据中没有的“37 倍” | 记为非必需 unknown（列出数字），不阻断 | V1 |
| 模型边界 | `source_index`/`evidence_refs` 越界 | Pydantic 拒绝 | V1 |

**未验证**：真实公网来源抓取（本轮无网络抓取任务）、PDF/表格定位（S3-06）、真实模型对
`importance`/`excerpt` 的采纳率（无模型端点）。

## A5 · S1-05 制作 brief、题材与能力路由（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 路由表 | 6 组标题 | 程序图形 supported；录屏/采访 unsupported；三维/生成图/历史影像 needs_extension | V1 |
| 冲突 | “三维演示：用录屏展示真实建模过程” | 取更严格者：unsupported | V1 |
| create 前置拒绝 | 录屏题目 | `ValueError`“无法真实呈现”，ledger 不新增任务行，无模型调用 | V1（M19） |
| 冻结请求 | 三维题目 `create` | `request.json` 记录 route/status/declared_capability | V1 |
| brief 字段 | 离线 pipeline | `production-brief.json`：受众（brief 指定或“未指定”）、先前知识、问题、中心解释、边界、画幅、时长、风格、预算、route/route_status/effective_route/substitutions | V1 |
| 预算未知 | 默认配置 | `estimated_cost: null`、`currency: ""`，不按 0 计 | V1 |
| 示意替代 | 三维题目成片 | `route_status: needs_extension`、`effective_route: program-graphics`、substitutions 注明“标注示意”，质检报告同步记录 | V1（离线 pipeline） |
| 换题保护 | `topic_violations` | 研究问题与冻结 brief 不一致时报告违规 | V1 |
| 能力表进入提示词 | `RENDERER_CAPABILITIES.routes` | 规划/编导提示词能看到各 route 的真实 status | V1 |

**未验证**：真实模型对 `production_brief` 的采纳（无端点）；`needs_extension` 题材的真实成片观感。

## A6 · S1-06 版本化契约、对象身份与语义事件（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 真实渲染 | `pytest -q -m slow`（Chrome + Remotion 4.0.538） | 1 passed：v1 风格 props 仍能渲染出真实帧 | V2 |
| TypeScript | `npm --prefix studio run typecheck` | 通过（types.ts 已加 v2 字段） | V1 |
| 契约同步 | `write_renderer_contracts` + `git diff` | 已提交 layout.json（schema_version 2、event_kinds）与 scene-schema.json | V1 |
| 重复短语 | 旁白“3 与 3 的平均还是 3”，事件取第 1/2 次 | 解析到不同时间；取第 3 次报错“找不到第 3 次” | V1 |
| 字符区间 | `char_start` 锚点 | 解析成功且落在镜头内 | V1 |
| 越界/倒序/目标 | 事件越界、同目标倒序、目标不存在、id 重复 | 各自报错，不静默修正 | V1 |
| 身份 | 同 `subject_id` 的卡片与点 | 两个 layer id 不同、subject 相同；只写状态不写 subject 被拒 | V1 |
| 迁移 | v1 场景、v1 + v2 字段、未来版本 | v1 只补版本号；v1+v2 字段拒绝；v>2 拒绝 | V1 |
| 时钟 | 5 镜 37/45/52/40/61 帧 | 样本区间首尾相接；总样本 = 各镜之和 | V1 |

**未验证**：v2 事件在真实成片中的驱动效果（相机/声音尚未消费事件，S2-03/06）；真实模型的 events 采纳率。

## A7 · S1-07 预算、运行观测与恢复（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 运行记录 | 离线 pipeline | `runs.jsonl` 每阶段一行：stage/status/started_at/ended_at/seconds/input_hash/calls/cache/usage/cost | V1 |
| TTS 用量 | sound 阶段 | `tts_characters`、`tts_seconds` 与旁白文本/音频时长一致（>0） | V1 |
| 渲染耗时 | render 阶段 | `render_seconds` 有值 | V1 |
| 费用未知 | 默认配置 | `cost.actual = null`、`cost.estimate = null`、`currency = "CNY"`、`price_version = ""` | V1 |
| 预算耗尽 | `model_calls = 0` | 首个阶段前抛 `BudgetExceeded`；`provider.calls == []`；无 research.json；ledger 记 failed | V1（M14） |
| 预留/结算 | `BudgetState` 单测 | 二次 reserve 超额即报错；settle 清空预留 | V1 |
| 失败仍记账 | 注入阶段异常 | RunRecord `failed` + `error_type` + `detail` | V1 |
| 缓存不花费 | 同输入二次 stage | 第二条记录 `cached`、calls=0、动作只执行一次 | V1 |
| 恢复 | 重新 `BudgetLedger.load` | used 与落盘一致，remaining 正确 | V1（M15 部分） |
| 配置严格性 | 拼错 `studio.long_second` | `ValueError` 指明键名，不再静默用默认值 | V1 |

**未验证**：真实模型 token 用量与真实费用（无端点/无价格表）；wall_seconds 与 render_minutes 的硬超时未在真实渲染上触发。

## A8 · S2-01 镜头配方与统一风格（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 配方登记 | `recipes.RECIPES` | 6 个：chart-focus / same-scale-compare / parameter-process / flow-expand / paper-evidence / conclusion-callback，每个都有用途、必需绑定、事件、画幅、限制与检查项 | V1 |
| 适用性 | 图表无注释 / 有注释；同单位 / 混单位 series；vectors；diagram+steps；text+source_note；text+claim_ids | 各自正确判定适用或不适用 | V1 |
| 未实现配方 | `recipe="magic-transition"` | 脚本契约在渲染前拒绝，写入 `script-feedback.json`，不产生 final.mp4 | V1 |
| 不适用的已登记配方 | chart 场景声明 `flow-expand` | 拒绝并说明缺少的绑定 | V1 |
| 配方检查 | 注释 x 离数据点过远、对照单位不一致、hero 不存在、纸面缺 source_note | 各自报告 | V1 |
| 记录 | 离线成片 | `质检报告.json` 的 `recipes` 按镜记录实际使用的配方 | V1 |
| 能力暴露 | `RENDERER_CAPABILITIES.recipes`、director.md | 编导提示词列出 6 个配方与必需绑定 | V1 |

**未验证**：真实模型选择配方的分布与采纳率；清爽/纸面两套风格的媒体对照（S2-08 未启用）。

## A9 · S2-09 布局预检、整片草片与编码核对（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 布局 dry-run | `precheck` 阶段（渲染前） | `layout-precheck.json`：每镜问题/警告、`sampling_plan`、`passed` | V1 |
| 字幕过快/闪现 | 0.3 s 塞 22 字 | 预检阻断，不产生 final.mp4；报告写明原因 | V1 |
| 空白字幕页 | 空白 text | 报“空白字幕页” | V1 |
| 未登记素材 | `data_ref="not_registered"` | 报“未引用的素材未登记”；内置 `svd_12` 不误报 | V1 |
| 静止段 | 6 s 镜头无动作/事件/字幕变化 | 无 `hold_reason` 时警告；写了则不再警告 | V1 |
| 无效配方 | 场景声明 `flow-expand` 但无 diagram | 预检报“不适用” | V1 |
| 采样计划 | 8 s 镜头 | 含 opening/ending/scene-midpoint，`(cut, seconds)` 去重 | V1 |
| 整片草片渲染 | 真实 render.mjs，2 镜 180 帧，`animaticScale=0.25` | `animatic.mp4` 480×270、6.000 s、180 帧（Chrome + Remotion 4.0.538） | V2 |
| 草片带真实混音 | ffmpeg 复制视频流 + AAC 96k 混音 | `probe_media` 返回 `duration=2.0, has_audio=true, width=480` | V2 |
| 草片/成片一致 | 帧数、时长、音轨 | 缺草片、帧数不一致、无音轨都判失败；一致时通过（并注明“不等于已连续看听”） | V1 |
| 记录 | 离线成片 | `质检报告.json` 含 `animatic`/`layout_precheck`/`sampling_plan`；`render-spec.json` 含 `animaticScale` | V1 |

**未验证**：真实长片（180 s）草片与成片的完整看听（V5）；草片渲染耗时与节省的正式渲染成本未统计。

## A10 · S2-06 内容绑定焦点相机（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 焦点求解 | 1164×730 主体框 | 缩放 1.0–1.55；取景中心被夹在 `[0.5/s, 1-0.5/s]`，不露出画面外 | V1 |
| 计划生成 | 8 s 镜头、30% 处 emphasis 指向 chart | 关键帧：overview(0) → focus(2.4, target=chart) → overview(7.3)；`reason` 可读 | V1 |
| 无目标事件 | target 为空 | 不产生 focus（相机只指向真实对象） | V1 |
| 画幅差异 | portrait vs landscape | 横版可推近注释带；竖版该带已占 87% 宽，正确放弃推近；窄框在两种画幅都推近但中心不同 | V1 |
| 确定性 | 同输入两次 | 计划完全一致 | V1 |
| 计划校验 | 越界/缩放越界/取景溢出/倒序 | 各自报错，并进入 `validate_cut_timeline` | V1 |
| 关键帧保持 | node 直接调用 `cameraFromPlan` | 0.4 s 到达焦点后保持到 2.6 s，再在 0.7 s 内回到 overview（修复了“提前到位”的插值） | V1 |
| 真实帧对照 | 真实 Remotion 渲染同一镜（有无 focus 计划） | 960×540 两帧平均像素差 **8.86**，均非空白 | V2 |

**未验证**：follow/reframe 两种模式（未实现，能力声明不包含）；真实长片中焦点是否帮助理解（V5，需人群评估）。

## A11 · S2-05 受控计算驱动的参数与图形（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 迭代函数 | x0=1, rate=0.5, steps=4 | 序列 1 / 0.5 / 0.25 / 0.125 / 0.0625，可复现 | V1 |
| 线性变换 | a=1,b=0.5,c=0,d=2 | 四角坐标与行列式 2.0、面积倍数 2.0 同源 | V1 |
| 投影 | (3,4) 投到 x 轴 | 投影点 (3,0)、残差 4.0 | V1 |
| 越界/缺参/零向量/未注册 | 5 组非法输入 | 全部 `ParameterError`，不产生数值 | V1 |
| 曲线与计算不一致 | series 写成 9/8/7/6 | 报“曲线与 iteration 的计算结果不一致” | V1 |
| 标签数字不在计算里 | 文字“面积放大 37 倍” | 报 37 不在计算结果中 | V1 |
| 标签数字来自计算 | “面积放大 2 倍” | 通过 | V1 |
| 矩阵与参数不一致 | matrix=[1,0,0,1] 但参数 d=2 | 报不一致 | V1 |
| 契约暴露 | `RENDERER_CAPABILITIES.parameter_functions`、director.md | 编导只能选 3 个函数与有界参数 | V1 |

**未验证**：真实模型使用 function 的采纳率；参数动画在真实横竖版成片中的观感。

## A12 · S3-01 按缺陷类型路由的最小修复（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 分类 | 9 组 finding 文本 | fact / data / pronunciation / mix / caption / layout / event / asset / review 各自正确 | V1 |
| 信号冲突 | “音乐把结论压住了”“纵轴单位写成毫秒但数据是秒” | 按信号计分选 mix / data，不按首个关键词 | V1 |
| 路由表 | 9 类缺陷 | 每类都有 operations / invalidates / rechecks / must_not；排版修复不得改 claims 或音频 | V1 |
| 轮次 | layout 第 1/2/3 轮 | 前两轮允许，第 3 轮 `blocked_reason` 明确“已用尽” | V1 |
| 分组 | 3 条 finding（2 layout + 1 fact） | 归为 2 个计划，layout 带两个 scene_id | V1 |
| 范围检查 | 未在范围内的镜头被改动 / 被删除 | 各自报告“改动了未在范围内的镜头”“删除了未在范围内的镜头” | V1 |
| 排版缺陷 | 视觉审片报 `visual_defect` | 只失效 render/check（不含 sound）；ledger 记录 `invalidated` 事件 | V1（离线 pipeline） |
| 事实缺陷 | 视觉审片报 `factual` | 失效 evidence/script/sound/render/check | V1（离线 pipeline） |
| 不可修复的硬失败 | 技术检查失败（非 model/source 来源） | 仍直接 `RuntimeError`，不进修复循环 | V1 |
| 范围保持 | 编导重写全部镜头、只指定 one | 范围外镜头逐字不变（merge + scope guard 双重保护） | V1 |
| 轮次上限 | 同一 layout 缺陷持续出现 | 总尝试次数 ≤ 3，任务记为 failed，不无限循环 | V1 |

**未验证**：真实模型在路由后的修复采纳率；`remix`/`re-synthesise-clause` 两个操作的独立执行路径（当前按阶段失效重建，未做单句级重合成）。

## A13 · S3-02 单镜缓存、转场策略与正确组装（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 失效闭包 | `invalidated_by(["research"|"script"|"render"|"policy"|"unknown"])` | 传递闭包正确；未知项不失效任何阶段 | V1 |
| 场景键 | 同输入 / 改旁白 / 改 fps | 一致 / 不同 / 不同 | V1 |
| 邻镜依赖 | 下一镜改 transition 或带 subject_id | 本镜键改变（转场把手与共享对象跨边界） | V1 |
| 单镜变更范围 | 中间镜键改变 | 报告该镜 + 前后邻镜（≤3），另一 cut 单列 | V1（离线 pipeline） |
| 缓存文件 | hash 一致 / 半文件 / 缺失 | 有效 / 无效（“hash 不一致”）/ 无效 | V1 |
| 转场策略 | `TRANSITION_POLICY` | `mode=overlay`，写明 60+60 重叠 15 只剩 105 帧的风险 | V1 |
| 组装算术 | composition 120 帧 vs 镜头和 120 / 105 | 通过 / 拒绝（“不一致”） | V1 |
| 空/坏时间轴 | 无镜头、帧数 0 | 拒绝 | V1 |
| 编码后核对 | 真实 320×180 h264+aac 1 s | `probe_media` 返回 fps 30、双声道、h264、时长 1.0 s；fps/时长/音轨/声道不符各自报错 | V2 |
| 接点黑帧 | 采样亮度含 2.0 | 报“接点附近出现黑帧” | V1 |
| 交付记录 | 离线成片 | 质检报告含 `transition_policy`、`assembly`、`assembly_encoded`、`scene_changes` | V1 |

**未验证**：逐镜分段渲染（当前整 cut 一次渲染，缓存粒度到阶段与场景键，不是到镜头视频文件）；
真实长片的接点黑帧采样（`samples` 回调已实现但未接 ffmpeg 逐帧读取）。

## A14 · S3-03 资产需求、匹配、授权与裁切（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 匹配 | 请求“服务器机柜/插拔网线/机房” | 首选 server_rack（7.0 分），理由含主体/动作/情境/授权 | V1 |
| 禁止含义 | `must_not=["流程图"]` | 示意素材被拒，理由记录在 rejected | V1 |
| 证据要求 | `authenticity=evidence` | 示意素材被拒（“需要真实证据，但素材标注为示意”） | V1 |
| 授权缺失 | license 置空 | 硬拒（“授权信息缺失”） | V1 |
| 空库 | 无素材 | 返回“没有可用素材”，不生成替代图 | V1 |
| 相关度不足 | 请求“海底珊瑚” | 不选任何素材（score < 2），记录 skipped | V1 |
| 横版裁切 | 1600×900、主体框 0.3/0.2/0.4/0.5 | 16:9 裁切、主体在框内、矩形在源图内 | V1（真实 PNG） |
| 竖版裁切切掉主体 | 同上主体框 | 拒绝：“裁切会切掉主体”，不选无关素材替代 | V1 |
| 裁切后主体太小 | 1200×1200 方形转 9:16 | 拒绝：“裁切后主体只占 x%，太小” | V1 |
| 未裁切的源图 | 主体占比 16% 但无需裁切 | 通过（拒绝它等于没有素材） | V1 |
| 矢量素材 | SVG | 不裁切，按 contain，说明原因 | V1 |
| 管线记录 | 离线成片 + 自有素材 | `asset-decisions.json` 记录 chosen/crop/reasons；`render-spec.json` 的 image 图层带 `crop`/`crop_source` | V1 |
| 渲染 | `pytest -m slow` | 通过（image 图层在无 crop 时仍按 contain 渲染） | V2 |

**未验证**：联网素材供应商（E 部分，未接入，能力声明不含）；真实照片的裁切观感（需人眼确认构图）。

## A15 · S2-02 语音后端、读法与独立核对（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 旧配置兼容 | 无 `[speech]` 的配置 | 继承 studio.voice/rate/pitch/volume，行为不变 | V1 |
| 局部覆盖 | `[speech]` 只写 voice/granularity | 其余沿用 studio | V1 |
| 不支持的控制 | pitch 非默认 + supported_controls 不含 pitch | `ValueError`“不支持 pitch”，不静默忽略 | V1 |
| 缓存键 | 同文本 / 改 granularity / 改读法 / 改后端 | 一致 / 不同 / 不同 / 不同 | V1 |
| 合成记录 | 1 s 24kHz 音频 + 1 个边界 | samples=24000、seconds=1.0、boundary_source=native、usage 有值 | V1 |
| 边界来源 | 无边界 | 记为 `estimated`，不冒充 native | V1 |
| 备用音色 | `fallback_from` | 记录被替换的主音色 | V1 |
| 读法单位 | “0.5 / -0.05 / 12 毫秒” | 提取带符号、量级与单位的读法单位；否定/术语/公式各自识别 | V1 |
| 等价读法 | “零点五 / 负零点零五 / 十二毫秒” | 全部折叠为 0.5 / -0.05 / 12，判为通过 | V1 |
| 正负号被改变 | 正确读 -0.05，转写为 0.05 | `changed`（“正负号被改变”），critical 阻断 | V1 |
| 量级被改变 | 正确读 0.5，转写为 5 | `changed`（“数字位数/量级被改变”），critical 阻断 | V1 |
| 漏否定词 | “不正确”转写为“正确” | `missing`（不），非必需 unknown，需复听 | V1 |
| ASR 未启用 | `content_check` | `not-run`，明确写“语音内容未做独立核对” | V1 |

**未验证**：真实 Edge TTS 合成与 faster-whisper 转写（本轮未跑，需联网/模型）；逐句 vs 整段合成的
主观自然度对照（V5，需实听）。

## A16 · S2-04 字体、字幕与动态布局（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 真实字体 | `load_font("body", 66)` | Microsoft YaHei Regular（msyh.ttc）；display 用 msyhbd、serif 用 SimSun | V1 |
| 真实宽度 | “损失” vs “损失下降很多” vs 96px | 宽度随文本与字号单调增加 | V1 |
| 缺字检测 | “天气 ☃ 与 ☂” | 从 cmap 读出 ☃ ☂ 缺字（coverage=cmap）；无 fontTools 时降级为 unknown | V1 |
| 阅读速度 | 22 字塞进 0.3 s | 报“字/秒”与“只显示 0.3s” | V1 |
| 交叠 | 两页时间重叠 | 报“与上一页交叠” | V1 |
| 画幅差异 | 17 字 / 2.0 s（8.5 字/秒） | 横版通过、竖版（上限 8）报错 | V1 |
| 文本层宽度 | 超长注释 | 报“单行宽度占 x%，会换行或缩小” | V1 |
| SRT 同源 | 同一 cue 生成 SRT | `srt_matches_cues` 通过；篡改一个数字后判失败 | V1 |
| 交付记录 | 离线成片 | 质检报告含 `fonts`（各风格实际字体）、`captions`（SRT 与 cue 一致性） | V1 |

**未验证**：浏览器实际渲染宽度与 PIL 度量的偏差（报告注明 ±2%，未做逐字比对）；
逐词高亮在竖版长句上的可读性（V5，需实看）。

## A17 · S2-03 声音事件、分轨与混音（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 分轨 | `soundtrack_stems` | voice_dry / voice / music / arp / sfx / room / duck 各自可读，写入 `stems/*.wav` + `stems.json` | V1（真实 prepare_cut 路径，TTS 打桩） |
| 人声缺失（M04） | 人声轨全零、音乐有能量 | 混音报告 `passed=false`，policy 判 critical 阻断 | V1 |
| 事件落点 | sfx 在 2.0 s 有能量、3.5 s 没有 | 2.0 命中、3.5 报“事件处能量未高于基线” | V1 |
| 事件越界 | 事件在 9 s、混音 1 s | 报“事件时间在混音之外” | V1 |
| 尾音截断 | 结尾仍在峰值 | 报“尾音被截断” | V1 |
| 尾音淡出 | 指数衰减 | 通过 | V1 |
| 侧链抽吸 | 20 Hz 增益翻转 | 报“侧链压摆在抽吸” | V1 |
| 分轨平衡 | music 比人声高 15 dB | 报“music 比人声高 x dB” | V1 |
| 报告缺失 | 无 stems（离线桩） | `audio.<cut>.mix` 记为非必需 unknown，不阻断 | V1 |

**未验证**：真实成片的整片实听、手机外放/耳机/低音量/单声道条件下的听感（V5）；
编码后按事件时间点的亮度/帧差核对（`verify_assembly` 的 `samples` 回调已就绪但未接 ffmpeg 逐帧）。

## A18 · S2-07 真实形变、共享对象与公式对应（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 共享对象 | 同 subject_id、同色、不同图层类型 | 判为连续，列出出现在哪些镜头 | V1 |
| 换色 | 同 subject_id 两镜颜色不同 | 报“换了颜色” | V1 |
| 状态错位 | 上一镜 after=10、下一镜 before=7 | 报出具体状态不一致 | V1 |
| 几何形变（同拓扑） | 4 顶点 → 4 顶点 | `mode=geometry`，顶点数 4，可解析到 actions_resolved | V1 |
| 顶点数不同 | 4 → 2 | 拒绝：“顶点数不同…只能显式 crossfade” | V1 |
| 非 shape 图层 | chart 声明几何形变 | 拒绝：“不支持几何形变” | V1 |
| 旧语义 | 不写 morph_mode | `crossfade`，注明“不是几何形变” | V1 |
| 插值端点 | 0 / 0.5 / 1 | 端点精确、中点线性 | V1 |
| 真实帧对照 | 同一镜 crossfade vs geometry（真实 Remotion） | 差异像素占 **>0.5%**、平均差 >0.5，证明形变真的改变了画面 | V2 |
| 公式 token | `L=(a+b)/2` → `L=(a+c)/2` | 保留比例与共享 token 可查，注明“不检查公式是否等价” | V1 |

**未验证**：公式跨镜形变（渲染端尚无公式 morph）；真实成片中形变的观感与是否需要交叉淡化。

## A19 · S2-08 稳定纸面、手绘圈注与确定性（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 五种笔触 | circle/underline/highlight/bracket/box | 每种 ≥24 个点，坐标在主体框 ±60px 内 | V1 |
| 同 seed | 同输入两次 | 几何完全一致；换 seed 不同 | V1 |
| 时间无关 | 4 个不同 progress | 路径几何不变，只有可见比例变化 | V1 |
| 抖动上限 | underline | 与基线偏差 ≤3px | V1 |
| 渲染端一致 | 用 studio 自带 esbuild 打包真实 `SketchOverlay.tsx`，node 计算同一组输入 | 5 种笔触的顶点与 Python **完全一致**（含 LCG 用 `Math.imul` 对齐 32 位乘法） | V1 |
| 目标校验 | 指向不存在图层 / 重复 id / 越界时间 / 压到字幕带 | 各自报错 | V1 |
| 真实帧确定性 | 同一帧两次独立渲染 | 静帧 JPEG **逐字节相同** | V2 |
| 换 seed | seed 7 vs 9 | 画面有可见差异（笔触不同） | V2 |

**未验证**：纸张纹理/材质叠加（未新增，保持现有主题渐变）；真实成片中圈注与数据的可读性（V5）。

## A20 · S4-03 故障矩阵（2026-10-28）

| 编号 | 注入 | 结果 | 层级 |
| --- | --- | --- | --- |
| M01 | passed=true + factual finding | 规范化后阻断，交付决定 blocked | V1 |
| M02 | 毫秒/秒、轴互换、缺轴变量 | 三类都保持 `fail`，不被降级 | V1 |
| M03 | 空 claims / 节选不存在 | 阻断 | V1 |
| M04 | 音乐有能量、人声全零 | 混音检查判 critical 阻断 | V1 |
| M05 | 漏否定词 / 0.5 读成 5 | 分别记为 missing / changed（量级） | V1 |
| M06 | 重复短语取第 2 次 / 第 5 次 | 第 2 次解析到更晚时间；第 5 次报错 | V1 |
| M07 | 长术语、短 cue、数字单位 | 分页保留单位，拉丁词不被拆开，短 cue 报错 | V1 |
| M08 | 焦点取景越界 | 计划校验报错；正常计划通过 | V1 |
| M09 | 标签数字 37 与计算 2 不符 | 报不一致 | V1 |
| M10 | 有理由的静止段 | 不再报 hold_reason | V1 |
| M11 | 字体/素材/策略变更 | 失效闭包正确 | V1 |
| M12 | 半文件 / 缺组成清单 | 缓存校验与 manifest 校验都拒绝 | V1 |
| M13 | 邻镜转场/共享对象变化 | 场景键改变，重做范围含邻镜 | V1 |
| M14 | 预算耗尽 | 阶段前抛 BudgetExceeded | V1 |
| M15 | 中断后恢复 | 预算账目与落盘一致 | V1 |
| M16 | 主体裁切 / 无关素材 | 不选素材，记录原因 | V1 |
| M17 | http/回环/非 443 来源 | 全部 BlockedSource | V1 |
| M18 | 三维/生成能力 | 标为 needs_extension，不假装可用 | V1 |
| M19 | 需要真实录屏的题目 | create 前置拒绝，不产生任务行 | V1 |
| M20 | 同帧重复/乱序计算 | 几何与相机计划完全一致 | V1（真实逐字节一致见 A19） |

未覆盖：真实 GPU/shader 捕获失败（O 类未启用）、真实模型超时（无端点）、并发进程写同一任务（`ledger.claim` 已有测试覆盖）。

## A21 · S4-04 一次配置、题目输入与可读状态（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 可读摘要 | `movelyth status <id>` | episode/status/revision/stages_done/route/decision/precheck/problems/budget/error/next | V1 |
| 就绪任务 | 离线成片后 | decision=ready，precheck 通过，next 明确“上传仍需本人完成” | V1 |
| 阻断任务 | 事实缺陷 | error.kind=review，problems 定位到 scene_id=two，next 给出 resume/revise | V1 |
| 未开始任务 | 只有 stages 目录 | 不编造阶段与决定，next=“等待运行” | V1 |
| 错误分类 | 预算/能力/素材/资源/复核/配置 | 各自映射到具体用户动作 | V1 |
| 能力矩阵 | `movelyth capabilities` | 5 条路线真实状态、6 个配方、3 个参数函数、E/O 明确 not_implemented/optional_deferred | V1 |

**未验证**：真实题目“只输入标题到成片”的端到端（需要模型端点，见 §3 阻塞）。

## A22 · S4-05 版本、时间点与观察窗口反馈（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 版本绑定 | 观察记录 | 含 episode/revision/cut/platform/url/observed_at/window/metrics | V1 |
| 未知不记 0 | `parse_metrics({"views":10,"likes":None,"completion_rate":""})` | 只保留 views | V1 |
| 非法输入 | 未知指标名、负数、非法窗口 | 各自报错 | V1 |
| 可比性 | 同 revision+窗口 / 换 revision / 换窗口 / 换 cut | 可比并给出 delta / 不可比并说明原因 | V1 |
| 单侧缺失 | 一侧没有 likes | delta 为 null | V1 |
| 观众问题 | “字幕来不及看、语速太快”@73.5s, scene l4 | 生成待验证假设 + 对应检查项（caption_reading_speed 等），状态 unverified | V1 |
| 落盘 | `feedback.json` | 往返可读；坏行被跳过；文件缺失返回空 | V1 |
| CLI | `movelyth feedback <id> --window 24h --cut short --views 120` | 记录 revision、窗口、cut；指标只含 views；提示未抓取平台留存 | V1 |

**未验证**：真实平台数据（无已授权接口，未抓取留存）；把反馈自动变成回归样例的闭环（只生成假设，需人工确认后写测试）。
