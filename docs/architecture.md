# 工作流与数据

能力路由 → 研究 Agent → 来源抓取与主张核对 → 冻结 production brief → 编导 Agent →
独立脚本审稿 → 受控 DSL 校验 → 配音/混音/素材 → 布局预检 → 渲染（含整片草片）→
技术/音频/字幕/组装检查 → 统一交付决定 → 编号交付。

阶段名与顺序（`movelyth status` 显示的就是这些）：`research` → `evidence` → `brief` →
`script` → `sound` → `assets` → `precheck` → `render` → `check`。每个阶段记录输入 hash、
输出 hash、用量与耗时（`runs.jsonl`、`budget.json`），命中缓存时同样留一行记录。

每个 Agent 是一次独立上下文的模型调用（默认 Codex CLI），输出由 Pydantic schema 校验。
角色默认串行运行，减少本机资源竞争；这不等同于多个模型供应商的并行集群。
模型不生成并执行 shell，也不修改制作工程；画面只采用枚举支持的组件及有界参数。

## Scene DSL 与渲染

编导输出的是版本化 Scene DSL（当前 `schema_version = 2`）：一个镜头由 1–6 个图层组成，
图层类型为 text/math/shape/chart/diagram/image/procedural，布局为 immersive/diagram/compare。
`scenedsl.py` 是布局、保留区、节拍解析与校验的唯一来源，并生成
`studio/src/generated/layout.json` 与 `scene-schema.json` 给渲染端，两侧不会各自漂移。

渲染端 `Stage.tsx` 用注册表按图层类型分派到 `components/` 下的组件；动画原语只有 8 种，
且只依赖 props 与 frame，因此可确定性复现。旧任务（只有 `visual` 字段）自动退化为单个
procedural 图层。V2 在这一层加了四个有界的方向字段（转场、运镜、重点词、音效），
并重做了栅格、图表与字幕；v2 再加**镜头配方**（`recipe`，编导只能选已实现且适用的配方）、
**语义事件**（`events`，绑定真实配音边界，重复短语用 occurrence/字符区间消歧）、
**对象身份**（`subject_id` 与图层 `id` 分离）、**受控参数函数**（`function`/`parameters`，
坐标与数字同源）与**手绘圈注**（`sketches`，几何只由 seed 决定）。细节见 [Scene DSL](scene-dsl.md)。

模块分工（都在 `src/movelyth/`）：`policy.py` 把每份报告汇成交付决定；`brief.py`/`capability.py`
决定这集能不能真实做；`sources.py` 抓取并核对主张；`recipes.py`/`parameters.py`/`camera.py`/
`sketch.py`/`continuity.py` 是编导可选能力的契约与检查；`animatic.py` 做布局 dry-run 与整片草片；
`cache.py` 管场景键与失效；`repair.py` 按缺陷类型路由修复；`budget.py` 管预算与账目；
`mix.py`/`speech.py`/`captions_qc.py`/`fonts.py` 是声音与文字的可测部分；`report.py` 汇总一屏状态。

## 声音：从"讲解"到"声音设计"

- **三级韵律**：句 → 从句（逗号/分号/冒号处）→ 重点短语。每段单独调 Edge TTS，
  从句之间 35–100 ms、句末按标点 120–420 ms；重点词放慢 10%、响 6%；
  问句抬高、末句略慢、长从句略快。引擎每句自带的前后静音会被裁掉。
- **配乐是编排，不是循环**（`sound.py`）：本地 numpy 合成，pad 常驻，低音/琶音/轻打击
  按镜头 `role` 的能量出现（hook 0.72 / mechanism 0.56 / example 0.46 / turn 0.80 /
  conclusion 0.66），turn 段掉一次脉冲；pad 用 6.7 ms 延迟做宽度，琶音分侧。
- **自动 Foley**：`design_sound_events` 从真实动画时间轴生成事件——转场提前 0.24 s（J-cut）、
  `draw` 起止、`appear`/`scale`/`highlight`、图表“当前点”、重点词 chime、结论 chime+sub、
  每三句一次翻页声；20/min 上限、0.30 s 内合并，导演 `cues` 优先级最高。
- **共享空间**：合成混响脉冲按 `sum|h|` 归一（按峰值归一会让湿声比干声大 20 dB），
  音效走同一条 send，另加 -66 dBFS 房间底噪，句间不再是数字静音。
