# 能力矩阵与最终声明（第二版提纲）

> 依据：本轮实际代码与运行结果（`docs/optimization/acceptance.md`）。未实现、未验证的部分
> 单列，不并入“已支持”。`movelyth capabilities` 输出同一份数据的机器可读版本。

## 1. 题材路线

| 路线 | 状态 | 含义 | 证据 |
| --- | --- | --- | --- |
| program-graphics | **supported** | 程序图形（text/math/shape/chart/diagram/timeline/image/procedural + 配方） | `capability.py`、`recipes.py`、真实渲染 smoke |
| licensed-media | needs_extension | 本地已登记素材可检索/匹配/裁切；联网供应商未接入 | `assetplan.py`、A14 |
| generated-media | needs_extension | 生成式图像/视频默认关闭，未接受控工作流 | 无调用路径 |
| spatial-demo | needs_extension | 只有伪三维程序动画，无真三维模板 | 无 ThreeCanvas |
| real-footage | **unsupported** | 录屏/实拍/采访：管线无法真实呈现，`create` 前置拒绝 | `capability.classify_route`、M19 |

`needs_extension` 的题目可以继续制作，但 brief 会记录 `effective_route=program-graphics`
与“标注示意”，不会声称已实现该能力。

## 2. 已实现并验证（V1/V2 与 V4 增量）

| 能力 | 位置 | 证据 |
| --- | --- | --- |
| 统一检查结果与交付决定（pass/fail/unknown/not_applicable × critical/major/minor） | `policy.py` | A2 |
| 交付包绑定组成清单、revision 与决定；篡改/旧 revision/重生成音频都判失效 | `pipeline.build_composition`/`manifest_report` | A3 |
| 编导前抓取来源并逐条核对主张（节选必须能在正文中定位） | `sources.py`、`evidence` 阶段 | A4 |
| 冻结 production brief（受众/问题/边界/画幅/预算/路线）与能力路由 | `brief.py`、`capability.py` | A5 |
| Scene DSL v2：语义事件、subject 身份、统一时钟、迁移规则 | `models.py`、`scenedsl.resolve_events`、`clock.py` | A6 |
| 预算门、逐阶段运行记录、配置严格校验 | `budget.py`、`validate_settings` | A7 |
| 6 个镜头配方（语义条件、阶段/焦点、动态演示与失败例；编导提示按场景过滤） | `recipes.py`、`pipeline.py` | A8、N02 |
| 布局 dry-run、整片草片（带真实混音）、草片与成片一致性 | `animatic.py`、`render.mjs` | A9 |
| 对象几何相机（overview/focus/follow/reframe；命名 chart/diagram 目标，横竖分别求解） | `camera.py`、`motion.cameraFromPlan` | A10、N03 |
| 受控参数函数（迭代/线性变换/投影），数字与几何同源 | `parameters.py` | A11 |
| 缺陷路由的最小修复（9 类缺陷，各自失效范围与轮次） | `repair.py` | A12 |
| 场景缓存键（含邻镜）、失效闭包、组装与编码核对（ffprobe 解析统一在 `media.probe_media`） | `cache.py`、`media.py` | A13 |
| 素材请求/匹配/授权/裁切（本地库） | `assetplan.py` | A14 |
| 语音设置、读法单位、独立内容核对（符号/量级不可折叠） | `speech.py`、`audioqc.content_check` | A15 |
| 真实字体度量、缺字检测、字幕/SRT 同源、字幕带冲突（字幕阈值只在 `captions_qc` 定义） | `fonts.py`、`captions_qc.py` | A16 |
| 可审计分轨、事件落点、尾音、抽吸、分轨平衡（人声缺失在人声轨上判） | `mix.py`、`sound.soundtrack_stems` | A17 |
| 同拓扑几何形变、相邻场景共享对象状态/颜色审计（同场多层合并，保留图层证据） | `continuity.py` | A18、N04 |
| 统一动效令牌与风格时间参数（入场、停稳、相机、转场、强调） | `studio/src/theme.ts`、`studio/src/motion.ts` | N05 |
| 关联主张到可见图形的双向覆盖核对；缺少画面见证时保留 unknown | `policy.py` | N06 |
| 中文静音阅读、字幕速度与手机画面估算（项目启发式） | `captions_qc.py`、`policy.py` | N07 |
| 确定性手绘圈注（seed 决定几何，两次渲染逐字节一致） | `sketch.py`、`SketchOverlay.tsx` | A19 |
| 故障矩阵 M01–M20 | `tests/test_fault_matrix.py` | A20 |
| 一屏状态摘要与错误分类 | `report.py`、`status`/`capabilities` | A21 |

