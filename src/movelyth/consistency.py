"""Narration ↔ visual consistency checks (P0-06).

These checks are deliberately narrow and testable: they only reject claims that
the rendered parameters demonstrably contradict (a falling curve described as
rising, a rotation claim on a non-rotation matrix, a "measured data" claim on a
purely illustrative chart).  They are not a general fact checker.
"""
from __future__ import annotations

import re

from .models import Scene

DOWN = ("下降", "减少", "降低", "变小", "缩小", "下跌", "回落", "衰减", "减小")
UP = ("上升", "增加", "增大", "增长", "升高", "上涨", "提升", "变大")
MEASURED = ("实测", "实验数据", "真实数据", "测量值", "采样数据", "统计结果")
ILLUSTRATIVE = ("示意", "原理示意", "合成数据", "演示数据", "本地生成")
ROTATION = ("旋转", "转动", "转一圈", "旋转矩阵")
AREA_PRESERVED = ("面积不变", "面积保持不变", "面积保持", "保持面积", "面积相等")
DISTANCE_PRESERVED = ("保持距离", "长度不变", "不改变长度", "保距")
COLLAPSE = ("塌缩", "不可逆", "降维", "压成一条线", "行列式为零", "行列式为 0")


def _mentions(text: str, words: tuple[str, ...]) -> list[str]:
    return [word for word in words if word in text]


def _trend(values: list[float]) -> str:
    if len(values) < 2:
        return "flat"
    delta = values[-1] - values[0]
    scale = max(1e-9, max(abs(v) for v in values))
    if delta / scale > 0.05:
        return "up"
    if delta / scale < -0.05:
        return "down"
    return "flat"


def _orthonormal(matrix: list[float]) -> bool:
    a, b, c, d = matrix
    return (abs(a * a + c * c - 1) < 0.02 and abs(b * b + d * d - 1) < 0.02
            and abs(a * b + c * d) < 0.02)


def _is_rotation(matrix: list[float]) -> bool:
    a, b, c, d = matrix
    det = a * d - b * c
    return _orthonormal(matrix) and abs(det - 1) < 0.02


def check_scene(scene: Scene) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for one scene."""
    errors, warnings = [], []
    narration = scene.narration
    layers = scene.layers

    for layer in layers:
        if layer.type != "chart":
            continue
        values = layer.series[0].values if layer.series else []
        trend = _trend(values)
        down, up = _mentions(narration, DOWN), _mentions(narration, UP)
        if trend == "down" and up and not down:
            errors.append(f"镜头 {scene.id}：旁白说“{up[0]}”，但 {layer.id} 的数据实际下降")
        if trend == "up" and down and not up:
            errors.append(f"镜头 {scene.id}：旁白说“{down[0]}”，但 {layer.id} 的数据实际上升")
        measured = _mentions(narration + " " + layer.source_note, MEASURED)
        illustrative = layer.source_note or ""
        if measured and (not layer.data_ref or any(word in illustrative for word in ILLUSTRATIVE)):
            errors.append(f"镜头 {scene.id}：{layer.id} 是示意数据，旁白却写成“{measured[0]}”")

    for layer in layers:
        if layer.type == "procedural" and layer.procedural == "matrix":
            det = scene.matrix[0] * scene.matrix[3] - scene.matrix[1] * scene.matrix[2]
            if _mentions(narration, ROTATION) and not _is_rotation(scene.matrix):
                warnings.append(f"镜头 {scene.id}：旁白称旋转，但 matrix={scene.matrix} 不是纯旋转")
            if _mentions(narration, AREA_PRESERVED) and abs(abs(det) - 1) > 0.05:
                errors.append(f"镜头 {scene.id}：旁白称面积不变，但 |det|={abs(det):.2f}")
            if _mentions(narration, DISTANCE_PRESERVED) and not _orthonormal(scene.matrix):
                errors.append(f"镜头 {scene.id}：旁白称保持长度，但 matrix={scene.matrix} 不是正交矩阵")
            if _mentions(narration, COLLAPSE) and abs(det) > 0.2:
                errors.append(f"镜头 {scene.id}：旁白称塌缩/不可逆，但 |det|={abs(det):.2f} 并不接近 0")

    for number in re.findall(r"\d+(?:\.\d+)?", narration):
        value = float(number)
        if value > 100 and not layers:
            warnings.append(f"镜头 {scene.id}：旁白出现数值 {number}，但画面没有对应数据")
    for layer in layers:
        if layer.type == "math" and not any(ch.isdigit() for ch in layer.text) and "=" in layer.text:
            warnings.append(f"镜头 {scene.id}：公式 {layer.text} 没有具体参数，需确认与口播一致")
    return errors, warnings


def check_film(film) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for cut_name in ("long", "short"):
        cut = getattr(film, cut_name)
        for scene in cut.scenes:
            scene_errors, scene_warnings = check_scene(scene)
            errors.extend(f"{cut_name}/{message}" for message in scene_errors)
            warnings.extend(f"{cut_name}/{message}" for message in scene_warnings)
    return errors, warnings
