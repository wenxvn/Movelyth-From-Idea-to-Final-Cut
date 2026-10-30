"""S2-09: layout pre-check, full-length animatic and final-vs-animatic comparison."""
from __future__ import annotations

import json

import pytest

from movelyth.agents import MockProvider
from movelyth.animatic import (
    animatic_spec,
    compare_animatic,
    layout_precheck,
    sampling_plan,
)
from movelyth.models import Scene
from movelyth.scenedsl import normalize_scene
from tests.conftest import make_studio
from tests.factories import film, layer, research_payload, review_payload, scene

CONFIG = {"fps": 30}


def timeline(*, captions=None, hold_reason="", duration=6.0, layers=None, scene_id="one") -> dict:
    model = Scene.model_validate(scene(scene_id, "这是一个用于测试的旁白句子，说明画面的真实含义。",
                                      layers or [layer()], hold_reason=hold_reason))
    normalized = normalize_scene(model, duration=duration)
    normalized["frames"] = int(duration * 30)
    normalized["captions"] = captions if captions is not None else [
        {"start": 0.2, "end": 2.4, "text": "这是一个用于测试的旁白句子"}]
    return {"scenes": [normalized], "seconds": duration, "frames": int(duration * 30)}


def test_a_healthy_timeline_passes_the_dry_run():
    report = layout_precheck({"long": timeline()}, CONFIG)
    assert report["passed"] is True and report["checked_scenes"] == 1
    scene_report = report["cuts"]["long"]["scenes"][0]
    assert scene_report["mobile_readability"]["profile"] == "landscape-rotated-844px"
    assert "非实际理解评测" in scene_report["mobile_readability"]["method"]


def test_phone_readability_uses_portrait_feed_scale_and_flags_small_content():
    small_chart = timeline(layers=[{
        "id": "plot", "type": "chart", "chart": "line",
        "series": [{"label": "A", "values": [1, 2, 3]}],
        "annotations": [{"x": 1, "text": "起点"}],
    }])
    report = layout_precheck({"short": small_chart}, CONFIG)
    mobile = report["cuts"]["short"]["scenes"][0]["mobile_readability"]
    assert mobile["profile"] == "portrait-feed-390px"
    assert mobile["scale"] == pytest.approx(390 / 1080, abs=1e-4)
    assert mobile["small_text"]
    assert any("项目 12px 复核线" in warning for warning in mobile["warnings"])


def test_a_still_reading_pause_with_a_reason_is_not_reported_as_a_motion_defect():
    quiet = timeline(captions=[{"start": 0.2, "end": 2.0, "text": "停住读完结果"}],
                     hold_reason="停稳后让观众读完结果")
    report = layout_precheck({"long": quiet}, CONFIG)
    assert not any("没有动作/事件/字幕变化" in warning for warning in report["warnings"])


def test_caption_reading_speed_and_flash_are_caught():
    slow = layout_precheck({"long": timeline(captions=[
        {"start": 0.2, "end": 0.6, "text": "这是一句非常非常长的字幕内容需要读很久"}])}, CONFIG)
    assert not slow["passed"]
    # The wording comes from captions_qc, the single owner of caption thresholds.
    assert any("字/秒" in problem for problem in slow["problems"])
    assert any("只显示" in problem for problem in slow["problems"])


def test_an_empty_caption_page_is_a_problem():
    report = layout_precheck({"long": timeline(captions=[{"start": 0.2, "end": 2.0, "text": " "}])}, CONFIG)
    assert any("空白页" in problem for problem in report["problems"])


def test_an_unregistered_asset_is_caught_but_builtin_images_are_not():
    bad = timeline(layers=[layer("pic", type="image", data_ref="not_registered")])
    report = layout_precheck({"long": bad}, CONFIG, library_ids=["own_photo"])
    assert any("未登记的素材" in problem for problem in report["problems"])
    builtin = timeline(layers=[layer("pic", type="image", data_ref="svd_12")])
    assert layout_precheck({"long": builtin}, CONFIG, library_ids=["own_photo"])["passed"] is True


