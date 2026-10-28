"""S2-07: shared-object continuity and real geometry morphs."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from movelyth.continuity import (
    continuity_report,
    formula_correspondence,
    formula_tokens,
    interpolate,
    morph_plan,
    morph_problems,
    subject_states,
)
from movelyth.models import Scene
from movelyth.pipeline import browser as chrome
from movelyth.scenedsl import normalize_scene
from tests.factories import chart_layer, layer, scene

ROOT = Path(__file__).parents[1]


def scene_model(scene_id="one", **overrides) -> Scene:
    return Scene.model_validate(scene(scene_id, **overrides))


# ------------------------------------------------------------------ continuity

def test_a_subject_that_keeps_its_colour_is_continuous():
    scenes = [scene_model("one", layers=[layer("card", type="text", text="均值",
                                               subject_id="mean", color="cyan")]),
              scene_model("two", layers=[layer("point", procedural="vectors",
                                               subject_id="mean", color="cyan")])]
    report = continuity_report(scenes)
    assert report["problems"] == []
    assert report["shared"][0]["subject_id"] == "mean"
    assert report["shared"][0]["scenes"] == ["one", "two"]


def test_a_subject_that_changes_colour_is_a_continuity_defect():
    scenes = [scene_model("one", layers=[layer("card", type="text", text="均值",
                                               subject_id="mean", color="cyan")]),
              scene_model("two", layers=[layer("point", procedural="vectors",
                                               subject_id="mean", color="coral")])]
    problems = continuity_report(scenes)["problems"]
    assert any("换了颜色" in problem for problem in problems)


def test_a_state_that_does_not_line_up_is_reported():
    scenes = [scene_model("one", layers=[layer("card", type="text", text="均值",
                                               subject_id="mean", state_before="4",
                                               state_after="10")]),
              scene_model("two", layers=[layer("point", procedural="vectors",
                                               subject_id="mean", state_before="7")])]
    problems = continuity_report(scenes)["problems"]
    assert any("之后是“10”" in problem and "开始时是“7”" in problem for problem in problems)


def test_subject_states_are_listed_in_scene_order():
    scenes = [scene_model("a", layers=[layer("x", type="text", text="一", subject_id="s")]),
              scene_model("b", layers=[layer("y", type="text", text="二", subject_id="s")])]
    states = subject_states(scenes)
    assert [item["scene"] for item in states["s"]] == ["a", "b"]


# ----------------------------------------------------------------------- morph

def morph_layer(points, **overrides) -> Scene:
    return scene_model("one", layers=[layer("poly", type="shape", shape="polygon", points=points)],
                       actions=[{"target": "poly", "kind": "morph", "start": "0.1", "end": "0.5",
                                 **overrides}])


def test_a_geometry_morph_with_the_same_topology_is_accepted():
    model = morph_layer([100, 100, 300, 100, 300, 300, 100, 300],
                        morph_mode="geometry", target_points=[400, 80, 700, 120, 650, 400, 420, 360])
    action = model.actions[0]
    plan = morph_plan(model.layers[0], action)
    assert plan["ok"] is True and plan["mode"] == "geometry" and plan["vertices"] == 4
    assert morph_problems([model]) == []


def test_a_morph_with_a_different_vertex_count_is_refused():
    model = morph_layer([100, 100, 300, 100, 300, 300, 100, 300],
                        morph_mode="geometry", target_points=[400, 80, 700, 120])
    problems = morph_problems([model])
    assert problems and "顶点数不同" in problems[0]


def test_a_geometry_morph_on_a_non_shape_layer_is_refused():
    model = scene_model("one", layers=[chart_layer("loss", [0.9, 0.5, 0.3])],
                        actions=[{"target": "loss", "kind": "morph", "start": "0.1", "end": "0.4",
                                  "morph_mode": "geometry", "target_points": [1, 1]}])
    problems = morph_problems([model])
    assert problems and "不支持几何形变" in problems[0]


def test_the_default_morph_keeps_the_old_crossfade_semantics():
    model = morph_layer([100, 100, 300, 100, 300, 300])
    plan = morph_plan(model.layers[0], model.actions[0])
    assert plan["mode"] == "crossfade" and plan["ok"] is True
    assert "不是几何形变" in plan["note"]


def test_interpolation_hits_the_endpoints_exactly():
    source = [0.0, 0.0, 100.0, 0.0, 100.0, 100.0]
    target = [10.0, 20.0, 200.0, 0.0, 200.0, 300.0]
    assert interpolate(source, target, 0.0) == source
    assert interpolate(source, target, 1.0) == target
    middle = interpolate(source, target, 0.5)
    assert middle[0] == 5.0 and middle[4] == 150.0


def test_the_resolved_action_carries_the_morph_target():
    model = morph_layer([0, 0, 100, 0, 100, 100], morph_mode="geometry",
                        target_points=[0, 0, 200, 0, 200, 200])
    resolved = normalize_scene(model, duration=4.0)["actions_resolved"][0]
    assert resolved["morph_mode"] == "geometry"
    assert resolved["target_points"] == [0, 0, 200, 0, 200, 200]


# --------------------------------------------------------------------- formula

def test_formula_tokens_and_correspondence():
    before = "L = (a + b) / 2"
    after = "L = (a + c) / 2"
    assert "=" in formula_tokens(before)
    result = formula_correspondence(before, after)
    assert result["shared"] and result["kept_ratio"] > 0.5
    assert result["note"].startswith("只比较符号")


# ----------------------------------------------------------------- real frames

def _available() -> bool:
    return (bool(shutil.which("node")) and chrome() is not None
            and (ROOT / "studio/node_modules/@remotion/renderer/package.json").is_file())


def _props(morph_mode: str) -> dict:
    raw = {
        "id": "morph", "heading": "形状变化", "narration": "正方形被拉成一条长长的平行四边形。",
        "visual": "matrix", "labels": ["观察"], "matrix": [1, 0, 0, 1], "color": "cyan",
        "source_index": 0, "layout": "immersive",
        "layers": [layer("poly", type="shape", shape="polygon", region="main",
                         points=[700, 300, 900, 300, 900, 500, 700, 500])],
        "actions": [{"target": "poly", "kind": "morph", "start": "0.05", "end": "0.95",
                     "morph_mode": morph_mode,
                     "target_points": [200, 380, 800, 380, 800, 460, 200, 460]}],
    }
    normalized = normalize_scene(Scene.model_validate(raw), duration=4.0)
    normalized["frames"] = 120
    normalized["captions"] = [{"start": 0.2, "end": 3.0, "text": "正方形被拉成平行四边形"}]
    return {"title": "形变对照", "episode": "TEST-MORPH", "fps": 30, "scenes": [normalized],
            "sources": [{"label": "本地", "url": "https://example.com"}], "layers": [],
            "cover": False, "coverCaption": "", "style": "tech", "schema_version": 2}


def _render(tmp_path: Path, name: str, mode: str) -> Path:
    output = tmp_path / name
    spec = {"cuts": [{"name": "long", "composition": "Landscape", "props": _props(mode),
                      "output": str(output)}],
            "assets": str(tmp_path / "assets"), "browser": chrome(), "concurrency": 1,
            "result": str(tmp_path / f"{name}.json"), "version": "morph-smoke",
            "stillsOnly": True, "scale": 0.5}
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}-spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([shutil.which("node") or "node", str(ROOT / "studio" / "render.mjs"),
                           str(path)], cwd=ROOT / "studio", capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    return Path(json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))["long"]["stills"][0])


@pytest.mark.slow
@pytest.mark.skipif(not _available(), reason="需要 Node 与已安装的 Remotion 渲染器")
def test_a_geometry_morph_changes_the_rendered_shape(tmp_path):
    plain = np.asarray(Image.open(_render(tmp_path, "crossfade", "crossfade")).convert("L"), dtype=float)
    morphed = np.asarray(Image.open(_render(tmp_path, "geometry", "geometry")).convert("L"), dtype=float)
    assert plain.shape == morphed.shape
    difference = np.abs(plain - morphed)
    # The crossfade keeps the original square; the geometry morph stretches it into a
    # wide bar, so a real fraction of the frame must change, not just antialiasing.
    changed = float((difference > 20).mean())
    assert changed > 0.005, f"只有 {changed:.3%} 的像素发生变化，形变没有真正生效"
    assert float(difference.mean()) > 0.5
