"""Versioned audience feedback: observations belong to a revision, not to "the video".

A metric without a version, an observation time and a window is not evidence: the same
episode changes revision, a platform number is cumulative at one moment, and an
observation at day 1 cannot be compared with day 14.  This module keeps those apart and
turns a viewer's complaint into a located, testable item.
"""
from __future__ import annotations

import json

from pydantic import Field

from .models import Contract

# Metrics a platform may report.  Anything not measured stays ``None`` — never 0.
METRICS = ("views", "likes", "comments", "shares", "favorites", "completion_rate",
           "average_watch_seconds", "followers_gained")
WINDOWS = {"cumulative": "自发布以来的累计值", "24h": "发布后 24 小时", "7d": "发布后 7 天",
           "28d": "发布后 28 天", "custom": "自定义区间"}


class Observation(Contract):
    """One measurement of one revision, at one time, over one window."""

    episode: str = Field(pattern=r"^VID-[0-9]{6}$")
    revision: int = Field(ge=1)
    cut: str = Field(default="long", pattern=r"^(long|short)$")
    platform: str = Field(pattern=r"^(bilibili|douyin)$")
    url: str = Field(pattern=r"^https://", max_length=400)
    observed_at: str = Field(min_length=10, max_length=40)
    window: str = Field(default="cumulative", max_length=16)
    metrics: dict[str, float | None] = Field(default_factory=dict)
    note: str = Field(default="", max_length=300)

    def __init__(self, **data):
        super().__init__(**data)
        if self.window not in WINDOWS:
            raise ValueError(f"window 只能是 {'/'.join(WINDOWS)}")
        unknown = set(self.metrics) - set(METRICS)
        if unknown:
            raise ValueError(f"未知指标：{', '.join(sorted(unknown))}")
        for name, value in self.metrics.items():
            if value is not None and value < 0:
                raise ValueError(f"{name} 不能为负")


class ViewerIssue(Contract):
    """A viewer's complaint, located on the version that was actually published."""

    episode: str = Field(pattern=r"^VID-[0-9]{6}$")
    revision: int = Field(ge=1)
    cut: str = Field(default="long", pattern=r"^(long|short)$")
    at_seconds: float | None = Field(default=None, ge=0, le=3600)
    scene_id: str = Field(default="", max_length=32)
    kind: str = Field(default="other",
                      pattern=r"^(unclear|wrong|too_fast|too_slow|audio|visual|caption|other)$")
    original: str = Field(min_length=2, max_length=400)


def parse_metrics(raw: dict) -> dict:
    """Keep only measured numbers; a missing metric is absent, not zero."""
    metrics = {}
    for name in METRICS:
        value = raw.get(name)
        if value is None or value == "":
            continue
        try:
            metrics[name] = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} 需要数字") from None
    return metrics


def compare(previous: Observation, current: Observation) -> dict:
    """Compare two observations only when the window and the revision match."""
    problems = []
    if previous.revision != current.revision:
        problems.append("两次观察属于不同 revision，不能直接比较")
    if previous.window != current.window:
        problems.append(f"观察窗口不同（{previous.window} vs {current.window}）")
    if previous.platform != current.platform or previous.cut != current.cut:
        problems.append("平台或版本不同，不能直接比较")
    deltas = {}
    if not problems:
        for name in set(previous.metrics) | set(current.metrics):
            before, after = previous.metrics.get(name), current.metrics.get(name)
            if before is None or after is None:
                deltas[name] = None      # unknown stays unknown
            else:
                deltas[name] = round(after - before, 3)
    return {"comparable": not problems, "problems": problems, "deltas": deltas,
            "note": "累计值与区间值不能混用；未知保持 null"}


def hypothesis(issue: ViewerIssue, *, scene: dict | None = None) -> dict:
    """Turn a complaint into one testable hypothesis plus the check that would show it."""
    mapping = {
        "unclear": ("这一段的解释顺序或术语密度让观众跟不上",
                    ["caption_reading_speed", "scene_hold_reason", "recipe_check"]),
        "wrong": ("画面/数字与旁白不一致", ["claim_coverage", "parameters_same_source",
                                            "review_findings"]),
        "too_fast": ("语速或信息密度超过观众处理速度", ["prosody_rate", "caption_reading_speed"]),
        "too_slow": ("停顿过多或镜头过长", ["pacing_report", "scene_hold_reason"]),
        "audio": ("人声被压低、尾音被截断或音量不足", ["mix_balance", "tail_report", "loudness"]),
        "visual": ("构图/遮挡/焦点让人找不到重点", ["layout_precheck", "camera_plan", "composition"]),
        "caption": ("字幕过快、分页错误或与口播不一致", ["caption_reading_speed", "srt_matches_cues"]),
        "other": ("未分类的观感问题", ["human_review"]),
    }
    claim, checks = mapping[issue.kind]
    return {
        "episode": issue.episode, "revision": issue.revision, "cut": issue.cut,
        "at_seconds": issue.at_seconds, "scene_id": issue.scene_id or (scene or {}).get("id", ""),
        "kind": issue.kind, "original": issue.original,
        "hypothesis": claim, "checks": checks,
        "status": "unverified",
        "note": "这是待验证假设，不是结论；一次偏好或播放上涨不改变全局默认",
    }


def load_observations(path) -> list[Observation]:
    """Read observations recorded next to the workspace; malformed rows are skipped."""
    from pathlib import Path

    file = Path(path)
    if not file.is_file():
        return []
    try:
        rows = json.loads(file.read_text(encoding="utf-8")).get("observations") or []
    except (OSError, ValueError):
        return []
    result = []
    for row in rows:
        try:
            result.append(Observation.model_validate(row))
        except ValueError:
            continue
    return result


def append_observation(path, observation: Observation) -> None:
    from pathlib import Path

    from .util import atomic_json

    file = Path(path)
    rows = []
    if file.is_file():
        try:
            rows = json.loads(file.read_text(encoding="utf-8")).get("observations") or []
        except (OSError, ValueError):
            rows = []
    rows.append(observation.model_dump())
    atomic_json(file, {"observations": rows[-200:],
                       "note": "每条观察绑定 episode/revision/cut/时间/窗口；未知指标不写 0"})
