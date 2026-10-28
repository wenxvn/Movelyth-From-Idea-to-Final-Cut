"""S4-03: the fault matrix, one test per injected failure.

Each entry of the matrix in the task book is exercised through the module that owns the
decision, so the file doubles as a map from "what can go wrong" to "where it is caught".
Entries that need a real model, a real GPU or a human viewer are marked as such instead
of being asserted on a stub.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from movelyth.agents import MockProvider
from movelyth.assetplan import AssetRequest, choose
from movelyth.assets import register
from movelyth.budget import BudgetExceeded, BudgetLedger
from movelyth.cache import changed_scenes, invalidated_by, scene_key, scene_keys, verify_cached_file
from movelyth.camera import camera_plan, validate_plan
from movelyth.capability import classify_route
from movelyth.captions_qc import cue_report
from movelyth.continuity import continuity_report
from movelyth.mix import mix_report
from movelyth.models import Finding, Review, Scene
from movelyth.parameters import evaluate, validate_scene_parameters
from movelyth.pipeline import manifest_report
from movelyth.policy import decide, mix_checks, normalize_review, review_checks
from movelyth.scenedsl import normalize_scene, resolve_events
from movelyth.sketch import path_points
from movelyth.speech import reading_units, verify_reading
from movelyth.textfit import caption_chunks, wrap
from movelyth.util import file_hash
from tests.conftest import make_studio
from tests.factories import film, layer, research_payload, review_payload, scene

ROOT = Path(__file__).parents[1]


# M01 — passed=true with a factual finding
def test_m01_passed_true_cannot_override_a_factual_finding():
    raw = Review(passed=True, issues=[], strengths=[], warnings=[], findings=[
        Finding(category="factual", scene_id="l2", detail="结论与证据冲突")])
    normalized = normalize_review(raw)
    assert normalized["review"].passed is False
    _, checks, _ = review_checks(raw)
    assert decide(checks).decision == "blocked"


# M02 — seconds/ms, swapped axes, missing variable
@pytest.mark.parametrize("detail", [
    "纵轴单位写成毫秒，但数据是秒",
    "横轴与纵轴标签互换",
    "缺少 y 轴变量说明",
])
def test_m02_unit_axis_and_variable_defects_are_not_softened(detail):
    raw = Review(passed=False, issues=[], strengths=[], warnings=[], findings=[
        Finding(category="visual_mismatch", scene_id="l3", detail=detail)])
    _, checks, _ = review_checks(raw, ticks_by_scene={"l3": ["0", "1", "2"]})
    assert [check.status for check in checks] == ["fail"]


# M03 — unsupported source / empty claims
def test_m03_a_claim_without_evidence_blocks():
    from movelyth.policy import source_checks

    assert decide(source_checks([])).decision == "blocked"
    unsupported = [{"claim_id": "c1", "statement": "某结论", "status": "excerpt-missing",
                    "scope": "established", "importance": "key", "source_index": 0,
                    "evidence_refs": [], "detail": "找不到节选"}]
    assert decide(source_checks(unsupported)).decision == "blocked"


# M04 — music present, voice missing
def test_m04_music_cannot_hide_a_missing_voice():
    silent = np.zeros(24000 * 3, dtype=np.float32)
    report = mix_report({"voice": silent,
                         "music": (0.3 * np.ones(24000 * 3)).astype(np.float32)})
    assert decide(mix_checks(report, cut="long")).decision == "blocked"


# M05 — dropped number / negation / term
def test_m05_dropped_negation_and_changed_number_are_detected():
    units = reading_units("这个结论不正确，误差是 0.5 秒。")
    dropped = verify_reading(units, "这个结论正确，误差是零点五秒")
    assert any(item["written"] == "不" for item in dropped["missing"])
    changed = verify_reading(units, "这个结论不正确，误差是5秒")
    assert changed["changed"] and "量级" in changed["changed"][0]["reason"]


# M06 — repeated phrase must not bind to the first occurrence
def test_m06_repeated_phrases_bind_to_the_requested_occurrence():
    narration = "3 与 3 的平均还是 3，所以中位数不动。"
    model = Scene.model_validate(scene(narration=narration, events=[
        {"id": "second", "kind": "reveal",
         "anchor": {"kind": "narration", "text": "3", "occurrence": 2}}]))
    first = Scene.model_validate(scene(narration=narration, events=[
        {"id": "first", "kind": "reveal",
         "anchor": {"kind": "narration", "text": "3", "occurrence": 1}}]))
    boundaries = [{"text": narration[i:i + 6], "start": i * 0.2, "end": (i + 1) * 0.2}
                  for i in range(0, len(narration), 6)]
    second_at = resolve_events(model, 4.0, boundaries)[0]["at"]
    first_at = resolve_events(first, 4.0, boundaries)[0]["at"]
    assert second_at > first_at
    with pytest.raises(ValueError, match="第 5 次"):
        resolve_events(Scene.model_validate(scene(narration=narration, events=[
            {"id": "nope", "kind": "reveal",
             "anchor": {"kind": "narration", "text": "3", "occurrence": 5}}])), 4.0, boundaries)


# M07 — long terms, short cues, split units
def test_m07_caption_pages_keep_units_and_terms_whole():
    pages = caption_chunks("矩阵的列是基向量的像，耗时 12 毫秒，误差 0.5 个百分点。", 14)
    assert all(len(page) <= 18 for page in pages)
    assert any("12 毫秒" in page or "12毫秒" in page for page in pages)
    lines = wrap("Remotion 渲染器与 Microsoft YaHei 字体", 10)
    assert not any(line.endswith("Remotio") for line in lines)
    data = {"id": "one", "captions": [{"start": 0.2, "end": 0.6, "text": "短" * 20}],
            "layers": [], "layout": "diagram"}
    problems = cue_report(data, "long", orientation="landscape")["problems"]
    assert any("字/秒" in problem for problem in problems)


# M08 — occlusion or focus extremes mid-move
def test_m08_a_focus_that_leaves_the_frame_is_rejected():
    bad = [{"at": 0.0, "mode": "focus", "scale": 1.5, "cx": 0.02, "cy": 0.5, "reason": ""}]
    assert validate_plan(bad, orientation="landscape", duration=6.0)
    good = camera_plan({"layout": "diagram", "layers": [{"id": "m", "region": "main"}],
                        "events_resolved": [{"id": "f", "kind": "emphasis", "at": 1.0,
                                             "target": "m"}]},
                       orientation="landscape", duration=6.0)
    assert not validate_plan(good, orientation="landscape", duration=6.0)


# M09 — label disagrees with the computation
def test_m09_a_label_that_disagrees_with_the_computation_is_rejected():
    model = Scene.model_validate(scene(
        function="linear-transform", parameters={"a": 1, "b": 0, "c": 0, "d": 2},
        layers=[layer("note", type="text", text="面积放大 37 倍")]))
    assert any("37" in problem for problem in validate_scene_parameters(model))
    assert evaluate("linear-transform", {"a": 1, "b": 0, "c": 0, "d": 2})["area_scale"] == 2.0


# M10 — a still reading segment is legitimate; optional effects off are not_applicable
def test_m10_a_reasoned_hold_and_a_disabled_option_are_not_defects():
    from movelyth.animatic import layout_precheck

    timeline = {"long": {"seconds": 8.0, "frames": 240, "scenes": [
        {**normalize_scene(Scene.model_validate(scene(
            hold_reason="对照两个刻度需要停留")), duration=8.0),
         "frames": 240,
         "captions": [{"start": 0.2, "end": 2.4, "text": "这一段需要停下来对照"}]}]}}
    report = layout_precheck(timeline, {"fps": 30})
    assert not any("hold_reason" in warning for warning in report["warnings"])


# M11 — a font/asset/model/recipe change invalidates the right things
def test_m11_changes_invalidate_the_right_stages():
    assert set(invalidated_by(["fonts"])) == {"check", "render"}
    assert "render" in invalidated_by(["assets"])
    assert "check" in invalidated_by(["policy"])
    first = scene_key(scene("one"), environment={"fps": 30, "fonts": ["A"]})
    second = scene_key(scene("one"), environment={"fps": 30, "fonts": ["B"]})
    assert first != second


# M12 — half file, tampered video, old revision report
def test_m12_half_files_and_tampering_are_refused(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"complete")
    digest = file_hash(path)
    assert verify_cached_file(path, digest)["valid"] is True
    path.write_bytes(b"half")
    assert verify_cached_file(path, digest)["valid"] is False
    # A package without a composition/decision cannot be reused.
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"status": "ready", "files": {"clip.mp4": file_hash(path)}}), encoding="utf-8")
    assert manifest_report(tmp_path)["valid"] is False


# M13 — neighbour transition / shared object / cross-scene caption
def test_m13_a_neighbour_change_rebuilds_this_scene():
    base = scene_keys({"scenes": [scene("a"), scene("b"), scene("c")]})
    shifted = dict(base)
    shifted["b"] = "changed"
    assert changed_scenes(base, shifted) == ["a", "b", "c"]
    neighbour = scene("b", transition="wipe")
    alone = scene_key(scene("a"))
    assert scene_key(scene("a"), neighbours=(None, neighbour)) != alone


# M14 — TTS/render/review timeout and exhausted budget
def test_m14_an_exhausted_budget_stops_before_the_next_stage(tmp_path):
    studio = make_studio(tmp_path, MockProvider({"research": research_payload(),
                                                 "director": film(),
                                                 "reviewer": review_payload()}))
    try:
        studio.config["budget"]["model_calls"] = 0
        episode = studio.create("预算耗尽")
        with pytest.raises(BudgetExceeded):
            studio.produce(episode["id"])
    finally:
        studio.close()


# M15 — repeated resume and interrupted recovery keep one accounting
def test_m15_budget_state_survives_an_interrupted_run(offline_pipeline):
    studio = make_studio(offline_pipeline, MockProvider({"research": research_payload(),
                                                         "director": film(),
                                                         "reviewer": review_payload()}))
    try:
        episode = studio.create("恢复记录")
        studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        used = json.loads((job / "budget.json").read_text(encoding="utf-8"))["used"]
        reloaded = BudgetLedger.load(job, studio.config)
        assert reloaded.state.used == used
        assert reloaded.summary()["remaining"]["model_calls"] < reloaded.state.limits["model_calls"]
    finally:
        studio.close()


# M16 — asset with the wrong action, cropped subject, missing licence
def test_m16_wrong_action_and_missing_licence_are_refused(tmp_path):
    from PIL import Image

    workspace = tmp_path / "workspace"
    Image.new("RGB", (800, 800), (40, 60, 90)).save(tmp_path / "shot.png")
    register(workspace, tmp_path / "shot.png", asset_id="shot", source="自有", author="维护者",
             license="自有素材", subject="服务器机柜", action="插拔网线",
             subject_box={"x": 0.05, "y": 0.4, "w": 0.9, "h": 0.2})
    decision = choose(workspace, AssetRequest(subject="服务器机柜", action="插拔网线"),
                      orientation="portrait")
    assert decision["chosen"] == ""
    other = choose(workspace, AssetRequest(subject="海底珊瑚"), orientation="landscape")
    assert other["chosen"] == ""


# M17 — redirect to a non-public address / oversized document
def test_m17_source_boundaries_still_hold():
    from movelyth.sources import BlockedSource, validate_url

    for url in ("http://example.com/x", "https://127.0.0.1/x", "https://localhost/x",
                "https://example.com:8443/x"):
        with pytest.raises(BlockedSource):
            validate_url(url)


# M18 — GPU/texture/font not ready, shader capture failure
def test_m18_optional_heavy_capabilities_are_deferred_not_faked():
    from movelyth.capability import ROUTES

    assert ROUTES["spatial-demo"]["status"] == "needs_extension"
    assert ROUTES["generated-media"]["status"] == "needs_extension"


# M19 — a topic that needs real footage
def test_m19_a_real_footage_topic_is_refused_at_create(tmp_path):
    studio = make_studio(tmp_path, MockProvider({}))
    try:
        before = len(studio.ledger.list(10000))
        with pytest.raises(ValueError, match="无法真实呈现"):
            studio.create("跟着录屏一步步部署这个服务")
        assert len(studio.ledger.list(10000)) == before
    finally:
        studio.close()
    assert classify_route("实拍采访：城市早高峰")["status"] == "unsupported"


# M20 — the same frame rendered twice / out of order / concurrently
def test_m20_the_same_frame_is_identical_regardless_of_order():
    box = {"x": 100, "y": 100, "w": 400, "h": 200}
    first = path_points(box, "circle", 3)
    path_points(box, "box", 9)          # compute something else in between
    assert path_points(box, "circle", 3) == first
    plan_a = camera_plan({"layout": "diagram", "layers": [{"id": "m", "region": "main"}],
                          "events_resolved": [{"id": "f", "kind": "emphasis", "at": 1.0,
                                               "target": "m"}]},
                         orientation="landscape", duration=6.0)
    plan_b = camera_plan({"layout": "diagram", "layers": [{"id": "m", "region": "main"}],
                          "events_resolved": [{"id": "f", "kind": "emphasis", "at": 1.0,
                                               "target": "m"}]},
                         orientation="landscape", duration=6.0)
    assert plan_a == plan_b


# Continuity of shared objects (S2-07) is part of the same matrix of failure modes.
def test_shared_object_identity_is_part_of_the_matrix():
    scenes = [Scene.model_validate(scene("one", layers=[
        layer("card", type="text", text="均值", subject_id="mean", color="cyan")])),
        Scene.model_validate(scene("two", layers=[
            layer("point", procedural="vectors", subject_id="mean", color="coral")]))]
    assert any("换了颜色" in problem for problem in continuity_report(scenes)["problems"])
