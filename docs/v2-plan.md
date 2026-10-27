# V2 方案：从"能自动出片"到"像专业团队做的片"

日期：2026-10-27。对象：`main` @ `1d18c59`（V1 已完成三题材双画幅验收）。
本文档只记录**本轮审计发现的真实问题、证据位置和排序**；未实施的项目明确标注。

## 0. 审计方法与证据

| 手段 | 覆盖 |
|---|---|
| 读源码 | `pipeline.py` / `media.py` / `quality.py` / `scenedsl.py` / `studio/src/**` 全部 |
| 看真实成片 | VID-000004 横版，按秒抽帧（3/9/30/45/70/95/120/150/175/200/230 s），放大局部 |
| 听真实混音 | `混音_B站_横版.mp3`、`原声_B站_横版.mp3` 波形与频谱（`ffmpeg ebur128` / `astats`） |
| 读运行数据 | `workspace/VID-000004/timelines.json`、`voice-cache/*/timing.json`、`metrics.csv` |
| 读参考实现 | `references/` 下 Remotion 官方 skills（transitions / effects / text-highlights / timing）、remotion-skill、Lunamos paper2video 的 verify 与 visual-style |
| 外部调研 | OpenMontage、anything2explainer、AdForge/remotion-ad-video-skill、MoneyPrinterTurbo、Qwen3-TTS/ForcedAligner、AudioLDM2、AudioSFX |

**未执行**：真实 Codex 编导（本机无 `codex` 可执行文件），因此本轮所有"新成片"都用
`--import-film` 复用 VID-000004 的**已审脚本**重渲染。这是有意的对照实验：脚本、配音文本不变，
只换渲染、转场、字幕与声音设计，差异归因清楚。

## 1. 真实缺陷清单（按观感影响排序）

### 1.1 构图与排版

| # | 缺陷 | 证据 |
|---|---|---|
| V1 | 横版左栏大面积空白：标题只占顶部一行，标签被推到 y≈690，中间 400px 空 | `b-3.jpg`、`f-70.png` |
| V2 | 字号偏小：1920 宽标题 58px、标签 27px。Remotion 官方版式建议 1080 宽主标题 84px，等比到 1920 应 ≈150px | `Movie.tsx` `headingBase` |
| V3 | `immersive` 并没有真正"沉浸"：主画面仍是右侧 1200×480 的框，和 `diagram` 几乎一样 | `scenedsl.LAYOUTS` |
| V4 | 文字图层全部是"左侧竖线 + 半透明底"的同一种卡片，重复感强，层级不分明 | `TextLayer.tsx` |
| V5 | 封面固定第 45 帧、固定排版，与正文风格割裂 | `render.mjs` `frame: 45` |

### 1.2 图表（最刺眼）

| # | 缺陷 | 证据 |
|---|---|---|
| V6 | 刻度不是"整"数：`3.24 / 2.0 / 0.76`、`9.11 / 5.63 / 2.14 / 11.3`。专业图表必须用 1-2-5 取整 | `b-3.jpg`、`f-70.png` |
| V7 | 图例压在绘图区内，与折线首值标签、`source_note` 互相遮挡；橙色"当前点 w=0, L=5"直接压在图例上 | `f-70.png` |
| V8 | 二次函数用 8 个点的**折线**画出来，呈锯齿状，不是抛物线 | `f-70.png` |
| V9 | y 轴只画中间两个刻度，首末值缺失；轴标题塞在左下角小字 | `ChartLayer.tsx` |
| V10 | 散点/柱状没有零基线强调、没有面积填充、没有当前点高亮，视觉层次只有一条线 | `b-3.jpg` |

### 1.3 动画与转场

| # | 缺陷 | 证据 |
|---|---|---|
| V11 | 每镜入场都是"整体 opacity + 14px 上移"，没有分层节奏；长镜头（25–29 s）中段完全静止 | `motion.ts`、`Movie.tsx` |
| V12 | 场景之间是硬切 + 全屏淡入淡出到背景，机械；没有 crossfade/slide/wipe，没有 J/L cut | `Movie.tsx` `fade` |
| V13 | `draw` 动作在开始前就把 opacity 抬到 0.05，画面提前"透出"半成品 | `motion.ts` `hasEntrance` |
| V14 | `morph` 名不副实（淡入），且没有替代方案；模型被 prompt 劝阻使用后，可用动画只剩 7 种 | `scenedsl.layout_warnings` |

