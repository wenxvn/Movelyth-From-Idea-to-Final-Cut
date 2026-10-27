"""The axis-reading guard, tested against the reviewer output that motivated it.

Two runs of a vision model over the same stills reported different tick numbers for
the same chart, which means the numbers were guessed.  Chart ticks are generated
deterministically from the data range and covered by tests, so those findings must
not force a re-render — but a finding that also names a structural defect must.
"""
from __future__ import annotations

from movelyth.models import Finding, Review
from movelyth.quality import downgrade_axis_readings


def review_with(issues, findings=None, *, passed=False, warnings=None) -> Review:
    return Review(passed=passed, issues=list(issues), strengths=["长短版分别编排"],
                  warnings=list(warnings or []), findings=list(findings or []))


def test_a_pure_tick_reading_becomes_a_warning_instead_of_a_blocker():
    raw = review_with(["长版 l3 纵轴刻度显示 3.11、5.63、2.14，与数据不符"])
    guard = downgrade_axis_readings(raw)
    assert guard["applied"]
    assert guard["review"].issues == []
    assert guard["review"].passed is True
    assert "已降级为参考" in guard["review"].warnings[-1]
    assert len(guard["downgraded"]) == 1


def test_a_structural_defect_in_the_same_finding_still_blocks():
    raw = review_with(["长版 l7 向量示意图过暗近乎空白，且纵轴刻度不对"])
    guard = downgrade_axis_readings(raw)
    assert guard["applied"] is False
    assert guard["review"].issues == ["长版 l7 向量示意图过暗近乎空白，且纵轴刻度不对"]
    assert guard["review"].passed is False


def test_findings_are_classified_individually():
    findings = [Finding(category="visual_mismatch", scene_id="l3",
                        detail="纵轴刻度 3.11/5.63/2.14 与数据 11.25/5/1.25/0 不对应"),
                Finding(category="visual_defect", scene_id="l7",
                        detail="向量示意图主体过暗，画面大面积空白"),
                Finding(category="factual", scene_id="l2",
                        detail="旁白说面积翻倍，公式给出 1.5 倍")]
    raw = review_with(["问题一", "问题二"], findings=findings)
    guard = downgrade_axis_readings(raw)
    kept = [f.scene_id for f in guard["review"].findings]
    assert kept == ["l7", "l2"]
    assert guard["review"].passed is False  # real findings remain


def test_only_axis_findings_means_the_review_passes():
    findings = [Finding(category="visual_mismatch", scene_id="l6",
                        detail="柱状图 y-axis ticks 21.5/15.2/3.86 与柱顶标签不符")]
    guard = downgrade_axis_readings(review_with(["柱状图刻度错位"], findings=findings))
    assert guard["review"].issues == [] and guard["review"].findings == []
    assert guard["review"].passed is True
    assert len(guard["review"].warnings) == 2


def test_the_guard_can_be_disabled_for_a_model_that_reads_ticks_reliably():
    raw = review_with(["长版 l3 纵轴刻度显示 3.11，与数据不符"])
    guard = downgrade_axis_readings(raw, enabled=False)
    assert guard["applied"] is False
    assert guard["review"].issues and guard["review"].passed is False


def test_a_clean_review_is_untouched():
    raw = review_with([], passed=True, warnings=["未人工实听"])
    guard = downgrade_axis_readings(raw)
    assert guard["applied"] is False
    assert guard["review"].warnings == ["未人工实听"]
    assert guard["review"].passed is True
