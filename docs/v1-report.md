# V1 交付报告

> 按《Movelyth V1 规划与执行提纲》§9 组织。结论都对应可核验证据；没有证据的地方写"未验证"。

## 1. 执行摘要

| 批次 | 任务 | 结果 |
|---|---|---|
| 准备 | 基线、回归保护、阶段成本 | 完成（`docs/v1-baseline.md`、`workspace/metrics.csv`） |
| A | P0-01 基线 / P0-02 brief / P0-03 Scene DSL v1 | 完成 |
| B | P0-04 可组合画面 / P0-05 声画节拍 / P0-06 审稿与一致性 | 完成 |
| C | P0-07 预览与局部修复 / P0-08 音频质检 / P0-09 来源安全 | 完成 |
| D | P0-10 三题材真实验收 | **完成**（T01/T02/T03 双画幅均通过） |
| E | P1-01/02/03/05/06/07/08/09 | 完成或部分完成（见 §7） |
| F | P2-01 `suggest`/`daily` | 完成（不自动定时） |
| F | P2-02～04 工作台 / 队列 / 反馈策略 | 未实施 |

未做的部分与原因见 §7；逐任务状态见 [V1 执行记录](v1-execution.md)。

## 2. 源码与文档

- **Scene DSL v1**：[scene-dsl.md](scene-dsl.md)。契约在 `src/movelyth/models.py` + `scenedsl.py`，
  渲染端类型在 `studio/src/types.ts`，生成的 `studio/src/generated/{layout,scene-schema}.json`
  入库并有漂移测试。
- **CLI**：`create`（含 `--brief-file/--preview/--plan-only/--new`）、`resume`（含 `--reuse-script`）、
  `preview`、`revise`、`status`、`ideas`、`suggest`、`daily`、`assets`、`asset-add`、`asset-check`、
  `schema`、`components`、`check`、`feedback`、`doctor`。
- **兼容/迁移**：旧库自动补 `brief/brief_hash`；旧脚本（只有 `visual`）自动退化为单个 procedural
  图层；旧交付目录不会被覆盖。
- **质量限制**：见 [architecture.md](architecture.md)、[verification.md](verification.md) 的验证边界。

## 3. 测试记录

```text
pytest -q                            → 111 passed
pytest -q -m "not slow"              → 110 passed, 1 deselected
pytest tests/test_render_smoke.py -q → 1 passed（真实 Remotion 静帧）
ruff check src tests                 → All checks passed
npm --prefix studio run typecheck    → 通过
```

分层：`unit`（默认）/ `slow`（真实渲染）/ `live`（真实模型或在线 TTS，未纳入自动测试）。
CI（`.github/workflows/ci.yml`）只跑 ruff + 非 slow 测试 + 契约漂移 + typecheck，不产生费用；
**GitHub 上的实际运行状态未知**（本机未执行 Actions）。

## 4. 可核验的输出

真实 Codex 制作（标题驱动，未导入脚本，每个 17 个文件）：

```text
delivery/待上传/VID-000002_矩阵为什么能让整个空间旋转？/r001/
delivery/待上传/VID-000003_一条网络消息如何从我的电脑到达服务器？/r001/
delivery/待上传/VID-000004_梯度下降为什么能让模型逐步减少错误？/r001/
```

横竖时长 242.6/64.8、218.9/67.2、242.6/69.5 秒；均 H.264/AAC、1920×1080 与 1080×1920、30 fps，
11 项技术检查通过，独立视觉审片 `passed=true`。代表帧在 `docs/v1-evaluation/`。

mock 剧本的链路验证任务（VID-000001/000005–000011）只用于验证预览、修订、ASR、素材、选题，
报告中统一标为 `mock-provider`，不作为创作能力证据。

## 5. 性能变化

| 阶段 | 首次（40 s + 15 s 双画幅） | 命中缓存 |
|---|---:|---:|
| research | 0.02 s（mock）/ 92.4 s（真实 Codex） | 0 s |
| script | 0.06 s（mock）/ 610.7 s（真实 Codex） | 0 s |
| sound | 23.4 s | 0.15–0.2 s |
| render | 90.5 s | 整体 `cut_cached` |
| check | 84.0 s | — |

同条件前后对比只对"22 项测试 → 111 项测试"有意义；渲染耗时随片长变化，没有同片长的
V0/V1 对照；**内存峰值未测量**，标为未知。

## 6. 变更索引

