from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .media import ffmpeg, ffprobe
from .util import run

# Delivery loudness.  B站 normalises anything above -28 LUFS up to -14 LUFS and
# 抖音 sits around -14 to -15, so matching the platform here avoids a second,
# uncontrolled gain pass on upload.
LOUDNESS_TARGET = {"integrated_lufs": -14.0, "true_peak_db": -1.5, "lra": 11.0}

# Motion review.  Sampling at 4 fps keeps a 5-minute film cheap while still
# resolving a frozen shot or a drift that lasts more than a second.
MOTION_GRID = (8, 6)
MOTION_SAMPLE_FPS = 4
EDGE_THRESHOLD = 40
CELL_CHANGE_PIXELS = 6
FULL_FRAME_SHARE = 0.6
FULL_FRAME_SECONDS = 2.0
SCENE_BOUNDARY_GUARD = 0.6
# A shot that holds one frozen frame for this long is reported; a scene that
# animates, pauses, then animates again is normal (real cuts peak around 3–4 s).
STILL_MIN_SECONDS = 5.0


def measure_loudness(path: Path) -> dict:
    """Pass one: measure the programme so pass two can normalise without guessing."""
    target = LOUDNESS_TARGET
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-af",
         (f"loudnorm=I={target['integrated_lufs']}:TP={target['true_peak_db']}"
          f":LRA={target['lra']}:print_format=json"), "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, check=False)
    text = result.stderr
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {"status": "unavailable", "reason": "ffmpeg 没有返回响度测量结果"}
    try:
        measured = json.loads(text[start:end + 1])
    except ValueError:
        return {"status": "unavailable", "reason": "响度测量结果不是有效 JSON"}
    return {"status": "measured",
            **{key: measured.get(key) for key in
               ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}}


def loudness_filter(measured: dict) -> str:
    """Pass two filter.  Falls back to dynamic mode when the measurement is unusable."""
    target = LOUDNESS_TARGET
    base = (f"loudnorm=I={target['integrated_lufs']}:TP={target['true_peak_db']}"
            f":LRA={target['lra']}")
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    try:
        values = {key: float(measured[key]) for key in keys}
    except (KeyError, TypeError, ValueError):
        return f"{base},aresample=48000"
    if not all(math.isfinite(value) for value in values.values()):
        # A silent mix measures -inf; linear mode would divide by zero.
        return f"{base},aresample=48000"
    return (f"{base}:measured_I={values['input_i']}:measured_TP={values['input_tp']}"
            f":measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}"
            f":offset={values['target_offset']}:linear=true,aresample=48000")


def mux_with_loudness(video: Path, mix: Path, output: Path, *, log: Path | None = None) -> dict:
    """Mux the render with the mix and hit the loudness target in two passes."""
    measured = measure_loudness(mix)
    run([ffmpeg(), "-y", "-v", "error", "-i", str(video), "-i", str(mix),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", loudness_filter(measured), "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(output)], timeout=900, log=log)
    return {"target": dict(LOUDNESS_TARGET), "measurement": measured,
            "mode": "linear" if "measured_I" in loudness_filter(measured) else "dynamic"}


