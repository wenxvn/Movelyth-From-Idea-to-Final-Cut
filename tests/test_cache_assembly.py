"""S3-02: cache keys, invalidation closure and correct assembly."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from movelyth.agents import MockProvider
from movelyth.cache import (
    DEPENDENTS,
    TRANSITION_POLICY,
    assembly_report,
    changed_scenes,
    invalidated_by,
    scene_key,
    scene_keys,
    verify_assembly,
    verify_cached_file,
)
from movelyth.pipeline import probe_media
from tests.conftest import make_studio
from tests.factories import film, layer, research_payload, review_payload, scene


def timeline(*scenes: dict) -> dict:
    rows = []
    for index, raw in enumerate(scenes):
        rows.append({**raw, "frames": 60, "captions": [{"start": 0.2, "end": 2.0, "text": "字幕"}],
                     "actions_resolved": [], "events_resolved": [], "duration": 2.0})
    return {"scenes": rows, "frames": 60 * len(rows), "seconds": 2.0 * len(rows)}


def base_scene(scene_id="one", **overrides) -> dict:
    return {**scene(scene_id), **overrides}


# ------------------------------------------------------------------- invalidation

def test_the_closure_covers_transitive_dependents():
    assert "check" in invalidated_by(["research"])
    assert invalidated_by(["script"]) == ["check", "render", "sound"]
    assert invalidated_by(["render"]) == ["check"]
    assert invalidated_by(["policy"]) == ["check"]
    assert invalidated_by(["unknown"]) == []


def test_every_stage_in_the_graph_has_a_declared_dependent():
    known = set(DEPENDENTS)
    for dependents in DEPENDENTS.values():
        assert dependents <= known, "依赖图里出现了未声明的阶段"


# ------------------------------------------------------------------- scene keys

def test_a_scene_key_covers_content_and_environment():
    first = scene_key(base_scene(), environment={"fps": 30})
    assert first == scene_key(base_scene(), environment={"fps": 30})
    assert first != scene_key(base_scene(narration="完全不同的旁白内容，用于验证缓存失效。"),
                              environment={"fps": 30})
    assert first != scene_key(base_scene(), environment={"fps": 25})


def test_a_neighbour_change_invalidates_this_scene():
    previous = base_scene("a")
    changed = base_scene("a")
    alone = scene_key(previous, neighbours=(None, None))
    assert alone == scene_key(changed, neighbours=(None, None))
    # The next scene's transition and shared subject are part of this scene's key.
    next_scene = base_scene("b", transition="wipe",
                            layers=[layer("card", subject_id="mean")])
    assert scene_key(changed, neighbours=(None, next_scene)) != alone


def test_changed_scenes_include_the_neighbours_of_a_change():
    keys = scene_keys(timeline(base_scene("a"), base_scene("b"), base_scene("c")))
    previous = dict(keys)
    current = dict(keys)
    current["b"] = "different"
    assert changed_scenes(previous, current) == ["a", "b", "c"]


def test_changed_scenes_is_empty_when_nothing_changed():
    keys = scene_keys(timeline(base_scene("a"), base_scene("b")))
    assert changed_scenes(keys, keys) == []


# ----------------------------------------------------------------- cache files

def test_a_cached_file_is_valid_only_when_its_hash_matches(tmp_path):
    path = tmp_path / "voice.wav"
    path.write_bytes(b"audio")
    from movelyth.util import file_hash

    good = file_hash(path)
    assert verify_cached_file(path, good)["valid"] is True
    path.write_bytes(b"half-writ")   # a truncated or tampered file
    result = verify_cached_file(path, good)
    assert result["valid"] is False and "hash" in result["reason"]
    assert verify_cached_file(tmp_path / "missing", good)["valid"] is False


# --------------------------------------------------------------------- assembly

def test_overlay_transition_policy_keeps_the_frame_sum():
    policy = TRANSITION_POLICY
    assert policy["mode"] == "overlay"
    assert "105" in policy["why"], "策略必须写明重叠会缩短时长"
    data = timeline(base_scene("a"), base_scene("b"))
    report = assembly_report({"frames": 120}, data)
    assert report["passed"] is True and report["total_frames"] == 120


def test_a_composition_that_subtracted_overlap_is_rejected():
    data = timeline(base_scene("a"), base_scene("b"))
    report = assembly_report({"frames": 105}, data)  # TransitionSeries-style overlap
    assert report["passed"] is False
    assert any("不一致" in problem for problem in report["problems"])


def test_assembly_rejects_an_empty_or_broken_timeline():
    assert assembly_report({"frames": 0}, {"scenes": []})["passed"] is False
    broken = {"scenes": [{"id": "a", "frames": 0}]}
    assert assembly_report({"frames": 0}, broken)["passed"] is False


def test_encoded_assembly_checks_fps_duration_audio_and_channels():
    data = timeline(base_scene("a"), base_scene("b"))

    def probe(**overrides):
        base = {"duration": 4.0, "has_audio": True, "width": 1920, "height": 1080,
                "fps": 30.0, "codec": "h264", "channels": 2}
        base.update(overrides)
        return lambda path: base

    assert verify_assembly(Path("x.mp4"), expected_frames=120, fps=30,
                           scenes=data["scenes"], probe=probe())["passed"] is True
    wrong_fps = verify_assembly(Path("x.mp4"), expected_frames=120, fps=30,
                                scenes=data["scenes"], probe=probe(fps=25.0))
    assert any("fps" in problem for problem in wrong_fps["problems"])
    silent = verify_assembly(Path("x.mp4"), expected_frames=120, fps=30,
                             scenes=data["scenes"], probe=probe(has_audio=False))
    assert any("没有音轨" in problem for problem in silent["problems"])
    mono = verify_assembly(Path("x.mp4"), expected_frames=120, fps=30,
                           scenes=data["scenes"], probe=probe(channels=1))
    assert any("双声道" in problem for problem in mono["problems"])
    short = verify_assembly(Path("x.mp4"), expected_frames=120, fps=30,
                            scenes=data["scenes"], probe=probe(duration=3.1))
    assert any("时长" in problem for problem in short["problems"])


def test_black_frames_near_a_join_are_reported():
    data = timeline(base_scene("a"), base_scene("b"))
    result = verify_assembly(Path("x.mp4"), expected_frames=120, fps=30, scenes=data["scenes"],
                             probe=lambda path: {"duration": 4.0, "has_audio": True,
                                                 "fps": 30.0, "channels": 2},
                             samples=lambda offsets: [40.0, 40.0, 2.0, 40.0])
    assert result["passed"] is False
    assert any("黑帧" in problem for problem in result["problems"])


# ------------------------------------------------------------------- pipeline

def test_the_pipeline_records_scene_keys_and_the_transition_policy(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("缓存键记录测试")
        result = studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        keys = json.loads((job / "scene-keys.json").read_text(encoding="utf-8"))
        assert set(keys) == {"long", "short"}
        assert all(len(value) == 64 for value in keys["long"].values())
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["transition_policy"]["mode"] == "overlay"
        assert quality["technical"]["long"]["assembly"]["passed"] is True
        assert quality["technical"]["long"]["assembly_encoded"]["passed"] is True
    finally:
        studio.close()


def test_a_second_run_reports_which_scenes_would_be_rebuilt(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("单镜变更记录测试")
        studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        first = json.loads((job / "scene-keys.json").read_text(encoding="utf-8"))
        # Simulate a changed middle scene: only it and its neighbours are affected.
        keys = dict(first["long"])
        middle = list(keys)[1]
        keys[middle] = "0" * 64
        (job / "scene-keys.json").write_text(json.dumps({**first, "long": keys}), encoding="utf-8")
        (job / "stages" / "sound.json").unlink()
        # Resume as a not-yet-delivered task so the stages actually run again.
        studio.ledger.status(episode["id"], "script")
        studio.produce(episode["id"])
        changes = json.loads((job / "scene-changes.json").read_text(encoding="utf-8"))
        changed = changes["changed"]["long"]["changed"]
        assert middle in changed
        assert len(changed) <= 3, "只有变更镜头与相邻镜头应被重做"
        assert "short" in changes["changed"]
    finally:
        studio.close()


def test_probe_media_reports_stream_shape_of_a_real_file(tmp_path):
    import subprocess

    from movelyth.media import ffmpeg

    video = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=320x180:rate=30:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2",
                    "-shortest", str(video)], check=True)
    measured = probe_media(video)
    assert measured["has_audio"] is True and measured["fps"] == pytest.approx(30.0)
    assert measured["channels"] == 2 and measured["codec"] == "h264"
    assert measured["duration"] == pytest.approx(1.0, abs=0.1)
