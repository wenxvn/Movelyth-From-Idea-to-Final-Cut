"""Real TTS timing, original procedural audio and computed image assets.

Two deliberate choices shape the sound of a Movelyth film:

* Narration is synthesised **sentence by sentence**, so each sentence can carry its
  own rate/pitch and be followed by a real pause.  One flat utterance per scene
  (V1) is why every shot sounded like the same reader at the same speed, with no
  breath between thoughts.
* Music and sound effects are synthesised locally with numpy.  Nothing is
  downloaded, so there is no licence or network dependency, and the bed can be
  arranged in sections (intro / body / outro) instead of one 8-second loop.
"""
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

from .sound import design_sound_events
from .textfit import caption_chunks
from .util import atomic_json, file_hash, fingerprint, read_json, run

SAMPLE_RATE = 24000
# Bump when the synthesis pipeline changes in a way that alters the audio, so the
# voice cache does not serve audio made by the old implementation.
TTS_VERSION = 3


def ffmpeg() -> str:
    return os.getenv("MOVELYTH_FFMPEG") or imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_candidates() -> list[Path]:
    """Every place ffprobe is looked for, in resolution order."""
    found: list[Path] = []
    configured = os.getenv("MOVELYTH_FFPROBE")
    if configured:
        found.append(Path(configured))
    on_path = shutil.which("ffprobe")
    if on_path:
        found.append(Path(on_path))
    packages = Path(__file__).resolve().parents[2] / "studio/node_modules/@remotion"
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    found.extend(sorted(packages.glob(f"compositor-*/{name}")))
    return found


def ffprobe() -> str:
    """Locate ffprobe, or fail with the locations that were actually checked.

    The Remotion compositor binary is a fallback because ``studio/node_modules``
    is only populated by ``npm ci``; CI used to run pytest before that install,
    so the media checks failed on a clean checkout.  The error now names every
    checked location instead of only suggesting one of them.
    """
    candidates = ffprobe_candidates()
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    searched = "；".join(str(path) for path in candidates) or "（未找到任何候选路径）"
    raise RuntimeError(
        "缺少 ffprobe：媒体验证与编码检查无法进行。已检查：" + searched
        + "。请运行 npm ci --prefix studio，或设置 MOVELYTH_FFPROBE 指向 ffprobe 可执行文件")


def tool_version(binary: str) -> str | None:
    """First line of ``<binary> -version``; ``None`` when it cannot be executed."""
    try:
        result = run([binary, "-version"], timeout=20)
    except (OSError, RuntimeError):
        return None
    line = (result.stdout or "").splitlines()
    return line[0].strip() if line else None


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


# --------------------------------------------------------------------------- TTS


async def synthesize(text: str, voice: str, rate: str, mp3: Path,
                     pitch: str = "+0Hz", volume: str = "+0%") -> list[dict]:
    proxy = os.getenv("MOVELYTH_TTS_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume,
                                       boundary="WordBoundary", proxy=proxy)
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


def timing_matches_audio(audio: np.ndarray, boundaries: list[dict]) -> bool:
    """Word boundaries must lie inside the audio they were measured on.

    A truncated WAV with intact boundaries silently drops the last captions: one
    cached entry out of 338 had 17.4 s of timings on 14.6 s of audio, which clipped
    two pages.  Treating that as a cache miss regenerates the take instead.
    """
    if not boundaries:
        return True
    seconds = len(audio) / SAMPLE_RATE
    last = max(float(item.get("end") or 0) for item in boundaries)
    return last <= seconds + 0.05


def _percent(value: str, delta: int) -> str:
    """Add *delta* percentage points to a rate/volume string such as ``+0%``."""
    match = re.fullmatch(r"\s*([+-]?\d+)\s*%?\s*", str(value))
    base = int(match.group(1)) if match else 0
    total = max(-50, min(50, base + delta))
    return f"{total:+d}%"


def _hertz(value: str, delta: int) -> str:
    match = re.fullmatch(r"\s*([+-]?\d+)\s*Hz\s*", str(value))
    base = int(match.group(1)) if match else 0
    total = max(-30, min(30, base + delta))
    return f"{total:+d}Hz"


