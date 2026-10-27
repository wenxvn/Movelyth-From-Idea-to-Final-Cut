import csv
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from movelyth.ledger import BusyError, Ledger
from movelyth.media import captions, image_layers, soundtrack, speech_plan
from movelyth.models import Film, Scene, strict_schema
from movelyth.pipeline import Studio, intent_key, manifest_valid, safe_title
from movelyth.quality import srt
from movelyth.util import atomic_json, file_hash


@pytest.fixture
def studio(tmp_path):
    config = Path(__file__).parents[1] / "movelyth.toml"
    (tmp_path / "movelyth.toml").write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    value = Studio(tmp_path)
    yield value
    value.close()


def test_duplicate_intent_and_explicit_new(studio):
    first = studio.create("矩阵，如何改变世界？")
    duplicate = studio.create("矩阵 如何改变世界")
    assert first["id"] == duplicate["id"]
    second = studio.create("矩阵，如何改变世界？", new=True)
    assert second["id"] > first["id"]


def test_concurrent_id_reservation(tmp_path):
    path = tmp_path / "ledger.sqlite"
    Ledger(path).close()

    def reserve(_):
        store = Ledger(path)
        try:
            return store.reserve("一个标题", "same-intent")["id"]
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(reserve, range(8)))
    assert len(set(ids)) == 1


def test_live_lock_excludes_second_worker_and_releases(studio):
    episode = studio.create("测试互斥任务")
    second = Ledger(studio.workspace / "studio.sqlite")
    try:
        with studio.ledger.claim(episode["id"]):
            with pytest.raises(BusyError):
                with second.claim(episode["id"]):
                    pytest.fail("运行中的任务不得被重复执行")
        with second.claim(episode["id"]):
            assert second.get(episode["id"])["pid"] == os.getpid()
    finally:
        second.close()


def test_failed_stage_and_corrupt_artifact_are_recoverable(studio):
    episode = studio.create("断点恢复验证")
    out = studio.workspace / "artifact.txt"
    calls = []

    def action():
        calls.append(1)
        out.write_text("fresh", encoding="utf-8")
        return {"ok": True}, [out]

    def fail():
        raise RuntimeError("injected interruption")

    with pytest.raises(RuntimeError):
        studio.stage(episode, "test", {}, fail)
    studio.stage(episode, "test", {}, action)
    studio.stage(episode, "test", {}, action)
    assert len(calls) == 1
    out.write_text("corrupted", encoding="utf-8")
    studio.stage(episode, "test", {}, action)
    assert len(calls) == 2
    marker = studio.workspace / f"VID-{episode['id']:06d}/stages/test.json"
    marker.write_text("broken", encoding="utf-8")
    studio.stage(episode, "test", {}, action)
    assert len(calls) == 3
    states = [r[0] for r in studio.ledger.db.execute("SELECT state FROM events ORDER BY id")]
    assert "failed" in states and states[-1] == "passed"
    assert studio.ledger.context()["failures"][0]["detail"]["message"] == "injected interruption"


def test_approved_plan_survives_renderer_repair_but_not_artifact_tampering(studio):
    episode = studio.create("固定已审故事")
    output = studio.workspace / "approved.json"
    calls = []

    def action():
        calls.append(1)
        atomic_json(output, {"revision": len(calls)})
        return {"revision": len(calls)}, [output]

    studio.stage(episode, "script", {"prompt": "original"}, action)
    value = studio.stage(episode, "script", {"prompt": "new-visual-review"}, action, freeze_approved_plan=True)
    assert value["revision"] == 1 and len(calls) == 1
    assert studio.ledger.db.execute("SELECT COUNT(*) FROM events WHERE state='frozen-plan-reused'").fetchone()[0] == 1
    output.write_text("changed", encoding="utf-8")
    value = studio.stage(episode, "script", {"prompt": "new-visual-review"}, action, freeze_approved_plan=True)
    assert value["revision"] == 2


