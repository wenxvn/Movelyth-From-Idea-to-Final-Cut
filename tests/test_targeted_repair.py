"""Targeted contract repair: fix only the scenes that broke a rule.

A real DeepSeek run failed contract validation with 8 problems, then 1, then 7 —
each attempt rewrote the whole script and lost what the previous one had fixed.
The repair loop now freezes the passing scenes and hands back only the broken ones.
"""
from __future__ import annotations

from movelyth.models import Cut, Film, Finding, Review
from movelyth.pipeline import Studio


def scene(scene_id: str, heading: str = "讲解", narration: str | None = None) -> dict:
    return {"id": scene_id, "heading": heading,
            "narration": narration or "减去一个负数等于加上它的相反数，所以结果变大。",
            "visual": "matrix", "labels": ["面积"], "matrix": [1, 0, 0, 1],
            "color": "cyan", "source_index": 0,
            "layers": [{"id": "main", "type": "procedural", "procedural": "matrix"}]}


def film(long_ids=("l1", "l2", "l3"), short_ids=("s1", "s2", "s3")) -> Film:
    def cut(ids, title):
        return Cut(title=title, description="用翻转和分配律解释符号规则，并用具体数值验证。",
                   tags=["数学", "符号"], scenes=[scene(i) for i in ids])
    return Film(title="为什么负负得正", thesis="负负得正来自翻转两次回到原处。",
                long=cut(long_ids, "为什么负负得正"), short=cut(short_ids, "为什么负负得正"))


def test_only_named_scenes_are_handed_back():
    target = film()
    problems = ["镜头 l2 只有文字/公式，等于动态字幕，没有真正的画面"]
    frozen, scene_ids, notes = Studio._focus_repair(target, problems)
    assert frozen is target
    assert scene_ids == ["l2"]
    assert "l2" in notes and "逐字保持不变" in notes


def test_scene_level_problems_across_both_cuts_are_all_collected():
    problems = ["镜头 l3 的动画 appear 起止时间无效", "镜头 s2 只有文字/公式"]
    _, scene_ids, _ = Studio._focus_repair(film(), problems)
    assert scene_ids == ["l3", "s2"]


def test_a_cut_level_problem_falls_back_to_a_full_rewrite():
    """Narration length and visual variety concern the whole cut, not one scene."""
    problems = ["long 旁白长度 81 字不适配目标 12 秒"]
    frozen, scene_ids, notes = Studio._focus_repair(film(), problems)
    assert frozen is None and scene_ids == [] and notes == ""


def test_a_mix_of_scene_and_cut_level_problems_also_rewrites_everything():
    problems = ["镜头 l2 只有文字/公式", "long 至少应有三种与内容相关的视觉表达"]
    frozen, scene_ids, _ = Studio._focus_repair(film(), problems)
    assert frozen is None and scene_ids == []


def test_freezing_keeps_passing_scenes_verbatim_and_restores_dropped_ones():
    original = film(long_ids=("l1", "l2", "l3", "l4"))
    revised_data = original.model_dump()
    # The director rewrote l1 and l2 (l2 is the target) and dropped l4 entirely.
    revised_data["long"]["scenes"] = [
        {**scene("l1"), "heading": "被改写了"},
        {**scene("l2"), "heading": "修好的镜头"},
        scene("l3"),
    ]
    revised = Film.model_validate(revised_data)
    merged = Studio._keep_untouched_scenes(original, revised, {"l2"})
    headings = {s.id: s.heading for s in merged.long.scenes}
    assert headings == {"l1": "讲解", "l2": "修好的镜头", "l3": "讲解", "l4": "讲解"}
    assert [s.id for s in merged.long.scenes] == ["l1", "l2", "l3", "l4"]


def review_naming(*scene_ids) -> Review:
    return Review(passed=False, issues=["旁白与画面不一致"], strengths=[],
                  findings=[Finding(category="factual", scene_id=scene_id,
                                    detail=f"{scene_id} 的旁白与结论矛盾")
                            for scene_id in scene_ids])


def test_review_findings_drive_a_targeted_repair():
    target = film()
    frozen, scene_ids, notes = Studio._focus_review_repair(target, review_naming("s1", "l3"))
    assert frozen is target
    assert scene_ids == ["s1", "l3"]
    assert "s1" in notes and "逐字保持不变" in notes


def test_a_review_that_names_most_scenes_rewrites_everything():
    """Freezing a majority of the film would leave nothing to actually rewrite."""
    _, scene_ids, _ = Studio._focus_review_repair(
        film(), review_naming("l1", "l2", "l3", "s1", "s2", "s3"))
    assert scene_ids == []


def test_a_review_without_scene_ids_rewrites_everything():
    _, scene_ids, _ = Studio._focus_review_repair(
        film(), Review(passed=False, issues=["整体偏弱"], strengths=[]))
    assert scene_ids == []


def test_unknown_scene_ids_are_ignored():
    _, scene_ids, _ = Studio._focus_review_repair(film(), review_naming("s1", "不存在"))
    assert scene_ids == ["s1"]
