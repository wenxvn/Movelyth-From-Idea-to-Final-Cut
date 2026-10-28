"""S1-03: the delivered package is bound to one revision, its audio and its decision.

``manifest_valid`` used to mean "the listed files hash the same".  These tests pin
down the stricter contract: composition, release decision, revision and (when the
workspace is available) the audio stems that were actually muxed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from movelyth.agents import MockProvider
from movelyth.pipeline import (
    COMPOSITION_FILE,
    DECISION_FILE,
    manifest_report,
    manifest_valid,
)
from movelyth.util import fingerprint, read_json
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload


def _produce(root):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(root, provider)
    episode = studio.create("组成清单测试")
    result = studio.produce(episode["id"])
    job = studio.workspace / f"VID-{episode['id']:06d}"
    return studio, episode, Path(result["delivery"]), job


def test_package_carries_composition_and_decision(offline_pipeline):
    studio, episode, delivery, job = _produce(offline_pipeline)
    try:
        composition = read_json(delivery / COMPOSITION_FILE)
        manifest = read_json(delivery / "manifest.json")
        decision = read_json(delivery / DECISION_FILE)
        assert manifest["composition_hash"] == fingerprint(composition)
        assert decision["decision"] == "ready"
        assert composition["episode"] == f"VID-{episode['id']:06d}"
        assert composition["revision"] == episode["revision"]
        assert composition["policy_version"] == decision["policy_version"]
        assert set(composition["cuts"]) == {"long", "short"}
        long_cut = composition["cuts"]["long"]
        assert long_cut["voice"]["path"] == "audio/long/narration.wav"
        assert long_cut["mix"]["path"] == "audio/long/mix.wav"
        assert long_cut["captions_hash"] and long_cut["timeline_hash"]
        # Delivered artefacts are registered by hash under their package names.
        assert any(name.endswith("横版.mp4") for name in composition["delivered"])
        # No developer absolute path leaks into the package.
        text = (delivery / COMPOSITION_FILE).read_text(encoding="utf-8")
        assert str(offline_pipeline) not in text and "\\\\" not in text
        assert manifest_report(delivery, job=job)["valid"] is True
    finally:
        studio.close()


def test_modified_video_invalidates_the_delivery(offline_pipeline):
    """M12: a hand-edited or half-written video must not stay 'ready'."""
    studio, episode, delivery, job = _produce(offline_pipeline)
    try:
        video = next(delivery.glob("*横版.mp4"))
        video.write_bytes(b"tampered")
        report = manifest_report(delivery, job=job)
        assert report["valid"] is False
        assert any("已改动" in reason for reason in report["reasons"])
        with pytest.raises(RuntimeError, match="已交付文件缺失或发生变化"):
            studio.produce(episode["id"])
        assert video.read_bytes() == b"tampered", "不得自动覆盖用户手上的交付文件"
    finally:
        studio.close()


def test_a_decision_from_another_revision_is_rejected(offline_pipeline):
    studio, _episode, delivery, job = _produce(offline_pipeline)
    try:
        decision_path = delivery / DECISION_FILE
        decision = read_json(decision_path)
        decision["inputs"]["revision"] = decision["inputs"]["revision"] + 1
        decision_path.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")
        report = manifest_report(delivery, job=job)
        assert report["valid"] is False
        assert any("其他 revision" in reason for reason in report["reasons"])
    finally:
        studio.close()


def test_a_missing_decision_blocks_reuse(offline_pipeline):
    studio, _episode, delivery, job = _produce(offline_pipeline)
    try:
        (delivery / DECISION_FILE).unlink()
        report = manifest_report(delivery, job=job)
        assert report["valid"] is False
        assert any(DECISION_FILE in reason for reason in report["reasons"])
    finally:
        studio.close()


def test_regenerated_audio_invalidates_the_delivery(offline_pipeline):
    """New audio that never entered the final video must not keep the package ready."""
    studio, _episode, delivery, job = _produce(offline_pipeline)
    try:
        (job / "audio" / "long" / "mix.wav").write_bytes(b"a different mix")
        report = manifest_report(delivery, job=job)
        assert report["valid"] is False
        assert any("重新生成" in reason for reason in report["reasons"])
    finally:
        studio.close()


def test_interrupted_staging_is_not_reused(offline_pipeline):
    studio = make_studio(offline_pipeline, MockProvider({
        "research": research_payload(), "director": film(), "reviewer": review_payload()}))
    try:
        episode = studio.create("中断暂存测试")
        name = f"VID-{episode['id']:06d}_中断暂存测试"
        staging = studio.delivery / ".staging" / name / "r001"
        staging.mkdir(parents=True)
        (staging / "遗留文件.txt").write_text("half-written", encoding="utf-8")
        result = studio.produce(episode["id"])
        delivery = Path(result["delivery"])
        assert not (delivery / "遗留文件.txt").exists()
        manifest = read_json(delivery / "manifest.json")
        assert "遗留文件.txt" not in manifest["files"]
        assert manifest_valid(delivery)
        assert not staging.exists(), "完成后不得留下暂存目录"
    finally:
        studio.close()
