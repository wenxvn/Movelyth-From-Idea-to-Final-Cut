"""Build the frozen production brief for one episode.

The brief answers four questions before any expensive stage runs: who is this for,
what single question does it answer, which route can actually deliver it, and what
is the budget.  It is derived from the research record plus configuration, so it
needs no extra model call and is reproducible offline.
"""
from __future__ import annotations

import re

from .capability import classify_route, strictest
from .models import Budget, ProductionBrief
from .util import fingerprint

DEFAULT_AUDIENCE = "未指定：按科普默认处理，不假设专业背景"
DEFAULT_PRIOR = "未指定：按科普默认，知道基础四则运算，不了解专业术语"
AUDIENCE_PATTERN = re.compile(r"(?:面向|受众[是为：:]?|给)([^，。;；\n]{2,30})")
STYLE_VALUES = {"minimal", "tech", "documentary"}


def audience_from(user_brief: str | None) -> tuple[str, str]:
    """Audience and prior knowledge, taken from the user's own words when given.

    Nothing is invented: when the brief does not say, the field states that it was
    not specified instead of pretending a persona was chosen.
    """
    if not user_brief:
        return DEFAULT_AUDIENCE, DEFAULT_PRIOR
    match = AUDIENCE_PATTERN.search(user_brief)
    if not match:
        return DEFAULT_AUDIENCE, DEFAULT_PRIOR
    audience = match.group(1).strip(" 　:：,，")
    if len(audience) < 2:
        return DEFAULT_AUDIENCE, DEFAULT_PRIOR
    return audience, f"由 brief 指定受众：{audience}；其余背景未说明"


def estimate_budget(config: dict, *, long_seconds: int, short_seconds: int) -> Budget:
    """A bound, not a bill: unknown money stays ``None`` instead of becoming 0."""
    studio = config.get("studio") or {}
    retries = int(studio.get("max_retries", 2))
    director_calls = 2 * (1 + retries)  # long + short per attempt
    review_calls = 1 + retries
    return Budget(
        model_calls=1 + 2 + director_calls + review_calls,
        tts_characters=int((long_seconds + short_seconds) * 5.5),
        render_minutes=float(round((long_seconds + short_seconds) * 2 / 60, 1)),
        estimated_cost=None, currency="",
        note="估算上限；实际费用未知时保持 null，不按 0 计（价格表未配置）")


def build_production_brief(*, title: str, user_brief: str | None, research, config: dict,
                           declared_capability: str | None = None,
                           declared_route: str | None = None) -> ProductionBrief:
    """Freeze audience, question, route and budget for this task."""
    studio = config.get("studio") or {}
    route = strictest(classify_route(title, user_brief),
                      _declared(declared_capability, declared_route, title, user_brief))
    audience, prior = audience_from(user_brief)
    style = str(studio.get("style") or "tech")
    if style not in STYLE_VALUES:
        style = "tech"
    substitutions = []
    if route["status"] == "needs_extension" and route["substitute"] == "program-graphics":
        substitutions.append(f"{route['route']} → program-graphics（标注示意，不声称已实现）")
    return ProductionBrief(
        audience=audience,
        prior_knowledge=prior,
        question=research.question,
        central_explanation=research.angle,
        boundaries=list(research.cautions)[:8],
        route=route["route"],
        route_status=route["status"],
        effective_route=route["substitute"] or route["route"],
        route_reason=route["reason"],
        substitutions=substitutions,
        orientations=["landscape", "portrait"],
        long_seconds=int(studio.get("long_seconds", 180)),
        short_seconds=int(studio.get("short_seconds", 60)),
        style=style,
        budget=estimate_budget(config, long_seconds=int(studio.get("long_seconds", 180)),
                               short_seconds=int(studio.get("short_seconds", 60))),
        created_from={"title": title, "brief": fingerprint(user_brief) if user_brief else None,
                      "research": fingerprint(research.model_dump()),
                      "route_signals": route["signals"]},
    )


def _declared(capability: str | None, route_name: str | None, title: str,
              user_brief: str | None) -> dict | None:
    """Translate a planner's declared capability into a route decision."""
    if not capability and not route_name:
        return None
    base = classify_route(title, user_brief)
    if route_name:
        base = {**base, "route": route_name,
                "status": "unsupported" if route_name == "real-footage" else base["status"]}
    if capability == "unsupported":
        base = {**base, "status": "unsupported", "can_answer_with_program_graphics": False,
                "reason": base["reason"] + "；选题阶段已声明当前能力无法完成"}
    elif capability == "needs_extension" and base["status"] == "supported":
        base = {**base, "status": "needs_extension", "substitute": "program-graphics",
                "reason": base["reason"] + "；选题阶段声明需要新增能力，先以程序图形示意"}
    return base


def topic_violations(brief: dict, *, title: str, research) -> list[str]:
    """Repairs may change scenes; they may not silently change the topic."""
    problems = []
    if brief.get("question") and brief["question"] != research.question:
        problems.append("研究与已冻结的 production brief 问题不一致（疑似换题）")
    created = brief.get("created_from") or {}
    if created.get("title") and created["title"] != title:
        problems.append("标题与已冻结的 production brief 不一致")
    return problems
