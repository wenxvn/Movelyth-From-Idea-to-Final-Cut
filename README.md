# Movelyth — 幕绎

**多智能体驱动的全流程 AI 视频创作引擎**
From Idea to Final Cut.

输入一个标题（可选附一段背景 brief），让研究、编导和审片角色协作，自动制作有声音的 B站横版与
抖音竖版，并保存选题、失败与编号交付记录。

首版采用本地程序动画，复用已有 Codex 登录，无需另配模型 API Key；配音通过联网 Edge TTS，
配乐与音效为本地程序合成。V1 增加了**可组合的 Scene DSL**、按真实配音驱动的节拍、
低成本预览、按镜头局部修改、音频质检与来源抓取安全边界。

V2 把重心从"能自动出片"移到"像专业团队做的片"：重做构图栅格与字阶、图表刻度与曲线、
五类镜头转场、逐词高亮字幕；配音改为**按句合成**（句级语速/音高、真实句间停顿），
配乐改为**分段编排**并按人声做带 lookahead 的侧链压低，新增**与画面同源的本地合成音效**。
新增的镜头字段（`transition`/`camera`/`emphasis`/`cues`）都有默认值，V1 已审脚本可原样渲染。
方案与实测见 [docs/v2-plan.md](docs/v2-plan.md)、[docs/v2-evaluation.md](docs/v2-evaluation.md)。

```text
标题 (+ 可选 brief) → 研究 Agent（主张—证据映射）→ 编导 Agent（Scene DSL 多图层分镜）
     → 独立脚本审稿（结构化 findings）→ 受控 DSL 校验
     → Edge TTS 真实词语边界 → 声画节拍/字幕 → Remotion 横竖版
     → FFmpeg 混音 + 技术检查 + 音频机器检查 + 实际抽帧审片
     → 编号上传包（manifest / 质检 / 溯源）
```

## 运行

需要 Python 3.11+、Node.js 兼容当前 Remotion 的版本，以及联网配音服务。
脚本生成默认使用你已登录的 **Codex CLI**；也可以改用任意 **[OI] 兼容端点**
（DeepSeek 官方、中转网关、vLLM、Ollama）。见下方「其他模型」。
当前 Windows 开发环境为 Python 3.11 / Node 24 / Chrome；其它平台尚未端到端验证。

```powershell
git clone https://github.com/wenxvn/Movelyth-From-Idea-to-Final-Cut.git
cd Movelyth-From-Idea-to-Final-Cut
.\setup.ps1
# 若 Codex 尚未登录，先完成 codex login。
.\生成视频.ps1 "矩阵，如何改变我们看到的世界"
```

已有项目环境时，只需要最后一行。也可以运行不带参数的 `生成视频.ps1`，直接输入标题。
需要重做相同标题的另一条视频时增加 `-New`。

## 其他模型（[OI] 兼容端点）

Movelyth 的画面是本地 Remotion 程序动画，**不需要文生图或文生视频模型**。整条链路只有四个角色调用
模型：研究、编导、脚本审稿、画面审片。任何支持 `/chat/completions` 的端点都能驱动这四个角色。

```toml
[agents]
provider = "openai"
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"   # 密钥只从环境变量读取，不写入本文件
model = "deepseek-flash"
# structured_output = "auto"       # auto 先试 json_schema，再退 json_object，最后纯提示词
# vision = "auto"                  # 审片要读抽帧；disabled 时会明确拒绝而不是假装审过
# thinking = "disabled"            # 推理模型的隐藏思考会占用输出上限
```

```powershell
.\.venv\Scripts\python.exe -m movelyth doctor   # 配置与密钥是否存在
.\.venv\Scripts\python.exe -m movelyth probe --image .\test.jpg   # 连通性 + JSON + 图片能力
```

`probe` 会实际发一次请求并报告该端点是否真的支持 JSON 输出与图片输入——"密钥存在"说明不了这些。
模型能力差异是真实的：较小的模型需要更多修复轮次（`studio.max_retries`），
`movelyth probe` 与 `workspace/VID-*/agents/*/events.log` 记录了每一轮的实际失败原因。

## 两种入口

**只输入标题**（默认入口，和以前完全一样）：

```powershell
.\.venv\Scripts\python.exe -m movelyth create "一条网络消息如何从我的电脑到达服务器？"
```

**标题 + 可选 brief**（背景、受众、语气、要强调或要避免的内容）：

```powershell
# brief.md 里用几段普通文字写清楚即可，不需要填表单
.\.venv\Scripts\python.exe -m movelyth create "一条网络消息如何从我的电脑到达服务器？" --brief-file .\brief.md
```

- brief 上限 4000 字，会被规范化为纯文本；标题和 brief 都当作**选题素材**，不是高权限指令。
- brief 的 hash 参与同题判定：**同题不同 brief 不会复用不相关成片**；只有标题时沿用历史行为。
- 用户输入的信息不等于已经核实，研究阶段仍会给出 claims/来源/cautions。

