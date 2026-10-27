# 参考来源与依赖

本项目为自建编排器与程序动画实现，没有将上级 references/ 中六个项目整库 vendoring 进来。

- [Lunamos/paper2video](https://github.com/Lunamos/paper2video)：参考研究→脚本→声音→动画→质检→发布包的流程组织、数据诚实原则与语音时序思路。
- [Remotion](https://github.com/remotion-dev/remotion)：作为实际本地渲染依赖，锁定 4.0.538；画面 API 依据官方规范。Remotion 使用其自身许可，详见原项目 LICENSE.md。
- [mquhuy/remotion-skill](https://github.com/mquhuy/remotion-skill)：参考按帧动画与渲染验证的规范组织方式。
- [karlyma/paper2video](https://github.com/karlyma/paper2video)：参考轻量 Python 阶段编排的结构；本项目不使用其默认输出目录或机器路径。
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)：后续素材路线的候选，首版没有启动或直接集成该项目。
- [awesome-claude-video-skills](https://github.com/zhuyansen/awesome-claude-video-skills)：工具发现索引，未作为运行依赖。
- [Vincentwei1021/anything2explainer](https://github.com/Vincentwei1021/anything2explainer)：V3 参考其
  「一个主角 + 光 + 高光时刻」的构图规则、动效词汇表（SoftIn/GlitchIn/CameraRig）与
  「每句一个可察觉变化 / 末拍停留」的量化判据，以及主体高度、空场、柔光面积等帧级 QC 指标。
  许可证为 PolyForm Noncommercial，**未复制其代码或资产**，只借鉴公开文档里的设计原则与阈值。
- [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage)：参考其管线/阶段/交付契约与
  「运镜与转场是硬需求」的立场；AGPL-3.0，未 vendoring。
- [Alon17-12/remotion-ad-video-skill](https://github.com/Alon17-12/remotion-ad-video-skill)、
  [JonnyFi/adforge](https://github.com/JonnyFi/adforge)：参考其「少而软的合成音效」「每个修复用帧证明」
  与节拍对齐的工程做法；MIT / 未集成。
- [cutroom](https://github.com/Young-1231/cutroom)、[PySceneDetect](https://github.com/Breakthrough/PySceneDetect)：
  参考「先记录再剪辑、每个剪辑有依据」；未接入其场景检测（Movelyth 是程序动画，镜头边界由脚本给出）。
- Qwen3-TTS、IndexTTS、Qwen3-ForcedAligner、AudioLDM2、AudioSFX：**本轮只做技术调研，未安装、
  未下载权重、未调用**。原因：需要 GPU/数 GB 权重或为 CC BY-NC，与「无 GPU 也能跑、程序合成、
  无授权风险」的现有约束冲突；接口位置见 `docs/v3-plan.md` 的 P1-6/P2。

实际 Python/Node 依赖分别在 pyproject.toml 与 studio/package-lock.json。源代码仓库保留各第三方许可；展示作品、外部配乐与图片不因此获得授权。本版配乐、音效和图像为程序生成。

Codex CLI 结构化调用依据 [OpenAI 官方文档](https://developers.openai.com/codex/noninteractive)。本项目调用用户已登录的 CLI，不复制账号凭据，也不把凭据存进配置或日志。CLI 自身的账号与用量由用户管理。

## 模型端点

`provider = "openai"` 时通过标准 `/chat/completions` 协议调用任意兼容端点，代码只依赖该协议本身
（`Authorization: Bearer`、`response_format`、`image_url` 内容块），没有绑定任何厂商的 SDK。
已验证端点：DeepSeek 官方 `api.deepseek.com/v1`（`deepseek-flash`、`deepseek-v4-pro`）。
`json_schema` 在部分端点上不可用，因此实现为三级降级：`json_schema` → `json_object` → 纯提示词 +
内联 schema。密钥只从环境变量读取，不写入 `movelyth.toml`，也不写进日志或交付包。