import json
from pathlib import Path
from subprocess import CompletedProcess

import numpy as np
import pytest

from movelyth.agents import MockProvider
from movelyth.ledger import Ledger
from movelyth.media import write_wav
from movelyth.models import Film
from movelyth.pipeline import Studio, manifest_valid, normalize_brief
from tests.factories import film, layer, research_payload, review_payload


def make_studio(tmp_path, provider=None) -> Studio:
    config = Path(__file__).parents[1] / "movelyth.toml"
    text = config.read_text(encoding="utf-8")
    text = text.replace("long_seconds = 180", "long_seconds = 20").replace("short_seconds = 60", "short_seconds = 10")
    text = text.replace("long_min_seconds = 120", "long_min_seconds = 10").replace("long_max_seconds = 300", "long_max_seconds = 40")
    text = text.replace("short_min_seconds = 45", "short_min_seconds = 5").replace("short_max_seconds = 90", "short_max_seconds = 20")
    (tmp_path / "movelyth.toml").write_text(text, encoding="utf-8")
    return Studio(tmp_path, provider=provider)


def test_title_only_and_brief_have_separate_intents(tmp_path):
    studio = make_studio(tmp_path)
    try:
        first = studio.create("矩阵为什么能让空间旋转？")
        same = studio.create("矩阵为什么能让空间旋转")
        assert same["id"] == first["id"] and same["brief"] is None
        briefed = studio.create("矩阵为什么能让空间旋转？", brief="面向高中生，语气轻松，强调面积变化")
        assert briefed["id"] != first["id"] and briefed["brief"].startswith("面向高中生")
        assert len(briefed["brief_hash"]) == 64
        again = studio.create("矩阵为什么能让空间旋转？", brief="面向高中生，语气轻松，强调面积变化")
        assert again["id"] == briefed["id"]
        other = studio.create("矩阵为什么能让空间旋转？", brief="面向研究生，强调特征值")
        assert other["id"] != briefed["id"], "同题不同 brief 不得复用不相关成片"
        explicit = studio.create("矩阵为什么能让空间旋转？", brief="面向高中生，语气轻松，强调面积变化", new=True)
        assert explicit["id"] != briefed["id"] and explicit["revision"] == briefed["revision"] + 1
    finally:
        studio.close()


def test_brief_is_bounded_and_control_characters_are_removed():
    assert normalize_brief("  ") is None
    assert normalize_brief("背景\x00说明\n\n受众：高中生") == "背景说明\n\n受众：高中生"
    with pytest.raises(ValueError, match="brief"):
        normalize_brief("长" * 4001)


