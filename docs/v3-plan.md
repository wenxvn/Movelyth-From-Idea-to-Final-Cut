# V3 方案：从“专业的画面”到“专业的讲述”

> **历史记录（V3 方案，2026-10-27）**：本文件记录当时的条件、结果与未完成项。当前状态与能力边界见 [optimization/execution.md](optimization/execution.md) 与 [optimization/capabilities.md](optimization/capabilities.md)，最新验证数字见 [verification.md](verification.md)。

> 实施状态见文末 §5；实测对照见 [v3-evaluation.md](v3-evaluation.md)。

日期：2026-10-27。对象：`main` @ `22237b5`（V2 已交付同一脚本的 A/B）。
本文只记录**审计证据、外部参考、排序与本轮取舍**；未验证的项目明确标注。

## 0. 审计方法与证据

| 手段 | 覆盖 |
|---|---|
| 读源码 | `media.py` / `scenedsl.py` / `quality.py` / `pipeline.py` / `studio/src/**` 全部 |
| 看 V2 成片 | VID-000015 横版，3 / 21 / 70 / 130 / 200 s 原生分辨率抽帧 |
| 读 V2 质量报告 | `workspace/VID-000015/quality.json`、`timelines.json` |
| 读 V2 交付 | `delivery-ab/待上传/VID-000015_*/r011/` |
| 读 references | Remotion 4.0.538、remotion-skill、MoneyPrinterTurbo、Lunamos paper2video |
| 外部调研 | anything2explainer、OpenMontage、AdForge、remotion-ad-video-skill、Qwen3-TTS、IndexTTS、Qwen3-ForcedAligner、AudioLDM2、AudioSFX、cutroom、PySceneDetect |
| 机器指标 | 现有 `quality.json`、运动分析、响度、混音/原声比 |

**未执行**：真实 Codex 编导（本机无 `codex`），因此本轮的“新成片”仍是**同一份已审脚本**
换 V3 渲染与 V3 声音。脚本层面的 prompt / 字段 / 叙事检查只做实现与离线测试，
不冒充真实模型采纳率。人工观看与实听仍标注为未做。

## 1. V2 仍然不够专业的地方（按观感排序）

### 1.1 构图：画面“空、小、暗”，没有主角

| # | 缺陷 | 证据 |
|---|---|---|
| C1 | 画面主体太小：1920×1080 里图表的绘图区只有约 1100×380，主体高度不到画面 1/3 | `v2-70.jpg`、`v2-130.jpg` |
| C2 | 左栏标题 + 3 条标签之后有约 400×500 px 的空区，画面重心偏右上 | `v2-70.jpg`、`v2-200.jpg` |
| C3 | 图表是“放在右栏的一张卡”，不是叙事主角；没有注释、没有指向、没有“当前要看哪里” | `v2-70.jpg` |
| C4 | 所有元素同一亮度、同一层级；没有主光、没有景深、没有前后景 | 全部 V2 帧 |
| C5 | 标签是“左侧竖线 + 文字”，重复且低信息量；没有 chip、编号、图标或语义色 | 全部 V2 帧 |
| C6 | 字幕 46 px（约画面高 4.3%），而同类解说片 720p 用 44 px（约 6.1%）；手机上偏小 | `Movie.tsx` `theme.type.caption` |
| C7 | 封面是“标题 + 右侧视觉”，与正文没有共同的光影语言 | `cover.png` |

### 1.2 动画：只有“入场”，没有“讲述中的动作”

