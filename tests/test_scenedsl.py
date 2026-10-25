import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from movelyth.consistency import check_scene
from movelyth.models import Action, Film, Layer, Scene, VisualKind
from movelyth.quality import validate_script
from movelyth.scenedsl import (
    normalize_scene,
    resolve_data_layers,
    scene_signature,
    validate_cut_dsl,
    validate_cut_timeline,
)
from tests.factories import chart_layer, diagram_layer, film, layer, research_payload, scene

ROOT = Path(__file__).parents[1]


def test_legacy_scene_without_layers_still_renders_as_procedural():
    legacy = Scene.model_validate(scene("legacy"))
    normalized = normalize_scene(legacy, duration=6.0)
    assert [item["type"] for item in normalized["layers"]] == ["procedural"]
    assert normalized["layers"][0]["procedural"] == "matrix"
    assert normalized["actions_resolved"] == []
    assert normalized["schema_version"] == 1


def test_narration_beats_and_actions_resolve_to_real_tts_time():
    payload = scene("beats", "误差从零点九降到零点三，最后稳定下来。",
                    [chart_layer("loss", [0.9, 0.7, 0.5, 0.3]),
                     layer("note", type="text", text="梯度下降", procedural="")],
                    beats=[{"at": "start", "purpose": "展示初始误差"},
                           {"at": "narration:最后稳定下来", "purpose": "强调收敛"}],
                    actions=[{"target": "loss", "kind": "draw", "start": "start", "end": "narration:最后稳定下来",
                              "dx": 0, "dy": 0, "scale": 1, "degrees": 0},
                             {"target": "note", "kind": "appear", "start": "0.6", "end": "0.8",
                              "dx": 0, "dy": 0, "scale": 1, "degrees": 0}])
    model = Scene.model_validate(payload)
    boundaries = [{"text": "误差从零点九降到零点三", "start": 0.4, "end": 1.8},
                  {"text": "最后稳定下来", "start": 2.0, "end": 2.6}]
    normalized = normalize_scene(model, duration=3.2, boundaries=boundaries)
    assert normalized["beat_timing"] == "tts-word-boundaries"
    assert normalized["beat_times"][0]["fraction"] == 0.0
    assert normalized["beat_times"][1]["at"] == pytest.approx(2.0, abs=0.01)
    draw = next(item for item in normalized["actions_resolved"] if item["kind"] == "draw")
    assert 0 <= draw["from"] < draw["to"] <= 1
    assert draw["to"] > 0.5


def test_missing_narration_fragment_and_bad_spans_are_rejected():
    payload = scene("bad", "旁白里没有那句话，只有这一句内容。", [layer()],
                    actions=[{"target": "visual", "kind": "fade", "start": "narration:不存在的句子",
                              "end": "end", "dx": 0, "dy": 0, "scale": 1, "degrees": 0}])
    with pytest.raises(ValueError):
        normalize_scene(Scene.model_validate(payload), duration=3.0)
    reversed_span = scene("rev", "这是一段足够长的旁白内容用于测试。", [layer()],
                          actions=[{"target": "visual", "kind": "move", "start": "0.8", "end": "0.2",
                                    "dx": 0.1, "dy": 0, "scale": 1, "degrees": 0}])
    with pytest.raises(ValueError):
        normalize_scene(Scene.model_validate(reversed_span), duration=3.0)
    ghost = scene("ghost", "这是一段足够长的旁白内容用于测试。", [layer()],
                  actions=[{"target": "nope", "kind": "move", "start": "0.2", "end": "0.4",
                            "dx": 0, "dy": 0, "scale": 1, "degrees": 0}])
    with pytest.raises(ValidationError):
        Scene.model_validate(ghost)


def test_unbounded_or_executable_parameters_are_rejected():
    base = layer()
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "points": [float("nan"), 0]})
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "data_ref": "../../secrets"})
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "data_ref": "https://evil.example/data"})
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "procedural": "os.system"})
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "series": [{"label": "x", "values": [1] * 61, "unit": ""}]})
    with pytest.raises(ValidationError):
        Layer.model_validate({**base, "text": "长" * 121})
    with pytest.raises(ValidationError):
        Action.model_validate({"target": "visual", "kind": "move", "start": "0", "end": "1",
                               "dx": 5, "dy": 0, "scale": 1, "degrees": 0})


