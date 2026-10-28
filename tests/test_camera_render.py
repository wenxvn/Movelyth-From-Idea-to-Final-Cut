"""S2-06 real-media check: a camera plan must change the rendered frame.

The Python tests prove the plan's arithmetic; this renders the same scene twice with
the real renderer — once with a focus keyframe and once without — and compares the
actual pixels.  A plan that changes nothing on screen is not a feature.
"""
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
from movelyth.scenedsl import normalize_scene
from tests.factories import chart_layer, layer

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.slow


def available() -> bool:
    return (bool(shutil.which("node")) and chrome() is not None
            and (ROOT / "studio/node_modules/@remotion/renderer/package.json").is_file())


def props(*, with_focus: bool) -> dict:
    raw = {
        "id": "focus", "heading": "损失曲线", "narration": "误差每一轮都在下降，最后趋于稳定。",
        "visual": "matrix", "labels": ["观察"], "matrix": [1, 0, 0, 1], "color": "cyan",
        "source_index": 0, "layout": "diagram", "beats": [], "layers": [
            chart_layer("loss", [0.92, 0.78, 0.61, 0.44, 0.3], annotations=[{"x": 3, "text": "拐点"}]),
            layer("note", type="text", region="annotation", procedural="", text="误差逐轮下降"),
        ],
        "actions": [], "visual_intent": "把注意力带到拐点",
        "events": ([{"id": "focus", "kind": "emphasis", "target": "loss",
                     "anchor": {"kind": "fraction", "fraction": 0.1}}] if with_focus else []),
    }
    normalized = normalize_scene(Scene.model_validate(raw), duration=4.0)
    normalized["frames"] = 120
    normalized["captions"] = [{"start": 0.2, "end": 2.5, "text": "误差每一轮都在下降"}]
    return {"title": "相机计划对照", "episode": "TEST-CAMERA", "fps": 30, "scenes": [normalized],
            "sources": [{"label": "本地", "url": "https://example.com"}], "layers": [],
            "cover": False, "coverCaption": "", "style": "tech", "schema_version": 2}


def render(tmp_path: Path, name: str, *, with_focus: bool) -> Path:
    output = tmp_path / name
    spec = {"cuts": [{"name": "long", "composition": "Landscape", "props": props(with_focus=with_focus),
                      "output": str(output)}],
            "assets": str(tmp_path / "assets"), "browser": chrome(), "concurrency": 1,
            "result": str(tmp_path / f"{name}-result.json"), "version": "camera-smoke",
            "stillsOnly": True, "scale": 0.5}
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    spec_path = tmp_path / f"{name}-spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([shutil.which("node") or "node", str(ROOT / "studio" / "render.mjs"),
                           str(spec_path)], cwd=ROOT / "studio", capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    result = json.loads((tmp_path / f"{name}-result.json").read_text(encoding="utf-8"))
    return Path(result["long"]["stills"][0])


@pytest.mark.skipif(not available(), reason="需要 Node 与已安装的 Remotion 渲染器")
def test_a_focus_keyframe_changes_the_rendered_pixels(tmp_path):
    plain = np.asarray(Image.open(render(tmp_path, "plain", with_focus=False)).convert("L"), dtype=float)
    focused = np.asarray(Image.open(render(tmp_path, "focused", with_focus=True)).convert("L"), dtype=float)
    assert plain.shape == focused.shape
    difference = float(np.abs(plain - focused).mean())
    assert difference > 3.0, f"相机计划没有产生可见变化（平均像素差 {difference:.2f}）"
    # Both frames must still contain readable content, not an empty crop.
    assert plain.mean() > 10 and focused.mean() > 10
