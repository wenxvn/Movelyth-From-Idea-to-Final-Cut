# 对照实验工具（V2）

这些脚本不是产品代码，只用于**同一份已审脚本的 A/B**：脚本与配音文本不变，只换渲染器与声音，
这样"更好看/更好听"的差异才能归因到本轮改动，而不是模型这次写得不一样。

产物写入 `workspace/ab/`（已被 `.gitignore` 忽略）。

## 前提

- 本机有 Node + Chrome（Remotion 渲染），`studio/` 已 `npm ci`。
- **不需要 Codex**：脚本与研究都通过 `--import-film/--import-research` 导入，
  审片角色用 `mock/mock/reviewer.json` 预设。质检报告会写 `provider: mock`，
  不能当作真实模型审片。
- 需要联网做 Edge TTS。

## 步骤

```powershell
# 1. 从已审脚本派生对照脚本（只重排两个重叠节点 + 补齐 V2 默认方向）
.\.venv\Scripts\python.exe tools\ab\make_film.py

# 2. 用专用配置跑完整流水线（workspace 相同，交付到 delivery-ab/）
$env:MOVELYTH_CONFIG = "tools\ab\movelyth-ab.toml"
.\.venv\Scripts\python.exe -m movelyth create "梯度下降为什么能让模型逐步减少错误？" `
    --new --import-film workspace\ab\film-004-v2.json `
    --import-research workspace\VID-000004\research.json
```

脚本默认读取 `workspace/VID-000004/`（V1 已交付任务）作为输入，输出任务编号会递增；
把命令输出里的 `VID-xxxxxx` 记下来供下面的工具使用。

## 观察与测量

| 脚本 | 用途 |
|---|---|
| `build_props.py <VID> <out> <long\|short>` | 用已有 timelines 出静帧（storyboard 级） |
| `frame_spec.py <VID> <out> <cut> <frames>` | 指定帧号，配 `studio/` 里临时的 renderer 脚本看转场 |
| `tune_mix.py` | 不重渲染，直接在真实旁白上试配乐/音效平衡（秒级） |
| `analyze_mix.py` | 找出混音/原声比值最高的时间点 |
| `compare_audio.py` | 对比两版的句间停顿、语音占比、句级响度差 |
| `frame_diff.py` | 同一镜头相隔 6 秒的两帧差异（判断镜头是否真的在动） |

`tune_mix.py` / `analyze_mix.py` / `compare_audio.py` 里写死了 `VID-00000x` 编号，
换任务时改文件顶部的路径即可。

## 已知限制

- `mock` 审片不会真的看图；画面结论必须来自人工/逐帧抽检。
- 这些脚本只覆盖"同一脚本换渲染"的对照，不验证新 prompt 在真实模型上的采纳率。