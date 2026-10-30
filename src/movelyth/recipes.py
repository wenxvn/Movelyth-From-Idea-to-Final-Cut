"""Shot recipes: the small set of visual moves a director may choose from.

A recipe is not a new layer kind.  It is a named, reviewable combination of the
layers, events and checks that already exist, with the bindings it needs and the
verification that proves it was used as intended.  The director may only select a
recipe that is *implemented* and applicable to the scene's content; anything else is
rejected before a render is paid for.
"""
from __future__ import annotations

# id → contract.  ``requires`` is what the scene must contain; ``checks`` names the
# deterministic verification a scene using the recipe must pass.
RECIPES: dict[str, dict] = {
    "chart-focus": {
        "purpose": "把注意力带到曲线上的一个真实数据点，并说明它为什么重要",
        "requires": {"layer_types": ["chart"], "min_series": 1, "annotations": 1},
        "events": ["reveal", "emphasis"],
        "orientations": ["landscape", "portrait"],
        "limits": "注释 x 必须是真实数据坐标；聚焦范围不超过绘图区",
        "semantic_conditions": ["旁白正在解释一个具体样本、拐点或异常值"],
        "timeline": [
            {"phase": "建立全图", "span": [0.0, 0.22], "focus": "全部序列与坐标轴",
             "action": "先让图表完整出现"},
            {"phase": "指出数据点", "span": [0.22, 0.7], "focus": "annotation 对应的真实 x 值",
             "action": "高亮该点并显示数值"},
            {"phase": "留出阅读", "span": [0.7, 1.0], "focus": "数据点及相邻趋势",
             "action": "停住镜头，让观众比较前后关系"},
        ],
        "dynamic_demo": "曲线先完整显示；旁白说到拐点时，高亮落在真实采样值上；随后停稳并保留坐标上下文。",
        "failure_examples": ["高亮落在两个样本之间", "放大后丢失坐标尺度", "持续脉冲导致读数不稳"],
        "checks": ["annotation-on-data", "hero-exists"],
    },
    "same-scale-compare": {
        "purpose": "同一尺度下对照两条序列，让差异自己显现",
        "requires": {"layer_types": ["chart"], "min_series": 2, "shared_unit": True},
        "events": ["compare", "reveal"],
        "orientations": ["landscape", "portrait"],
        "limits": "两条序列单位必须一致；不允许各自缩放",
        "semantic_conditions": ["解释目标是比较两组数值的差异"],
        "timeline": [
            {"phase": "建立共同尺度", "span": [0.0, 0.24], "focus": "共同坐标轴与两条序列",
             "action": "同时建立单位、范围和图例"},
            {"phase": "呈现差异", "span": [0.24, 0.68], "focus": "同一 x 位置上的成对值",
             "action": "标记差值，不改变任一序列的比例"},
            {"phase": "稳定比较", "span": [0.68, 1.0], "focus": "完整两组数据",
             "action": "停稳保留图例和坐标刻度"},
        ],
        "dynamic_demo": "两组数据共用同一坐标轴；差异出现时只标差值，结束时完整图例与单位仍在画面内。",
        "failure_examples": ["左右图分别缩放", "切换序列时单位或颜色改变", "差值标签盖住数据点"],
        "checks": ["shared-unit", "annotation-on-data"],
    },
    "parameter-process": {
        "purpose": "让一个参数驱动坐标、数值和标签，展示过程的每一步",
        "requires": {"layer_types": ["procedural"], "procedural": ["vectors", "projection", "matrix"]},
        "events": ["transform", "reveal"],
        "orientations": ["landscape", "portrait"],
        "limits": "参数来自受控函数或 series；模型不能各写一份互不相干的假数据",
        "semantic_conditions": ["关键结论取决于某个参数的变化过程"],
        "timeline": [
            {"phase": "给出初态", "span": [0.0, 0.2], "focus": "受控参数和初始几何",
             "action": "显示同一组数据的起点"},
            {"phase": "执行变化", "span": [0.2, 0.72], "focus": "参数、几何与数值的共同变化",
             "action": "由一个受控函数同步驱动"},
            {"phase": "停在结果", "span": [0.72, 1.0], "focus": "最终几何和计算值",
             "action": "保持读数，给结论留出时间"},
        ],
        "dynamic_demo": "同一参数驱动图形坐标和屏幕数值；运动结束后保留最终结果，不另造一组解释数字。",
        "failure_examples": ["几何和标签各用一套数据", "运动未结束旁白就报结果", "只移动装饰线而主体不变"],
        "checks": ["controlled-parameters", "hero-exists"],
    },
    "flow-expand": {
        "purpose": "沿一条路径逐步展开过程，再进入节点内部",
        "requires": {"layer_types": ["diagram"], "min_steps": 2},
        "events": ["reveal", "transform"],
        "orientations": ["landscape", "portrait"],
        "limits": "节点不重叠、不出界；连线必须引用已有节点",
        "semantic_conditions": ["概念由有方向的步骤、状态或传递关系构成"],
        "timeline": [
            {"phase": "建立路径", "span": [0.0, 0.22], "focus": "全部节点及方向",
             "action": "先显示完整路径和必要上下文"},
            {"phase": "沿路展开", "span": [0.22, 0.7], "focus": "当前节点和关联连线",
             "action": "按真实顺序逐步揭示"},
            {"phase": "停在关键节点", "span": [0.7, 1.0], "focus": "当前节点及前后关系",
             "action": "保留足够上下文供阅读"},
        ],
        "dynamic_demo": "完整流程先建立方向；随后按状态顺序点亮节点与边；最后停在解释目标上并保留前后节点。",
        "failure_examples": ["高亮节点与旁白步骤不对应", "聚焦后看不见路径方向", "步骤标签重复或遮挡节点"],
        "checks": ["diagram-geometry"],
    },
    "paper-evidence": {
        "purpose": "把一段来源文字/公式放到纸面上，圈注关键处并保留出处",
        "requires": {"layer_types_any": ["text", "math"], "source_note": True},
        "events": ["reveal", "emphasis"],
        "orientations": ["landscape", "portrait"],
        "limits": "圈注不遮挡单位与数字；数值几何保持精确",
        "semantic_conditions": ["需要核对来源原文、定义、公式或有限证据片段"],
        "timeline": [
            {"phase": "展示证据", "span": [0.0, 0.28], "focus": "原句或公式及出处",
             "action": "先让文本和来源完整可见"},
            {"phase": "标记关键处", "span": [0.28, 0.68], "focus": "一段实际存在的证据",
             "action": "圈注只强调，不遮掉条件或单位"},
            {"phase": "读完再收束", "span": [0.68, 1.0], "focus": "证据与来源",
             "action": "停留后再进入下一镜"},
        ],
        "dynamic_demo": "来源和原句先完整出现；圈注只框住支持结论的部分；镜头停稳时保留条件、单位与出处。",
        "failure_examples": ["圈注遮住否定词或单位", "正文未见却用动画假装高亮", "只展示结论不留来源"],
        "checks": ["source-note-present", "annotation-on-data"],
    },
    "conclusion-callback": {
        "purpose": "回扣开场问题，用一句话和一条主张收束",
        "requires": {"layer_types": ["text"], "claim_ids": 1},
        "events": ["conclude", "emphasis"],
        "orientations": ["landscape", "portrait"],
        "limits": "结论不得超出已核对主张的适用范围",
        "semantic_conditions": ["本镜负责回答开场问题或总结已验证主张"],
        "timeline": [
            {"phase": "回到问题", "span": [0.0, 0.24], "focus": "开场问题或预测",
             "action": "唤回观众正在等待的答案"},
            {"phase": "给出结论", "span": [0.24, 0.68], "focus": "绑定的 claim 与结果图形",
             "action": "让结论和实际演示同时成立"},
            {"phase": "留白收束", "span": [0.68, 1.0], "focus": "结论本身",
             "action": "保持稳定，不继续添加新信息"},
        ],
        "dynamic_demo": "开场的具体问题再次出现；已验证的结果与对应图形同屏呈现；最后停稳，结论不引入新范围。",
        "failure_examples": ["结论新增来源未支持的范围", "画面只重复标题没有结果", "结尾运动干扰结论阅读"],
        "checks": ["claim-binding"],
    },
}


