"""S4-04: one configuration, a topic, and an actionable status."""
from __future__ import annotations

import json
from pathlib import Path

from movelyth.agents import MockProvider
from movelyth.report import BLOCKER_KINDS, classify_error, review_items, summary
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload


def _run(root, title="状态摘要测试", reviewer=None):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": reviewer or review_payload()})
    studio = make_studio(root, provider)
    episode = studio.create(title)
    return studio, episode


def test_a_ready_episode_summarises_what_was_checked(offline_pipeline):
    studio, episode = _run(offline_pipeline)
    try:
        result = studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        report = summary(job, studio.ledger.get(episode["id"]))
        assert report["status"] == "ready"
        assert report["decision"] == "ready"
        assert report["route"]["status"] == "supported"
        assert report["precheck"]["passed"] is True
        assert "配音与混音" in report["stages_done"]
        assert report["problems"] == []
        assert "上传仍需要你本人完成" in report["next"]
        assert report["budget"]["used"]["model_calls"] >= 1
        assert Path(result["delivery"]).is_dir()
    finally:
        studio.close()


def test_a_blocked_episode_reports_the_located_problem(offline_pipeline):
    reviewer = {"passed": True, "issues": [], "strengths": [], "warnings": [],
                "findings": [{"category": "factual", "scene_id": "two",
                              "detail": "结论与证据冲突，超出适用范围"}]}
    studio, episode = _run(offline_pipeline, "阻断摘要测试", reviewer)
    try:
        try:
            studio.produce(episode["id"])
        except RuntimeError:
            pass
        job = studio.workspace / f"VID-{episode['id']:06d}"
        report = summary(job, studio.ledger.get(episode["id"]))
        assert report["status"] == "failed"
        assert report["error"]["kind"] == "review"
        assert report["error"]["label"] == BLOCKER_KINDS["review"]
        assert any(item["where"].get("scene_id") == "two" for item in report["problems"])
        assert "revise" in report["next"] or "resume" in report["next"]
    finally:
        studio.close()


def test_review_items_are_ordered_blocking_first(tmp_path):
    job = tmp_path
    (job / "release-decision.json").write_text(json.dumps({
        "decision": "blocked",
        "blocking": [{"check_id": "review.visual.factual.1", "source": "model",
                      "observation": "事实错误", "repairable": True,
                      "location": {"scene_id": "two", "stage": "visual"}}],
        "review": [{"check_id": "audio.long.content", "source": "audio",
                    "observation": "需要复听", "repairable": True, "location": {"cut": "long"}}],
    }, ensure_ascii=False), encoding="utf-8")
    items = review_items(job)
    assert [item["severity"] for item in items] == ["阻断", "待复核"]
    assert items[0]["where"]["scene_id"] == "two"


def test_each_error_kind_maps_to_a_user_action(tmp_path):
    cases = {
        "预算不足：model_calls 40+1 > 40": "budget",
        "当前管线无法真实呈现该题目：需要真实录屏": "capability",
        "素材库中没有 own_photo": "asset",
        "缺少 ffprobe：媒体验证无法进行": "resource",
        "需要复核：audio.long.content": "review",
        "未知配置项：studio.long_second": "config",
    }
    for message, kind in cases.items():
        assert classify_error(message) == kind, message
        assert kind in BLOCKER_KINDS
    (tmp_path / "stages").mkdir()
    report = summary(tmp_path, {"id": 1, "title": "x", "status": "failed",
                                "revision": 1, "error": "缺少 ffprobe"})
    assert report["error"]["kind"] == "resource"
    assert "doctor" in report["next"]


def test_status_does_not_invent_progress(tmp_path):
    """A planned episode has no stages, no decision and no route yet."""
    (tmp_path / "stages").mkdir()
    report = summary(tmp_path, {"id": 7, "title": "未开始", "status": "planned", "revision": 1})
    assert report["stages_done"] == []
    assert report["decision"] is None and report["route"]["status"] is None
    assert report["next"] == "等待运行"


def test_capabilities_command_lists_only_real_capabilities(tmp_path, capsys):
    from movelyth.cli import main

    config = Path(__file__).parents[1] / "movelyth.toml"
    (tmp_path / "movelyth.toml").write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["--root", str(tmp_path), "capabilities"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["routes"]["program-graphics"]["status"] == "supported"
    assert payload["routes"]["real-footage"]["status"] == "unsupported"
    assert set(payload["recipes"]) == {"chart-focus", "same-scale-compare", "parameter-process",
                                       "flow-expand", "paper-evidence", "conclusion-callback"}
    assert set(payload["parameter_functions"]) == {"iteration", "linear-transform", "projection"}
    assert payload["optional"]["S3-07 三维/shader/生成后端"] == "optional_deferred"
    assert payload["missing_components"] == []
