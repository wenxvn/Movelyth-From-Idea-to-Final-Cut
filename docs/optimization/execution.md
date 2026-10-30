# 四阶段优化执行状态（第二版提纲）

> 对象：`main`（开工基线 `5383447`，当时 `origin/main` 为 `22237b5`）。
> 本文件是**唯一任务状态**：编号、依赖、状态、证据索引与下一步动作。
> 证据分层见 [verification.md](../verification.md) 与本文件 §2 的 V1–V5 约定。

## 0. 开工检查（提纲 §0.1）

| 项 | 记录 |
| --- | --- |
| 仓库 | 本仓库，分支 `main`；开工时 HEAD `5383447`，`origin/main` = `22237b5`（提纲核对基线） |
| 工作区 | 开工时干净（`git status --short` 空），无未提交的用户修改 |
| 文档 | 已读根 `AGENTS.md`、`README.md`、`docs/architecture.md`、`scene-dsl.md`、`verification.md`、`v2-evaluation.md`、`v3-plan.md`、`v3-evaluation.md` |
| 环境 | 见 §1 环境能力表 |
| 基线（开工时） | `pytest -q -m "not slow and not live"`：206 passed；`ruff`、`tsc --noEmit` 通过；`--help`/`schema`/`doctor` 可运行 |
| 当前 | 524 passed、5 deselected（本轮）；5 项真实渲染 slow 为既有结果、未在本轮重跑；数字只在本行与 [verification.md](../verification.md) 维护 |
| 冻结对照输入 | `tests/fixtures/` 六题 fixture；`docs/v1-evaluation/`、`docs/v2-evaluation/`、`docs/v3-evaluation/` 代表帧（已提交）；V3 成片在本地 `delivery-ab/`（未提交） |
| 核心生产配置 | 程序动画 + Edge TTS（联网）+ 本地 ASR 质检（未默认开启）；付费生成/大模型权重默认关闭 |
| 模型后端 | 2026-10-29 已由配置的 Codex backend 完成 `VID-000038` 研究、长短版编导与脚本审稿真实调用；后续可用性/配额逐次看日志，不再沿用 2026-10-28 的“端点不可用”结论，见 §5 |

## 1. 环境能力表（2026-10-28 实测）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Python | 3.11.9（`.venv`） | `python -V` |
| Node / npm | v24.12.0 / 11.6.2 | `node -v`、`npm -v` |
| FFmpeg | 7.1（imageio-ffmpeg 内置） | `doctor.ffmpeg` + `ffmpeg -version` |
| ffprobe | Remotion `compositor-win32-x64-msvc/ffprobe.exe` | `doctor.ffprobe`（系统 PATH 无 ffprobe） |
| 浏览器 | Chrome `C:\Program Files\Google\Chrome\Application\chrome.exe` | `doctor.browser` |
| 字体 | Noto Sans SC / Noto Serif SC / 微软雅黑 / 宋体 可用 | `C:\Windows\Fonts` 列表 |
| 渲染器 | `studio/node_modules/@remotion/*` 已安装（4.0.538） | `doctor.renderer_installed` |
| 语音 | edge-tts 7.3.1，需联网 | `pip` 元数据；实听见 acceptance |
| ASR | faster-whisper 已安装（首次用需下模型） | `doctor.asr` |
| 时区数据 | `tzdata` 已随环境安装（Windows 无系统 tzdata） | `zoneinfo.ZoneInfo("Asia/Shanghai")` 可用 |
| 模型端点 | 2026-10-29 的 Codex backend 真实调用成功；本机命令探测表为 2026-10-28 快照，不适用于本次运行 | `workspace/VID-000038/runs.jsonl`、`agents/research/events.log`、长短版编导与审稿日志 |
| GPU | 未检测/未使用 | 本轮无三维与 shader 启用 |

## 2. 32 项任务状态

状态取值：`todo` / `in_progress` / `implemented` / `verified` / `blocked` / `optional_deferred`。
`implemented` 不自动等于 `verified`；E/O 延期与核心阻塞分开记录。

