"""Release policy: one place that turns every report into one delivery decision.

Before this module the pipeline decided delivery by a series of independent
``if`` statements, and the visual review could be softened by a keyword rule that
matched the word "axis".  A finding that merely *mentions* a tick label was
therefore enough to drop a real defect, and a model's ``passed: true`` could
override a factual finding that said otherwise.

The policy here is deliberately narrow:

* every check becomes a :class:`CheckResult` with an explicit status, severity and
  whether it is *required* for delivery;
* a model review is normalised first (consistency), then its axis findings are
  kept, downgraded **only with deterministic evidence**, or marked ``unknown``;
* :func:`decide` aggregates: any critical/major failure blocks, any required
  unknown needs review, everything else may be ready.

Nothing in this module renders, calls a model or touches the filesystem.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from .charts import scene_tick_labels
from .models import Contract, Finding, Review

POLICY_VERSION = "2"

# A finding that reports one of these is never downgraded: the words describe a
# defect that can be seen without reading any number off an axis.
STRUCTURAL_PATTERN = re.compile(
    r"空白|遮挡|溢出|裁切|重叠|缺字|缺刻度|未标|不可读|过暗|过亮|太小|颜色|布局|位置错|未显示|丢失|"
    r"截断|黑屏|闪烁|模糊|错位")
AXIS_PATTERN = re.compile(r"刻度|坐标轴|纵轴|横轴|axis|ticks?|y-?axis|x-?axis", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
# A finding that talks about the data, the units or the axis structure is a claim
# about correctness, not about reading a label; deterministic tick labels say
# nothing about it, so it is never softened.
DATA_PATTERN = re.compile(r"数据|数值|单位|趋势|互换|交换|缺轴|漏轴|轴变量|量级|刻度数|series|unit")
SCENE_PATTERN = re.compile(r"\b([ls]\d{1,2})\b")

# Findings that describe a defect in the work itself.  ``warning`` and
# ``visual_mismatch`` are observations that may be a misreading; the rest are not.
BLOCKING_CATEGORIES = {"factual", "visual_defect", "audio_defect"}

Status = Literal["pass", "fail", "unknown", "not_applicable"]
Severity = Literal["critical", "major", "minor"]
CheckSource = Literal["technical", "audio", "source", "layout", "caption", "motion", "model", "deterministic"]


class CheckResult(Contract):
    """One check, its status, and what it would take to resolve it."""

    check_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,48}$")
    source: CheckSource
    status: Status
    severity: Severity = "major"
    required: bool = True
    repairable: bool = False
    observation: str = Field(default="", max_length=400)
    location: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)


class ReleaseDecision(Contract):
    """The delivery decision for one cut/revision, with every input that shaped it."""

    decision: Literal["ready", "needs_review", "blocked"]
    policy_version: str = POLICY_VERSION
    blocking: list[CheckResult] = Field(default_factory=list)
    review: list[CheckResult] = Field(default_factory=list)
    warnings: list[CheckResult] = Field(default_factory=list)
    not_applicable: list[CheckResult] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    inputs: dict = Field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.decision == "ready"


# --------------------------------------------------------------------------- review

def normalize_review(review: Review) -> dict:
    """Make a model review self-consistent, keeping the raw result for the record.

    A reviewer that says ``passed: true`` while listing a factual finding, or while
    listing issues, is contradictory; the stricter reading wins.  A reviewer that
    says ``passed: false`` without naming a reason is *not* silently turned into a
    pass either — it stays a rejection and is flagged as unsupported.
    """
    changes: list[str] = []
    blocking = [finding for finding in review.findings if finding.category in BLOCKING_CATEGORIES]
    passed = review.passed
    if passed and blocking:
        passed = False
        changes.append("passed=true 但存在阻断 finding（" +
                       "、".join(sorted({f.category for f in blocking})) + "），按阻断处理")
    if passed and review.issues:
        passed = False
        changes.append("passed=true 但 issues 非空，按未通过处理")
    if not passed and not review.issues and not review.findings:
        changes.append("passed=false 但未给出任何理由；保留未通过，不自动改为通过")
    normalized = Review.model_validate({
        "passed": passed,
        "issues": review.issues[:15],
        "strengths": review.strengths[:6],
        "warnings": review.warnings[:10],
        "findings": [finding.model_dump() for finding in review.findings[:15]],
    })
    return {"review": normalized, "raw": review, "changes": changes}


def classify_axis_finding(finding: Finding, ticks_by_scene: dict[str, list[str]]) -> dict:
    """Decide what an axis finding is: a misread label, a real defect, or unresolved.

    Tick labels are generated from the data (see :mod:`movelyth.charts`), so a claim
    about *what the labels are* can be checked against the labels that exist.  A
    claim about the data, the units or the axis structure cannot: those describe
    correctness, and no generated label can excuse them.
    """
    return classify_axis_text(finding.detail, finding.scene_id, ticks_by_scene,
                              category=finding.category)


def classify_axis_text(detail: str, scene_id: str, ticks_by_scene: dict[str, list[str]],
                       *, category: str = "visual_mismatch") -> dict:
    if category != "visual_mismatch" or not AXIS_PATTERN.search(detail):
        return {"verdict": "not-axis"}
    if STRUCTURAL_PATTERN.search(detail):
        return {"verdict": "not-axis", "why": "同时报告了结构性缺陷，按原样阻断"}
    if DATA_PATTERN.search(detail):
        return {"verdict": "block",
                "evidence": {"kind": "claim-about-data-or-units",
                             "why": "涉及数据/单位/轴结构，生成刻度不能证明其正确，不能降级"}}
    labels = ticks_by_scene.get(scene_id or "", [])
    if not labels:
        return {"verdict": "unresolved", "why": "该场景没有可核对的程序生成刻度"}
    claimed = NUMBER_PATTERN.findall(detail)
    if not claimed:
        return {"verdict": "unresolved", "why": "finding 没有给出具体数字，无法与生成刻度核对"}
    known = {label for label in labels}
    matching = [number for number in claimed if _matches_label(number, known)]
    if len(matching) == len(claimed):
        return {"verdict": "downgrade",
                "evidence": {"kind": "generated-tick-labels", "scene_id": scene_id,
                             "labels": labels, "claimed": claimed}}
    # The axis can only show the generated labels, so a claimed label that does not
    # exist in that set is a misreading; the real labels are the evidence.
    return {"verdict": "downgrade",
            "evidence": {"kind": "claimed-label-not-generated", "scene_id": scene_id,
                         "labels": labels, "claimed": claimed,
                         "why": "刻度由程序生成，claimed 中的数字不在生成刻度里，判定为读数不确定"}}


def _matches_label(number: str, labels: set[str]) -> bool:
    try:
        value = float(number)
    except ValueError:
        return False
    for label in labels:
        try:
            if abs(float(label) - value) <= 1e-9 * max(1.0, abs(value)):
                return True
        except ValueError:
            continue
    return False


def review_checks(review: Review, *, ticks_by_scene: dict[str, list[str]] | None = None,
                  axis_policy: str = "deterministic", stage: str = "visual") -> tuple[Review, list[CheckResult], list[str]]:
    """Turn a normalised review into checks, with a traceable axis policy.

    ``axis_policy``:
      * ``deterministic`` (default): downgrade only with generated-tick evidence;
        unresolved axis readings become ``unknown`` but are not required, so they
        inform the operator without forcing a re-render;
      * ``strict``: keep every axis reading as a blocking finding.
    """
    ticks_by_scene = ticks_by_scene or {}
    normalized = normalize_review(review)
    clean: Review = normalized["review"]
    notes: list[str] = list(normalized["changes"])
    kept: list[Finding] = []
    kept_issues: list[str] = []
    checks: list[CheckResult] = []
    softened = False
    block_evidence: dict[int, dict] = {}
    for finding in clean.findings:
        if finding.category not in BLOCKING_CATEGORIES:
            verdict = (classify_axis_finding(finding, ticks_by_scene) if axis_policy == "deterministic"
                       else {"verdict": "not-axis"})
            if verdict["verdict"] == "downgrade":
                evidence = verdict["evidence"]
                notes.append(f"已降级为参考（{finding.scene_id}）：刻度由程序按数据范围生成 "
                             f"{evidence['labels']}，finding 中的数字 {evidence['claimed']} 与其一致，"
                             "判定为读数不确定")
                checks.append(CheckResult(
                    check_id=f"review.{stage}.axis.{finding.scene_id or 'unscoped'}",
                    source="model", status="unknown", severity="minor", required=False,
                    observation=finding.detail, evidence=evidence,
                    location={"scene_id": finding.scene_id, "stage": stage}))
                softened = True
                continue
            if verdict["verdict"] == "unresolved":
                checks.append(CheckResult(
                    check_id=f"review.{stage}.axis-unresolved.{finding.scene_id or 'unscoped'}",
                    source="model", status="unknown", severity="minor", required=False,
                    observation=finding.detail,
                    location={"scene_id": finding.scene_id, "stage": stage},
                    evidence={"kind": "no-deterministic-evidence", "why": verdict["why"]}))
                notes.append(f"未降级的轴读数疑点（{finding.scene_id or '未定位'}）：{finding.detail[:120]}")
                softened = True
                continue
            if verdict["verdict"] == "block":
                # Kept as a blocking finding; the data/unit claim is what matters,
                # and _finding_checks records it with its evidence.
                kept.append(finding)
                block_evidence[id(finding)] = verdict["evidence"]
                continue
        kept.append(finding)
    issue_results = issue_verdicts(clean.issues, ticks_by_scene) if axis_policy == "deterministic"         else [{"verdict": "not-axis"} for _ in clean.issues]
    for issue, verdict in zip(clean.issues, issue_results, strict=True):
        if verdict["verdict"] in {"downgrade", "unresolved"}:
            softened = True
            notes.append(f"轴读数疑点（{issue[:60]}）：{verdict.get('why', '刻度由程序生成，判定为读数不确定')}")
        else:
            kept_issues.append(issue)
    checks.extend(_finding_checks(kept, stage=stage, evidence=block_evidence))
    checks.extend(_issue_checks(clean.issues, stage=stage, verdicts=issue_results))
    # A review whose only objections were axis readings no longer fails the cut, but
    # the softened observations stay in the decision as optional unknowns.
    base = clean.passed or (softened and not kept and not kept_issues)
    final = Review.model_validate({
        "passed": base and not kept and not kept_issues,
        "issues": kept_issues,
        "strengths": clean.strengths,
        "warnings": clean.warnings,
        "findings": [finding.model_dump() for finding in kept],
    })
    return final, checks, notes


def _finding_checks(findings: list[Finding], *, stage: str,
                    evidence: dict[int, dict] | None = None) -> list[CheckResult]:
    results = []
    for index, finding in enumerate(findings):
        if finding.category == "warning":
            # A reviewer's own soft note: recorded, never blocking.
            results.append(CheckResult(
                check_id=f"review.{stage}.warning.{index + 1}", source="model", status="unknown",
                severity="minor", required=False, observation=finding.detail,
                location={"scene_id": finding.scene_id, "stage": stage}))
            continue
        results.append(CheckResult(
            check_id=f"review.{stage}.{finding.category}.{index + 1}",
            source="model",
            status="fail",
            severity="critical" if finding.category == "factual" else "major",
            required=True,
            repairable=True,
            observation=finding.detail,
            evidence=(evidence or {}).get(id(finding), {}),
            location={"scene_id": finding.scene_id, "stage": stage}))
    return results


def issue_verdicts(issues: list[str], ticks_by_scene: dict[str, list[str]]) -> list[dict]:
    """Classify free-text issues; scene ids are read from the text (``l3``/``s2``)."""
    verdicts = []
    for issue in issues:
        match = SCENE_PATTERN.search(issue)
        verdicts.append(classify_axis_text(issue, match.group(1) if match else "", ticks_by_scene))
    return verdicts


def _issue_checks(issues: list[str], *, stage: str, verdicts: list[dict] | None = None) -> list[CheckResult]:
    results = []
    for index, issue in enumerate(issues):
        verdict = (verdicts[index] if verdicts and index < len(verdicts) else {"verdict": "not-axis"})
        if verdict["verdict"] == "downgrade":
            results.append(CheckResult(
                check_id=f"review.{stage}.axis.issue.{index + 1}", source="model", status="unknown",
                severity="minor", required=False, observation=issue, evidence=verdict["evidence"],
                location={"stage": stage}))
        elif verdict["verdict"] == "unresolved":
            results.append(CheckResult(
                check_id=f"review.{stage}.axis-unresolved.issue.{index + 1}", source="model",
                status="unknown", severity="minor", required=False, observation=issue,
                evidence={"kind": "no-deterministic-evidence", "why": verdict.get("why", "")},
                location={"stage": stage}))
        else:
            results.append(CheckResult(
                check_id=f"review.{stage}.issue.{index + 1}", source="model", status="fail",
                severity="major", required=True, repairable=True, observation=issue,
                location={"stage": stage}))
    return results


# ------------------------------------------------------------------- deterministic

TECHNICAL_CHECKS: dict[str, tuple[str, bool]] = {
    # name: (severity, required)
    "full_decode": ("critical", True),
    "h264": ("minor", True),
    "aac": ("minor", True),
    "dimensions": ("major", True),
    "fps": ("minor", True),
    "duration_matches_timeline": ("major", True),
    "requested_duration_range": ("major", True),
    "audible": ("major", True),
    "no_clipping": ("minor", True),
    "loudness_matches_target": ("major", True),
    "true_peak_below_ceiling": ("minor", True),
    "moving_picture": ("minor", False),
    "not_black": ("critical", True),
}


def technical_checks(report: dict, *, cut: str) -> list[CheckResult]:
    """Map a ``verify_video`` report onto policy checks (one per named check)."""
    results: list[CheckResult] = []
    for name, value in (report.get("checks") or {}).items():
        severity, required = TECHNICAL_CHECKS.get(name, ("major", True))
        results.append(CheckResult(
            check_id=f"technical.{cut}.{name}", source="technical",
            status="pass" if value else "fail", severity=severity, required=required,
            observation="" if value else f"{cut} 技术检查未通过：{name}",
            location={"cut": cut},
            evidence={"measured": {key: report.get(key) for key in
                                   ("duration", "width", "height", "fps", "mean_volume_db", "max_volume_db")}}))
    return results


def audio_checks(report: dict, *, cut: str) -> list[CheckResult]:
    """Voice presence, silence, ducking and transcript coverage on the voice stem.

    A missing voice track must not be hidden by music energy, so the voice check is
    taken from the voice report, never from the mix.
    """
    results: list[CheckResult] = []
    asr = (report.get("asr") or {}).get("status", "disabled")
    transcript = report.get("transcript_check") or {}
    if asr == "completed":
        status = "pass" if transcript.get("status") in {"pass", "ok", "completed"} else "fail"
        results.append(CheckResult(
            check_id=f"audio.{cut}.transcript", source="audio", status=status, severity="major",
            required=True, repairable=True,
            observation=transcript.get("note", ""), location={"cut": cut},
            evidence={"asr": asr, "detail": transcript}))
    else:
        results.append(CheckResult(
            check_id=f"audio.{cut}.transcript", source="audio", status="not_applicable",
            severity="minor", required=False,
            observation="ASR 未启用：未做语音内容核对（能力声明需注明）",
            location={"cut": cut}, evidence={"asr": asr}))
    silence = report.get("silence") or {}
    results.append(CheckResult(
        check_id=f"audio.{cut}.silence", source="audio",
        status="pass" if silence.get("status") == "ok" else
               ("not_applicable" if silence.get("status") in {None, "disabled", "not-run"} else "fail"),
        severity="major", required=silence.get("status") not in {None, "disabled", "not-run"},
        repairable=True, observation=silence.get("note", ""), location={"cut": cut},
        evidence=silence))
    ducking = report.get("ducking") or {}
    results.append(CheckResult(
        check_id=f"audio.{cut}.ducking", source="audio",
        status="pass" if ducking.get("status") == "ok" else
               ("not_applicable" if ducking.get("status") in {None, "disabled", "not-run"} else "fail"),
        severity="minor", required=False, repairable=True,
        observation=ducking.get("note", ""), location={"cut": cut}, evidence=ducking))
    return results


def layout_checks(timeline: dict, *, cut: str) -> list[CheckResult]:
    """Soft layout warnings and estimated caption timing, per scene.

    These are *not* blockers: they say the renderer will shrink text or that a
    caption boundary is an estimate.  They stay visible in the decision so an
    operator can see why a frame looked crowded.
    """
    results: list[CheckResult] = []
    for scene in timeline.get("scenes") or []:
        scene_id = str(scene.get("id", ""))
        for index, warning in enumerate(scene.get("layout_warnings") or []):
            results.append(CheckResult(
                check_id=f"layout.{cut}.{scene_id}.{index + 1}", source="layout", status="unknown",
                severity="minor", required=False, observation=str(warning),
                location={"cut": cut, "scene_id": scene_id}))
        timing = scene.get("caption_timing")
        if timing and timing != "tts-word-boundaries":
            results.append(CheckResult(
                check_id=f"caption.{cut}.{scene_id}.timing", source="caption", status="unknown",
                severity="minor", required=False,
                observation=f"字幕时间来自 {timing}，不是真实词语边界",
                location={"cut": cut, "scene_id": scene_id}, evidence={"timing": timing}))
    return results


def decide(checks: list[CheckResult], *, inputs: dict | None = None) -> ReleaseDecision:
    """Aggregate checks: blocking failure > required unknown > ready."""
    blocking = [c for c in checks if c.status == "fail" and c.severity in {"critical", "major"}]
    minor_failures = [c for c in checks if c.status == "fail" and c.severity == "minor"]
    unknown_required = [c for c in checks if c.status == "unknown" and c.required]
    unknown_optional = [c for c in checks if c.status == "unknown" and not c.required]
    not_applicable = [c for c in checks if c.status == "not_applicable"]
    passed = [c.check_id for c in checks if c.status == "pass"]
    review = blocking + unknown_required
    warnings = minor_failures + unknown_optional
    reasons = [c.observation for c in blocking + unknown_required if c.observation]
    for check in not_applicable:
        if check.required:
            warnings.append(check)
            reasons.append(f"{check.check_id} 标为不适用但被声明为必需：{check.observation}")
    decision = "blocked" if blocking else ("needs_review" if unknown_required else "ready")
    return ReleaseDecision(decision=decision, blocking=blocking, review=review, warnings=warnings,
                           not_applicable=not_applicable, passed=passed, reasons=reasons[:20],
                           inputs=inputs or {})


def scene_ticks(scenes: list[dict]) -> dict[str, list[str]]:
    """Generated y-axis labels per scene, used as axis-finding evidence."""
    return scene_tick_labels(scenes)