SENTENCE_END = "。！？!?；;…"
CLAUSE_END = "，,、：:"


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Split *text* into sentences (keeping punctuation) as character spans.

    Long sentences are additionally split at a comma so one paragraph does not
    become a 12-second unbroken take; spans always cover the whole string, so the
    character map used for captions stays exact.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for index, ch in enumerate(text):
        if ch in SENTENCE_END and index + 1 - start >= 2:
            spans.append((start, index + 1))
            start = index + 1
    if start < len(text):
        spans.append((start, len(text)))
    result: list[tuple[int, int]] = []
    for begin, end in spans:
        if end - begin <= 52:
            result.append((begin, end))
            continue
        cut = begin
        for index in range(begin, end):
            if text[index] in CLAUSE_END and index - cut >= 18:
                result.append((cut, index + 1))
                cut = index + 1
        if cut < end:
            result.append((cut, end))
    return [span for span in result if text[span[0]:span[1]].strip()]


def prosody_plan(narration: str, emphasis: list[str] | None = None,
                 config: dict | None = None) -> list[dict]:
    """Per-sentence delivery: rate, pitch, volume and the pause that follows.

    This is the difference between "a TTS engine read the script" and "someone is
    explaining something".  The rules are deliberately small and inspectable:
    a sentence that carries an emphasis word slows down and gets slightly louder;
    a question lifts; the first sentence settles in and the last one lands; long
    sentences speed up a little so they do not drag.
    """
    config = config or {}
    base_rate = config.get("voice_rate", "+0%")
    base_pitch = config.get("voice_pitch", "+0Hz")
    base_volume = config.get("voice_volume", "+0%")
    words = [word for word in (emphasis or []) if word]
    plan = []
    spans = sentence_spans(narration)
    for order, (begin, end) in enumerate(spans):
        text = narration[begin:end]
        stripped = text.strip()
        rate_delta = 0
        pitch_delta = 0
        volume_delta = 0
        if any(word in stripped for word in words):
            rate_delta -= 7
            volume_delta += 5
        if stripped.endswith(("？", "?")):
            rate_delta -= 3
            pitch_delta += 2
        if order == 0 and len(spans) > 2:
            rate_delta -= 2
        if order == len(spans) - 1 and len(spans) > 2:
            rate_delta -= 4
            volume_delta += 2
        if len(stripped) > 40:
            rate_delta += 3
        last = stripped[-1:] if stripped else ""
        if last in "。！":
            pause = 0.30
        elif last in "？?":
            pause = 0.36
        elif last in "；;":
            pause = 0.22
        elif last in "，,、：:":
            pause = 0.15
        elif last == "…":
            pause = 0.42
        else:
            pause = 0.12
        plan.append({"text": text, "start": begin, "end": end,
                     "rate": _percent(base_rate, rate_delta),
                     "pitch": _hertz(base_pitch, pitch_delta),
                     "volume": _percent(base_volume, volume_delta),
                     "pause_after": pause, "emphasis": bool(rate_delta <= -7)})
    return plan


def _split_clauses(text: str, base: int, min_length: int = 9) -> list[tuple[int, int]]:
    """Split a sentence at commas/colons, keeping punctuation; never split a Latin word."""
    spans, start = [], 0
    for index, ch in enumerate(text):
        if ch in CLAUSE_END and index + 1 - start >= min_length:
            spans.append((start + base, index + 1 + base))
            start = index + 1
    if start < len(text):
        spans.append((start + base, len(text) + base))
    return [span for span in spans if span[1] > span[0]] or [(base, base + len(text))]


def _split_emphasis(text: str, base: int, words: list[str]) -> list[tuple[int, int, bool]]:
    """Split a clause around the first emphasis phrase so it can be delivered with weight."""
    for word in sorted((word for word in words if word), key=len, reverse=True):
        index = text.find(word)
        if index < 0:
            continue
        # Do not cut inside a Latin token.
        before, after = index, index + len(word)
        if before > 0 and text[before - 1].isascii() and text[before - 1].isalnum() and text[before].isascii() and text[before].isalnum():
            continue
        if after < len(text) and text[after - 1].isascii() and text[after - 1].isalnum() and text[after].isascii() and text[after].isalnum():
            continue
        parts = []
        if before > 0:
            parts.append((base, base + before, False))
        parts.append((base + before, base + after, True))
        if after < len(text):
            parts.append((base + after, base + len(text), False))
        return parts
    return [(base, base + len(text), False)]


