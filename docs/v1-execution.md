# V1 执行记录

按《Movelyth V1 规划与执行提纲》执行。每项任务记录目标、实际改变、测试、命令与结果、
验证类型、已知风险与提交。**验证类型严格区分**：`mock` / `单元` / `静帧` / `片段` / `真实长短版` / `人工完整观看`。

## Task ID：P0-01 基线、回归保护与成本记录

- 目标与实际改变：建立 `docs/v1-baseline.md`（环境、基线测试、VID-000001 实际文件参数、
  V1 前抽帧截图）；新增 `src/movelyth/metrics.py`，每个阶段写一行 CSV
  （`workspace/metrics.csv`：时间、任务、阶段、状态、秒数、缓存命中、产物字节数）。
- 修改文件：`docs/v1-baseline.md`、`docs/baseline/v0/*.jpg`、`src/movelyth/metrics.py`、`src/movelyth/pipeline.py`。
- 新增/调整测试：`tests/test_pipeline_v1.py::test_stage_records_lightweight_metrics`。
- 执行命令与结果：`pytest -q` → 65 passed（V1 批次一结束时的数量）；`ruff check src tests` → 通过；
  `npm --prefix studio run typecheck` → 通过。
- 有无调用模型/TTS/渲染：无。
- 验证类型：单元。
- 已知未验证/风险：VID-000001 只做抽帧，未完整观看/实听；Codex 链路不可用（见 baseline §4）。

## Task ID：P0-02 标题 → 可选 brief

- 目标与实际改变：`create` 新增 `--brief-file`；`normalize_brief()` 限制 4000 字、去控制字符；
  `intent_key(title, brief)` 把 brief 的 hash 并入意图判定——同题不同 brief 得到不同任务，
  只有标题时沿用历史 intent（旧任务继续复用）。`episodes` 表新增 `brief`/`brief_hash`
  并对旧库自动 `ALTER TABLE` 迁移。brief 作为数据进入 prompt（明确标注"不是指令"）。
- 修改文件：`cli.py`、`pipeline.py`、`ledger.py`、`prompts/research.md`、`prompts/director.md`、`README.md`。
- 新增/调整测试：`test_title_only_and_brief_have_separate_intents`、
  `test_brief_is_bounded_and_control_characters_are_removed`、
  `test_old_database_is_migrated_without_losing_episodes`。
- 执行命令与结果：`pytest tests/test_pipeline_v1.py -q` → 8 passed。
- 有无调用模型/TTS/渲染：无（mock）。
- 验证类型：单元。
- 已知未验证/风险：brief 只影响创作输入，不会让模型"核实"用户提供的事实；预检说明写在 README。

## Task ID：P0-03 版本化 Scene DSL v1

- 目标与实际改变：
  - `models.py` 新增 `Layer`（text/math/shape/chart/diagram/image/procedural）、`Action`（8 种原语）、
    `Beat`、`Claim`、`Finding`，`Scene` 增加 `layout`/`beats`/`layers`/`actions`/`visual_intent`，
    `Cut` 增加 `schema_version`/`style`。所有字段都有长度/数量/数值范围约束，`extra="forbid"`。
  - 新增 `scenedsl.py`：布局常量与区域、保留区（标题/标签/字幕/页脚）、节拍与动作按**真实 TTS
    词语边界**解析、文本容量估算、时间轴一致性校验、本地数据绑定、渲染端契约生成。
  - `studio/src/types.ts` 同步类型；`studio/src/generated/layout.json` 与 `scene-schema.json`
    由 Python 生成并提交，`test_generated_renderer_contract_matches_committed_files` 防止漂移。
  - 旧任务（只有 `visual`）自动退化为单个 procedural 图层，仍可渲染。
- 修改文件：`src/movelyth/models.py`、`src/movelyth/scenedsl.py`、`src/movelyth/pipeline.py`、
  `src/movelyth/quality.py`、`studio/src/types.ts`、`studio/src/generated/*`、`docs/scene-dsl.md`。
- 新增/调整测试：`tests/test_scenedsl.py`（15 项：旧任务兼容、节拍解析、非法参数拒绝、
  枚举不漂移、契约文件一致、区域不越界等）。