### S1 可验证的生产基础（C）

| 编号 | 状态 | 依赖 | 证据 | 下一步 |
| --- | --- | --- | --- | --- |
| S1-01 基线/CI/工具/时区 | verified（本地；远程 CI 未跑） | 开工检查 | A1；`tests/test_doctor.py`、`tests/test_util.py`、`.github/workflows/ci.yml` | 推送后补远程 Windows/Linux 结果 |
| S1-02 Review 一致性/轴读数/交付策略 | verified（V1；真实审片模型未接入） | S1-01 | A2；`policy.py`、`charts.py`、`tests/test_release_policy.py`、`tests/test_release_gate.py`、`tests/test_charts.py`、D3/D4 | S1-04 补来源检查后合并进决定 |
| S1-03 组成表与 revision 完整性 | verified（V1；真实媒体验收在 S2-09） | S1-02 | A3；`pipeline.py`（`build_composition`/`manifest_report`）、`tests/test_composition.py`、D5 | 交付包绑定当前 revision 与决定；S2-09 补编码后核对 |
| S1-04 来源前移与主张覆盖 | verified（V1；真实公网抓取未跑） | S1-02 | A4；`sources.py`（`verify_claims`/`locate_excerpt`）、`policy.source_checks`/`claim_usage_checks`、`evidence` 阶段、`tests/test_claim_coverage.py`、D6 | 真实题目抓取与 PDF 留 S3-06 |
| S1-05 brief/题材/能力路由 | verified（V1；真实模型路由未跑） | S1-04 | A5；`capability.py`、`brief.py`、`models.ProductionBrief`、`brief` 阶段、`tests/test_capability_route.py`、D7 | 真实题目路由统计留 S4-02 |
| S1-06 版本化契约/对象身份/语义事件 | verified（V1 + V2 smoke） | S1-03, S1-05 | A6；`models.py`（v2 + migrate）、`scenedsl.resolve_events`、`clock.py`、`studio/src/types.ts`、`tests/test_semantic_events.py`、D8 | 事件驱动相机/声音在 S2-06/03 消费 |
| S1-07 预算/运行观测/恢复 | verified（V1） | S1-03 | A7；`budget.py`、`runs.jsonl`、`budget.json`、`validate_settings`、`tests/test_budget.py`、D9 | 真实模型用量与费用留 S2-10/S4-02 |

### S2 有解释力的完整成片（C）

| 编号 | 状态 | 依赖 | 证据 |
| --- | --- | --- | --- |
| S2-01 镜头配方与统一风格 | verified（V1；真实模型选择未跑） | S1-05, S1-06 | A8；`recipes.py`、`Scene.recipe`、`tests/test_recipes.py`、D10 |
| S2-02 语音后端/读法/韵律/核对 | verified（V1；真实 TTS/ASR 未在本轮重跑） | S1-06, S1-07 | A15；`speech.py`、`audioqc.content_check`、`[speech]` 配置、`tests/test_speech.py`、D17 |
| S2-03 声音事件/分轨/混音 | verified（V1；真实混音实听未做） | S2-02, S1-06 | A17；`mix.py`、`sound.soundtrack_stems`、`stems/`、`tests/test_mix.py`、D19 |
| S2-04 字体/字幕/动态布局 | verified（V1 + 真实字体度量；逐词高亮沿用既有实现） | S2-01, S2-02 | A16；`fonts.py`、`captions_qc.py`、`tests/test_captions_qc.py`、D18 |
| S2-05 受控计算驱动的参数动画 | verified（V1；真实成片未跑） | S2-01, S1-06 | A11；`parameters.py`、`Scene.function/parameters`、`tests/test_parameters.py`、D13 |
| S2-06 内容绑定焦点相机 | verified（V1 + V2 真实帧对照；跟随/重新取景未实现） | S2-04, S2-05 | A10；`camera.py`、`motion.cameraFromPlan`、`tests/test_camera.py`、`tests/test_camera_render.py`、D12 |
| S2-07 真实形变/共享对象/公式 | verified（V1 + V2 真实帧对照；公式对应只做 token 保留统计） | S2-05, S2-06, S1-06 | A18；`continuity.py`、`Action.morph_mode/target_points`、`Stage.morphPointsFor`、`tests/test_continuity.py`、D20 |
| S2-08 稳定纸面/圈注/材质 | verified（V1 + V2 确定性渲染；材质/纸面纹理未新增） | S2-01, S2-04 | A19；`sketch.py`、`SketchOverlay.tsx`、`Scene.sketches`、`tests/test_sketch.py`、D21 |
| S2-09 布局预检/完整草片/编码核对 | verified（V1 + V2 草片渲染/混音；真实整片看听未做） | S2-03/04/05/06 | A9；`animatic.py`、`precheck` 阶段、`render.mjs` animatic 分支、`tests/test_animatic.py`、D11 |
| S2-10 真实编导使用新能力 | in_progress（VID-000039 NIST 来源版横竖成片 machine-ready；真实模型与媒体链路已走通，完整看听/受众理解未验） | S2-01/07/08/09, S1-04 |
| S2-11 三组样片与两题成片 | in_progress（网络消息 VID-000035 r003、平均数 VID-000039 r002 均 machine-ready；第三组样片未做） | S2-03/04/07/08/09/10 |

