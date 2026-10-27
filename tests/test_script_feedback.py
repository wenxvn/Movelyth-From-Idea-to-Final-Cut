"""Contract failures must arrive as itemized, actionable feedback.

A weak director model re-broke the same rule three times when the failure was one
semicolon-joined sentence.  These tests pin the shape of the feedback the repair
loop passes back.
"""
from __future__ import annotations

import pytest

from movelyth.models import Cut, Film, Research, Scene
from movelyth.quality import ScriptIssues, validate_script
from movelyth.scenedsl import resolve_actions


def scene(**overrides) -> Scene:
    base = {"id": "l1", "heading": "先看一个熟悉的规则", "visual": "matrix", "labels": ["面积"],
            "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0,
            "narration": "减去一个负数，等于加上它的相反数，所以五减负三等于八。"}
    return Scene.model_validate({**base, **overrides})


def research() -> Research:
    return Research(title="为什么负负得正", question="为什么负负得正？",
                    angle="用翻转和分配律两种方式解释符号规则。",
                    facts=["减去负数等于加上相反数", "乘以负一是翻转", "分配律给出唯一结果"],
                    sources=[{"label": "示例来源", "url": "https://example.com/a",
                              "supports": "符号规则的推导"}],
                    cautions=[], next_ideas=["模运算里的规则", "复数的乘法"])


def film(scenes) -> Film:
    cut = Cut(title="为什么负负得正", description="用翻转和分配律解释负负得正，并用具体数值验证。",
              tags=["数学", "符号"], scenes=scenes)
    return Film(title="为什么负负得正", thesis="负负得正来自翻转两次回到原处。",
                long=cut, short=cut)


def test_the_same_anchor_for_start_and_end_names_the_real_cause():
    bad = scene(actions=[{"target": "main", "kind": "appear",
                          "start": "narration:五减负三", "end": "narration:五减负三"}],
                layers=[{"id": "main", "type": "procedural", "procedural": "matrix"}])
    with pytest.raises(ValueError, match="同一个锚点"):
        resolve_actions(bad, duration=10.0, boundaries=[])


def test_a_reversed_span_says_which_end_is_wrong():
    bad = scene(actions=[{"target": "main", "kind": "appear",
                          "start": "narration:等于八", "end": "narration:五减负三"}],
                layers=[{"id": "main", "type": "procedural", "procedural": "matrix"}])
    with pytest.raises(ValueError, match="早于或等于"):
        resolve_actions(bad, duration=10.0, boundaries=[])


def three(scene_factory) -> list[Scene]:
    """Three scenes with distinct ids, so Cut validation passes on ids alone."""
    return [scene_factory(f"l{index}") for index in (1, 2, 3)]


def test_contract_failures_are_itemized_not_joined():
    def broken(scene_id):
        return scene(id=scene_id, layers=[{"id": "steps", "type": "timeline", "region": "side",
                                           "steps": ["写零", "展开", "消项"]}])

    with pytest.raises(ScriptIssues) as caught:
        validate_script(film(three(broken)), research(), 12, 10)
    problems = caught.value.problems
    assert isinstance(problems, list) and problems
    # Each entry stands on its own and names where the defect is, so the director
    # can fix one item at a time instead of re-reading one joined sentence.
    assert all(("镜头 l" in problem) or problem.startswith(("long", "short"))
               for problem in problems)
    assert any("side" in problem and "compare" in problem for problem in problems)


def test_a_math_layer_too_long_for_its_region_is_reported_with_the_reason():
    long_formula = "(-1)×(1+(-1)) = 0 → -1 + (-1)×(-1) = 0 → (-1)×(-1) = 1"

    def broken(scene_id):
        return scene(id=scene_id,
                     layers=[{"id": "chain", "type": "shape", "region": "main", "shape": "arrow"},
                             {"id": "formula", "type": "math", "region": "annotation",
                              "text": long_formula}])

    with pytest.raises(ScriptIssues) as caught:
        validate_script(film(three(broken)), research(), 12, 10)
    assert any("formula" in problem and "annotation" in problem
               for problem in caught.value.problems)


def test_script_issues_is_a_value_error_so_existing_handlers_still_catch_it():
    assert issubclass(ScriptIssues, ValueError)
    error = ScriptIssues(["问题一", "问题二"])
    assert "问题一" in str(error) and "问题二" in str(error)
    assert error.problems == ["问题一", "问题二"]
