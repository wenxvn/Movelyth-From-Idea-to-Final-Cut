"""Layout pre-check and animatic: find whole-film problems before the final encode.

Two cheap stages sit between the render and the delivery:

* a **layout dry-run** over the resolved timeline (fonts and assets are ready by
  then), which looks at reading speed, caption length, action extremes, camera range,
  asset references and unexplained holds;
* a **full-length low-resolution animatic** rendered with the real voice, captions,
  pauses, sound events and transitions — not a twelve-second teaser.

The sampling plan names *why* each moment is inspected (opening, event, transition,
caption change, motion extreme, anomaly) so a review cannot be reduced to one pretty
frame per scene.
"""
from __future__ import annotations

from .models import Scene
from .scenedsl import regions

MAX_CAPTION_CHARS_PER_SECOND = {"long": 9.0, "short": 8.0}
MIN_CAPTION_SECONDS = 1.0
MAX_CAPTION_LINES = 2
HOLD_WITHOUT_REASON_SECONDS = 1.5
CAMERA_SCALE_LIMIT = 1.12


def _caption_metrics(scene: dict, cut: str) -> list[str]:
    problems = []
    for page in scene.get("captions") or []:
        seconds = max(1e-3, float(page["end"]) - float(page["start"]))
        characters = len(str(page.get("text") or ""))
        rate = characters / seconds
        if rate > MAX_CAPTION_CHARS_PER_SECOND[cut]:
            problems.append(f"镜头 {scene['id']} 字幕过快：{rate:.1f} 字/秒（上限 "
                            f"{MAX_CAPTION_CHARS_PER_SECOND[cut]}）")
        if seconds < MIN_CAPTION_SECONDS:
            problems.append(f"镜头 {scene['id']} 字幕闪现：{seconds:.2f}s 短于 {MIN_CAPTION_SECONDS}s")
        if not str(page.get("text") or "").strip():
            problems.append(f"镜头 {scene['id']} 有空白字幕页")
    return problems


def _action_extremes(scene: dict) -> list[str]:
    problems = []
    for action in scene.get("actions_resolved") or []:
        if action.get("degrees") is not None and abs(float(action["degrees"])) > 360:
            problems.append(f"镜头 {scene['id']} 的旋转超过 360°")
        if action.get("scale") is not None and float(action["scale"]) <= 0.15:
            problems.append(f"镜头 {scene['id']} 的缩放小于 0.15，内容会消失")
    return problems


def _holds(scene: dict) -> list[str]:
    """A long gap with no action, event or caption change needs a stated reason."""
    warnings = []
    duration = float(scene.get("duration") or 0)
    if duration < 6:
        return warnings
    marks = [0.0, duration]
    marks.extend(float(action["from"]) * duration for action in scene.get("actions_resolved") or [])
    marks.extend(float(action["to"]) * duration for action in scene.get("actions_resolved") or [])
    marks.extend(float(event["at"]) for event in scene.get("events_resolved") or [])
    marks.extend(float(page["start"]) for page in scene.get("captions") or [])
    marks.extend(float(page["end"]) for page in scene.get("captions") or [])
    marks = sorted(mark for mark in marks if 0 <= mark <= duration)
    gap = max((b - a for a, b in zip(marks, marks[1:], strict=False)), default=0.0)
    if gap > HOLD_WITHOUT_REASON_SECONDS and not scene.get("hold_reason"):
        warnings.append(f"镜头 {scene['id']} 有 {gap:.1f}s 没有动作/事件/字幕变化，"
                        "但未写 hold_reason")
    return warnings


def layout_precheck(timelines: dict, config: dict, assets: list[str] | None = None,
                    library_ids: tuple[str, ...] | list[str] = ()) -> dict:
    """Deterministic dry-run over the resolved timeline; no rendering involved."""
    known_assets = set(library_ids or ())
    report: dict = {"cuts": {}, "problems": [], "warnings": [], "checked_scenes": 0}
    for cut, timeline in timelines.items():
        cut_report = {"scenes": [], "problems": [], "warnings": []}
        portrait = cut == "short"
        for raw in timeline.get("scenes") or []:
            scene = Scene.model_validate({key: raw[key] for key in Scene.model_fields if key in raw})
            problems = _caption_metrics(raw, cut)
            problems.extend(_action_extremes(raw))
            warnings = list(raw.get("layout_warnings") or []) + _holds(raw)
            camera = raw.get("camera", "none")
            if camera != "none":
                boxes = regions("portrait" if portrait else "landscape", scene.layout)
                if not boxes:
                    problems.append(f"镜头 {scene.id} 的布局 {scene.layout} 不存在")
            from .captions_qc import collision_report, cue_report, text_layer_report

            caption_report = cue_report(raw, cut, orientation="portrait" if portrait else "landscape")
            problems.extend(caption_report["problems"])
            warnings.extend(caption_report["warnings"])
            problems.extend(collision_report(raw, orientation="portrait" if portrait else "landscape"))
            text_report = text_layer_report(raw, orientation="portrait" if portrait else "landscape",
                                            cut=cut)
            problems.extend(text_report["problems"])
            warnings.extend(text_report["warnings"])
            for layer in scene.layers:
                if layer.type == "image" and layer.data_ref:
                    internal = layer.data_ref.startswith("svd") or layer.data_ref in {"svd_1", "svd_4",
                                                                                     "svd_12", "svd_32"}
                    if known_assets and not internal and layer.data_ref not in known_assets:
                        problems.append(f"镜头 {scene.id} 引用了未登记的素材 {layer.data_ref}")
            if scene.recipe:
                from .recipes import check_scene, validate_scene_recipe

                problems.extend(validate_scene_recipe(scene))
                problems.extend(check_scene(scene))
            cut_report["scenes"].append({"id": scene.id, "problems": problems, "warnings": warnings})
            cut_report["problems"].extend(problems)
            cut_report["warnings"].extend(warnings)
            report["checked_scenes"] += 1
        report["cuts"][cut] = cut_report
        report["problems"].extend(cut_report["problems"])
        report["warnings"].extend(cut_report["warnings"])
    report["passed"] = not report["problems"]
    return report