- **侧链与人声处理**：人声做 92 Hz 高通、3 kHz 存在感提升与轻压缩；bed 用带 lookahead 的
  平滑侧链（18 ms / 300 ms）压低，Foley 用更浅的 duck（0.30 + 0.35×duck）。
  总线电平经过实测校准：混音/原声最大比 1.17–1.18，均值 0.84–0.85。

机器可测的只有响度、真峰值、混音/原声能量比、长静音、事件密度/类型/同步率；
"好听"仍需人工实听，报告里 `listened_audio` 默认 false。

## 画面：coverage beat 与构图指标

渲染端按真实字幕句把长镜切成 2–4 个 coverage beat（`studio/src/insights.ts`）：每个 beat
换 Insight 卡的主值、换图表注释点、把镜头轻推/轻拉 3% 并留出末段稳定期。它不是随机动效，
边界来自配音句读。`craft.py` 在成片后测量两件与观感直接相关的事：

- `composition_report`：代表帧的最大主体高度、墨迹占比、空白网格占比（V2 21% → V3 56% 主体高度）；
- `rhythm_report`：多少字幕页在 ±0.8 s 内有动作或 beat 起点（覆盖率 47%）；
- `sound_design_report`：事件密度、类型数、与动作锚点的同步率、混音电平与立体声相关系数；
- `narrative_report`：报幕句、句长变异、role 多样性、结论是否回扣开场、每镜动作数。

四者都在 `quality.json` 里，且都写明局限：它们是可复核的信号，不是审美评分。

## 来源与适用范围

研究角色可使用只读搜索，输出 facts 与 **claims**（主张 → 来源下标 → 摘录 → established /
illustrative / uncertain）。审稿角色核查脚本与来源的对应关系，并给出结构化 findings
（factual / visual_mismatch / visual_defect / audio_defect / warning + scene_id）。
机器检查和 AI 审稿不能替代所有领域的人工事实审查。

来源只作为文本引用。抓取限制：仅 HTTPS、443、无凭据；DNS 解析后固定连接到已校验的公网 IP；
拒绝回环、RFC1918、link-local、metadata 与内网重定向；限制 URL 长度、响应大小、MIME 与重定向次数。
成功证据缓存 30 天、失败缓存 6 小时，记录抓取时间、解析 IP 与内容 hash。网页正文始终是数据，
不会被当成 Agent 指令。

本版图像为自身程序绘制，SVD 数据由 NumPy 真实计算；不自动下载并转载第三方图片或视频。
用户素材必须通过 `movelyth asset-add` 显式登记（作者/许可/范围/来源），登记后按 hash 校验并复制
进任务受控目录；未登记、被改动或授权字段不全的素材会在渲染前失败。交付时自动记录引用任务
（`used_by_episodes`），`movelyth asset-check` 会重校验全部素材并把失效项写回 `valid=false`，
失效素材同样被拒绝，不会静默替换。
本地素材只能从受控目录读取，拒绝绝对路径、`..` 逃逸与非白名单后缀。

## 台账

`workspace/studio.sqlite` 使用 WAL 与事务分配编号。`episodes` 保留标题意图、brief 与其 hash、
状态、运行进程、错误和交付路径；`events` 追加阶段起止与失败；`ideas` 保留未来选题；
`feedback` 保存带观察时间的数据；`publications` 将发布状态与制作 ready 分开记录。
旧数据库在启动时自动补齐 `brief`/`brief_hash` 列，历史记录不丢。

相同规范化标题（且相同 brief）默认恢复原任务；`--new` 表示另做一个新任务，获得新编号。
它不是原作品的原地覆盖修订。标题规范化仅能处理完全相同/标点不同的标题，语义去重还需要
选题角色或用户判断，尚无向量库相似度保证。

运行锁由数据库事务和进程存活检查维护。强行结束进程后可重新认领；PID 被系统重用的少见情形
可能需要人工确认，程序不会直接终止别人的任务。

## 缓存与文件

