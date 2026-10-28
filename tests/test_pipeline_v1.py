import json
from pathlib import Path

import pytest

from movelyth.agents import MockProvider
from movelyth.ledger import Ledger
from movelyth.models import SCHEMA_VERSION, Film
from movelyth.pipeline import Studio, manifest_valid, normalize_brief
from tests.conftest import make_studio
from tests.factories import film, layer, research_payload, review_payload


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
        first = data["cuts"]["long"]["scenes"][0]
        assert first["start"] == 0 and first["end"] > 0
        assert first["layers"][0]["region"] and "caption_timing" in first
        assert data["cuts"]["long"]["seconds"] > 0
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
        assert provenance["provider"] == "mock" and provenance["schema_version"] == SCHEMA_VERSION
        assert (destination / "字幕_B站_横版.srt").is_file()
        # Dry voice and mix travel with the package so the user can audition audio alone.
        for label in ("原声", "混音"):
            for platform in ("B站_横版", "抖音_竖版"):
                assert (destination / f"{label}_{platform}.mp3").is_file()
        again = studio.produce(episode["id"])
        assert again["reused"] is True
    finally:
        studio.close()


def test_user_library_asset_flows_into_render_and_credits(offline_pipeline):
    from movelyth.assets import register
    from tests.factories import scene as make_scene

    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        source = offline_pipeline / "own-photo.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 128)
        register(studio.workspace, source, asset_id="my_shot", source="用户拍摄", author="wenxvn",
                 license="自有素材", scope="本片使用")
        image_scene = make_scene("own", "这张照片是用户自己拍摄的素材，用于说明图层来源。", [
            layer("pic", type="image", procedural="", data_ref="my_shot", region="main"),
            layer("note", type="text", text="自有素材", procedural="", region="annotation"),
        ])
        payload = film()
        payload["long"]["scenes"][0] = image_scene
        payload["short"]["scenes"][0] = image_scene
        provider.responses["director"] = payload
        episode = studio.create("本地素材测试")
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        spec = json.loads((studio.workspace / f"VID-{episode['id']:06d}" / "render-spec.json")
                          .read_text(encoding="utf-8"))
        staged = studio.workspace / f"VID-{episode['id']:06d}" / "assets" / "asset-my_shot.png"
        assert staged.is_file(), "素材应被复制进受控渲染目录"
        assert Path(spec["assets"]) == staged.parent
        assert spec["cuts"][0]["props"]["scenes"][0]["layers"][0]["data_ref"] == "my_shot"
        credits = (Path(result["delivery"]) / "素材来源与署名.md").read_text(encoding="utf-8")
        assert "my_shot" in credits and "自有素材" in credits
        provenance = json.loads((Path(result["delivery"]) / "制作溯源.json").read_text(encoding="utf-8"))
        assert "my_shot" in provenance["library_assets"]
        from movelyth.assets import load_library

        entry = load_library(studio.workspace)["assets"]["my_shot"]
        assert entry["used_by_episodes"] == [episode["id"]], "交付后应记录引用任务"
    finally:
        studio.close()


def test_missing_library_asset_fails_before_rendering(offline_pipeline):
    from movelyth.assets import AssetError
    from tests.factories import scene as make_scene

    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        payload = film()
        payload["long"]["scenes"][0] = make_scene("own", "引用一个没有登记过的素材，应该在渲染前失败。", [
            layer("pic", type="image", procedural="", data_ref="ghost_asset", region="main"),
        ])
        provider.responses["director"] = payload
        episode = studio.create("缺失素材测试")
        with pytest.raises(AssetError, match="asset-add"):
            studio.produce(episode["id"])
        assert studio.ledger.get(episode["id"])["status"] == "failed"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        assert not (job / "render-spec.json").exists(), "不得在素材缺失时启动渲染"
    finally:
        studio.close()


def test_script_rejection_is_kept_for_the_next_resume(offline_pipeline, monkeypatch):
    """A rejected script must not be silently regenerated with the same prompt."""
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload(passed=False)})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("审稿拒绝留痕")
        with pytest.raises(RuntimeError, match="脚本审片未通过"):
            studio.produce(episode["id"])
        feedback = studio.workspace / f"VID-{episode['id']:06d}" / "script-feedback.json"
        assert feedback.is_file()
        data = json.loads(feedback.read_text(encoding="utf-8"))
        assert data["issues"] and data["at"]
        prompts = list((studio.workspace / f"VID-{episode['id']:06d}" / "agents").glob("director-*/prompt.txt"))
        assert "review_issues" in prompts[0].read_text(encoding="utf-8")
        provider.responses["reviewer"] = review_payload(passed=True)
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        assert not feedback.exists(), "通过后应清掉旧的拒绝记录"
    finally:
        studio.close()


def test_invalid_cached_script_is_regenerated_not_shipped(offline_pipeline):
    """A frozen script that no longer satisfies the contract must be rebuilt."""
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("契约变化后的缓存")
        assert studio.produce(episode["id"])["status"] == "ready"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        # Simulate a contract change: the approved script now violates the DSL.
        broken = json.loads((job / "film.json").read_text(encoding="utf-8"))
        broken["long"]["scenes"][0]["beats"] = [{"at": "narration:不存在的片段", "purpose": "分层"}]
        (job / "film.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        (job / "stages" / "script.json").unlink(missing_ok=True)
        (job / "stages" / "sound.json").unlink(missing_ok=True)
        (job / "stages" / "render.json").unlink(missing_ok=True)
        (job / "stages" / "check.json").unlink(missing_ok=True)
        studio.ledger.status(episode["id"], "failed")
        result = studio.produce(episode["id"])
        assert result["status"] == "ready"
        fixed = json.loads((job / "film.json").read_text(encoding="utf-8"))
        assert fixed["long"]["scenes"][0]["beats"] == []
        assert not (job / "script-feedback.json").exists()
    finally:
        studio.close()


def test_reuse_script_keeps_approved_film_without_calling_director(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("复用已审脚本")
        assert studio.produce(episode["id"])["status"] == "ready"
        job = studio.workspace / f"VID-{episode['id']:06d}"
        original = json.loads((job / "film.json").read_text(encoding="utf-8"))
        for name in ("script", "sound", "render", "check"):
            (job / "stages" / f"{name}.json").unlink(missing_ok=True)
        studio.ledger.status(episode["id"], "failed")
        provider.calls.clear()
        provider.responses["director"] = {"title": "不该被使用"}
        result = studio.produce(episode["id"], reuse_script=True)
        assert result["status"] == "ready"
        assert "director" not in provider.calls, "复用脚本时不得重新调用编导"
        assert json.loads((job / "film.json").read_text(encoding="utf-8")) == original
        events = [row["state"] for row in studio.ledger.history(episode["id"])]
        assert "approved-script-reused" in events
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
