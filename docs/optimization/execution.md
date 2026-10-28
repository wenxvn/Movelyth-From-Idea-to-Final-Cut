# 四阶段优化执行状态（第二版提纲）

> 对象：`main` @ `5383447`（本地领先 `origin/main` 22237b5 一个提交，工作区干净）。
> 本文件是**唯一任务状态**：编号、依赖、状态、证据索引与下一步动作。
> 证据分层见 [verification.md](../verification.md) 与本文件 §2 的 V1–V5 约定。

## 0. 开工检查（提纲 §0.1）

| 项 | 记录 |
| --- | --- |
| 仓库 | `D:\wenxvn(2)\视频\Movelyth`，分支 `main`，HEAD `5383447`，`origin/main` = `22237b5`（提纲核对基线） |
| 工作区 | 干净（`git status --short` 空）；未提交用户修改无 |
| 文档 | 已读根 `AGENTS.md`、`README.md`、`docs/architecture.md`、`scene-dsl.md`、`verification.md`、`v2-evaluation.md`、`v3-plan.md`、`v3-evaluation.md` |
| 环境 | 见 §1 环境能力表 |
| 基线 | `pytest -q -m "not slow and not live"`：206 passed；`ruff check src tests`：通过；`npm --prefix studio run typecheck`：通过；`movelyth --help` / `schema` / `doctor`：可运行 |
| 冻结对照输入 | `tests/fixtures/` 六题 fixture、`docs/v1-evaluation/`、`docs/v2-evaluation/`、`docs/v3-evaluation/` 代表帧；`delivery-ab/待上传/VID-000015_*/r011`（V3 成片） |
| 核心生产配置 | 程序动画 + Edge TTS（联网）+ 本地 ASR 质检（未默认开启）；付费生成/大模型权重默认关闭 |
| 模型后端 | **本机无可用真实模型端点**：`codex` 未安装，`DEEPSEEK_API_KEY`/`OPENAI_API_KEY` 均未设置（只检查存在性，不读取值）。→ 真实题目 V4 与真实编导/审片证据本轮阻塞，见 §3 |

## 1. 环境能力表（2026-10-28 实测）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Python | 3.11.9（`.venv`） | `python -V` |
| Node / npm | v24.12.0 / 11.6.2 | `node -v`、`npm -v` |
| FFmpeg | 7.1（imageio-ffmpeg 内置） | `doctor.ffmpeg` + `ffmpeg -version` |
| ffprobe | Remotion `compositor-win32-x64-msvc/ffprobe.exe` | `doctor.ffprobe`（系统 PATH 无 ffprobe） |
| 浏览器 | Chrome `C:\Program Files\Google\Chrome\Application\chrome.exe` | `doctor.browser` |
| 字体 | Noto Sans SC / Noto Serif SC / 微软雅黑 / 宋体 可用 | `C:\Windows\Fonts` 列表 |
| 渲染器 | `studio/node_modules/@remotion/*` 已安装（4.0.538） | `doctor.renderer_installed` |
| 语音 | edge-tts 7.3.1，需联网 | `pip` 元数据；实听见 acceptance |
| ASR | faster-whisper 已安装（首次用需下模型） | `doctor.asr` |
| 时区数据 | `tzdata` 已随环境安装（Windows 无系统 tzdata） | `zoneinfo.ZoneInfo("Asia/Shanghai")` 可用 |
| 模型端点 | **不可用**（codex 缺失、无 API Key 环境变量） | `doctor.codex = null`、环境变量存在性检查 |
| GPU | 未检测/未使用 | 本轮无三维与 shader 启用 |

## 2. 32 项任务状态

状态取值：`todo` / `in_progress` / `implemented` / `verified` / `blocked` / `optional_deferred`。
`implemented` 不自动等于 `verified`；E/O 延期与核心阻塞分开记录。

### S1 可验证的生产基础（C）

| 编号 | 状态 | 依赖 | 证据 | 下一步 |
| --- | --- | --- | --- | --- |
| S1-01 基线/CI/工具/时区 | verified（本地；远程 CI 未跑） | 开工检查 | A1；`tests/test_doctor.py`、`tests/test_util.py`、`.github/workflows/ci.yml` | 推送后补远程 Windows/Linux 结果 |
| S1-02 Review 一致性/轴读数/交付策略 | verified（V1；真实审片模型未接入） | S1-01 | A2；`policy.py`、`charts.py`、`tests/test_release_policy.py`、`tests/test_release_gate.py`、`tests/test_charts.py`、D3/D4 | S1-04 补来源检查后合并进决定 |
| S1-03 组成表与 revision 完整性 | verified（V1；真实媒体验收在 S2-09） | S1-02 | A3；`pipeline.py`（`build_composition`/`manifest_report`）、`tests/test_composition.py`、D5 | 交付包绑定当前 revision 与决定；S2-09 补编码后核对 |
| S1-04 来源前移与主张覆盖 | verified（V1；真实公网抓取未跑） | S1-02 | A4；`sources.py`（`verify_claims`/`locate_excerpt`）、`policy.source_checks`/`claim_usage_checks`、`evidence` 阶段、`tests/test_claim_coverage.py`、D6 | 真实题目抓取与 PDF 留 S3-06 |
| S1-05 brief/题材/能力路由 | verified（V1；真实模型路由未跑） | S1-04 | A5；`capability.py`、`brief.py`、`models.ProductionBrief`、`brief` 阶段、`tests/test_capability_route.py`、D7 | 真实题目路由统计留 S4-02 |
| S1-06 版本化契约/对象身份/语义事件 | todo | S1-03, S1-05 | — | DSL v2 + 事件 |
| S1-07 预算/运行观测/恢复 | todo | S1-03 | — | RunRecord + 预算门 |

