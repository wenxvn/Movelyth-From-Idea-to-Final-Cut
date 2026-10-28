"""One-screen task status for the person making the video.

The pipeline writes machine-readable JSON; a user needs a short answer: what stage is
it at, what is missing, where exactly is the problem, and what can they do next.  This
module derives that from the files already on disk — it never invents progress.
"""
from __future__ import annotations

from pathlib import Path

from .util import read_json

STAGE_LABELS = {
    "research": "研究", "evidence": "来源核对", "brief": "制作 brief", "script": "脚本与审稿",
    "sound": "配音与混音", "assets": "素材", "precheck": "布局预检", "render": "渲染",
    "check": "成片检查", "preview": "预览",
}
BLOCKER_KINDS = {
    "config": "配置", "resource": "资源/工具", "asset": "素材或证据", "capability": "能力缺口",
    "budget": "预算", "review": "需要人工复核",
}


def _read(path: Path):
    try:
        return read_json(path) if path.is_file() else None
    except (OSError, ValueError):
        return None


def classify_error(message: str) -> str:
    """Which kind of blocker is this?  A user action depends on the answer."""
    text = str(message or "")
    if "预算" in text or "BudgetExceeded" in text:
        return "budget"
    if "无法真实呈现" in text or "能力" in text or "未实现" in text:
        return "capability"
    if "素材" in text or "证据" in text or "来源" in text:
        return "asset"
    if "缺少" in text or "ffprobe" in text or "Codex" in text or "时区" in text:
        return "resource"
    if "需要复核" in text or "可修复缺陷" in text or "审片未通过" in text:
        return "review"
    return "config"


def review_items(job: Path) -> list[dict]:
    """Located, actionable problems from the release decision."""
    decision = _read(job / "release-decision.json") or {}
    items = []
    for group, label in (("blocking", "阻断"), ("review", "待复核")):
        for check in decision.get(group) or []:
            items.append({
                "severity": label,
                "check": check.get("check_id"),
                "where": check.get("location") or {},
                "what": check.get("observation") or "",
                "repairable": check.get("repairable", False),
                "source": check.get("source"),
            })
    return items


def summary(job: Path, episode: dict) -> dict:
    """A compact, honest status for one episode."""
    stages = {}
    for marker in sorted((job / "stages").glob("*.json")) if (job / "stages").is_dir() else []:
        data = _read(marker) or {}
        stages[marker.stem] = data.get("finished_at") or "已完成"
    brief = _read(job / "production-brief.json") or {}
    decision = _read(job / "release-decision.json") or {}
    precheck = _read(job / "layout-precheck.json") or {}
    budget = _read(job / "budget.json") or {}
    error = episode.get("error") or ""
    status = episode.get("status") or "planned"
    next_step = "等待运行"
    if status == "ready":
        next_step = "成片与投稿包已就绪，上传仍需要你本人完成"
    elif status in {"failed", "blocked"}:
        kind = classify_error(error)
        next_step = {
            "budget": "提高 [budget] 上限后运行 movelyth resume",
            "capability": "换一个不需要该能力的角度，或先实现对应扩展（S3-04/05/07）",
            "asset": "补充来源/素材或改掉依赖该素材的镜头，再 resume",
            "resource": "按 doctor 的提示安装缺失工具或修正配置，再 resume",
            "review": "查看下面的定位问题，修好后 resume 或用 revise 局部重做",
            "config": "修正 movelyth.toml 后 resume",
        }[kind]
    elif status in {"script", "sound", "render", "check", "previewed"}:
        next_step = "正在制作中；中断后可运行 movelyth resume"
    return {
        "episode": f"VID-{episode['id']:06d}",
        "title": episode.get("title"),
        "status": status,
        "revision": episode.get("revision"),
        "delivery": episode.get("delivery"),
        "stages_done": [STAGE_LABELS.get(name, name) for name in stages],
        "route": {"route": brief.get("route"), "status": brief.get("route_status"),
                  "effective": brief.get("effective_route"),
                  "substitutions": brief.get("substitutions") or []},
        "decision": decision.get("decision"),
        "precheck": {"passed": precheck.get("passed"),
                     "problems": (precheck.get("problems") or [])[:5]},
        "problems": review_items(job)[:10],
        "budget": {"used": budget.get("used") or {}, "limits": budget.get("limits") or {},
                   "blocked": budget.get("blocked_reason") or ""},
        "error": {"kind": classify_error(error) if error else "",
                  "label": BLOCKER_KINDS.get(classify_error(error), "") if error else "",
                  "message": error},
        "next": next_step,
        "note": "ready 不等于 published；状态来自磁盘上的真实阶段与检查记录",
    }
