# V1 交付报告

> 本文按《Movelyth V1 规划与执行提纲》§9 的 8 项要求组织。所有结论都对应可核验的证据；
> 没有证据的地方明确写"未验证"。

## 1. 执行摘要

| 批次 | 任务 | 状态 |
|---|---|---|
| 准备 | 基线、回归保护、成本记录 | 完成 |
| A | P0-01 基线 / P0-02 brief / P0-03 Scene DSL | 完成 |
| B | P0-04 可组合画面 / P0-05 声画节拍 / P0-06 审稿与一致性 | 完成 |
| C | P0-07 预览与局部修复 / P0-08 音频质检 / P0-09 来源安全 | 完成 |
| D | P0-10 三题材真实验收 | **2/3 完成**（T01、T02 通过；T03 被额度阻塞） |
| E | P1-01 组件与元数据 / P1-02 风格 / P1-03 素材 / P1-05 provider / P1-06 时区与缓存 / P1-07 发布包 / P1-08 CI / P1-09 回归集 | 完成（P1-04 部分、P1 其余见 §7） |
| F | P2 日更选题 / 工作台 / 队列 / 反馈策略 | **未实施**（不在 V1 完成条件内） |

跳过项与原因：P2 全部（提纲要求 P0/P1 稳定后再做）；外部素材搜索与在线许可核查（不做自动转载）；
按单镜重编码的局部渲染（Remotion 按 composition 整体渲染，做了按 cut 复用并如实记录）。

## 2. 源码与文档

- 版本化 Scene DSL：`docs/scene-dsl.md`；契约在 `src/movelyth/models.py` + `src/movelyth/scenedsl.py`，
  渲染端类型在 `studio/src/types.ts`，生成的 `studio/src/generated/{layout,scene-schema}.json` 提交入库并有漂移测试。
- CLI：`docs`、`README.md` 的"常用命令"；新增 `preview`、`revise`、`schema`、`components`、`asset-add`
  与 `create --brief-file/--preview/--plan-only`。
- 兼容/迁移：旧 `episodes` 表自动补 `brief`/`brief_hash`；旧脚本（只有 `visual`）自动退化为单个
  procedural 图层；旧交付目录不会被覆盖。
- 质量限制：`docs/architecture.md` 末节、`README.md` "能力与限制"、`docs/verification.md` "验证边界"。

## 3. 测试记录

```text
pytest -q                        → 103 passed
pytest -q -m "not slow"          → 102 passed, 1 deselected（CI 用这一条）
pytest tests/test_render_smoke.py -q  → 1 passed（真实 Remotion + Chrome，横竖 10 张静帧）
ruff check src tests             → All checks passed
npm --prefix studio run typecheck → 通过
```

分层：`unit`（默认）/ `slow`（真实渲染）/ `live`（真实模型或在线 TTS，本轮未纳入自动测试）。
CI（`.github/workflows/ci.yml`）只跑 ruff + 非 slow 测试 + 契约漂移 + typecheck，不产生费用；
**GitHub 上的实际运行状态未知**（本机没有执行 Actions）。

## 4. 可核验的输出

真实 Codex 制作（标题驱动，未导入脚本）：

```text
delivery/待上传/VID-000002_矩阵为什么能让整个空间旋转？/r001/          # T01 通过
delivery/待上传/VID-000003_一条网络消息如何从我的电脑到达服务器？/r001/  # T02 通过
```

两者各 13 个文件（横竖版 MP4、封面、字幕、发布文案、交付审计、脚本、研究、质检、溯源、manifest）。

真实 TTS + 真实渲染（mock 剧本，用于验证链路，不是真实模型创作）：

```text
delivery/v1-demo/待上传/VID-000002_梯度下降为什么能让模型逐步减少错误？/r002/
delivery/v1-demo/待上传/VID-000004_…/r004/     # revise 生成的新 revision
delivery/v1-demo/待上传/VID-000007_…/r005/     # 平台文案 + 交付审计 + 封面构图
delivery/v1-demo/待上传/VID-000008_…/r006/     # 开启 ASR
delivery/v1-demo/待上传/VID-000010_…/r008/     # 已登记本地素材
workspace/v1-demo/VID-000003/storyboard.json   # 预览故事板
workspace/v1-demo/metrics.csv                  # 每阶段耗时/缓存/产物大小
```