def implemented() -> dict[str, dict]:
    return {name: spec for name, spec in RECIPES.items()}


class _LayerView:
    """Read a layer from a Pydantic model or a plain dict with the same field names."""

    __slots__ = ("raw",)

    def __init__(self, raw):
        self.raw = raw

    def __getattr__(self, name):
        if isinstance(self.raw, dict):
            return self.raw.get(name)
        return getattr(self.raw, name)


class _SceneView:
    __slots__ = ("raw",)

    def __init__(self, raw):
        self.raw = raw

    def __getattr__(self, name):
        if isinstance(self.raw, dict):
            value = self.raw.get(name)
            if name == "layers":
                return [_LayerView(layer) for layer in value or []]
            return value
        if name == "layers":
            return [_LayerView(layer) for layer in self.raw.layers]
        return getattr(self.raw, name)


def applicable(scene) -> list[str]:
    """Recipes whose bindings this scene already satisfies (model or dict)."""
    scene = _SceneView(scene)
    names = []
    layer_types = {layer.type for layer in scene.layers}
    for name, spec in RECIPES.items():
        requires = spec["requires"]
        if not set(requires.get("layer_types") or []) <= layer_types:
            continue
        if requires.get("layer_types_any") and not set(requires["layer_types_any"]) & layer_types:
            continue
        charts = [layer for layer in scene.layers if layer.type == "chart"]
        if requires.get("min_series"):
            if not any(len(layer.series or []) >= requires["min_series"] for layer in charts):
                continue
        if requires.get("shared_unit"):
            units = {series.get("unit") if isinstance(series, dict) else series.unit
                     for layer in charts for series in (layer.series or [])}
            if len(units) != 1:
                continue
        if requires.get("annotations"):
            if not any(layer.annotations for layer in charts):
                continue
        if requires.get("procedural"):
            if not any(layer.procedural in requires["procedural"] for layer in scene.layers):
                continue
        if requires.get("min_steps"):
            if not any(len(layer.steps or []) >= requires["min_steps"] for layer in scene.layers):
                continue
        if requires.get("source_note"):
            if not any((layer.source_note or "").strip() for layer in scene.layers):
                continue
        if requires.get("claim_ids"):
            if len(scene.claim_ids or []) < requires["claim_ids"]:
                continue
        names.append(name)
    return names


