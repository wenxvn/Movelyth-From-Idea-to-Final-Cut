"""Cache keys, the dependency graph and assembly verification.

Two separate problems are solved here:

**Invalidation.**  "The file exists" is not a cache hit.  Every artefact is keyed by
the exact inputs that can change it (text, data, assets, fonts, recipes, code, aspect,
fps, policy), and the dependency graph says which downstream artefacts a change
invalidates.  A scene's key also includes its *neighbours*, because a transition
handle, a J-cut or a shared object crosses the scene boundary.

**Assembly.**  The renderer draws each scene for a whole number of frames and overlays
the transitions on top of those frames (the Movie component fades/slides between
scenes without shortening the timeline).  That policy has to be explicit, because
`TransitionSeries` would *subtract* the overlap: two 60-frame scenes with a 15-frame
overlap are 105 frames, not 120, and the narration would then be a second out of sync
for the rest of the film.
"""
from __future__ import annotations

from pathlib import Path

from .util import file_hash, fingerprint

# Which artefact invalidates which downstream artefacts.  Used to compute the closure.
DEPENDENTS: dict[str, set[str]] = {
    "research": {"evidence", "brief", "script", "sound", "render", "check"},
    "evidence": {"script", "sound", "render", "check"},
    "brief": {"script", "sound", "render", "check"},
    "script": {"sound", "render", "check"},
    "fonts": {"render", "check"},
    "theme": {"render", "check"},
    "recipes": {"script", "render", "check"},
    "parameters": {"script", "render", "check"},
    "policy": {"check"},
    "assets": {"render", "check"},
    "sound": {"render", "check"},
    "mix": {"render", "check"},
    "captions": {"render", "check"},
    "render": {"check"},
    "check": set(),          # terminal: nothing depends on the release decision itself
}

# The transition policy the renderer implements, stated once so a change is visible.
TRANSITION_POLICY = {
    "mode": "overlay",
    "detail": "转场叠加在相邻镜头各自的完整帧数之上（Movie.tsx），不从时间轴扣除重叠帧",
    "why": "TransitionSeries 会用重叠帧缩短总时长：60+60 帧重叠 15 帧只剩 105 帧，"
           "旁白按 120 帧编排就会在剩余全片错位",
    "handles": "相邻镜头共享的视觉衔接（共享对象、J-cut、跨场字幕）以 scene 边界为界，"
               "不写入额外帧；如需真正的 handle 必须在时间轴显式增加帧数并重算旁白",
    "total_frames": "sum(scene.frames)；composition 的 durationInFrames 必须与之一致",
}


def invalidated_by(changed: list[str]) -> list[str]:
    """Stages to drop for the given changed artefacts (transitive closure)."""
    pending = list(changed)
    result: set[str] = set()
    while pending:
        item = pending.pop()
        for dependent in DEPENDENTS.get(item, set()):
            if dependent not in result:
                result.add(dependent)
                pending.append(dependent)
    return sorted(result)


def scene_key(scene: dict, *, neighbours: tuple[dict, dict] | None = None,
              environment: dict | None = None) -> str:
    """Fingerprint of everything that can change how this scene looks or sounds.

    ``neighbours`` are the previous and next scenes: a transition handle or a shared
    subject crosses the boundary, so a change there must invalidate this scene too.
    """
    previous, following = neighbours or (None, None)
    return fingerprint({
        "scene": {key: scene.get(key) for key in
                  ("id", "narration", "heading", "layers", "actions", "events", "beats",
                   "captions", "frames", "layout", "style", "recipe", "function", "parameters",
                   "transition", "camera", "claim_ids", "emphasis", "cues", "hold_reason")},
        "previous": _edge(previous),
        "following": _edge(following),
        "environment": environment or {},
    })


def _edge(scene: dict | None) -> dict:
    if not scene:
        return {}
    return {"id": scene.get("id"), "transition": scene.get("transition"),
            "subject_ids": sorted({layer.get("subject_id") for layer in scene.get("layers") or []
                                   if layer.get("subject_id")}),
            "last_caption": (scene.get("captions") or [{}])[-1].get("text") if scene.get("captions") else None}


