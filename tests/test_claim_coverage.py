"""S1-04: evidence is fetched and claims are located before the film is directed.

Retrieval, parsing and claim support are separate states.  A source can be
retrieved while the claimed excerpt is absent from it, and an unfetched source can
never support anything — both must be caught before an expensive render, not after.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from movelyth.agents import MockProvider
from movelyth.models import Research
from movelyth.policy import claim_usage_checks, decide, source_checks
from movelyth.sources import coverage_summary, locate_excerpt, verify_claims
from tests.conftest import make_studio
from tests.factories import chart_layer, film, research_payload, review_payload, scene


def research_model(**overrides) -> Research:
    payload = research_payload()
    payload.update(overrides)
    return Research.model_validate(payload)


def snapshot(url="https://example.com/linear-algebra", **overrides) -> dict:
    item = {"url": url, "status": "retrieved", "content_sha256": "a" * 64,
            "retrieved_at": "2026-10-28T00:00:00+08:00", "title": "示例课程",
            "excerpt": "矩阵的列是基向量的像。columns are images of basis vectors."}
    item.update(overrides)
    return item


# ------------------------------------------------------------ excerpt location

def test_excerpt_location_ignores_whitespace_and_case():
    position = locate_excerpt("COLUMNS   are images of basis vectors",
                              "前言 矩阵的列是基向量的像。columns are images of basis vectors. 结尾")
    assert position and position["start"] < position["end"]


def test_an_absent_excerpt_is_not_supported():
    assert locate_excerpt("这句话不在正文里", "一段完全不同的正文") is None


# ------------------------------------------------------------- claim checking

def test_supported_claim_records_position_and_hash():
    checks = verify_claims(research_model(), [snapshot()])
    assert checks[0]["status"] == "supported"
    assert checks[0]["position"]["start"] >= 0
    assert checks[0]["content_sha256"] == "a" * 64
    assert coverage_summary(checks)["supported_key_claims"] == 1


def test_missing_excerpt_is_reported_as_invented_evidence():
    checks = verify_claims(research_model(), [snapshot(excerpt="完全无关的正文")])
    assert checks[0]["status"] == "excerpt-missing"
    assert "找不到" in checks[0]["detail"]


def test_claim_beyond_preview_prefix_is_found_in_complete_snapshot():
    prefix = "无关内容 " * 5000
    evidence = snapshot(excerpt=prefix[:16000], search_text=prefix + " columns are images of basis vectors.")
    check = verify_claims(research_model(), [evidence])[0]
    assert check["status"] == "supported"
    assert check["position"]["start"] > 16000


def test_unfetched_source_never_supports_a_claim():
    checks = verify_claims(research_model(), [snapshot(status="unavailable", error="HTTP 403")])
    assert checks[0]["status"] == "source-unavailable"
    assert "HTTP 403" in checks[0]["detail"]


def test_claim_pointing_at_a_missing_source_is_rejected_by_the_model():
    payload = research_payload()
    payload["claims"][0]["source_index"] = 4
    with pytest.raises(ValidationError, match="不存在的来源"):
        Research.model_validate(payload)
    payload = research_payload()
    payload["claims"][0]["evidence_refs"] = [9]
    with pytest.raises(ValidationError, match="evidence_refs"):
        Research.model_validate(payload)


# ------------------------------------------------------------------- policy

def test_no_claims_cannot_pass_the_factual_gate():
    decision = decide(source_checks([]))
    assert decision.decision == "blocked"
    assert "claims 为空" in decision.blocking[0].observation


def test_invented_excerpt_is_a_critical_failure():
    checks = source_checks(verify_claims(research_model(), [snapshot(excerpt="无关正文")]))
    decision = decide(checks)
    assert decision.decision == "blocked"
    assert decision.blocking[0].severity == "critical"


def test_uncertain_scope_is_a_warning_not_a_blocker():
    payload = research_payload()
    payload["claims"][0]["scope"] = "uncertain"
    checks = source_checks(verify_claims(Research.model_validate(payload), [snapshot()]))
    decision = decide(checks)
    assert decision.decision == "ready"
    assert any(check.check_id.endswith(".uncertain") for check in decision.warnings)


def test_a_key_claim_that_never_reaches_a_scene_blocks():
    coverage = [{"claim_id": "c1", "statement": "矩阵的列是基向量的像", "status": "supported",
                 "scope": "established", "importance": "key", "source_index": 3,
                 "evidence_refs": [], "source_url": "https://example.com"}]
    checks = claim_usage_checks(film(), coverage)
    assert any(check.status == "fail" and "没有进入任何镜头" in check.observation for check in checks)


def test_a_narration_number_outside_the_evidence_is_reported_not_blocked():
    payload = film()
    payload["long"]["scenes"][0]["narration"] = "矩阵把单位正方形变成平行四边形，面积放大 37 倍。"
    coverage = [{"claim_id": "c1", "statement": "矩阵的列是基向量的像", "status": "supported",
                 "scope": "established", "importance": "key", "source_index": 0,
                 "evidence_refs": [], "source_url": "https://example.com"}]
    checks = claim_usage_checks(payload, coverage)
    numbers = [check for check in checks if check.check_id.endswith(".numbers")]
    assert numbers and "37" in numbers[0].observation
    assert decide(checks).decision == "ready"  # recorded as an optional unknown


def test_numeric_claim_is_unknown_when_only_subtitles_narrate_the_missing_value():
    graphic = chart_layer(values=[4], source_note="自行构造示意数据")
    shot = scene("one", narration="这里说到数字三十四，但图上没有这个值。", layers=[graphic],
                 claim_ids=["c1"])
    payload = film(long_scenes=[shot], short_scenes=[{**shot, "id": "s1"}])
    coverage = [{"claim_id": "c1", "statement": "该数据从 4 变为 34", "status": "supported",
                 "scope": "established", "importance": "key", "source_index": 0,
                 "evidence_refs": []}]

    checks = claim_usage_checks(payload, coverage)
    visual = next(check for check in checks if check.check_id == "source.visual.long.c1.numbers")
    assert visual.status == "unknown"
    assert "34" in visual.observation
    assert decide(checks).decision == "ready"  # optional warning, never a silent pass


def test_lost_condition_and_illustrative_scope_are_reported_for_visual_review():
    shot = scene("one", layers=[chart_layer(values=[4, 34], source_note="")], claim_ids=["c1"])
    payload = film(long_scenes=[shot], short_scenes=[{**shot, "id": "s1"}])
    coverage = [{"claim_id": "c1", "statement": "仅在本例中，数据从 4 变为 34", "status": "supported",
                 "scope": "illustrative", "importance": "key", "source_index": 0,
                 "evidence_refs": []}]

    checks = claim_usage_checks(payload, coverage)
    ids = {check.check_id: check for check in checks}
    assert ids["source.visual.long.c1.scope"].status == "unknown"
    assert ids["source.visual.long.c1.boundary"].status == "unknown"


def test_screen_data_without_claim_or_source_note_is_reported_as_unmapped():
    shot = scene("one", layers=[chart_layer(values=[4, 99], source_note="")], claim_ids=["c1"])
    payload = film(long_scenes=[shot], short_scenes=[{**shot, "id": "s1"}])
    coverage = [{"claim_id": "c1", "statement": "数据从 4 变为 34", "status": "supported",
                 "scope": "established", "importance": "key", "source_index": 0,
                 "evidence_refs": []}]

    checks = claim_usage_checks(payload, coverage)
    visual = next(check for check in checks if check.check_id == "source.visual.long.c1.reverse")
    assert visual.status == "unknown"
    assert "99" in visual.observation


# --------------------------------------------------------- pipeline ordering

def test_unsupported_claim_blocks_before_the_director_is_called(offline_pipeline, monkeypatch):
    monkeypatch.setattr("movelyth.sources.collect_sources", lambda sources, directory: [
        {"url": source["url"], "status": "retrieved", "content_sha256": "0" * 64,
         "retrieved_at": "2026-10-28T00:00:00+08:00", "title": source["label"],
         "excerpt": "这段正文没有包含研究声称的节选"} for source in sources])
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("证据不支持测试")
        # An unsupported claim is an editorial defect: it goes back for a routed
        # repair (and still fails after the retry budget, never reaching delivery).
        with pytest.raises(RuntimeError, match="source.research.c1"):
            studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        coverage = json.loads((job / "claim-coverage.json").read_text(encoding="utf-8"))
        assert coverage["claims"][0]["status"] == "excerpt-missing"
        assert coverage["summary"]["by_status"] == {"excerpt-missing": 1}
        decision = json.loads((job / "release-decision.json").read_text(encoding="utf-8"))
        assert decision["decision"] == "blocked"
        assert any(check["check_id"] == "source.research.c1" for check in decision["blocking"])
    finally:
        studio.close()


def test_evidence_is_fetched_before_directing(offline_pipeline, monkeypatch):
    calls: list[str] = []
    from movelyth import sources as sources_module

    real = sources_module.collect_sources

    def spy(items, directory, **kwargs):
        calls.append("evidence")
        return real(items, directory, **kwargs)

    monkeypatch.setattr("movelyth.sources.collect_sources", spy)
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    original_call = provider.call

    def recorded(role, context, contract, directory, images=None, sanitize=None):
        if role == "director":
            calls.append("director")
        return original_call(role, context, contract, directory, images=images, sanitize=sanitize)

    provider.call = recorded
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("证据顺序测试")
        studio.produce(episode["id"])
        assert calls.index("evidence") < calls.index("director")
        job = studio.workspace / f"VID-{episode['id']:06d}"
        prompt = (job / "agents" / "director-long-0" / "prompt.txt").read_text(encoding="utf-8")
        assert "claim_coverage" in prompt and "source_evidence" in prompt
        assert "columns are images of basis vectors" in prompt
    finally:
        studio.close()
