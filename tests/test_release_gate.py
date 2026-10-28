"""S1-02 integration: the release decision gates delivery and is recorded.

The unit tests cover the policy; these run the real (offline) pipeline so the
wiring — technical checks, audio checks, review normalisation, the decision file
and the delivery gate — is proven together.
"""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from tests.conftest import make_studio
from tests.factories import chart_layer, film, layer, research_payload, review_payload, scene


def _studio(root, reviewer):
    provider = MockProvider({"research": research_payload(), "director": film(), "reviewer": reviewer})
    return make_studio(root, provider)


def test_release_decision_is_written_and_lists_the_checks(offline_pipeline):
    studio = _studio(offline_pipeline, review_payload())
    try:
        episode = studio.create("交付决定记录测试")
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        decision = json.loads((job / "release-decision.json").read_text(encoding="utf-8"))
        assert decision["decision"] == "ready"
        assert decision["policy_version"] == "2"
        assert decision["blocking"] == []
        assert "technical.long.full_decode" in decision["passed"]
        assert "technical.short.full_decode" in decision["passed"]
        assert decision["inputs"]["episode"] == f"VID-{episode['id']:06d}"
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["release_decision"]["decision"] == "ready"
    finally:
        studio.close()


def test_passed_true_with_a_factual_finding_blocks_delivery(offline_pipeline):
    """M01 at pipeline level: the model's own boolean cannot wave a fact error through."""
    reviewer = {"passed": True, "issues": [], "strengths": ["叙事清晰"], "warnings": [],
                "findings": [{"category": "factual", "scene_id": "one",
                              "detail": "旁白说面积翻倍，公式给出 1.5 倍"}]}
    studio = _studio(offline_pipeline, reviewer)
    try:
        episode = studio.create("事实缺陷阻断测试")
        with pytest.raises(RuntimeError, match="成片检查未通过"):
            studio.produce(episode["id"])
        assert not list(studio.delivery.rglob("*.mp4")), "未通过的成片不得进入待上传目录"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        decision = json.loads((job / "release-decision.json").read_text(encoding="utf-8"))
        assert decision["decision"] == "blocked"
        assert any(check["check_id"].startswith("review.visual.factual")
                   for check in decision["blocking"])
        assert studio.ledger.get(episode["id"])["status"] != "ready"
    finally:
        studio.close()


def test_axis_reading_matching_generated_ticks_does_not_block(offline_pipeline):
    """The old keyword guard is replaced by generated-tick evidence."""
    scenes = [scene("one", "损失从 0.9 降到 0.3，下降速度先快后慢。",
                    [chart_layer(values=[0.9, 0.7, 0.5, 0.3])]),
              scene("two", "把学习率调小之后，下降曲线会更平滑一些，但最后的位置不变。",
                    [layer("vec", procedural="vectors")]),
              scene("three", "两条曲线最后收敛到同一个位置，只是走过的路径不同。",
                    [layer("proj", procedural="projection")])]
    reviewer = {"passed": False, "issues": [], "strengths": ["叙事清晰"], "warnings": [],
                "findings": [{"category": "visual_mismatch", "scene_id": "one",
                              "detail": "纵轴刻度显示 0.4 与 0.8，两个标签间距看起来不均匀"}]}
    class StageAware(MockProvider):
        """Script review passes; the visual review is the one that reports the ticks."""

        def call(self, role, context, contract, directory, images=None, sanitize=None):
            if role == "reviewer":
                payload = reviewer if context.get("stage") == "visual" else review_payload()
                self.responses = {**self.responses, role: payload}
            return super().call(role, context, contract, directory, images=images, sanitize=sanitize)

    provider = StageAware({"research": research_payload(), "director": film(long_scenes=scenes)})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("刻度读数降级测试")
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        decision = json.loads((job / "release-decision.json").read_text(encoding="utf-8"))
        assert decision["decision"] == "ready"
        assert decision["blocking"] == []
        axis = [check for check in decision["warnings"] if "axis" in check["check_id"]]
        assert axis and axis[0]["evidence"]["kind"] == "generated-tick-labels"
        assert axis[0]["evidence"]["labels"] == ["0.2", "0.4", "0.6", "0.8", "1.0"]
        visual = json.loads((job / "visual-review.json").read_text(encoding="utf-8"))
        assert visual["axis_policy"] == "deterministic"
        assert visual["normalized"]["passed"] is True
        assert visual["raw"]["passed"] is False
    finally:
        studio.close()


from pathlib import Path  # noqa: E402
