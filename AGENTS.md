# Movelyth — 幕绎

多智能体驱动的全流程 AI 视频创作引擎。From Idea to Final Cut.

- 使用简体中文交流；维护者 wenxvn，联系邮箱 1055602033@qq.com。
- 首版本地程序动画优先，付费图像/视频/音乐服务不自动启用。
- 修改代码前检查 Git 状态；保留已有用户修改。第三方参考仓库位于上级 references/，不要修改或整库复制进本项目。
- 创作由独立上下文的研究、编导和审片角色协作，编排器拥有状态、缓存、渲染和交付；不把简单阶段函数虚称独立模型 Agent。
- 生成文件、数据库、配音缓存、模型运行日志、依赖和密钥不提交 Git。用户素材与已交付版本不可自动覆盖清理。
- 运行外部程序使用参数数组，禁止执行模型提供的 shell 或代码。模型只生成受约束的结构化内容。
- 修改后运行相关 pytest、TypeScript 检查与必要的媒体验证；明确区分模拟、人工提供脚本和真实标题驱动的端到端验证。
- 任务状态、能力边界、取舍理由与验收证据只维护在 `docs/optimization/`（execution / capabilities /
  decisions / acceptance）与 `docs/verification.md`；不要另建变更日志或重复记录同一结论。
- 只有当前 revision 的适用必需检查全部通过才 `ready`；`unknown` 不记 0，`ready` 不等于 `published`，
  未知反馈同样不记为 0。
- 改动契约（`models.py`/`scenedsl.py`/`studio/src/types.ts`）后必须重新生成渲染端契约并提交差异：
  `python -c "from pathlib import Path; from movelyth.scenedsl import write_renderer_contracts; write_renderer_contracts(Path('studio/src'))"`
