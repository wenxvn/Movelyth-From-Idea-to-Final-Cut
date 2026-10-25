"""Real Remotion still smoke test for the composable Scene DSL.

This renders actual frames with Chrome.  It is skipped when the Node renderer
or browser is unavailable, and it never produces a deliverable video.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from movelyth.media import image_layers
from movelyth.pipeline import browser as chrome
from tests.factories import chart_layer, diagram_layer, layer

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.slow


def available() -> bool:
    return (bool(shutil.which("node")) and chrome() is not None
            and (ROOT / "studio/node_modules/@remotion/renderer/package.json").is_file())


def scene(scene_id, layout, layers, heading, narration):
    return {
        "id": scene_id, "heading": heading, "narration": narration, "visual": "matrix",
        "labels": ["观察", "结构"], "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0,
        "layout": layout, "beats": [], "beat_times": [], "actions": [],
        "actions_resolved": [], "visual_intent": "测试构图与图层组合", "frames": 90,
        "captions": [{"start": 0.3, "end": 1.6, "text": narration[:12]}],
        "caption_timing": "tts-word-boundaries", "layout_warnings": [], "duration": 3.0,
        "layers": layers,
    }


@pytest.mark.skipif(not available(), reason="需要 Node 与已安装的 Remotion 渲染器")
def test_composable_layers_render_real_distinct_frames(tmp_path):
    assets, _paths, _report = image_layers(tmp_path / "assets")
    assert "svd-1.png" in assets
    scenes = [
        scene("matrix", "diagram", [
            layer("grid", region="main", procedural="matrix"),
            layer("caption", type="text", region="annotation", procedural="", text="单位正方形变成平行四边形"),
            layer("formula", type="math", region="side", procedural="", text="det A = a·d − b·c", emphasis=2),
        ], "矩阵改变空间", "矩阵把单位正方形变成平行四边形，面积按行列式缩放。"),
        scene("chart", "compare", [
            chart_layer("loss", [0.92, 0.78, 0.61, 0.44, 0.3], region="main"),
            chart_layer("steps", [1.0, 0.9, 0.75, 0.55, 0.4], region="side"),
            layer("note", type="text", region="annotation", procedural="", text="误差逐轮下降"),
        ], "损失曲线", "误差每一轮都在下降，最后趋于稳定。"),
        scene("flow", "immersive", [
            diagram_layer("flow", region="main"),
            layer("head", type="text", region="top", procedural="", text="一条消息的旅程", emphasis=3),
            layer("arrow", type="shape", region="annotation", procedural="", shape="arrow",
                  points=[120, 560, 880, 560]),
        ], "消息如何到达", "请求经过多个节点，最终到达服务器并返回。"),
        scene("image", "diagram", [
            layer("pic", type="image", region="main", procedural="", data_ref="svd_12", text="真实 SVD 重建"),
            layer("box", type="shape", region="side", procedural="", shape="rect",
                  points=[120, 120, 760, 420], color="amber"),
            layer("label", type="text", region="bottom", procedural="", text="低秩近似保留主要结构"),
        ], "低秩重建", "保留少数奇异值，图像的主要结构仍然可以辨认。"),
    ]
    props = {"title": "图层组合静帧测试", "episode": "TEST-GALLERY", "fps": 30, "scenes": scenes,
             "sources": [{"label": "本地程序演示", "url": "https://example.com/demo"}],
             "layers": assets, "cover": False, "style": "tech", "schema_version": 1}
    cuts = [{"name": "landscape", "composition": "Landscape", "props": props,
             "output": str(tmp_path / "render" / "landscape")},
            {"name": "portrait", "composition": "Portrait", "props": props,
             "output": str(tmp_path / "render" / "portrait")}]
    spec = {"cuts": cuts, "assets": str(tmp_path / "assets"), "browser": chrome(), "concurrency": 1,
            "result": str(tmp_path / "result.json"), "version": "smoke", "stillsOnly": True, "scale": 0.5}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([shutil.which("node") or "node", str(ROOT / "studio" / "render.mjs"), str(spec_path)],
                          cwd=ROOT / "studio", capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    for name in ("landscape", "portrait"):
        cut = result[name]
        assert len(cut["stills"]) == len(scenes)
        digests = set()
        for still in cut["stills"]:
            path = Path(still)
            assert path.is_file() and path.stat().st_size > 5_000, f"静帧过小：{path}"
            digests.add(path.read_bytes()[:2048])
        assert len(digests) == len(scenes), f"{name} 不同镜头应产生不同的真实画面"
        assert Path(cut["cover"]).stat().st_size > 20_000
