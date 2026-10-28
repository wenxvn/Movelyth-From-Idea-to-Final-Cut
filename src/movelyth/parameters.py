"""Controlled parameter functions: one state drives geometry, numbers and labels.

A model may pick a function and bounded parameters; it may not write its own maths.
The evaluated values are then the *only* source for the drawn coordinates, the series
and the numbers shown on screen, so a label cannot disagree with the curve.  This is a
small registry on purpose — an expression evaluator would be a different product.
"""
from __future__ import annotations

import math

MAX_STEPS = 24
MAX_VALUE = 1_000_000.0


class ParameterError(ValueError):
    """The requested function/parameters cannot be evaluated honestly."""


def _finite(values, limit: float = MAX_VALUE) -> list[float]:
    result = []
    for value in values:
        number = float(value)
        if not math.isfinite(number) or abs(number) > limit:
            raise ParameterError("参数必须是绝对值不超过 1000000 的有限数")
        result.append(number)
    return result


def _iteration(x0: float, rate: float, steps: int) -> dict:
    """x_{n+1} = x_n - rate * x_n (a teaching descent), all steps recorded."""
    values = [float(x0)]
    for _ in range(int(steps)):
        values.append(values[-1] - rate * values[-1])
    return {"series": values, "steps": int(steps),
            "start": values[0], "end": values[-1],
            "numbers": values}


def _linear(a: float, b: float, c: float, d: float) -> dict:
    """Image of the unit square under [[a, b], [c, d]]; the determinant is computed."""
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    mapped = [(a * x + b * y, c * x + d * y) for x, y in corners]
    determinant = a * d - b * c
    return {"points": [round(value, 6) for point in mapped for value in point],
            "determinant": determinant, "area_scale": abs(determinant),
            "numbers": [determinant, abs(determinant)]}


def _projection(x: float, y: float, u: float, v: float) -> dict:
    """Projection of (x, y) onto the direction (u, v), with the residual."""
    norm = u * u + v * v
    if norm < 1e-12:
        raise ParameterError("投影方向不能是零向量")
    scale = (x * u + y * v) / norm
    px, py = scale * u, scale * v
    residual = math.hypot(x - px, y - py)
    return {"projection": [round(px, 6), round(py, 6)],
            "residual": round(residual, 6),
            "numbers": [round(px, 6), round(py, 6), round(residual, 6)]}


FUNCTIONS: dict[str, dict] = {
    "iteration": {
        "purpose": "单变量迭代：每一轮的数值与曲线同源",
        "params": {"x0": "起始值", "rate": "步长比例（0–1）", "steps": "迭代次数（1–24）"},
        "requires": {"x0": (-1000, 1000), "rate": (0.01, 0.9), "steps": (1, MAX_STEPS)},
        "evaluate": _iteration,
        "recipe": "parameter-process",
    },
    "linear-transform": {
        "purpose": "线性变换：四个系数驱动四角坐标与行列式",
        "params": {"a": "左上", "b": "右上", "c": "左下", "d": "右下"},
        "requires": {"a": (-4, 4), "b": (-4, 4), "c": (-4, 4), "d": (-4, 4)},
        "evaluate": _linear,
        "recipe": "parameter-process",
    },
    "projection": {
        "purpose": "投影：向量与方向驱动投影点、残差",
        "params": {"x": "向量 x", "y": "向量 y", "u": "方向 u", "v": "方向 v"},
        "requires": {"x": (-100, 100), "y": (-100, 100), "u": (-100, 100), "v": (-100, 100)},
        "evaluate": _projection,
        "recipe": "parameter-process",
    },
}


def evaluate(name: str, params: dict) -> dict:
    """Evaluate a registered function with bounded parameters."""
    spec = FUNCTIONS.get(name)
    if spec is None:
        raise ParameterError(f"未注册的参数函数：{name}")
    cleaned = {}
    for key, (low, high) in spec["requires"].items():
        if key not in params:
            raise ParameterError(f"{name} 缺少参数 {key}")
        value = float(params[key])
        if not math.isfinite(value) or not low <= value <= high:
            raise ParameterError(f"{name} 的参数 {key}={value} 超出范围 {low}–{high}")
        cleaned[key] = value
    if name == "iteration":
        steps = int(cleaned["steps"])
        if steps != cleaned["steps"]:
            raise ParameterError("iteration 的 steps 必须是整数")
        cleaned["steps"] = steps
    result = spec["evaluate"](**cleaned)
    result["function"] = name
    result["params"] = cleaned
    result["numbers"] = _finite(result.get("numbers") or [])
    return result


def catalog() -> dict:
    return {"functions": {name: {"purpose": spec["purpose"], "params": spec["params"],
                                 "requires": spec["requires"], "recipe": spec["recipe"]}
                          for name, spec in FUNCTIONS.items()},
            "note": "模型只能选函数与有界参数；坐标、曲线与数字由这里计算"}


def validate_scene_parameters(scene) -> list[str]:
    """The scene's declared numbers must come from the controlled evaluation.

    Two ways to disagree are both rejected: a series that does not match the
    computed values, and a label/annotation number that appears nowhere in the
    computed set.
    """
    if not getattr(scene, "function", ""):
        return []
    result = evaluate(scene.function, dict(scene.parameters))
    problems: list[str] = []
    expected = result["numbers"]
    for layer in scene.layers:
        if scene.function == "iteration" and layer.type == "chart" and layer.series:
            values = layer.series[0].values
            if len(values) != len(result["series"]) or any(
                    abs(float(a) - float(b)) > 1e-6 for a, b in zip(values, result["series"], strict=True)):
                problems.append(f"镜头 {scene.id} 的曲线与 {scene.function} 的计算结果不一致")
        if scene.function == "linear-transform" and layer.type == "procedural":
            # The matrix lives on the scene (it is the legacy procedural visual field).
            matrix = getattr(scene, "matrix", None)
            if matrix:
                wanted = [result["params"][key] for key in ("a", "b", "c", "d")]
                if any(abs(float(a) - float(b)) > 1e-9
                       for a, b in zip(matrix, wanted, strict=True)):
                    problems.append(f"镜头 {scene.id} 的矩阵与 {scene.function} 的参数不一致")
        for text in [layer.text, *(annotation.text for annotation in layer.annotations)]:
            for token in __import__("re").findall(r"-?\d+(?:\.\d+)?", str(text or "")):
                number = float(token)
                if not any(abs(number - value) <= max(1e-6, abs(value) * 1e-3) for value in expected):
                    problems.append(f"镜头 {scene.id} 的文字“{text}”里的数字 {token} 不在计算结果里")
    return problems
