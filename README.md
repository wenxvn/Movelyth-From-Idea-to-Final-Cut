# Movelyth — 幕绎

**多智能体驱动的全流程 AI 视频创作引擎**
From Idea to Final Cut.

输入一个标题（可选附一段背景 brief），让研究、编导和审片角色协作，自动制作有声音的 B站横版与
抖音竖版，并保存选题、失败与编号交付记录。

首版采用本地程序动画，复用已有 Codex 登录，无需另配模型 API Key；配音通过联网 Edge TTS，
配乐与音效为本地程序合成。V1 增加了**可组合的 Scene DSL**、按真实配音驱动的节拍、
低成本预览、按镜头局部修改、音频质检与来源抓取安全边界。

```text
标题 (+ 可选 brief) → 研究 Agent（主张—证据映射）→ 编导 Agent（Scene DSL 多图层分镜）
     → 独立脚本审稿（结构化 findings）→ 受控 DSL 校验
     → Edge TTS 真实词语边界 → 声画节拍/字幕 → Remotion 横竖版
     → FFmpeg 混音 + 技术检查 + 音频机器检查 + 实际抽帧审片
     → 编号上传包（manifest / 质检 / 溯源）
```

## 运行

需要 Python 3.11+、Node.js 兼容当前 Remotion 的版本、已登录的 Codex CLI，以及联网配音服务。
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
.\.venv\Scripts\python.exe -m movelyth status [VID-000002]
.\.venv\Scripts\python.exe -m movelyth ideas
.\.venv\Scripts\python.exe -m movelyth assets
.\.venv\Scripts\python.exe -m movelyth schema            # 输出 Scene DSL 的 JSON Schema
.\.venv\Scripts\python.exe -m movelyth components        # 组件元数据：用途/必需字段/限制/横竖适配
.\.venv\Scripts\python.exe -m movelyth asset-add .\我的图.png --id my_photo `
    --source "我自己拍摄" --author "我" --license "自有素材" --scope "本片使用"
```

登记后的素材在脚本里用 `image` 图层引用：`"type": "image", "data_ref": "my_photo"`。
素材会被校验 hash、复制进任务受控目录，并在发布文案里自动附上授权行；未登记或授权信息不全
的素材在渲染前就会失败，不会静默换成别的图。

`revise` 的 notes 里写清"镜头 3"或具体的 `scene_id`；只有被点名的镜头会交给编导重写，
其余镜头原样保留，并生成新的 revision，不覆盖已交付版本。

同题默认复用原任务和已验证交付；`--new` 明确要求另建任务。失败不回收编号，修复后用 `resume`，
有效的阶段和语音请求按 hash 缓存。每个阶段的耗时与缓存命中写入 `workspace/metrics.csv`。

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
    发布文案.md          # 分平台：采用标题 / 备选标题 / 封面文案 / 简介 / 标签 / 来源
    交付审计.md          # 机器检查、ASR/静音/混音状态、人工观看与实听是否执行
    素材来源与署名.md
    脚本.json / 研究记录.json / 质检报告.json / 制作溯源.json / manifest.json
```

通过检查才写入待上传。完整解码、音轨、画幅、帧率、时长、音量、黑屏与采样运动检查之后，
由独立 Agent 查看实际抽帧。审片拒绝会交回编导有限修复，程序问题或达到上限则保存为失败，
不会静默输出无声或不完整的上传包。

上传由用户手动完成。`发布文案.md` 按平台分开，含采用标题、备选标题、封面文案、简介与标签，
你可以直接挑选或改写；`交付审计.md` 用一页说明哪些检查真的跑了、哪些人工验证还没做。
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
  模型约 2 分钟，默认关闭）、长静音检测、混音/原声能量比。
  未安装或未开启 ASR 时报告会明确写"未检查"；`audible` 只表示音轨非静音，**不表示听感正确**。
  ASR 覆盖率是下限信号：小模型会把"梯度"写成"T度"，覆盖率下降不等于配音有错。
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
