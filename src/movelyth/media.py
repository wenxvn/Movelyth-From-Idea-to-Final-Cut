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

from .textfit import caption_chunks
from .util import atomic_json, file_hash, fingerprint, read_json, run

SAMPLE_RATE = 24000
# Bump when the synthesis pipeline changes in a way that alters the audio, so the
# voice cache does not serve audio made by the old implementation.
TTS_VERSION = 2


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


def voice(text: str, config: dict, cache: Path, *, rate: str | None = None,
          pitch: str | None = None, volume: str | None = None) -> tuple[np.ndarray, list[dict], list[Path]]:
    rate = rate or config["voice_rate"]
    pitch = pitch or config.get("voice_pitch", "+0Hz")
    volume = volume or config.get("voice_volume", "+0%")
    key = fingerprint({"text": text, "voice": config["voice"], "rate": rate, "pitch": pitch,
                       "volume": volume, "version": TTS_VERSION})
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


# ------------------------------------------------------------------------ music


def _semitones(root: float, steps: float) -> float:
    return root * (2.0 ** (steps / 12.0))


def _adsr(size: int, attack: float, release: float, curve: float = 1.0) -> np.ndarray:
    """Deterministic attack/release envelope; avoids the click a hard edge makes."""
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    seconds = size / SAMPLE_RATE
    up = np.clip(t / max(1e-4, attack), 0, 1)
    down = np.clip((seconds - t) / max(1e-4, release), 0, 1)
    env = np.minimum(up, down) ** curve
    return env.astype(np.float32)


def _onepole(signal: np.ndarray, cutoff) -> np.ndarray:
    """One-pole lowpass with a scalar or time-varying cutoff (in Hz).

    Implemented with FFT convolution of the exact exponential kernel, in blocks
    when the cutoff moves.  A per-sample Python loop over a five-minute stereo bed
    is far too slow, and a truncated IIR kernel is accurate to well below the noise
    floor here.
    """
    size = len(signal)
    if size == 0:
        return signal
    values = np.atleast_1d(np.asarray(cutoff, dtype=np.float64))
    if values.size == 1:
        alpha = 1.0 - math.exp(-2.0 * math.pi * max(20.0, float(values[0])) / SAMPLE_RATE)
        length = int(min(size, max(8, math.ceil(7.0 / max(alpha, 1e-6)))))
        kernel = (alpha * (1 - alpha) ** np.arange(length)).astype(np.float32)
        nfft = 1 << (size + length - 1).bit_length()
        spectrum = np.fft.rfft(signal, nfft) * np.fft.rfft(kernel, nfft)
        return np.fft.irfft(spectrum, nfft)[:size].astype(np.float32)
    block = max(64, int(math.ceil(size / values.size)))
    out = np.empty(size, dtype=np.float32)
    state = 0.0
    for index in range(0, size, block):
        end = min(size, index + block)
        alpha = 1.0 - math.exp(-2.0 * math.pi * max(20.0, float(values[min(index // block,
                                                                       values.size - 1)])) / SAMPLE_RATE)
        length = end - index
        kernel = (alpha * (1 - alpha) ** np.arange(length)).astype(np.float32)
        nfft = 1 << (2 * length - 1).bit_length()
        spectrum = np.fft.rfft(signal[index:end], nfft) * np.fft.rfft(kernel, nfft)
        convolved = np.fft.irfft(spectrum, nfft)[:length]
        decay = (1 - alpha) ** (np.arange(length) + 1)
        out[index:end] = convolved + state * decay
        state = float(out[end - 1])
    return out