| 提交 | 内容 |
|---|---|
| `a308233` | Scene DSL v1 + 分层渲染器 + 契约/几何/静帧测试 |
| `e44cd65` | brief、预览、局部修订、音频质检、来源加固、provider 抽象 |
| `a01b12d` | 基线/执行/验收文档 + CI |
| `05e2a8e` | 平台发布包、封面专用构图、交付审计 |
| `9e4c164` | 真实本地 ASR 与覆盖率报告 |
| `3d56508` | 受控本地素材库（授权 + hash） |
| `1de109c` | 组件元数据、CSV 数据、折线路径、时间线图层 |
| `2912760` | 故事板携带真实时间轴与动作窗口 |
| `3ebdf98` | 每镜必须有真实画面图层；离线 `check`；审片抽帧时机 |
| `5f9fafa` | 真实成片暴露的缺陷修复（分 cut 生成、契约失效、一致性措辞、版式） |
| `ff4849d` | 三题材记录 |
| `a4f4c0e` / `1537307` | `--reuse-script`；图表画布按区域宽高比 |
| `c7209aa` | 第三个真实题材通过；图例带与柱状图数值 |
| `b4353f5` / `3e80021` | `suggest`/`daily` 选题模式 |

回归风险：渲染器重写（`Visual.tsx` → `components/`）是最大风险点，已用 8 种图层 × 横竖真实静帧
覆盖；旧任务兼容由 `test_legacy_scene_without_layers_still_renders_as_procedural` 与
VID-000001 的 `film.json` 解析验证。区域改为互不重叠后，旧的"同区域叠放"脚本会被拒绝，
这是有意的行为变化，已在 scene-dsl.md 说明。

## 7. 遗留问题

1. **人工观看与实听未做**：三个真实交付包的 `human_review` 仍为 false，无 1–5 分人工评分。
   这是唯一未完成的核心验收环节。
2. T04–T06（声音合成 / 二维码 / GPS）未执行，只有输入与预期能力固化在 `tests/fixtures/topics/`。
3. 每个真实题材只做一条，未验证同题多次的稳定性。
4. `revise` 仍重渲染整条 cut；单镜重编码需要先解决转场与音画对齐。
5. ASR 默认关闭；三个真实成片 `asr_checked=false`。
6. 字体容量按字符数估算，没有真实字体测量与专门裁切回归测试。
7. CI 未在 GitHub 实际运行；只在 Windows 验证。
8. 未接入第二个真实模型后端（接口已抽象，只有 Codex + mock）。
9. 外部素材搜索、网络队列/状态机专用组件、P2-02～04 未实现。

## 8. 用户使用演示

```powershell
# 只输入标题（默认入口）
.\.venv\Scripts\python.exe -m movelyth create "一条网络消息如何从我的电脑到达服务器？"

# 标题 + 可选 brief
.\.venv\Scripts\python.exe -m movelyth create "一条网络消息如何从我的电脑到达服务器？" --brief-file .\brief.md

# 先看故事板与 12 秒预览，再决定是否整片渲染
.\.venv\Scripts\python.exe -m movelyth create "…" --preview
.\.venv\Scripts\python.exe -m movelyth preview VID-000002

# 按审阅意见只改指定镜头
.\.venv\Scripts\python.exe -m movelyth revise VID-000002 --notes .\notes.txt

# 只修渲染器，不改写已审脚本
.\.venv\Scripts\python.exe -m movelyth resume VID-000002 --reuse-script

# 登记自己的素材（记录作者/许可/来源，之后脚本用 data_ref 引用）
.\.venv\Scripts\python.exe -m movelyth asset-add .\图.png --id my_photo --source "自己拍摄" --author "我" --license "自有素材"
.\.venv\Scripts\python.exe -m movelyth asset-check

# 不知道做什么时：先看候选，再让 CLI 选一个可支持的题目
.\.venv\Scripts\python.exe -m movelyth suggest --count 3
.\.venv\Scripts\python.exe -m movelyth daily --preview
```

`suggest` 与 `daily` 都是一次性命令：前者只读历史并输出候选（含画面计划与能力评估），
后者取第一个 `supported` 候选走与 `create` 相同的流水线；候选都需要新增能力时会拒绝生成。
**没有定时器，不会后台自动选题**，也不承诺播放量。

## Definition of Done 对照

| 条件 | 结果 |
|---|---|
| 原 CLI、缓存、恢复、编号交付、横竖版、来源/质量记录不倒退 | 通过 |
| 可组合、可验证、可扩展的视觉 DSL，不再只靠七类固定动画 | 通过 |
| 声画节拍机制，关键画面能与真实配音/字幕同步 | 通过 |
| 可用的故事板/轻量预览 | 通过 |
| 严格安全边界，不执行任意代码 | 通过 |
| 至少三种不同主题经真实模型与 TTS 驱动双画幅成片 | **达成**（T01/T02/T03） |
| 每条通过的片子经过程序检查，人工观看单独记录 | 程序检查通过；人工观看**未执行**（如实标注 false） |
| 文档、测试、真实限制、提交记录齐全 | 通过 |

结论：**代码阶段与三题材双画幅实片验收完成；人工观看/实听是唯一未完成的核心环节。**
