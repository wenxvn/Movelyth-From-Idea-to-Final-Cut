"""Defect-routed minimal repair.

A rejected cut is not a reason to rewrite the film.  Each defect is classified into a
small set of codes, and each code has exactly one route: what may be changed, which
cached stages become invalid, and which checks must run again.  A repair that changes
anything outside its route is rejected, so a layout fix cannot quietly rewrite a fact.

Rounds and cost are bounded per defect; an unfixed defect stops instead of looping.
"""
from __future__ import annotations

import re

from pydantic import Field

from .models import Contract

MAX_ROUNDS = {"layout": 2, "caption": 2, "pronunciation": 2, "mix": 1, "event": 2,
              "data": 2, "asset": 1, "fact": 2, "review": 2}

# defect → what a repair may touch, which stages it invalidates, what must be rechecked
ROUTES: dict[str, dict] = {
    "layout": {
        "description": "排版、遮挡、溢出、文字过小",
        "operations": ["reflow-layout", "shorten-secondary-text"],
        "invalidates": ["render", "check"],
        "rechecks": ["layout", "technical", "captions"],
        "must_not": ["claims", "narration", "audio"],
    },
    "caption": {
        "description": "字幕分页、错字、显示文本与口播不一致",
        "operations": ["repaginate-caption"],
        "invalidates": ["render", "check"],
        "rechecks": ["captions", "layout", "technical"],
        "must_not": ["claims", "audio"],
    },
    "pronunciation": {
        "description": "读法、漏读、多音字、术语发音",
        "operations": ["re-synthesise-clause"],
        "invalidates": ["sound", "render", "check"],
        "rechecks": ["audio", "captions", "events"],
        "must_not": ["claims", "visuals"],
    },
    "mix": {
        "description": "音乐压人声、爆点、尾音、响度",
        "operations": ["remix"],
        "invalidates": ["sound-mix", "render", "check"],
        "rechecks": ["audio", "technical"],
        "must_not": ["claims", "narration", "visuals"],
    },
    "event": {
        "description": "事件/焦点/动画时机错位",
        "operations": ["retime-events"],
        "invalidates": ["render", "check"],
        "rechecks": ["events", "layout"],
        "must_not": ["claims", "audio"],
    },
    "data": {
        "description": "数值、单位、图表与旁白不一致",
        "operations": ["recompute", "rewrite-scene"],
        "invalidates": ["script", "sound", "render", "check"],
        "rechecks": ["claims", "narration", "technical"],
        "must_not": ["research"],
    },
    "asset": {
        "description": "素材不符、授权缺失、裁切丢主体",
        "operations": ["replace-asset", "request-asset"],
        "invalidates": ["assets", "render", "check"],
        "rechecks": ["assets", "layout"],
        "must_not": ["claims"],
    },
    "fact": {
        "description": "事实、结论、适用范围与证据冲突",
        "operations": ["re-evidence", "rewrite-scene"],
        "invalidates": ["evidence", "script", "sound", "render", "check"],
        "rechecks": ["sources", "claims", "narration"],
        "must_not": [],
    },
    "review": {
        "description": "未分类的审片意见",
        "operations": ["rewrite-scene"],
        "invalidates": ["script", "sound", "render", "check"],
        "rechecks": ["sources", "claims", "technical"],
        "must_not": [],
    },
}

