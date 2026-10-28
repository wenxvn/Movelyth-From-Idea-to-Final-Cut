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
