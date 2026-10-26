# Movelyth 实施记录

按时间倒序。任务级状态见 [docs/v1-execution.md](docs/v1-execution.md)，
证据见 [docs/verification.md](docs/verification.md)，结论见 [docs/v1-report.md](docs/v1-report.md)。

## 2026-10-26 · 借鉴 references 的四项质检与排版改进

- 参考 `references/lunamos-paper2video` 的 `verify.py`、`finalize.sh`、`text_check.py` 与
  `reference/visual-style.md`，补四处 Movelyth 原本的空白，未整库接入。
- **两遍响度**：`mux_with_loudness` 先测量混音，再用 `measured_I/TP/LRA/thresh/offset` 线性归一
  到 -14 LUFS / -1.5 dBTP（原为单遍 -16 LUFS），交付后用 `ebur128` 独立复核；
  纯静音测量为 `-inf` 时退回动态模式。实测 -41.8 LUFS 的混音输出 -14.0 LUFS。
- **逐镜运动**：`motion_report` 以 4 fps、8×6 网格只统计"有内容格子"的变化，输出每镜静帧占比
  与整帧漂移段（≥2 秒，排除场景淡入淡出）；连续静止 ≥5 秒的镜头单列。原实现只有全片平均帧差，
  单镜静止或整屏抖动都会漏过。三份真实成片回测：整帧漂移零误报，最长连续静帧 3.8 秒。
- **发音与字幕分离**：`speech_plan` 生成配音文本并记录字符来源，`captions` 按来源映射时间；
  `speech_replace` 只改配音，字幕显示原文。原实现会把"熵→商"直接写进字幕。
- **中文排版**：新增 `textfit.py`（标点优先断行、不拆拉丁词与数字单位、避头尾、避免孤行），
  字幕分页改用它，不再硬切出两字残页；`layout_warnings` 报告估算断行里的排版问题。
- **术语核对**：`key_terms`（如 `"Qwen|千问"`）在 ASR 转写中查找，缺失记为待复听；
  未开 ASR 时明确写未检查，不影响制作。
- 交付审计新增实测响度、运动分析与术语状态三行。测试 125 项通过（新增 14 项），
  Ruff 与真实渲染 smoke 通过。
- 真实数据验证：VID-000004 重放 `check_action` 全通过（-14.4 LUFS，13 项检查）；
  326 个真实 TTS 边界用例零失败；真实 edge-tts 验证替换只改配音、字幕保原文。
  未跑新的真实标题驱动成片，`key_terms` 在真实 ASR 开启时未验证。

## 2026-10-26 · 收尾与精简

- 三个真实题材全部通过：VID-000002（矩阵，242.6 s / 64.8 s）、VID-000003（网络消息，
  218.9 s / 67.2 s）、VID-000004（梯度下降，242.6 s / 69.5 s），均 11 项技术检查 + 独立视觉审片通过。
- 交付包加入 `原声_*.mp3` / `混音_*.mp3`（128 kbps，便于不开视频也能试听），现有交付同步补齐，
  manifest 已更新并校验通过（17 个文件）。
- 素材库补 `valid` 与 `used_by_episodes`：交付后自动记录引用任务，`asset-check` 重校验并标记失效，
  失效素材在渲染前被拒绝。
- 真实成片代表帧入库 `docs/v1-evaluation/`（6 张，约 115 KB）。
- 精简：删除未使用的 `safe_local_asset` / `write_schema_doc`、过时的 `task_plan.md`；
  合并重复的文档表述，`docs/v1-execution.md` 从 25 KB 压到约 6 KB；清理 `workspace/` 下的
  一次性探测目录。
- 测试 111 项通过，Ruff 与 TypeScript 通过。

## 2026-10-25 · V1 实现

- 确认基线 `963b1aa`，记录环境、22 项测试、VID-000001 参数与 V1 前抽帧基线。
- P0-02：`--brief-file`，brief 规范化 + hash 并入意图判定；旧库自动迁移 `brief`/`brief_hash`。
- P0-03/04：Scene DSL v1（8 种图层、3 布局、3 风格、8 种动画原语、结构化 findings）；
  Python 契约生成渲染端 JSON 并有漂移测试；渲染端拆成组件注册表。
- P0-05：节拍与动作绑定真实 TTS 词语边界；时间轴一致性校验。
- P0-06：研究输出 claims；审稿输出结构化 findings；`consistency.py` 拒绝旁白与画面矛盾。
- P0-07：`preview`（故事板 + 12 s 低分辨率片段）与 `revise`（只改指定镜头、新 revision）。
- P0-08：可选本地 ASR、长静音（区分片头片尾留白）、混音/原声比、三套配乐预设。
- P0-09：来源抓取重写（DNS 校验 + 固定公网 IP + 逐跳重定向校验 + 缓存 TTL）。
- P1：组件元数据、CSV 数据、素材库、发布包、provider 抽象、时区可配、CI 工作流、六题回归集。
- P2-01：`suggest` / `daily`（不自动定时）。
- 真实 Codex 制作期间修复了 11 个由真实成片暴露的缺陷（详见 v1-execution.md）。
- 未完成：人工观看与实听、T04–T06、单镜重编码、P2-02～04。

## 2026-10-25 · 首版 0.1.0

- 项目命名 Movelyth — 幕绎，仓库与联系邮箱确定；上级素材与参考仓库保持原样。
- 实现标题入口、独立上下文角色调用、SQLite 台账、阶段缓存、编号交付。
- 七类本地动画、真实逐镜配音与边界字幕、原创程序音轨、横竖版渲染与最终文件检查。
- VID-000001《矩阵，如何改变我们看到的世界》真实端到端成片通过（209.9 s / 62.8 s）。
- 22 项 pytest、Ruff、TypeScript 与 skill 格式检查通过。
