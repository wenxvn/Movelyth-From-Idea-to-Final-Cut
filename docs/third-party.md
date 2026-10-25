# 参考来源与依赖

本项目为自建编排器与程序动画实现，没有将上级 references/ 中六个项目整库 vendoring 进来。

- [Lunamos/paper2video](https://github.com/Lunamos/paper2video)：参考研究→脚本→声音→动画→质检→发布包的流程组织、数据诚实原则与语音时序思路。
- [Remotion](https://github.com/remotion-dev/remotion)：作为实际本地渲染依赖，锁定 4.0.538；画面 API 依据官方规范。Remotion 使用其自身许可，详见原项目 LICENSE.md。
- [mquhuy/remotion-skill](https://github.com/mquhuy/remotion-skill)：参考按帧动画与渲染验证的规范组织方式。
- [karlyma/paper2video](https://github.com/karlyma/paper2video)：参考轻量 Python 阶段编排的结构；本项目不使用其默认输出目录或机器路径。
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)：后续素材路线的候选，首版没有启动或直接集成该项目。
- [awesome-claude-video-skills](https://github.com/zhuyansen/awesome-claude-video-skills)：工具发现索引，未作为运行依赖。

实际 Python/Node 依赖分别在 pyproject.toml 与 studio/package-lock.json。源代码仓库保留各第三方许可；展示作品、外部配乐与图片不因此获得授权。本版配乐、音效和图像为程序生成。

Codex CLI 结构化调用依据 [OpenAI 官方文档](https://developers.openai.com/codex/noninteractive)。本项目调用用户已登录的 CLI，不复制账号凭据，也不把凭据存进配置或日志。CLI 自身的账号与用量由用户管理。
