"""V3 craft metrics: sentence coverage, frame composition and sound design.

These are deliberately *separate* from ``quality.py``'s technical checks.  They
answer questions a viewer would ask ("is there a subject?", "does the picture
change when the sentence does?", "is there sound design?") and they say what they
cannot measure.  Nothing here claims aesthetic quality.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from PIL import Image


def _coverage_beats(scene: dict, seconds: float) -> list[float]:
    """Mirror of the renderer's sceneBeats: sentence starts grouped into 2–4 beats."""
    pages = sorted(scene.get("captions") or [], key=lambda page: float(page.get("start", 0)))
    if not pages:
        target = 4 if seconds > 22 else 3 if seconds > 14 else 2
        return [seconds / target * index for index in range(target)]
    sentences: list[list[float]] = []
    for page in pages:
        if sentences and float(page.get("start", 0)) - sentences[-1][1] <= 0.18:
            sentences[-1][1] = max(sentences[-1][1], float(page.get("end", 0)))
        else:
            sentences.append([float(page.get("start", 0)), float(page.get("end", 0))])
    if sentences:
        sentences[0][0] = 0.0
    target = 4 if seconds > 22 else 3 if seconds > 14 else 2 if seconds > 8 else 1
    if len(sentences) <= target:
        return [item[0] for item in sentences]
    groups, wanted = [], seconds / target
    begin, last = sentences[0][0], sentences[0][1]
    for index, sentence in enumerate(sentences[1:], start=1):
        if (last - begin >= wanted * 0.82 or index == len(sentences) - 1) and len(groups) < target - 1:
            groups.append(begin)
            begin = sentence[0]
        last = sentence[1]
    groups.append(begin)
    return groups


def rhythm_report(cut: dict, fps: int) -> dict:
    """Does the picture change when the sentence does?

    V3 turns each long shot into 2–4 coverage beats (camera re-frame + insight
    change), derived from sentence starts.  A caption page is covered if an
    authored action *or* a beat start falls within 0.8 s of it.  This measures the
    editing rhythm, not just how many actions the director wrote.
    """
    pages = 0
    covered_pages = 0
    events = 0
    beat_count = 0
    total = 0.0
    silent_pages: list[dict] = []
    for scene in cut.get("scenes", []):
        seconds = max(0.1, scene["frames"] / fps)
        total += seconds
        actions = scene.get("actions_resolved") or []
        beats = _coverage_beats(scene, seconds)
        beat_count += len(beats)
        events += len(actions) + max(0, len(beats) - 1)
        anchors = [float(action.get("from", 0)) * seconds for action in actions]
        anchors += [float(action.get("to", 0)) * seconds for action in actions]
        anchors += beats
        for page in scene.get("captions") or []:
            pages += 1
            start = float(page.get("start", 0))
            if any(abs(anchor - start) <= 0.8 for anchor in anchors):
                covered_pages += 1
            elif len(silent_pages) < 12:
                silent_pages.append({"scene": scene.get("id"), "at": round(start, 2),
                                     "text": str(page.get("text", ""))[:22]})
    coverage = covered_pages / pages if pages else 0.0
    rate = events / max(1e-6, total) * 60
    warnings = []
    if pages >= 6 and coverage < 0.35:
        warnings.append(f"只有 {coverage:.0%} 的字幕页在 ±0.8s 内有画面动作；长句之间会出现“只有人声”的空转")
    if total >= 60 and rate < 6:
        warnings.append(f"画面动作只有 {rate:.1f} 个/分钟，镜头容易在句间静止")
    return {"status": "review" if warnings else "ok", "caption_pages": pages,
            "covered_pages": covered_pages, "sentence_coverage": round(coverage, 3),
            "visual_events": events, "coverage_beats": beat_count,
            "events_per_minute": round(rate, 2),
            "silent_pages": silent_pages, "warnings": warnings}


