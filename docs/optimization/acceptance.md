# 验收与证据索引（第二版提纲）

记录每次工作包完成时的**命令、输入、结果与媒体位置**。真实运行产物留在 git 忽略目录
（`workspace/`、`delivery*/`），本文件只保存可复核的索引与结论。

验证层级：V1 离线逻辑 / V2 小型真实媒体 / V3 导入脚本制作 / V4 真实题目制作 / V5 实际看听。

## A1 · S1-01 基线、CI、工具与时区（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 离线测试 | `python -m pytest -q -m "not slow and not live"` | 215 passed, 1 deselected | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 231 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 238 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 251 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 269 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 300 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 300 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 310 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 321 passed | V1 |
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
| 离线测试 | `pytest -q -m "not slow and not live"` | 329 passed | V1 |
| 焦点求解 | 1164×730 主体框 | 缩放 1.0–1.55；取景中心被夹在 `[0.5/s, 1-0.5/s]`，不露出画面外 | V1 |
| 计划生成 | 8 s 镜头、30% 处 emphasis 指向 chart | 关键帧：overview(0) → focus(2.4, target=chart) → overview(7.3)；`reason` 可读 | V1 |
| 无目标事件 | target 为空 | 不产生 focus（相机只指向真实对象） | V1 |
| 画幅差异 | portrait vs landscape | 横版可推近注释带；竖版该带已占 87% 宽，正确放弃推近；窄框在两种画幅都推近但中心不同 | V1 |
| 确定性 | 同输入两次 | 计划完全一致 | V1 |
| 计划校验 | 越界/缩放越界/取景溢出/倒序 | 各自报错，并进入 `validate_cut_timeline` | V1 |
| 关键帧保持 | node 直接调用 `cameraFromPlan` | 0.4 s 到达焦点后保持到 2.6 s，再在 0.7 s 内回到 overview（修复了“提前到位”的插值） | V1 |
| 真实帧对照 | 真实 Remotion 渲染同一镜（有无 focus 计划） | 960×540 两帧平均像素差 **8.86**，均非空白 | V2 |

**未验证**：follow/reframe 两种模式（未实现，能力声明不包含）；真实长片中焦点是否帮助理解（V5，需人群评估）。
