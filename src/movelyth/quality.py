from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .media import ffmpeg, ffprobe
from .util import run


def duration_policy(config: dict, cut: str) -> dict:
    target = config[f"{cut}_seconds"]
    low = config.get(f"{cut}_min_seconds", target * 0.55)
    high = config.get(f"{cut}_max_seconds", target * 1.55)
    if not 0 < low <= target <= high:
        raise ValueError(f"{cut} 时长范围必须满足 0 < min <= target <= max")
    return {"target_seconds": target, "minimum_seconds": low, "maximum_seconds": high,
            "target_is_approximate": True}


def verify_video(path: Path, *, width: int, height: int, seconds: float, fps: int,
                 policy: dict | None = None) -> dict:
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
    sample = subprocess.run([ffmpeg(), "-v", "error", "-threads", "2", "-i", str(path),
                             "-vf", "fps=1,scale=128:72,format=gray", "-an", "-f", "rawvideo", "-"],
                            capture_output=True, timeout=300, check=True)
    frames = np.frombuffer(sample.stdout, dtype=np.uint8).reshape(-1, 72, 128)
    movement = float(np.abs(np.diff(frames.astype(np.float32), axis=0)).mean()) if len(frames) > 1 else 0
    checks["moving_picture"] = movement > 0.15
    checks["not_black"] = bool(len(frames) and np.mean(frames) > 6)
    return {"passed": all(checks.values()), "checks": checks, "duration": actual_seconds,
            "timeline_seconds": seconds, "duration_policy": policy,
            "width": video.get("width"), "height": video.get("height"), "fps": frame_rate,
            "max_volume_db": float(peak[1]) if peak else None,
            "mean_volume_db": float(mean[1]) if mean else None,
            "mean_sample_motion": movement, "audio_listened": False,
            "asr_checked": False, "full_motion_aesthetic_review": False}


def contact_sheet(stills: list[str], output: Path, *, portrait: bool):
    cell_w, cell_h = (270, 480) if portrait else (480, 270)
    columns = 3
    rows = (len(stills) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * (cell_h + 30)), "#122531")
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(stills):
        with Image.open(name) as im:
            im = im.convert("RGB").resize((cell_w, cell_h))
            x, y = (i % columns) * cell_w, (i // columns) * (cell_h + 30)
            sheet.paste(im, (x, y))
            draw.text((x + 10, y + cell_h + 5), f"SCENE {i + 1:02d}", fill="white")
    sheet.save(output)


def encoded_stills(video: Path, cut: dict, fps: int, directory: Path, *, portrait: bool) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    offset, images = 0, []
    for index, scene in enumerate(cut["scenes"]):
        seconds = (offset + int(scene["frames"] * 0.55)) / fps
        output = directory / f"scene-{index + 1:02d}.jpg"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{seconds:.6f}", "-threads", "2", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=540:-2" if portrait else "scale=960:-2",
             "-threads", "1", str(output)], timeout=60)
        images.append(str(output))
        offset += scene["frames"]
    return images


def validate_script(film, research, long_seconds: int, short_seconds: int) -> None:
    for name, target in [("long", long_seconds), ("short", short_seconds)]:
        cut = getattr(film, name)
        characters = sum(len(scene.narration) for scene in cut.scenes)
        if not target * 3.4 <= characters <= target * 6.5:
            raise ValueError(f"{name} 旁白长度 {characters} 字不适配目标 {target} 秒")
        if len({s.visual for s in cut.scenes}) < 3:
            raise ValueError(f"{name} 至少应有三种与内容相关的视觉表达")
        if any(s.source_index >= len(research.sources) for s in cut.scenes):
            raise ValueError("source_index 引用了不存在的来源")


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