## 常用命令

```powershell
.\.venv\Scripts\python.exe -m movelyth doctor            # 环境与可选能力（含 ASR 是否安装）
.\.venv\Scripts\python.exe -m movelyth create "标题" --plan-only     # 只做研究/编导/审稿
.\.venv\Scripts\python.exe -m movelyth create "标题" --preview       # 故事板 + 12s 低分辨率片段
.\.venv\Scripts\python.exe -m movelyth preview VID-000002            # 对已有任务做预览
.\.venv\Scripts\python.exe -m movelyth revise VID-000002 --notes .\notes.txt  # 按镜头局部修改
.\.venv\Scripts\python.exe -m movelyth resume VID-000002
.\.venv\Scripts\python.exe -m movelyth resume VID-000002 --reuse-script   # 只修渲染器，不改写已审脚本
.\.venv\Scripts\python.exe -m movelyth status [VID-000002]
.\.venv\Scripts\python.exe -m movelyth ideas
.\.venv\Scripts\python.exe -m movelyth suggest --count 3     # 候选选题（含画面计划与能力评估），不制作
.\.venv\Scripts\python.exe -m movelyth daily --preview       # 选一个可支持的候选，走同一 create 流水线
.\.venv\Scripts\python.exe -m movelyth assets
.\.venv\Scripts\python.exe -m movelyth schema            # 输出 Scene DSL 的 JSON Schema
.\.venv\Scripts\python.exe -m movelyth components        # 组件元数据：用途/必需字段/限制/横竖适配
.\.venv\Scripts\python.exe -m movelyth check --film .\film.json --research .\research.json  # 离线校验脚本
.\.venv\Scripts\python.exe -m movelyth asset-add .\我的图.png --id my_photo `
    --source "我自己拍摄" --author "我" --license "自有素材" --scope "本片使用"
.\.venv\Scripts\python.exe -m movelyth asset-check   # 重新校验 hash/授权，标记失效素材
```

登记后的素材在脚本里用 `image` 图层引用：`"type": "image", "data_ref": "my_photo"`。
素材会被校验 hash、复制进任务受控目录，并在发布文案里自动附上授权行；未登记、授权信息不全
或被 `asset-check` 标记失效的素材在渲染前就会失败，不会静默换成别的图。素材库记录
`hash / 来源 / 作者 / 许可 / 适用范围 / 引用任务（used_by_episodes）/ 有效性（valid）`。

`suggest` 只读历史与当前能力，输出 3 个候选（问题、为什么现在做、画面计划、能力评估、风险），
不占用编号、不渲染。`daily` 取第一个标为 `supported` 的候选，调用与 `create` **完全相同**的
流水线；如果候选都需要新增能力，它会拒绝生成并指向 `workspace/topic-plan/plan.json`。
两者都只在你调用时运行一次，**不会后台定时启动**，也不会承诺播放量。

`revise` 的 notes 里写清"镜头 3"或具体的 `scene_id`；只有被点名的镜头会交给编导重写，
其余镜头原样保留，并生成新的 revision，不覆盖已交付版本。

同题默认复用原任务和已验证交付；`--new` 明确要求另建任务。失败不回收编号，修复后用 `resume`，
有效的阶段和语音请求按 hash 缓存。如果只是渲染器/排版修复、不想让编导重写故事，用
`resume <id> --reuse-script`：它会复用已通过审片的 `film.json`（仍按当前契约重新校验），
并在事件记录里写 `approved-script-reused`。每个阶段的耗时与缓存命中写入 `workspace/metrics.csv`。

## 画面能力（Scene DSL v1）

一个镜头可以由多个图层组合：`text`、`math`、`shape`、`chart`（折线/柱状/散点，真实数值或本地
JSON 数据）、`diagram`（任意节点/连线/步骤）、`image`（仅受控本地素材）、`procedural`（原有七类
程序动画）。布局有 `immersive` / `diagram` / `compare`，风格有 `minimal` / `tech` / `documentary`。
动画只有 8 种可审核原语，时间点可以绑定到**真实配音的词语边界**。

细节与兼容规则见 [Scene DSL v1](docs/scene-dsl.md)。旧任务（只有 `visual`）仍按原样渲染。

## 交付

```text
delivery/
  交付清单.csv
  待上传/VID-000001_本集标题/r001/
    VID-000001_B站_横版.mp4
    VID-000001_抖音_竖版.mp4
    封面_B站_横版.png
    封面_抖音_竖版.png
    字幕_B站_横版.srt
    字幕_抖音_竖版.srt
    原声_B站_横版.mp3 / 混音_B站_横版.mp3    # 不开视频也能单独试听配音与配乐
    原声_抖音_竖版.mp3 / 混音_抖音_竖版.mp3
    发布文案.md          # 分平台：采用标题 / 备选标题 / 封面文案 / 简介 / 标签 / 来源
    交付审计.md          # 机器检查、ASR/静音/混音状态、人工观看与实听是否执行
    素材来源与署名.md
    脚本.json / 研究记录.json / 质检报告.json / 制作溯源.json / manifest.json