每个阶段保存输入 hash、输出文件 hash 和结果。输入变化、缓存损坏或缺文件时重新执行；
不只凭文件存在认定成功。语音缓存以文本、音色、语速、音高、音量与实现版本为 key，
保留真实边界时间和 PCM 音频，因此局部修改只会重新合成被改动的句子。
每个阶段的耗时、缓存命中与产物大小写入 `workspace/metrics.csv`（一行一阶段，不引入监控平台）。

已通过校验的研究与脚本在同一任务恢复时保持固定，避免修复渲染器却重写故事并重新合成所有语音；
复用仍检查原始产物 hash 并记录原始/当前输入版本。prompt 更新默认用于新任务，明确重做用 `--new`。
实际审片反馈要求改写时会解除脚本冻结；导入新脚本也会重新审核。

`revise` 用 `revise-base.json` 保存被修改任务的已审脚本，只把被点名的镜头交给编导，
其余镜头原样合并回来，并生成新 revision。

纯渲染器修复（版式、字号、图层画法）不需要重写故事：`resume <id> --reuse-script` 复用已审
`film.json`，仍按当前契约重新校验，并记录 `approved-script-reused` 事件。

研究/编导/审稿的 prompt、schema、原始结构化结果与事件日志保存在对应任务的 `agents/`。
它们属于本地运行数据，不提交 Git。无效的模型内容不会作为可执行代码处理。

## 声画

先按镜头、再按句子合成 Edge TTS，按音频真实样本数对齐帧数（秒→帧→样本只在 `clock.py` 定义，
各镜半开区间首尾相接，不累积漂移）；字幕使用语音边界，匹配不到时标明估计时间模式。
`beats`/`actions`/`events` 里的 `narration:片段` 会按真实词语边界换算成秒，
关键画面能在对应词句处触发；重复短语用 `occurrence` 或字符区间消歧，找不到就报错。
同一套词边界还驱动字幕的逐词高亮与重点词着色。

语音参数在 `[speech]`（backend/voice/rate/pitch/volume/granularity/boundary_policy），
缺省继承 `[studio]`，旧配置不变；后端不支持的控制项直接报错而不是静默忽略。
每次合成记录真实采样数、音色、模型、边界来源与用量（`timelines.json` 的 `speech`）。

混音落盘为可审计的分轨：`voice_dry`/`voice`/`music`/`arp`/`sfx`/`room`/`duck`
（`audio/<cut>/stems/`）。**人声缺失在人声轨上判**，不会被音乐能量掩盖；
事件落点、尾音截断、侧链抽吸与分轨平衡在编码前检查（`mix.py`）。

程序配乐有三套预设（minimal/tech/documentary），按段落编排而非循环播放，
并按真实旁白能量做带 lookahead 的平滑侧链压低；音效由 `cues` 驱动、本地合成。
FFmpeg 两遍 loudnorm 归一到 -14 LUFS / -1.5 dBTP，编码 AAC。
Remotion 生成 1920×1080 横版和 1080×1920 的独立短版场景序列。

## 检查和交付

检查实际最终文件的完整解码、H.264/AAC、画幅、帧率、时长、音量、黑屏与低分辨率时间采样运动变化；
另外测量构图（主体高度/空白网格）、讲述节奏（字幕页覆盖率）、声音设计（事件/同步/电平）与
离线叙事检查（报幕、句长、role、回扣）；
再把每镜代表帧交给独立视觉审片。音频侧另有可选 ASR、长静音（区分片头片尾留白）与混音/原声
能量比检查。肉眼看不到的东西不写成通过：抽帧审片不能证明全片运动观感，音量检查不能证明配音
听感或术语全部正确；报告里 `listened_by_human`、`watched_full_video` 默认 false。

V2 的质量报告另外包含 `pacing`（每镜真实时长、离散度、重复视觉签名、转场种类、音效数）与
`sound_design`（每分钟音效数、类型分布、运镜分布、混音电平与动态范围）。运动检查从
1 fps 均值改为 2 fps 中位数并统计静止采样占比：一次硬切不该让三分钟的静帧蒙混过关。

所有检查都归一成 `CheckResult`（`pass/fail/unknown/not_applicable` × `critical/major/minor` ×
是否必需），由 `policy.decide()` 汇成一个 `ReleaseDecision`：任一 critical/major 失败 → 阻断，
必需项未知 → 待复核，其余才 `ready`。模型的 `passed=true` 不能覆盖事实缺陷；
坐标刻度读数只有在能与程序生成的刻度逐值对上时才降级为 warning。

