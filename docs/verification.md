# 验证记录

本文件只保留**当前**可复核的验证状态与历史的关键证据；每版的详细分析在
[v1-execution](v1-execution.md)、[v2-evaluation](v2-evaluation.md)、[v3-evaluation](v3-evaluation.md)，
逐项验收证据在 [optimization/acceptance.md](optimization/acceptance.md)。

## 当前状态（2026-10-28，第二版提纲）

### 验证分层

| 层级 | 内容 | 能支持的结论 |
| --- | --- | --- |
| V1 离线逻辑 | 契约、策略、状态、故障注入、缓存 | 给定输入下程序行为正确 |
| V2 小型真实媒体 | 字体、编码、动态帧、音频与同步 | 指定媒体机制实际工作 |
| V3 导入脚本制作 | 固定 film/research → 真实渲染与检查 | 当前实现能制作该脚本 |
| V4 真实题目制作 | 不导入脚本的标题驱动链路 | 固定条件下标题驱动链路工作 |
| V5 实际看听 | 完整观看、实听、内容问题与时间点 | 指定评估者对指定版本的观察 |

V1/V3/mock 不能替代 V4；静帧不能证明运动；对齐不能证明没有漏读；响度不能证明自然度。

### 本轮实际运行

```text
pytest -q -m "not slow and not live"   → 509 passed, 5 deselected
pytest -q -m slow                      → 5 passed
ruff check src tests                   → All checks passed
npm --prefix studio run typecheck      → 通过
movelyth schema / components / capabilities / doctor → 可运行，输出可解析 JSON
契约生成 git diff studio/src/generated → 无差异
```

`-m slow` 的五项都是真实 Remotion 渲染（Chrome + 4.0.538）：图层组合静帧、相机焦点帧差
（平均 8.86）、几何形变帧差（>0.5% 像素）、圈注两次渲染逐字节一致、换 seed 后画面不同。

| 覆盖 | 层级 |
| --- | --- |
| 交付决定、组成清单、主张核对、能力路由、DSL v2、预算与运行记录 | V1 |
| 配方、参数函数、缺陷路由修复、缓存键与组装、素材裁切、语音读法、字体与字幕、混音分轨、形变、圈注、故障矩阵、状态摘要、反馈 | V1（含真实图片与真实编码探针） |
| 真实渲染（静帧/草片/相机/形变/圈注确定性）、ffprobe 编码核对 | V2 |
| 真实题目（V4）、人群对照（V5） | **未做**：本机无模型端点，且无目标受众样本 |

### 不能由本轮结果推出的结论

任何“更自然/更易懂”的主观判断、真实模型下的采纳率、平台数据表现。
`ready` 不等于 `published`；抽帧审片不等于完整看听。相关阻塞与所需条件见
[optimization/capabilities.md](optimization/capabilities.md) §4。

## 历史记录（关键证据）

| 时间 | 版本 | 关键结果 | 详细 |
| --- | --- | --- | --- |
| 2026-10-25 | 首版 0.1.0 | 22 项测试；VID-000001 真实端到端（209.9 s / 62.8 s） | [v1-baseline](v1-baseline.md) |
| 2026-10-26 | V1 | 三题真实成片通过（矩阵 / 网络消息 / 梯度下降）；真实抽帧暴露并修复 11 个渲染缺陷 | [v1-execution](v1-execution.md)、[v1-report](v1-report.md) |
| 2026-10-26 | 质检与排版 | 两遍响度（-14 LUFS）、逐镜运动分析、发音与字幕分离、中文排版、术语核对 | [v1-evaluation](v1-evaluation.md) |
| 2026-10-27 | 真实弱模型 | DeepSeek 端到端跑到视觉审片，被真实内容缺陷拒收（重复论证、数轴缺刻度） | 见下 |
| 2026-10-27 | V2 | 同一脚本重渲染：构图/图表/转场/字幕重做，句级韵律与分段配乐 | [v2-evaluation](v2-evaluation.md) |
| 2026-10-27 | V3 | 主体高度 21% → 53%，空白网格 44% → 27%，音效 9 → 41 个 | [v3-evaluation](v3-evaluation.md) |
| 2026-10-28 | 第二版提纲 | 22 个工作包实现并验收；真实题目与人群对照仍阻塞 | [optimization/](optimization/execution.md) |

### 真实弱模型端到端（唯一一次真实模型 + 真实 TTS + 真实渲染）

`movelyth probe`：`reachable=true`、`json_output=true`、`vision=true`。
research / script / sound / render / check 全部通过；横版 152.9 s、竖版 62.8 s，均 -14.4 LUFS，
13 项技术检查通过。**视觉审片拒收**（l5/l6 重复论证、l1 数轴未标刻度），未产出交付包——
这是内容缺陷而非程序缺陷，也是“机器检查通过 ≠ 可以交付”的直接证据。

`json_schema` 在 DeepSeek 官方端点返回 400，自动降级到 `json_object`；该降级按进程记忆。
`deepseek-flash` 在 8 镜结构里 12 轮修复仍未收敛到 0 项契约错误：弱模型可用但需要更多轮次。

### 真实 ASR 与成本（历史，mock 剧本）

- 真实 faster-whisper 转写用于核对术语与漏读；未开 ASR 时报告明确写“未检查”，不影响制作。
- 40 s + 15 s 双画幅的 mock 演示：全流程 1 次研究 + 2 次编导 + 1 次审稿调用；
  语音缓存命中后重跑不重复合成。费用字段在没有价格表时保持 `null`（第二版起）。