def _noise(size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(size).astype(np.float32)


def _soft_clip(signal: np.ndarray, drive: float = 1.2) -> np.ndarray:
    return np.tanh(signal * drive).astype(np.float32)


# Style presets: tempo, root, chord progression in semitones from the root, and
# how dense the arrangement is.  Kept as data so a new style is a table entry.
MUSIC_PRESETS = {
    "tech": {
        "bpm": 96, "root": 55.0,
        "chords": [(0, 3, 7), (-4, 0, 3), (3, 7, 10), (-2, 2, 5)],
        "pad": 0.030, "bass": 0.034, "arp": 0.018, "perc": 0.012, "swing": 0.0,
    },
    "minimal": {
        "bpm": 72, "root": 65.41,
        "chords": [(0, 4, 7), (-3, 0, 4), (5, 9, 12), (-5, -1, 2)],
        "pad": 0.036, "bass": 0.024, "arp": 0.015, "perc": 0.0, "swing": 0.0,
    },
    "documentary": {
        "bpm": 64, "root": 49.0,
        "chords": [(0, 3, 7), (-4, 0, 3), (-2, 2, 5), (0, 3, 7)],
        "pad": 0.032, "bass": 0.030, "arp": 0.010, "perc": 0.006, "swing": 0.0,
    },
}


def _music_bed(size: int, style: str) -> np.ndarray:
    """Sectioned bed: sparse intro, full body, fading outro.

    V1 repeated one four-chord loop every 8 s for the whole film.  Here the same
    progression is arranged by section, with a low bass, a detuned pad, a plucked
    arpeggio and a light pulse, so the music has a shape that matches the story.
    """
    preset = MUSIC_PRESETS.get(style, MUSIC_PRESETS["tech"])
    bpm = preset["bpm"]
    beat = 60.0 / bpm
    bar = beat * 4
    root = preset["root"]
    chords = preset["chords"]
    total_seconds = size / SAMPLE_RATE
    music = np.zeros(size, dtype=np.float32)
    arp_left = np.zeros(size, dtype=np.float32)
    arp_right = np.zeros(size, dtype=np.float32)
    # Section boundaries: 8% intro, 84% body, 8% outro, with a minimum length so a
    # 60 s short still has all three.
    intro = min(max(6.0, total_seconds * 0.08), total_seconds * 0.3)
    outro = min(max(5.0, total_seconds * 0.08), total_seconds * 0.3)

    def place(buffer: np.ndarray, at: float, wave_data: np.ndarray, gain: float, channel=None):
        begin = int(at * SAMPLE_RATE)
        if begin >= size or gain <= 0:
            return
        end = min(size, begin + len(wave_data))
        if end <= begin:
            return
        segment = wave_data[:end - begin] * gain
        if channel is None:
            buffer[begin:end] += segment
        else:
            channel[begin:end] += segment

    bar_count = int(math.ceil(total_seconds / bar)) + 1
    for bar_index in range(bar_count):
        at = bar_index * bar
        if at >= total_seconds:
            break
        chord = chords[bar_index % len(chords)]
        in_intro = at < intro
        in_outro = at >= total_seconds - outro
        body = not in_intro and not in_outro
        # Pad: three chord tones, two octaves up, slightly detuned per channel.
        pad_length = int((bar + 0.4) * SAMPLE_RATE)
        env = _adsr(pad_length, 0.9, 0.9, 1.3)
        local = np.arange(pad_length, dtype=np.float32) / SAMPLE_RATE
        pad = np.zeros(pad_length, dtype=np.float32)
        for offset in chord:
            freq = _semitones(root, offset) * 2
            pad += np.sin(2 * np.pi * freq * local) * 0.55
            pad += np.sin(2 * np.pi * freq * 2.002 * local) * 0.16
            pad += np.sin(2 * np.pi * freq * 0.999 * local) * 0.30
        pad /= max(1, len(chord))
        gain = preset["pad"] * (0.7 if in_intro or in_outro else 1.0)
        place(music, at, pad * env, gain)
        # Bass: only in the body, one octave below the root, long and soft.
        if body:
            bass_env = _adsr(pad_length, 0.05, 0.5, 1.6)
            bass = np.sin(2 * np.pi * root * local) + 0.25 * np.sin(2 * np.pi * root * 2 * local)
            place(music, at, bass * bass_env, preset["bass"])
        # Arpeggio: eighth notes through the chord, panned alternately.
        if preset["arp"] > 0 and (body or in_intro):
            steps = 8 if body else 4
            for step in range(steps):
                note_at = at + step * (bar / steps)
                if note_at >= total_seconds:
                    break
                tone = _semitones(root, chord[step % len(chord)] + 12)
                length = int(0.9 * SAMPLE_RATE)
                lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                pluck = (np.sin(2 * np.pi * tone * lt) + 0.28 * np.sin(2 * np.pi * tone * 2 * lt))
                pluck *= np.exp(-lt * 5.5)
                gain = preset["arp"] * (0.6 if in_intro else 1.0) * (0.8 if step % 2 else 1.0)
                if step % 2:
                    place(arp_right, note_at, pluck, gain)
                else:
                    place(arp_left, note_at, pluck, gain)
        # Percussion: a soft kick on 1 and 3, a tick on the offbeats.
        if preset["perc"] > 0 and body:
            for beat_index in range(4):
                beat_at = at + beat_index * beat
                if beat_index in (0, 2):
                    length = int(0.32 * SAMPLE_RATE)
                    lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                    kick = np.sin(2 * np.pi * (58 - 22 * lt / 0.32) * lt) * np.exp(-lt * 16)
                    place(music, beat_at, kick, preset["perc"] * 1.4)
                else:
                    length = int(0.06 * SAMPLE_RATE)
                    lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                    hat = _noise(length, 17 + beat_index) * np.exp(-lt * 60)
                    hat = _onepole(hat, 6000) - _onepole(hat, 2500)
                    place(music, beat_at, hat, preset["perc"] * 0.35)
    return music, arp_left, arp_right


def _sidechain(voice_track: np.ndarray, *, floor: float = 0.26, ceiling: float = 0.92) -> np.ndarray:
    """Smooth ducking with a real attack and release.

    V1 switched between 0.32 and 0.9 on a 20 ms window, which pumps audibly at
    every syllable boundary.  A one-pole follower with different attack and release
    times is what a compressor does to a music bed under a voice.
    """
    size = len(voice_track)
    window = max(1, SAMPLE_RATE // 100)
    frames = size // window
    if frames < 2:
        return np.ones(size, dtype=np.float32)
    energy = np.sqrt(np.mean(voice_track[:frames * window].reshape(frames, window) ** 2, axis=1))
    loud = np.clip((energy - 0.004) / 0.018, 0, 1).astype(np.float32)
    attack = 1.0 - math.exp(-1.0 / (0.018 * 100))    # 18 ms
    release = 1.0 - math.exp(-1.0 / (0.28 * 100))    # 280 ms
    smoothed = np.empty(frames, dtype=np.float32)
    value = 0.0
    for index in range(frames):
        coefficient = attack if loud[index] > value else release
        value += coefficient * (loud[index] - value)
        smoothed[index] = value
    gain = ceiling + (floor - ceiling) * smoothed
    interpolated = np.interp(np.arange(size), np.arange(frames) * window, gain).astype(np.float32)
    # Lookahead: a compressor without it can only react after the syllable has
    # started, which is exactly when a bed at full level covers the first word of a
    # new scene.  Taking the minimum over the next 90 ms ducks slightly early.
    lookahead = int(0.09 * SAMPLE_RATE)
    if lookahead < size:
        early = np.empty(size, dtype=np.float32)
        early[:-lookahead] = interpolated[lookahead:]
        early[-lookahead:] = interpolated[-1]
        interpolated = np.minimum(interpolated, early)
    return interpolated


def _sfx(kind: str, seed: int = 7) -> np.ndarray:
    """Synthesise one short sound effect.  No sample libraries, no licence risk."""
    if kind == "tick":
        length = int(0.09 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        tone = np.sin(2 * np.pi * 2100 * t) * np.exp(-t * 70)
        click = _noise(length, seed) * np.exp(-t * 120) * 0.5
        return _soft_clip((tone + click) * 0.5)
    if kind == "whoosh":
        length = int(0.55 * SAMPLE_RATE)
        noise = _noise(length, seed)
        sweep = np.linspace(320, 2600, 12)
        filtered = _onepole(noise, sweep)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        env = np.sin(np.pi * np.clip(t / 0.55, 0, 1)) ** 1.6
        return _soft_clip(filtered * env * 1.5)
    if kind == "impact":
        length = int(0.7 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        thump = np.sin(2 * np.pi * (78 - 34 * np.clip(t / 0.3, 0, 1)) * t) * np.exp(-t * 7)
        body = _onepole(_noise(length, seed + 3), 900) * np.exp(-t * 22) * 0.7
        return _soft_clip((thump + body) * 0.9)
    if kind == "riser":
        length = int(1.3 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        sweep = np.linspace(180, 780, 26)
        tone = np.sin(2 * np.pi * np.cumsum(np.interp(np.arange(length),
                                                     np.linspace(0, length, 26), sweep)) / SAMPLE_RATE)
        noise = _onepole(_noise(length, seed + 5), np.linspace(600, 5000, 26))
        env = np.clip(t / 1.3, 0, 1) ** 1.4
        return _soft_clip((tone * 0.5 + noise * 0.7) * env)
    # chime
    length = int(1.0 * SAMPLE_RATE)
    t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
    tone = (np.sin(2 * np.pi * 880 * t) * 0.6 + np.sin(2 * np.pi * 1320 * t) * 0.3
            + np.sin(2 * np.pi * 1760 * t) * 0.12)
    return _soft_clip(tone * np.exp(-t * 3.4) * 0.7)


SFX = {kind: _sfx(kind, seed=11 + index * 7)
       for index, kind in enumerate(["tick", "whoosh", "impact", "riser", "chime"])}


def _process_voice(voice_track: np.ndarray) -> np.ndarray:
    """High-pass rumble, a little presence, gentle levelling.

    Edge TTS output is clean but thin and its level varies between sentences.  A
    one-pole high-pass at ~95 Hz removes rumble, a small presence lift adds
    intelligibility, and a slow compressor evens out the sentences without
    squashing the consonants.
    """
    size = len(voice_track)
    if size == 0:
        return voice_track
    low = _onepole(voice_track, 95)
    high = voice_track - low
    presence = high - _onepole(high, 2600)
    shaped = high + presence * 0.22
    window = max(1, SAMPLE_RATE // 20)
    frames = size // window
    if frames > 2:
        rms = np.sqrt(np.mean(shaped[:frames * window].reshape(frames, window) ** 2, axis=1))
        target = np.percentile(rms[rms > 0.005], 70) if np.any(rms > 0.005) else 0.08
        gain = np.clip(target / np.maximum(rms, 1e-4), 0.62, 1.32)
        smoothed = np.empty(frames, dtype=np.float32)
        value = 1.0
        for index in range(frames):
            value += (0.08 if gain[index] < value else 0.02) * (gain[index] - value)
            smoothed[index] = value
        shaped = shaped * np.interp(np.arange(size), np.arange(frames) * window,
                                    smoothed).astype(np.float32)
    return _soft_clip(shaped, 1.05) * 0.92


def soundtrack(voice_track: np.ndarray, scene_starts: list[float], style: str = "tech",
               *, cues: list[dict] | None = None, scene_seconds: list[float] | None = None) -> np.ndarray:
    """Narration + arranged music + synchronised sound effects, as stereo PCM.

    ``cues`` are absolute-second events produced by the director (a whoosh on a
    transition, a tick on a number landing).  They are mixed *under* the voice so a
    cue punctuates the picture instead of competing with the sentence.
    """
    size = len(voice_track)
    music, arp_left, arp_right = _music_bed(size, style)
    bed = music + arp_left * 0.9 + arp_right * 0.9
    duck = _sidechain(voice_track)
    if cues:
        for cue in cues:
            sound = SFX.get(cue.get("kind", ""))
            if sound is None:
                continue
            begin = int(float(cue.get("at", 0)) * SAMPLE_RATE)
            if begin < 0 or begin >= size:
                continue
            end = min(size, begin + len(sound))
            # A cue punctuates the picture; it must never be louder than the voice.
            # Ducking it with the same follower (but a higher floor than the music)
            # is what keeps a whoosh from covering the first word of a sentence.
            window = duck[begin:end]
            bed[begin:end] += sound[:end - begin] * float(cue.get("gain", 0.6)) * 0.28 * (0.3 + 0.7 * window)
    # A single low "impact" at each scene start would be noise; instead the scene
    # starts get a barely audible swell that marks the chapter change.
    for start in scene_starts[1:]:
        begin = int(start * SAMPLE_RATE)
        length = min(int(0.5 * SAMPLE_RATE), max(0, size - begin))
        if length <= 0:
            continue
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        bed[begin:begin + length] += (np.sin(2 * np.pi * 110 * t) * np.exp(-t * 6)
                                      * 0.004).astype(np.float32)
    voice = _process_voice(voice_track)
    total = size / SAMPLE_RATE
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    # Fade the whole bed (not the voice) in and out; the voice already has padding.
    fade = np.minimum(np.clip(t / 1.3, 0, 1), np.clip((total - t) / 1.8, 0, 1))
    bed = bed * duck * fade
    # Stereo width from a short, quiet delay on the arpeggio side only: a wide pad
    # would pull the voice off-centre when summed to mono on a phone speaker.
    left = voice * 0.92 + bed
    right = voice * 0.92 + bed
    return np.stack([left, right], axis=1).astype(np.float32)


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

    fps = config["fps"]
    style = cut.get("style", "tech")
    replacements = config.get("speech_replace") or {}
    chunks, starts, paths, scenes, cursor = [], [], [], [], 0
    absolute_cues: list[dict] = []
    scene_seconds: list[float] = []
    for raw in cut["scenes"]:
        scene = Scene.model_validate(raw)
        spoken, origin = speech_plan(scene.narration, replacements)
        # Synthesise sentence by sentence: each sentence gets its own rate/pitch,
        # and the pause between sentences is real silence rather than the engine's
        # own comma timing.  Boundaries are offset into scene time as they are merged.
        pieces, boundaries = [], []
        position = 0.0
        for segment in prosody_plan(spoken, scene.emphasis, config):
            begin, end = segment["start"], segment["end"]
            if not spoken[begin:end].strip():
                continue
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
        lead = 0.25
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
        scenes.append(normalized)
        starts.append(cursor / SAMPLE_RATE)
        scene_seconds.append(frames / fps)
        for cue in normalized.get("cues_resolved", []):
            absolute_cues.append({"at": cursor / SAMPLE_RATE + lead + cue["at"],
                                  "kind": cue["kind"], "gain": cue["gain"]})
        cursor += samples
        chunks.append(chunk)
    narration = np.concatenate(chunks)
    output.mkdir(parents=True, exist_ok=True)
    dry, mixed = output / "narration.wav", output / "mix.wav"
    write_wav(dry, narration)
    write_wav(mixed, soundtrack(narration, starts, style, cues=absolute_cues,
                                scene_seconds=scene_seconds))
    paths.extend([dry, mixed])
    return {"title": cut["title"], "scenes": scenes, "frames": sum(s["frames"] for s in scenes),
            "seconds": len(narration) / SAMPLE_RATE, "mix": str(mixed), "voice": str(dry),
            "style": style, "cues": absolute_cues, "prosody": "sentence"}, paths


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