视觉审片被拒时按缺陷类型路由修复（`repair.py`）：排版只重做 render/check，读法只重做声音，
事实缺陷回到证据与脚本；每类缺陷有自己的轮次上限，范围外的镜头逐字不变。
模型只能修改结构化内容，不能自动改渲染代码。达到次数上限或遇到程序故障时留下 failed；
程序故障可在修复后恢复。

交付先写 `.staging`（先清空，避免把上次中断的残留当成本次产物），校验通过后原子重命名至
`待上传`，最后更新数据库。已存在且损坏的交付包不会被覆盖。一个包 20 个文件（有预览时再加
`分镜预览.json`）：

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | 登记包内每个文件的 hash、组成清单指纹与版本 |
| `组成清单.json` | 研究/脚本/质检/决定的 hash、每 cut 的时间轴/字幕/人声/混音 hash 与渲染指纹 |
| `交付决定.json` | 授权这次交付的 `ReleaseDecision`（策略版本、阻断项、通过项） |
| `质检报告.json` | 技术/音频/混音/字幕/组装/审片结果与限制 |
| `制作溯源.json` | schema 版本、provider、creation_mode、渲染指纹、素材 hash |
| `发布文案.md` | 采用标题/备选标题/封面文案/简介/标签/来源 + AI 说明草稿 |
| `交付审计.md` | 哪些机器检查通过、ASR 与人工验证是否真的执行 |
| `素材来源与署名.md` | 来源链接与本地素材授权 |
| `原声_*.mp3` / `混音_*.mp3` | 不打开视频也能试听 |

改包内任一文件、换掉音频或拿旧 revision 的决定来用，`manifest_valid()` 都会判失效。

## 预览与成本

`--preview` / `preview` 只渲染每镜代表帧、封面与 12 秒 0.5 倍分辨率片段，输出 `storyboard.json`，
状态为 `previewed`，**不进入待上传**。它用于在昂贵渲染前检查构图、文字容量与画面是否贴题。

正式渲染前还有两道更便宜的关卡：`precheck` 阶段做布局 dry-run（字幕阅读速度/闪现/空白页、
动作极值、未登记素材、无效配方、长静止段是否写 `hold_reason`、真实字体宽度与缺字），
渲染端再输出整条时间轴的低清草片（`animatic.mp4`），管线把该 cut 的真实混音 mux 进去，
并用 ffprobe 核对草片有音轨、时长与帧数与时间轴一致。`sampling_plan` 为每个抽帧点写明理由
（opening/event/motion-extreme/caption-change/ending），避免只看每镜完成帧。
`storyboard.json` 现在也记录每镜的转场、运镜、重点词与音效，便于在预览阶段就发现
"全片一种转场"或"没有音效"。

revision 目前仍会重渲染整条 cut（Remotion 按 composition 整体渲染，逐镜拼接需要额外处理
转场与音画对齐），但语音、研究和其他未变化的阶段会命中缓存；`scene-keys.json` 记录每镜的键
（含前后邻镜与环境），`scene-changes.json` 说明这次重做涉及哪些镜头。这是已知限制，不做脆弱的大重构。

## 预算与运行观测

`[budget]` 冻结一次任务的调用数、token、TTS 字数/秒数、渲染分钟与墙钟上限；超限在**下一阶段开始前**
抛 `BudgetExceeded`，不降低事实与关键检查标准。每阶段写一行 `runs.jsonl`（状态、耗时、输入 hash、
调用数、用量、费用），并更新 `budget.json`。费用分 `estimate`/`actual`/`currency`/`price_version`，
没有价格表时 `actual` 为 `null` 而不是 0。未知配置项与拼错的键会直接报错，不会被静默忽略。

## 能力边界

`capability.py` 登记五条题材路线并给出真实状态：程序图形 supported；授权素材/生成素材/空间演示
needs_extension（需要新组件或外部资源）；真实录屏/实拍 unsupported，`create` 会前置拒绝，
不留失败任务行、不产生模型调用。`brief.py` 把受众、问题、边界、画幅、时长、风格、预算与路线
冻结成 `ProductionBrief`；needs_extension 的题目以程序图形替代时会记录 `substitutions`，
不会声称已实现该能力。