def test_old_database_is_migrated_without_losing_episodes(tmp_path):
    path = tmp_path / "old.sqlite"
    import sqlite3

    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE episodes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            intent TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            delivery TEXT, error TEXT, pid INTEGER, token TEXT, UNIQUE(intent, revision));
        INSERT INTO episodes(title,intent,created_at,updated_at) VALUES ('旧任务','old','t','t');
    """)
    db.commit()
    db.close()
    ledger = Ledger(path)
    try:
        columns = {row[1] for row in ledger.db.execute("PRAGMA table_info(episodes)")}
        assert {"brief", "brief_hash"} <= columns
        assert ledger.get(1)["title"] == "旧任务"
        row = ledger.reserve("新任务", "new-intent", brief="背景说明")
        assert row["brief"] == "背景说明" and row["brief_hash"]
    finally:
        ledger.close()


def test_stage_records_lightweight_metrics(tmp_path):
    studio = make_studio(tmp_path)
    try:
        episode = studio.create("指标记录测试")
        output = studio.workspace / "metric.txt"
        calls = []

        def action():
            calls.append(1)
            output.write_text("ok", encoding="utf-8")
            return {"ok": True}, [output]

        studio.stage(episode, "demo", {}, action)
        studio.stage(episode, "demo", {}, action)
        rows = (studio.workspace / "metrics.csv").read_text(encoding="utf-8-sig").strip().splitlines()
        assert len(rows) == 3 and "cache" in rows[0]
        assert "passed" in rows[1] and "cached" in rows[2]
        assert len(calls) == 1
    finally:
        studio.close()


def fake_render_run(command, *, cwd=None, timeout=600, log=None):
    if "render.mjs" in str(command[1]):
        spec = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        result = {}
        for cut in spec["cuts"]:
            out = Path(cut["output"])
            out.mkdir(parents=True, exist_ok=True)
            silent = out / "silent.mp4"
            silent.write_bytes(b"silent-video")
            cover = out / "cover.png"
            cover.write_bytes(b"png")
            stills = []
            for index, _scene in enumerate(cut["props"]["scenes"]):
                still = out / f"scene-{index + 1:02d}.jpg"
                still.write_bytes(b"jpg")
                stills.append(str(still))
            entry = {"video": str(silent), "cover": str(cover), "stills": stills,
                     "frames": sum(scene["frames"] for scene in cut["props"]["scenes"]),
                     "width": 1920 if cut["name"] == "long" else 1080,
                     "height": 1080 if cut["name"] == "long" else 1920, "fps": 30,
                     "fingerprint": "test", "hashes": {}}
            if spec.get("previewSeconds"):
                preview = out / "preview.mp4"
                preview.write_bytes(b"preview")
                entry["preview"] = str(preview)
            result[cut["name"]] = entry
        Path(spec["result"]).write_text(json.dumps(result), encoding="utf-8")
        return CompletedProcess(command, 0, "", "")
    Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
    Path(command[-1]).write_bytes(b"final-video")
    return CompletedProcess(command, 0, "", "")


def fake_prepare_cut(cut, config, cache, output, *, portrait):
    output.mkdir(parents=True, exist_ok=True)
    voice, mix = output / "narration.wav", output / "mix.wav"
    write_wav(voice, np.zeros(24000, dtype=np.float32))
    write_wav(mix, np.zeros((24000, 2), dtype=np.float32))
    seconds = float(config["short_seconds"] if portrait else config["long_seconds"])
    frames = max(1, round(seconds * config["fps"] / len(cut["scenes"])))
    scenes = []
    for raw in cut["scenes"]:
        scenes.append({**raw, "frames": frames,
                       "captions": [{"start": 0.2, "end": 1.0, "text": raw["narration"][:12]}],
                       "layers": raw.get("layers") or [layer()], "actions_resolved": [],
                       "caption_timing": "tts-word-boundaries", "layout_warnings": []})
    return {"title": cut["title"], "scenes": scenes, "frames": frames * len(scenes),
            "seconds": seconds, "mix": str(mix), "voice": str(voice),
            "style": cut.get("style", "tech")}, [voice, mix]


@pytest.fixture
def offline_pipeline(tmp_path, monkeypatch):
    def fake_assets(output):
        output.mkdir(parents=True, exist_ok=True)
        paths = []
        for rank in (1, 4, 12, 32):
            path = output / f"svd-{rank}.png"
            path.write_bytes(b"png")
            paths.append(path)
        return ["svd-1.png", "svd-4.png", "svd-12.png", "svd-32.png"], paths, {"1": {"mse": 0.1}}

    monkeypatch.setattr("movelyth.pipeline.prepare_cut", fake_prepare_cut)
    monkeypatch.setattr("movelyth.pipeline.image_layers", fake_assets)
    monkeypatch.setattr("movelyth.pipeline.run", fake_render_run)
    monkeypatch.setattr("movelyth.sources.collect_sources", lambda sources, directory: [
        {"url": source["url"], "status": "retrieved", "content_sha256": "0" * 64,
         "retrieved_at": "2026-10-25T00:00:00+08:00"} for source in sources])
    monkeypatch.setattr("movelyth.pipeline.verify_video", lambda *a, **k: {
        "passed": True, "checks": {"full_decode": True}, "duration": 60.0, "width": 1920, "height": 1080,
        "fps": 30.0, "mean_sample_motion": 1.0, "audio_listened": False, "asr_checked": False,
        "full_motion_aesthetic_review": False})
    def fake_stills(video, cut, fps, directory, portrait):
        directory.mkdir(parents=True, exist_ok=True)
        result = []
        for index in range(len(cut["scenes"])):
            path = directory / f"scene-{index}.jpg"
            path.write_bytes(b"jpg")
            result.append(str(path))
        return result

    monkeypatch.setattr("movelyth.pipeline.encoded_stills", fake_stills)
    monkeypatch.setattr("movelyth.pipeline.contact_sheet", lambda stills, output, portrait: output.write_bytes(b"jpg"))
    monkeypatch.setattr("movelyth.pipeline.audio_qc", lambda voice, mix, script, config: {
        "asr": {"status": "disabled"}, "transcript_check": {"status": "not-run"},
        "silence": {"status": "ok"}, "ducking": {"status": "ok"}, "listened_by_human": False})
    return tmp_path


def test_preview_stage_produces_storyboard_without_final_render(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("预览测试选题", brief="面向高中生，强调面积变化")
        result = studio.produce(episode["id"], preview_only=True)
        assert result["status"] == "previewed"
        storyboard = Path(result["storyboard"])
        assert storyboard.is_file()
        data = json.loads(storyboard.read_text(encoding="utf-8"))
        assert data["creation_mode"] == "preview" and data["provider"] == "mock"
        assert data["cuts"]["long"]["scenes"][0]["layers"]
        job = studio.workspace / f"VID-{episode['id']:06d}"
        assert (job / "preview" / "long" / "preview.mp4").is_file()
        assert "面向高中生" in (job / "agents" / "research" / "prompt.txt").read_text(encoding="utf-8")
        assert studio.ledger.get(episode["id"])["status"] == "previewed"
        assert not list(studio.delivery.rglob("*.mp4")), "预览不得进入待上传交付"
    finally:
        studio.close()


def test_full_offline_pipeline_delivers_manifest_and_quality_report(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("离线全流程测试")
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        destination = Path(result["delivery"])
        assert manifest_valid(destination)
        quality = json.loads((destination / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["creation_mode"] == "mock-provider"
        assert quality["provider"] == "mock"
        assert quality["audio"]["long"]["asr"]["status"] == "disabled"
        assert quality["human_review"] == {"watched_full_video": False, "listened_audio": False}
        provenance = json.loads((destination / "制作溯源.json").read_text(encoding="utf-8"))
        assert provenance["provider"] == "mock" and provenance["schema_version"] == 1
        assert (destination / "字幕_B站_横版.srt").is_file()
        again = studio.produce(episode["id"])
        assert again["reused"] is True
    finally:
        studio.close()


def test_local_revision_only_rewrites_targeted_scenes():
    frozen = Film.model_validate(film())
    revised = frozen.model_copy(deep=True)
    revised.long.scenes[1].narration = "被要求修改的镜头：把向量分解讲得更具体一些。"
    revised.long.scenes[0].narration = "审片模型擅自改写了没有要求修改的镜头。"
    merged = Studio._keep_untouched_scenes(frozen, revised, {"two"})
    assert merged.long.scenes[0].narration == frozen.long.scenes[0].narration
    assert merged.long.scenes[1].narration.startswith("被要求修改")


def test_revise_requires_locatable_notes(tmp_path):
    studio = make_studio(tmp_path)
    try:
        episode = studio.create("局部修改测试")
        with pytest.raises(ValueError, match="还没有通过审核"):
            studio.revise(episode["id"], "镜头 1 的字幕太长")
    finally:
        studio.close()
