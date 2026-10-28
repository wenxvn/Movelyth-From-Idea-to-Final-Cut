"""S1-05: production brief, genre routing and capability gating.

A topic that needs real footage has to be refused at ``create`` time — before a
research call, a script, a TTS bill or a render — and a topic that needs a capability
we only approximate must record that substitution in a frozen brief.
"""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from movelyth.brief import audience_from, build_production_brief, topic_violations
from movelyth.capability import ROUTES, classify_route, strictest
from movelyth.models import Research
from movelyth.pipeline import RENDERER_CAPABILITIES
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload


def research_model(**overrides) -> Research:
    payload = research_payload()
    payload.update(overrides)
    return Research.model_validate(payload)


# ------------------------------------------------------------------- routing

@pytest.mark.parametrize("title,route,status", [
    ("矩阵为什么能让空间旋转？", "program-graphics", "supported"),
    ("跟着录屏一步步部署这个服务", "real-footage", "unsupported"),
    ("这个城市的早高峰采访", "real-footage", "unsupported"),
    ("三维展示细胞内部结构", "spatial-demo", "needs_extension"),
    ("用 AI 生成图讲莫奈的光", "generated-media", "needs_extension"),
    ("从历史影像看城市变化", "licensed-media", "needs_extension"),
])
def test_route_signals_map_to_honest_status(title, route, status):
    decision = classify_route(title)
    assert decision["route"] == route and decision["status"] == status


def test_unsupported_signal_wins_over_a_supported_one():
    decision = classify_route("三维演示：用录屏展示真实建模过程")
    assert decision["status"] == "unsupported"
    assert "真实" in decision["reason"] or "录屏" in decision["reason"]


def test_strictest_combines_gate_and_planner_claim():
    gate = classify_route("矩阵为什么能让空间旋转？")
    declared = {"route": "program-graphics", "status": "needs_extension",
                "reason": "选题声明需要新增能力", "substitute": "program-graphics"}
    assert strictest(gate, declared)["status"] == "needs_extension"
    assert strictest(gate, None)["status"] == "supported"


def test_renderer_capabilities_expose_route_status():
    routes = RENDERER_CAPABILITIES["routes"]
    assert routes["program-graphics"]["status"] == "supported"
    assert routes["real-footage"]["status"] == "unsupported"
    assert set(routes) == set(ROUTES)


# -------------------------------------------------------------- create gate

def test_create_refuses_a_topic_that_needs_real_footage(tmp_path):
    studio = make_studio(tmp_path, MockProvider({}))
    try:
        before = len(studio.ledger.list(10000))
        with pytest.raises(ValueError, match="无法真实呈现"):
            studio.create("跟着录屏一步步部署这个服务")
        assert len(studio.ledger.list(10000)) == before, "被拒绝的题目不应留下失败任务行"
    finally:
        studio.close()


def test_create_freezes_the_route_request(tmp_path):
    studio = make_studio(tmp_path, MockProvider({}))
    try:
        episode = studio.create("三维展示细胞内部结构")
        request = json.loads((studio.workspace / f"VID-{episode['id']:06d}" / "request.json")
                             .read_text(encoding="utf-8"))
        assert request["route"]["route"] == "spatial-demo"
        assert request["route"]["status"] == "needs_extension"
    finally:
        studio.close()


# ------------------------------------------------------------------- brief

def test_brief_uses_the_users_own_audience_words():
    brief = build_production_brief(title="矩阵", user_brief="面向高中生，语气轻松",
                                   research=research_model(), config={"studio": {"long_seconds": 180,
                                                                               "short_seconds": 60}})
    assert brief.audience == "高中生"
    assert "由 brief 指定" in brief.prior_knowledge
    assert brief.long_seconds == 180 and brief.short_seconds == 60


def test_brief_states_unspecified_audience_instead_of_inventing_one():
    audience, prior = audience_from(None)
    assert "未指定" in audience and "未指定" in prior


def test_brief_records_boundaries_and_unknown_cost():
    brief = build_production_brief(title="矩阵", user_brief=None, research=research_model(),
                                   config={"studio": {"long_seconds": 180, "short_seconds": 60}})
    assert brief.boundaries == ["这是测试用研究记录"]
    assert brief.budget.estimated_cost is None and brief.budget.currency == ""
    assert brief.budget.model_calls > 0
    assert brief.created_from["research"] and len(brief.created_from["research"]) == 64


def test_brief_marks_a_program_graphic_substitution():
    brief = build_production_brief(title="三维展示细胞内部结构", user_brief=None,
                                   research=research_model(),
                                   config={"studio": {"long_seconds": 180, "short_seconds": 60}})
    assert brief.route == "spatial-demo" and brief.route_status == "needs_extension"
    assert brief.effective_route == "program-graphics"
    assert brief.substitutions and "标注示意" in brief.substitutions[0]


def test_topic_violations_detect_a_silent_topic_change():
    brief = build_production_brief(title="矩阵", user_brief=None, research=research_model(),
                                   config={"studio": {"long_seconds": 180, "short_seconds": 60}})
    changed = research_model(question="完全不同的问题是什么")
    assert topic_violations(brief.model_dump(), title="矩阵", research=changed)
    assert topic_violations(brief.model_dump(), title="矩阵", research=research_model()) == []


# ------------------------------------------------------------------ pipeline

def _produce(root, title="矩阵为什么能让空间旋转？", research=None):
    provider = MockProvider({"research": research or research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(root, provider)
    episode = studio.create(title)
    result = studio.produce(episode["id"])
    job = studio.workspace / f"VID-{episode['id']:06d}"
    return studio, episode, result, job


def test_pipeline_writes_the_frozen_brief_and_uses_it(offline_pipeline):
    studio, _episode, result, job = _produce(offline_pipeline)
    try:
        brief = json.loads((job / "production-brief.json").read_text(encoding="utf-8"))
        assert brief["route_status"] == "supported"
        assert brief["effective_route"] == "program-graphics"
        assert brief["question"] == "矩阵如何改变空间？"
        prompt = (job / "agents" / "director-long-0" / "prompt.txt").read_text(encoding="utf-8")
        assert "production_brief" in prompt and "audience" in prompt
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["production_brief"]["route_status"] == "supported"
    finally:
        studio.close()


def test_pipeline_marks_a_substituted_route_in_the_report(offline_pipeline):
    studio, _episode, result, job = _produce(offline_pipeline, title="三维展示细胞内部结构")
    try:
        brief = json.loads((job / "production-brief.json").read_text(encoding="utf-8"))
        assert brief["route"] == "spatial-demo" and brief["route_status"] == "needs_extension"
        assert brief["substitutions"]
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["production_brief"]["route_status"] == "needs_extension"
    finally:
        studio.close()


from pathlib import Path  # noqa: E402
