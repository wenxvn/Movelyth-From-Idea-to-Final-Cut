# 验收与证据索引（第二版提纲）

记录每次工作包完成时的**命令、输入、结果与媒体位置**。真实运行产物留在 git 忽略目录
（`workspace/`、`delivery*/`），本文件只保存可复核的索引与结论。

验证层级：V1 离线逻辑 / V2 小型真实媒体 / V3 导入脚本制作 / V4 真实题目制作 / V5 实际看听。

## A1 · S1-01 基线、CI、工具与时区（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 离线测试 | `python -m pytest -q -m "not slow and not live"` | 215 passed, 1 deselected | V1 |
| Ruff | `python -m ruff check src tests` | All checks passed | V1 |
| TypeScript | `npm --prefix studio run typecheck` | 无错误 | V1 |
| 契约同步 | `write_renderer_contracts` + `git diff -- studio/src/generated` | 无差异 | V1 |
| CLI | `movelyth --help` / `schema` / `doctor` | 可运行，doctor 输出可解析 JSON | V1 |
| 工具表 | `doctor` | ffmpeg 7.1（imageio-ffmpeg）、ffprobe n7.1（Remotion compositor）、Chrome 156.0.8078.48、4 个中文字体 | V1 |
| 时区 | `MOVELYTH_TZ` 未设 / `UTC` / `Not/AZone` | `+08:00` / `+00:00` / 明确 `TimezoneError`（不再静默 +08:00） | V1 |
| 缺 ffprobe | `ffprobe_candidates()` 只含不存在路径 | `RuntimeError` 列出已检查位置与 `npm ci --prefix studio` | V1 |
| 媒体验证 | 2 秒 1920×1080 h264+aac 合成片 → `verify_video` | `passed: true`（10 项检查全通过） | V2 |

**未验证**：远程 Windows/Linux CI 尚未运行（本轮未推送）；`doctor` 的 TTS 连通性未探测（按设计）。

## A2 · S1-02 Review 一致性、轴读数与交付策略（2026-10-28）

| 项 | 命令 / 输入 | 结果 | 层级 |
| --- | --- | --- | --- |
| 离线测试 | `pytest -q -m "not slow and not live"` | 231 passed | V1 |
| 刻度镜像 parity | `tests/test_charts.py` 用 node 执行 `ChartLayer.tsx` 的真实 `niceStep/niceDomain/format` 源码 | 8 组输入（含 0.0004–0.003 与常量序列）域/步长/标签完全一致 | V1 |
| M01 一致性 | reviewer `passed=true` + factual finding | 规范化后 `passed=false`；pipeline 抛 `成片检查未通过`，交付目录无 mp4，ledger 非 ready | V1（离线 pipeline） |
| M02 单位/轴错 | “纵轴刻度显示 0.76，但数据点标的是 5” | 不降级：`fail/major`，证据 `claim-about-data-or-units` | V1 |
| 结构性缺陷 | “纵轴刻度被裁切，标签缺字” | 不降级：`fail/major` | V1 |
| 确定性降级 | “纵轴刻度显示 0.4 与 0.8…”（场景实际刻度 0.2/0.4/0.6/0.8/1.0） | 降级为 warning，证据记录生成标签；整片仍 ready | V1（离线 pipeline） |
| 无证据轴疑点 | “纵轴刻度好像不太对” | `unknown` 且非必需 → 不阻断，但留痕 | V1 |
| 交付决定 | 每次 check 阶段 | `release-decision.json`：decision/policy_version/blocking/warnings/passed/inputs | V1 |
| 旧配置兼容 | `downgrade_axis_readings=true/false` | 分别等价 `deterministic/strict`；非法值报错 | V1 |

**未验证**：真实视觉模型的 finding 分布（本机无模型端点）；因此“降级率”与“误降级率”暂无实测数字。