### S3 自动修复、效率与扩展

| 编号 | 范围 | 状态 | 依赖 |
| --- | --- | --- | --- |
| S3-01 按缺陷类型最小修复 | C | verified（V1；真实模型修复未跑） | S1-02, S1-06, S1-07, S2-09 | A12；`repair.py`、`_repair_plans`/`_invalidate_stages`、`tests/test_repair_routing.py`、D14 |
| S3-02 单镜缓存/转场把手/组装 | C | verified（V1 + V2 真实编码探针；未做逐镜分段渲染） | S1-03, S1-06, S1-07, S3-01 | A13；`cache.py`、`scene-keys.json`/`scene-changes.json`、`tests/test_cache_assembly.py`、D15 |
| S3-03 资产需求/匹配/授权/裁切 | C（本地已实现；联网供应商未接入） | verified（V1 + 真实图片裁切；联网来源 E 未启用） | S1-04/05, S2-01/04, S1-07 | A14；`assetplan.py`、`assets.register` 元数据、`apply_asset_crops`、`tests/test_asset_plan.py`、D16 |
| S3-04 代码/数据结构/公式模板 | E | not_implemented | S1-05/06, S2-04/07/10 |
| S3-05 素材视频/证据面板 | E | not_implemented | S1-04/05, S2-01/04, S3-03 |
| S3-06 PDF 可定位证据 | E | not_implemented | S1-04, S1-07 |
| S3-07 三维/shader/生成后端 | O | optional_deferred | S1-05/07, S2-06, S3-02/03 |
| S3-08 可编辑时间轴导出 | O | optional_deferred | S1-03/06, S2-03/04, S3-02 |

### S4 真实验收、体验与反馈（C）

| 编号 | 状态 | 依赖 |
| --- | --- | --- |
| S4-01 冻结实验与可归因对照 | blocked（需 3–5 名目标受众） | S2-11, S1-07 |
| S4-02 六题材重复真实评测 | in_progress（N01 两题均有来源可追溯的 machine-ready 成片；六题双跑批次未开始，受众评测仍缺） | S4-01, S3-01/02/03, S1-07 |
| S4-03 异常/恢复/确定性/资源回归 | verified（V1 故障矩阵 23 项；真实编码/模型注入见 A20） | S1-02/03/07, S2-09, S3-01/02 | A20；`tests/test_fault_matrix.py` |
| S4-04 一次配置、题目输入与投稿包 | implemented（V1；真实题目端到端见 S2-11 阻塞） | S1-05/03/07, S2-11, S3-01 | A21；`report.py`、`status`/`capabilities` 命令、`tests/test_report.py`、D22 |
| S4-05 版本/时间点/观察窗口反馈 | implemented（V1；真实平台数据未接入） | S1-03/07, S4-02 | A22；`feedback.py`、`feedback` 命令、`tests/test_feedback.py`、D23 |
| S4-06 最终能力声明与交接 | implemented（能力矩阵与交接文档已交付） | S4-01…S4-05 |

