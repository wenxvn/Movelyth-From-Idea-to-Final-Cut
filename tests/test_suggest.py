import json

import pytest

from movelyth.agents import MockProvider
from movelyth.models import TopicPlan
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload


def plan(capabilities: list[str]) -> dict:
    return {"candidates": [
        {"title": f"候选题目{i + 1}", "question": f"第{i + 1}个问题是什么？",
         "why_now": "与已完成内容不重复，且能用现有图层讲清。",
         "visual_plan": ["折线图展示趋势", "有向图展示步骤"],
         "capability": capability, "risks": [] if capability == "supported" else ["缺少专用组件"]}
        for i, capability in enumerate(capabilities)
    ], "notes": []}


def test_suggest_returns_structured_candidates_without_reserving_an_episode(tmp_path):
    provider = MockProvider({"planner": plan(["supported", "needs_extension", "unsupported"])})
    studio = make_studio(tmp_path, provider)
    try:
        result = studio.suggest(count=3)
        assert result["provider"] == "mock"
        assert len(result["candidates"]) == 3
        assert result["supported"] == ["候选题目1"]
        assert result["candidates"][1]["capability"] == "needs_extension"
        assert (studio.workspace / "topic-plan" / "plan.json").is_file()
        assert studio.ledger.list() == [], "选题建议不得占用编号"
        assert provider.calls == ["planner"]
    finally:
        studio.close()


def test_daily_refuses_when_no_candidate_is_supported(tmp_path):
    provider = MockProvider({"planner": plan(["unsupported", "needs_extension"])})
    studio = make_studio(tmp_path, provider)
    try:
        with pytest.raises(ValueError, match="未自动生成"):
            studio.daily(count=2)
        assert studio.ledger.list() == []
    finally:
        studio.close()


def test_daily_uses_the_same_create_pipeline(offline_pipeline):
    provider = MockProvider({"planner": plan(["supported"]), "research": research_payload(),
                             "director": film(), "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        result = studio.daily(count=1, preview_only=True)
        assert result["chosen"]["title"] == "候选题目1"
        assert result["episode"]["status"] == "previewed"
        assert "不会自动定时运行" in result["note"]
        episode = studio.ledger.get(result["episode"]["id"])
        assert episode["title"] == "候选题目1"
    finally:
        studio.close()


def test_planner_contract_bounds_the_candidates():
    with pytest.raises(Exception):
        TopicPlan.model_validate({"candidates": []})
    with pytest.raises(Exception):
        TopicPlan.model_validate({"candidates": [
            {"title": "题", "question": "这是一个问题吗？", "why_now": "值得做",
             "visual_plan": ["x"], "capability": "maybe"}]})
    payload = plan(["supported"])
    payload["candidates"][0]["visual_plan"] = ["好" * 81]
    with pytest.raises(Exception):
        TopicPlan.model_validate(payload)


def test_suggest_rejects_out_of_range_count(tmp_path):
    studio = make_studio(tmp_path, MockProvider({"planner": plan(["supported"])}))
    try:
        with pytest.raises(ValueError, match="1–5"):
            studio.suggest(count=0)
        with pytest.raises(ValueError, match="1–5"):
            studio.suggest(count=6)
    finally:
        studio.close()


def test_suggest_writes_plan_json_with_history_context(tmp_path):
    provider = MockProvider({"planner": plan(["supported"])})
    studio = make_studio(tmp_path, provider)
    try:
        studio.create("已完成的题目")
        studio.suggest()
        prompt = (studio.workspace / "topic-plan" / "agents" / "planner" / "prompt.txt").read_text(encoding="utf-8")
        assert "已完成的题目" in prompt, "选题必须看到历史，避免语义重复"
        data = json.loads((studio.workspace / "topic-plan" / "plan.json").read_text(encoding="utf-8"))
        assert data["candidates"][0]["capability"] == "supported"
    finally:
        studio.close()