| # | 缺陷 | 证据 |
|---|---|---|
| M1 | 9 个镜头 24.5–28.2 s，几乎等长；每个镜头只有 2 个 action（全片 18 个） | `pacing.long` |
| M2 | 镜头内只有 2–4% 的线性推拉；没有“说到第二个节拍时推近主角”的运镜 | `motion.ts` `cameraFor` |
| M3 | 元素入场后就静止；图表画完后没有持续动作（扫描、脉冲、数据点移动） | `v2-70.jpg` 与 `actions` |
| M4 | 转场固定 0.40–0.52 s，类型与内容无关；没有声音先入（J-cut） | `Movie.tsx` `TRANSITION_SECONDS` |
| M5 | 没有“高光时刻”（主角登场、结论落地、数字量级）；每镜同一个模板 | 全部 V2 帧 |
| M6 | 没有节拍级重构图：一镜到底一张版式，观众 25 秒看同一构图 | `Movie.tsx` |

### 1.3 图表：能读，但不“讲数据”

| # | 缺陷 | 证据 |
|---|---|---|
| D1 | 只有首末值/当前点标签，没有“最低点、拐点、目标线、区间”的注释 | `v2-70.jpg` |
| D2 | 曲线没有“当前关注点”的持续脉冲；画完后是一条静态线 | `v2-70.jpg` |
| D3 | 柱状图没有差值括号/基线强调；散点没有“这个点为什么重要”的说明 | `v2-130.jpg` |
| D4 | 刻度/轴标题字号偏小（约 24/1920），投屏和手机都吃力 | `v2-70.jpg` |

### 1.4 声音：从“念稿”进了一步，但仍像“一条人声 + 一条循环”

| # | 缺陷 | 证据 |
|---|---|---|
| A1 | 句内只有一个 rate/pitch；逗号处的停顿由引擎决定，不是表演 | `prosody_plan` |
| A2 | 重点词只在整句放慢 7%，没有词级强调；问句只抬 2 Hz | `prosody_plan` |
| A3 | 全片只有 9 个音效（1 impact + 8 whoosh），2.33/min；与画线、数字、节点无关 | `sound_design.long` |
| A4 | 配乐是“分段循环”，没有随旁白能量/场景角色变化；没有 riser、drop、breakdown | `_music_bed` |
| A5 | 没有混响/空间感；人声干、音效贴脸；立体声几乎相同 | `soundtrack` |
| A6 | 转场音效不提前，画面切了才响；没有 J-cut/L-cut | `prepare_cut` cues |
| A7 | 没有 room tone；句间是数字静音，听感“跳” | `narration.wav` |

### 1.5 叙事与节奏

| # | 缺陷 | 证据 |
|---|---|---|
| S1 | 镜头时长均匀是脚本层问题；V2 的 prompt 要求快慢对比，但没有真实模型验证 | `pacing.warnings` |
| S2 | 没有“每句一个可察觉变化”的约束；动作只要求“每镜至少一个” | `director.md` |
| S3 | 没有章节/角色/记忆点字段；模型无法表达“这一镜是钩子/机制/转折/收束” | `models.Scene` |
| S4 | 没有叙事质量检查（钩子、主线、术语解释、结尾回扣、句子节奏） | `quality.py` |
| S5 | 没有“高光时刻”预算；所有镜头同权重 | `director.md` |

## 2. 外部参考：借什么，不借什么