## 3. 已知外部阻塞（不伪造通过）

| 阻塞 | 影响 | 处置 |
| --- | --- | --- |
| 无 3–5 名目标受众 | S4-01 主观对照、S4-02 理解题、S2-11 看听记录 | 交付可盲评包 + 自评时间点记录，明确“未做人群评估” |
| 无 GPU | S3-07 O1/O2 | O 类默认 `optional_deferred` |

## 4. 下一步（可直接执行）

核心 C 中不依赖外部条件的部分已完成。按优先级：

1. **N01 交付边界**：`VID-000039` r002 与 `VID-000035` r003 均 machine-ready，来源和组成清单已核；`VID-000037` OpenStax 来源版暂不进入上传候选。两题均未完成整片人耳实听、ASR 或目标受众理解评估。
2. **推进首批 P1（N02 + N03 + N07）**：补六种配方动态规格与失败样例、具体对象几何焦点/跟随/重取景，以及静音/手机文字边界检查；每项都需同一真实题材回到横竖成片验证。
3. **S4-02 固定批次**：待首批 P1 和两题来源/成片复核后，按 `tests/fixtures/topics/` 的六题冻结 commit/模型/预算/时长，
   每题独立新制作 2 次；用 `movelyth status` 记录首轮通过/修复后/待复核/失败与成本。
4. **S4-01 主观对照**：用同稿 A/B（配音策略、参数动画、字幕/布局、纸面与焦点）做盲评包，
   3–5 名目标受众；结论只写“在本组样本下”。
5. **E 类按需启用**：S3-04（代码图层）、S3-05（素材视频）、S3-06（PDF）各自需要新契约与检查，
   未启用前能力声明保持 `not_implemented`。
6. **真实媒体验收补强**：把 `verify_assembly(samples=…)` 接到 ffmpeg 逐帧读取，做接点黑帧与重帧检测；
   在真实 180 s 成片上跑一次整片草片与成片对照。

## 5. V4 跨平台提纲执行（2026-10-29 至 2026-10-30）

