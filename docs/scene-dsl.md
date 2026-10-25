# Scene DSL v1

版本号：`schema_version = 1`。Python 契约在 `src/movelyth/models.py`，渲染端类型在
`studio/src/types.ts`，布局常量在 `src/movelyth/scenedsl.py`，并由
`write_renderer_contracts()` 生成 `studio/src/generated/layout.json` 与
`studio/src/generated/scene-schema.json`。

模型只输出符合该契约的 JSON；制作进程只读取枚举、数字和短字符串，**从不执行模型生成的代码**。

## 1. 兼容性

- 旧任务（只有 `visual` + `matrix` + `labels`）仍可读取：`layers` 为空时自动退化为单个
  `procedural` 图层，画面与旧版一致。
- 新任务应显式写 `layers`，同一镜头可组合 1–6 个图层。
- `schema_version` 目前只接受 `1`。未来版本升级时，读取端按版本分派，旧 revision 不会被就地改写。

## 2. 结构

```json
{
  "schema_version": 1,
  "id": "gradient_descent",
  "heading": "误差在下降",
  "narration": "每一次更新，都在寻找更小的误差。",
  "visual": "matrix",
  "matrix": [1, 0, 0, 1],
  "color": "cyan",
  "source_index": 0,
  "layout": "diagram",
  "beats": [{"at": "start", "purpose": "展示初始误差"},
            {"at": "narration:更小的误差", "purpose": "强调损失下降"}],
  "layers": [
    {"id": "loss", "type": "chart", "chart": "line", "region": "main",
     "series": [{"label": "损失", "values": [0.9, 0.6, 0.35, 0.2], "unit": ""}],
     "axis": "更新轮次", "source_note": "示意", "color": "cyan", "emphasis": 1},
    {"id": "note", "type": "text", "text": "梯度下降示意", "region": "annotation"}
  ],
  "actions": [
    {"target": "loss", "kind": "draw", "start": "start", "end": "narration:更小的误差"},
    {"target": "note", "kind": "appear", "start": "0.6", "end": "0.8"}
  ],
  "visual_intent": "折线真实反映每轮误差下降，用于说明损失降低而非装饰。"
}
```

### 图层类型

| type | 用途 | 关键参数 |
|---|---|---|
| `text` | 短文本/注解 | `text` ≤120 字，`emphasis` 1–3 |
| `math` | 公式行（Unicode `^`/`_`） | `text` |
| `shape` | 点/线/矩形/圆/箭头/多边形/括号 | `shape`、`points`（x,y 对，0–1000 / 0–640） |
| `chart` | 折线/柱状/散点 | `chart`、`series` 或本地 `data_ref`、`unit`、`axis`、`source_note` |
| `diagram` | 有向节点图 | `nodes`（2–12）、`edges`、`steps`（≤6） |
| `image` | 本地受控素材 | `data_ref` 为已登记素材 id（`movelyth asset-add`）或内置 `svd_1/4/12/32` |
| `procedural` | 原有七类程序动画 | `procedural` = matrix/vectors/projection/wave/network/image_layers/orbit |

### 布局与区域

`layout`：`immersive`（全屏沉浸）、`diagram`（图解讲解）、`compare`（左右/上下对照）。
`region`：`main`、`side`、`top`、`bottom`、`annotation`、`full`。每个布局的矩形由 Python 定义并生成给
TypeScript，两侧不会各自漂移。

保留区：标题区、标签区、字幕区、页脚区。图层不得与之重叠，脚本审批前即报错。

### 节拍与动画

`at` / `start` / `end` 支持：

- `start` / `end`：镜头起止；
- `0`–`1` 的小数：镜头内比例；
- `narration:片段`：该片段在旁白中**第一次出现**的位置，按真实 Edge TTS 词语边界换算成秒。

动画原语：`appear`、`fade`、`move`、`scale`、`rotate`、`highlight`、`draw`、`morph`。
`morph` 目前以淡入实现，属于已知限制（报告会记录）。动画只依赖 props 与 frame，可确定性复现。

## 3. 校验边界

- 文本长度、坐标范围、元素数量、帧数、时长全部有上限；拒绝 `NaN`/`Infinity`、超大列表。
- `data_ref` 只能是小写标识符，不能是路径或 URL；`image` 只能引用受控素材目录中已存在的文件
  （内置 SVD 图或 `movelyth asset-add` 登记的素材，登记时会校验 hash 与授权字段）。
- `chart` 必须由 `series` 或 `workspace/VID-xxxxxx/data/<data_ref>.json` 提供真实数值，缺失时在渲染前报错。
  数据文件格式：`{"label": "误差", "unit": "%", "axis": "轮次", "values": [0.9, 0.6, 0.3]}`，
  或 `{"series": [{"label": "...", "values": [...]}, ...]}`；上限 256 KB、每序列 2–60 个有限数。
- 旁白与画面一致性检查见 `consistency.py`：数据趋势、面积/长度/塌缩断言、示意数据被说成实测等。
- 渲染器无法表达的动作或数据在脚本审批阶段拒绝，不会退化成一张无关的通用图。

## 4. 生成与校验命令

```powershell
# 重新生成渲染端契约（修改布局或模型后必须执行）
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from pathlib import Path; from movelyth.scenedsl import write_renderer_contracts; write_renderer_contracts(Path('studio/src'))"

# 查看当前 JSON Schema
.\.venv\Scripts\python.exe -m movelyth schema
```

`tests/test_scenedsl.py` 会比对已提交的生成文件与 Python 契约、TypeScript 枚举与 Pydantic 枚举，
任何一侧漂移都会失败。