def test_delivery_hash_and_path_traversal(tmp_path):
    artifact = tmp_path / "video.mp4"
    artifact.write_bytes(b"test content")
    atomic_json(tmp_path / "manifest.json", {"status": "ready", "files": {artifact.name: file_hash(artifact)}})
    assert manifest_valid(tmp_path)
    artifact.write_bytes(b"changed")
    assert not manifest_valid(tmp_path)
    atomic_json(tmp_path / "manifest.json", {"status": "ready", "files": {"../outside": "abc"}})
    assert not manifest_valid(tmp_path)
    atomic_json(tmp_path / "manifest.json", {"status": "ready", "files": {}})
    assert not manifest_valid(tmp_path)


def test_invalid_model_content_is_rejected():
    base = {"id": "scene1", "heading": "标题", "narration": "这是一段具有具体意义的旁白内容，用于验证。",
            "visual": "matrix", "labels": ["面积"], "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0}
    with pytest.raises(ValidationError):
        Scene.model_validate({**base, "shell": "arbitrary command"})
    with pytest.raises(ValidationError):
        Scene.model_validate({**base, "matrix": [float("nan"), 0, 0, 1]})
    with pytest.raises(ValidationError):
        Scene.model_validate({**base, "visual": "execute_python"})
    assert strict_schema(Film)["additionalProperties"] is False


def test_captions_use_real_word_offsets_and_srt_bounds():
    text = "看见变化，理解结构。"
    words = [{"start": 0.2, "end": 0.9, "text": "看见变化"},
             {"start": 1.2, "end": 2.0, "text": "理解结构"}]
    pages, mode = captions(text, words, 2.3, 8)
    assert mode == "tts-word-boundaries"
    assert pages[0]["start"] == 0.2
    assert all(p["start"] < p["end"] <= 2.3 for p in pages)
    assert all(a["end"] <= b["start"] for a, b in zip(pages, pages[1:]))
    cut = {"scenes": [{"frames": 90, "captions": pages}, {"frames": 90, "captions": pages}]}
    result = srt(cut, 30)
    assert "00:00:03,200" in result


def test_pronunciation_replacement_changes_the_voice_but_not_the_caption():
    narration = "这里用熵来度量不确定性。"
    spoken, origin = speech_plan(narration, {"熵": "商"})
    assert spoken == "这里用商来度量不确定性。"
    assert len(origin) == len(spoken)
    words = [{"start": 0.1, "end": 0.5, "text": "这里用商来度量"},
             {"start": 0.6, "end": 1.2, "text": "不确定性。"}]
    pages, mode = captions(narration, words, 1.6, 12, spoken=spoken, origin=origin)
    shown = "".join(page["text"] for page in pages)
    assert mode == "tts-word-boundaries"
    assert "熵" in shown and "商" not in shown
    assert pages[0]["start"] == 0.1


def test_replacement_that_changes_length_still_times_the_caption():
    narration = "用 det 表示行列式。"
    spoken, origin = speech_plan(narration, {"det": "determinant"})
    assert spoken == "用 determinant 表示行列式。"
    assert len(origin) == len(spoken)
    words = [{"start": 0.1, "end": 0.8, "text": "用 determinant 表示"},
             {"start": 0.9, "end": 1.4, "text": "行列式。"}]
    pages, mode = captions(narration, words, 1.8, 12, spoken=spoken, origin=origin)
    assert mode == "tts-word-boundaries"
    assert "det" in "".join(page["text"] for page in pages)


def test_captions_never_go_backwards_when_two_pages_share_one_word():
    """A page boundary inside a TTS word used to give both pages the same start.

    The timeline check then rejected the whole cut with "字幕交叠" — a real failure
    on a DeepSeek-generated script.
    """
    text = "所以结果的符号取正：负一乘负一，得正一。"
    words = [{"start": 0.1, "end": 0.5, "text": "所以"},
             {"start": 0.5, "end": 1.4, "text": "结果的符号取正"},
             {"start": 1.4, "end": 2.0, "text": "负一乘负一"},
             {"start": 2.0, "end": 2.4, "text": "得正一"}]
    pages, _mode = captions(text, words, 2.5, 8)
    assert pages
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(pages, pages[1:]))


