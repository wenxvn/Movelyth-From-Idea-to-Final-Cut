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

## 2. 已实现并验证（V1/V2）

| 能力 | 位置 | 证据 |
| --- | --- | --- |
| 统一检查结果与交付决定（pass/fail/unknown/not_applicable × critical/major/minor） | `policy.py` | A2 |
| 交付包绑定组成清单、revision 与决定；篡改/旧 revision/重生成音频都判失效 | `pipeline.build_composition`/`manifest_report` | A3 |
| 编导前抓取来源并逐条核对主张（节选必须能在正文中定位） | `sources.py`、`evidence` 阶段 | A4 |
| 冻结 production brief（受众/问题/边界/画幅/预算/路线）与能力路由 | `brief.py`、`capability.py` | A5 |
| Scene DSL v2：语义事件、subject 身份、统一时钟、迁移规则 | `models.py`、`scenedsl.resolve_events`、`clock.py` | A6 |
| 预算门、逐阶段运行记录、配置严格校验 | `budget.py`、`validate_settings` | A7 |
| 6 个镜头配方（图表聚焦/同尺度对照/参数过程/流程展开/纸面证据/结论回扣） | `recipes.py` | A8 |
| 布局 dry-run、整片草片（带真实混音）、草片与成片一致性 | `animatic.py`、`render.mjs` | A9 |
| 内容绑定相机（overview → focus → overview，横竖分别求解） | `camera.py`、`motion.cameraFromPlan` | A10 |
| 受控参数函数（迭代/线性变换/投影），数字与几何同源 | `parameters.py` | A11 |
| 缺陷路由的最小修复（9 类缺陷，各自失效范围与轮次） | `repair.py` | A12 |
| 场景缓存键（含邻镜）、失效闭包、组装与编码核对 | `cache.py` | A13 |
| 素材请求/匹配/授权/裁切（本地库） | `assetplan.py` | A14 |
| 语音设置、读法单位、独立内容核对（符号/量级不可折叠） | `speech.py`、`audioqc.content_check` | A15 |
| 真实字体度量、缺字检测、字幕/SRT 同源、字幕带冲突 | `fonts.py`、`captions_qc.py` | A16 |
| 可审计分轨、事件落点、尾音、抽吸、分轨平衡 | `mix.py` | A17 |
| 同拓扑几何形变、共享对象连续性 | `continuity.py` | A18 |
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
| 真实题目 V4（S2-10、S2-11、S4-02） | 本机无模型端点（`codex` 缺失、无 API Key），无法跑真实研究/编导/审片 |
| 主观对照与理解题（S4-01、S4-02、S4-05） | 需要 3–5 名目标受众；本轮只交付可盲评材料与自评时间点 |
| 真实 TTS 与 ASR 复核（S2-02 的 V2 部分） | 本轮未联网重跑合成与识别；读法核对逻辑已用离线样例验证 |
| 整片实听与手机外放/耳机/单声道 | 需要人耳（V5） |
| 平台反馈数据（S4-05） | 需要真实投稿与已授权接口 |

## 5. 已知限制（写在报告里，不隐藏）

1. 渲染仍是**整 cut 一次渲染**；缓存粒度到阶段与场景键，不是逐镜 mp4。
2. 转场是 overlay 语义（不扣帧）；没有实现真正的 transition handle 扣帧与旁白重排。
3. 相机只有 overview/focus 两种模式；`follow`、`reframe` 未实现。
4. 草片与成片一致性用 ffprobe（时长/帧数/音轨）证明，接点黑帧采样未接 ffmpeg 逐帧。
5. 视觉审片的“降级”只在能对程序生成刻度做确定性核对时发生；真实模型下的降级率未测。
6. 平台 AI 声明只提供草稿，勾选仍由用户完成；`ready` 不等于 `published`。
