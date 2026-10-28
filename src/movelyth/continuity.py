"""Object continuity and real geometry morphs.

Two claims this module makes checkable:

**Shared objects.**  A ``subject_id`` that appears in several scenes must keep its
identity — same colour, same meaning — and its declared before/after states must line
up with the neighbouring scene.  A card that turns into a chart point is a shared
object; a card that silently changes colour between shots is a continuity defect.

**Morphs.**  A ``morph`` action is only a *geometry* morph when the target has the same
vertex count (same topology).  Otherwise it stays the pre-v2 crossfade, and the plan
says so — a rounded-rectangle demo is not "arbitrary shape morphing".
"""
from __future__ import annotations

from .models import Layer, Scene

MAX_PAIRS = 32


def subject_states(scenes: list[Scene]) -> dict[str, list[dict]]:
    """Every appearance of a subject, in scene order."""
    seen: dict[str, list[dict]] = {}
    for scene in scenes:
        for layer in scene.layers:
            if not layer.subject_id:
                continue
            seen.setdefault(layer.subject_id, []).append({
                "scene": scene.id, "layer": layer.id, "type": layer.type,
                "color": layer.color, "state_before": layer.state_before,
                "state_after": layer.state_after,
                "label": layer.text or layer.axis or (layer.series[0].label if layer.series else ""),
            })
    return seen


def continuity_report(scenes: list[Scene]) -> dict:
    """Problems that break the identity of a shared object across scenes."""
    subjects = subject_states(scenes)
    problems, shared, transitions = [], [], []
    for subject_id, appearances in subjects.items():
        colours = {item["color"] for item in appearances}
        if len(colours) > 1:
            problems.append(f"主体 {subject_id} 在不同镜头换了颜色：{sorted(colours)}")
        labels = {item["label"] for item in appearances if item["label"]}
        if len(labels) > 1:
            problems.append(f"主体 {subject_id} 在不同镜头叫法不同：{sorted(labels)[:3]}")
        if len(appearances) > 1:
            shared.append({"subject_id": subject_id, "scenes": [item["scene"] for item in appearances],
                           "types": sorted({item["type"] for item in appearances})})
        for previous, current in zip(appearances, appearances[1:], strict=False):
            if previous["state_after"] and current["state_before"] and \
                    previous["state_after"] != current["state_before"]:
                problems.append(f"主体 {subject_id} 在 {previous['scene']} 之后是"
                                f"“{previous['state_after']}”，但 {current['scene']} 开始时是"
                                f"“{current['state_before']}”")
            if previous["state_after"] or current["state_before"]:
                transitions.append({"subject_id": subject_id,
                                    "from": previous["scene"], "to": current["scene"],
                                    "state": current["state_before"] or previous["state_after"]})
    return {"problems": problems, "shared": shared, "transitions": transitions,
            "subjects": sorted(subjects),
            "note": "共享对象只检查身份一致性；不检查语义是否相同"}


def morph_plan(layer: Layer, action) -> dict:
    """What a morph action will actually do for this layer and target."""
    if action.kind != "morph":
        return {"mode": "not-a-morph", "ok": True}
    if action.morph_mode != "geometry":
        return {"mode": "crossfade", "ok": True,
                "note": "crossfade 是 v1/v2 的淡入淡出语义，不是几何形变"}
    if layer.type != "shape":
        return {"mode": "unsupported", "ok": False,
                "reason": f"{layer.type} 图层不支持几何形变（只支持 shape 多边形/折线）"}
    if len(layer.points) % 2 or len(action.target_points) % 2:
        return {"mode": "unsupported", "ok": False, "reason": "坐标必须成对"}
    source_pairs = len(layer.points) // 2
    target_pairs = len(action.target_points) // 2
    if source_pairs != target_pairs:
        return {"mode": "unsupported", "ok": False,
                "reason": f"顶点数不同（{source_pairs} → {target_pairs}），"
                          "只能显式 crossfade，不能声称几何形变"}
    if not 2 <= source_pairs <= MAX_PAIRS:
        return {"mode": "unsupported", "ok": False,
                "reason": f"顶点数 {source_pairs} 超出 2–{MAX_PAIRS} 的支持范围"}
    return {"mode": "geometry", "ok": True, "vertices": source_pairs,
            "source": list(layer.points), "target": list(action.target_points)}


def morph_problems(scenes: list[Scene]) -> list[str]:
    """Every morph in the film, checked against its layer."""
    problems = []
    for scene in scenes:
        layers = {layer.id: layer for layer in scene.layers}
        for action in scene.actions:
            if action.kind != "morph":
                continue
            layer = layers.get(action.target)
            if layer is None:
                problems.append(f"镜头 {scene.id} 的形变目标 {action.target} 不存在")
                continue
            plan = morph_plan(layer, action)
            if not plan["ok"]:
                problems.append(f"镜头 {scene.id} 的形变 {action.target}：{plan['reason']}")
    return problems


def interpolate(source: list[float], target: list[float], progress: float) -> list[float]:
    """Vertex-wise interpolation; the renderer uses the same arithmetic."""
    k = max(0.0, min(1.0, float(progress)))
    return [round(a + (b - a) * k, 4) for a, b in zip(source, target, strict=True)]


def formula_tokens(text: str) -> list[str]:
    """Split a formula into comparable tokens so a shared symbol can be tracked."""
    import re

    return [token for token in re.findall(r"[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|[^\sA-Za-z0-9]", str(text or ""))
            if token.strip()]


def formula_correspondence(before: str, after: str) -> dict:
    """Which tokens survive a formula change, in order."""
    left, right = formula_tokens(before), formula_tokens(after)
    shared = [token for token in left if token in right]
    return {"before": left, "after": right, "shared": shared,
            "kept_ratio": round(len(shared) / max(1, len(left)), 3),
            "note": "只比较符号是否保留；不检查公式是否等价"}
