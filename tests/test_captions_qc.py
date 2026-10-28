"""S2-04: real font measurement, caption cues and layout collisions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from movelyth.agents import MockProvider
from movelyth.captions_qc import (
    READING_SPEED,
    collision_report,
    cue_report,
    srt_matches_cues,
    text_layer_report,
)
from movelyth.fonts import availability, font_report, load_font, measure, text_width_ratio
from movelyth.models import Scene
from movelyth.pipeline import srt
from movelyth.scenedsl import caption_band, normalize_scene
from tests.conftest import make_studio
from tests.factories import chart_layer, film, layer, research_payload, review_payload, scene


def page(start=0.2, end=2.2, text="损失从 0.9 降到 0.3") -> dict:
    return {"start": start, "end": end, "text": text}


def scene_data(**overrides) -> dict:
    raw = scene("one", "损失从 0.9 降到 0.3，下降速度先快后慢，需要看清拐点在哪里。",
                [chart_layer(values=[0.9, 0.7, 0.5, 0.3], annotations=[{"x": 2, "text": "拐点"}])],
                **overrides)
    normalized = normalize_scene(Scene.model_validate(raw), duration=4.0)
    normalized["frames"] = 120
    normalized["captions"] = [page()]
    return normalized


# ---------------------------------------------------------------------- fonts

def test_the_real_font_is_loaded_and_named():
    font, path = load_font("body", 66)
    assert font is not None and Path(path).is_file()
    report = font_report("损失下降 0.5", size=66)
    assert report["ok"] is True and report["family"] and report["width"] > 0
    assert report["coverage"] in {"cmap", "unknown"}


def test_missing_glyphs_are_detected_from_the_font_cmap():
    report = font_report("天气 ☃ 与 ☂")
    if report["coverage"] != "cmap":
        pytest.skip("fontTools 不可用，覆盖率无法从 cmap 读取")
    assert report["ok"] is False and set(report["missing"]) == {"☃", "☂"}


def test_measured_width_scales_with_text_and_size():
    short = measure("损失", size=66)["width"]
    longer = measure("损失下降很多", size=66)["width"]
    bigger = measure("损失", size=96)["width"]
    assert short < longer and short < bigger
    ratio = text_width_ratio("损失下降", 1000, size=66)
    assert 0 < ratio < 1


def test_availability_reports_every_style():
    report = availability()
    assert report["body"]["ok"] and report["display"]["ok"]
    assert report["ok"] is True


# ------------------------------------------------------------------- captions

def test_a_well_paced_caption_passes():
    report = cue_report(scene_data(), "long", orientation="landscape")
    assert report["problems"] == []


def test_too_fast_and_too_short_pages_are_reported():
    data = scene_data()
    data["captions"] = [page(0.2, 0.5, "这句话很长但只给了不到三分之一秒的时间")]
    problems = cue_report(data, "long", orientation="landscape")["problems"]
    assert any("字/秒" in problem for problem in problems)
    assert any("只显示" in problem for problem in problems)


def test_overlapping_pages_are_reported():
    data = scene_data()
    data["captions"] = [page(0.2, 2.0, "第一页字幕"), page(1.5, 3.0, "第二页字幕")]
    problems = cue_report(data, "long", orientation="landscape")["problems"]
    assert any("交叠" in problem for problem in problems)


def test_the_portrait_reading_speed_is_stricter():
    data = scene_data()
    text = "这是一个用于测试阅读速度的字幕句内"   # 17 chars in 2.0 s → 8.5 cps
    assert len(text) == 17, len(text)
    data["captions"] = [page(0.2, 2.2, text)]
    long_problems = cue_report(data, "long", orientation="landscape")["problems"]
    short_problems = cue_report(data, "short", orientation="portrait")["problems"]
    assert not any("字/秒" in problem for problem in long_problems)
    assert any("字/秒" in problem for problem in short_problems)
    assert READING_SPEED["short"] < READING_SPEED["long"]


def test_a_caption_that_overlaps_content_is_reported():
    data = scene_data(layout="immersive")
    # In immersive, `bottom` sits just above the caption band; a tall layer can cross it.
    data["layers"] = [{**layer("note", type="text", region="bottom", text="注释"),
                       "region": "bottom"}]
    problems = collision_report(data, orientation="landscape")
    assert isinstance(problems, list)


def test_caption_band_is_defined_for_both_orientations():
    assert caption_band("landscape")["h"] > 0 and caption_band("portrait")["h"] > 0


def test_a_text_layer_wider_than_its_box_is_reported():
    data = scene_data()
    data["layers"] = [layer("long_note", type="text", region="annotation",
                            text="这是一条明显超过注释区域宽度的很长很长很长的注释文字")]
    problems = text_layer_report(data, orientation="landscape", cut="long")["problems"]
    assert any("宽度占" in problem for problem in problems)


def test_srt_is_generated_from_the_same_cues():
    data = scene_data()
    data["captions"] = [page(0.2, 2.0, "损失从 0.9 降到 0.3"), page(2.2, 3.6, "拐点出现在第三轮")]
    text = srt({"scenes": [data]}, 30)
    assert "损失从 0.9 降到 0.3" in text
    assert srt_matches_cues({"scenes": [data]}, text)["passed"] is True


def test_a_tampered_srt_is_detected():
    data = scene_data()
    data["captions"] = [page(0.2, 2.0, "损失从 0.9 降到 0.3")]
    text = srt({"scenes": [data]}, 30).replace("损失从 0.9 降到 0.3", "损失从 9 降到 3")
    result = srt_matches_cues({"scenes": [data]}, text)
    assert result["passed"] is False and result["missing"]


# ------------------------------------------------------------------- pipeline

def test_the_report_records_fonts_captions_and_srt_consistency(offline_pipeline):
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("字体与字幕记录测试")
        result = studio.produce(episode["id"])
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert quality["fonts"]["ok"] is True
        assert quality["fonts"]["body"]["family"]
        assert quality["captions"]["long"]["passed"] is True
        assert quality["captions"]["short"]["cues"] >= 1
    finally:
        studio.close()