def test_voice_cache_rejects_boundaries_longer_than_the_audio():
    """One cached take had 17.4 s of timings on 14.6 s of audio and clipped captions."""
    from movelyth.media import SAMPLE_RATE, timing_matches_audio

    audio = np.zeros(int(SAMPLE_RATE * 2.0), dtype=np.float32)
    inside = [{"start": 0.1, "end": 1.9, "text": "好"}]
    beyond = [{"start": 0.1, "end": 2.9, "text": "好"}]
    assert timing_matches_audio(audio, inside) is True
    assert timing_matches_audio(audio, beyond) is False
    assert timing_matches_audio(audio, []) is True


def test_missing_feedback_remains_unknown(studio):
    episode = studio.create("反馈测试")
    studio.ledger.add_feedback(episode["id"], "bilibili", "https://www.bilibili.com/video/example", {})
    assert studio.ledger.context()["feedback"][0]["metrics"] == {}


def test_proposed_next_ideas_do_not_become_completed_with_origin_film(studio):
    episode = studio.create("本期实际制作的题目")
    studio.ledger.add_ideas(["下期候选之一", "下期候选之二"], episode["id"])
    studio.ledger.status(episode["id"], "ready")
    states = {v["title"]: v["state"] for v in studio.ledger.context()["ideas"]}
    assert states["本期实际制作的题目"] == "completed"
    assert states["下期候选之一"] == states["下期候选之二"] == "backlog"
    next_episode = studio.create("下期候选之一")
    studio.ledger.status(next_episode["id"], "ready")
    states = {v["title"]: v["state"] for v in studio.ledger.context()["ideas"]}
    assert states["下期候选之一"] == "completed" and states["下期候选之二"] == "backlog"


def test_index_separates_production_and_publication(studio):
    episode = studio.create("发布状态清单")
    url = "https://www.bilibili.com/video/example"
    studio.ledger.add_feedback(episode["id"], "bilibili", url, {})
    studio.export_index()
    with (studio.delivery / "交付清单.csv").open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["B站发布链接"] == url and rows[0]["抖音发布链接"] == ""
    assert rows[0]["制作状态"] == "planned"


def test_asset_feedback_keeps_observations_separate_from_popularity(studio):
    episode = studio.create("素材记录测试")
    scenes = [{"id": "one", "visual": "matrix", "matrix": [1, 1, 0, 1], "color": "cyan"},
              {"id": "two", "visual": "matrix", "matrix": [1, 1, 0, 1], "color": "cyan"}]
    studio.ledger.record_assets(episode["id"], "long", scenes, "source-version")
    assets = studio.ledger.asset_observations()
    assert len(assets) == 1 and len(assets[0]["usage"]) == 2
    assert assets[0]["popularity"] == "unknown"
    studio.ledger.add_feedback(episode["id"], "bilibili", "https://www.bilibili.com/video/example", {"views": 42})
    assets = studio.ledger.asset_observations()
    assert len(assets[0]["feedback_observations"]) == 1
    assert assets[0]["feedback_observations"][0]["metrics"] == {"views": 42}
    assert assets[0]["popularity"] == "associated-video-data-only"


def test_original_svd_error_decreases(tmp_path):
    names, paths, report = image_layers(tmp_path)
    assert len(names) == 4 and all(p.is_file() for p in paths)
    errors = [report[str(k)]["mse"] for k in [1, 4, 12, 32]]
    assert all(a >= b for a, b in zip(errors, errors[1:]))
    assert errors[-1] < errors[0] / 10


def test_soundtrack_has_sound_without_clipping():
    track = soundtrack(np.zeros(24000 * 4, dtype=np.float32), [0, 2])
    assert track.shape == (96000, 2)
    assert np.max(np.abs(track)) < 0.98
    assert np.sqrt(np.mean(track ** 2)) > 0.005


def test_title_is_data_not_a_path():
    assert "/" not in safe_title('../../test|title')
    assert intent_key("ＡＢＣ，矩阵！") == intent_key("abc 矩阵")
