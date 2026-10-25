# Movelyth — 幕绎

**多智能体驱动的全流程 AI 视频创作引擎**
From Idea to Final Cut.

输入一个标题，让研究、编导和审片角色协作，自动制作有声音的 B站横版与抖音竖版，并保存选题、失败与编号交付记录。

首版采用本地程序动画，复用已有 Codex 登录，无需另配模型 API Key；配音通过联网 Edge TTS，配乐与音效为本地程序合成。已实现可恢复的 CLI 制作链路，完整成片验证记录见 [验证记录](docs/verification.md)。

```text
一句话/标题 → 研究 Agent → 编导 Agent → 独立审稿
          → 配音/字幕/音乐 → Remotion 横竖版 → 技术检查与实际抽帧审片
          → 编号上传包 + 历史、idea、素材、失败记录
```

## 运行

需要 Python 3.11+、Node.js 兼容当前 Remotion 的版本、已登录的 Codex CLI，以及联网配音服务。当前 Windows 开发环境为 Python 3.11 / Node 24 / Chrome；其它平台尚未端到端验证。

```powershell
git clone https://github.com/wenxvn/Movelyth-From-Idea-to-Final-Cut.git
cd Movelyth-From-Idea-to-Final-Cut
.\setup.ps1
# 若 Codex 尚未登录，先完成 codex login。
.\生成视频.ps1 "矩阵，如何改变我们看到的世界"
```

已有项目环境时，只需要最后一行。也可以运行不带参数的 `生成视频.ps1`，直接输入标题。需要重做相同标题的另一条视频时增加 `-New`。

配置位于 `movelyth.toml`：默认中文，B站约 3 分钟横版，抖音约 1 分钟独立编排的竖版；实际时长由旁白决定，输出 1080p / 30fps。默认单渲染并发、编码 2 线程，避免占满机器。

时长目标用于创作参考，硬范围单独配置：默认横版 120–300 秒、竖版 45–90 秒。程序分别检查文件与配音时间轴是否一致、成片是否落在允许范围；审片不会把参考目标当成精确截止时间。

Python 依赖解析锁定在 `uv.lock`，Node 依赖锁定在 `studio/package-lock.json`。需要严格复现 Python 环境时可使用 `uv sync --locked --extra dev`；setup.ps1 的 pip 路线用于普通安装。

## 一句话调用与日常管理

`skills/movelyth-video/` 提供可复用 Codex skill。把该目录放入 Codex skills 目录后，在项目或其父目录中可以说：

> 用 Movelyth 生成视频，标题是“矩阵，如何改变我们看到的世界”。

也支持对助手说“生成今日份视频”，由 skill 先读取历史与 idea 再选题。独立 CLI 的 `create` 需要明确标题，不会在后台自行定时启动。skill 自动发现取决于当前 Codex 会话；需要时可显式使用 `$movelyth-video`。

```powershell
.\.venv\Scripts\python.exe -m movelyth doctor
.\.venv\Scripts\python.exe -m movelyth create "标题"
.\.venv\Scripts\python.exe -m movelyth resume VID-000001
.\.venv\Scripts\python.exe -m movelyth status
.\.venv\Scripts\python.exe -m movelyth ideas
.\.venv\Scripts\python.exe -m movelyth assets
# 只生成并审核脚本，先不制作音视频：
.\.venv\Scripts\python.exe -m movelyth create "另一个标题" --plan-only
```

同题默认复用原任务和已验证交付，避免重复生成；`--new` 明确要求另建任务。失败不回收编号，修复后用 `resume`，有效的阶段和语音请求按 hash 缓存。

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
    发布文案.md
    素材来源与署名.md
    脚本.json / 研究记录.json / 质检报告.json / manifest.json
```

通过检查才写入待上传。完整解码、音轨、画幅、帧率、时长、音量、黑屏与采样运动检查之后，由独立 Agent 查看实际抽帧。审片拒绝会交回编导有限修复，程序问题或达到上限则保存为失败，不会静默输出无声或不完整的上传包。

上传由用户手动完成。发布后可以记录实际链接和数据；没有填的指标保持未知：

```powershell
.\.venv\Scripts\python.exe -m movelyth feedback VID-000001 --platform bilibili --url "你的真实视频链接" --views 123 --likes 8 --completion-rate 0.45
```

`assets` 将程序素材的使用镜头关联到真实成片反馈，仅作观察，不声称某个素材导致了高播放。

## 能力与限制

- 当前支持矩阵网格/图形变换、向量、正交投影、波形、网络、真实 SVD 图像重建与旋转三维点云，适合能用这些手段表达的科普题目。
- 角色是独立上下文的真实模型调用，默认串行协作。本地动画和声音阶段为确定性程序；没有把普通函数冒充多个模型 Agent。
- 任意剧情、写实人物、复杂实拍素材和完整论文复现尚未接入；不承诺任意标题都能得到高质量成片。
- 不依赖付费文生视频/音乐服务，但 Codex 会消耗账号额度，Edge TTS 依赖网络。本地渲染也需要时间、内存与磁盘。
- 技术检查和抽帧不能保证全片听感、发音、审美和所有领域事实。本版尚未内置 ASR 或人工实听，报告会如实记录；首次使用新主题/音色时建议上传前观看。
- 本版自建总控，参考仓库的用途和实际依赖见 [第三方说明](docs/third-party.md)，机制见 [架构文档](docs/architecture.md)。

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
npm.cmd --prefix studio run typecheck
```

`workspace/`、`delivery/`、模型日志、语音缓存、凭据与依赖均不进入 Git。不要把已有 `ready` 等同于用户已发布，也不要把导入脚本或渲染测试写成真实标题驱动的验收。

维护者：wenxvn · 1055602033@qq.com
仓库：https://github.com/wenxvn/Movelyth-From-Idea-to-Final-Cut