def guidance_for_scene(scene) -> dict[str, dict]:
    """Return dynamic recipe guidance only for recipes this scene can satisfy.

    The result is suitable for a scene-scoped director/revision prompt; it avoids
    suggesting a chart recipe to a scene that contains only a diagram, for example.
    """
    names = applicable(scene)
    fields = ("purpose", "semantic_conditions", "timeline", "dynamic_demo",
              "failure_examples", "limits", "checks")
    return {name: {field: RECIPES[name][field] for field in fields}
            for name in names}


def choose(scene) -> str:
    """The recipe a scene actually uses: its declared one, else the first applicable."""
    declared = _SceneView(scene).recipe
    if declared:
        return declared
    candidates = applicable(scene)
    return candidates[0] if candidates else ""


def recipe_warnings(scene) -> list[str]:
    """A scene outside the six recipes is allowed, but worth reporting."""
    view = _SceneView(scene)
    if view.recipe or applicable(scene):
        return []
    return [f"镜头 {view.id} 没有匹配到已登记配方（可用图层组合仍然合法）"]


def validate_scene_recipe(scene) -> list[str]:
    """Problems that must be fixed before rendering (empty means the recipe holds)."""
    view = _SceneView(scene)
    problems: list[str] = []
    if not view.recipe:
        return problems
    if view.recipe not in RECIPES:
        problems.append(f"镜头 {view.id} 选择了未实现的配方 {view.recipe}")
        return problems
    if view.recipe not in applicable(scene):
        spec = RECIPES[view.recipe]
        problems.append(f"镜头 {view.id} 的配方 {view.recipe} 不适用：需要 "
                        f"{spec['requires']}")
    return problems