| 项目 | 可借 | 不借 / 限制 |
|---|---|---|
| **anything2explainer** | “一个主角 + 光 + 高光时刻”的构图规则；动效词汇表（SoftIn/GlitchIn/LightSweep/CameraRig）；“每个字幕块一个持续动作”；“末拍落位后停 30–45 帧”；帧级 QC（主体尺度/空场/柔光） | PolyForm Noncommercial；1280×720 单画幅；生成式代码不适合 Movelyth 的受控 DSL |
| **OpenMontage** | 管线/阶段/交付契约；reference video analyst；音乐库优先于生成；运镜与转场作为硬需求 | AGPL-3.0；大量外部生成服务；不适合直接 vendoring |
| **AdForge / remotion-ad-video-skill** | BPM/节拍网格；合成 SFX（numpy）；“少而软”的音效；每个修复用帧证明；一两个视觉母题贯穿 | 广告节奏/品牌片结构不能直接套科普 |
| **Remotion** | `interpolate`/`spring`/`Easing`；`TransitionSeries`；audio visualization；`@remotion/media-utils`；帧确定性 | 不引入重型依赖；保持当前 4.0.538 |
| **remotion-skill** | 纯函数、按帧动画、渲染验证 | — |
| **MoneyPrinterTurbo** | Edge TTS + word boundary + 字幕对齐；多 TTS provider 的接口思路 | 素材拼接型视频，不是程序动画 |
| **Qwen3-TTS / IndexTTS** | instruction/emotion、音色设计、零样本克隆；句级/词级情绪控制 | 需要 GPU/数 GB 权重；本轮不下载、不自动启用付费 API |
| **Qwen3-ForcedAligner** | 更准的词级对齐 | Edge 已给逐词边界；收益不抵 0.6B 部署成本 |
| **AudioLDM2 / AudioSFX** | 文本/视频生成音效、环境底声 | CC BY-NC / 体积 / GPU；本轮继续程序合成 |
| **cutroom / PySceneDetect** | 先记录再剪辑；“每个剪辑有依据” | 针对实拍素材；Movelyth 是程序动画 |
| **narration-guidance** | 处境开场、一条主线、动机先于机制、数字可感、结尾回扣 | 作为 prompt 与离线检查的依据 |

## 3. 方案（按 P0/P1/P2）

排序原则：先修“每一帧都看得见”的构图/主角/图表，再修“每一秒都听得见”的配音/配乐/音效，
最后才是需要真实模型验证的叙事字段与生成式能力。不引入新的付费服务，不引入重型依赖。

### P0（本轮实施，决定成片观感）

| ID | 内容 | 验收 |
|---|---|---|
| **P0-1 构图 3.0** | 12 列栅格重排：横版主画面 1164×750（原 1024×660），竖版 1000×760；标题 110–120 px；标签改 chip；新增 **Insight Card**（大数字/关键词 + 一句解释）填充左栏空区；封面重做 | 同脚本重渲染，主体高度 ≥ 画面 1/3；左栏空区显著减少 |
| **P0-2 图表 3.0** | 绘图区占满 main；刻度/轴标题/图例字号 +30%；**按节拍自动注释**（起点/最低点/终点/标记点）；注释点脉冲、引导线、区间高亮；柱状图差值/基线；散点重点 | 全部 V2 图表帧重渲染；注释不重叠；数值与数据一致 |
| **P0-3 动效 3.0** | 按字幕句/节拍把长镜切成 2–4 个 **coverage beat**：每个 beat 重选 Insight、推近/拉远/平移主角、点亮当前注释、持续扫描/脉冲；进入/离场分层；转场时长自适应 + 声音提前 | 每镜至少 1 个持续动作；最长静止 < 3 s；运镜 4–8 次/分钟 |
| **P0-4 声音 3.0** | 句内 clause 级韵律；重点词单独放慢/加响；句末降速；room tone；**自动音效设计**（动作/转场/重点词/注释/结论）；8 种新 SFX；配乐随旁白能量分段落；混响/立体声/总线 | 音效 ≥ 8/min 且类型 ≥ 4；转场音效提前 0.2 s；混音/原声比 < 1.6 |
| **P0-5 字幕 3.0** | 字幕 64–68 px、两行、底部渐变 scrim、逐词高亮 + 当前词轻底色；页间 0.12 s 交叉 | 手机竖屏可读；不压内容 |
| **P0-6 质量与对照** | 帧级 `composition_report`（主体高度/内容占比/空区）；`motion_report` 增加每句覆盖与最长静止；`sound_design` 增加事件/同步/类型；V2/V3 同脚本 A/B | 指标可复现；报告区分“机器通过”与“人工未看/未听” |

### P1（本轮部分实施；需真实模型验证的标注）

