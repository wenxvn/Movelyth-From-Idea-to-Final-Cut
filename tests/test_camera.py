"""S2-06: content-bound camera plans (overview → focus → overview)."""
from __future__ import annotations

import pytest

from movelyth.camera import MAX_FOCUS_SCALE, focus_on, validate_plan
from movelyth.models import Scene
from movelyth.scenedsl import normalize_scene, validate_cut_timeline
from tests.factories import chart_layer, layer, scene


def scene_model(**overrides) -> Scene:
    return Scene.model_validate(scene(**overrides))


def focused_scene(*, layout="diagram", target="chart", kind="emphasis"):
    return scene_model(layout=layout, layers=[
        chart_layer("chart", values=[0.9, 0.7, 0.5, 0.3], annotations=[{"x": 2, "text": "拐点"}]),
        layer("note", type="text", text="损失下降", region="annotation"),
    ], events=[{"id": "focus", "kind": kind, "target": target,
                "anchor": {"kind": "fraction", "fraction": 0.3}}])


def test_focus_scales_a_region_into_the_viewport_and_stays_inside():
    box = {"x": 660, "y": 150, "w": 1164, "h": 730}
    focus = focus_on(box, "landscape")
    assert 1.0 < focus["scale"] <= MAX_FOCUS_SCALE
    half = 0.5 / focus["scale"]
    assert half <= focus["cx"] <= 1 - half
    assert half <= focus["cy"] <= 1 - half


def test_plan_starts_at_the_overview_and_focuses_a_real_layer():
    scene_data = normalize_scene(focused_scene(), duration=8.0)
    plan = scene_data["camera_plan"]
    assert plan[0]["mode"] == "overview" and plan[0]["scale"] == 1.0
    focus = [key for key in plan if key["mode"] == "focus"]
    assert focus and focus[0]["target"] == "chart"
    assert focus[0]["at"] == pytest.approx(2.4, abs=0.01)  # 30% of 8 s
    assert plan[-1]["mode"] == "overview", "结论不能被裁切"


def test_an_event_without_a_real_target_creates_no_focus():
    scene_data = normalize_scene(scene_model(layers=[layer()],
                                             events=[{"id": "ghost", "kind": "emphasis",
                                                      "target": "", "anchor": {"kind": "start"}}]),
                                 duration=6.0)
    assert [key["mode"] for key in scene_data["camera_plan"]] == ["overview"]


def test_portrait_and_landscape_solve_different_framings():
    # Landscape can zoom into the annotation band; in portrait the same band already
    # spans 87% of the width, so a focus there is correctly declined instead of
    # cropping the text.  A narrow box (a chart sub-region) zooms in both.
    landscape = normalize_scene(focused_scene(target="note"), duration=8.0)["camera_plan"]
    portrait = normalize_scene(focused_scene(target="note"), duration=8.0, vertical=True)["camera_plan"]
    assert any(key["mode"] == "focus" for key in landscape)
    assert not any(key["mode"] == "focus" for key in portrait)
    narrow = {"x": 300, "y": 800, "w": 420, "h": 300}
    assert focus_on(narrow, "portrait")["scale"] > 1.2
    assert focus_on(narrow, "portrait")["cx"] != focus_on(narrow, "landscape")["cx"]


def test_the_plan_is_deterministic():
    first = normalize_scene(focused_scene(), duration=8.0)["camera_plan"]
    second = normalize_scene(focused_scene(), duration=8.0)["camera_plan"]
    assert first == second


def test_validate_plan_rejects_out_of_range_and_reversed_keyframes():
    bad_time = [{"at": 9.0, "mode": "overview", "scale": 1.0, "cx": 0.5, "cy": 0.5, "reason": ""}]
    assert any("镜头外" in problem for problem in validate_plan(bad_time, orientation="landscape", duration=8.0))
    too_zoomed = [{"at": 0.0, "mode": "focus", "scale": 3.0, "cx": 0.5, "cy": 0.5, "reason": ""}]
    assert any("缩放越界" in problem for problem in validate_plan(too_zoomed, orientation="landscape", duration=8.0))
    overflow = [{"at": 0.0, "mode": "focus", "scale": 1.5, "cx": 0.1, "cy": 0.5, "reason": ""}]
    assert any("取景超出" in problem for problem in validate_plan(overflow, orientation="landscape", duration=8.0))
    reversed_plan = [{"at": 2.0, "mode": "overview", "scale": 1.0, "cx": 0.5, "cy": 0.5, "reason": ""},
                     {"at": 1.0, "mode": "overview", "scale": 1.0, "cx": 0.5, "cy": 0.5, "reason": ""}]
    assert any("倒序" in problem for problem in validate_plan(reversed_plan, orientation="landscape", duration=8.0))


def test_the_cut_timeline_accepts_the_generated_plan_in_both_orientations():
    for portrait in (False, True):
        scene_data = normalize_scene(focused_scene(), duration=8.0, vertical=portrait)
        scene_data["frames"] = 240
        scene_data["captions"] = [{"start": 0.2, "end": 2.0, "text": "损失下降"}]
        cut = {"scenes": [scene_data]}
        assert validate_cut_timeline(cut, 30, portrait=portrait) == []


def test_focusing_the_main_box_in_portrait_is_a_no_op():
    plan = normalize_scene(focused_scene(), duration=8.0, vertical=True)["camera_plan"]
    assert [key["mode"] for key in plan] == ["overview"]