def test_timeline_layer_requires_real_steps():
    timeline = layer("stages", type="timeline", procedural="", steps=["封装", "路由", "解封装"])
    assert Layer.model_validate(timeline).type == "timeline"
    with pytest.raises(ValidationError, match="timeline"):
        Layer.model_validate({**timeline, "steps": ["只有一个"]})
    with pytest.raises(ValidationError, match="步骤"):
        Layer.model_validate({**timeline, "steps": ["好" * 25, "第二步"]})


def test_chart_trend_must_match_narration():
    falling = Scene.model_validate(scene("trend", "误差不断上升，情况越来越糟，问题仍然存在。",
                                        [chart_layer("loss", [0.9, 0.7, 0.5, 0.3])]))
    errors, _warnings = check_scene(falling)
    assert errors and "实际下降" in errors[0]
    honest = Scene.model_validate(scene("trend2", "误差不断下降，最后收敛到一个很小的数值。",
                                       [chart_layer("loss", [0.9, 0.7, 0.5, 0.3])]))
    assert check_scene(honest)[0] == []


def test_measured_claim_on_illustrative_chart_is_rejected():
    scene_model = Scene.model_validate(scene("measured", "这组实验数据表明误差持续下降并稳定。",
                                             [chart_layer("loss", [0.9, 0.7, 0.5], source_note="示意")]))
    errors, _ = check_scene(scene_model)
    assert any("示意数据" in message for message in errors)


def test_matrix_claims_are_checked_against_real_coefficients():
    rotation = Scene.model_validate(scene("rot", "这个矩阵让整个空间旋转九十度角。", [layer()],
                                          matrix=[0, -1, 1, 0]))
    assert check_scene(rotation)[0] == []
    fake_rotation = Scene.model_validate(scene("rot2", "这个矩阵让整个空间发生九十度旋转。", [layer()],
                                               matrix=[1, 1, 0, 1]))
    assert any("不是纯旋转" in warning for warning in check_scene(fake_rotation)[1])
    wrong_area = Scene.model_validate(scene("area", "这个变换让图形的面积保持不变。", [layer()],
                                            matrix=[2, 0, 0, 2]))
    assert any("面积不变" in error for error in check_scene(wrong_area)[0])
    wrong_collapse = Scene.model_validate(scene("collapse", "这个矩阵把平面压成一条线，不可逆。", [layer()],
                                                matrix=[1, 0, 0, 1]))
    assert any("塌缩" in error for error in check_scene(wrong_collapse)[0])


def test_layout_budget_and_caption_band_are_checked():
    crowded = Scene.model_validate(scene("crowded", "这是一段足够长的旁白内容用于测试。", [
        layer("note", type="text", text="说" * 100, procedural="", region="annotation")]))
    problems = validate_cut_dsl(_cut_with(crowded), vertical=False)
    assert any("超出" in problem for problem in problems)


def test_every_region_stays_inside_canvas_and_clear_of_reserved_bands():
    from itertools import combinations

    from movelyth.scenedsl import LAYOUTS, _overlap, reserved_bands

    for orientation, variants in LAYOUTS.items():
        width, height = (1920, 1080) if orientation == "landscape" else (1080, 1920)
        for layout, boxes in variants.items():
            bands = reserved_bands(orientation, layout)
            for band in bands:
                assert 0 <= band["x"] and 0 <= band["y"], f"{orientation}/{layout} {band['name']} 越界"
                assert band["x"] + band["w"] <= width, f"{orientation}/{layout} {band['name']} 越界"
                assert band["y"] + band["h"] <= height, f"{orientation}/{layout} {band['name']} 越界"
            rects = {}
            for name, (x, y, w, h) in boxes.items():
                assert 0 <= x and 0 <= y, f"{orientation}/{layout}/{name} 越出画布"
                assert x + w <= width and y + h <= height, f"{orientation}/{layout}/{name} 越出画布"
                if name == "full":
                    continue
                box = {"x": x, "y": y, "w": w, "h": h}
                rects[name] = box
                for band in bands:
                    assert not _overlap(box, band), f"{orientation}/{layout}/{name} 与{band['name']}重叠"
            for left, right in combinations(rects, 2):
                assert not _overlap(rects[left], rects[right]), \
                    f"{orientation}/{layout} 的 {left} 与 {right} 区域互相遮挡"