| ID | 内容 | 状态 |
|---|---|---|
| P1-1 | DSL 新增有界字段：`chapter` / `role` / `takeaway` / `metric` / `hero` / `layer.annotations` / `layer.highlight`，全部有默认值 | 实施 |
| P1-2 | 编导 prompt 增加“每句一个变化”、高光时刻预算、章节/角色、数据注释、音效与画面同锚点 | 实施（无真实模型验证） |
| P1-3 | 离线叙事检查：钩子、句子长度方差、术语先解释后命名、结尾回扣、报幕句、每镜动作/节拍覆盖 | 实施（警告为主） |
| P1-4 | 章节卡/章节导航（不增加时长，叠在转场上） | 记录，未实施 |
| P1-5 | 单镜重渲染 | 未实施（仍是整片渲染） |
| P1-6 | 可选本地 TTS provider（Qwen3-TTS / IndexTTS）接口与文档 | 记录，未实施（无权重/GPU 预算） |

### P2（记录，不在本轮）

- 外部素材/B-roll 检索与授权（OpenMontage asset ranking）。
- 生成式音效/环境声（AudioLDM2 / AudioSFX，许可与 GPU 成本）。
- 强制对齐（Qwen3-ForcedAligner）替换 Edge 词边界。
- 真实生成式视频/3D/数字人。
- 自动剪辑 EDL + 多轨时间线编辑器。

## 4. 验收方式

1. `pytest -q`、`ruff`、`tsc --noEmit`。
2. 同脚本 A/B：`tools/ab/make_film.py` 派生脚本 → V3 流水线 → 同一批时间点抽帧。
3. 帧级指标：主体高度、内容占比、空区、字幕字号、注释数量、最长静止、每句覆盖。
4. 音频指标：响度/真峰值、混音/原声比、音效密度/类型/同步偏移、句间停顿、句级响度差。
5. 主观检查：逐帧看图；**人工实听仍标注未做**。不把“机器检查通过”写成“观感专业”。

## 5. 实施状态（2026-10-27 收尾）

| ID | 状态 | 落地位置 | 证据 |
|---|---|---|---|
| P0-1 构图 3.0 | 完成 | `scenedsl.LAYOUTS`/`HEADING_BANDS`/`INSIGHT_BANDS`、`studio/src/Movie.tsx`、`theme.ts` | 主体高度 0.206 → 0.556 |
| P0-2 图表 3.0 | 完成 | `components/ChartLayer.tsx`、`insights.ts`、`models.Annotation` | 注释/区间/差值/图名面板 |
| P0-3 动效 3.0 | 完成 | `insights.sceneBeats`、`motion.cameraFor`、`Stage.tsx` | 36 个 beat，静止 4.3% → 2.4% |
| P0-4 声音 3.0 | 完成 | `sound.py`（新）、`media.prosody_segments` | 41 个事件、10 类；混音比 1.17 |
| P0-5 字幕 3.0 | 完成 | `Movie.tsx`、`CAPTION_BANDS` | 66 px + 渐变 scrim |
| P0-6 质量与对照 | 完成 | `craft.py`（新）、`pipeline.check`、`tools/ab/make_film_v3.py` | `composition`/`rhythm`/`sound_design` |
| P1-1 DSL 字段 | 完成 | `models.Scene`/`Layer` | 全部有默认值，旧脚本原样渲染 |
| P1-2 编导 prompt | 完成（未验证） | `prompts/director.md` | 需真实模型 |
| P1-3 离线叙事检查 | 完成 | `craft.narrative_report` | 报幕、句长、role、回扣、动作数 |
| P1-4 章节卡 | 未做 | — | 章节名只出现在镜号旁 |
| P1-5 单镜重渲染 | 未做 | — | 仍是整片渲染 |
| P1-6 本地 TTS 接口 | 未做 | — | 见 §2 取舍 |

**未完成且必须如实标注**：真实 Codex 端到端、人工观看、人工实听。三者都不在本轮机器指标里。
