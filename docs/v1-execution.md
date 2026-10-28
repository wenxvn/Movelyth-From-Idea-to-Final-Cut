# V1 执行记录

> **历史记录（V1 执行，2026-10-26）**：本文件记录当时的条件、结果与未完成项。当前状态与能力边界见 [optimization/execution.md](optimization/execution.md) 与 [optimization/capabilities.md](optimization/capabilities.md)，最新验证数字见 [verification.md](verification.md)。

按《Movelyth V1 规划与执行提纲》执行。**验证类型严格区分**：mock / 单元 / 静帧 / 片段 /
真实长短版 / 人工完整观看。命令与结果的完整证据在 [验证记录](verification.md)，
跨题材结论在 [V1 验收](v1-evaluation.md)，最终状态在 [V1 报告](v1-report.md)。

## 任务状态

| Task | 内容 | 状态 | 主要证据 |
|---|---|---|---|
| P0-01 | 基线、回归保护、阶段成本 | 完成 | `docs/v1-baseline.md`、`workspace/metrics.csv` |
| P0-02 | 标题 → 可选 brief，意图隔离 | 完成 | `test_title_only_and_brief_have_separate_intents` 等 3 项 |
| P0-03 | 版本化 Scene DSL v1 | 完成 | `tests/test_scenedsl.py`、`docs/scene-dsl.md` |
| P0-04 | 可组合画面、3 布局、3 风格 | 完成 | `tests/test_render_smoke.py`（横竖 10 张真实静帧） |
| P0-05 | 以实际配音为准的节拍 | 完成 | 真实 TTS 词语边界 + 时间轴校验测试 |
| P0-06 | 审稿与事实/视觉一致性 | 完成 | `consistency.py` + 3 项反例测试 |
| P0-07 | 故事板预览、局部修订、按 cut 复用 | 完成 | `preview`/`revise` 测试 + 真实 `cut_cached` 实测 |
| P0-08 | 音频质检（可选 ASR、静音、混音比） | 完成 | `tests/test_audioqc.py` + VID-000008 真实 ASR |
| P0-09 | 来源抓取安全边界 | 完成 | `tests/test_sources.py` 15 项 |
| P0-10 | 三题材真实验收 | 完成 | VID-000002 / 000003 / 000004 |
| P1-01 | 组件元数据、CSV 数据、折线/时间线 | 完成 | `tests/test_components.py`、`movelyth components` |
| P1-02 | 三套风格 | 完成 | `theme.ts` + 静帧 |
| P1-03 | 本地素材库与授权 | 完成 | `tests/test_assets.py` 9 项 |
| P1-04 | 按镜头局部修改 | 部分 | `revise` 完成；**无前后对比预览与变更记录** |
| P1-05 | 模型后端抽象 | 部分 | provider 协议 + mock；**未接第二家真实后端** |
| P1-06 | 低成本稳定性与性能 | 部分 | `--reuse-script`、画布自适应、metrics；**未测内存/CPU** |
| P1-07 | 发布包改进 | 完成 | `publish.py`、`交付审计.md`、封面专用构图 |
| P1-08 | CI 与测试分层 | 部分 | 工作流已提交；**未在 GitHub 实际运行** |
| P1-09 | 六主题回归集 | 部分 | 六题输入已固化；**T04–T06 未执行** |
| P2-01 | `suggest` / `daily` 选题模式 | 完成 | `tests/test_suggest.py` + 真实 `suggest` |
| P2-02～04 | 工作台 / 队列 / 反馈策略 | 未实施 | 提纲要求 P0/P1 稳定后再做 |

## 关键实现要点

- **brief 与标题都是数据**：`normalize_brief()` 限 4000 字、去控制字符；brief hash 并入意图判定，
  同题不同 brief 不复用旧成片；只有标题时沿用历史 intent（旧任务继续复用）。
- **DSL 单一来源**：`scenedsl.py` 定义布局矩形、保留区、容量估算与节拍解析，并生成
  `studio/src/generated/{layout,scene-schema}.json`；测试比对 Python 契约、已提交生成文件、
  TypeScript 枚举与渲染器注册表，任一侧漂移即失败。
- **每镜必须有真实画面**：只有 text + math 的镜头视为"动态字幕"并拒绝脚本。
- **区域互不重叠**：图表/图示/时间线/程序动画只能放 `main`（compare 可 `main` + `side`）。
- **节拍绑定真实配音**：`narration:片段` 按 TTS 词语边界换算成秒；片段不在旁白中时
  在脚本审批阶段就失败，不会等到付费配音之后。
- **契约变更使缓存脚本失效**：`scenedsl/consistency/quality` 的 hash 计入 script 阶段输入；
  校验失败转成可修复的编辑反馈重新生成，不会把失效脚本直接送去渲染。
- **分 cut 生成**：整部 Film 会触发 `max_output_tokens`，long/short 各调用一次再组装。
- **审片抽帧时机**：取该镜最后一个动作结束之后，避免抽到半成品画面造成误判。
- **来源安全**：仅 HTTPS/443，DNS 解析后固定到已校验公网 IP，逐跳校验重定向，
  成功缓存 30 天、失败 6 小时；网页正文始终是数据。
- **素材可追溯**：`asset-add` 记录 hash/来源/作者/许可/范围/引用任务/有效性；
  渲染前校验 hash 与 `valid`，失效即拒绝，不会静默替换。

## 真实成片暴露并已修复的缺陷

1. 视觉审稿拒绝时 `Finding` 不可 JSON 序列化。
2. 脚本被拒后 `resume` 静默重生成同样脚本 → 现写入 `script-feedback.json` 并在下次继续反馈。
3. 缓存中的"已审脚本"在契约变更后仍被复用 → 现纳入契约 hash 并转成编辑反馈。
4. 公式/矩阵被压成一行、字号过小 → 数学图层放大并保留换行。
5. `shape.line` 只画第一段 → 按全部顶点画折线，`connect` 加起点与箭头。
6. 不同图层占同一区域互相遮挡 → 区域改为互不重叠并在审批阶段拒绝。
7. 图表末值 0 仍显示柱高 → 从 0 基线绘制。
8. 封装框内无文字 → `rect` 支持框内自动放大文字。
9. 图例压住首值标签 → 图例独占顶部带；柱状图标系列名与数值。
10. 竖版图表被留白压小 → 画布按区域宽高比生成。
11. 流程图的重复小字 → 与节点标签重复的 `steps` 不再绘制。

## 已知未验证 / 风险

- **人工完整观看与实听未执行**：三个真实交付包的 `human_review` 均为 `false`。
- 每个真实题材只做一条，未验证同题多次的稳定性。
- `revise` 仍重渲染整条 cut（按 cut 复用，未做单镜重编码）。
- ASR 默认关闭（首次加载模型约 2 分钟）；三个真实成片 `asr_checked=false`。
- CI 未在 GitHub 实际运行；只在 Windows 验证。
- 字体容量按字符数估算，没有真实字体测量；无专门的裁切回归测试。
- 交付包只带 `原声`/`混音` MP3 便于试听，不含分轨工程。
