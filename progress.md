# Movelyth 实施记录

## 2026-10-25 · V1

- 确认基线：HEAD `963b1aa`、工作区干净、远端一致；22 项 pytest / Ruff / TypeScript 通过。
  记录在 `docs/v1-baseline.md`，并从 VID-000001 编码成片抽帧保存 V1 前视觉基线。
- 发现本机 Codex 不可用：`%APPDATA%\npm` 的 `@openai/codex` 缺 `codex-win32-x64` 可选依赖；
  可执行的 0.130.0-alpha.5 访问后端持续 `tls handshake eof`，代理下 `chatgpt.com` 亦不可达。
  因此真实模型驱动的跨题材验收被阻塞，本轮只能标"代码阶段完成、实片验收未完成"。
- P0-02：`--brief-file` 可选输入，brief 规范化 + hash 并入意图判定；旧库自动迁移
  `brief`/`brief_hash`，历史任务不受影响。
- P0-03/P0-04：新增版本化 Scene DSL v1（图层/布局/节拍/动作/结构化 findings），
  Python 契约生成 TypeScript 侧 `layout.json` 与 `scene-schema.json` 并加漂移测试；
  渲染端拆成组件注册表 + 三套布局 + 三套风格，图表/有向图/公式/图形/图片/程序动画可组合。
- P0-05：节拍与动作绑定真实 TTS 词语边界，新增时间轴一致性校验（越界、交叠、无效区间）。
- P0-06：研究输出 claims 映射，审稿输出结构化 findings；新增 `consistency.py`
  拒绝"说下降画上升""示意数据说成实测""称旋转但矩阵不是旋转"等。
- P0-07：`preview`（故事板 + 12s 低分辨率片段，不入交付）与 `revise`（只改指定镜头、
  新 revision、不覆盖旧交付）；阶段耗时与缓存命中写入 `workspace/metrics.csv`。
- P0-08：可选本地 ASR、长静音（区分片头片尾留白）、混音/原声能量比、三套配乐预设、
  可选发音映射；`audible` 明确解释为"非静音"，不等于听感正确。
- P0-09：来源抓取重写为 DNS 校验 + 固定公网 IP 连接 + 逐跳重定向校验 + MIME/大小/超时限制 +
  成功 30 天/失败 6 小时缓存；本地素材路径白名单与逃逸阻断。
- 真实渲染与 TTS 演示（mock 剧本）：VID-000002 双画幅 `ready`（41.0s / 17.0s，11 项检查通过），
  VID-000003 `previewed`（storyboard + 12.0s 960×540 片段），VID-000004 `revise` 成功
  （语音全命中缓存，sound 0.2s vs 首次 23.4s）。
- 测试从 22 项增至 72 项（另有 1 项真实渲染 slow 测试），Ruff 与 TypeScript 通过。
- 文档：`docs/scene-dsl.md`、`docs/v1-baseline.md`、`docs/v1-execution.md`、
  `docs/v1-evaluation.md`，README/architecture/verification/skill 同步更新；新增 CI 工作流。
- 未完成：真实模型三题材验收、ASR 实际执行、人工完整观看与实听、按单镜重编码的局部渲染、
  P1 剩余视觉组件（网络队列、状态机、外部素材授权管理）、P2 全部。

## 2026-10-25
- 用户确定项目名称 Movelyth — 幕绎、标语 From Idea to Final Cut.、仓库与联系邮箱。
- 已克隆指定的空仓库，设置仓库级 Git 作者信息；上级原有视频与参考仓库保持原样。
- 已核验 Node 24、Python 3.11、Chrome、已登录的 Codex CLI 和既有 edge-tts/imageio-ffmpeg/Pillow/numpy。PATH 中尚缺独立 ffprobe。
- 正在实现真正的标题入口、角色输出校验、台账和渲染链路。
- 已实现总控、独立上下文 Codex 角色调用、结构化内容校验、SQLite 台账、基于 hash 的阶段缓存、任务互斥和编号交付暂存。
- 已实现七类本地动画、真实逐镜配音与边界字幕、原创程序音轨、横竖版渲染及最终文件技术检查；尚待完整成片验收。
- 13 项 pytest 通过，包括并发编号、运行锁、失败恢复、缓存篡改、SVD 误差递减、真实媒体解码/画幅/静音拒绝。TypeScript 与 Ruff 检查通过。
- 已完成 Edge TTS 连通实测（3.672 秒，10 条词语边界）；真实标题任务 VID-000001 研究角色已完成，正在编导/审稿。
- 新增并验证 movelyth-video skill，已复制至用户 Codex skills 目录。项目运行环境使用 .venv；首次无隔离的项目 editable 安装和新增 Ruff 之后改为项目虚拟环境，既有依赖未升级。
- 真实脚本审稿通过：long 10 镜/928 字、short 4 镜/266 字；真实 TTS 已完成全部镜头并保存时间轴。
- 渲染期间观察到本机空闲内存不足、编码进程约 1.45GB 私有内存及 NumPy 诊断导入内存失败。已只终止明确属于本次任务的两组渲染进程，保留台账/脚本/配音，改为单渲染并发、编码2线程、受限媒体缓存、BLAS单线程与 veryfast 编码；需重新验证后恢复正式任务。
- Python 环境首次使用 --no-build-isolation 时缺少 bdist_wheel，随后标准 editable 安装成功；uv.lock 已生成，pip check 无依赖冲突。Remotion --version 并非此CLI的版本子命令，版本依据 npm 锁文件与实际包元数据。
- 限流后七类画面渲染测试成功；正式任务成功命中研究/脚本/声音/素材缓存，长版与短版已完成渲染进度，待最终文件与审片阶段结束。
- 新增程序素材使用台账及与真实发布反馈的关联；发布链接与制作状态分别导出。修复 idea 来源任务与实际制作任务不能混用的问题，防止把本期提出的下期 idea 误记为已完成。
- 首轮技术检查通过但实际审片拒绝（矩阵没有排成2×2、上下文缺来源）。已修复矩阵标注并补齐来源正文证据；预览复核通过，非阻断的实听/获取限制单独记为 warnings。
- 最终检查改为直接从编码后的 MP4 提取代表帧，再生成审片拼图；保留同一角色的多次尝试目录和 latest 指针。已审研究/脚本恢复时冻结并检查 hash，渲染修复不会重新生成整部故事。
- 初版源码已提交 fcd3ef9 并推送 origin/main；正式修正版正在重渲染，完整交付验证尚未结束。
- 已将 Ruff 安装到项目 .venv，并移除首次安装遗留的全局 Movelyth editable 入口与新装 Ruff；项目解释器/模块路径确认正常，原有全局依赖未升级。
- 最终审片对参考180秒产生误判并触发改写；已终止该轮，明确目标与允许范围，保存被取消的改写，从原始真实Agent输出恢复已审故事，并逐场景核对render-spec。缓存命中研究/脚本/声音/素材/渲染，只重新检查最终文件。
- VID-000001 最终交付通过：横版209.9秒/1920×1080、竖版62.8秒/1080×1920，均30fps、H.264/AAC。最终编码帧独立审片 passed=true，issues为空；实听/ASR/完整运动观感未验证，来源可用性限制保留为warnings。
- 上传包13个文件，manifest与两版原始成片/交付副本hash核对通过；再次通过生成视频.ps1触发同题，返回ready、同编号和reused=true。实际已做题与三条下期idea状态分别为completed/backlog，未伪造发布数据。
- 最终22项pytest、Ruff、TypeScript通过；全局skill与项目源同步且格式校验通过。验证结论与范围已写入docs/verification.md。