# Keyword signals per defect.  A finding can mention several things ("音乐把结论压住了"),
# so the code with the most distinct signals wins instead of the first pattern that
# happens to match; ties fall back to SIGNAL_ORDER.
SIGNALS: dict[str, list[str]] = {
    "data": [r"数据", r"数值", r"单位", r"曲线", r"图表.*不符", r"不符.*图表", r"轴", r"量级",
             r"行列式", r"面积.*倍", r"趋势"],
    "pronunciation": [r"漏读", r"多音字", r"读法", r"发音", r"读成", r"念错", r"读出来", r"没读",
                      r"重读"],
    "mix": [r"音乐", r"人声", r"爆点", r"尾音", r"响度", r"压低", r"混音", r"压住"],
    "caption": [r"字幕", r"分页", r"错字", r"显示文本", r"断句"],
    "layout": [r"遮挡", r"溢出", r"裁切", r"重叠", r"缺字", r"太小", r"过暗", r"布局", r"排版",
               r"空白", r"间距"],
    "event": [r"事件", r"时机", r"焦点", r"相机", r"时间点", r"错位", r"提前", r"延后"],
    "asset": [r"素材", r"授权", r"图片不", r"版权", r"署名"],
}
SIGNAL_ORDER = ["data", "pronunciation", "mix", "caption", "layout", "event", "asset"]


def scores(detail: str) -> dict[str, int]:
    text = str(detail or "")
    return {code: sum(1 for pattern in patterns if re.search(pattern, text))
            for code, patterns in SIGNALS.items()}


class RepairPlan(Contract):
    defect: str
    description: str
    scenes: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    invalidates: list[str] = Field(default_factory=list)
    rechecks: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    round_index: int = Field(default=1, ge=1)
    rounds_left: int = Field(default=1, ge=0)
    blocked_reason: str = Field(default="", max_length=200)

    def allowed(self) -> bool:
        return self.rounds_left > 0 and not self.blocked_reason


def classify(detail: str, category: str = "") -> str:
    """Defect code for a finding or free-text issue.

    The model's own category decides the two unambiguous cases (a factual finding is
    a fact problem, an audio finding is a pronunciation problem); everything else is
    decided by counting keyword signals, never by the first word that matches.
    """
    if category == "factual":
        return "fact"
    if category == "audio_defect":
        return "pronunciation"
    counted = scores(detail)
    best = max(counted.values(), default=0)
    if best == 0:
        return {"visual_defect": "layout", "visual_mismatch": "event"}.get(category, "review")
    for code in SIGNAL_ORDER:
        if counted[code] == best:
            return code
    return "review"


def plan(detail: str, *, scenes: list[str] | None = None, category: str = "",
         round_index: int = 1) -> RepairPlan:
    defect = classify(detail, category)
    route = ROUTES[defect]
    rounds_left = MAX_ROUNDS[defect] - round_index + 1
    blocked = "" if rounds_left > 0 else f"{defect} 类缺陷已用尽 {MAX_ROUNDS[defect]} 轮修复"
    return RepairPlan(defect=defect, description=route["description"],
                      scenes=list(scenes or []), operations=list(route["operations"]),
                      invalidates=list(route["invalidates"]), rechecks=list(route["rechecks"]),
                      must_not=list(route["must_not"]), round_index=round_index,
                      rounds_left=max(0, rounds_left), blocked_reason=blocked)


def plan_for_review(findings, *, round_index: int = 1) -> list[RepairPlan]:
    """One plan per defect code, with the scenes the reviewer named."""
    grouped: dict[str, RepairPlan] = {}
    for finding in findings:
        code = classify(finding.detail, getattr(finding, "category", ""))
        current = grouped.get(code)
        scene = getattr(finding, "scene_id", "") or ""
        if current is None:
            grouped[code] = plan(finding.detail, scenes=[scene] if scene else [],
                                 category=getattr(finding, "category", ""),
                                 round_index=round_index)
        elif scene and scene not in current.scenes:
            current.scenes.append(scene)
    return list(grouped.values())


def scope_violations(frozen_scenes: dict[str, dict], revised_scenes: dict[str, dict],
                     targets: set[str]) -> list[str]:
    """Changes outside the planned scenes are a scope violation, not a repair."""
    problems = []
    for scene_id, original in frozen_scenes.items():
        if scene_id in targets:
            continue
        if scene_id not in revised_scenes:
            problems.append(f"修复删除了未在范围内的镜头 {scene_id}")
        elif revised_scenes[scene_id] != original:
            problems.append(f"修复改动了未在范围内的镜头 {scene_id}")
    return problems