def scene_keys(timeline: dict, *, environment: dict | None = None) -> dict[str, str]:
    scenes = timeline.get("scenes") or []
    keys = {}
    for index, scene in enumerate(scenes):
        neighbours = (scenes[index - 1] if index else None,
                      scenes[index + 1] if index + 1 < len(scenes) else None)
        keys[str(scene.get("id"))] = scene_key(scene, neighbours=neighbours, environment=environment)
    return keys


def changed_scenes(previous: dict[str, str], current: dict[str, str]) -> list[str]:
    """Scene ids whose key changed, including neighbours of a changed scene."""
    changed = [scene_id for scene_id, key in current.items() if previous.get(scene_id) != key]
    order = list(current)
    expanded = set(changed)
    for scene_id in changed:
        index = order.index(scene_id)
        if index:
            expanded.add(order[index - 1])
        if index + 1 < len(order):
            expanded.add(order[index + 1])
    return sorted(expanded)


def verify_cached_file(path: Path, expected: str) -> dict:
    """A cache entry is valid only when the file exists and still hashes the same."""
    if not path.is_file():
        return {"valid": False, "reason": "文件不存在"}
    try:
        actual = file_hash(path)
    except OSError as exc:
        return {"valid": False, "reason": f"无法读取：{exc}"}
    if actual != expected:
        return {"valid": False, "reason": "hash 不一致（半文件或被篡改）", "actual": actual}
    return {"valid": True}


def assembly_report(composition: dict, timeline: dict, *, policy: dict | None = None) -> dict:
    """Frame arithmetic: the composition must be exactly the sum of its scenes."""
    policy = policy or TRANSITION_POLICY
    frames = [int(scene.get("frames") or 0) for scene in timeline.get("scenes") or []]
    problems = []
    if not frames:
        problems.append("时间轴没有镜头")
    if any(value <= 0 for value in frames):
        problems.append("存在帧数非正的镜头")
    total = sum(frames)
    expected = int(composition.get("frames") or 0)
    if expected and expected != total:
        problems.append(f"composition 帧数 {expected} 与镜头帧数之和 {total} 不一致")
    if policy.get("mode") == "overlay":
        # Under the overlay policy nothing may be subtracted from the timeline.
        if expected and expected < total:
            problems.append("时间轴帧数被转场扣除：overlay 策略下不应发生")
    return {"passed": not problems, "problems": problems, "scene_frames": frames,
            "total_frames": total, "composition_frames": expected, "policy": policy}


def verify_assembly(video: Path, *, expected_frames: int, fps: int, scenes: list[dict],
                    probe=None, samples=None) -> dict:
    """Check the encoded file against the timeline: fps, duration, audio, joins.

    ``probe`` returns ``{"duration", "has_audio", "width", "fps", "channels"}`` for the
    file; ``samples`` returns the mean luminance of frames at given second offsets, so
    black frames and duplicate frames at a join can be detected.
    """
    problems = []
    measured = probe(video) if probe else None
    if probe and measured is None:
        problems.append("无法读取成片")
    if measured:
        expected_seconds = expected_frames / fps
        if measured.get("duration") is not None and abs(float(measured["duration"]) - expected_seconds) > 0.25:
            problems.append(f"成片时长 {measured['duration']:.2f}s 与时间轴 {expected_seconds:.2f}s 不一致")
        if measured.get("fps") is not None and abs(float(measured["fps"]) - fps) > 0.01:
            problems.append(f"成片 fps {measured['fps']} 与项目 {fps} 不一致")
        if not measured.get("has_audio"):
            problems.append("成片没有音轨")
        if measured.get("channels") not in (None, 2):
            problems.append(f"成片声道数 {measured['channels']} 不是双声道")
    joins = []
    offset = 0
    for scene in scenes:
        joins.append((offset + int(scene.get("frames") or 0)) / fps)
        offset += int(scene.get("frames") or 0)
    if samples:
        luminance = samples([max(0.0, join - 0.05) for join in joins] +
                            [min(expected_frames / fps - 0.05, join + 0.05) for join in joins])
        if luminance is not None:
            dark = [round(value, 2) for value in luminance if value < 6]
            if dark:
                problems.append(f"接点附近出现黑帧（亮度 {dark[:3]}）")
    return {"passed": not problems, "problems": problems, "joins": [round(j, 3) for j in joins],
            "measured": measured}