真实模型（Codex）尝试：`workspace/VID-000002/`（研究、脚本、审稿、渲染、抽帧、审片意见），
最终状态见 §7。

V1 前基线抽帧：`docs/baseline/v0/*.jpg`（来自 VID-000001 编码成片）。

## 5. 性能变化

| 阶段 | 首次（40s+15s 双画幅） | 命中缓存 |
|---|---:|---:|
| research | 0.02 s（mock）/ 92.4 s（真实 Codex） | 0 s |
| script | 0.06 s（mock）/ 610.7 s（真实 Codex） | 0 s |
| sound | 23.4 s | 0.15–0.2 s |
| assets | 0.2 s | 0.1 s |
| render | 90.5 s | 整体 `cut_cached`，未重新编码 |
| check | 84.0 s | — |

同条件前后对比只对"V1 前 22 项测试 / V1 后 97 项测试"有意义；渲染耗时随片长变化，
没有同片长的 V0/V1 对照，**内存峰值未测量**，标为未知。

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

回归风险：渲染器重写（`Visual.tsx` → `components/`）是最大风险点，已用真实静帧覆盖
8 种图层 × 横竖版；旧任务兼容由 `test_legacy_scene_without_layers_still_renders_as_procedural`
与 VID-000001 的 `film.json` 解析验证。布局区域改为互不重叠后，旧的"同一区域叠放"脚本会被拒绝，
这是有意的行为变化，已在 `docs/scene-dsl.md` 说明。

## 7. 遗留问题

1. **第 3 个真实题材未完成**：T03 已跑完研究/编导/配音/渲染，视觉审片提出可读性问题，
   修复过程中 Codex 账号额度用尽（提示 11:21 后恢复）。T01、T02 已通过。
2. **人工观看与实听未做**：所有 `质检报告.json` 的 `human_review` 仍为 false，没有 1–5 分人工评分。
3. ASR 已实测（覆盖率 0.949/0.942），但只在显式开启时运行；默认关闭以免首次加载耗时。
4. 局部修改仍重渲染整条 cut；按单镜重编码需要处理转场与音画对齐，属下一轮。
5. CI 未在 GitHub 实际运行；Windows 是唯一验证过的平台。
6. 外部素材搜索、通用状态机/丢包动画、P2 全部功能未实现。

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

# 登记自己的素材（记录作者/许可/来源，之后脚本用 data_ref 引用）
.\.venv\Scripts\python.exe -m movelyth asset-add .\图.png --id my_photo --source "自己拍摄" --author "我" --license "自有素材"
```

`daily` / `suggest` **没有实现**，不是现有功能；"生成今日份视频"目前仍需助手先读历史再选题目，
CLI 不会自动定时启动。

## Definition of Done 对照

| 条件 | 结果 |
|---|---|
| 原 CLI、缓存、恢复、编号交付、横竖版、来源/质量记录不倒退 | 通过（97 项测试 + VID-000001 兼容解析） |
| 可组合、可验证、可扩展的视觉 DSL，不再只靠七类固定动画 | 通过 |
| 声画节拍机制，关键画面能与真实配音/字幕同步 | 通过（真实词语边界解析 + 时间轴校验） |
| 可用的故事板/轻量预览 | 通过 |
| 严格安全边界，不执行任意代码 | 通过（枚举/数值契约、SSRF、素材白名单） |
| 至少三种不同主题经真实模型与 TTS 驱动双画幅成片 | **2/3 达成**（T01、T02 通过；T03 被 Codex 额度阻塞） |
| 每条通过的片子经过程序检查，人工观看单独记录 | 程序检查通过；人工观看**未执行** |
| 文档、测试、真实限制、提交记录齐全 | 通过 |

结论：**代码阶段完成；V1 实片验收未完成**。
