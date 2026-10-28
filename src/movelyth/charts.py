"""Deterministic chart scales shared by the renderer contract and the release policy.

The renderer (``studio/src/components/ChartLayer.tsx``) derives axis ticks from the
data range with 1-2-5 rounding.  Mirroring that arithmetic in Python is what lets a
review finding about "wrong tick numbers" be checked against the *actual* labels
instead of being dismissed because it happens to mention the word "axis".
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def nice_step(span: float, target: int = 4) -> float:
    """1-2-5 rounding; mirror of ``niceStep`` in ChartLayer.tsx."""
    if not math.isfinite(span) or span <= 0:
        return 1.0
    raw = span / target
    magnitude = 10.0 ** math.floor(math.log10(raw))
    normal = raw / magnitude
    step = 1.0 if normal <= 1 else 2.0 if normal <= 2 else 5.0 if normal <= 5 else 10.0
    return step * magnitude


def nice_domain(values: Sequence[float], target: int = 4) -> dict:
    """Padded axis domain and step; mirror of ``niceDomain`` in ChartLayer.tsx."""
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"lo": 0.0, "hi": 1.0, "step": 0.25}
    low, high = min(finite), max(finite)
    if high - low < 1e-9:
        pad = abs(high) * 0.15 or 1.0
        low -= pad
        high += pad
    step = nice_step(high - low, target)
    lo = math.floor(low / step + 1e-9) * step
    hi = math.ceil(high / step - 1e-9) * step
    return {"lo": lo, "hi": hi, "step": step}


def domain_ticks(domain: dict) -> list[float]:
    """Every tick position from ``lo`` to ``hi`` inclusive."""
    step = domain["step"]
    if step <= 0:
        return [domain["lo"]]
    count = int(round((domain["hi"] - domain["lo"]) / step))
    return [round(domain["lo"] + index * step, 10) for index in range(count + 1)]


def format_tick(value: float, step: float) -> str:
    """Label text the renderer draws for a tick; mirror of ``format`` in ChartLayer.tsx."""
    decimals = 0 if step >= 1 else min(3, math.ceil(-math.log10(step)))
    text = f"{value:.{decimals}f}"
    return "0" if text == "-0" else text


def tick_labels(values: Iterable[float], target: int = 4) -> list[str]:
    """Label strings a chart of these values actually shows on its y axis."""
    domain = nice_domain(list(values), target)
    return [format_tick(value, domain["step"]) for value in domain_ticks(domain)]


def layer_values(layer) -> list[float]:
    """Every y value a chart layer draws (annotations excluded: they snap to samples)."""
    values: list[float] = []
    for series in getattr(layer, "series", []) or []:
        values.extend(float(value) for value in series.values)
    return values


def layer_tick_labels(layer) -> list[str]:
    return tick_labels(layer_values(layer))


def scene_tick_labels(scenes: Iterable[dict]) -> dict[str, list[str]]:
    """Computed y-axis labels per scene id, for scenes that contain chart layers."""
    labels: dict[str, list[str]] = {}
    for scene in scenes:
        scene_labels: list[str] = []
        for layer in scene.get("layers") or []:
            if layer.get("type") != "chart":
                continue
            series = layer.get("series") or []
            values = [float(value) for item in series for value in item.get("values") or []]
            if values:
                scene_labels.extend(tick_labels(values))
        if scene_labels:
            labels[str(scene.get("id", ""))] = sorted(set(scene_labels), key=_label_order)
    return labels


def _label_order(text: str):
    try:
        return (0, float(text))
    except ValueError:
        return (1, 0.0)