def prosody_segments(narration: str, emphasis: list[str] | None = None,
                     config: dict | None = None, role: str = "mechanism") -> list[dict]:
    """V3 delivery: sentence → clause → emphasis phrase.

    Edge TTS gives one rate/pitch per request.  V2 therefore applied a single
    contour to a whole 30-character sentence, so the middle of a long sentence was
    as flat as its ending.  Splitting at commas and around the emphasis phrase is
    the smallest change that produces audible phrasing: each clause can breathe,
    the keyword gets its own slower take, and the final clause lands a little
    slower.  Character offsets stay exact, so captions still map onto the merged
    word boundaries.
    """
    config = config or {}
    base_pitch = config.get("voice_pitch", "+0Hz")
    words = [word for word in (emphasis or []) if word]
    plan = prosody_plan(narration, emphasis, config)
    role_delta = {"hook": 2, "conclusion": -2, "turn": -1, "example": 0, "mechanism": 0}.get(role, 0)
    out: list[dict] = []
    for sentence in plan:
        text = narration[sentence["start"]:sentence["end"]]
        clauses = _split_clauses(text, sentence["start"])
        for clause_index, (begin, end) in enumerate(clauses):
            clause = narration[begin:end]
            last_clause = clause_index == len(clauses) - 1
            pieces = _split_emphasis(clause, begin, words)
            for piece_index, (pbegin, pend, marked) in enumerate(pieces):
                piece = narration[pbegin:pend]
                if not piece.strip():
                    continue
                rate_delta = 0
                pitch_delta = role_delta
                volume_delta = 0
                if marked:
                    rate_delta -= 10
                    pitch_delta += 1
                    volume_delta += 6
                if last_clause and len(piece) >= 5:
                    rate_delta -= 2
                if sentence["emphasis"] and not marked:
                    rate_delta -= 2
                if len(piece) > 34:
                    rate_delta += 2
                if last_clause:
                    pause_after = sentence["pause_after"]
                elif piece.endswith(("，", ",", "、", "：", ":")):
                    pause_after = 0.10
                else:
                    pause_after = 0.045
                if piece_index < len(pieces) - 1:
                    pause_after = 0.035
                if piece_index > 0:
                    pause_before = 0.025
                else:
                    pause_before = 0.0
                out.append({"text": piece, "start": pbegin, "end": pend,
                            "rate": _percent(sentence["rate"], rate_delta),
                            "pitch": _hertz(base_pitch, pitch_delta),
                            "volume": _percent(sentence["volume"], volume_delta),
                            "pause_after": pause_after, "pause_before": pause_before,
                            "emphasis": marked, "role": role})
    return [item for item in out if narration[item["start"]:item["end"]].strip()]


