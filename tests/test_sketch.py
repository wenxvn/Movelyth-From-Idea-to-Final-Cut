"""S2-08: stable hand-drawn annotations — seeded geometry, deterministic frames."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from movelyth.models import Scene
from movelyth.pipeline import browser as chrome
from movelyth.scenedsl import normalize_scene, regions
from movelyth.sketch import KINDS, path_points, path_string, reveal, sketch_problems
from tests.factories import chart_layer, layer, scene

ROOT = Path(__file__).parents[1]
NL = chr(10)
BOX = {"x": 660, "y": 150, "w": 1164, "h": 730}


def scene_model(**overrides) -> Scene:
    return Scene.model_validate(scene(**overrides))


# -------------------------------------------------------------------- geometry

def test_every_kind_produces_a_bounded_path():
    for kind in KINDS:
        points = path_points(BOX, kind, 7)
        assert len(points) >= 24
        assert all(-60 <= px <= BOX["x"] + BOX["w"] + 60 for px, _ in points)
        assert all(-60 <= py <= BOX["y"] + BOX["h"] + 60 for _, py in points)
        assert path_string(BOX, kind, 7).startswith("M")


def test_the_same_seed_produces_identical_geometry():
    first = path_points(BOX, "circle", 11)
    assert first == path_points(BOX, "circle", 11)
    assert first != path_points(BOX, "circle", 12)


def test_the_geometry_does_not_depend_on_time():
    """Only the reveal changes with time; the path itself must be time-independent."""
    before = path_string(BOX, "circle", 7)
    for progress in (0.0, 0.25, 0.5, 0.99):
        assert reveal(progress, 0.1, 0.6) >= 0
        assert path_string(BOX, "circle", 7) == before


def test_reveal_is_a_clamped_ramp():
    assert reveal(0.0, 0.1, 0.6) == 0.0
    assert reveal(0.35, 0.1, 0.6) == pytest.approx(0.5)
    assert reveal(1.0, 0.1, 0.6) == 1.0
    assert reveal(0.5, 0.6, 0.6) == 0.0


def test_the_jitter_is_small_enough_to_stay_on_the_shape():
    points = path_points(BOX, "underline", 7)
    ys = [py for _, py in points]
    baseline = BOX["y"] + BOX["h"] * 0.96
    assert max(abs(value - baseline) for value in ys) <= 3.0


# ------------------------------------------------------------------ validation

def test_an_annotation_must_target_a_real_layer():
    model = scene_model(sketches=[{"id": "circle1", "target": "ghost"}])
    problems = sketch_problems(model, boxes=regions("landscape", "diagram"))
    assert any("不存在的图层" in problem for problem in problems)


def test_duplicate_annotation_ids_are_rejected():
    model = scene_model(sketches=[{"id": "a1", "target": "visual"},
                                  {"id": "a1", "target": "visual", "kind": "box"}])
    assert any("重复" in problem for problem in sketch_problems(model))


def test_an_unknown_kind_is_rejected_by_the_model():
    with pytest.raises(ValueError, match="sketch.kind"):
        scene_model(sketches=[{"id": "a1", "target": "visual", "kind": "sparkle"}])


def test_timing_outside_zero_to_one_is_reported():
    model = scene_model(sketches=[{"id": "a1", "target": "visual", "start": "1.4"}])
    assert any("越界" in problem for problem in sketch_problems(model))


def test_an_annotation_that_would_reach_the_captions_is_reported():
    """The standard regions stop above the caption band; this is the safety net."""
    model = scene_model(layers=[layer("note", type="text", region="bottom", text="注释")],
                        sketches=[{"id": "a1", "target": "note", "kind": "underline"}])
    boxes = dict(regions("landscape", "diagram"))
    boxes["bottom"] = {"x": 96, "y": 860, "w": 520, "h": 80}   # reaches into the band
    assert any("字幕带" in problem for problem in sketch_problems(model, boxes=boxes))


def test_normalized_scene_keeps_the_sketches():
    model = scene_model(sketches=[{"id": "a1", "target": "visual", "kind": "circle", "seed": 5}])
    normalized = normalize_scene(model, duration=4.0)
    assert normalized["sketches"][0]["seed"] == 5


# ------------------------------------------------------------- renderer parity

def _overlay_geometry(box: dict, seed: int) -> dict:
    """Compute the geometry with the renderer's own TSX, via its own esbuild."""
    studio = ROOT / "studio"
    if not (studio / "node_modules" / "esbuild").is_dir():
        pytest.skip("studio/node_modules 里没有 esbuild")
    script = [
        "import * as esbuild from 'esbuild';",
        "const result = await esbuild.build({",
        "  entryPoints: ['src/components/SketchOverlay.tsx'], bundle: true, format: 'esm',",
        "  jsx: 'automatic', write: false,",
        "  platform: 'node', logLevel: 'silent',",
        "});",
        "const code = result.outputFiles[0].text;",
        "const module = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));",
        "const box = JSON.parse(process.argv[1]);",
        "const out = {};",
        "for (const kind of ['circle', 'underline', 'highlight', 'bracket', 'box']) {",
        "  out[kind] = module.pathPoints(box, kind, Number(process.argv[2]));",
        "}",
        "console.log(JSON.stringify(out));",
    ]
    proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", NL.join(script),
                           json.dumps(box), str(seed)],
                          cwd=studio, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout)