- N01：基线 `134b038`，工作区起初干净；当前模型为配置的 Codex CLI，预算见 `movelyth.toml`。真实标题 `VID-000026`「为什么平均数容易被极端值影响？」与输入 `workspace/v4-mean-brief.md`；研究、来源、brief、长短版脚本和脚本审稿通过，声音、成片及审片尚未完成。记录见 `workspace/VID-000026/runs.jsonl` 与 agents；费用无价格表，保持 unknown。
- 首次及恢复均在声音阶段失败，错误 `NoAudioReceived`；定位到强调词切分产生仅含中文逗号的 TTS 请求。修复分段后再次恢复，复用有效缓存；运行中修改了 `media.py`，因此该次后续结果不是干净 `134b038` 的完整基线。
- N01 第二题、动态成片评估、N02–N13 仍待进行；远程 CI 历史失败详情因本机 `gh` 未认证尚未获取。受众看听、真实投稿和平台反馈均未执行。
- N01 后续：`VID-000026` 的真实 TTS 完成后因字幕预检失败；`VID-000027` 局部修订后仍有竖版图层超宽及浮点边界误判；`VID-000028` 消除了前者部分问题，但 `s4.result` 仍为区域宽度 109%。`VID-000029` 在运行，针对该图层进一步修订；各任务保留原始脚本、音频缓存、日志及失败结果。每次 `revise` 新建任务并重新研究，成本和耗时需计入；不能将这些修订称为单次自动通过。
- 修复：强调词切分合并孤立标点；字幕优先使用无重叠空档延长显示，仍不足时阻断；时长阈值只容忍 1e-9 秒浮点误差。验证：离线 510 passed/5 deselected（在字幕延长与边界误差修复之前）；随后相关 48 passed、Ruff 通过。完整动态成片、人耳实听和受众验证仍未完成。
- `VID-000029` 双画幅真实渲染并经视觉审片拒绝：排序焦点错误、短版公式标签对应错误及文字重叠；短版 contact sheet 可复核。自动修复继承旧局部范围并命中旧视频缓存，未证明问题修复，已停止；修复循环现清除旧范围与复用标志，相关测试通过。
- `VID-000030` 根据视觉缺陷修订并在修复实测字体宽度分页后通过预检，目前渲染中。该次来源 c1 超时、c3 证书验证失败，仍不可交付；按公网地址探测 OpenStax 部分地址可连、部分超时，Penn State 证书失败，未关闭 TLS 验证。
- 第二题 `VID-000031` 按真实标题计划制作；编导输出 `emphasis` 超过 12 字，Pydantic 校验失败，尚无脚本或成片。实际失败记录在任务日志；待修复模型契约失败的重试路径。
- `VID-000030` 两版已渲染并完成抽帧审阅：s3 前后公式标签与 s4 文字重叠有所改善，但 timeline 自动突出末项，排序中位数焦点仍错误；来源 c1/c3 也未核实。自动修复被停止以节省资源，图像为失败样例。
- `VID-000031` 第二题：完整 RFC 快照实测重新定位 c1–c4；模型脚本计划通过，但有跨镜对象换色/状态不连续警告。真实配音完成后预检在短版 s1.scope 宽度 121% 处失败，尚未渲染；已保存语音缓存。`VID-000033` 第一题新计划：三项 OpenStax 主张定位、脚本通过；受众理解与视觉仍未验证，当前正在真实配音。
- 来源安全改进：受校验公网地址间有限重试，TLS 验证保持开启；完整文本用于节选定位，预览仍限长；RFC c2/c4 在完整文本第 73743/94016 字符处实测定位。编导自定义契约错误允许有限重试，timeline 限制写入提示。完整离线回归 518 passed、5 deselected；这不是媒体或受众验证。
- `VID-000035` 复用 `VID-000031` 的真实研究并重新核对 c1–c4，修复 s1 后通过预检并完成两版渲染；视觉审片拒绝 s4 的“应用读取”边标签位置。现场核实是 `DiagramLayer` 将标签放在上方节点前，修复为曲线中点；`workspace/v4-diagram-check/short/scene-04.jpg` 为真实脚本重新渲染的代表帧，实际 SVG 定位回归与 TypeScript 检查通过。当前按原脚本重新渲染，完整审片未完成。
- `VID-000036` 复用 `VID-000033` 的研究并重新定位三项 OpenStax 主张；l7 宽度修订后的脚本计划通过，等待真实制作。此前 `VID-000034` 因局部修订触发新研究并引入未定位来源而停止；`VID-000035` 的人工编排复用原研究，不能据此声称标准 revise 命令已自动复用。
- `VID-000035` r003：两版渲染及机器门禁为 ready，组成清单复核有效；原始视觉审片 passed=true 且只有 warnings，但旧归一化结果错误写成 passed=false。修复 policy 后 warning 不再翻转通过结果，无理由拒绝保持待复核；21 项相关测试和 Ruff 通过。旧交付包不就地改写，需重新审片并生成新 revision；未实听、ASR 未启用，对象连续性仍待动态验证。
- `VID-000036`：第一题真实 TTS、两版预检和渲染完成；视觉审片因 Codex 用量限制失败，日志提示 20:42 后重试。未 ready；保留缓存与失败证据。恢复时需复用 `workspace/VID-000033/research.json`，不得重新计为从头通过。
- `VID-000036` 在额度恢复后复用全部阶段缓存完成视觉审片；审片拒绝 l1 刻度堆叠、l4/l8/s2 结果卡裁切。长版 contact sheet 已人工查看，问题可见；自动编导修复已停止，待定位并修复渲染器，未 ready。最新完整离线回归 521 passed、5 deselected；不代表成片通过。
- 标准 `revise` 已保存来源任务的研究快照并在续做时复用，新的 evidence 阶段仍重新抓取核验；22 项修复路由测试与 Ruff 通过。第一题 compare 版式的 insight band 仅 60/100 px，当前字体和多行内容可能超出；刻度密度及结果卡修复尚未实施，不以隐藏内容或缩减门槛代替验收。
- `VID-000036` 失败脚本代表帧重渲：调整窄 insight card 字号和盒模型后，横版 l4/l8 截断改善；窄 annotation 去掉卡片内边距后，短版 s2 文字完整可见，但在截图尺寸下偏小，手机可读性未知；横版 l1 刻度堆叠仍未修复。证据 `workspace/v4-card-check-2/`，TypeScript typecheck 通过；未重渲整片或重新审片。
- 横版柱图刻度修复为包含零基线，避免柱从 0 起画而刻度却从数据最小值开始；横版窄 insight card 与短版窄 annotation 按实际盒高排版。代表帧证据保留在 `workspace/v4-chart-check/`、`workspace/v4-card-check-3/` 至 `workspace/v4-card-check-6/`；`tests/test_charts.py` 覆盖刻度，场景刻度同步使用该规则。全套离线回归后来通过 524 项（5 deselected），Ruff 与 TypeScript 检查通过。
- `VID-000037` 是 `VID-000036` 的标准修订，完整横竖版渲染与机器审片通过，revision r003 状态 ready；原始审片没有阻断项，旧视觉缺陷已经修正。其来源仍含 OpenStax《Principles of Data Science》3.1 页面；页面明确限制 CC BY-NC-SA 内容的商业使用，并限制未经书面许可输入 LLM/生成式 AI。为避免来源权利不清，r003 原包保留审计、不进入投稿，转以 NIST 来源重做。
- `VID-000038`：同题新任务，brief 限定 NIST/SEMATECH e-Handbook §1.3.5.1 为唯一外部统计来源，示意数据与计算由本项目自行构造；NIST 页面已真实抓取，3/3 关键主张定位为 supported，hash `d4bd438c0a48147502ea4c3a24607a322a8ab9e879e075a155ef5b2e6635e36b`。脚本通过审稿（长版 9 镜、短版 4 镜）；真实配音完成（横版 225.17 s、竖版 80.83 s），但预检因 l2 一条字幕仅 0.95 s、l9 callback 宽度 107%、s1 prompt 宽度 110% 而失败，未渲染或审片。用量为 4 次模型调用、302,192 输入 token、17,550 输出 token、1285 TTS 字符、306 s TTS；费用未配置价格表，保持 null。
- `VID-000039`：从 VID-000038 标准修订而来，复用 NIST 研究并重新抓取核验；只定向修订 l2/l9/s1，脚本和布局预检尚在运行，未确认是否通过。失败的 VID-000038 及 TTS 缓存均保留，不能把修订写成已完成或从头制作。
- 截至 2026-10-29 22:32，VID-000039 脚本审稿已通过；l2 合并短字幕表达、l9/s1 缩短屏幕文字，3/3 NIST 主张仍为 supported。现进入配音/预检，尚无新版预检结果或渲染。修订阶段另用 3 次模型调用（229,851 输入、14,294 输出 token）；费用无价格表，保持 null。
- `VID-000035` r003 的当前账本、release-decision 与待上传 manifest 均为 ready，RFC 9293 是唯一来源，发布文案与来源/署名文件列有链接；两版时长分别 204.17 s、79.1 s。机器审片无阻断项，但保留节奏、重复构图、音效密度、ASR 未启用和未实听等 warnings；本轮没有替代人工观看、实听或受众理解测试。
- N01 当前状态：网络消息题 `VID-000035` machine-ready；平均数题 `VID-000037` r003 因 OpenStax 来源许可条件暂不投稿，NIST 来源版 `VID-000038` 仍在配音。目标受众看听、人工实听、ASR 与实际投稿均未完成。
- `VID-000039` r002：由 `VID-000038` 定向修订 l2/l9/s1，复用 NIST 研究并重新抓取核验；3/3 主张 supported。横版 H.264/AAC 1920×1080、30 fps、225.8 s；竖版 H.264/AAC 1080×1920、30 fps、80.9 s。双版响度 -14.2 LUFS、true peak -1.4 dBTP；未检测到削波、静止镜头或编码问题。总用时 26.329 min；4 次模型调用，288,981 输入 token、15,252 输出 token；TTS 1284 字符/306.6 s（大部分缓存复用）；费用字段 null（未配置价格表）。账本、release-decision、19 文件 manifest 均 ready，`published:false`。
- `VID-000039` 抽帧复核：两版主要计算、同尺度图表与结论可见，视觉审片 raw/normalized 均 passed 且无 issues。非阻断 warning：长版节奏偏均匀，l3/l7 排序细节小；短版 s2 图表上聚且下方留白较多；机器声音事件检出偏少，不能据此判断缺声。未做 ASR、完整实听或全动态审片。来源脚注在画面中截断于 `Me`，完整来源标题、章节、URL 与说明位于投稿文案和 `素材来源与署名.md`；这是成片可见性瑕疵，未改写已生成包。
- OpenStax 版 `VID-000037` r003 继续保留审计、不进入上传候选；根据其官方 CC BY-NC-SA 与生成式 AI 使用条款提示，未据此作法律结论，改用 NIST/SEMATECH e-Handbook §1.3.5.1 作为 `VID-000039` 统计来源。网络消息题 `VID-000035` RFC 9293 包仍为 machine-ready。两题均 unpublished；平台发布、完整实听/ASR 及目标受众评估未执行。
- 首批 P1 尚未开始：N02 配方动态规格、N03 具体对象几何相机、N07 静音/手机可读性门禁；下一步先检查现有能力，再优先实现能用两题真实脚本验证的部分。