def _cut_with(*scenes):
    from movelyth.models import Cut

    padded = list(scenes)
    while len(padded) < 3:
        clone = padded[0].model_copy(update={"id": f"{padded[0].id}_{len(padded)}"})
        padded.append(clone)
    return Cut.model_validate({"title": "布局测试", "description": "这是一个用于布局检查的描述文本，长度足够。",
                               "tags": ["测试", "布局"], "scenes": padded, "schema_version": 1})


def test_cover_layout_exists_for_both_orientations():
    from movelyth.scenedsl import HEADING_BANDS, LAYOUTS, regions

    for orientation in ("landscape", "portrait"):
        assert "cover" in LAYOUTS[orientation]
        assert "cover" in HEADING_BANDS[orientation]
        boxes = regions(orientation, "cover")
        assert boxes["main"]["w"] > 0 and boxes["main"]["h"] > 0


def test_visual_layers_must_use_a_large_region():
    tiny = Scene.model_validate(scene("tiny", "这是一段足够长的旁白内容用于测试。", [
        chart_layer("loss", region="annotation")]))
    problems = validate_cut_dsl(_cut_with(tiny), vertical=False)
    assert any("会缩得太小" in problem for problem in problems)
    side_without_compare = Scene.model_validate(scene("side", "这是一段足够长的旁白内容用于测试。", [
        chart_layer("loss", region="side")], layout="diagram"))
    assert any("layout=compare" in problem for problem in validate_cut_dsl(_cut_with(side_without_compare), vertical=False))
    compare_side = Scene.model_validate(scene("cmp", "这是一段足够长的旁白内容用于测试。", [
        chart_layer("loss", region="side")], layout="compare"))
    assert not [p for p in validate_cut_dsl(_cut_with(compare_side), vertical=False) if "会缩得太小" in p]


def test_scene_signature_distinguishes_real_composition_changes():
    a = Scene.model_validate(scene("a", "这是一段足够长的旁白内容用于测试。", [layer()]))
    b = Scene.model_validate(scene("b", "这是一段足够长的旁白内容用于测试。", [chart_layer("loss")]))
    c = Scene.model_validate(scene("c", "这是一段足够长的旁白内容用于测试。", [diagram_layer("flow")]))
    assert len({scene_signature(item) for item in (a, b, c)}) == 3


def test_script_validation_rejects_repetitive_visuals_and_accepts_three():
    repetitive = Film.model_validate(film(
        long_scenes=[scene("one", "矩阵把单位正方形变成平行四边形，面积按行列式缩放。", [layer()]),
                     scene("two", "矩阵的列向量说明基向量去了哪里，形状随之改变。", [layer()]),
                     scene("three", "行列式为零时整个平面塌缩，信息无法还原。", [layer()])],
        short_scenes=[scene("s1", "矩阵改变的是整个空间，而不只是一个点。", [layer()]),
                      scene("s2", "矩阵的列向量说明基向量去了哪里。", [layer()]),
                      scene("s3", "行列式为零时整个平面会塌缩成一条线。", [layer()])]))
    from movelyth.models import Research

    research = Research.model_validate(research_payload())
    with pytest.raises(ValueError, match="三种"):
        validate_script(repetitive, research, 12, 10)
    varied = Film.model_validate(film())
    warnings = validate_script(varied, research, 12, 10)
    assert isinstance(warnings, list)


def test_timeline_checks_catch_overlap_and_out_of_range_actions():
    cut = {"scenes": [{"id": "a", "frames": 30, "captions": [
        {"start": 0.1, "end": 0.6, "text": "第一句"}, {"start": 0.5, "end": 0.9, "text": "交叠"}],
        "actions_resolved": [{"from": 0.9, "to": 1.4}]}]}
    problems = validate_cut_timeline(cut, 30)
    assert any("交叠" in problem for problem in problems)
    assert any("动画区间" in problem for problem in problems)
    negative = {"scenes": [{"id": "b", "frames": 0, "captions": [], "actions_resolved": []}]}
    assert validate_cut_timeline(negative, 30)


