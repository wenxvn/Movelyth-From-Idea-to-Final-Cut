"""Capability routing: what a topic needs versus what this pipeline can honestly show.

The registry is deliberately small and explicit.  A topic that needs real screen
recording, an interview or licensed footage is *unsupported*: the pipeline must say
so before spending money on research, a script and a render, instead of drawing a
plausible-looking fake.  A topic that needs 3D or generated media is
``needs_extension``: it can proceed only as an explicitly labelled program-graphic
substitute, and the brief records that substitution.
"""
from __future__ import annotations

import re

# route → honest capability statement.  ``evidence`` names where the claim comes
# from, so a capability statement can always be traced back to code or a document.
ROUTES: dict[str, dict] = {
    "program-graphics": {
        "status": "supported",
        "description": "程序图形：text/math/shape/chart/diagram/timeline/image/procedural 组合图层",
        "evidence": "components.COMPONENTS 与 Scene DSL",
        "can_answer": True,
    },
    "licensed-media": {
        "status": "needs_extension",
        "description": "授权图片/视频：本地已登记素材可用；联网素材供应商尚未接入（S3-03 增强）",
        "evidence": "assets.py 只接受已登记本地素材",
        "can_answer": True,
    },
    "generated-media": {
        "status": "needs_extension",
        "description": "生成式图像/视频：默认关闭，未接入受控工作流（S3-07 可选）",
        "evidence": "pipeline 不自动调用付费生成服务",
        "can_answer": True,
    },
    "spatial-demo": {
        "status": "needs_extension",
        "description": "三维/空间演示：当前只有程序动画的伪三维点云，没有真正的三维模板（S3-07 可选）",
        "evidence": "studio/src 无 ThreeCanvas 组件",
        "can_answer": True,
    },
    "real-footage": {
        "status": "unsupported",
        "description": "真实录屏/实拍/采访：管线没有真实素材采集与证据链，画出来只能是伪造",
        "evidence": "assets.py 与 sources.py 都不采集视频实拍",
        "can_answer": False,
    },
}

# Text signals in the title/brief.  Ordered by severity: an unsupported signal wins.
SIGNALS: list[tuple[str, str]] = [
    (r"录屏|屏幕录制|实拍|实机|采访|现场拍摄|纪录片片段|监控画面|真人出镜|手把手操作", "real-footage"),
    (r"三维|立体结构|空间结构|剖面图|三维建模|3D", "spatial-demo"),
    (r"生成图|AI 绘图|生成视频|AI 生成画面|插画生成", "generated-media"),
    (r"照片|图片素材|海报|素材库|历史影像", "licensed-media"),
]

SEVERITY = {"supported": 0, "needs_extension": 1, "unsupported": 2}


def classify_route(title: str, brief: str | None = None) -> dict:
    """Deterministic route for a title/brief pair.

    This is the cheap gate that runs at ``create`` time: it must not depend on a
    model, because its whole job is to stop an impossible topic before any model
    call is paid for.
    """
    text = f"{title} {brief or ''}"
    matched = []
    for pattern, route in SIGNALS:
        match = re.search(pattern, text)
        if match:
            matched.append({"route": route, "signal": match.group(0)})
    route = max((item["route"] for item in matched), key=lambda name: SEVERITY[ROUTES[name]["status"]],
                default="program-graphics")
    spec = ROUTES[route]
    return {
        "route": route,
        "status": spec["status"],
        "description": spec["description"],
        "evidence": spec["evidence"],
        "signals": [item["signal"] for item in matched],
        "can_answer_with_program_graphics": spec["can_answer"],
        "substitute": ("program-graphics" if spec["status"] == "needs_extension" else None),
        "reason": _reason(route, spec, matched),
    }


def _reason(route: str, spec: dict, matched: list[dict]) -> str:
    signals = "、".join(sorted({item["signal"] for item in matched}))
    if route == "program-graphics":
        return "题目可用程序图形讲清，无需外部素材"
    if spec["status"] == "unsupported":
        return (f"题目信号「{signals}」需要{spec['description'].split('：')[0]}，"
                "当前管线无法真实呈现，不做伪造画面")
    return (f"题目信号「{signals}」指向{route}；当前为 {spec['status']}："
            f"{spec['description']}。以程序图形示意替代时必须标注示意，不声称已实现该能力")


def strictest(*decisions: dict | None) -> dict:
    """Combine route decisions (deterministic gate + planner claim) conservatively."""
    present = [item for item in decisions if item]
    if not present:
        return classify_route("")
    return max(present, key=lambda item: SEVERITY.get(item.get("status", "supported"), 0))


def capability_table() -> dict:
    return {"routes": ROUTES,
            "note": "status 是当前实现的真实状态；needs_extension 表示需要新组件或素材，"
                    "unsupported 表示管线不应假装能做"}
