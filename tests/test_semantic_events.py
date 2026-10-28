"""S1-06: semantic events, object identity, a single clock and a versioned contract."""
from __future__ import annotations

import pytest

from movelyth.clock import frame_at, frames_to_samples, scene_spans, seconds_to_frames
from movelyth.models import SCHEMA_VERSION, Layer, Scene, migrate_cut, migrate_scene
from movelyth.scenedsl import normalize_scene, resolve_events
from tests.factories import layer as layer_payload
from tests.factories import scene as scene_payload


def scene_model(**overrides) -> Scene:
    return Scene.model_validate(scene_payload(**overrides))


def boundaries_for(narration: str, *, words: int = 6) -> list[dict]:
    """Evenly spaced word boundaries over the narration, like a real TTS result."""
    step = len(narration) / words
    return [{"text": narration[int(i * step):int((i + 1) * step)],
             "start": i * 0.4, "end": (i + 1) * 0.4} for i in range(words)]


# ------------------------------------------------------------------ the clock

def test_scene_spans_are_contiguous_and_never_drift():
    spans = scene_spans([37, 45, 52, 40, 61], fps=30, sample_rate=24000)
    for previous, current in zip(spans, spans[1:], strict=False):
        assert previous["end_sample"] == current["start_sample"]
        assert previous["end_seconds"] == pytest.approx(current["start_seconds"])
    assert spans[-1]["end_sample"] == sum(span["samples"] for span in spans)


def test_frame_and_sample_rounding_is_defined_once():
    assert seconds_to_frames(4.0000001, 30) == 120
    assert seconds_to_frames(4.02, 30) == 121  # a scene never cuts its own audio
    assert frames_to_samples(30, 30, 24000) == 24000
    assert frame_at(1.999, 30) == 59
    assert frame_at(-3, 30) == 0


# ------------------------------------------------------------ semantic events

def test_a_repeated_phrase_binds_to_the_requested_occurrence():
    narration = "3 与 3 的平均还是 3，所以中位数不动。"
    boundaries = boundaries_for(narration)
    scene = scene_model(narration=narration, events=[
        {"id": "first", "kind": "reveal", "anchor": {"kind": "narration", "text": "3", "occurrence": 1}},
        {"id": "second", "kind": "reveal", "anchor": {"kind": "narration", "text": "3", "occurrence": 2}},
    ])
    resolved = resolve_events(scene, 4.0, boundaries)
    assert resolved[0]["at"] < resolved[1]["at"]
    assert resolved[0]["timing"] == "tts-word-boundaries"


def test_a_missing_occurrence_is_an_error_not_the_first_match():
    narration = "这句话里只有一个关键词，后面都是解释。"
    scene = scene_model(narration=narration, events=[
        {"id": "late", "kind": "reveal",
         "anchor": {"kind": "narration", "text": "关键词", "occurrence": 3}}])
    with pytest.raises(ValueError, match="第 3 次"):
        resolve_events(scene, 4.0, boundaries_for(narration))


def test_character_range_anchor_is_supported():
    narration = "先看起点，再看终点，最后比较两者。"
    scene = scene_model(narration=narration, events=[
        {"id": "end", "kind": "conclude",
         "anchor": {"kind": "narration", "char_start": narration.index("最后")}}])
    resolved = resolve_events(scene, 4.0, boundaries_for(narration))
    assert 0 <= resolved[0]["at"] <= 4.0


def test_event_target_must_exist():
    scene = scene_model(events=[{"id": "x", "kind": "reveal", "target": "ghost",
                                "anchor": {"kind": "start"}}])
    with pytest.raises(ValueError, match="不存在的目标"):
        resolve_events(scene, 4.0, [])


def test_an_event_outside_the_scene_is_rejected():
    scene = scene_model(events=[{"id": "late", "kind": "reveal",
                                "anchor": {"kind": "end"}, "offset_seconds": 3}])
    with pytest.raises(ValueError, match="落在镜头外"):
        resolve_events(scene, 4.0, [])


