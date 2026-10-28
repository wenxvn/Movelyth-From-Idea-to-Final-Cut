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
        "checks": ["annotation-on-data", "hero-exists"],
    },
    "same-scale-compare": {
        "purpose": "同一尺度下对照两条序列，让差异自己显现",
        "requires": {"layer_types": ["chart"], "min_series": 2, "shared_unit": True},
        "events": ["compare", "reveal"],
        "orientations": ["landscape", "portrait"],
        "limits": "两条序列单位必须一致；不允许各自缩放",
        "checks": ["shared-unit", "annotation-on-data"],
    },
    "parameter-process": {
        "purpose": "让一个参数驱动坐标、数值和标签，展示过程的每一步",
        "requires": {"layer_types": ["procedural"], "procedural": ["vectors", "projection", "matrix"]},
        "events": ["transform", "reveal"],
        "orientations": ["landscape", "portrait"],
        "limits": "参数来自受控函数或 series；模型不能各写一份互不相干的假数据",
        "checks": ["controlled-parameters", "hero-exists"],
    },
    "flow-expand": {
        "purpose": "沿一条路径逐步展开过程，再进入节点内部",
        "requires": {"layer_types": ["diagram"], "min_steps": 2},
        "events": ["reveal", "transform"],
        "orientations": ["landscape", "portrait"],
        "limits": "节点不重叠、不出界；连线必须引用已有节点",
        "checks": ["diagram-geometry"],
    },
    "paper-evidence": {
        "purpose": "把一段来源文字/公式放到纸面上，圈注关键处并保留出处",
        "requires": {"layer_types_any": ["text", "math"], "source_note": True},
        "events": ["reveal", "emphasis"],
        "orientations": ["landscape", "portrait"],
        "limits": "圈注不遮挡单位与数字；数值几何保持精确",
        "checks": ["source-note-present", "annotation-on-data"],
    },
    "conclusion-callback": {
        "purpose": "回扣开场问题，用一句话和一条主张收束",
        "requires": {"layer_types": ["text"], "claim_ids": 1},
        "events": ["conclude", "emphasis"],
        "orientations": ["landscape", "portrait"],
        "limits": "结论不得超出已核对主张的适用范围",
        "checks": ["claim-binding"],
    },
}


def implemented() -> dict[str, dict]:
    return {name: spec for name, spec in RECIPES.items()}


def recipe_ids() -> list[str]:
    return sorted(RECIPES)


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
