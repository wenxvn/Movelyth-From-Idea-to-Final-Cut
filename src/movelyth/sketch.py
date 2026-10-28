"""Hand-drawn annotations that are stable: seeded geometry, progress-only reveal.

A rough annotation is usually drawn by a library that animates itself with CSS or
randomness, which makes two renders of the same frame differ.  Here the *geometry* is a
pure function of (box, kind, seed) and only the visible portion of the stroke changes
with time, so:

* the same frame always renders identically (no per-frame jitter, no jitter in stills);
* the still areas of a paper scene never wobble;
* the annotation is an overlay drawn outside the content transform, so it can never
  move the data, the axes or a number it is pointing at.

The renderer mirrors ``path_points`` exactly; the parity test executes this module and
the TSX source on the same inputs.
"""
from __future__ import annotations

import math

from .models import SKETCH_KINDS

KINDS = SKETCH_KINDS
MAX_OFFSET = 3.0          # px of hand-drawn irregularity, never more
POINTS_PER_SHAPE = 48


def _rng(seed: int):
    """Deterministic LCG: the same seed always yields the same jitter."""
    state = (seed * 1103515245 + 12345) & 0x7FFFFFFF

    def next_value() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return next_value


def path_points(box: dict, kind: str, seed: int) -> list[list[float]]:
    """The stroke geometry, independent of time. Mirrored by SketchOverlay.tsx."""
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    rng = _rng(seed)
    points: list[list[float]] = []
    if kind == "circle":
        cx, cy = x + w / 2, y + h / 2
        rx, ry = w * 0.52, h * 0.55
        for index in range(POINTS_PER_SHAPE):
            angle = -0.35 + (index / (POINTS_PER_SHAPE - 1)) * 6.6
            wobble = 1 + (rng() - 0.5) * 0.05
            points.append([round(cx + rx * wobble * math.cos(angle), 2),
                           round(cy + ry * wobble * math.sin(angle), 2)])
    elif kind == "underline":
        for index in range(POINTS_PER_SHAPE):
            t = index / (POINTS_PER_SHAPE - 1)
            points.append([round(x + w * 0.04 + (w * 0.92) * t, 2),
                           round(y + h * 0.96 + (rng() - 0.5) * MAX_OFFSET, 2)])
    elif kind == "highlight":
        for index in range(POINTS_PER_SHAPE):
            t = index / (POINTS_PER_SHAPE - 1)
            points.append([round(x + w * 0.02 + (w * 0.96) * t, 2),
                           round(y + h * 0.55 + (rng() - 0.5) * h * 0.35, 2)])
    elif kind == "bracket":
        for index in range(POINTS_PER_SHAPE // 2):
            t = index / (POINTS_PER_SHAPE // 2 - 1)
            points.append([round(x - 18 + (rng() - 0.5) * MAX_OFFSET, 2), round(y + h * t, 2)])
        for index in range(POINTS_PER_SHAPE // 2):
            t = index / (POINTS_PER_SHAPE // 2 - 1)
            points.append([round(x - 18 + (rng() - 0.5) * MAX_OFFSET, 2),
                           round(y + h - h * t, 2)])
    else:  # box
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        for index in range(POINTS_PER_SHAPE):
            t = index / (POINTS_PER_SHAPE - 1) * 4
            segment = min(3, int(t))
            local = t - segment
            ax, ay = corners[segment]
            bx, by = corners[segment + 1]
            points.append([round(ax + (bx - ax) * local + (rng() - 0.5) * MAX_OFFSET, 2),
                           round(ay + (by - ay) * local + (rng() - 0.5) * MAX_OFFSET, 2)])
    return points


def path_string(box: dict, kind: str, seed: int) -> str:
    points = path_points(box, kind, seed)
    return "M" + " L".join(f"{px} {py}" for px, py in points)


def reveal(progress: float, start: float, end: float) -> float:
    """Visible share of the stroke; the only time-dependent quantity."""
    if end <= start:
        return 1.0 if progress >= end else 0.0
    return max(0.0, min(1.0, (progress - start) / (end - start)))


def sketch_problems(scene, *, boxes: dict | None = None) -> list[str]:
    """Validate annotations: real target, sane timing, and not over the captions."""
    problems = []
    layer_ids = {layer.id for layer in scene.layers}
    seen = set()
    for sketch in getattr(scene, "sketches", []) or []:
        if sketch.id in seen:
            problems.append(f"镜头 {scene.id} 的标注 id 重复：{sketch.id}")
        seen.add(sketch.id)
        if sketch.target not in layer_ids:
            problems.append(f"镜头 {scene.id} 的标注 {sketch.id} 指向不存在的图层 {sketch.target}")
        for label, value in (("start", sketch.start), ("end", sketch.end)):
            try:
                number = float(value)
            except ValueError:
                problems.append(f"镜头 {scene.id} 的标注 {sketch.id} 的 {label} 只能是 0–1 数字")
                continue
            if not 0 <= number <= 1:
                problems.append(f"镜头 {scene.id} 的标注 {sketch.id} 的 {label}={number} 越界")
        if boxes and sketch.target in layer_ids:
            layer = next(item for item in scene.layers if item.id == sketch.target)
            box = boxes.get(layer.region)
            if box and box["y"] + box["h"] > 900 and sketch.kind in {"underline", "box"}:
                problems.append(f"镜头 {scene.id} 的标注 {sketch.id} 可能压到字幕带")
    return problems
