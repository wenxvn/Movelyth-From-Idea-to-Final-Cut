"""Asset requests, matching and aspect-aware cropping.

An ``AssetRequest`` describes what a *shot* needs — subject, action, setting, framing,
duration, aspect, authenticity and licence — not just a keyword.  Matching ranks the
registered local library against that description and records why each candidate was
accepted or rejected, so "the picture was wrong" becomes a reviewable decision rather
than an unexplained choice.

Cropping is computed, not guessed: the crop keeps the asset's declared focus point and
must contain the whole subject box, otherwise the candidate is rejected (a portrait
crop that decapitates the subject is worse than no asset at all).
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field

from .assets import AssetError, library_root, load_library, resolve
from .models import Contract

MAX_CANDIDATES = 6
MIN_SUBJECT_SHARE = 0.35   # the subject must occupy at least this share of a real crop
MIN_SCORE = 2.0            # below this a picture is unrelated, not a substitute
ASPECTS = {"landscape": 16 / 9, "portrait": 9 / 16}


class AssetRequest(Contract):
    """What one shot needs from a picture."""

    subject: str = Field(min_length=1, max_length=40)
    action: str = Field(default="", max_length=40)
    setting: str = Field(default="", max_length=40)
    composition: str = Field(default="", max_length=40)
    min_seconds: float = Field(default=0.0, ge=0, le=600)
    orientations: list[str] = Field(default_factory=lambda: ["landscape", "portrait"],
                                    min_length=1, max_length=2)
    authenticity: str = Field(default="illustration", max_length=20)
    license_required: bool = True
    must_not: list[str] = Field(default_factory=list, max_length=4)

    def __init__(self, **data):
        super().__init__(**data)
        if any(value not in {"landscape", "portrait"} for value in self.orientations):
            raise ValueError("orientations 只能是 landscape/portrait")
        if self.authenticity not in {"evidence", "atmosphere", "illustration"}:
            raise ValueError("authenticity 只能是 evidence/atmosphere/illustration")


def _entry_text(entry: dict) -> str:
    return " ".join(str(entry.get(key) or "") for key in
                    ("subject", "action", "setting", "tags", "description", "source", "author")).casefold()


def _words(text: str) -> set[str]:
    return {word for word in re.split(r"[^0-9a-z\u4e00-\u9fff]+", str(text or "").casefold()) if word}


def score(entry: dict, request: AssetRequest) -> dict:
    """Match score with the reasons that produced it."""
    text = _entry_text(entry)
    reasons = []
    total = 0.0
    if request.subject and request.subject.casefold() in text:
        total += 3.0
        reasons.append(f"主体匹配“{request.subject}”")
    for field in ("action", "setting", "composition"):
        value = getattr(request, field)
        if value and value.casefold() in text:
            total += 1.5
            reasons.append(f"{field} 匹配“{value}”")
    overlap = _words(request.subject) & _words(text)
    if overlap:
        total += 0.5 * len(overlap)
        reasons.append("关键词重合：" + "、".join(sorted(overlap)[:4]))
    if request.license_required:
        if all(str(entry.get(field) or "").strip() for field in ("license", "author", "source", "scope")):
            total += 0.5
            reasons.append("授权信息完整")
    return {"score": round(total, 3), "reasons": reasons}


def rejected(entry: dict, request: AssetRequest) -> list[str]:
    """Hard rejections: these cannot be fixed by a better crop or a nicer preview."""
    problems = []
    if entry.get("valid") is False:
        problems.append(f"素材已失效：{entry.get('invalid_reason') or '需重新登记'}")
    if request.license_required:
        missing = [field for field in ("license", "author", "source", "scope")
                   if not str(entry.get(field) or "").strip()]
        if missing:
            problems.append("授权信息缺失：" + "、".join(missing))
    forbidden = [word for word in request.must_not if word and word.casefold() in _entry_text(entry)]
    if forbidden:
        problems.append("命中禁止含义：" + "、".join(forbidden))
    if request.authenticity == "evidence" and entry.get("authenticity") == "illustration":
        problems.append("需要真实证据，但素材标注为示意")
    return problems


def plan_crop(path: Path, orientation: str, *, focus: tuple[float, float] | None = None,
              subject_box: dict | None = None) -> dict:
    """Crop rectangle that keeps the focus point and the whole subject.

    ``focus`` is a relative point (0–1); ``subject_box`` is a relative box.  The crop
    has the target aspect, is centred on the focus point, clamped inside the source,
    and is rejected when the subject would fall outside it.
    """
    target = ASPECTS[orientation]
    width, height = _dimensions(path)
    if width is None:
        return {"ok": True, "skipped": "矢量或无法读取尺寸的素材按 contain 处理，不裁切",
                "orientation": orientation}
    fx, fy = focus or (0.5, 0.5)
    if height * target <= width:      # crop the width
        crop_h = height
        crop_w = height * target
    else:
        crop_w = width
        crop_h = width / target
    left = min(max(0.0, fx * width - crop_w / 2), width - crop_w)
    top = min(max(0.0, fy * height - crop_h / 2), height - crop_h)
    result = {"ok": True, "orientation": orientation, "source": [width, height],
              "crop": [round(left), round(top), round(crop_w), round(crop_h)],
              "focus": [fx, fy], "target_aspect": round(target, 4)}
    if subject_box:
        sx0 = subject_box["x"] * width
        sy0 = subject_box["y"] * height
        sx1 = (subject_box["x"] + subject_box["w"]) * width
        sy1 = (subject_box["y"] + subject_box["h"]) * height
        inside = (sx0 >= left - 0.5 and sy0 >= top - 0.5
                  and sx1 <= left + crop_w + 0.5 and sy1 <= top + crop_h + 0.5)
        share = (subject_box["w"] * width * subject_box["h"] * height) / (crop_w * crop_h)
        cropped = crop_w * crop_h < 0.95 * width * height
        result["subject_inside"] = inside
        result["subject_share"] = round(share, 3)
        if not inside:
            result["ok"] = False
            result["reason"] = "裁切会切掉主体"
        elif cropped and share < MIN_SUBJECT_SHARE:
            # Only a *crop* can make the subject too small.  If the source itself is
            # already the frame, rejecting it would just mean "no asset at all".
            result["ok"] = False
            result["reason"] = f"裁切后主体只占 {share:.0%}，太小"
    return result


def _dimensions(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() == ".svg":
        return None, None
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def candidates(workspace: Path, request: AssetRequest) -> dict:
    """Ranked candidates with rejection reasons; bounded, never an endless search."""
    data = load_library(workspace)
    accepted, refused = [], []
    for asset_id, entry in sorted(data["assets"].items()):
        problems = rejected(entry, request)
        if problems:
            refused.append({"id": asset_id, "reasons": problems})
            continue
        scored = score(entry, request)
        accepted.append({"id": asset_id, "score": scored["score"], "reasons": scored["reasons"],
                         "tags": entry.get("tags") or [], "author": entry.get("author"),
                         "license": entry.get("license"), "source": entry.get("source")})
    accepted.sort(key=lambda item: (-item["score"], item["id"]))
    return {"request": request.model_dump(), "candidates": accepted[:MAX_CANDIDATES],
            "rejected": refused[:MAX_CANDIDATES],
            "exhausted": len(accepted) > MAX_CANDIDATES}


def choose(workspace: Path, request: AssetRequest, *, orientation: str) -> dict:
    """Pick the best candidate whose crop survives, or report why none does."""
    ranked = candidates(workspace, request)
    skipped = []
    for candidate in ranked["candidates"]:
        if candidate["score"] < MIN_SCORE:
            # A licence-clean but unrelated picture is worse than no picture: it would
            # claim to show something it does not.
            skipped.append({"id": candidate["id"], "score": candidate["score"],
                            "reason": "相关度不足，不能当作替代素材"})
            continue
        entry = load_library(workspace)["assets"][candidate["id"]]
        try:
            path = resolve(workspace, candidate["id"])
        except AssetError as exc:
            candidate["reasons"].append(str(exc))
            continue
        crop = plan_crop(path, orientation, focus=tuple(entry.get("focus") or (0.5, 0.5)),
                         subject_box=entry.get("subject_box"))
        if not crop["ok"]:
            candidate["reasons"].append(crop.get("reason", "裁切不合格"))
            continue
        return {"chosen": candidate["id"], "score": candidate["score"],
                "reasons": candidate["reasons"], "crop": crop,
                "provenance": {"author": entry.get("author"), "license": entry.get("license"),
                               "source": entry.get("source"), "scope": entry.get("scope"),
                               "sha256": entry.get("sha256"), "added_at": entry.get("added_at")},
                "candidates": ranked["candidates"], "rejected": ranked["rejected"],
                "skipped": skipped}
    return {"chosen": "",
            "reason": "没有可用素材：候选为空、被授权/含义规则拒绝、相关度不足，或裁切会切掉主体",
            "candidates": ranked["candidates"], "rejected": ranked["rejected"],
            "skipped": skipped}


def record_decision(job: Path, decision: dict) -> Path:
    """Persist the decision next to the episode so a bad picture can be traced."""
    from .util import atomic_json

    path = job / "asset-decisions.json"
    existing = []
    if path.is_file():
        from .util import read_json

        try:
            existing = read_json(path).get("decisions") or []
        except (OSError, ValueError):
            existing = []
    existing.append(decision)
    atomic_json(path, {"decisions": existing[-20:]})
    return path


def library_metadata(workspace: Path) -> dict:
    """Which metadata fields the registered assets actually carry."""
    data = load_library(workspace)
    keys = ("subject", "action", "setting", "tags", "focus", "subject_box", "authenticity")
    return {"assets": len(data["assets"]),
            "with_metadata": sum(1 for entry in data["assets"].values()
                                 if any(entry.get(key) for key in keys)),
            "fields": {key: sum(1 for entry in data["assets"].values() if entry.get(key))
                       for key in keys},
            "root": str(library_root(workspace))}
