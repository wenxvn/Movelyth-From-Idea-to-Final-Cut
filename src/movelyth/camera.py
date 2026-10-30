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

import math

from .charts import nice_domain
from .scenedsl import regions

STAGE = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
MAX_FOCUS_SCALE = 1.55
POINT_FOCUS_MAX_SCALE = 1.12
MESSAGE_FOCUS_MAX_SCALE = 1.12
MIN_FOCUS_SCALE = 1.0
FOCUS_FILL = 0.86          # how much of the viewport the focused box should occupy
EASE_SECONDS = 0.7
RETURN_TO_OVERVIEW = True
POINT_CONTEXT = {"w": 180, "h": 140}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_inside_view(value: float, half: float) -> float:
    """Round a normalized centre inward so serialization cannot cross the viewport edge."""
    low = math.ceil(half * 10_000 - 1e-9) / 10_000
    high = math.floor((1 - half) * 10_000 + 1e-9) / 10_000
    return round(_clamp(value, low, high), 4)


def focus_on(box: dict, orientation: str, *, max_scale: float = MAX_FOCUS_SCALE) -> dict:
    """Scale and centre that bring ``box`` into the middle of the viewport."""
    width, height = STAGE[orientation]
    box_w, box_h = max(1, box["w"]), max(1, box["h"])
    scale_cap = _clamp(float(max_scale), MIN_FOCUS_SCALE, MAX_FOCUS_SCALE)
    scale = round(_clamp(min(width / box_w, height / box_h) * FOCUS_FILL,
                         MIN_FOCUS_SCALE, scale_cap), 4)
    cx = (box["x"] + box_w / 2) / width
    cy = (box["y"] + box_h / 2) / height
    # Keep the viewport inside the stage: at scale s the half-view is 0.5/s.
    half = 0.5 / scale
    cx = _round_inside_view(cx, half)
    cy = _round_inside_view(cy, half)
    return {"scale": scale, "cx": cx, "cy": cy}