- 执行命令与结果：`pytest tests/test_scenedsl.py -q` → 15 passed。
- 有无调用模型/TTS/渲染：无。
- 验证类型：单元 + 契约。

## Task ID：P0-04 可组合画面与多布局

- 目标与实际改变：
  - `Visual.tsx` 巨型条件分支拆为 `components/` 下的 `TextLayer`、`ShapeLayer`、`ChartLayer`、
    `DiagramLayer`、`ImageLayer`、`ProceduralLayer`，由 `Stage.tsx` 的注册表按 `layer.type` 分派。
  - 新增真实可配置的坐标轴折线/柱状/散点图（带单位、轴标签、来源标注、首末值标签），
    有向节点图（任意节点/连线/步骤），文本与公式（Unicode 上下标），图形原语。
  - 三种叙事布局 `immersive` / `diagram` / `compare`，横竖版各自一套区域；标题与标签改用
    `fitFont` 自动缩字，区域不侵入字幕/页脚。
  - 新增 `theme.ts` 三套风格（minimal/tech/documentary），只改配色、字体层级、节奏。
  - `motion.ts`：动画只依赖 props 与 progress，确定性可复现。
- 修改文件：`studio/src/{Movie,Stage,motion,theme,layouts,types}.tsx|ts`、`studio/src/components/*`、
  `studio/src/Root.tsx`、`src/movelyth/scenedsl.py`。
- 新增/调整测试：`tests/test_render_smoke.py`（真实 Remotion 渲染 4 种构图 × 横竖版，
  断言静帧互不相同且尺寸正常）、`test_scene_signature_distinguishes_real_composition_changes`、
  `test_every_region_stays_inside_canvas_and_clear_of_reserved_bands`。
- 执行命令与结果：`pytest tests/test_render_smoke.py -q --basetemp=workspace/gallery-tmp` → 1 passed
  （横竖共 8 张真实静帧）；`typecheck` 通过。
- 有无调用模型/TTS/渲染：**真实 Remotion + Chrome 渲染**（静帧，非成片）。
- 验证类型：静帧。
- 已知未验证/风险：静帧不能证明运动观感；字体依赖本机 Microsoft YaHei，未分发第三方字体。

## Task ID：P0-05 以实际配音为准的时间轴

- 目标与实际改变：`prepare_cut` 逐镜合成 TTS 后，用**真实词语边界**把 `beats`/`actions` 解析为
  0–1 比例（`actions_resolved`、`beat_times`、`beat_timing`）；边界缺失时明确标注
  `estimated-character-timing`。`validate_cut_timeline` 检查帧数、字幕越界/交叠、动作区间；
  `sound` 阶段失败即拒绝继续。字幕仍是真实词语边界生成，不抢先不滞后。
- 修改文件：`media.py`、`scenedsl.py`、`pipeline.py`、`quality.py`。
- 新增/调整测试：`test_narration_beats_and_actions_resolve_to_real_tts_time`、
  `test_missing_narration_fragment_and_bad_spans_are_rejected`、
  `test_timeline_checks_catch_overlap_and_out_of_range_actions`。
- 执行命令与结果：`pytest tests/test_scenedsl.py -q` → 15 passed。
- 有无调用模型/TTS/渲染：单元用构造边界；真实 TTS 见 P0-10 演示。
- 验证类型：单元 + 片段（真实 TTS 见下）。

## Task ID：P0-06 脚本审核与事实/视觉匹配

- 目标与实际改变：`Research` 增加 `claims`（claim_id、来源下标、摘录、`established/illustrative/uncertain`）；
  `Review` 增加结构化 `findings`（factual / visual_mismatch / visual_defect / audio_defect / warning +
  scene_id）；新增 `consistency.py`：图表趋势与口播方向、示意数据被说成实测、矩阵旋转/面积/保距/塌缩断言、
  数值无对应画面等可测规则；`validate_script` 现在返回 warnings 并拒绝明显不一致。
- 修改文件：`models.py`、`consistency.py`、`quality.py`、`prompts/research.md`、`prompts/reviewer.md`、`prompts/director.md`。
- 新增/调整测试：`test_chart_trend_must_match_narration`、`test_measured_claim_on_illustrative_chart_is_rejected`、
  `test_matrix_claims_are_checked_against_real_coefficients`。