def test_local_data_files_bind_chart_series_and_reject_unknown_assets(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "loss_demo.json").write_text(json.dumps({"label": "误差", "unit": "%", "axis": "轮次",
                                                     "values": [0.9, 0.6, 0.3]}), encoding="utf-8")
    scenes = [{"id": "chart", "layers": [chart_layer("loss", values=[], data_ref="loss_demo",
                                                     series=[], source_note="")]}]
    resolved = resolve_data_layers(scenes, data, assets=[])
    assert resolved[0]["layers"][0]["series"][0]["values"] == [0.9, 0.6, 0.3]
    assert resolved[0]["layers"][0]["source_note"].startswith("本地数据")
    image = [{"id": "img", "layers": [layer("pic", type="image", procedural="", data_ref="missing_asset")]}]
    with pytest.raises(ValueError, match="受控素材"):
        resolve_data_layers(image, data, assets=["svd-1.png"])


def test_csv_data_is_read_with_labels_and_bounded(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "runs.csv").write_text("轮次,训练,验证\n1,0.9,1.0\n2,0.7,0.85\n3,0.5,0.7\n", encoding="utf-8")
    scenes = [{"id": "chart", "layers": [chart_layer("loss", values=[], data_ref="runs", series=[])]}]
    resolved = resolve_data_layers(scenes, data, assets=[])
    series = resolved[0]["layers"][0]["series"]
    assert [entry["label"] for entry in series] == ["轮次", "训练", "验证"]
    assert series[1]["values"] == [0.9, 0.7, 0.5]
    (data / "single.csv").write_text("0.9\n0.6\n0.3\n", encoding="utf-8")
    scenes = [{"id": "chart", "layers": [chart_layer("loss", values=[], data_ref="single", series=[])]}]
    resolved = resolve_data_layers(scenes, data, assets=[])
    assert resolved[0]["layers"][0]["series"][0]["values"] == [0.9, 0.6, 0.3]
    (data / "bad.csv").write_text("a,b\nx,y\n", encoding="utf-8")
    scenes = [{"id": "chart", "layers": [chart_layer("loss", values=[], data_ref="bad", series=[])]}]
    with pytest.raises(ValueError):
        resolve_data_layers(scenes, data, assets=[])
    (data / "big.csv").write_text("v\n" + "\n".join(str(i) for i in range(80)), encoding="utf-8")
    scenes = [{"id": "chart", "layers": [chart_layer("loss", values=[], data_ref="big", series=[])]}]
    with pytest.raises(ValueError, match="2–60"):
        resolve_data_layers(scenes, data, assets=[])


def test_generated_renderer_contract_matches_committed_files(tmp_path):
    from movelyth.scenedsl import write_renderer_contracts

    files = write_renderer_contracts(tmp_path)
    for generated in files:
        committed = ROOT / "studio" / "src" / "generated" / generated.name
        assert committed.is_file(), f"缺少提交的生成文件：{committed}"
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
            generated.read_text(encoding="utf-8")), f"{committed.name} 与 Python 契约不一致，请重新生成"


def test_typescript_and_python_enums_do_not_drift():
    source = (ROOT / "studio" / "src" / "types.ts").read_text(encoding="utf-8")

    def union(name: str) -> set[str]:
        match = re.search(rf"export type {name} = ([^;]+);", source)
        assert match, name
        return set(re.findall(r"'([^']+)'", match.group(1)))

    assert union("LayerKind") == set(__import__("movelyth.models", fromlist=["LayerKind"]).LayerKind.__args__)
    assert union("ActionKind") == set(__import__("movelyth.models", fromlist=["ActionKind"]).ActionKind.__args__)
    assert union("VisualKind") == set(VisualKind.__args__)
    assert union("Region") == set(__import__("movelyth.models", fromlist=["Region"]).Region.__args__)