def composition_report(stills: list[str], *, portrait: bool) -> dict:
    """Measure the rendered frame: subject height, ink share and empty cells.

    ``anything2explainer`` uses the largest object height as a proxy for "is
    there a hero"; a frame whose largest object is under ~1/4 of the height reads
    as a small floating card.  This is a row-projection estimate, not connected
    component analysis: it catches the empty-frame defect without claiming to
    measure beauty.
    """
    rows = []
    for name in stills:
        try:
            with Image.open(name) as image:
                gray = image.convert("L").resize((320, 180), Image.BILINEAR)
        except OSError:
            continue
        data = np.asarray(gray, dtype=np.float32)
        border = np.concatenate([data[0, :], data[-1, :], data[:, 0], data[:, -1]])
        background = float(np.median(border))
        ink = data > background + 16
        height, width = ink.shape
        row_ink = ink.sum(axis=1) > max(2, width * 0.008)
        best = current = 0
        for value in row_ink:
            current = current + 1 if value else 0
            best = max(best, current)
        # 18 rows × 10 columns of 10×32 px cells.
        cells = ink.reshape(18, 10, 10, 32).mean(axis=(2, 3))
        empty_share = float((cells < 0.012).mean())
        rows.append({"still": str(name), "largest_object_height_ratio": round(best / height, 3),
                     "ink_share": round(float(ink.mean()), 3),
                     "empty_cell_share": round(empty_share, 3),
                     "background_luma": round(background, 1)})
    if not rows:
        return {"status": "unavailable", "reason": "没有可分析的代表帧"}
    heights = sorted(row["largest_object_height_ratio"] for row in rows)
    inks = sorted(row["ink_share"] for row in rows)
    empties = sorted(row["empty_cell_share"] for row in rows)
    warnings = []
    threshold = 0.22 if portrait else 0.26
    if heights[len(heights) // 2] < threshold:
        warnings.append(f"代表帧主体高度中位数 {heights[len(heights) // 2]:.0%}，低于“一个主角占画面 1/4 以上”的构图线")
    if float(np.median(empties)) > 0.45:
        warnings.append(f"约 {np.median(empties):.0%} 的画面网格没有任何内容，容易显得空")
    return {"status": "review" if warnings else "ok", "frames": len(rows),
            "subject_height_median": round(heights[len(heights) // 2], 3),
            "subject_height_min": round(heights[0], 3),
            "ink_share_median": round(inks[len(inks) // 2], 3),
            "empty_cell_share_median": round(float(np.median(empties)), 3),
            "per_scene": rows, "warnings": warnings,
            "limitations": ["行投影估算，不区分有意义的图形与大字；不代表审美评价"]}


def _read_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768
        return data.reshape(-1, channels).mean(axis=1) if channels > 1 else data


def sound_design_report(cut: dict, mix: Path) -> dict:
    """Count automatic and director cues, their kinds, sync and the mix level."""
    seconds = sum(scene["frames"] for scene in cut["scenes"]) / 30.0
    events = cut.get("sound_events") or cut.get("cues") or []
    kinds: dict[str, int] = {}
    sources: dict[str, int] = {}
    for event in events:
        kind = str(event.get("kind", "?"))
        source = str(event.get("source", "director"))
        kinds[kind] = kinds.get(kind, 0) + 1
        sources[source] = sources.get(source, 0) + 1
    transitions = [scene.get("transition", "fade") for scene in cut["scenes"]]
    cameras = [scene.get("camera", "push") for scene in cut["scenes"]]
    offset, anchors = 0.0, []
    for scene in cut["scenes"]:
        length = scene["frames"] / 30.0
        anchors.append(offset)
        anchors.append(offset - 0.24)  # transition lead (J-cut)
        for action in scene.get("actions_resolved") or []:
            anchors.append(offset + float(action.get("from", 0)) * length)
            anchors.append(offset + float(action.get("to", 0)) * length)
        offset += length
    automatic = [event for event in events if event.get("source") != "director"]
    synced = sum(1 for event in automatic
                 if any(abs(float(event.get("at", 0)) - anchor) <= 0.30 for anchor in anchors))
    levels: dict = {}
    stereo: dict = {}
    try:
        audio = _read_mono(mix)
        window = 2400
        frames = len(audio) // window
        if frames > 4:
            rms = np.sqrt(np.mean(audio[:frames * window].reshape(frames, window) ** 2, axis=1))
            levels = {"rms_db": round(float(20 * np.log10(max(1e-6, float(np.median(rms))))), 1),
                      "dynamic_range_db": round(float(20 * np.log10(
                          max(1e-6, float(np.percentile(rms, 95))) / max(1e-6, float(np.percentile(rms, 10))))), 1)}
        with wave.open(str(mix), "rb") as stream:
            if stream.getnchannels() == 2:
                raw = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768
                pair = raw.reshape(-1, 2)
                if len(pair) > 10 and float(np.std(pair[:, 0])) > 1e-9 and float(np.std(pair[:, 1])) > 1e-9:
                    correlation = float(np.corrcoef(pair[:, 0], pair[:, 1])[0, 1])
                else:
                    correlation = 1.0
                stereo = {"correlation": round(correlation, 3),
                          "note": "以人声为主的混音接近 1 是正常的（人声居中且占主导）；"
                                  "这条只用于发现“完全复制单声道”或反相问题，不代表空间感好坏"}
    except (OSError, ValueError, wave.Error) as exc:  # pragma: no cover - corrupt wav
        levels = {"status": "unavailable", "reason": str(exc)}
    warnings = []
    if seconds >= 60 and len(events) / max(1e-6, seconds / 60) < 6:
        warnings.append("音效密度低于 6 个/分钟，画面动作缺少声音回应")
    if len(kinds) < 4 and len(events) >= 8:
        warnings.append(f"音效类型只有 {len(kinds)} 种，容易听成同一种“咔哒”")
    return {"status": "review" if warnings else "ok", "seconds": round(seconds, 1),
            "events": len(events),
            "events_per_minute": round(len(events) / max(1e-6, seconds / 60), 2),
            "cue_kinds": kinds, "event_sources": sources,
            "automatic_sync_ratio": round(synced / len(automatic), 3) if automatic else None,
            "transition_variety": len(set(transitions)),
            "camera_moves": {name: cameras.count(name) for name in sorted(set(cameras))},
            "mix_levels": levels, "stereo": stereo,
            "prosody": cut.get("prosody", "flat"),
            "mix_recipe": "voice + adaptive pad/bass/arp/pulse + automatic Foley + one reverb bus + room tone",
            "warnings": warnings,
            "limitations": ["程序合成的音效与配乐不是采样音源；机器统计不能替代实听"]}


ANNOUNCEMENTS = ("今天我们来", "本期视频", "下面我们", "接下来我们", "首先我们", "让我们来看", "话不多说")
CALLBACKS = ("回到开头", "回到最初", "回到那个", "回到这条", "回到一开始", "回到问题", "所以，")


def narrative_report(film) -> dict:
    """Offline craft review of the script itself (no model call).

    These are warnings, not gates: they point at the failure modes the reference
    narration guidance names — a definition instead of a situation, a glossary
    without a spine, three same-shaped sentences in a row, and an ending that
    summarizes instead of returning to the opening.
    """
    import re

    warnings: list[str] = []
    cuts: dict[str, dict] = {}
    for name in ("long", "short"):
        cut = getattr(film, name, None)
        if cut is None:
            continue
        scenes = list(cut.scenes)
        narrations = [scene.narration for scene in scenes]
        all_text = "".join(narrations)
        first = narrations[0] if narrations else ""
        last = narrations[-1] if narrations else ""
        sentences = [part for part in re.split(r"[。！？!?；;]", all_text) if part.strip()]
        lengths = [len(part) for part in sentences]
        mean = sum(lengths) / len(lengths) if lengths else 0
        variance = (sum((value - mean) ** 2 for value in lengths) / len(lengths)) ** 0.5 if lengths else 0
        cv = variance / mean if mean else 0
        announced = sum(text.count(phrase) for text in narrations for phrase in ANNOUNCEMENTS)
        roles = [scene.role for scene in scenes]
        role_variety = len(set(roles))
        chapters = [scene.chapter for scene in scenes if scene.chapter]
        takeaways = [scene.takeaway for scene in scenes if scene.takeaway]
        actions = [len(scene.actions) for scene in scenes]
        silent_scenes = [scene.id for scene, count in zip(scenes, actions) if count < 2]
        questions = first.count("？") + first.count("?")
        cut_warnings: list[str] = []
        if announced >= 1:
            cut_warnings.append(f"出现 {announced} 处报幕式过渡（如“接下来我们”）；用上一段留下的问题接住下一段，而不是报顺序")
        if len(lengths) >= 8 and cv < 0.2:
            cut_warnings.append(f"句长变异系数 {cv:.2f}，几乎每句一样长；长短句交替才有讲述感")
        if silent_scenes and len(scenes) >= 4:
            cut_warnings.append(f"{len(silent_scenes)} 个镜头少于 2 个动作（{', '.join(silent_scenes[:4])}），"
                                f"一句一个新元素比一个入场动画撑 25 秒更有效")
        if role_variety == 1 and len(scenes) >= 4 and any(role != "mechanism" for role in roles):
            cut_warnings.append("所有镜头都是同一种 role；钩子/机制/例子/转折/收束应至少出现三种")
        if chapters and len(set(chapters)) < len(chapters) * 0.6:
            cut_warnings.append("章节名重复过多，观众看不出主线走到了哪一步")
        if takeaways and len(takeaways) < len(scenes) * 0.5:
            cut_warnings.append("不足一半镜头写了 takeaway；insight 卡会退回到自动数据标签")
        if first and not questions and len(first) < 26 and not any(word in first for word in ("我", "你", "想象", "如果", "为什么")):
            cut_warnings.append("开场第一句既没有处境、人称，也没有问题；容易像定义而不是故事")
        if last and first:
            overlap = {last[index:index + 2] for index in range(len(last) - 1)}
            opening = {first[index:index + 2] for index in range(len(first) - 1)}
            if not (overlap & opening) and not any(word in last for word in CALLBACKS):
                cut_warnings.append("结尾没有回扣开场的人/物/问题；最后一段不要只做总结清单")
        warnings.extend(f"{name} 叙事：{warning}" for warning in cut_warnings)
        cuts[name] = {"sentences": len(sentences), "sentence_length_cv": round(cv, 3),
                      "announcements": announced, "roles": {role: roles.count(role) for role in sorted(set(roles))},
                      "chapters": chapters, "takeaways": len(takeaways),
                      "actions": actions, "silent_scenes": silent_scenes,
                      "warnings": cut_warnings}
    return {"status": "review" if warnings else "ok", "cuts": cuts, "warnings": warnings,
            "limitations": ["启发式离线检查；不能判断事实正确性或讲述是否真的有趣"]}
