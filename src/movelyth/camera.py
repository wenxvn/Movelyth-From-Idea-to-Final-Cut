"""Content-bound camera plans.

The camera is not a decoration: it establishes the whole picture first, then brings
the attention to the object the sentence is about.  A plan is computed in Python from
the *region box of the layer the event targets*, so the target is always a real object
in the scene — never a pair of coordinates guessed by a model.

Coordinate spaces:

* content/world space — the 1920×1080 (or 1080×1920) stage the layers are drawn in;
* viewport — what the camera shows, derived from ``scale`` and the focus centre;
* fixed layer — captions, footer and source line are drawn outside the camera
  transform in the renderer, so they never rotate or zoom with the content.

All numbers are bounded, and the focus solve keeps the viewport inside the stage, so a
focus never reveals empty paper beyond the composition.
"""
from __future__ import annotations

from .scenedsl import regions

STAGE = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
MAX_FOCUS_SCALE = 1.55
MIN_FOCUS_SCALE = 1.0
FOCUS_FILL = 0.86          # how much of the viewport the focused box should occupy
EASE_SECONDS = 0.7
RETURN_TO_OVERVIEW = True


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def focus_on(box: dict, orientation: str) -> dict:
    """Scale and centre that bring ``box`` into the middle of the viewport."""
    width, height = STAGE[orientation]
    box_w, box_h = max(1, box["w"]), max(1, box["h"])
    scale = _clamp(min(width / box_w, height / box_h) * FOCUS_FILL, MIN_FOCUS_SCALE, MAX_FOCUS_SCALE)
    cx = (box["x"] + box_w / 2) / width
    cy = (box["y"] + box_h / 2) / height
    # Keep the viewport inside the stage: at scale s the half-view is 0.5/s.
    half = 0.5 / scale
    cx = _clamp(cx, half, 1 - half)
    cy = _clamp(cy, half, 1 - half)
    return {"scale": round(scale, 4), "cx": round(cx, 4), "cy": round(cy, 4)}


def camera_plan(scene: dict, *, orientation: str, duration: float) -> list[dict]:
    """Keyframes: overview first, then a bounded focus per emphasis/reveal event.

    Only events whose ``target`` is a layer in this scene create a focus, so a camera
    move always points at something that exists.  The plan ends back at the overview
    when the scene has a conclusion, so the last frame is not cropped.
    """
    boxes = regions(orientation, scene.get("layout") or "diagram")
    layer_region = {layer["id"]: layer.get("region", "main") for layer in scene.get("layers") or []}
    plan = [{"at": 0.0, "mode": "overview", "scale": 1.0, "cx": 0.5, "cy": 0.5,
             "reason": "先建立全局上下文"}]
    events = sorted((event for event in scene.get("events_resolved") or []
                     if event.get("kind") in {"reveal", "emphasis", "compare", "transform"}),
                    key=lambda event: float(event["at"]))
    for event in events:
        target = event.get("target")
        if not target or target not in layer_region:
            continue
        box = boxes.get(layer_region[target])
        if not box:
            continue
        focus = focus_on(box, orientation)
        if focus["scale"] <= 1.001:
            continue
        plan.append({"at": round(float(event["at"]), 3), "mode": "focus", **focus,
                     "target": target, "reason": f"{event['kind']} {event['id']}"})
    if len(plan) > 1 and RETURN_TO_OVERVIEW:
        plan.append({"at": round(max(0.0, duration - EASE_SECONDS), 3), "mode": "overview",
                     "scale": 1.0, "cx": 0.5, "cy": 0.5, "reason": "回到全局，避免结论被裁切"})
    return plan


def validate_plan(plan: list[dict], *, orientation: str, duration: float) -> list[str]:
    """Problems a plan must not have before it reaches the renderer."""
    problems = []
    width, height = STAGE[orientation]
    for index, key in enumerate(plan):
        if not 0 <= float(key["at"]) <= duration + 1e-6:
            problems.append(f"相机关键帧 {index} 落在镜头外")
        if not MIN_FOCUS_SCALE <= float(key["scale"]) <= MAX_FOCUS_SCALE + 1e-6:
            problems.append(f"相机关键帧 {index} 的缩放越界：{key['scale']}")
        half_x, half_y = 0.5 / float(key["scale"]), 0.5 / float(key["scale"])
        if not (half_x - 1e-6 <= float(key["cx"]) <= 1 - half_x + 1e-6):
            problems.append(f"相机关键帧 {index} 的水平取景超出画面")
        if not (half_y - 1e-6 <= float(key["cy"]) <= 1 - half_y + 1e-6):
            problems.append(f"相机关键帧 {index} 的垂直取景超出画面")
        if index and float(key["at"]) < float(plan[index - 1]["at"]) - 1e-6:
            problems.append(f"相机关键帧 {index} 相对前一帧倒序")
        if width <= 0 or height <= 0:
            problems.append("舞台尺寸无效")
    return problems
