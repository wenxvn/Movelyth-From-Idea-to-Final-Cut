"""S2-05: controlled parameter functions — one state drives geometry and numbers."""
from __future__ import annotations

import pytest

from movelyth.models import Scene
from movelyth.parameters import FUNCTIONS, ParameterError, catalog, evaluate, validate_scene_parameters
from movelyth.scenedsl import normalize_scene
from tests.factories import chart_layer, layer, scene


def test_iteration_is_evaluated_step_by_step_and_is_deterministic():
    result = evaluate("iteration", {"x0": 1.0, "rate": 0.5, "steps": 4})
    assert result["series"] == [1.0, 0.5, 0.25, 0.125, 0.0625]
    assert result["start"] == 1.0 and result["end"] == 0.0625
    assert result["numbers"] == result["series"]
    assert evaluate("iteration", {"x0": 1.0, "rate": 0.5, "steps": 4}) == result


def test_linear_transform_computes_corners_and_determinant():
    result = evaluate("linear-transform", {"a": 1, "b": 0.5, "c": 0, "d": 2})
    assert result["points"][:4] == [0.0, 0.0, 1.0, 0.0]
    assert result["determinant"] == 2.0 and result["area_scale"] == 2.0


def test_projection_returns_the_point_and_residual():
    result = evaluate("projection", {"x": 3, "y": 4, "u": 1, "v": 0})
    assert result["projection"] == [3.0, 0.0]
    assert result["residual"] == pytest.approx(4.0)


@pytest.mark.parametrize("name,params", [
    ("iteration", {"x0": 1, "rate": 1.5, "steps": 3}),      # rate out of range
    ("iteration", {"x0": 1, "rate": 0.5}),                   # missing steps
    ("linear-transform", {"a": 9, "b": 0, "c": 0, "d": 1}),  # coefficient too large
    ("projection", {"x": 1, "y": 1, "u": 0, "v": 0}),        # zero direction
    ("unregistered", {"x": 1}),                              # unknown function
])
def test_bad_functions_or_parameters_are_rejected(name, params):
    with pytest.raises(ParameterError):
        evaluate(name, params)


def test_the_catalog_is_reviewable():
    functions = catalog()["functions"]
    assert set(functions) == set(FUNCTIONS) == {"iteration", "linear-transform", "projection"}
    for spec in functions.values():
        assert spec["purpose"] and spec["params"] and spec["requires"]


def model(**overrides) -> Scene:
    return Scene.model_validate(scene(**overrides))


def test_normalized_scene_carries_the_computed_state():
    scene_model = model(function="iteration", parameters={"x0": 1.0, "rate": 0.5, "steps": 3},
                        layers=[chart_layer("loss", [1.0, 0.5, 0.25, 0.125])])
    normalized = normalize_scene(scene_model, duration=6.0)
    assert normalized["computed"]["series"] == [1.0, 0.5, 0.25, 0.125]
    assert validate_scene_parameters(scene_model) == []


def test_a_series_that_disagrees_with_the_computation_is_rejected():
    scene_model = model(function="iteration", parameters={"x0": 1.0, "rate": 0.5, "steps": 3},
                        layers=[chart_layer("loss", [9.0, 8.0, 7.0, 6.0])])
    problems = validate_scene_parameters(scene_model)
    assert any("曲线与" in problem for problem in problems)


def test_a_label_number_outside_the_computation_is_rejected():
    scene_model = model(function="linear-transform", parameters={"a": 1, "b": 0, "c": 0, "d": 2},
                        layers=[layer("note", type="text", text="面积放大 37 倍")])
    problems = validate_scene_parameters(scene_model)
    assert any("37" in problem for problem in problems)


def test_a_label_number_from_the_computation_is_accepted():
    scene_model = model(function="linear-transform", parameters={"a": 1, "b": 0, "c": 0, "d": 2},
                        layers=[layer("note", type="text", text="面积放大 2 倍")])
    assert validate_scene_parameters(scene_model) == []


def test_a_matrix_that_disagrees_with_the_parameters_is_rejected():
    scene_model = model(function="linear-transform", parameters={"a": 1, "b": 0, "c": 0, "d": 2},
                        matrix=[1, 0, 0, 1], layers=[layer("grid", procedural="matrix")])
    assert any("矩阵与" in problem for problem in validate_scene_parameters(scene_model))


def test_a_function_without_parameters_is_rejected_by_the_model():
    with pytest.raises(ValueError, match="parameters"):
        model(function="iteration")