def sampling_plan(timelines: dict, fps: int) -> list[dict]:
    """When to look at the animatic, and why. Each entry is a named reason."""
    plan: list[dict] = []
    for cut, timeline in timelines.items():
        offset = 0.0
        duration = float(timeline.get("seconds") or 0)
        plan.append({"cut": cut, "seconds": 0.2, "reason": "opening"})
        for scene in timeline.get("scenes") or []:
            length = float(scene.get("duration") or 0)
            scene_start = offset
            for event in scene.get("events_resolved") or []:
                moment = scene_start + float(event["at"])
                plan.append({"cut": cut, "seconds": round(moment, 2),
                             "reason": f"event:{event['kind']}:{event['id']}"})
            for action in scene.get("actions_resolved") or []:
                # The midpoint of a move is where an unintended overlap would show.
                moment = scene_start + (float(action["from"]) + float(action["to"])) / 2 * length
                plan.append({"cut": cut, "seconds": round(moment, 2),
                             "reason": f"motion-extreme:{action['kind']}"})
            for index, page in enumerate(scene.get("captions") or []):
                if index:
                    plan.append({"cut": cut, "seconds": round(scene_start + float(page["start"]), 2),
                                 "reason": "caption-change"})
            plan.append({"cut": cut, "seconds": round(scene_start + length * 0.5, 2),
                         "reason": f"scene-midpoint:{scene['id']}"})
            offset += length
        plan.append({"cut": cut, "seconds": max(0.0, duration - 0.3), "reason": "ending"})
    deduped, seen = [], set()
    for item in plan:
        key = (item["cut"], item["seconds"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def animatic_spec(cuts: list[dict], *, scale: float = 0.35) -> dict:
    """Extra render options for the full-length low-resolution animatic."""
    return {"animaticScale": scale, "animaticCuts": [cut["name"] for cut in cuts],
            "note": "整条真实时间轴的低清草片，使用真实配音/字幕/停顿/音效/转场"}


def compare_animatic(animatic: dict, final: dict, timelines: dict, fps: int,
                     probe=None) -> dict:
    """The final encode must be the same version as the animatic, not a cousin.

    ``probe`` is an optional callable returning ``{"duration", "has_audio"}`` for a
    media file; when given, the animatic itself is measured instead of trusted.
    """
    problems = []
    for cut, timeline in timelines.items():
        entry = (animatic.get(cut) or {})
        final_entry = (final.get(cut) or {})
        if not entry.get("animatic"):
            problems.append(f"{cut} 缺少整片草片")
            continue
        if abs(float(entry.get("frames", 0)) - float(final_entry.get("frames", -1))) > 0:
            problems.append(f"{cut} 草片与成片帧数不一致")
        if abs(float(timeline.get("seconds", 0)) - float(final_entry.get("frames", 0)) / fps) > 0.2:
            problems.append(f"{cut} 成片时长与时间轴不一致")
        if not timeline.get("scenes"):
            problems.append(f"{cut} 时间轴为空")
        if probe and entry.get("animatic"):
            measured = probe(entry["animatic"])
            if measured is None:
                problems.append(f"{cut} 草片无法读取")
            else:
                if not measured.get("has_audio"):
                    problems.append(f"{cut} 草片没有音轨：不是带真实配音的整片草片")
                if measured.get("duration") is not None and abs(
                        float(measured["duration"]) - float(timeline.get("seconds") or 0)) > 0.3:
                    problems.append(f"{cut} 草片时长与时间轴不一致")
    return {"passed": not problems, "problems": problems,
            "note": "草片与成片一致只说明版本相同；不等于已连续看听（V5）"}