def test_reversed_events_for_the_same_target_are_rejected():
    scene = scene_model(events=[
        {"id": "after", "kind": "reveal", "target": "visual",
         "anchor": {"kind": "fraction", "fraction": 0.8}},
        {"id": "before", "kind": "reveal", "target": "visual",
         "anchor": {"kind": "fraction", "fraction": 0.2}},
    ])
    with pytest.raises(ValueError, match="倒序"):
        resolve_events(scene, 4.0, [])


def test_duplicate_event_ids_are_rejected_by_the_model():
    with pytest.raises(ValueError, match="不能重复"):
        scene_model(events=[{"id": "same", "kind": "reveal", "anchor": {"kind": "start"}},
                            {"id": "same", "kind": "pause", "anchor": {"kind": "end"}}])


def test_normalized_scene_carries_resolved_events_and_timing():
    narration = "先把数值放到数轴上，再移动那一个点。"
    scene = scene_model(narration=narration, events=[
        {"id": "move", "kind": "transform", "target": "visual",
         "anchor": {"kind": "narration", "text": "移动"}}])
    normalized = normalize_scene(scene, duration=4.0, boundaries=boundaries_for(narration))
    assert normalized["events_resolved"][0]["id"] == "move"
    assert normalized["events_resolved"][0]["timing"] == "tts-word-boundaries"
    assert 0 <= normalized["events_resolved"][0]["fraction"] <= 1


# ----------------------------------------------------------------- identity

def test_subject_identity_is_separate_from_the_layer_instance():
    first = Layer.model_validate({**layer_payload("card"), "subject_id": "mean",
                                 "state_before": "均值 4", "state_after": "均值 10"})
    second = Layer.model_validate({**layer_payload("point"), "subject_id": "mean"})
    assert first.id != second.id and first.subject_id == second.subject_id


def test_state_without_a_subject_is_rejected():
    with pytest.raises(ValueError, match="subject_id"):
        Layer.model_validate({**layer_payload("card"), "state_before": "均值 4"})


def test_claim_ids_are_bounded_references():
    with pytest.raises(ValueError, match="claim_ids"):
        scene_model(claim_ids=["claim-1"])


# ----------------------------------------------------------------- migration

def test_a_v1_scene_migrates_without_inventing_anything():
    legacy = {key: value for key, value in scene_payload().items() if key != "schema_version"}
    legacy["schema_version"] = 1
    migrated = migrate_scene(legacy)
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert "events" not in migrated, "迁移只补版本号，不编造事件"
    # A bare v1 scene stays v1 (it is still a valid v1 scene); the cut/film migration
    # is what upgrades a script, and it only adds the version number.
    validated = Scene.model_validate(legacy)
    assert validated.schema_version == 1
    assert validated.events == [] and validated.claim_ids == []


def test_v2_fields_under_a_v1_version_are_refused():
    legacy = {**scene_payload(), "schema_version": 1,
              "events": [{"id": "x", "kind": "reveal", "anchor": {"kind": "start"}}]}
    with pytest.raises(ValueError, match="v2 字段"):
        migrate_scene(legacy)


def test_a_future_schema_version_is_refused():
    with pytest.raises(ValueError, match="高于当前实现"):
        migrate_scene({**scene_payload(), "schema_version": SCHEMA_VERSION + 1})


def test_cut_migration_applies_to_every_scene():
    cut = {"title": "测试横版", "description": "一段用于测试的横版发布说明。",
           "tags": ["测试"], "title_candidates": ["候选"], "cover_caption": "",
           "style": "tech", "schema_version": 1,
           "scenes": [{**scene_payload("one"), "schema_version": 1},
                      {**scene_payload("two"), "schema_version": 1}]}
    migrated = migrate_cut(cut)
    assert {scene["schema_version"] for scene in migrated["scenes"]} == {SCHEMA_VERSION}