### 1.4 声音

| # | 缺陷 | 证据 |
|---|---|---|
| A1 | 全片一个语速、一个音高。Edge TTS 的 `rate/pitch/volume` 参数在 `voice()` 里恒定，句间只有固定 0.25 s 前导 + 0.85 s 尾部 | `media.py` `prepare_cut` |
| A2 | 音乐是 3 套正弦三和弦循环，每 8 秒换一个和弦，全片无段落（intro/body/outro）、无 riser、无转场音效 | `media.py` `soundtrack` |
| A3 | 音效只有"每镜开头一个和弦 accent"，与具体动作（画线、节点流动、数字跳动）无关 | 同上 |
| A4 | ducking 是 20 ms 窗的硬二值（0.32 / 0.9），会泵动；无 attack/release | 同上 |
| A5 | 混音无 EQ、无压缩；bed 左右声道几乎相同，没有立体声宽度 | `np.stack([... * 0.93])` |

### 1.5 字幕与叙事

| # | 缺陷 | 证据 |
|---|---|---|
| S1 | 整页字幕一次性出现，无逐词高亮、无关键词强调；字号 39/44 偏小 | `Movie.tsx` `captionSize` |
| S2 | 字幕只有一行（caption 区 100px），长句被切成很多短页，阅读节奏碎 | `media.captions` max_chars 25 |
| S3 | 编导 prompt 没有镜头语言（景别/运镜/转场/声音提示/强调词），模型只能产出"图表 + 文字" | `prompts/director.md` |
| S4 | 没有节奏约束：VID-000004 九个镜头 25.4–29.6 s，几乎等长，缺少快慢对比 | `timelines.json` |
| S5 | 没有跨镜连续性：每镜独立，元素不延续 | `Movie.tsx` |

### 1.6 工程缺陷（顺带修复）

- `quality.py` 的 `verify_video` 用 `fps=1` 采样算 `moving_picture`，25 s 长镜头里
  一次 0.4 s 的入场动画就足以让它通过，无法反映"中段静止"。V2 改为 2 fps 中位数 +
  静止采样占比。
- 字幕的 `words`（真实词边界）在 `media.captions` 里被丢弃，渲染端只能整页显示。

（初稿曾记录 `cli.py` 的 `--import-film` 分支引用未定义名字 `import_researrgs`；
核对 `git diff` 后确认该行原本就是正确的 `import_researrgs.import_research`，
是我读错，**不是缺陷**，已删除该条。）

## 2. 方案

排序原则：**先修"每一帧都看得见"的东西**（构图、图表、字幕），再修"每一秒都听得见"的东西
（配音韵律、音乐、音效），最后才是需要模型配合的叙事能力（prompt / DSL 扩展）。
不引入付费生成服务，不引入新依赖（沿用 numpy / Pillow / Edge TTS / Remotion）。

### P0（本轮实施，决定成片观感）

| ID | 内容 | 依据 |
|---|---|---|
| P0-1 | **构图系统重做**：12 列栅格 + 4 级字阶（display/heading/body/caption）；标题 92/78px 起；标签紧跟标题；`immersive` 改为真正的全幅底图 + 侧向 scrim；内容按语义顺序入画 | V1–V5；Remotion `video-layout.md` |
| P0-2 | **图表专业化**：1-2-5 nice ticks、单调三次插值平滑曲线、图例独立带、值标签碰撞避让、零基线、面积渐变、当前点高亮、轴标题规范化 | V6–V10 |
| P0-3 | **动效系统**：bezier/spring 缓动、分层 stagger、镜头微推（push-in）避免长镜静止、场景间 crossfade/slide/wipe/dip 转场、`draw` 提前透出修复 | V11–V14；Remotion `timing.md` |
| P0-4 | **声音设计**：句级韵律（按句给 rate/pitch/volume，标点处插入停顿，关键句放慢）、段落化配乐（intro/body/outro + 低音 + pad + 轻打击）、平滑 sidechain、程序合成 whoosh/tick/impact/riser、人声 EQ + 轻压缩 + 立体声宽度 | A1–A5 |
| P0-5 | **字幕**：逐词高亮（用真实 TTS 词边界）、关键词 accent 色、最多两行、字号加大、底部渐变压暗替代胶囊底 | S1–S2 |

