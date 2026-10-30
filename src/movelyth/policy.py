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

import math
import re
from typing import Literal

from pydantic import Field

from .charts import scene_tick_labels
from .models import Contract, Finding, Review

POLICY_VERSION = "3"

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
    has_failure = any(check.status == "fail" for check in checks)
    base = clean.passed or (softened and not has_failure and not kept_issues)
    if not base and not has_failure and not kept_issues:
        checks.append(CheckResult(check_id=f"review.{stage}.unexplained-rejection", source="model",
                                  status="unknown", severity="major", required=True,
                                  observation="审片未通过但没有可核对的阻断原因"))
    final = Review.model_validate({
        "passed": base and not has_failure and not kept_issues,
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
        content = report.get("content_check") or {}
        changed = content.get("changed") or []
        missing = content.get("missing") or []
        # A changed sign or magnitude is a meaning change, not a mishearing: it blocks.
        results.append(CheckResult(
            check_id=f"audio.{cut}.content", source="audio",
            status="fail" if changed else ("unknown" if missing else "pass"),
            severity="critical" if changed else "major",
            required=bool(changed), repairable=True,
            observation=("语音核对发现数值被改变：" + "；".join(
                f"{item['written']}（{item['reason']}）" for item in changed[:3])) if changed
                        else (f"语音核对未在转写中找到 {len(missing)} 处关键内容，需复听" if missing else ""),
            location={"cut": cut},
            evidence={"changed": changed[:5], "missing": missing[:5], "units": content.get("units")}))
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


CLAIM_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def source_checks(coverage: list[dict], *, stage: str = "research") -> list[CheckResult]:
    """Claim support against the snapshots that were actually fetched.

    An unfetched or unparsable source can never support a claim, and an excerpt
    that is absent from the snapshot is treated as invented rather than "roughly
    right".  A research record with no claims cannot pass the factual gate.
    """
    if not coverage:
        return [CheckResult(
            check_id=f"source.{stage}.no-claims", source="source", status="fail",
            severity="major", required=True, repairable=True,
            observation="研究没有主张—证据映射（claims 为空），关键事实无法核对")]
    results = []
    for entry in coverage:
        claim_id = entry["claim_id"]
        status = entry["status"]
        base = {"source": "source", "location": {"claim_id": claim_id,
                                                 "source_index": entry.get("source_index")},
                "evidence": {key: entry.get(key) for key in
                             ("source_url", "position", "content_sha256", "title", "detail")
                             if entry.get(key) is not None}}
        if status == "supported":
            results.append(CheckResult(check_id=f"source.{stage}.{claim_id}", status="pass",
                                       severity="major", required=True,
                                       observation=f"{claim_id} 已定位到来源节选", **base))
        elif status == "excerpt-missing":
            results.append(CheckResult(check_id=f"source.{stage}.{claim_id}", status="fail",
                                       severity="critical", required=True, repairable=True,
                                       observation=f"{claim_id} 的节选在抓取正文中找不到：{entry['statement'][:60]}",
                                       **base))
        elif status == "source-unavailable":
            results.append(CheckResult(check_id=f"source.{stage}.{claim_id}", status="fail",
                                       severity="major", required=True, repairable=True,
                                       observation=f"{claim_id} 的来源未取到：{entry.get('detail', '')[:120]}",
                                       **base))
        elif status == "source-missing":
            results.append(CheckResult(check_id=f"source.{stage}.{claim_id}", status="fail",
                                       severity="major", required=True, repairable=True,
                                       observation=f"{claim_id} 引用了不存在的来源", **base))
        else:
            results.append(CheckResult(check_id=f"source.{stage}.{claim_id}", status="unknown",
                                       severity="minor", required=False,
                                       observation=f"{claim_id} 状态未知：{status}", **base))
        if entry.get("scope") == "uncertain":
            results.append(CheckResult(
                check_id=f"source.{stage}.{claim_id}.uncertain", source="source", status="unknown",
                severity="minor", required=False,
                observation=f"{claim_id} 标注为不确定，正文必须保留适用条件",
                location={"claim_id": claim_id}, evidence={"scope": entry.get("scope")}))
    if not any(entry.get("importance") == "key" for entry in coverage):
        results.append(CheckResult(
            check_id=f"source.{stage}.no-key-claim", source="source", status="unknown",
            severity="minor", required=False,
            observation="所有主张都标为 supporting：核心结论缺少 key 主张"))
    return results


def claim_usage_checks(film: dict, coverage: list[dict]) -> list[CheckResult]:
    """After directing: do key claims reach a scene, and are there unsupported numbers?

    The second part is deliberately a warning, not a gate: a narration number can be
    a date, a count of steps or a teaching parameter.  It is reported with the
    numbers that appear nowhere in the evidence so a human can look, instead of
    silently passing or blocking every video.
    """
    results: list[CheckResult] = []
    used = {int(scene.get("source_index", -1)) for cut in ("long", "short")
            for scene in (film.get(cut) or {}).get("scenes", [])}
    for entry in coverage:
        if entry.get("importance") != "key" or entry["status"] != "supported":
            continue
        indices = {int(entry.get("source_index", -1)), *[int(i) for i in entry.get("evidence_refs") or []]}
        if used & indices:
            continue
        results.append(CheckResult(
            check_id=f"source.coverage.{entry['claim_id']}", source="source", status="fail",
            severity="major", required=True, repairable=True,
            observation=f"关键主张 {entry['claim_id']} 没有进入任何镜头：{entry['statement'][:60]}",
            location={"claim_id": entry["claim_id"]}))
    known_numbers: set[str] = set()
    for entry in coverage:
        known_numbers.update(CLAIM_NUMBER.findall(str(entry.get("statement", ""))))
        known_numbers.update(CLAIM_NUMBER.findall(str(entry.get("detail", ""))))
    for cut in ("long", "short"):
        for scene in (film.get(cut) or {}).get("scenes", []):
            for layer in scene.get("layers") or []:
                for series in layer.get("series") or []:
                    known_numbers.update(str(value) for value in series.get("values") or [])
                known_numbers.update(str(value) for value in layer.get("points") or [])
            unknown = [number for number in CLAIM_NUMBER.findall(scene.get("narration", ""))
                       if number not in known_numbers]
            if unknown:
                results.append(CheckResult(
                    check_id=f"source.coverage.{cut}.{scene.get('id', '?')}.numbers",
                    source="source", status="unknown", severity="minor", required=False,
                    observation="旁白里的数字没有出现在主张或受控数据中：" + "、".join(unknown[:5]),
                    location={"cut": cut, "scene_id": scene.get("id")},
                    evidence={"numbers": unknown[:10]}))
    results.extend(screen_claim_checks(film, coverage))
    return results


def _number_key(value) -> str | None:
    """Normalize displayed and sourced numbers without mistaking geometry for data."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return str(int(number)) if number.is_integer() else format(number, ".12g")


def _screen_content(scene: dict) -> tuple[str, set[str]]:
    """Collect graphic content and encoded data; subtitles are deliberately excluded."""
    text_parts: list[str] = []
    numbers: set[str] = set()

    def add_text(value) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        text_parts.append(text)
        numbers.update(_number_key(token) for token in CLAIM_NUMBER.findall(text)
                       if _number_key(token) is not None)

    for key in ("heading", "chapter", "takeaway", "metric"):
        add_text(scene.get(key))
    for value in scene.get("labels") or []:
        add_text(value)

    for layer in scene.get("layers") or []:
        for key in ("text", "axis", "source_note"):
            add_text(layer.get(key))
        for annotation in layer.get("annotations") or []:
            add_text(annotation.get("text"))
        for series in layer.get("series") or []:
            add_text(series.get("label"))
            numbers.update(key for value in series.get("values") or []
                           if (key := _number_key(value)) is not None)
        for node in layer.get("nodes") or []:
            for key in ("label", "value", "text"):
                add_text(node.get(key))
        for edge in layer.get("edges") or []:
            for key in ("label", "value", "text"):
                add_text(edge.get(key))
        for step in layer.get("steps") or []:
            add_text(step)
    return "\n".join(text_parts), numbers


def screen_claim_checks(film: dict, coverage: list[dict]) -> list[CheckResult]:
    """Check that supported claims have visible numeric/caveat witnesses.

    This is a structural audit, not proof of semantic understanding: it ignores
    subtitles so that repeated narration cannot count as a visual demonstration,
    and leaves any missing or ambiguous witness as ``unknown`` for human review.
    """
    results: list[CheckResult] = []
    boundary_groups = (
        ("only", ("仅", "只", "only")),
        ("condition", ("如果", "若", "当", "除非", "if", "when", "unless")),
        ("assumption", ("假设", "前提", "条件", "assuming", "provided that")),
        ("bound", ("至少", "至多", "不超过", "不低于", "at least", "at most", "no more than")),
    )
    illustrative_markers = ("示意", "演示", "本例", "自行构造", "illustrative", "example")

    for cut in ("long", "short"):
        scenes = (film.get(cut) or {}).get("scenes", [])
        for entry in coverage:
            if entry.get("importance") != "key" or entry.get("status") != "supported":
                continue
            claim_id = str(entry.get("claim_id") or "claim")
            linked = [scene for scene in scenes if claim_id in (scene.get("claim_ids") or [])]
            if not linked:
                source_indices = {int(entry.get("source_index", -1)),
                                  *[int(i) for i in entry.get("evidence_refs") or []]}
                if any(int(scene.get("source_index", -1)) in source_indices for scene in scenes):
                    results.append(CheckResult(
                        check_id=f"source.visual.{cut}.{claim_id}.binding", source="source",
                        status="unknown", severity="minor", required=False,
                        observation=f"{claim_id} 只通过来源编号间接进入镜头，未显式绑定 claim_ids，无法核实其画面见证",
                        location={"cut": cut, "claim_id": claim_id}))
                continue

            visible_text_parts: list[str] = []
            visible_numbers: set[str] = set()
            linked_data_numbers: set[str] = set()
            for scene in linked:
                text, numbers = _screen_content(scene)
                visible_text_parts.append(text)
                visible_numbers.update(numbers)
                for layer in scene.get("layers") or []:
                    for series in layer.get("series") or []:
                        linked_data_numbers.update(key for value in series.get("values") or []
                                                   if (key := _number_key(value)) is not None)
                    for node in layer.get("nodes") or []:
                        value = node.get("value")
                        if value is not None and (key := _number_key(value)) is not None:
                            linked_data_numbers.add(key)
            screen_text = "\n".join(visible_text_parts).casefold()
            statement = str(entry.get("statement") or "")
            expected_numbers = {_number_key(token) for token in CLAIM_NUMBER.findall(statement)}
            expected_numbers.discard(None)
            missing_numbers = sorted(expected_numbers - visible_numbers, key=lambda value: (float(value), value))
            results.append(CheckResult(
                check_id=f"source.visual.{cut}.{claim_id}.numbers", source="source",
                status="unknown" if missing_numbers else "pass", severity="minor", required=False,
                observation=(f"{claim_id} 主张中的数值 {', '.join(missing_numbers[:8])} 未在关联图形或可见文字中找到；字幕不计作演示"
                             if missing_numbers else f"{claim_id} 的数值可在关联图形或可见文字中找到"),
                location={"cut": cut, "claim_id": claim_id},
                evidence={"missing": missing_numbers, "visible_numbers": sorted(visible_numbers)}))

            scope = entry.get("scope")
            if scope == "illustrative":
                marked = any(marker in screen_text for marker in illustrative_markers)
                results.append(CheckResult(
                    check_id=f"source.visual.{cut}.{claim_id}.scope", source="source",
                    status="pass" if marked else "unknown", severity="minor", required=False,
                    observation=("示意范围在关联画面文字中有标记" if marked else
                                 f"{claim_id} 是示意性主张，但关联画面未标明示意/本例范围"),
                    location={"cut": cut, "claim_id": claim_id},
                    evidence={"scope": scope, "illustrative_marker_visible": marked}))
            elif scope == "uncertain":
                results.append(CheckResult(
                    check_id=f"source.visual.{cut}.{claim_id}.scope", source="source",
                    status="unknown", severity="minor", required=False,
                    observation=f"{claim_id} 的适用条件仍需人工确认是否在画面中保留",
                    location={"cut": cut, "claim_id": claim_id},
                    evidence={"scope": scope, "visible_text": screen_text[:240]}))

            missing_boundary = [name for name, markers in boundary_groups
                                if any(marker in statement.casefold() for marker in markers)
                                and not any(marker in screen_text for marker in markers)]
            if missing_boundary:
                results.append(CheckResult(
                    check_id=f"source.visual.{cut}.{claim_id}.boundary", source="source",
                    status="unknown", severity="minor", required=False,
                    observation=f"{claim_id} 的限定词 {', '.join(missing_boundary)} 未在关联画面文字中找到；图形是否表达该边界仍需复核",
                    location={"cut": cut, "claim_id": claim_id},
                    evidence={"missing_boundary_groups": missing_boundary, "scope": scope}))

            source_note_present = any((layer.get("source_note") or "").strip()
                                      for scene in linked for layer in scene.get("layers") or [])
            unsupported_data = sorted(linked_data_numbers - expected_numbers,
                                      key=lambda value: (float(value), value))
            illustrative_note = any(marker in screen_text for marker in illustrative_markers)
            if unsupported_data and not source_note_present and not illustrative_note:
                results.append(CheckResult(
                    check_id=f"source.visual.{cut}.{claim_id}.reverse", source="source",
                    status="unknown", severity="minor", required=False,
                    observation=f"{claim_id} 关联图形含有无法回溯到主张或来源说明的数值：{', '.join(unsupported_data[:8])}",
                    location={"cut": cut, "claim_id": claim_id},
                    evidence={"unmapped_data_numbers": unsupported_data}))
    return results


def mix_checks(report: dict, *, cut: str) -> list[CheckResult]:
    """Voice presence and stem balance, measured on stems before encoding."""
    if not report:
        return [CheckResult(check_id=f"audio.{cut}.mix", source="audio", status="unknown",
                            severity="minor", required=False,
                            observation="没有混音报告（未生成 stems）", location={"cut": cut})]
    results = []
    voice = report.get("voice") or {}
    results.append(CheckResult(
        check_id=f"audio.{cut}.voice-stem", source="audio",
        status="pass" if voice.get("present") else "fail",
        severity="critical", required=True, repairable=True,
        observation="" if voice.get("present") else
        f"人声轨缺失或几乎全静音（{voice.get('reason') or voice.get('audible_share')}）",
        location={"cut": cut}, evidence={"voice": voice}))
    balance = report.get("balance") or {}
    results.append(CheckResult(
        check_id=f"audio.{cut}.balance", source="audio",
        status="pass" if balance.get("ok", True) else "fail",
        severity="major", required=True, repairable=True,
        observation="；".join(balance.get("problems") or []), location={"cut": cut},
        evidence=balance))
    onsets = report.get("onsets") or {}
    if onsets.get("checked"):
        results.append(CheckResult(
            check_id=f"audio.{cut}.onsets", source="audio",
            status="pass" if not onsets.get("missing") else "unknown",
            severity="minor", required=False,
            observation=("有 %d 个声音事件没有测到能量" % len(onsets.get("missing") or []))
                        if onsets.get("missing") else "",
            location={"cut": cut}, evidence=onsets))
    ducking = report.get("ducking") or {}
    if ducking:
        results.append(CheckResult(
            check_id=f"audio.{cut}.ducking", source="audio",
            status="pass" if ducking.get("ok", True) else "unknown",
            severity="minor", required=False, observation=ducking.get("note", ""),
            location={"cut": cut}, evidence=ducking))
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