def _ebur128(path: Path) -> dict:
    """Independent read-back of the delivered file, so the mux is not trusted blindly."""
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path),
                             "-af", "ebur128=peak=true", "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=900, check=False)
    text = result.stderr
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else ""

    def number(pattern: str):
        match = re.search(pattern, tail)
        if not match or match.group(1) == "-inf":
            return None
        return float(match.group(1))

    return {"integrated_lufs": number(r"I:\s+(-?[\d.]+|-inf)\s+LUFS"),
            "true_peak_db": number(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS")}


def duration_policy(config: dict, cut: str) -> dict:
    target = config[f"{cut}_seconds"]
    low = config.get(f"{cut}_min_seconds", target * 0.55)
    high = config.get(f"{cut}_max_seconds", target * 1.55)
    if not 0 < low <= target <= high:
        raise ValueError(f"{cut} 时长范围必须满足 0 < min <= target <= max")
    return {"target_seconds": target, "minimum_seconds": low, "maximum_seconds": high,
            "target_is_approximate": True}


def verify_video(path: Path, *, width: int, height: int, seconds: float, fps: int,
                 policy: dict | None = None, loudness_target: float | None = None) -> dict:
    """Decode the actual deliverable, inspect stream metadata, signal and temporal samples."""
    result = run([ffmpeg(), "-hide_banner", "-nostats", "-threads", "2", "-i", str(path),
                  "-map", "0:v:0", "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"], timeout=600)
    text = result.stderr
    metadata = json.loads(run([ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json",
                               str(path)], timeout=30).stdout)
    video = next((s for s in metadata["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in metadata["streams"] if s["codec_type"] == "audio"), {})
    numerator, denominator = (int(s) for s in video.get("avg_frame_rate", "0/1").split("/"))
    frame_rate = numerator / denominator if denominator else 0
    peak = re.search(r"max_volume: (-?[\d.]+) dB", text)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", text)
    actual_seconds = float(metadata["format"]["duration"])
    checks = {
        "full_decode": True,
        "h264": video.get("codec_name") == "h264",
        "aac": audio.get("codec_name") == "aac",
        "dimensions": (video.get("width"), video.get("height")) == (width, height),
        "fps": abs(frame_rate - fps) < 0.01,
        "duration_matches_timeline": actual_seconds is not None and abs(actual_seconds - seconds) <= 0.2,
        "audible": bool(mean and float(mean[1]) > -40),
        "no_clipping": bool(peak and float(peak[1]) < -0.2),
    }
    if policy:
        checks["requested_duration_range"] = policy["minimum_seconds"] <= actual_seconds <= policy["maximum_seconds"]
    loudness = _ebur128(path)
    if loudness_target is not None:
        measured_lufs = loudness["integrated_lufs"]
        checks["loudness_matches_target"] = (measured_lufs is not None
                                             and abs(measured_lufs - loudness_target) <= 1.5)
        checks["true_peak_below_ceiling"] = (loudness["true_peak_db"] is None
                                             or loudness["true_peak_db"] <= -0.5)
    sample = subprocess.run([ffmpeg(), "-v", "error", "-threads", "2", "-i", str(path),
                             "-vf", "fps=2,scale=128:72,format=gray", "-an", "-f", "rawvideo", "-"],
                            capture_output=True, timeout=300, check=True)
    frames = np.frombuffer(sample.stdout, dtype=np.uint8).reshape(-1, 72, 128)
    diffs = np.abs(np.diff(frames.astype(np.float32), axis=0)).mean(axis=(1, 2)) if len(frames) > 1 else np.array([])
    # Median, not mean: one big cut should not make a five-minute still frame look
    # like a moving picture (V1 sampled at 1 fps and averaged, which did exactly that).
    movement = float(np.median(diffs)) if diffs.size else 0.0
    static_share = float((diffs < 0.12).mean()) if diffs.size else 1.0
    checks["moving_picture"] = movement > 0.12
    checks["not_black"] = bool(len(frames) and np.mean(frames) > 6)
    return {"passed": all(checks.values()), "checks": checks, "duration": actual_seconds,
            "timeline_seconds": seconds, "duration_policy": policy,
            "width": video.get("width"), "height": video.get("height"), "fps": frame_rate,
            "max_volume_db": float(peak[1]) if peak else None,
            "mean_volume_db": float(mean[1]) if mean else None,
            "audio_signal": {"mean_volume_db": float(mean[1]) if mean else None,
                             "max_volume_db": float(peak[1]) if peak else None,
                             "meaning": "audible 只表示音轨非静音；不表示发音、语速或听感正确"},
            "mean_sample_motion": round(movement, 3),
            "static_sample_share": round(static_share, 3),
            "audio_listened": False,
            "loudness": loudness, "loudness_target_lufs": loudness_target,
            "asr_checked": False, "full_motion_aesthetic_review": False}


def _longest_run(values: list[bool]) -> int:
    """Length of the longest consecutive run of True."""
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def motion_report(video: Path, scenes: list[dict], fps: int, *, portrait: bool) -> dict:
    """Per-scene stillness and full-frame motion, measured on the encoded file.

    A single average frame difference hides two different defects: a scene that
    never moves (the picture is frozen while the voice talks) and a shot that
    drifts or jitters as a whole (a zoom, a shake, sub-pixel wobble).  This samples
    at :data:`MOTION_SAMPLE_FPS`, judges change only in grid cells that actually
    hold content, and excludes scene fades, which legitimately move every cell.
    """
    width, height = (180, 320) if portrait else (320, 180)
    gx, gy = MOTION_GRID
    cell_w, cell_h = width // gx, height // gy
    sample = subprocess.run([ffmpeg(), "-v", "error", "-threads", "2", "-i", str(video),
                             "-vf", f"fps={MOTION_SAMPLE_FPS},scale={width}:{height},format=gray",
                             "-an", "-f", "rawvideo", "-"],
                            capture_output=True, timeout=600, check=True)
    frame_bytes = width * height
    count = len(sample.stdout) // frame_bytes
    if count < 3:
        return {"status": "unavailable", "reason": "成片帧数不足，未做运动分析",
                "sample_fps": MOTION_SAMPLE_FPS}
    frames = np.frombuffer(sample.stdout[:count * frame_bytes], dtype=np.uint8)
    frames = frames.reshape(count, height, width)
    # Trim to whole grid cells: 180 wide / 8 columns is 22.5, so the last column is dropped.
    frames = frames[:, :cell_h * gy, :cell_w * gx]

    spans, offset = [], 0
    for scene in scenes:
        length = max(1, int(scene["frames"]))
        spans.append((scene["id"], offset / fps, (offset + length) / fps))
        offset += length
    boundaries = [start for _sid, start, _end in spans] + [spans[-1][2] if spans else 0.0]

    def scene_at(seconds: float) -> str:
        for scene_id, start, end in spans:
            if start <= seconds < end:
                return scene_id
        return "-"

    still, glob = [], []
    previous = frames[0].astype(np.int16)
    for index in range(1, count):
        current = frames[index].astype(np.int16)
        changed = (np.abs(current - previous) > EDGE_THRESHOLD).reshape(gy, cell_h, gx, cell_w)
        changed = changed.sum(axis=(1, 3))
        edges = ((np.abs(np.diff(previous, axis=1, append=previous[:, -1:])) > EDGE_THRESHOLD)
                 | (np.abs(np.diff(previous, axis=0, append=previous[-1:, :])) > EDGE_THRESHOLD))
        content = edges.reshape(gy, cell_h, gx, cell_w).sum(axis=(1, 3)) >= 40
        still.append(not changed.any())
        glob.append(float((changed[content] >= CELL_CHANGE_PIXELS).mean()) if content.sum() >= 6 else 0.0)
        previous = current

    runs, opened = [], None
    for index, share in enumerate(glob):
        seconds = (index + 1) / MOTION_SAMPLE_FPS
        fading = any(abs(seconds - edge) <= SCENE_BOUNDARY_GUARD for edge in boundaries)
        moving = share >= FULL_FRAME_SHARE and not fading
        if moving and opened is None:
            opened = index
        elif not moving and opened is not None:
            begin, finish = (opened + 1) / MOTION_SAMPLE_FPS, (index + 1) / MOTION_SAMPLE_FPS
            if finish - begin >= FULL_FRAME_SECONDS:
                runs.append({"from": round(begin, 2), "to": round(finish, 2), "scene": scene_at(begin)})
            opened = None

    per_scene, frozen = {}, []
    for scene_id, start, end in spans:
        first = max(0, int(round(start * MOTION_SAMPLE_FPS)))
        last = min(len(still), int(round(end * MOTION_SAMPLE_FPS)))
        segment = still[first:last]
        if not segment:
            continue
        per_scene[scene_id] = round(sum(segment) / len(segment), 2)
        longest = _longest_run(segment) / MOTION_SAMPLE_FPS
        if longest >= STILL_MIN_SECONDS:
            frozen.append({"scene": scene_id, "still_share": per_scene[scene_id],
                           "longest_still_seconds": round(longest, 2)})

    return {"status": "review" if runs else "ok", "sample_fps": MOTION_SAMPLE_FPS,
            "grid": list(MOTION_GRID), "frames": count,
            "still_share_by_scene": per_scene, "frozen_scenes": frozen,
            "full_frame_runs": runs,
            "note": "静帧占比是参考；frozen_scenes 只列连续静止 ≥5 秒的镜头，"
                    "整帧运动通常是缩放/抖动，需人工确认是否设计意图"}


def contact_sheet(stills: list[str], output: Path, *, portrait: bool, columns: int = 3,
                  cell: int = 960):
    """Tile review stills for the reviewer agent.

    Cells stay large enough to read on-screen text: a chart's axis labels are about
    50 px at 1920 wide, so 480 px cells reduced them to ~12 px and the reviewer
    reported guessed values as defects.  960 px cells keep them legible while the
    whole sheet stays under a few megabytes.
    """
    if not stills:
        raise ValueError("没有可拼图的审片静帧")
    cell_w = cell
    cell_h = round(cell * 9 / 16) if not portrait else round(cell * 16 / 9)
    columns = max(1, min(columns, len(stills)))
    rows = (len(stills) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * (cell_h + 34)), "#122531")
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(stills):
        with Image.open(name) as im:
            im = im.convert("RGB").resize((cell_w, cell_h), Image.LANCZOS)
            x, y = (i % columns) * cell_w, (i // columns) * (cell_h + 34)
            sheet.paste(im, (x, y))
            draw.text((x + 10, y + cell_h + 8), f"SCENE {i + 1:02d}", fill="white")
    sheet.save(output, quality=90)


def review_frame_fraction(scene: dict) -> float:
    """Where to sample a review still: after all actions finish, before the fade-out."""
    last = max((float(item.get("to") or 0) for item in scene.get("actions_resolved", [])), default=0.0)
    return min(0.96, max(0.55, last + 0.04))


def encoded_stills(video: Path, cut: dict, fps: int, directory: Path, *, portrait: bool) -> list[str]:
    """Extract one still per scene at native resolution for review.

    Downscaling here used to make on-screen text unreadable to the reviewer, which
    then reported guessed values as defects.
    """
    directory.mkdir(parents=True, exist_ok=True)
    offset, images = 0, []
    for index, scene in enumerate(cut["scenes"]):
        seconds = (offset + int(scene["frames"] * review_frame_fraction(scene))) / fps
        output = directory / f"scene-{index + 1:02d}.jpg"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{seconds:.6f}", "-threads", "2", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=iw:ih",
             "-threads", "1", "-q:v", "3", str(output)], timeout=60)
        images.append(str(output))
        offset += scene["frames"]
    return images


class ScriptIssues(ValueError):
    """Script contract failures, itemized so the director can fix each one.

    A single semicolon-joined sentence makes a weak model re-break the same rule;
    one item per defect with the scene id is what actually gets repaired.
    """

    def __init__(self, problems: list[str], headline: str = "脚本不满足渲染契约"):
        self.problems = [str(problem) for problem in problems]
        super().__init__(headline + "：" + "；".join(self.problems))


def repair_dangling_actions(value: dict) -> tuple[dict, list[str]]:
    """Drop actions whose target layer is not in the scene, and say so.

    This is a mechanical defect, not an editorial choice: the action cannot be
    drawn, and one such action otherwise fails the whole contract four times in a
    row on a weaker model (observed with DeepSeek).  Removing it loses an animation
    but keeps the picture and the narration intact, and the removal is recorded.

    Works on a whole Film (``long``/``short``) or a single Cut (``scenes``).
    """
    notes: list[str] = []

    def visit(container: dict) -> None:
        for scene in container.get("scenes") or []:
            layers = {layer.get("id") for layer in scene.get("layers") or []}
            if not layers:
                continue
            kept = []
            for action in scene.get("actions") or []:
                if action.get("target") in layers:
                    kept.append(action)
                else:
                    notes.append(f"{scene.get('id')}: 删除引用不存在图层 "
                                 f"{action.get('target')} 的 {action.get('kind')} 动作")
            scene["actions"] = kept

    visit(value)
    for cut_name in ("long", "short"):
        if isinstance(value.get(cut_name), dict):
            visit(value[cut_name])
    return value, notes


def validate_script(film, research, long_seconds: int, short_seconds: int) -> list[str]:
    """Reject scripts the renderer cannot honestly draw; return non-blocking warnings."""
    from .consistency import check_film
    from .scenedsl import pacing_estimate, scene_signature, validate_cut_dsl

    problems: list[str] = []
    recipe_notes: list[str] = []
    for name, target in [("long", long_seconds), ("short", short_seconds)]:
        cut = getattr(film, name)
        characters = sum(len(scene.narration) for scene in cut.scenes)
        if not target * 3.4 <= characters <= target * 6.5:
            problems.append(f"{name} 旁白长度 {characters} 字不适配目标 {target} 秒")
        if len({scene_signature(scene) for scene in cut.scenes}) < 3:
            problems.append(f"{name} 至少应有三种与内容相关的视觉表达")
        if any(s.source_index >= len(research.sources) for s in cut.scenes):
            problems.append(f"{name} 有镜头的 source_index 引用了不存在的来源")
        problems.extend(validate_cut_dsl(cut, vertical=name == "short"))
        from .continuity import continuity_report, morph_problems
        from .parameters import ParameterError, validate_scene_parameters
        from .recipes import recipe_warnings, validate_scene_recipe

        problems.extend(morph_problems(cut.scenes))
        report = continuity_report(cut.scenes)
        if report["problems"]:
            recipe_notes.extend(f"{name} 连续性：{problem}" for problem in report["problems"])
        for scene in cut.scenes:
            problems.extend(validate_scene_recipe(scene))
            try:
                problems.extend(validate_scene_parameters(scene))
            except ParameterError as exc:
                problems.append(f"镜头 {scene.id}：{exc}")
            recipe_notes.extend(recipe_warnings(scene))
    if problems:
        raise ScriptIssues(problems)
    errors, warnings = check_film(film)
    warnings.extend(recipe_notes)
    if errors:
        raise ScriptIssues(errors, headline="旁白与画面不一致")
    # Rhythm is a craft problem, not a contract violation: report it before TTS so
    # the director can act on it, without blocking a script that is otherwise valid.
    for name in ("long", "short"):
        for warning in pacing_estimate(getattr(film, name))["warnings"]:
            warnings.append(f"{name} 节奏：{warning}")
    from .craft import narrative_report

    warnings.extend(narrative_report(film)["warnings"])
    return warnings


def srt(cut: dict, fps: int) -> str:
    def stamp(seconds: float):
        ms = max(0, round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    lines, offset, n = [], 0, 1
    for scene in cut["scenes"]:
        for page in scene["captions"]:
            lines.append(f"{n}\n{stamp(offset + page['start'])} --> {stamp(offset + page['end'])}\n{page['text']}\n")
            n += 1
        offset += scene["frames"] / fps
    return "\n".join(lines)
