"""S2-01: shot recipes are a reviewable contract the director may choose from."""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from movelyth.models import SCHEMA_VERSION
from movelyth.pipeline import RENDERER_CAPABILITIES
from movelyth.recipes import (
    RECIPES,
    applicable,
    catalog,
    check_scene,
    choose,
    recipe_warnings,
    validate_scene_recipe,
)
from tests.conftest import make_studio
from tests.factories import chart_layer, diagram_layer, film, layer, research_payload, review_payload, scene


def chart(*, recipe=None, hero="", annotations=None, series=None, claim_ids=None):
    layer_kwargs = {}
    if annotations is not None:
        layer_kwargs["annotations"] = annotations
    if series is not None:
        layer_kwargs["series"] = series
    overrides = {"schema_version": SCHEMA_VERSION}
    if recipe:
        overrides["recipe"] = recipe
    if hero:
        overrides["hero"] = hero
    if claim_ids is not None:
        overrides["claim_ids"] = claim_ids
    return scene("one", "损失从 0.9 降到 0.3，下降速度先快后慢，需要看清拐点。",
                 [chart_layer(values=[0.9, 0.7, 0.5, 0.3], **layer_kwargs)], **overrides)


def test_every_recipe_declares_its_contract():
    assert set(RECIPES) == {"chart-focus", "same-scale-compare", "parameter-process",
                            "flow-expand", "paper-evidence", "conclusion-callback"}
    for name, spec in RECIPES.items():
        assert spec["purpose"] and spec["requires"] and spec["events"] and spec["checks"]
        assert spec["orientations"] == ["landscape", "portrait"]
    assert catalog()["recipes"] is RECIPES


def test_chart_focus_needs_an_annotation():
    without = chart()
    assert "chart-focus" not in applicable(without)
    with_annotation = chart(annotations=[{"x": 2, "text": "拐点"}])
    assert "chart-focus" in applicable(with_annotation)


def test_same_scale_compare_requires_one_unit():
    two_same = chart(series=[{"label": "A", "values": [1, 2, 3], "unit": "%", "x_values": []},
                             {"label": "B", "values": [2, 3, 4], "unit": "%", "x_values": []}])
    assert "same-scale-compare" in applicable(two_same)
    two_different = chart(series=[{"label": "A", "values": [1, 2, 3], "unit": "%", "x_values": []},
                                  {"label": "B", "values": [2, 3, 4], "unit": "秒", "x_values": []}])
    assert "same-scale-compare" not in applicable(two_different)


def test_other_recipes_bind_to_their_content():
    assert "parameter-process" in applicable(scene("p", "向量分解成两个方向的分量，就能看清变换。",
                                                  [layer("vec", procedural="vectors")]))
    assert "flow-expand" in applicable(scene("f", "请求先建立连接，再发送数据，最后返回结果。",
                                             [diagram_layer()]))
    paper = scene("paper", "原文写着：矩阵的列就是基向量的像。",
                  [layer("quote", type="text", text="矩阵的列是基向量的像", source_note="示例课程")])
    assert "paper-evidence" in applicable(paper)
    assert "conclusion-callback" in applicable(scene("c", "所以中位数不受极端值影响，这一点很重要。",
                                                     [layer("note", type="text", text="中位数 4")],
                                                     claim_ids=["c1"]))


def test_declared_recipe_wins_and_unknown_ids_are_rejected():
    with_annotation = chart(annotations=[{"x": 2, "text": "拐点"}], recipe="chart-focus")
    assert choose(with_annotation) == "chart-focus"
    assert validate_scene_recipe(with_annotation) == []
    unknown = chart(recipe="magic-transition")
    assert "未实现" in validate_scene_recipe(unknown)[0]
    not_applicable = chart(recipe="flow-expand")
    assert "不适用" in validate_scene_recipe(not_applicable)[0]


def test_recipe_checks_catch_broken_bindings():
    far_annotation = chart(annotations=[{"x": 40, "text": "远处"}])
    assert any("离真实数据点过远" in problem for problem in check_scene(far_annotation))
    mismatched_units = chart(series=[{"label": "A", "values": [1, 2, 3], "unit": "%", "x_values": []},
                                     {"label": "B", "values": [2, 3, 4], "unit": "秒", "x_values": []}],
                             recipe="same-scale-compare")
    assert any("单位不一致" in problem for problem in check_scene(mismatched_units))
    bad_hero = chart(annotations=[{"x": 2, "text": "拐点"}], hero="ghost")
    assert any("hero" in problem for problem in check_scene(bad_hero))
    no_source = scene("paper", "原文写着：矩阵的列就是基向量的像。",
                      [layer("quote", type="text", text="矩阵的列是基向量的像")], recipe="paper-evidence")
    assert any("source_note" in problem for problem in check_scene(no_source))


def test_a_scene_outside_the_recipes_is_a_warning_not_a_blocker():
    plain = scene("plain", "这是一段没有图形绑定的旁白，只有一句说明文字。",
                  [layer("note", type="text", text="一句说明")])
    assert recipe_warnings(plain) and not validate_scene_recipe(plain)


def test_renderer_capabilities_and_prompt_expose_recipes():
    assert set(RENDERER_CAPABILITIES["recipes"]) == set(RECIPES)
    prompt = (__import__("pathlib").Path(__file__).parents[1] / "src/movelyth/prompts/director.md")
    text = prompt.read_text(encoding="utf-8")
    for name in RECIPES:
        assert f"`{name}`" in text


def test_pipeline_records_recipe_usage_and_rejects_an_unimplemented_one(offline_pipeline):
    scenes = [chart(annotations=[{"x": 2, "text": "拐点"}], recipe="chart-focus"),
              scene("two", "把向量分解成两个方向的分量，就能看清变换做了什么。",
                    [layer("vec", procedural="vectors")]),
              scene("three", "沿着投影方向取最近的落点，残差就是丢掉的那部分。",
                    [layer("proj", procedural="projection")])]
    provider = MockProvider({"research": research_payload(), "director": film(long_scenes=scenes),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("配方记录测试")
        result = studio.produce(episode["id"])
        quality = json.loads((__import__("pathlib").Path(result["delivery"]) / "质检报告.json")
                             .read_text(encoding="utf-8"))
        assert quality["recipes"]["long"][0] == "chart-focus"
        assert all(quality["recipes"]["long"])
    finally:
        studio.close()


def test_an_unimplemented_recipe_never_reaches_the_renderer(offline_pipeline):
    scenes = [chart(annotations=[{"x": 2, "text": "拐点"}], recipe="magic-transition"),
              scene("two", "把向量分解成两个方向的分量，就能看清变换做了什么。",
                    [layer("vec", procedural="vectors")]),
              scene("three", "沿着投影方向取最近的落点，残差就是丢掉的那部分。",
                    [layer("proj", procedural="projection")])]
    provider = MockProvider({"research": research_payload(), "director": film(long_scenes=scenes),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("未实现配方测试")
        # The contract failure is itemised and retried; either the itemised error or
        # the exhausted retry budget is acceptable, but nothing may reach the renderer.
        with pytest.raises((RuntimeError, ValueError)):
            studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        assert not (job / "renders" / "long" / "final.mp4").exists()
        feedback = json.loads((job / "script-feedback.json").read_text(encoding="utf-8"))
        assert any("未实现" in issue for issue in feedback["issues"])
    finally:
        studio.close()