## 3. 未实现（增强 E，逐项标明）

| 编号 | 状态 | 说明 |
| --- | --- | --- |
| S3-04 代码/数据结构/有限公式模板 | **not_implemented** | 没有代码图层；公式只做 token 保留统计（`continuity.formula_correspondence`），不做跨镜公式形变 |
| S3-05 素材视频/证据面板 | **not_implemented** | image 图层只接受已登记静态素材，没有视频解码与源范围 |
| S3-06 PDF 可定位证据 | **not_implemented** | `sources.py` 只解析 HTML/纯文本，`ALLOWED_MIME` 不含 PDF |
| S3-07 三维/shader/生成后端 | **optional_deferred** | 需要 GPU/预算/许可；能力表标 needs_extension |
| S3-08 可编辑时间轴导出 | **optional_deferred** | 无 OTIO/剪辑软件适配；交付仍是 MP4 包 |

## 4. 未验证（需要外部条件）

| 项 | 阻塞原因 |
| --- | --- |
| 六题重复真实评测 V4（S4-02） | 已有两题真实标题基线；六题双跑冻结批次仍未开始 |
| 主观对照与理解题（S4-01、S4-02、S4-05） | 需要 3–5 名目标受众；本轮只交付可盲评材料与自评时间点 |
| 完整实听与 TTS A/B 感受（S2-02 的 V2 部分） | 已对 VID-000040 最终 AAC 运行 ASR，并生成同稿 A/B；需要人耳判断发音、停顿与自然度 |
| 整片实听与手机外放/耳机/单声道 | 需要人耳（V5） |
| 平台反馈数据（S4-05） | 需要真实投稿与已授权接口 |

## 5. 已知限制（写在报告里，不隐藏）

1. 渲染仍是**整 cut 一次渲染**；缓存粒度到阶段与场景键，不是逐镜 mp4。
2. 转场是 overlay 语义（不扣帧）；没有实现真正的 transition handle 扣帧与旁白重排。
3. 相机已支持 overview/focus/follow/reframe，但只覆盖已有命名 chart/diagram 几何；对象 ID 的语义正确性和跨镜画面清晰度仍需审片。
4. 草片与成片一致性用 ffprobe（时长/帧数/音轨）证明，接点黑帧采样未接 ffmpeg 逐帧。
5. 视觉审片的“降级”只在能对程序生成刻度做确定性核对时发生；真实模型下的降级率未测。
6. 平台 AI 声明只提供草稿，勾选仍由用户完成；`ready` 不等于 `published`。
7. 连续性审计只处理显式 `subject_id` 的直接相邻场景，并以场景主视觉表示作比较；它不判断隐喻是否清楚，也不代替成片接点审查。

## 6. V4 跨平台参考提纲执行状态（2026-10-30）

| 工作包 | 当前证据 | 限制/后续 |
| --- | --- | --- |
| N01 两题标题驱动基线 | `VID-000040` r007 policy v3、manifest 有效；`VID-000035` r003 原包仍为 policy v2，当前检查器因版本不匹配判为无效。其既有证据按 v3 只读重算为 ready（48 pass、0 fail、15 optional unknown、2 N/A） | 未新建或重写 `VID-000035` revision；六题重复评测未开始 |
| N02–N07 配方、对象相机、连续性、动效、内容覆盖、中文可读性 | 代码与聚焦回归通过；对象接力和三风格对照有真实 Remotion 预览 | 三风格只检查抽样帧，未做完整动态观众对比；连续性审计仍报告两题脚本的状态/身份问题 |
| N08–N09 音频接缝与语义段 A/B | 真实 AAC 场景接点窗口测量；Edge TTS 同稿 A/B 与 faster-whisper ASR 已保存 | 测量不能证明无点击声或自然度；ASR 需人工复听，A/B 不选胜者 |
| N10–N13 扩展能力、逐镜导出、捕获方式、可选三维 | 维持未实现/延后；两题无需素材视频、PDF、代码执行或三维资产 | 逐镜 MP4 未实现；Windows 本轮未执行共享内存捕获对照；真三维/生成式能力不进入默认路线 |