- 执行命令与结果：`pytest tests/test_scenedsl.py -q` → 15 passed。
- 有无调用模型/TTS/渲染：无。
- 验证类型：单元（构造"说下降却画上升"等反例）。

## Task ID：P0-07 分镜预览、局部修复、避免昂贵整片重做

- 目标与实际改变：
  - `movelyth preview VID-xxxxxx` / `create --preview`：只渲染代表帧 + 12 秒低分辨率（0.5 倍）片段，
    输出 `storyboard.json`（镜头、布局、图层类型、静帧与预览路径）与 `previewed` 状态；
    **不进入待上传交付**。
  - `movelyth revise VID-xxxxxx --notes notes.txt`：从审阅意见定位 scene id 或"镜头 N"，
    新建 revision，只把目标镜头交给编导重写，其余镜头从 `revise-base.json` 原样保留
    （`_keep_untouched_scenes`）；旧交付不被覆盖。
  - 缓存：语音按镜头文本 hash 复用；`sound`/`render` 阶段按输入 hash 复用。真实演示中
    revision 的 `sound` 阶段 0.2 s（全部命中语音缓存），而首次为 23.4 s。
- 修改文件：`pipeline.py`、`cli.py`、`studio/render.mjs`。
- 新增/调整测试：`test_preview_stage_produces_storyboard_without_final_render`、
  `test_local_revision_only_rewrites_targeted_scenes`、`test_revise_requires_locatable_notes`。
- 执行命令与结果：`pytest tests/test_pipeline_v1.py -q` → 8 passed；
  真实演示 `movelyth create "…" --preview --new` → VID-000003 `previewed`，
  `workspace/v1-demo/VID-000003/preview/{long,short}/preview.mp4` 均 12.0 s、960×540；
  `movelyth revise VID-000002 --notes …` → VID-000004 `ready`。
- 有无调用模型/TTS/渲染：演示用 mock provider + 真实 TTS + 真实渲染。
- 验证类型：片段 + 真实长短版（mock 剧本）。
- 已知未验证/风险：**未实现按单镜重新编码再拼接**；revision 仍重渲染整条 cut。
  原因：当前 Remotion 按 composition 整体渲染，逐镜拼接需要额外处理转场与音画对齐，
  属于提纲允许的"按 cut 复用"，已在本文档与 README 如实记录，未做脆弱重构。

## Task ID：P0-08 声音与字幕质检升级

- 目标与实际改变：新增 `audioqc.py`：可选本地 ASR（`faster-whisper`，未安装时如实报
  `disabled`/`unavailable`）、转写与原稿的字符覆盖率/漏词/重复检查、长静音检测
  （区分片头片尾留白与内部断裂）、混音/原声能量比（配乐是否盖住人声）。`quality.verify_video`
  增加 `audio_signal` 说明"audible 只表示非静音"。配乐从固定循环扩展为
  `minimal/tech/documentary` 三种本地合成预设。`speech_replace` 可选发音映射（同时作用于配音与字幕）。
- 修改文件：`audioqc.py`、`quality.py`、`media.py`、`pipeline.py`、`movelyth.toml`。
- 新增/调整测试：`tests/test_audioqc.py`（6 项：ASR 可选、覆盖率、内部长静音、尾部留白、配乐过响、缺失文件）。
- 执行命令与结果：`pytest tests/test_audioqc.py -q` → 6 passed。
- 有无调用模型/TTS/渲染：真实 FFmpeg 分析 + 合成音频。
- 验证类型：单元 + 真实音频分析。
- 已知未验证/风险：**未安装 faster-whisper，ASR 未执行**；没有人工实听，报告里
  `listened_by_human=false` 保持不变。

## Task ID：P0-09 源信息安全与不可信内容边界

- 目标与实际改变：`sources.py` 重写：仅 HTTPS/443/无凭据；拒绝 loopback、RFC1918、link-local、
  metadata、保留地址与 `.internal/.local/.lan` 等主机名；**DNS 解析后固定连接到已校验的公网 IP**
  （TLS 仍用真实 SNI），重定向逐跳重新校验（最多 3 次）；限制 URL 长度、响应大小、MIME、编码；
  成功缓存 30 天、失败缓存 6 小时（不会永久读取过期失败）；记录 `retrieved_at`、`resolved_ip`、
  `content_sha256`、`status`。新增 `safe_local_asset`：受控目录 + 后缀白名单 + 拒绝绝对路径与 `..` 逃逸。
