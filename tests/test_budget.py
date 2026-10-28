"""S1-07: budget gate, per-stage run records and configuration strictness."""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from movelyth.budget import (
    BudgetExceeded,
    BudgetLedger,
    BudgetState,
    Cost,
    Usage,
    budget_from_config,
    provider_snapshot,
    usage_since,
)
from movelyth.pipeline import settings, validate_settings
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload

# ------------------------------------------------------------------- budget

def test_reserve_prevents_overspending_before_the_call():
    state = BudgetState(limits={"model_calls": 3})
    state.reserve(model_calls=2)
    with pytest.raises(BudgetExceeded, match="model_calls"):
        state.reserve(model_calls=2)
    assert state.remaining()["model_calls"] == 1


def test_settle_clears_the_reservation_and_records_usage():
    state = BudgetState(limits={"model_calls": 3})
    state.reserve(model_calls=2)
    state.settle({"model_calls": 1}, reserved={"model_calls": 2})
    assert state.used["model_calls"] == 1 and state.reserved["model_calls"] == 0
    state.reserve(model_calls=2)  # still room for two more


def test_unknown_cost_is_null_not_zero():
    cost = Cost()
    assert cost.actual is None and cost.estimate is None and cost.currency == ""


def test_usage_keeps_missing_measurements_unknown():
    usage = Usage(model_calls=1)
    assert usage.input_tokens is None and usage.output_tokens is None
    assert usage.counters() == {"model_calls": 1.0}


def test_usage_since_counts_only_the_stage(monkeypatch):
    provider = MockProvider({})
    provider.usage_total = {"prompt_tokens": 100, "completion_tokens": 50}
    provider.call_count = 1
    before = provider_snapshot(provider)
    provider.usage_total = {"prompt_tokens": 180, "completion_tokens": 90}
    provider.call_count = 3
    usage = usage_since(provider, before)
    assert usage.model_calls == 2 and usage.input_tokens == 80 and usage.output_tokens == 40


def test_budget_from_config_overrides_only_known_counters():
    state = budget_from_config({"budget": {"model_calls": 5, "currency": "CNY",
                                          "price_version": "2026-10"}})
    assert state.limits["model_calls"] == 5 and state.limits["render_minutes"] == 30
    assert state.currency == "CNY" and state.price_version == "2026-10"


# ---------------------------------------------------------------- config

def test_unknown_setting_is_rejected_with_its_name():
    with pytest.raises(ValueError, match="studio.long_second"):
        validate_settings({"studio": {"long_second": 90}})


def test_unknown_section_is_rejected():
    with pytest.raises(ValueError, match="未知配置分区"):
        validate_settings({"studios": {}})


def test_the_shipped_configuration_is_valid():
    from pathlib import Path

    config = settings(Path(__file__).parents[1])
    assert config["budget"]["model_calls"] >= 1
    assert config["studio"]["axis_reading_policy"] in {"deterministic", "strict"}


# ---------------------------------------------------------------- pipeline

def _studio(root, provider=None):
    provider = provider or MockProvider({"research": research_payload(), "director": film(),
                                         "reviewer": review_payload()})
    return make_studio(root, provider)


def test_stage_records_are_written_with_usage_and_cost(offline_pipeline):
    studio = _studio(offline_pipeline)
    try:
        episode = studio.create("预算记录测试")
        studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        records = [json.loads(line) for line in
                   (job / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
        stages = {record["stage"] for record in records}
        assert {"research", "evidence", "brief", "script", "sound", "render", "check"} <= stages
        research = next(record for record in records if record["stage"] == "research")
        assert research["status"] == "passed" and research["seconds"] >= 0
        assert research["calls"] == 1 and research["input_hash"]
        assert research["cost"]["actual"] is None and research["cost"]["currency"] == "CNY"
        sound = next(record for record in records if record["stage"] == "sound")
        assert sound["usage"]["tts_characters"] > 0 and sound["usage"]["tts_seconds"] > 0
        render = next(record for record in records if record["stage"] == "render")
        assert render["usage"]["render_seconds"] is not None
        state = json.loads((job / "budget.json").read_text(encoding="utf-8"))
        assert state["used"]["model_calls"] >= 1
        assert state["used"]["tts_characters"] > 0
        # A second produce is a delivery reuse: no stage runs, so no extra spend.
        again = studio.produce(episode["id"])
        assert again["reused"] is True
        after = (job / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(after) == len(records)
    finally:
        studio.close()


def test_a_failed_stage_records_its_usage_and_error_type(tmp_path):
    studio = _studio(tmp_path)
    try:
        episode = studio.create("失败记录测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"

        def action():
            raise RuntimeError("模拟媒体失败")

        with pytest.raises(RuntimeError, match="模拟媒体失败"):
            studio.stage(episode, "demo", {"x": 1}, action)
        record = json.loads((job / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert record["status"] == "failed" and record["error_type"] == "RuntimeError"
        assert "模拟媒体失败" in record["detail"]
    finally:
        studio.close()


def test_an_exhausted_budget_stops_before_spending(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        studio.config["budget"]["model_calls"] = 0
        episode = studio.create("预算耗尽测试")
        with pytest.raises(BudgetExceeded):
            studio.produce(episode["id"])
        assert provider.calls == [], "预算耗尽后不得再提交模型调用"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        assert not (job / "research.json").exists()
        assert studio.ledger.get(episode["id"])["status"] == "failed"
    finally:
        studio.close()


def test_budget_state_survives_a_resume(offline_pipeline):
    studio = _studio(offline_pipeline)
    try:
        episode = studio.create("预算持久化测试")
        studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        used = json.loads((job / "budget.json").read_text(encoding="utf-8"))["used"]
        reloaded = BudgetLedger.load(job, studio.config)
        assert reloaded.state.used == used
        assert reloaded.summary()["remaining"]["model_calls"] < reloaded.state.limits["model_calls"]
    finally:
        studio.close()


def test_a_cached_stage_is_recorded_without_spend(offline_pipeline):
    studio = _studio(offline_pipeline)
    try:
        episode = studio.create("缓存记录测试")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        output = job / "cached.txt"
        calls = []

        def action():
            calls.append(1)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("ok", encoding="utf-8")
            return {"ok": True}, [output]

        studio.stage(episode, "demo", {"k": 1}, action)
        studio.stage(episode, "demo", {"k": 1}, action)
        records = [json.loads(line) for line in
                   (job / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [record["status"] for record in records] == ["passed", "cached"]
        assert records[1]["cache"] is True and records[1]["calls"] == 0
        assert len(calls) == 1
    finally:
        studio.close()
