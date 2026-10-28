"""S1-02: review consistency, axis readings and the release decision.

The old guard downgraded any finding that mentioned "刻度" — a keyword match, not
evidence.  Two runs of a vision model over the same stills disagreed about the
same tick labels, which is what motivated the guard, but the fix has to be
deterministic: the renderer generates ticks from the data, so a claimed label can
be compared with the labels that actually exist.  Anything else stays a finding.
"""
from __future__ import annotations

import pytest

from movelyth.models import Finding, Review
from movelyth.policy import (
    CheckResult,
    decide,
    normalize_review,
    review_checks,
    scene_ticks,
    technical_checks,
)

TICKS = {"l3": ["0", "2", "4", "6"]}


def review_with(issues=(), findings=(), *, passed=False, warnings=()) -> Review:
    return Review(passed=passed, issues=list(issues), strengths=["长短版分别编排"],
                  warnings=list(warnings), findings=list(findings))


# ---------------------------------------------------------------- consistency

def test_passed_true_cannot_override_a_factual_finding():
    """M01: a model boolean must not erase a factual defect."""
    raw = review_with([], [Finding(category="factual", scene_id="l2",
                                   detail="旁白说面积翻倍，公式给出 1.5 倍")], passed=True)
    result = normalize_review(raw)
    assert result["review"].passed is False
    assert result["raw"].passed is True  # the raw result stays on record
    assert any("阻断 finding" in change for change in result["changes"])


def test_passed_true_with_issues_is_not_a_pass():
    result = normalize_review(review_with(["l4 缺少单位"], passed=True))
    assert result["review"].passed is False
    assert result["changes"]


def test_passed_false_without_a_reason_is_not_silently_passed():
    result = normalize_review(review_with([], passed=False))
    assert result["review"].passed is False
    assert any("未给出任何理由" in change for change in result["changes"])


# -------------------------------------------------------------- axis readings

def test_claimed_labels_that_are_generated_ticks_become_traceable_warnings():
    raw = review_with(["长版 l3 纵轴刻度显示 3.11、5.63"], findings=[
        Finding(category="visual_mismatch", scene_id="l3", detail="纵轴刻度标签 4.0 与 6.0 顺序反了")])
    review, checks, notes = review_checks(raw, ticks_by_scene=TICKS)
    assert review.passed is True and review.findings == [] and review.issues == []
    assert all(check.status == "unknown" and not check.required for check in checks)
    assert checks[0].evidence["kind"] == "generated-tick-labels"
    assert checks[0].evidence["labels"] == ["0", "2", "4", "6"]
    assert notes


def test_a_claim_about_data_or_units_still_blocks():
    """M02: a wrong unit, a swapped axis or a data mismatch must not be downgraded."""
    raw = review_with([], [Finding(category="visual_mismatch", scene_id="l3",
                                   detail="纵轴刻度显示 0.76，但数据点标的是 5")])
    review, checks, _ = review_checks(raw, ticks_by_scene=TICKS)
    assert review.passed is False
    assert [check.status for check in checks] == ["fail"]
    assert checks[0].severity == "major"
    assert checks[0].evidence["kind"] == "claim-about-data-or-units"


def test_structural_defects_are_never_downgraded():
    raw = review_with([], [Finding(category="visual_mismatch", scene_id="l3",
                                   detail="纵轴刻度被裁切，标签缺字")])
    review, checks, _ = review_checks(raw, ticks_by_scene=TICKS)
    assert review.passed is False and checks[0].status == "fail"


def test_an_axis_claim_without_numbers_stays_unknown_not_pass():
    raw = review_with([], [Finding(category="visual_mismatch", scene_id="l3",
                                   detail="纵轴刻度好像不太对")])
    review, checks, _ = review_checks(raw, ticks_by_scene=TICKS)
    assert checks[0].status == "unknown" and checks[0].required is False
    assert checks[0].evidence["kind"] == "no-deterministic-evidence"
    assert review.passed is True  # nothing blocking remains, but the doubt is recorded


def test_strict_policy_keeps_every_axis_reading_as_a_blocker():
    raw = review_with([], [Finding(category="visual_mismatch", scene_id="l3",
                                   detail="纵轴刻度 4 与 6 对不上数据")])
    review, checks, _ = review_checks(raw, ticks_by_scene=TICKS, axis_policy="strict")
    assert review.passed is False and checks[0].status == "fail"


def test_a_clean_review_stays_clean():
    raw = review_with([], passed=True, warnings=["未人工实听"])
    review, checks, notes = review_checks(raw, ticks_by_scene=TICKS)
    assert review.passed is True and review.warnings == ["未人工实听"]
    assert checks == [] and notes == []


# ------------------------------------------------------------------- decision

def test_generated_ticks_come_from_the_cut():
    scenes = [{"id": "l1", "layers": [{"type": "chart", "series": [
        {"label": "均值", "values": [3, 4, 4, 5, 34]}]}]}]
    assert scene_ticks(scenes) == {"l1": ["0", "10", "20", "30", "40"]}


def test_major_failure_blocks_and_required_unknown_needs_review():
    report = {"checks": {"full_decode": True, "audible": True, "dimensions": False},
              "duration": 60.0, "width": 1280, "height": 720, "fps": 30.0}
    checks = technical_checks(report, cut="long")
    decision = decide(checks)
    assert decision.decision == "blocked"
    assert [check.check_id for check in decision.blocking] == ["technical.long.dimensions"]


def test_minor_failure_is_only_a_warning():
    checks = [CheckResult(check_id="technical.long.fps", source="technical", status="fail",
                          severity="minor")]
    decision = decide(checks)
    assert decision.decision == "ready"
    assert decision.warnings and not decision.blocking


def test_required_unknown_forces_review():
    checks = [CheckResult(check_id="audio.long.transcript", source="audio", status="unknown",
                          severity="major", required=True, observation="语音核对超时")]
    decision = decide(checks)
    assert decision.decision == "needs_review"
    assert decision.reasons == ["语音核对超时"]


def test_optional_unknown_and_not_applicable_stay_out_of_the_way():
    checks = [CheckResult(check_id="audio.long.transcript", source="audio", status="not_applicable",
                          severity="minor", required=False, observation="ASR 未启用"),
              CheckResult(check_id="review.visual.axis.l3", source="model", status="unknown",
                          severity="minor", required=False)]
    decision = decide(checks)
    assert decision.decision == "ready"
    assert decision.not_applicable and decision.warnings


# --------------------------------------------------------------- configuration

def test_axis_policy_reads_the_new_key_and_the_legacy_alias():
    from movelyth.pipeline import axis_reading_policy

    assert axis_reading_policy({}) == "deterministic"
    assert axis_reading_policy({"axis_reading_policy": "strict"}) == "strict"
    # Pre-v2 configs keep working, but only as an alias for the two explicit modes.
    assert axis_reading_policy({"downgrade_axis_readings": True}) == "deterministic"
    assert axis_reading_policy({"downgrade_axis_readings": False}) == "strict"
    with pytest.raises(ValueError, match="axis_reading_policy"):
        axis_reading_policy({"axis_reading_policy": "sometimes"})
    with pytest.raises(ValueError, match="downgrade_axis_readings"):
        axis_reading_policy({"downgrade_axis_readings": "yes"})
