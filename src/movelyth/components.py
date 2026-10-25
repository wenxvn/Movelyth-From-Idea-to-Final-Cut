"""Component registry metadata: one place describing what each layer can honestly show.

The renderer implements these components; this module is the reviewable contract
of their purpose, required fields, limits and portrait/landscape behaviour.  The
``movelyth components`` command prints it, and tests assert every declared kind is
implemented on both sides.
"""
from __future__ import annotations

from .models import LayerKind

COMPONENTS: dict[str, dict] = {
    "text": {
        "purpose": "短文本、结论句、注解",
        "required": ["text"],
        "limits": "≤120 字；最小 22px；超长会被拒绝或缩小",
        "regions": ["main", "top", "side", "bottom", "annotation"],
        "portrait": "按区域宽度自动换行，字号上限略放大",
        "sample": {"id": "note", "type": "text", "region": "annotation", "text": "误差逐轮下降"},
    },
    "math": {
        "purpose": "公式、矩阵、带上下标的表达式",
        "required": ["text"],
        "limits": "≤120 字；支持 `^`/`_` 与 `\\n` 换行；最小 34px；不做符号求解",
        "regions": ["main", "top", "side", "bottom", "annotation"],
        "portrait": "单列居中，长公式会缩小但仍保留行结构",
        "sample": {"id": "formula", "type": "math", "region": "main",
                   "text": "θ ← θ − η · ∇L(θ)", "emphasis": 2},
    },
    "shape": {
        "purpose": "点、折线、矩形、圆、箭头、多边形、括号",
        "required": ["shape", "points"],
        "limits": "坐标 0–1000 × 0–640，最多 32 个点；line 按全部顶点连线，connect=true 加起点与箭头",
        "regions": ["main", "top", "side", "bottom", "annotation"],
        "portrait": "同一坐标系内缩放，注意竖版可显示宽度更小",
        "sample": {"id": "arrow", "type": "shape", "region": "main", "shape": "arrow",
                   "points": [180, 520, 820, 520]},
    },
    "chart": {
        "purpose": "折线/柱状/散点，展示真实或明确标注为示意的数据",
        "required": ["chart", "series 或 data_ref"],
        "limits": "每条 2–60 个有限数，最多 4 条；>24 个点会警告；必须写 unit/axis/source_note",
        "regions": ["main", "side(仅 compare)"],
        "portrait": "坐标轴与刻度字号随区域放大，首末值标签自动避让",
        "sample": {"id": "loss", "type": "chart", "region": "main", "chart": "line",
                   "series": [{"label": "误差", "values": [0.9, 0.6, 0.3], "unit": ""}],
                   "axis": "更新轮次", "source_note": "示意数据"},
    },
    "diagram": {
        "purpose": "有向节点图：流程、分层、状态转移",
        "required": ["nodes", "edges"],
        "limits": "2–12 个节点，坐标 0–1000 × 0–640；连线必须引用已存在节点；是结构示意，不是实测拓扑",
        "regions": ["main", "side(仅 compare)"],
        "portrait": "节点改为圆角方框，字号放大，避免文字被挤在圆内",
        "sample": {"id": "flow", "type": "diagram", "region": "main",
                   "nodes": [{"id": "a", "label": "客户端", "x": 200, "y": 300},
                             {"id": "b", "label": "服务器", "x": 800, "y": 300}],
                   "edges": [{"source": "a", "target": "b", "label": "请求"}]},
    },
    "timeline": {
        "purpose": "阶段/里程碑序列，当前阶段随旁白高亮",
        "required": ["steps"],
        "limits": "2–6 个阶段，每个 ≤24 字",
        "regions": ["main", "side(仅 compare)"],
        "portrait": "标签上下交错排列，字号放大",
        "sample": {"id": "stages", "type": "timeline", "region": "main",
                   "steps": ["封装", "路由", "排队", "解封装"]},
    },
    "image": {
        "purpose": "已登记并核验授权的本地图片",
        "required": ["data_ref"],
        "limits": "只能引用 `movelyth asset-add` 登记过的素材或内置 svd_1/4/12/32；禁止远程 URL",
        "regions": ["main", "side(仅 compare)", "bottom"],
        "portrait": "contain 缩放，不会溢出到字幕区",
        "sample": {"id": "pic", "type": "image", "region": "main", "data_ref": "svd_12"},
    },
    "procedural": {
        "purpose": "原有七类程序动画，作为可组合图层之一",
        "required": ["procedural"],
        "limits": "matrix 系数绝对值 ≤4；network/wave/orbit 是原理示意，不能称为实测",
        "regions": ["main", "full"],
        "portrait": "按区域等比缩放，point 云与网络会自动收拢",
        "sample": {"id": "visual", "type": "procedural", "region": "main", "procedural": "matrix"},
    },
}


def registry() -> dict:
    return {"schema_version": 1, "components": COMPONENTS}


def missing_kinds() -> list[str]:
    """Kinds declared in the DSL but not documented here."""
    return sorted(set(LayerKind.__args__) - set(COMPONENTS))


def unknown_kinds() -> list[str]:
    return sorted(set(COMPONENTS) - set(LayerKind.__args__))