def voice(text: str, config: dict, cache: Path, *, rate: str | None = None,
          pitch: str | None = None, volume: str | None = None,
          adapter: str = "edge") -> tuple[np.ndarray, list[dict], list[Path]]:
    rate = rate or config["voice_rate"]
    pitch = pitch or config.get("voice_pitch", "+0Hz")
    volume = volume or config.get("voice_volume", "+0%")
    # The cache key names the adapter as well: a different backend for the same text,
    # voice and rate produces different audio.
    key = fingerprint({"text": text, "voice": config["voice"], "rate": rate, "pitch": pitch,
                       "volume": volume, "adapter": adapter, "version": TTS_VERSION})
    folder = cache / key
    folder.mkdir(parents=True, exist_ok=True)
    wav, mp3, timing = folder / "voice.wav", folder / "voice.mp3", folder / "timing.json"
    receipt = folder / "receipt.json"
    if receipt.exists():
        hashes = read_json(receipt)
        if all(p.exists() and hashes.get(p.name) == file_hash(p) for p in (wav, mp3, timing)):
            cached_audio, cached_timing = read_wav(wav), read_json(timing)
            if timing_matches_audio(cached_audio, cached_timing):
                return cached_audio, cached_timing, [wav, mp3, timing, receipt]
            print("[缓存] 配音时长与词语边界不一致，重新合成", flush=True)
    error = None
    for attempt in range(config["max_retries"] + 1):
        try:
            boundaries = asyncio.run(synthesize(text, config["voice"], rate, mp3, pitch, volume))
            run([ffmpeg(), "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE),
                 "-c:a", "pcm_s16le", str(wav)], timeout=90)
            audio = read_wav(wav)
            if len(audio) < SAMPLE_RATE // 8 or float(np.max(np.abs(audio))) < 0.001:
                raise RuntimeError("配音为空或近乎静音")
            if not timing_matches_audio(audio, boundaries):
                raise RuntimeError("词语边界超出音频时长，重新合成该段配音")
            atomic_json(timing, boundaries)
            atomic_json(receipt, {p.name: file_hash(p) for p in (wav, mp3, timing)})
            return audio, boundaries, [wav, mp3, timing, receipt]
        except Exception as exc:
            error = exc
            if attempt < config["max_retries"]:
                time.sleep(1 + attempt * 2)
    raise RuntimeError(f"配音失败，已保留缓存；不会降级为无声视频：{type(error).__name__}: {error}") from error


def trim_silence(audio: np.ndarray, *, threshold: float = 0.008,
                 keep_head: float = 0.05, keep_tail: float = 0.10) -> tuple[np.ndarray, float]:
    """Trim the engine's padding around one synthesised sentence.

    Edge TTS pads every utterance with ~0.2 s of silence before and ~0.9 s after.
    Concatenating sentences therefore added roughly 45 s of dead air to a 4-minute
    film, and the gaps were not the pauses the writing asked for.  The trimmed
    offset is returned so word boundaries can be shifted with the audio.
    """
    if len(audio) == 0:
        return audio, 0.0
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if len(loud) == 0:
        return audio, 0.0
    head = max(0, int(loud[0] - keep_head * SAMPLE_RATE))
    tail = min(len(audio), int(loud[-1] + keep_tail * SAMPLE_RATE))
    return audio[head:tail], head / SAMPLE_RATE


def captions(text: str, boundaries: list[dict], duration: float, max_chars: int,
             spoken: str | None = None, origin: list[int] | None = None) -> tuple[list[dict], str]:
    """Time caption pages of *text* (what viewers read) against TTS word boundaries.

    ``spoken`` is what the voice actually says, and ``origin`` maps each of its
    characters back to an index in *text*.  A pronunciation replacement therefore
    changes the audio without changing the caption on screen.

    Each page also carries its own word timings, which the renderer uses for
    karaoke highlighting: a caption that appears as one block for two seconds and
    then jumps is harder to follow than one whose words light up as they are said.
    """
    speech = text if spoken is None else spoken
    source = list(range(len(speech))) if origin is None else origin
    if len(source) != len(speech):
        # A mismatched map would misplace every caption; fall back to display order.
        speech, source = text, list(range(len(text)))
    parts = caption_chunks(text, max_chars)
    positions, cursor = [], 0
    for boundary in boundaries:
        start = speech.find(boundary["text"], cursor)
        if start < 0:
            continue
        end = start + len(boundary["text"])
        cursor = end
        last_index = min(end, len(source)) - 1
        if last_index < start or last_index < 0:
            continue
        first = source[start] if start < len(source) else len(text)
        last = source[last_index] + 1
        positions.append((first, last, boundary["start"], boundary["end"], boundary["text"]))
    pages, cursor, previous_end = [], 0, 0.0
    mode = "tts-word-boundaries" if positions else "estimated-character-timing"
    for part in parts:
        if not part:
            continue
        start, end = cursor, cursor + len(part)
        matched = [p for p in positions if p[0] < end and p[1] > start]
        t0 = matched[0][2] if matched else duration * start / max(1, len(text))
        t1 = matched[-1][3] if matched else duration * end / max(1, len(text))
        # Two pages can share one TTS word when a page boundary falls inside it; the
        # second page must not start before the first one ended, or the timeline
        # check rejects the cut ("字幕交叠").
        t0 = max(t0, previous_end)
        t1 = max(t1, t0 + 0.15)
        words = [{"text": item[4], "start": round(item[2], 3), "end": round(item[3], 3)}
                 for item in matched]
        pages.append({"start": min(t0, duration), "end": min(t1, duration),
                      "text": part.strip(" ，。！？；：,.!?;:"), "words": words})
        previous_end = pages[-1]["end"]
        cursor = end
    # Silence between clauses keeps the last caption briefly visible, without overlapping the next.
    for i, page in enumerate(pages):
        next_start = pages[i + 1]["start"] if i + 1 < len(pages) else duration
        page["end"] = max(page["start"], min(next_start, max(page["end"], page["start"] + 0.5)))
    return [p for p in pages if p["text"] and p["end"] > p["start"]], mode