### P1（本轮部分实施）

| ID | 内容 | 状态 |
|---|---|---|
| P1-1 | DSL 增加有界字段：`transition`、`camera`、`emphasis`、`cues`（声音提示），全部有默认值，旧脚本不变 | 实施 |
| P1-2 | 编导 prompt 增加镜头语言、节奏曲线、声音提示与强调词 | 实施（无真实模型可验证，标注） |
| P1-3 | 质量报告增加节奏/多样性/声音设计指标（cut 长度方差、视觉签名重复、cue 数、bed 与人声比） | 实施 |
| P1-4 | 对照实验可复现：`--import-film` 路径 + 机械修版（两个节点重叠） | 实施 |
| P1-5 | 单镜重渲染（避免整片重渲） | 未实施（需先解决转场重叠与音画对齐） |
| P1-6 | 真实 Codex 端到端重跑（新 prompt 的模型侧效果） | 未实施（本机无 codex） |

### P2（记录，不在本轮）

- 外部素材 / B-roll 检索与授权流水线（OpenMontage 的 asset ranking 思路）。
- 单镜重编码 + 增量合成。
- 用本地 TTS（Qwen3-TTS / IndexTTS）替换 Edge TTS：能给出情绪与音色控制，但需 GPU 与
  数 GB 权重，和"低成本、无 GPU 也能跑"的现有约束冲突，先留接口不落地。
- 强制对齐（Qwen3-ForcedAligner）替换 Edge 词边界：精度更高，但 Edge 已给出逐字边界，
  收益不足以抵消 0.6B 模型的部署成本。
- 生成式音效（AudioLDM2 / AudioSFX）：许可与体积成本高；本轮用程序合成覆盖 whoosh/tick/impact。

## 2.1 实施过程中新发现的缺陷（真实成片暴露）

| # | 缺陷 | 状态 |
|---|---|---|
| N1 | `wipe`/`slide` 只渲染当前镜，旧画面提前消失 → 实际是"黑底上揭开一块新画面" | 已修（双层合成 + 羽化遮罩） |
| N2 | 转场包装层没有 `position:absolute`，`clipPath` 把整镜裁成 0 高 → 使用 wipe 的镜头整段空白 | 已修（用真实帧定位） |
| N3 | `draw` 从 40% 处开始，柱子/图示在开头十秒完全空白 | 已修（结构化图形预揭示 45%，柱状图改为从基线生长） |
| N4 | 柱状图值标签被揭示遮罩裁掉；末柱贴边被切一半 | 已修（柱内标签 + 类别半槽留白） |
| N5 | 图表刻度非整（0.76/2.0/3.24），图例压在曲线上 | 已修（1-2-5 取整 + 图例独立带） |
| N6 | 常量序列被画成一条假的数据线（"当前点 L=5"） | 已修（识别为参考线/标记点） |
| N7 | 竖版 `bottom` 区被压到 34 px，公式放不下 → 导入脚本被判违约 | 已修（重排竖版栅格） |
| N8 | 向量/投影按 1000×640 画布letterbox，单位向量在画面上只有几十像素 | 已修（按内容与区域宽高比缩放） |
| N9 | `immersive` 与 `diagram` 布局几乎一样，没有"宽银幕" | 已修（全宽 hero 带 + 顶部压暗） |
| N10 | 字幕只有整页出现，词边界信息被丢弃 | 已修（词级时间进入 captions，卡拉 OK 高亮） |

## 3. 验收方式

1. `pytest -q`（含真实 Remotion 静帧 smoke）、`ruff`、`tsc --noEmit`。
2. **同脚本 A/B**：`--import-film` 重渲染 VID-000004，抽同一批时间点帧对比。
3. 机器指标：刻度整值、图例/标签不重叠（几何断言）、`motion_report` 的每镜 still 占比、
   响度/真峰值、bed 与人声能量比、cue 数量。
4. 主观检查：逐帧看图 + 实听混音；结论与限制写进 `docs/v2-evaluation.md`。
   不把"程序检查通过"写成"观感专业"。