- 修改文件：`sources.py`、`tests/test_sources.py`。
- 新增/调整测试：`tests/test_sources.py` 16 项（恶意 URL 参数化、内网解析、重定向到内网、
  重定向环、超大响应、错误 MIME、失败缓存过期、注入文本按数据处理、素材路径逃逸）。
- 执行命令与结果：`pytest tests/test_sources.py -q` → 16 passed。
- 有无调用模型/TTS/渲染：无（注入 opener/resolver）。
- 验证类型：单元 + 安全边界。

## Task ID：P0-10 第一次跨题材真实验收

- 目标与实际改变：见 `docs/v1-evaluation.md`。
- 结论：**未完成真实模型驱动的三题材验收**，因为本机 Codex 链路不可用（`tls handshake eof`）。
  已完成的是 1 个题材（梯度下降）在 mock 剧本 + 真实 TTS + 真实双画幅渲染下的端到端成片，
  以及 V1 前矩阵主题成片的抽帧对比基线。按提纲要求，只标"代码阶段完成，V1 实片验收未完成"。
- 验证类型：真实长短版（mock 剧本）+ 片段 + 静帧。

## Task ID：P1-05 模型后端接口抽象

- 目标与实际改变：`agents.py` 新增 `AgentProvider` 协议、`resolve_codex()`（支持 `MOVELYTH_CODEX`）、
  `MockProvider`（离线、确定性、同样做契约校验）与 `create_provider()`。Codex 仍是默认；
  未知 provider 直接报错，**不会静默切换到别的模型**。Codex 事件日志中的 `usage` 会解析进质检报告。
- 修改文件：`agents.py`、`pipeline.py`、`movelyth.toml`、`cli.py`。
- 新增/调整测试：`tests/test_providers.py`（6 项）。
- 执行命令与结果：`pytest tests/test_providers.py -q` → 6 passed。
- 验证类型：mock + 单元。

## Task ID：P1-01/P1-02/P1-03（部分）视觉组件、风格与素材

- 已实现：图表（真实数值/本地 JSON 数据）、有向图与步骤、公式、图形原语、程序动画作为图层；
  三套风格；本地受控图片素材（`data_ref` 绑定已生成的 SVD 图层，拒绝远程 URL）。
- 未实现（如实记录）：网络队列/丢包示意、算法状态机、读取用户 CSV 的通用数据面板、
  外部素材搜索与授权管理。这些留给下一轮，避免"堆组件"。
- 验证类型：静帧（`tests/test_render_smoke.py`）+ 单元。

## Task ID：P1-08 CI 与测试分层

- 目标与实际改变：新增 `.github/workflows/ci.yml`：Python 3.11 + Node 20，跑
  `ruff check`、`pytest -m "not slow and not live"`、`tsc --noEmit`、契约文件一致性检查；
  不安装 Remotion 渲染器、不调用 Codex/TTS，因此不会产生费用。
  本地用 `pytest -m slow` 跑真实渲染静帧，`-m live` 留给真实模型/TTS。
- 修改文件：`.github/workflows/ci.yml`、`pyproject.toml`（markers）。
- 执行命令与结果：本地 `pytest -q -m "not slow"` 通过；CI 实际运行状态见提交页（本机无法执行 GitHub Actions）。
- 验证类型：配置 + 本地等价命令。
- 已知未验证/风险：**CI 从未在 GitHub 上实际运行过**，不能声称已通过。

## Task ID：P1-09 六主题回归集

- 目标与实际改变：`tests/fixtures/topics/*.md` 固化六个验收题目的原始输入与预期能力，
  `docs/v1-evaluation.md` 保存逐题状态表（当前只有 T03 有离线演示成片）。
- 验证类型：文档 + 输入固化。

## Task ID：P2（未实施）

- `suggest` / `daily`、可视化工作台、任务队列、反馈闭环策略：**未实现**，不在 V1 完成条件内。
  `README` 与 `SKILL.md` 明确说明"生成今日份视频"仍需先读取历史再由助手选题，CLI 不会自动定时启动。
