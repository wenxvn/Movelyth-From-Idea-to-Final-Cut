"""S4-05: versioned feedback, comparable windows and located viewer issues."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from movelyth.feedback import (
    METRICS,
    Observation,
    ViewerIssue,
    append_observation,
    compare,
    hypothesis,
    load_observations,
    parse_metrics,
)
from tests.conftest import make_studio


def observation(**overrides) -> Observation:
    payload = {"episode": "VID-000025", "revision": 21, "cut": "long", "platform": "bilibili",
               "url": "https://www.bilibili.com/video/BV1xx", "observed_at": "2026-10-28T10:00:00+08:00",
               "window": "24h", "metrics": {"views": 1000.0, "likes": 40.0}}
    payload.update(overrides)
    return Observation(**payload)


def test_an_observation_records_the_version_it_belongs_to():
    record = observation()
    assert record.revision == 21 and record.cut == "long"
    assert record.metrics["views"] == 1000.0


def test_an_unknown_metric_is_absent_not_zero():
    metrics = parse_metrics({"views": 10, "likes": None, "completion_rate": ""})
    assert metrics == {"views": 10.0}
    assert "likes" not in metrics and "completion_rate" not in metrics


def test_an_unknown_metric_name_is_rejected():
    with pytest.raises(ValueError, match="未知指标"):
        observation(metrics={"play_count": 10})


def test_negative_counts_and_out_of_range_windows_are_rejected():
    with pytest.raises(ValueError, match="不能为负"):
        observation(metrics={"views": -1})
    with pytest.raises(ValueError, match="window"):
        observation(window="forever")


def test_two_observations_are_comparable_only_with_the_same_version_and_window():
    first = observation()
    same = observation(metrics={"views": 1400.0, "likes": 40.0})
    result = compare(first, same)
    assert result["comparable"] is True and result["deltas"]["views"] == 400.0
    assert result["deltas"]["likes"] == 0.0

    newer_revision = observation(revision=22)
    blocked = compare(first, newer_revision)
    assert blocked["comparable"] is False and "revision" in blocked["problems"][0]

    other_window = observation(window="7d")
    assert compare(first, other_window)["comparable"] is False

    other_cut = observation(cut="short")
    assert compare(first, other_cut)["comparable"] is False


def test_a_metric_missing_from_one_side_stays_null():
    result = compare(observation(metrics={"views": 10.0}),
                     observation(metrics={"views": 20.0, "likes": 5.0}))
    assert result["deltas"]["likes"] is None


def test_a_viewer_issue_becomes_a_testable_hypothesis():
    issue = ViewerIssue(episode="VID-000025", revision=21, cut="long", at_seconds=73.5,
                        scene_id="l4", kind="too_fast",
                        original="这一段字幕来不及看，语速也太快")
    result = hypothesis(issue)
    assert result["status"] == "unverified"
    assert result["scene_id"] == "l4" and result["at_seconds"] == 73.5
    assert "caption_reading_speed" in result["checks"]
    assert "不是结论" in result["note"]


@pytest.mark.parametrize("kind,check", [
    ("wrong", "claim_coverage"),
    ("audio", "mix_balance"),
    ("visual", "camera_plan"),
    ("caption", "srt_matches_cues"),
    ("unclear", "scene_hold_reason"),
])
def test_each_issue_kind_maps_to_the_check_that_would_show_it(kind, check):
    issue = ViewerIssue(episode="VID-000001", revision=1, kind=kind, original="观众反馈内容")
    assert check in hypothesis(issue)["checks"]


def test_observations_round_trip_and_skip_bad_rows(tmp_path):
    path = tmp_path / "feedback.json"
    append_observation(path, observation())
    append_observation(path, observation(window="7d"))
    assert len(load_observations(path)) == 2
    path.write_text(json.dumps({"observations": [{"episode": "bad"}, observation().model_dump()]}),
                    encoding="utf-8")
    assert len(load_observations(path)) == 1
    assert load_observations(tmp_path / "missing.json") == []


def test_the_cli_records_a_versioned_observation(tmp_path, capsys):
    from movelyth.cli import main

    config = Path(__file__).parents[1] / "movelyth.toml"
    (tmp_path / "movelyth.toml").write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    studio = make_studio(tmp_path)
    try:
        episode = studio.create("反馈记录测试")
        episode_id = episode["id"]
        revision = episode["revision"]
    finally:
        studio.close()
    code = main(["--root", str(tmp_path), "feedback", str(episode_id), "--platform", "bilibili",
                 "--url", "https://www.bilibili.com/video/BV1test", "--views", "120",
                 "--window", "24h", "--cut", "short"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["observation"]["revision"] == revision
    assert payload["observation"]["window"] == "24h" and payload["observation"]["cut"] == "short"
    assert "没有抓取平台留存" in payload["note"]
    stored = json.loads((tmp_path / "workspace" / "feedback.json").read_text(encoding="utf-8"))
    assert stored["observations"][0]["metrics"] == {"views": 120.0}
    assert "likes" not in stored["observations"][0]["metrics"]


def test_metric_list_is_documented():
    assert "completion_rate" in METRICS and "views" in METRICS
