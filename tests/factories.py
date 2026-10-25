"""Reusable, fully specified Scene DSL payloads for offline tests."""
from __future__ import annotations


def layer(layer_id: str = "visual", **overrides) -> dict:
    value = {
        "id": layer_id, "type": "procedural", "region": "main", "text": "", "shape": "rect",
        "chart": "line", "procedural": "matrix", "series": [], "nodes": [], "edges": [], "steps": [],
        "points": [], "data_ref": "", "unit": "", "axis": "", "source_note": "", "color": "cyan",
        "emphasis": 1, "connect": False,
    }
    value.update(overrides)
    return value


def chart_layer(layer_id: str = "loss", values: list[float] | None = None, **overrides) -> dict:
    value = layer(layer_id, type="chart", procedural="", chart="line", source_note="示意")
    value["series"] = overrides.pop(
        "series", [{"label": "损失", "values": values if values is not None else [0.9, 0.7, 0.5, 0.3],
                    "unit": "%"}])
    value.update(overrides)
    return value


def diagram_layer(layer_id: str = "flow", **overrides) -> dict:
    return layer(layer_id, type="diagram", procedural="", nodes=[
        {"id": "client", "label": "客户端", "x": 180, "y": 220},
        {"id": "server", "label": "服务器", "x": 760, "y": 220},
    ], edges=[{"source": "client", "target": "server", "label": "请求"}],
        steps=["建立连接", "发送请求", "返回结果"], **overrides)


def scene(scene_id: str = "one", narration: str = "这是一个用于测试的旁白句子，说明画面的真实含义。",
          layers: list[dict] | None = None, **overrides) -> dict:
    value = {
        "id": scene_id, "heading": "测试镜头", "narration": narration, "visual": "matrix",
        "labels": ["观察"], "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0,
        "layout": "diagram", "beats": [], "layers": layers if layers is not None else [layer()],
        "actions": [], "visual_intent": "展示一个真实的数学关系，而不是装饰",
    }
    value.update(overrides)
    return value


def film(long_scenes: list[dict] | None = None, short_scenes: list[dict] | None = None,
         style: str = "tech") -> dict:
    long_scenes = long_scenes or [
        scene("one", "矩阵把单位正方形变成平行四边形，面积按行列式缩放。", [layer()]),
        scene("two", "把向量分解成两个方向的分量，就能看清变换做了什么。",
              [layer("vec", procedural="vectors")]),
        scene("three", "沿着投影方向取最近的落点，残差就是丢掉的那部分。",
              [layer("proj", procedural="projection")]),
    ]
    short_scenes = short_scenes or [
        scene("s1", "矩阵改变的是整个空间，而不只是一个点。", [layer()]),
        scene("s2", "分解成方向，就能预测变换结果。", [layer("vec", procedural="vectors")]),
        scene("s3", "投影保留最接近的那一部分信息。", [layer("proj", procedural="projection")]),
    ]
    return {"title": "测试影片", "thesis": "用可组合图层讲清一个具体问题", "long": {
        "title": "横版测试", "description": "这是横版发布说明，用于离线测试，不代表真实发布内容。",
        "tags": ["测试", "科普"], "scenes": long_scenes, "schema_version": 1, "style": style,
        "title_candidates": ["横版候选标题一", "横版候选标题二"], "cover_caption": "横版封面文案",
    }, "short": {
        "title": "竖版测试", "description": "这是竖版发布说明，用于离线测试，不代表真实发布内容。",
        "tags": ["测试", "科普"], "scenes": short_scenes, "schema_version": 1, "style": style,
        "title_candidates": ["竖版候选标题一"], "cover_caption": "竖版封面文案",
    }}


def research_payload() -> dict:
    return {
        "title": "测试选题", "question": "矩阵如何改变空间？", "angle": "从单位正方形和基向量出发解释线性变换。",
        "facts": ["矩阵的列是基向量的像", "行列式表示面积缩放", "投影保留方向上的分量"],
        "sources": [{"label": "示例课程", "url": "https://example.com/linear-algebra",
                     "supports": "支持矩阵列向量与行列式的解释"}],
        "cautions": ["这是测试用研究记录"], "next_ideas": ["下一个选题", "再下一个选题"],
        "claims": [{"claim_id": "c1", "statement": "矩阵的列是基向量的像", "source_index": 0,
                    "excerpt": "columns are images of basis vectors", "scope": "established"}],
    }


def review_payload(passed: bool = True) -> dict:
    return {"passed": passed, "issues": [] if passed else ["镜头 one 的画面与口播不符"],
            "strengths": ["叙事清晰"], "warnings": [], "findings": [] if passed else [
                {"category": "visual_mismatch", "scene_id": "one", "detail": "画面没有体现面积变化"}]}