### 2026-10-30 阶段记录（早段）

- N02：六种配方已有语义条件、相对时段、焦点、动态演示和失败样例；`guidance_for_scene()` 可按场景过滤，但首次编导调用仍收到完整配方目录，故“模型只见适用配方”尚未完成。
- N03：镜头目标已支持真实 chart annotation 数据点、diagram node、follow 与结尾 reframe；`VID-000040` 用真实标题/NIST 研究生成同题导入脚本样片，长版 animatic、横版静音正式片、短版 animatic 已落盘，竖版正式渲染仍在运行。它验证的是导入脚本制作，不是新编导选配方；持续轨迹跟随和最终机器门禁仍待核。
- N04：连续性审计现只比较相邻镜头的直接接缝，并输出可复核的 handoff 状态，避免把隔着其他镜头的重新出现误当成直接跳变。仍需加入并审看片段中的共享图形接力样例。
- N05：样式已增加统一的 motion profile，令牌控制入场错峰、停稳、相机移动、转场时间和焦点脉冲；Tech/Documentary 有克制的分层偏移，图表与时间线保持同一几何平面。TypeScript typecheck 通过，同稿动态风格比较和渲染成本记录尚未完成。
- N06：新增双向图形内容核对：关联主张中的数字需在图形/可见文字出现，限定词和示意范围不清晰时输出非阻断 `unknown`，字幕不计为图形演示；屏幕数据未能回溯到主张或来源说明时也记 `unknown`。发布策略升至 v3；聚焦回归 34 passed，Ruff 与 TypeScript typecheck 通过。对 VID-000040 脚本做独立复核为 10 项、8 pass、2 unknown（c1 的“仅改变一个值”未有明确画面文字）；它的运行进程按启动时的旧策略版本生成交付记录，不能冒充 v3 门禁结果。
- N07：已有中文静音/手机文字估算与布局告警，阈值是项目启发式，并非平台标准或理解度证明；待 VID-000040 两版完成后复核实际文字边界、动态镜头与静音线索。
- 下一步：完成 VID-000040 的竖版、双版机器审片与释放决定；再用同一脚本做相邻场景接力和 motion profile 对照样片，记录实际画面、总时长与渲染耗时。人耳实听、ASR 与目标受众评估仍缺。