```

V1 起的完整交付包共 17 个文件（V1 之前的老包没有 `交付审计.md` 与 `分镜预览.json`，为 16 个）。

通过检查才写入待上传。完整解码、音轨、画幅、帧率、时长、两遍响度归一与实测复核、黑屏、逐镜运动与整帧漂移之后，
由独立 Agent 查看实际抽帧。审片拒绝会交回编导有限修复，程序问题或达到上限则保存为失败，
不会静默输出无声或不完整的上传包。

上传由用户手动完成。`发布文案.md` 按平台分开，含采用标题、备选标题、封面文案、简介与标签，
你可以直接挑选或改写；`交付审计.md` 用一页说明哪些检查真的跑了、哪些人工验证还没做；
`原声_*.mp3` / `混音_*.mp3` 让你不必打开 20MB 的视频就能单独听配音和配乐。
发布后可以记录实际链接和数据；没有填的指标保持未知：

```powershell
.\.venv\Scripts\python.exe -m movelyth feedback VID-000001 --platform bilibili --url "你的真实视频链接" --views 123 --likes 8 --completion-rate 0.45
```

## 能力与限制

- 当前适合能用程序图形讲清的数学/科学/技术概念。真人实拍、影视素材、高精度科学仿真、
  论文复现仍未接入；不承诺任意标题都能得到高质量成片。
- 画面由受控枚举与数值生成，模型不产出也不执行任意代码、Shell 或脚本。
- 角色是独立上下文的真实模型调用，默认串行。本地动画和声音阶段为确定性程序。
- **音频质检**：可选本地 ASR（`pip install -e ".[asr]"` 后把 `asr_enabled = true`；首次加载
  模型约 2 分钟，默认关闭）、长静音检测、混音/原声能量比，以及 `key_terms` 术语核对
  （如 `"Qwen|千问"`，ASR 里找不到时提示复听）。未安装或未开启 ASR 时报告会明确写"未检查"；
  `audible` 只表示音轨非静音，**不表示听感正确**。
  ASR 覆盖率是下限信号：小模型会把"梯度"写成"T度"，覆盖率下降不等于配音有错。
- **响度**：交付前两遍 `loudnorm`（先测量、再线性归一）到 -14 LUFS / -1.5 dBTP，交付后再用
  `ebur128` 独立复核。B站会把高于 -28 LUFS 的音频归一到 -14 LUFS、抖音约 -14~-15，
  交付即对齐可避免平台二次增益。
- **运动**：4 fps 网格采样，报告每个镜头的静帧占比与整帧漂移段；场景淡入淡出已排除，
  静帧可能是刻意停顿，整帧漂移通常是缩放或抖动，需人工确认是否为设计意图。
- **发音与字幕分离**：`speech_replace` 只改变配音，字幕始终显示原文，两者通过字符映射对齐时间。
- **来源抓取**：仅 HTTPS，解析后固定到已校验的公网 IP，拒绝内网/回环/元数据地址与内网重定向；
  失败缓存 6 小时过期。抓取成功不等于事实已核验。
- **预览不等于成片**：`--preview` 只渲染代表帧与 12 秒低分辨率片段，不会进入待上传。
- **局部修改不等于单镜重编码**：`revise` 会复用未改动镜头的配音缓存，但当前仍重渲染整条 cut。
- **发布包不等于已发布**：`发布文案.md` 里的备选标题与封面文案需要你人工挑选；`交付审计.md`
  如实标注人工观看/实听是否执行。
- 技术检查和抽帧不能保证全片听感、发音、审美和所有领域事实。首次使用新主题/音色时建议上传前观看。
- 本版自建总控，参考仓库的用途和实际依赖见 [第三方说明](docs/third-party.md)，机制见 [架构文档](docs/architecture.md)。
- V1 的执行状态、真实证据与未完成项见 [V1 执行记录](docs/v1-execution.md) 与
  [跨题材验收](docs/v1-evaluation.md)。

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q                  # 全部（含真实渲染静帧）
.\.venv\Scripts\python.exe -m pytest -q -m "not slow"    # 跳过真实渲染，CI 用这一条
.\.venv\Scripts\python.exe -m ruff check src tests
npm.cmd --prefix studio run typecheck
```

修改 `models.py` 的图层/布局常量后，需要重新生成渲染端契约：

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from pathlib import Path; from movelyth.scenedsl import write_renderer_contracts; write_renderer_contracts(Path('studio/src'))"
```

`workspace/`、`delivery/`、模型日志、语音缓存、凭据与依赖均不进入 Git。不要把已有 `ready`
等同于用户已发布，也不要把导入脚本、mock provider 或渲染测试写成真实标题驱动的验收。

维护者：wenxvn · 1055602033@qq.com
仓库：https://github.com/wenxvn/Movelyth-From-Idea-to-Final-Cut