def check_scene(scene) -> list[str]:
    """Deterministic verification for the recipe's declared checks."""
    results: list[str] = []
    recipe = choose(scene)
    if not recipe:
        return results
    view = _SceneView(scene)
    checks = RECIPES[recipe]["checks"]
    charts = [layer for layer in view.layers if layer.type == "chart"]
    if "annotation-on-data" in checks:
        for layer in charts:
            xs = [value for series in (layer.series or [])
                  for value in ((series.get("x_values") if isinstance(series, dict) else series.x_values)
                                or list(range(len(series.get("values") if isinstance(series, dict)
                                                      else series.values))))]
            for annotation in layer.annotations or []:
                x = annotation.get("x") if isinstance(annotation, dict) else annotation.x
                if xs and min(abs(x - value) for value in xs) > max(1e-6, (max(xs) - min(xs)) * 0.12):
                    results.append(f"镜头 {view.id} 的注释 x={x} 离真实数据点过远")
    if "shared-unit" in checks:
        units = {(series.get("unit") if isinstance(series, dict) else series.unit)
                 for layer in charts for series in (layer.series or [])}
        if len(units) > 1:
            results.append(f"镜头 {view.id} 的对照序列单位不一致：{sorted(units)}")
    if "hero-exists" in checks:
        drawing = [layer.id for layer in view.layers if layer.type in {"chart", "diagram", "procedural"}]
        identifiers = {layer.id for layer in view.layers}
        if view.hero and view.hero not in identifiers:
            results.append(f"镜头 {view.id} 的 hero 指向不存在的图层")
        elif not view.hero and not drawing:
            results.append(f"镜头 {view.id} 没有可作主角的图形层")
    if "diagram-geometry" in checks:
        for layer in view.layers:
            if layer.type != "diagram":
                continue
            identifiers = {node.get("id") if isinstance(node, dict) else node.id
                           for node in layer.nodes or []}
            edges = layer.edges or []
            if any((edge.get("source") if isinstance(edge, dict) else edge.source) not in identifiers
                   or (edge.get("target") if isinstance(edge, dict) else edge.target) not in identifiers
                   for edge in edges):
                results.append(f"镜头 {view.id} 的连线引用了不存在的节点")
    if "source-note-present" in checks:
        if not any((layer.source_note or "").strip() for layer in view.layers):
            results.append(f"镜头 {view.id} 的纸面证据缺少 source_note")
    if "claim-binding" in checks and not (view.claim_ids or []):
        results.append(f"镜头 {view.id} 的结论没有绑定 claim_ids")
    if "controlled-parameters" in checks:
        for layer in view.layers:
            if layer.type == "procedural" and layer.procedural in {"vectors", "projection"}:
                series = layer.series or []
                values = (series[0].get("values") if isinstance(series[0], dict) else series[0].values)                     if series else []
                if series and len(values) < 2:
                    results.append(f"镜头 {view.id} 的参数序列不足两个值")
    return results


def catalog() -> dict:
    """Reviewable list for prompts and `movelyth components`."""
    return {"recipes": RECIPES,
            "note": "只有这里登记的配方可被编导选择；未登记的配方会在渲染前被拒绝"}