### 2026-10-30 收口更新（V4 跨平台提纲）

- N01：`VID-000040` 平均数题 r007 已按当前 policy v3 通过，`manifest_report` 为 valid；横版 197.5 s、竖版 64.9 s，均为 H.264/AAC、30 fps。NIST/SEMATECH 唯一来源的 3/3 主张 supported。`VID-000035` RFC 9293 r003 原包仍保留 policy v2；当前 `manifest_report` 因版本不匹配返回 invalid。用现有技术/音频/布局/来源/原始审片证据按 v3 只读重算为 ready（48 pass、0 fail、15 optional unknown、2 not_applicable，animatic 一致性通过）；未改写 r003，也未伪造新 revision。
- N02：六类配方已有语义适用条件、阶段/焦点、动态与失败样例；导演首稿上下文不再含完整配方目录，定向修订和审稿按场景仅见适用配方。聚焦测试与 prompt context 测试通过。
- N03：命名 chart/diagram 对象可作为相机目标，支持 focus/follow/reframe 与结尾回全景。用 VID-000035 的实际网络图制作 6 s 双场景样片（180 帧，1920×1080、30 fps）；消息标记从发送端经网络节点接到接收端，抽帧在接点显示连续。渲染器将消息标记绘制在节点底色上方、节点文字下方，解决首轮样片里标记被遮住的问题。样片不是上传成片。
- N04：连续性审计只比较直接相邻场景；同一场景里的图形与注释合并成一个主体表示，同时保留各层证据。接力样片 `continuity-report.json` 为 1 个 handoff、颜色和状态一致、0 问题。对既有脚本审计仍发现身份/状态不匹配：VID-000035 长/短版 12/5 项，VID-000040 长/短版 15/2 项；这些脚本没有因此被静默改写，后续编辑需确认哪些 subject_id 是同一视觉对象。
- N05：同一 VID-000040 脚本的 Tech、Minimal、Documentary 各输出 25 s 横版/竖版预览，共 6 条；30 fps，半尺寸 960×540 / 540×960。三次长短成对渲染耗时为 130.699 / 134.877 / 131.579 s。t=12 s 抽帧未见关键值或标签丢失；未完整动态审看、手机实机评估或盲评，因此不据此宣布风格胜出。
- N06/N07：v3 双向内容核对已随 VID-000040 r007 运行；来源主张数值/示意边界无法从当前画面文本确认时保留 optional unknown。静音阅读与手机排版仍是本地启发式，不代表平台规范或理解度。
- N08：从 VID-000040 两个最终 MP4 解码 AAC，检查每个场景接点前后各 250 ms：横版 8 处、竖版 3 处，窗口内均无精确零样本；最大前后 RMS 差为 3.20 / 1.65 dB。该检查只能排查数字静音和大幅电平变化，不能证明无点击声或音色自然。声音事件起音报告仍保留 unknown。
- N09：Edge TTS 同稿 A/B 使用相同 voice/rate/pitch/volume 和 32 字文本。整句 A 为 6.554 s、一次请求；语义分段 B 为 6.070 s、三次请求、段间 0.1 s。faster-whisper small 对两版给出相同粗转写，无法据此判断停顿、重音或自然度；未选胜者，待人耳盲听。VID-000040 最终 AAC ASR：长版覆盖 85.7%（73/73 关键内容未检出缺失/改写，状态 review），短版 99.2%（2/2 key unit，状态 ok；“极端值”是未出现在短稿的旧术语项）。ASR 疑点需复听，不等于已确认读错。
- N10/N13：当前两题为程序图形题，无需引入素材视频、PDF、代码执行或生成式/真三维支路；能力继续标记未实现/可选延后，没有新增依赖或外部素材。
- N11/N12：逐镜 MP4 输出与真正 handle 扣帧仍未实现，本轮不改动整片渲染架构。捕获方式对照未在 Windows 上执行；共享内存捕获仍关闭，不把其他系统下的收益外推到本机。
- V5 与投稿：完整片人耳实听、目标受众 3–5 人盲评/理解题、手机外放与真实平台发布/反馈尚未完成；当前工作区不具备人群样本或平台观察数据。费用没有价格表，均记 unknown/null。未提交或推送改动。