def test_a_long_gap_needs_a_hold_reason():
    without = layout_precheck({"long": timeline(captions=[{"start": 0.2, "end": 2.0, "text": "短句"}])}, CONFIG)
    assert any("hold_reason" in warning for warning in without["warnings"])
    with_reason = layout_precheck({"long": timeline(
        captions=[{"start": 0.2, "end": 2.0, "text": "短句"}], hold_reason="对照两个刻度需要停留")}, CONFIG)
    assert not any("hold_reason" in warning for warning in with_reason["warnings"])


def test_an_invalid_recipe_fails_the_dry_run():
    model = Scene.model_validate({**scene("one", "这是一个用于测试的旁白句子，说明画面的真实含义。",
                                          [layer()]), "recipe": "flow-expand"})
    normalized = normalize_scene(model, duration=6.0)
    normalized["frames"] = 180
    normalized["captions"] = [{"start": 0.2, "end": 2.4, "text": "这是一个用于测试的旁白句子"}]
    report = layout_precheck({"long": {"scenes": [normalized], "seconds": 6.0, "frames": 180}}, CONFIG)
    assert any("不适用" in problem for problem in report["problems"])


def test_the_sampling_plan_names_every_reason_and_has_no_duplicates():
    plan = sampling_plan({"long": timeline(duration=8.0)}, 30)
    reasons = {item["reason"].split(":")[0] for item in plan}
    assert {"opening", "ending", "scene-midpoint"} <= reasons
    assert len(plan) == len({(item["cut"], item["seconds"]) for item in plan})
    assert all(item["cut"] == "long" for item in plan)


def test_animatic_spec_requests_a_full_length_low_resolution_render():
    spec = animatic_spec([{"name": "long"}, {"name": "short"}], scale=0.35)
    assert spec["animaticScale"] == 0.35 and spec["animaticCuts"] == ["long", "short"]


def test_comparison_requires_the_animatic_and_the_same_frame_count():
    timelines = {"long": timeline()}
    missing = compare_animatic({"long": {"frames": 180}}, {"long": {"frames": 180}}, timelines, 30)
    assert missing["passed"] is False and "缺少整片草片" in missing["problems"][0]
    mismatch = compare_animatic({"long": {"animatic": "a.mp4", "frames": 170}},
                                {"long": {"frames": 180}}, timelines, 30)
    assert mismatch["passed"] is False
    good = compare_animatic({"long": {"animatic": "a.mp4", "frames": 180}},
                            {"long": {"frames": 180}}, timelines, 30)
    assert good["passed"] is True


def test_pipeline_precheck_runs_before_render_and_is_recorded(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("布局预检记录测试")
        result = studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        precheck = json.loads((job / "layout-precheck.json").read_text(encoding="utf-8"))
        assert precheck["passed"] is True and precheck["sampling_plan"]
        spec = json.loads((job / "render-spec.json").read_text(encoding="utf-8"))
        assert spec["animaticScale"] == 0.35
        assert (job / "renders" / "long" / "animatic.mp4").is_file()
        quality = json.loads((__import__("pathlib").Path(result["delivery"]) / "质检报告.json")
                             .read_text(encoding="utf-8"))
        assert quality["animatic"]["passed"] is True
        assert quality["layout_precheck"]["passed"] is True
        assert quality["sampling_plan"]
    finally:
        studio.close()


def test_precheck_blocks_the_render_when_captions_are_unreadable(offline_pipeline, monkeypatch):
    from movelyth import pipeline as pipeline_module

    real = pipeline_module.prepare_cut

    def too_fast(cut, config, cache, output, *, portrait):
        data, paths = real(cut, config, cache, output, portrait=portrait)
        for scene_data in data["scenes"]:
            scene_data["captions"] = [{"start": 0.2, "end": 0.5,
                                       "text": "这一整句话塞进不到半秒里，观众根本来不及读"}]
        return data, paths

    monkeypatch.setattr("movelyth.pipeline.prepare_cut", too_fast)
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("字幕过快阻断测试")
        with pytest.raises(RuntimeError, match="布局预检未通过"):
            studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        assert not (job / "renders" / "long" / "final.mp4").exists()
        report = json.loads((job / "layout-precheck.json").read_text(encoding="utf-8"))
        assert any("字幕" in problem for problem in report["problems"])
    finally:
        studio.close()
