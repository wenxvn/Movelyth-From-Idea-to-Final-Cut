"""S3-03: asset requests, local matching, provenance and aspect-aware cropping."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from movelyth.agents import MockProvider
from movelyth.assetplan import (
    AssetRequest,
    candidates,
    choose,
    library_metadata,
    plan_crop,
)
from movelyth.assets import register
from tests.conftest import make_studio
from tests.factories import film, layer, research_payload, review_payload, scene


def make_image(path: Path, size=(1600, 900)) -> Path:
    Image.new("RGB", size, (30, 90, 120)).save(path)
    return path


def library(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    register(workspace, make_image(tmp_path / "server.png"), asset_id="server_rack",
             source="自有拍摄", author="维护者", license="自有素材",
             subject="服务器机柜", action="插拔网线", setting="机房",
             tags=["机房", "网络"], focus=(0.5, 0.4), subject_box={"x": 0.3, "y": 0.2, "w": 0.4, "h": 0.5})
    register(workspace, make_image(tmp_path / "city.png", (900, 1600)), asset_id="city_night",
             source="自有拍摄", author="维护者", license="自有素材",
             subject="城市夜景", tags=["城市"])
    register(workspace, make_image(tmp_path / "sketch.png"), asset_id="sketch_flow",
             source="自制", author="维护者", license="自有素材",
             subject="流程图", authenticity="illustration")
    return workspace


def request(**overrides) -> AssetRequest:
    payload = {"subject": "服务器机柜", "action": "插拔网线", "setting": "机房"}
    payload.update(overrides)
    return AssetRequest(**payload)


# ------------------------------------------------------------------- matching

def test_a_matching_asset_is_found_with_reasons(tmp_path):
    workspace = library(tmp_path)
    ranked = candidates(workspace, request())
    assert ranked["candidates"][0]["id"] == "server_rack"
    assert any("主体匹配" in reason for reason in ranked["candidates"][0]["reasons"])
    assert any("授权信息完整" in reason for reason in ranked["candidates"][0]["reasons"])


def test_a_keyword_hit_with_the_wrong_meaning_is_not_chosen(tmp_path):
    workspace = library(tmp_path)
    decision = choose(workspace, request(must_not=["流程图"]), orientation="landscape")
    assert decision["chosen"] == "server_rack"
    refused = {item["id"]: item["reasons"] for item in decision["rejected"]}
    assert "sketch_flow" in refused


def test_evidence_requests_reject_illustrations(tmp_path):
    workspace = library(tmp_path)
    decision = choose(workspace, request(subject="流程图", authenticity="evidence"),
                      orientation="landscape")
    assert decision["chosen"] == ""
    assert any("示意" in reason for item in decision["rejected"] for reason in item["reasons"])


def test_missing_licence_is_a_hard_rejection(tmp_path):
    workspace = tmp_path / "workspace"
    register(workspace, make_image(tmp_path / "a.png"), asset_id="no_licence",
             source="未知", author="未知", license="待确认", subject="服务器机柜")
    # Simulate a library entry whose licence was later found to be unknown.
    path = workspace / "assets" / "library.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["assets"]["no_licence"]["license"] = ""
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    decision = choose(workspace, request(), orientation="landscape")
    assert decision["chosen"] == ""
    assert any("授权信息缺失" in reason for item in decision["rejected"] for reason in item["reasons"])


def test_an_empty_library_reports_the_reason_instead_of_a_fake_picture(tmp_path):
    decision = choose(tmp_path / "empty", request(), orientation="landscape")
    assert decision["chosen"] == "" and "没有可用素材" in decision["reason"]


# --------------------------------------------------------------------- cropping

def test_landscape_crop_keeps_the_subject_and_reports_the_rectangle(tmp_path):
    path = make_image(tmp_path / "wide.png", (1600, 900))
    crop = plan_crop(path, "landscape", focus=(0.5, 0.5), subject_box={"x": 0.3, "y": 0.2, "w": 0.4, "h": 0.5})
    assert crop["ok"] is True and crop["subject_inside"] is True
    left, top, width, height = crop["crop"]
    assert width / height == pytest.approx(16 / 9, rel=0.01)
    assert left >= 0 and top >= 0 and left + width <= 1600.5 and top + height <= 900.5


def test_a_portrait_crop_that_would_cut_the_subject_is_rejected(tmp_path):
    path = make_image(tmp_path / "wide.png", (1600, 900))
    crop = plan_crop(path, "portrait", focus=(0.5, 0.5),
                     subject_box={"x": 0.0, "y": 0.2, "w": 0.95, "h": 0.5})
    assert crop["ok"] is False
    assert "切掉主体" in crop["reason"]


def test_a_subject_that_is_too_small_after_a_real_crop_is_rejected(tmp_path):
    # A square source cropped to 9:16 loses most of its width; a tiny subject then
    # becomes unreadably small in the crop.
    path = make_image(tmp_path / "square.png", (1200, 1200))
    crop = plan_crop(path, "portrait", focus=(0.5, 0.5),
                     subject_box={"x": 0.45, "y": 0.45, "w": 0.1, "h": 0.1})
    assert crop["ok"] is False and "太小" in crop["reason"]


def test_an_uncropped_source_is_not_rejected_for_a_small_subject(tmp_path):
    path = make_image(tmp_path / "wide.png", (1600, 900))
    crop = plan_crop(path, "landscape", focus=(0.5, 0.5),
                     subject_box={"x": 0.45, "y": 0.45, "w": 0.05, "h": 0.05})
    assert crop["ok"] is True and crop["subject_share"] < 0.35


def test_an_svg_is_left_uncropped_instead_of_guessed(tmp_path):
    svg = tmp_path / "vector.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', encoding="utf-8")
    crop = plan_crop(svg, "portrait")
    assert crop["ok"] is True and "contain" in crop["skipped"]


def test_choose_returns_the_crop_and_provenance(tmp_path):
    workspace = library(tmp_path)
    decision = choose(workspace, request(), orientation="landscape")
    assert decision["chosen"] == "server_rack"
    assert decision["crop"]["ok"] is True
    assert decision["provenance"]["author"] == "维护者"
    assert len(decision["provenance"]["sha256"]) == 64


def test_a_portrait_crop_that_would_cut_the_subject_returns_no_asset(tmp_path):
    workspace = library(tmp_path)
    decision = choose(workspace, request(), orientation="portrait")
    assert decision["chosen"] == ""
    assert "没有可用素材" in decision["reason"]


def test_an_unrelated_picture_is_not_used_as_a_substitute(tmp_path):
    workspace = library(tmp_path)
    decision = choose(workspace, request(subject="服务器机柜", action="", setting=""), orientation="landscape")
    assert decision["chosen"] == "server_rack"
    decision = choose(workspace, request(subject="海底珊瑚", action="", setting=""), orientation="landscape")
    assert decision["chosen"] == ""
    assert all(item["score"] < 2.0 for item in decision["skipped"])


def test_library_metadata_reports_which_fields_are_actually_present(tmp_path):
    workspace = library(tmp_path)
    meta = library_metadata(workspace)
    assert meta["assets"] == 3 and meta["with_metadata"] == 3
    assert meta["fields"]["subject"] == 3


# -------------------------------------------------------------------- pipeline

def test_pipeline_records_asset_decisions_and_crop(offline_pipeline):
    from movelyth.assets import register as register_asset

    workspace = offline_pipeline / "workspace"
    register_asset(workspace, make_image(offline_pipeline / "own.png"), asset_id="own_photo",
                   source="自有拍摄", author="维护者", license="自有素材",
                   subject="矩阵", focus=(0.5, 0.5), subject_box={"x": 0.3, "y": 0.3, "w": 0.4, "h": 0.4})
    scenes = [scene("one", "矩阵把单位正方形变成平行四边形，面积按行列式缩放。",
                    [layer("pic", type="image", data_ref="own_photo")]),
              scene("two", "把向量分解成两个方向的分量，就能看清变换做了什么。",
                    [layer("vec", procedural="vectors")]),
              scene("three", "沿着投影方向取最近的落点，残差就是丢掉的那部分。",
                    [layer("proj", procedural="projection")])]
    provider = MockProvider({"research": research_payload(), "director": film(long_scenes=scenes),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("素材裁切记录测试")
        result = studio.produce(episode["id"])
        job = studio.workspace / f"VID-{episode['id']:06d}"
        decisions = json.loads((job / "asset-decisions.json").read_text(encoding="utf-8"))["decisions"]
        photo = [item for item in decisions if item.get("asset") == "own_photo"]
        assert photo and photo[0]["chosen"] == "own_photo"
        assert photo[0]["crop"]["ok"] is True
        spec = json.loads((job / "render-spec.json").read_text(encoding="utf-8"))
        long_scene = spec["cuts"][0]["props"]["scenes"][0]
        image_layer = next(item for item in long_scene["layers"] if item["type"] == "image")
        assert image_layer["crop"] and len(image_layer["crop_source"]) == 2
        assert (Path(result["delivery"]) / "manifest.json").is_file()
    finally:
        studio.close()
