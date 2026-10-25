"""Real TTS timing, original procedural audio and computed image assets."""
from __future__ import annotations

import asyncio
import math
import os
import re
import shutil
import time
import wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from .util import atomic_json, file_hash, fingerprint, read_json, run

SAMPLE_RATE = 24000


def ffmpeg() -> str:
    return os.getenv("MOVELYTH_FFMPEG") or imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe() -> str:
    configured = os.getenv("MOVELYTH_FFPROBE") or shutil.which("ffprobe")
    if configured:
        return configured
    packages = Path(__file__).resolve().parents[2] / "studio/node_modules/@remotion"
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    candidates = list(packages.glob(f"compositor-*/{name}"))
    if candidates:
        return str(candidates[0])
    raise RuntimeError("缺少 ffprobe。请先在 studio 运行 npm ci，或设置 MOVELYTH_FFPROBE")


def write_wav(path: Path, audio: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    channels = 1 if audio.ndim == 1 else audio.shape[1]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes((np.clip(audio, -0.98, 0.98) * 32767).astype("<i2").tobytes())


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        if stream.getframerate() != SAMPLE_RATE or stream.getnchannels() != 1:
            raise ValueError("旁白缓存必须为 24kHz 单声道 PCM")
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768


async def synthesize(text: str, voice: str, rate: str, mp3: Path) -> list[dict]:
    proxy = os.getenv("MOVELYTH_TTS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary", proxy=proxy)
    boundaries = []
    with mp3.open("wb") as output:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                output.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append({"start": chunk["offset"] / 10_000_000,
                                   "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                                   "text": chunk["text"]})
    return boundaries


def voice(text: str, config: dict, cache: Path) -> tuple[np.ndarray, list[dict], list[Path]]:
    key = fingerprint({"text": text, "voice": config["voice"], "rate": config["voice_rate"], "version": 1})
    folder = cache / key
    folder.mkdir(parents=True, exist_ok=True)
    wav, mp3, timing = folder / "voice.wav", folder / "voice.mp3", folder / "timing.json"
    receipt = folder / "receipt.json"
    if receipt.exists():
        hashes = read_json(receipt)
        if all(p.exists() and hashes.get(p.name) == file_hash(p) for p in (wav, mp3, timing)):
            return read_wav(wav), read_json(timing), [wav, mp3, timing, receipt]
    error = None
    for attempt in range(config["max_retries"] + 1):
        try:
            boundaries = asyncio.run(synthesize(text, config["voice"], config["voice_rate"], mp3))
            run([ffmpeg(), "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE),
                 "-c:a", "pcm_s16le", str(wav)], timeout=90)
            audio = read_wav(wav)
            if len(audio) < SAMPLE_RATE or float(np.max(np.abs(audio))) < 0.001:
                raise RuntimeError("配音为空或近乎静音")
            atomic_json(timing, boundaries)
            atomic_json(receipt, {p.name: file_hash(p) for p in (wav, mp3, timing)})
            return audio, boundaries, [wav, mp3, timing, receipt]
        except Exception as exc:
            error = exc
            if attempt < config["max_retries"]:
                time.sleep(1 + attempt * 2)
    raise RuntimeError(f"配音失败，已保留缓存；不会降级为无声视频：{type(error).__name__}: {error}") from error


def captions(text: str, boundaries: list[dict], duration: float, max_chars: int) -> tuple[list[dict], str]:
    parts = []
    for clause in re.split(r"(?<=[，。！？；：,.!?;:])", text):
        parts.extend(clause[i:i + max_chars] for i in range(0, len(clause), max_chars))
    positions, cursor = [], 0
    for boundary in boundaries:
        start = text.find(boundary["text"], cursor)
        if start >= 0:
            positions.append((start, start + len(boundary["text"]), boundary["start"], boundary["end"]))
            cursor = start + len(boundary["text"])
    pages, cursor = [], 0
    mode = "tts-word-boundaries" if positions else "estimated-character-timing"
    for part in parts:
        if not part:
            continue
        start, end = cursor, cursor + len(part)
        matched = [p for p in positions if p[0] < end and p[1] > start]
        t0 = matched[0][2] if matched else duration * start / max(1, len(text))
        t1 = matched[-1][3] if matched else duration * end / max(1, len(text))
        pages.append({"start": min(t0, duration), "end": min(max(t1, t0 + 0.15), duration),
                      "text": part.strip(" ，。！？；：,.!?;:")})
        cursor = end
    # Silence between clauses keeps the last caption briefly visible, without overlapping the next.
    for i, page in enumerate(pages):
        next_start = pages[i + 1]["start"] if i + 1 < len(pages) else duration
        page["end"] = min(next_start, max(page["end"], page["start"] + 0.5))
    return [p for p in pages if p["text"] and p["end"] > p["start"]], mode


def soundtrack(voice_track: np.ndarray, scene_starts: list[float], style: str = "tech") -> np.ndarray:
    """Original local music bed with three restrained style presets, ducked under speech."""
    size = len(voice_track)
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    music = np.zeros(size, dtype=np.float32)
    presets = {
        # key: (chords, bed gain, beat gain, accent gain, accent notes, beat period)
        "tech": ([(130.81, 164.81, 196.00), (110, 130.81, 164.81),
                  (87.31, 110, 130.81), (98.00, 123.47, 146.83)], 0.022, 0.025, 0.035,
                 (523.25, 783.99), 0.6),
        "minimal": ([(130.81, 196.00, 261.63), (116.54, 174.61, 233.08),
                     (98.00, 146.83, 196.00), (110.00, 164.81, 220.00)], 0.016, 0.0, 0.020,
                    (392.00,), 0.9),
        "documentary": ([(65.41, 98.00, 130.81), (58.27, 87.31, 116.54),
                         (49.00, 73.42, 98.00), (55.00, 82.41, 110.00)], 0.028, 0.008, 0.026,
                        (329.63, 493.88), 1.2),
    }
    chords, bed_gain, beat_gain, accent_gain, accent_notes, period = presets.get(style, presets["tech"])
    for begin in range(0, size, SAMPLE_RATE * 8):
        end = min(size, begin + SAMPLE_RATE * 8)
        local = t[begin:end] - begin / SAMPLE_RATE
        chord = chords[(begin // (SAMPLE_RATE * 8)) % len(chords)]
        envelope = np.minimum(local / 1.1, 1) * np.minimum((end - begin) / SAMPLE_RATE - local, 1.1) / 1.1
        for freq in chord:
            music[begin:end] += (bed_gain * np.sin(2 * np.pi * freq * local)
                                 + 0.008 * np.sin(2 * np.pi * freq * 2 * local)) * envelope
        if beat_gain:
            beat = np.mod(local, period)
            music[begin:end] += beat_gain * np.exp(-beat * 9) * np.sin(2 * np.pi * chord[2] * 4 * local)
    for start in scene_starts:
        begin = int(start * SAMPLE_RATE)
        count = min(SAMPLE_RATE, size - begin)
        local = np.arange(count) / SAMPLE_RATE
        accent = np.zeros(count, dtype=np.float32)
        for index, note in enumerate(accent_notes):
            accent += (accent_gain / (index + 1)) * np.sin(2 * np.pi * note * local)
        music[begin:begin + count] += accent * np.exp(-local * 6)
    window = SAMPLE_RATE // 20
    pad = (-size) % window
    energy = np.sqrt(np.mean(np.pad(voice_track, (0, pad)).reshape(-1, window) ** 2, axis=1))
    duck = np.interp(np.arange(size), np.arange(len(energy)) * window, np.where(energy > 0.014, 0.32, 0.9))
    fade = np.minimum(t / 2.0, 1) * np.minimum((size / SAMPLE_RATE - t) / 2, 1)
    bed = music * duck * np.maximum(0, fade)
    return np.stack([voice_track * 0.85 + bed, voice_track * 0.85 + bed * 0.93], axis=1)


def speech_text(text: str, replacements: dict | None = None) -> str:
    """Optional, explicit pronunciation mapping applied to TTS *and* captions.

    Defaults to no change so captions always match the written narration.
    """
    for source, target in (replacements or {}).items():
        if isinstance(source, str) and isinstance(target, str) and source:
            text = text.replace(source, target)
    return text


def prepare_cut(cut: dict, config: dict, cache: Path, output: Path, *, portrait: bool) -> tuple[dict, list[Path]]:
    from .models import Scene
    from .scenedsl import normalize_scene

    fps = config["fps"]
    style = cut.get("style", "tech")
    replacements = config.get("speech_replace") or {}
    chunks, starts, paths, scenes, cursor = [], [], [], [], 0
    for raw in cut["scenes"]:
        scene = Scene.model_validate(raw)
        spoken = speech_text(scene.narration, replacements)
        audio, boundaries, generated = voice(spoken, config, cache)
        paths.extend(generated)
        lead = 0.25
        seconds = len(audio) / SAMPLE_RATE
        frames = math.ceil((seconds + lead + 0.85) * fps)
        samples = round(frames / fps * SAMPLE_RATE)
        chunk = np.zeros(samples, dtype=np.float32)
        begin = round(lead * SAMPLE_RATE)
        chunk[begin:begin + len(audio)] = audio
        pages, timing = captions(spoken, boundaries, seconds, 16 if portrait else 25)
        for page in pages:
            page["start"] += lead
            page["end"] += lead
        shifted = [{"text": b["text"], "start": b["start"] + lead, "end": b["end"] + lead}
                   for b in boundaries]
        normalized = normalize_scene(scene, duration=frames / fps, boundaries=shifted, vertical=portrait)
        normalized.update({"frames": frames, "captions": pages, "caption_timing": timing})
        if spoken != scene.narration:
            normalized["spoken_narration"] = spoken
        scenes.append(normalized)
        starts.append(cursor / SAMPLE_RATE)
        cursor += samples
        chunks.append(chunk)
    narration = np.concatenate(chunks)
    output.mkdir(parents=True, exist_ok=True)
    dry, mixed = output / "narration.wav", output / "mix.wav"
    write_wav(dry, narration)
    write_wav(mixed, soundtrack(narration, starts, style))
    paths.extend([dry, mixed])
    return {"title": cut["title"], "scenes": scenes, "frames": sum(s["frames"] for s in scenes),
            "seconds": len(narration) / SAMPLE_RATE, "mix": str(mixed), "voice": str(dry),
            "style": style}, paths


def image_layers(output: Path) -> tuple[list[str], list[Path], dict]:
    """Generate our own landscape and compute real per-channel low-rank approximations."""
    output.mkdir(parents=True, exist_ok=True)
    width, height = 480, 300
    im = Image.new("RGB", (width, height))
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        f = y / height
        pixels[y, :] = (int(26 + 140 * f), int(61 + 90 * f), int(92 + 25 * f))
    im = Image.fromarray(pixels)
    draw = ImageDraw.Draw(im)
    draw.ellipse((325, 42, 392, 109), fill=(255, 211, 147))
    for level, color in [(0, (37, 83, 105)), (1, (24, 65, 87)), (2, (15, 47, 65))]:
        points = [(x, int(140 + level * 37 + 26 * math.sin(x * 0.015 + level * 2)
                          + 17 * math.sin(x * 0.037 + level))) for x in range(width)]
        draw.polygon(points + [(width, height), (0, height)], fill=color)
    for y in range(230, height, 5):
        draw.line((0, y, width, y), fill=(70 + y // 8, 118, 131), width=1)
    original = output / "landscape-original.png"
    im.save(original)
    data = np.asarray(im, dtype=np.float64) / 255
    decompositions = [np.linalg.svd(data[:, :, c], full_matrices=False) for c in range(3)]
    names, paths, report = [], [original], {}
    for rank in [1, 4, 12, 32]:
        approx = np.stack([(u[:, :rank] * s[:rank]) @ vt[:rank] for u, s, vt in decompositions], axis=2)
        name = f"svd-{rank}.png"
        target = output / name
        Image.fromarray(np.uint8(np.clip(approx, 0, 1) * 255)).save(target)
        names.append(name)
        paths.append(target)
        report[str(rank)] = {"mse": float(np.mean((data - approx) ** 2)), "rank": rank}
    metrics = output / "svd-metrics.json"
    atomic_json(metrics, {"method": "numpy.linalg.svd, RGB channels independently", "ranks": report})
    paths.append(metrics)
    return names, paths, report