def _field(value, name: str, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _js_round(value: float) -> int:
    """Match JavaScript Math.round for non-negative renderer font dimensions."""
    return math.floor(value + 0.5)


def _chart_point_box(layer: dict, x_value: float, region: dict) -> dict | None:
    """Map a chart's real sample to stage coordinates using ChartLayer's scales."""
    series = layer.get("series") or []
    if not series:
        # data_ref is resolved in the renderer; without that dataset there is no
        # trustworthy point geometry to focus on.
        return None
    rows = []
    for item in series:
        values = [float(v) for v in _field(item, "values", []) or []]
        x_values = [float(v) for v in _field(item, "x_values", []) or []]
        if len(values) < 2:
            continue
        rows.append({"values": values, "x_values": x_values})
    if not rows:
        return None

    explicit_x = all(len(item["x_values"]) == len(item["values"]) for item in rows)

    def is_constant(item):
        return all(abs(value - item["values"][0]) < 1e-9 for value in item["values"])

    def is_marker(item):
        return (explicit_x and item["x_values"]
                and all(abs(value - item["x_values"][0]) < 1e-9 for value in item["x_values"]))

    data_rows = [item for item in rows if not is_constant(item) and not is_marker(item)]
    x_rows = data_rows or rows
    xs = [x for item in x_rows for x in (item["x_values"] if explicit_x
                                          else list(range(len(item["values"])) ))]
    ys = [value for item in rows for value in item["values"]]
    if not xs or not ys:
        return None

    # ChartLayer.nearestSample ignores constant series and picks the closest real
    # sample. Keep that exact selection rule instead of trusting annotation text.
    candidates = []
    for item in rows:
        if is_constant(item):
            continue
        positions = item["x_values"] if explicit_x else list(range(len(item["values"])))
        candidates.extend((position, value) for position, value in zip(positions, item["values"], strict=True))
    if not candidates:
        candidates = [(position, value) for item in rows
                      for position, value in zip(item["x_values"] if explicit_x
                                                 else list(range(len(item["values"]))),
                                                 item["values"], strict=True)]
    sample_x, sample_y = min(candidates, key=lambda point: abs(point[0] - x_value))

    x_domain = nice_domain(xs)
    sorted_x = sorted(set(xs))
    bars = layer.get("chart") == "bar"
    if bars and len(sorted_x) > 1:
        slot = min(b - a for a, b in zip(sorted_x, sorted_x[1:], strict=False))
    else:
        slot = x_domain["step"]
    x_pad = slot * 0.5 if bars else x_domain["step"] * 0.5
    x_min, x_max = x_domain["lo"] - x_pad, x_domain["hi"] + x_pad

    if bars:
        y_domain = nice_domain([min(0.0, min(ys)), max(0.0, max(ys))])
    else:
        y_domain = nice_domain(ys)
    step = y_domain["step"]
    y_pad = ((y_domain["hi"] - y_domain["lo"]) * 0.22 if bars else step * 0.35)
    y_lo = min(0.0, y_domain["lo"]) if bars else y_domain["lo"] - y_pad
    y_hi = y_domain["hi"] + y_pad

    aspect = max(0.7, min(3.4, region["w"] / max(1, region["h"])))
    canvas_width = _js_round(640 * aspect)
    unit = canvas_width / 1000
    def font(size):
        return _js_round(size * unit)
    legend = [item for item in rows if not is_constant(item) and not is_marker(item)]
    has_legend = len(legend) > 1
    single_label = not has_legend and len(rows) == 1
    top = (font(42) if has_legend else font(4)) + (font(40) if single_label else 0) + font(20)
    bottom = font(116)
    left, right = font(108), font(44)
    width, height = canvas_width - left - right, 640 - top - bottom
    if width <= 0 or height <= 0 or abs(x_max - x_min) < 1e-9 or abs(y_hi - y_lo) < 1e-9:
        return None

    x = left + ((sample_x - x_min) / (x_max - x_min)) * width
    y = top + height - ((sample_y - y_lo) / (y_hi - y_lo)) * height
    center_x = region["x"] + x / canvas_width * region["w"]
    center_y = region["y"] + y / 640 * region["h"]
    return {"x": center_x - POINT_CONTEXT["w"] / 2,
            "y": center_y - POINT_CONTEXT["h"] / 2,
            **POINT_CONTEXT}


def _diagram_node_box(layer: dict, node_id: str, region: dict) -> dict | None:
    """Map one DiagramLayer node through its content-fitted SVG viewBox."""
    nodes = layer.get("nodes") or []
    node = next((item for item in nodes if item.get("id") == node_id), None)
    if node is None:
        return None
    widths = {item["id"]: max(210, len(item["label"]) * 46 + 70) for item in nodes}
    pad = 48
    min_x = min(item["x"] - widths[item["id"]] / 2 for item in nodes) - pad
    max_x = max(item["x"] + widths[item["id"]] / 2 for item in nodes) + pad
    min_y = min(item["y"] for item in nodes) - 56 - pad
    max_y = max(item["y"] for item in nodes) + 56 + pad
    box_width, box_height = max_x - min_x, max_y - min_y
    steps = [step for step in layer.get("steps") or []
             if not any(item["label"] in step or step in item["label"] for item in nodes)]
    content_height = box_height + (len(steps) * 52 + 26 if steps else 0)
    aspect = max(0.6, region["w"] / max(1, region["h"]))
    content_aspect = box_width / max(1, content_height)
    if content_aspect > aspect:
        view_w, view_h = box_width, box_width / aspect
    else:
        view_w, view_h = content_height * aspect, content_height
    view_x = min_x - (view_w - box_width) / 2
    view_y = min_y - (view_h - content_height) / 2
    center_x = region["x"] + (node["x"] - view_x) / view_w * region["w"]
    center_y = region["y"] + (node["y"] - view_y) / view_h * region["h"]
    node_w = widths[node_id] / view_w * region["w"]
    node_h = 112 / view_h * region["h"]
    return {"x": center_x - node_w / 2 - 16, "y": center_y - node_h / 2 - 16,
            "w": node_w + 32, "h": node_h + 32}


def _diagram_message_box(layer: dict, message_id: str, region: dict, at: float) -> dict | None:
    """Map the renderer's moving packet position to stage coordinates."""
    nodes = layer.get("nodes") or []
    edges = layer.get("edges") or []
    matches = [(index, edge) for index, edge in enumerate(edges)
               if edge.get("message_id") == message_id]
    if len(matches) != 1:
        return None
    edge_index, edge = matches[0]
    positions = {node["id"]: node for node in nodes}
    start, end = positions.get(edge.get("source")), positions.get(edge.get("target"))
    if not start or not end:
        return None

    widths = {node["id"]: max(210, len(node["label"]) * 46 + 70) for node in nodes}
    pad = 48
    min_x = min(node["x"] - widths[node["id"]] / 2 for node in nodes) - pad
    max_x = max(node["x"] + widths[node["id"]] / 2 for node in nodes) + pad
    min_y = min(node["y"] for node in nodes) - 56 - pad
    max_y = max(node["y"] for node in nodes) + 56 + pad
    box_width, box_height = max_x - min_x, max_y - min_y
    steps = [step for step in layer.get("steps") or []
             if not any(node["label"] in step or step in node["label"] for node in nodes)]
    content_height = box_height + (len(steps) * 52 + 26 if steps else 0)
    aspect = max(0.6, region["w"] / max(1, region["h"]))
    content_aspect = box_width / max(1, content_height)
    if content_aspect > aspect:
        view_w, view_h = box_width, box_width / aspect
    else:
        view_w, view_h = content_height * aspect, content_height
    view_x = min_x - (view_w - box_width) / 2
    view_y = min_y - (view_h - content_height) / 2

    progress = (float(at) * 0.32 + edge_index * 0.27) % 1
    bend = 0.12 * math.hypot(end["x"] - start["x"], end["y"] - start["y"])
    control_x = (start["x"] + end["x"]) / 2
    control_y = (start["y"] + end["y"]) / 2 - bend
    inverse = 1 - progress
    x = inverse * inverse * start["x"] + 2 * inverse * progress * control_x + progress * progress * end["x"]
    y = inverse * inverse * start["y"] + 2 * inverse * progress * control_y + progress * progress * end["y"]
    center_x = region["x"] + (x - view_x) / view_w * region["w"]
    center_y = region["y"] + (y - view_y) / view_h * region["h"]
    marker_w, marker_h = 30 / view_w * region["w"], 30 / view_h * region["h"]
    return {"x": center_x - marker_w / 2, "y": center_y - marker_h / 2,
            "w": marker_w, "h": marker_h}


def _target_box(target: str, layers: list[dict], boxes: dict, *, at: float = 0.0) -> dict | None:
    # A node id names the concrete object, so it is more specific than the layer
    # or cross-scene subject that contains it.
    node_matches = [(layer, node) for layer in layers if layer.get("type") == "diagram"
                    for node in layer.get("nodes") or [] if node.get("id") == target]
    if len(node_matches) == 1:
        layer, _node = node_matches[0]
        region = boxes.get(layer.get("region", "main"))
        return _diagram_node_box(layer, target, region) if region else None
    if len(node_matches) > 1:
        return None

    message_matches = [(layer, edge) for layer in layers if layer.get("type") == "diagram"
                       for edge in layer.get("edges") or [] if edge.get("message_id") == target]
    if len(message_matches) == 1:
        layer, _edge = message_matches[0]
        region = boxes.get(layer.get("region", "main"))
        return _diagram_message_box(layer, target, region, at) if region else None
    if len(message_matches) > 1:
        return None

    matched = [layer for layer in layers if target in {layer.get("id"), layer.get("subject_id")}]
    if len(matched) != 1:
        return None
    layer = matched[0]
    region = boxes.get(layer.get("region", "main"))
    if not region:
        return None
    if layer.get("subject_id") == target and layer.get("type") == "chart":
        annotations = layer.get("annotations") or []
        if len(annotations) == 1:
            point = _chart_point_box(layer, float(annotations[0]["x"]), region)
            if point:
                return point
    return region


def _is_chart_point_target(target: str, layers: list[dict], boxes: dict) -> bool:
    """Return true only when the subject resolves to a real annotated chart sample."""
    matched = [layer for layer in layers
               if target in {layer.get("id"), layer.get("subject_id")}]
    if len(matched) != 1:
        return False
    layer = matched[0]
    annotations = layer.get("annotations") or []
    region = boxes.get(layer.get("region", "main"))
    if layer.get("type") != "chart" or layer.get("subject_id") != target \
            or len(annotations) != 1 or not region:
        return False
    try:
        x_value = float(annotations[0]["x"])
    except (KeyError, TypeError, ValueError):
        return False
    return _chart_point_box(layer, x_value, region) is not None


def camera_plan(scene: dict, *, orientation: str, duration: float) -> list[dict]:
    """Keyframes: overview first, then a bounded focus per emphasis/reveal event.

    A target may be a layer, a cross-scene subject, a diagram node, or a chart subject
    with one annotated sample. Repeated targets create an eased follow path; the final
    overview is a reframe so the conclusion is not left cropped.
    """
    boxes = regions(orientation, scene.get("layout") or "diagram")
    layers = scene.get("layers") or []
    plan = [{"at": 0.0, "mode": "overview", "scale": 1.0, "cx": 0.5, "cy": 0.5,
             "reason": "先建立全局上下文"}]
    events = sorted((event for event in scene.get("events_resolved") or []
                     if event.get("kind") in {"reveal", "emphasis", "compare", "transform", "conclude"}),
                    key=lambda event: float(event["at"]))
    focused = 0
    for event in events:
        target = event.get("target")
        if not target:
            continue
        event_at = float(event["at"])
        box = _target_box(target, layers, boxes, at=event_at)
        if not box:
            continue
        is_message = any(layer.get("type") == "diagram"
                         and any(edge.get("message_id") == target for edge in layer.get("edges") or [])
                         for layer in layers)
        scale_cap = (POINT_FOCUS_MAX_SCALE if _is_chart_point_target(target, layers, boxes)
                     else MESSAGE_FOCUS_MAX_SCALE if is_message else MAX_FOCUS_SCALE)
        focus = focus_on(box, orientation, max_scale=scale_cap)
        if focus["scale"] <= 1.001:
            continue
        mode = "focus" if focused == 0 else "follow"
        plan.append({"at": round(event_at, 3), "mode": mode, **focus,
                     "target": target, "reason": f"{event['kind']} {event['id']}"})
        focused += 1
    if focused and RETURN_TO_OVERVIEW and float(plan[-1]["at"]) < duration - 1e-6:
        last_focus = float(plan[-1]["at"])
        reframe_at = max(0.0, duration - EASE_SECONDS)
        if reframe_at <= last_focus + 1e-3:
            reframe_at = duration
        plan.append({"at": round(reframe_at, 3), "mode": "reframe",
                     "scale": 1.0, "cx": 0.5, "cy": 0.5, "reason": "回到全局，避免结论被裁切"})
    return plan


def validate_plan(plan: list[dict], *, orientation: str, duration: float) -> list[str]:
    """Problems a plan must not have before it reaches the renderer."""
    problems = []
    width, height = STAGE[orientation]
    allowed_modes = {"overview", "focus", "follow", "reframe"}
    for index, key in enumerate(plan):
        if key.get("mode") not in allowed_modes:
            problems.append(f"相机关键帧 {index} 的模式无效：{key.get('mode')}")
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