@pytest.mark.skipif(not shutil.which("node"), reason="需要 node 运行 TSX 源码")
def test_python_and_typescript_geometry_agree():
    expected = _overlay_geometry(BOX, 7)
    for kind in KINDS:
        assert path_points(BOX, kind, 7) == expected[kind], f"{kind} 的几何与渲染端不一致"

# ------------------------------------------------------------ deterministic frames

def _available() -> bool:
    return (bool(shutil.which("node")) and chrome() is not None
            and (ROOT / "studio/node_modules/@remotion/renderer/package.json").is_file())


def _props(seed: int = 7) -> dict:
    raw = {
        "id": "paper", "heading": "纸面证据", "narration": "原文写着矩阵的列就是基向量的像。",
        "visual": "matrix", "labels": ["观察"], "matrix": [1, 0, 0, 1], "color": "cyan",
        "source_index": 0, "layout": "diagram",
        "layers": [layer("quote", type="text", region="main", text="矩阵的列是基向量的像",
                         source_note="示例课程"),
                   chart_layer("chart", [0.9, 0.7, 0.5], region="side")],
        "sketches": [{"id": "ring", "target": "quote", "kind": "circle", "seed": seed,
                      "start": "0.1", "end": "0.5"}],
        "actions": [],
    }
    normalized = normalize_scene(Scene.model_validate(raw), duration=4.0)
    normalized["frames"] = 120
    normalized["captions"] = [{"start": 0.2, "end": 3.0, "text": "原文写着矩阵的列就是基向量的像"}]
    return {"title": "纸面标注", "episode": "TEST-SKETCH", "fps": 30, "scenes": [normalized],
            "sources": [{"label": "本地", "url": "https://example.com"}], "layers": [],
            "cover": False, "coverCaption": "", "style": "documentary", "schema_version": 2}


def _render(tmp_path: Path, name: str, *, seed: int = 7) -> Path:
    output = tmp_path / name
    spec = {"cuts": [{"name": "long", "composition": "Landscape", "props": _props(seed),
                      "output": str(output)}],
            "assets": str(tmp_path / "assets"), "browser": chrome(), "concurrency": 1,
            "result": str(tmp_path / f"{name}.json"), "version": "sketch-smoke",
            "stillsOnly": True, "scale": 0.5}
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}-spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([shutil.which("node") or "node", str(ROOT / "studio" / "render.mjs"),
                           str(path)], cwd=ROOT / "studio", capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-1500:]
    return Path(json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))["long"]["stills"][0])


@pytest.mark.skipif(not _available(), reason="需要 Node 与已安装的 Remotion 渲染器")
def test_the_same_frame_renders_identically_twice(tmp_path):
    first = _render(tmp_path, "run-a")
    second = _render(tmp_path, "run-b")
    assert first.read_bytes() == second.read_bytes(), "同一帧两次渲染必须逐字节一致"


@pytest.mark.skipif(not _available(), reason="需要 Node 与已安装的 Remotion 渲染器")
def test_a_different_seed_draws_a_different_stroke(tmp_path):
    seven = np.asarray(Image.open(_render(tmp_path, "seed-7", seed=7)).convert("L"), dtype=float)
    nine = np.asarray(Image.open(_render(tmp_path, "seed-9", seed=9)).convert("L"), dtype=float)
    assert float(np.abs(seven - nine).mean()) > 0.01, "换 seed 应该画出不同的笔触"