### S2 有解释力的完整成片（C）

| 编号 | 状态 | 依赖 |
| --- | --- | --- |
| S2-01 镜头配方与统一风格 | todo | S1-05, S1-06 |
| S2-02 语音后端/读法/韵律/核对 | todo | S1-06, S1-07 |
| S2-03 声音事件/分轨/混音 | todo | S2-02, S1-06 |
| S2-04 字体/字幕/动态布局 | todo | S2-01, S2-02 |
| S2-05 受控计算驱动的参数动画 | todo | S2-01, S1-06 |
| S2-06 内容绑定焦点相机 | todo | S2-04, S2-05 |
| S2-07 真实形变/共享对象/公式 | todo | S2-05, S2-06, S1-06 |
| S2-08 稳定纸面/圈注/材质 | todo | S2-01, S2-04 |
| S2-09 布局预检/完整草片/编码核对 | todo | S2-03/04/05/06 |
| S2-10 真实编导使用新能力 | todo | S2-01/07/08/09, S1-04 |
| S2-11 三组样片与两题成片 | todo | S2-03/04/07/08/09/10 |

### S3 自动修复、效率与扩展

| 编号 | 范围 | 状态 | 依赖 |
| --- | --- | --- | --- |
| S3-01 按缺陷类型最小修复 | C | todo | S1-02, S1-06, S1-07, S2-09 |
| S3-02 单镜缓存/转场把手/组装 | C | todo | S1-03, S1-06, S1-07, S3-01 |
| S3-03 资产需求/匹配/授权/裁切 | C（联网 E） | todo | S1-04/05, S2-01/04, S1-07 |
| S3-04 代码/数据结构/公式模板 | E | todo | S1-05/06, S2-04/07/10 |
| S3-05 素材视频/证据面板 | E | todo | S1-04/05, S2-01/04, S3-03 |
| S3-06 PDF 可定位证据 | E | todo | S1-04, S1-07 |
| S3-07 三维/shader/生成后端 | O | optional_deferred | S1-05/07, S2-06, S3-02/03 |
| S3-08 可编辑时间轴导出 | O | optional_deferred | S1-03/06, S2-03/04, S3-02 |

### S4 真实验收、体验与反馈（C）

| 编号 | 状态 | 依赖 |
| --- | --- | --- |
| S4-01 冻结实验与可归因对照 | todo | S2-11, S1-07 |
| S4-02 六题材重复真实评测 | todo | S4-01, S3-01/02/03, S1-07 |
| S4-03 异常/恢复/确定性/资源回归 | todo | S1-02/03/07, S2-09, S3-01/02 |
| S4-04 一次配置、题目输入与投稿包 | todo | S1-05/03/07, S2-11, S3-01 |
| S4-05 版本/时间点/观察窗口反馈 | todo | S1-03/07, S4-02 |
| S4-06 最终能力声明与交接 | todo | S4-01…S4-05 |

## 3. 已知外部阻塞（不伪造通过）

| 阻塞 | 影响 | 处置 |
| --- | --- | --- |
| 无真实模型端点（codex 缺失、无 API Key） | S2-10 真实编导、S2-11 两题真实成片、S4-02 12 任务批次、S4-05 平台反馈 | 先完成不依赖模型的实现与 V1/V2/V3 验证；阻塞项保持 `blocked`，不改成 verified |
| 无 3–5 名目标受众 | S4-01 主观对照、S4-02 理解题、S2-11 看听记录 | 交付可盲评包 + 自评时间点记录，明确“未做人群评估” |
| 无 GPU | S3-07 O1/O2 | O 类默认 `optional_deferred` |

## 4. 下一步（可直接执行）

1. S1-01 收尾：ffprobe 定位与 doctor 报告、时区严格化、CI 依赖顺序，跑 V1。
2. S1-02：`CheckResult` / `ReleaseDecision` / 策略模块与故障注入 M01–M02、M04、M10。
3. S1-03：组成清单与原子交付（M12）。