def speech_plan(narration: str, replacements: dict | None = None) -> tuple[str, list[int]]:
    """Text to speak plus a map from each spoken character back to the narration.

    ``speech_replace`` exists to fix how TTS reads a symbol (「熵」→「商」).  The
    caption must keep showing the written word, so audio text and display text are
    kept apart and :func:`captions` maps one onto the other.  Without replacements
    the mapping is the identity.
    """
    pairs = [(source, target) for source, target in (replacements or {}).items()
             if isinstance(source, str) and source and isinstance(target, str)]
    if not pairs:
        return narration, list(range(len(narration)))
    # Longest source first so 「行列式」 wins over 「行」.
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    spoken: list[str] = []
    origin: list[int] = []
    index = 0
    while index < len(narration):
        for source, target in pairs:
            if narration.startswith(source, index):
                for offset in range(len(target)):
                    spoken.append(target[offset])
                    origin.append(index + min(offset, len(source) - 1))
                index += len(source)
                break
        else:
            spoken.append(narration[index])
            origin.append(index)
            index += 1
    return "".join(spoken), origin


def prepare_cut(cut: dict, config: dict, cache: Path, output: Path, *, portrait: bool) -> tuple[dict, list[Path]]:
    from .models import Scene
    from .scenedsl import normalize_scene
    from .speech import describe, speech_settings

    fps = config["fps"]
    style = cut.get("style", "tech")
    replacements = config.get("speech_replace") or {}
    chunks, starts, paths, scenes, cursor = [], [], [], [], 0
    script_events: list[dict] = []
    settings = speech_settings({"studio": config})
    speech_records: list[dict] = []
    scene_seconds: list[float] = []
    lead = 0.25
    for raw in cut["scenes"]:
        scene = Scene.model_validate(raw)
        spoken, origin = speech_plan(scene.narration, replacements)
        # Synthesise sentence by sentence: each sentence gets its own rate/pitch,
        # and the pause between sentences is real silence rather than the engine's
        # own comma timing.  Boundaries are offset into scene time as they are merged.
        pieces, boundaries = [], []
        position = 0.0
        for segment in prosody_segments(spoken, scene.emphasis, config, role=scene.role):
            begin, end = segment["start"], segment["end"]
            if not spoken[begin:end].strip():
                continue
            before = float(segment.get("pause_before") or 0.0)
            if before > 0:
                pieces.append(np.zeros(int(before * SAMPLE_RATE), dtype=np.float32))
                position += before
            audio, local, generated = voice(spoken[begin:end], config, cache,
                                            rate=segment["rate"], pitch=segment["pitch"],
                                            volume=segment["volume"])
            paths.extend(generated)
            audio, trimmed = trim_silence(audio)
            pieces.append(audio)
            span = len(audio) / SAMPLE_RATE
            for boundary in local:
                start_at = max(0.0, boundary["start"] - trimmed)
                end_at = min(span, boundary["end"] - trimmed)
                if end_at <= start_at:
                    continue
                boundaries.append({"text": boundary["text"], "start": start_at + position,
                                   "end": end_at + position})
            position += span
            pause = segment["pause_after"]
            pieces.append(np.zeros(int(pause * SAMPLE_RATE), dtype=np.float32))
            position += pause
        audio = np.concatenate(pieces) if pieces else np.zeros(SAMPLE_RATE // 4, dtype=np.float32)
        seconds = len(audio) / SAMPLE_RATE
        frames = math.ceil((seconds + lead + 0.85) * fps)
        samples = round(frames / fps * SAMPLE_RATE)
        chunk = np.zeros(samples, dtype=np.float32)
        begin = round(lead * SAMPLE_RATE)
        chunk[begin:begin + len(audio)] = audio
        # The caption shows the written narration; only the voice uses the replacement.
        pages, timing = captions(scene.narration, boundaries, seconds,
                                 16 if portrait else 25, spoken=spoken, origin=origin)
        for page in pages:
            page["start"] += lead
            page["end"] += lead
            for word in page.get("words", []):
                word["start"] = round(word["start"] + lead, 3)
                word["end"] = round(word["end"] + lead, 3)
        shifted = [{"text": b["text"], "start": b["start"] + lead, "end": b["end"] + lead}
                   for b in boundaries]
        normalized = normalize_scene(scene, duration=frames / fps, boundaries=shifted, vertical=portrait)
        normalized.update({"frames": frames, "captions": pages, "caption_timing": timing})
        if spoken != scene.narration:
            normalized["spoken_narration"] = spoken
        speech_records.append(describe(
            settings.backend, audio, boundaries, settings=settings, text=scene.narration,
            reading=spoken, sample_rate=SAMPLE_RATE,
            boundary_source="native" if boundaries else "estimated").model_dump())
        scenes.append(normalized)
        starts.append(cursor / SAMPLE_RATE)
        scene_seconds.append(frames / fps)
        for cue in normalized.get("cues_resolved", []):
            script_events.append({"at": cursor / SAMPLE_RATE + lead + cue["at"],
                                  "kind": cue["kind"], "gain": cue["gain"],
                                  "pan": 0.0, "send": 0.24, "priority": 9,
                                  "source": "director"})
        cursor += samples
        chunks.append(chunk)
    narration = np.concatenate(chunks)
    duration = len(narration) / SAMPLE_RATE
    sections = []
    role_energy = {"hook": 0.72, "mechanism": 0.56, "example": 0.46, "turn": 0.80, "conclusion": 0.66}
    for index, scene in enumerate(scenes):
        begin = starts[index]
        end = begin + scene_seconds[index]
        emphasis = len(scene.get("emphasis") or [])
        sections.append({"start": begin, "end": end,
                         "energy": min(1.0, role_energy.get(scene.get("role", "mechanism"), 0.56)
                                       + 0.06 * emphasis),
                         "role": scene.get("role", "mechanism")})
    events = design_sound_events(scenes, fps=fps, scene_starts=starts, lead=lead,
                                 duration=duration, extra=script_events)
    output.mkdir(parents=True, exist_ok=True)
    dry, mixed = output / "narration.wav", output / "mix.wav"
    write_wav(dry, narration)
    from .mix import mix_report, write_stems
    from .sound import soundtrack_stems

    mixed_audio, stems = soundtrack_stems(narration, starts, style, cues=events,
                                          scene_seconds=scene_seconds, sections=sections)
    write_wav(mixed, mixed_audio)
    stem_paths = write_stems(stems, output / "stems")
    # Measured on the stems, before encoding: a missing voice must be provable from
    # the voice stem, and a decorative stem may not outweigh the voice.
    report = mix_report(stems, events, mix=mixed_audio)
    paths.extend([dry, mixed, *[Path(path) for path in stem_paths.values()]])
    return {"title": cut["title"], "scenes": scenes, "frames": sum(s["frames"] for s in scenes),
            "seconds": duration, "mix": str(mixed), "voice": str(dry),
            "style": style, "cues": events, "sound_events": events,
            "prosody": "clause+emphasis",
            # What actually produced the audio: backend, voice, real sample counts and
            # where the boundaries came from, per scene.
            "mix_report": report, "stems": stem_paths,
            "speech": {"backend": settings.backend, "voice": settings.voice,
                       "model": settings.model, "granularity": settings.granularity,
                       "sample_rate": SAMPLE_RATE, "characters": sum(r["characters"] for r in speech_records),
                       "boundary_sources": sorted({r["boundary_source"] for r in speech_records}),
                       "scenes": speech_records}}, paths


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
