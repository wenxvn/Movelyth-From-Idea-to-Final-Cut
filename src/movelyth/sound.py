"""V3 sound design: adaptive bed, automatic Foley, room and reverb.

This module owns all audio synthesis (V2 kept a second copy in ``media.py``;
the two would have drifted).  ``media.py`` only does TTS, timing and captions.

The V2 soundtrack was one arranged loop plus nine director-authored cues.  This
module adds the missing half of sound design:

* **Automatic events** derived from the real animation timeline: every draw,
  reveal, highlight and transition gets a small Foley event, and a conclusion
  gets a sub/impact.  The director can still author cues; automatic events are
  deduplicated against them.
* **An adaptive bed**: pad / bass / arpeggio / pulse appear according to the
  scene's role and emphasis density instead of looping the same four bars.
* **A shared space**: one synthetic reverb bus for Foley, a low room tone, and
  equal-power panning, so effects sit in the same room as the voice.

Everything is synthesised locally with numpy; no samples, no licences, no GPU.
"""
from __future__ import annotations

import math

import numpy as np

SAMPLE_RATE = 24000


def _semitones(root: float, steps: float) -> float:
    return root * (2.0 ** (steps / 12.0))


def _noise(size: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(size).astype(np.float32)


def _soft_clip(signal: np.ndarray, drive: float = 1.2) -> np.ndarray:
    return np.tanh(signal * drive).astype(np.float32)


def _onepole(signal: np.ndarray, cutoff: float | np.ndarray) -> np.ndarray:
    """One-pole lowpass; a moving cutoff is applied in blocks."""
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
        alpha = 1.0 - math.exp(-2.0 * math.pi * max(20.0, float(values[min(index // block, values.size - 1)])) / SAMPLE_RATE)
        length = end - index
        kernel = (alpha * (1 - alpha) ** np.arange(length)).astype(np.float32)
        nfft = 1 << (2 * length - 1).bit_length()
        spectrum = np.fft.rfft(signal[index:end], nfft) * np.fft.rfft(kernel, nfft)
        convolved = np.fft.irfft(spectrum, nfft)[:length]
        decay = (1 - alpha) ** (np.arange(length) + 1)
        out[index:end] = convolved + state * decay
        state = float(out[end - 1])
    return out


def _adsr(size: int, attack: float, release: float, curve: float = 1.0) -> np.ndarray:
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    seconds = size / SAMPLE_RATE
    up = np.clip(t / max(1e-4, attack), 0, 1)
    down = np.clip((seconds - t) / max(1e-4, release), 0, 1)
    return (np.minimum(up, down) ** curve).astype(np.float32)


def _sidechain(voice_track: np.ndarray, *, floor: float = 0.26, ceiling: float = 0.92) -> np.ndarray:
    size = len(voice_track)
    window = max(1, SAMPLE_RATE // 100)
    frames = size // window
    if frames < 2:
        return np.ones(size, dtype=np.float32)
    energy = np.sqrt(np.mean(voice_track[:frames * window].reshape(frames, window) ** 2, axis=1))
    loud = np.clip((energy - 0.004) / 0.018, 0, 1).astype(np.float32)
    attack = 1.0 - math.exp(-1.0 / (0.018 * 100))
    release = 1.0 - math.exp(-1.0 / (0.30 * 100))
    smoothed = np.empty(frames, dtype=np.float32)
    value = 0.0
    for index in range(frames):
        coefficient = attack if loud[index] > value else release
        value += coefficient * (loud[index] - value)
        smoothed[index] = value
    gain = ceiling + (floor - ceiling) * smoothed
    interpolated = np.interp(np.arange(size), np.arange(frames) * window, gain).astype(np.float32)
    lookahead = int(0.09 * SAMPLE_RATE)
    if lookahead < size:
        early = np.empty(size, dtype=np.float32)
        early[:-lookahead] = interpolated[lookahead:]
        early[-lookahead:] = interpolated[-1]
        interpolated = np.minimum(interpolated, early)
    return interpolated


def _impulse(seconds: float, seed: int = 23) -> np.ndarray:
    """A small synthetic hall: early reflections plus a smooth exponential tail."""
    length = max(1, int(seconds * SAMPLE_RATE))
    t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
    tail = _noise(length, seed) * np.exp(-t * 5.2)
    tail = _onepole(tail, 4200.0)
    tail[: int(0.012 * SAMPLE_RATE)] *= 0.15
    for delay, gain in ((0.019, 0.45), (0.031, 0.32), (0.047, 0.24), (0.071, 0.17)):
        start = int(delay * SAMPLE_RATE)
        if start < length:
            tail[start] += gain
    # Normalise by the sum of |h|, not the peak: a peak-normalised 0.85 s tail
    # has a sum of ~1200 and made the wet bus louder than the dry signal.
    return (tail / max(1e-6, float(np.sum(np.abs(tail))))).astype(np.float32)


_IMPULSE = _impulse(0.85)


def _reverb(signal: np.ndarray, send: float = 0.35) -> np.ndarray:
    """Convolve a mono send with the shared impulse; returns mono wet signal."""
    if len(signal) == 0 or send <= 0:
        return np.zeros_like(signal)
    nfft = 1 << (len(signal) + len(_IMPULSE) - 1).bit_length()
    spectrum = np.fft.rfft(signal, nfft) * np.fft.rfft(_IMPULSE, nfft)
    wet = np.fft.irfft(spectrum, nfft)[: len(signal)].astype(np.float32)
    return wet * send


def _pan(sound: np.ndarray, pan: float) -> tuple[np.ndarray, np.ndarray]:
    """Equal-power pan; pan is -1 (left) … 0 (centre) … 1 (right)."""
    angle = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    return (sound * math.cos(angle)).astype(np.float32), (sound * math.sin(angle)).astype(np.float32)


# ----------------------------------------------------------------------- SFX


def _sfx(kind: str, seed: int = 7) -> np.ndarray:
    if kind == "tick":
        length = int(0.10 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        tone = np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 62)
        tone += 0.35 * np.sin(2 * np.pi * 2790 * t) * np.exp(-t * 90)
        click = _noise(length, seed) * np.exp(-t * 150) * 0.45
        return _soft_clip((tone + click) * 0.40)
    if kind == "tick_soft":
        length = int(0.075 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        tone = np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 70)
        click = _onepole(_noise(length, seed + 1), 5200) * np.exp(-t * 120) * 0.6
        return _soft_clip((tone * 0.7 + click) * 0.26)
    if kind == "pop":
        length = int(0.14 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        freq = 420 - 250 * np.clip(t / 0.14, 0, 1)
        tone = np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE) * np.exp(-t * 28)
        click = _noise(length, seed + 2) * np.exp(-t * 90) * 0.35
        return _soft_clip((tone + click) * 0.42)
    if kind == "swipe":
        length = int(0.38 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        sweep = np.interp(np.arange(length), np.linspace(0, length, 7),
                          [600, 1500, 3200, 4200, 2600, 1500, 900])
        noise = _onepole(_noise(length, seed + 3), sweep)
        noise -= _onepole(noise, 300)
        env = np.sin(np.pi * np.clip(t / 0.38, 0, 1)) ** 1.5
        return _soft_clip(noise * env * 1.3)
    if kind == "whoosh":
        length = int(0.55 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        sweep = np.linspace(280, 2900, 12)
        filtered = _onepole(_noise(length, seed), sweep)
        filtered -= _onepole(filtered, 220)
        env = np.sin(np.pi * np.clip(t / 0.55, 0, 1)) ** 1.4
        return _soft_clip(filtered * env * 1.2)
    if kind == "impact":
        length = int(0.95 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        thump = np.sin(2 * np.pi * (82 - 38 * np.clip(t / 0.32, 0, 1)) * t) * np.exp(-t * 6.5)
        body = _onepole(_noise(length, seed + 3), 700) * np.exp(-t * 18) * 0.65
        tail = np.sin(2 * np.pi * 54 * t) * np.exp(-t * 3.2) * 0.35
        return _soft_clip((thump + body + tail) * 0.85, 1.3)
    if kind == "sub":
        length = int(0.9 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        freq = 58 - 20 * np.clip(t / 0.5, 0, 1)
        tone = np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE) * np.exp(-t * 4.5)
        return _soft_clip(tone * 0.7, 1.6)
    if kind == "riser":
        length = int(1.5 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        sweep = np.linspace(160, 920, 30)
        tone = np.sin(2 * np.pi * np.cumsum(np.interp(np.arange(length), np.linspace(0, length, 30), sweep)) / SAMPLE_RATE)
        noise = _onepole(_noise(length, seed + 5), np.linspace(500, 6000, 30))
        env = np.clip(t / 1.5, 0, 1) ** 1.6
        return _soft_clip((tone * 0.35 + noise * 0.75) * env * 0.7)
    if kind == "riser_short":
        length = int(0.8 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        noise = _onepole(_noise(length, seed + 6), np.linspace(700, 5200, 20))
        env = np.clip(t / 0.8, 0, 1) ** 2.0
        tone = np.sin(2 * np.pi * (220 + 440 * t / 0.8) * t) * 0.2
        return _soft_clip((noise * 0.6 + tone) * env * 0.6)
    if kind == "chime":
        length = int(1.15 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        tone = (np.sin(2 * np.pi * 880 * t) * 0.5 + np.sin(2 * np.pi * 1320 * t) * 0.28
                + np.sin(2 * np.pi * 1760 * t) * 0.14 + np.sin(2 * np.pi * 2640 * t) * 0.06)
        return _soft_clip(tone * np.exp(-t * 3.0) * 0.55)
    if kind == "shimmer":
        length = int(0.9 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        tone = np.zeros(length, dtype=np.float32)
        for index, freq in enumerate((1760, 2340, 3120, 4180)):
            tone += np.sin(2 * np.pi * freq * t + index * 1.3) * (0.24 / (index + 1))
        return _soft_clip(tone * np.exp(-t * 4.2) * 0.55)
    if kind == "type":
        length = int(0.26 * SAMPLE_RATE)
        out = np.zeros(length, dtype=np.float32)
        for index, at in enumerate((0.0, 0.075, 0.15)):
            start = int(at * SAMPLE_RATE)
            part = _sfx("tick_soft", seed + 10 + index)[: length - start]
            out[start:start + len(part)] += part * (0.8 - index * 0.15)
        return out
    if kind == "page":
        length = int(0.32 * SAMPLE_RATE)
        t = np.arange(length, dtype=np.float32) / SAMPLE_RATE
        noise = _onepole(_noise(length, seed + 8), np.linspace(2400, 600, 9))
        crackle = _noise(length, seed + 9) * (np.random.default_rng(seed).random(length) > 0.985)
        return _soft_clip((noise * 0.55 + crackle * 0.3) * np.exp(-t * 12) * 0.5)
    # Unknown kind: a short neutral tick rather than silence.
    return _sfx("tick_soft", seed)


NEW_KINDS = ("tick", "tick_soft", "pop", "swipe", "whoosh", "impact", "sub", "riser",
             "riser_short", "chime", "shimmer", "type", "page")
SFX = {kind: _sfx(kind, seed=11 + index * 7) for index, kind in enumerate(NEW_KINDS)}


# --------------------------------------------------------------------- music


MUSIC_PRESETS = {
    "tech": {"bpm": 96, "root": 55.0, "chords": [(0, 3, 7), (-4, 0, 3), (3, 7, 10), (-2, 2, 5)],
             "pad": 0.030, "bass": 0.034, "arp": 0.018, "perc": 0.012},
    "minimal": {"bpm": 72, "root": 65.41, "chords": [(0, 4, 7), (-3, 0, 4), (5, 9, 12), (-5, -1, 2)],
                "pad": 0.036, "bass": 0.024, "arp": 0.015, "perc": 0.0},
    "documentary": {"bpm": 64, "root": 49.0, "chords": [(0, 3, 7), (-4, 0, 3), (-2, 2, 5), (0, 3, 7)],
                    "pad": 0.032, "bass": 0.030, "arp": 0.010, "perc": 0.006},
}


def _section_level(sections: list[dict] | None, at: float) -> tuple[float, str]:
    if not sections:
        return 0.55, "mechanism"
    for section in sections:
        if section["start"] <= at < section["end"]:
            return float(section.get("energy", 0.55)), str(section.get("role", "mechanism"))
    return 0.55, "mechanism"


def _music_bed_v3(size: int, style: str, sections: list[dict] | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    preset = MUSIC_PRESETS.get(style, MUSIC_PRESETS["tech"])
    bpm = preset["bpm"]
    beat = 60.0 / bpm
    bar = beat * 4
    root = preset["root"]
    chords = preset["chords"]
    total = size / SAMPLE_RATE
    music = np.zeros(size, dtype=np.float32)
    arp_left = np.zeros(size, dtype=np.float32)
    arp_right = np.zeros(size, dtype=np.float32)

    def place(buffer: np.ndarray, at: float, wave_data: np.ndarray, gain: float):
        begin = int(at * SAMPLE_RATE)
        if begin >= size or gain <= 0:
            return
        end = min(size, begin + len(wave_data))
        if end > begin:
            buffer[begin:end] += wave_data[:end - begin] * gain

    bar_count = int(math.ceil(total / bar)) + 1
    for bar_index in range(bar_count):
        at = bar_index * bar
        if at >= total:
            break
        level, role = _section_level(sections, at)
        # A turn drops the pulse for one bar; the next bar comes back louder.
        in_turn = role == "turn"
        chord_bank = chords
        if in_turn:
            chord_bank = [(-2, 1, 5), (-3, 0, 4), (-4, 0, 3), (-2, 2, 5)]
        chord = chord_bank[bar_index % len(chord_bank)]
        pad_length = int((bar + 0.5) * SAMPLE_RATE)
        env = _adsr(pad_length, 0.8, 0.9, 1.3)
        local = np.arange(pad_length, dtype=np.float32) / SAMPLE_RATE
        pad = np.zeros(pad_length, dtype=np.float32)
        for offset in chord:
            freq = _semitones(root, offset) * 2
            pad += np.sin(2 * np.pi * freq * local) * 0.52
            pad += np.sin(2 * np.pi * freq * 2.002 * local) * 0.15
            pad += np.sin(2 * np.pi * freq * 0.998 * local) * 0.28
        pad /= max(1, len(chord))
        place(music, at, pad * env, preset["pad"] * (0.55 + 0.65 * level))
        if level > 0.28:
            bass_env = _adsr(pad_length, 0.04, 0.5, 1.6)
            bass = np.sin(2 * np.pi * root * local) + 0.25 * np.sin(2 * np.pi * root * 2 * local)
            place(music, at, bass * bass_env, preset["bass"] * (0.5 + 0.6 * level))
        if preset["arp"] > 0 and level > 0.42 and not in_turn:
            steps = 8 if level > 0.6 else 4
            for step in range(steps):
                note_at = at + step * (bar / steps)
                if note_at >= total:
                    break
                tone = _semitones(root, chord[step % len(chord)] + 12)
                length = int(0.9 * SAMPLE_RATE)
                lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                pluck = np.sin(2 * np.pi * tone * lt) + 0.28 * np.sin(2 * np.pi * tone * 2 * lt)
                pluck *= np.exp(-lt * 5.2)
                gain = preset["arp"] * (0.55 + 0.55 * level) * (0.82 if step % 2 else 1.0)
                place(arp_right if step % 2 else arp_left, note_at, pluck, gain)
        if preset["perc"] > 0 and level > 0.58 and not in_turn:
            for beat_index in range(4):
                beat_at = at + beat_index * beat
                if beat_at >= total:
                    break
                if beat_index in (0, 2):
                    length = int(0.30 * SAMPLE_RATE)
                    lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                    kick = np.sin(2 * np.pi * (58 - 22 * lt / 0.30) * lt) * np.exp(-lt * 18)
                    place(music, beat_at, kick, preset["perc"] * 1.35)
                else:
                    length = int(0.06 * SAMPLE_RATE)
                    lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
                    hat = _noise(length, 17 + beat_index) * np.exp(-lt * 60)
                    hat = _onepole(hat, 6200) - _onepole(hat, 2400)
                    place(music, beat_at, hat, preset["perc"] * 0.32)
        if level > 0.78 and not in_turn:
            # A quiet high shimmer marks the most important section without adding
            # another melodic line.
            length = int(0.5 * SAMPLE_RATE)
            lt = np.arange(length, dtype=np.float32) / SAMPLE_RATE
            shimmer = np.sin(2 * np.pi * _semitones(root, 24) * lt) * np.exp(-lt * 7)
            place(music, at + beat * 2, shimmer, 0.004)
    return music, arp_left, arp_right


def _room_tone(size: int) -> np.ndarray:
    noise = _noise(size, 41)
    low = _onepole(noise, 260)
    body = _onepole(noise, 900) - low
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    modulation = 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t)
    return (body * modulation * 0.0018).astype(np.float32)


def _process_voice(voice: np.ndarray) -> np.ndarray:
    size = len(voice)
    if size == 0:
        return voice
    low = _onepole(voice, 92)
    high = voice - low
    presence = high - _onepole(high, 3000)
    shaped = high + presence * 0.24
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
        shaped = shaped * np.interp(np.arange(size), np.arange(frames) * window, smoothed).astype(np.float32)
    return _soft_clip(shaped, 1.04) * 0.92


# ------------------------------------------------------------ automatic Foley


ACTION_SFX = {
    "draw": ("swipe", 0.42, 0.20),
    "appear": ("pop", 0.30, 0.10),
    "fade": ("tick_soft", 0.20, 0.05),
    "scale": ("pop", 0.30, 0.08),
    "highlight": ("chime", 0.20, 0.28),
    "move": ("swipe", 0.22, 0.06),
    "rotate": ("whoosh", 0.22, 0.10),
    "morph": ("shimmer", 0.20, 0.24),
}


def design_sound_events(scenes: list[dict], *, fps: int, scene_starts: list[float], lead: float,
                        duration: float, max_per_minute: float = 20.0,
                        extra: list[dict] | None = None) -> list[dict]:
    """Derive Foley from the actual animation timeline, not from prose.

    Priorities keep a scene transition and a conclusion above a decorative tick;
    events closer than 0.30 s collapse into the higher-priority one so the track
    never turns into a machine-gun of ticks.
    """
    events: list[dict] = [dict(event) for event in (extra or [])]

    def add(at: float, kind: str, gain: float, *, pan: float = 0.0, send: float = 0.2,
            priority: int = 1, source: str = "auto") -> None:
        if not math.isfinite(at) or at < -0.2 or at > duration + 0.2:
            return
        events.append({"at": max(0.0, min(duration, at)), "kind": kind,
                       "gain": max(0.0, min(1.0, gain)), "pan": max(-0.6, min(0.6, pan)),
                       "send": max(0.0, min(1.0, send)), "priority": priority, "source": source})

    for index, scene in enumerate(scenes):
        start = scene_starts[index] + lead
        seconds = max(0.5, float(scene.get("frames", 0)) / fps)
        transition = str(scene.get("transition", "fade"))
        role = str(scene.get("role", "mechanism"))
        camera = str(scene.get("camera", "push"))
        layer_region = {layer.get("id"): layer.get("region", "main") for layer in scene.get("layers", [])}

        # Transition: start before the visual seam so the sound leads the picture.
        if index > 0:
            kind, gain = {
                "cut": ("impact", 0.26), "fade": ("whoosh", 0.28), "slide": ("swipe", 0.28),
                "wipe": ("swipe", 0.26), "dip": ("sub", 0.22), "zoom": ("whoosh", 0.28),
            }.get(transition, ("whoosh", 0.30))
            pan = -0.25 if camera == "pan_left" else 0.25 if camera == "pan_right" else 0.0
            add(start - 0.24, kind, gain, pan=pan, send=0.22, priority=6, source="transition")
        if index == 0 or role in {"hook", "conclusion"}:
            add(start + 0.02, "impact" if role != "conclusion" else "sub", 0.24,
                send=0.28, priority=7, source="beat")
        if transition == "cut" and index > 0:
            add(start + 0.02, "sub", 0.18, send=0.22, priority=6, source="transition")

        # Animation events: the sound and the movement share the same anchor.
        actions = sorted(scene.get("actions_resolved") or [], key=lambda item: item.get("from", 0))
        for action in actions:
            kind, gain, send = ACTION_SFX.get(str(action.get("kind")), ("tick_soft", 0.18, 0.06))
            region = layer_region.get(action.get("target"), "main")
            pan = -0.32 if region in {"side", "bottom", "annotation"} else 0.0
            at = start + float(action.get("from", 0)) * seconds
            add(at, kind, gain, pan=pan, send=send, priority=4 if kind in {"impact", "sub"} else 2)
            if kind == "swipe":
                add(at + float(action.get("to", 1) - action.get("from", 0)) * seconds,
                    "tick", 0.20, pan=pan, send=0.08, priority=3, source="action-end")
        # A chart's current marker lands with a tick; a diagram/timeline step with a soft tick.
        for layer in scene.get("layers", []):
            if layer.get("type") == "chart" and any(s.get("label", "").find("当前") >= 0 for s in layer.get("series", [])):
                add(start + seconds * 0.55, "tick", 0.18, send=0.10, priority=2, source="marker")

        # Sentence starts: a very quiet page/type sound only when the track is sparse.
        pages = sorted(scene.get("captions") or [], key=lambda page: page.get("start", 0))
        last_page_end = -99.0
        sentence_index = 0
        for page in pages:
            if float(page.get("start", 0)) - last_page_end > 0.35:
                last_page_end = float(page.get("end", 0))
                at = start + float(page.get("start", 0))
                # A page turn on every sentence is a metronome, not sound design.
                # One quiet page/type event every third sentence keeps the track
                # alive while leaving room for the animation Foley.
                if sentence_index % 3 == 0 and not any(abs(event["at"] - at) < 1.15 for event in events):
                    add(at, "type" if index % 2 else "page", 0.10, send=0.10, priority=1, source="sentence")
                sentence_index += 1
            # Emphasis words get a small chime, at the word boundary.
            for word in page.get("words") or []:
                text = str(word.get("text", ""))
                if any(key and key in text for key in (scene.get("emphasis") or [])):
                    at = start + float(word.get("start", 0))
                    if not any(abs(event["at"] - at) < 0.55 for event in events):
                        add(at, "chime", 0.13, pan=0.18, send=0.30, priority=2, source="emphasis")

        # Conclusion lands on the last sentence with a chime + sub.
        if role == "conclusion":
            add(start + max(0.4, seconds - 1.1), "chime", 0.18, send=0.35, priority=3, source="conclusion")
            add(start + max(0.4, seconds - 1.1), "sub", 0.16, send=0.22, priority=5, source="conclusion")

    # Director-authored cues are already in the list (priority 9) and win dedupe.
    events.sort(key=lambda event: event["at"])
    kept: list[dict] = []
    for event in events:
        if kept and event["at"] - kept[-1]["at"] < 0.30:
            if event["priority"] > kept[-1]["priority"]:
                kept[-1] = event
            continue
        kept.append(event)
    cap = max(12, int(duration / 60.0 * max_per_minute))
    if len(kept) > cap:
        # Keep the highest-priority events, then restore chronological order.
        ranked = sorted(kept, key=lambda event: (-event["priority"], event["at"]))[:cap]
        kept = sorted(ranked, key=lambda event: event["at"])
    return kept


def soundtrack_stems(voice_track: np.ndarray, scene_starts: list[float], style: str = "tech",
                     *, cues: list[dict] | None = None, scene_seconds: list[float] | None = None,
                     sections: list[dict] | None = None) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """The mix plus every stem it was built from, so the mix can be audited later.

    Stems keep the dry voice and the processed voice separately: a missing voice must
    be provable from the voice stem, not inferred from a mix where music could hide it.
    """
    mix, stems = _soundtrack_impl(voice_track, scene_starts, style, cues=cues,
                                  scene_seconds=scene_seconds, sections=sections)
    return mix, stems


def soundtrack(voice_track: np.ndarray, scene_starts: list[float], style: str = "tech",
                  *, cues: list[dict] | None = None, scene_seconds: list[float] | None = None,
                  sections: list[dict] | None = None) -> np.ndarray:
    return _soundtrack_impl(voice_track, scene_starts, style, cues=cues,
                            scene_seconds=scene_seconds, sections=sections)[0]


def _soundtrack_impl(voice_track: np.ndarray, scene_starts: list[float], style: str = "tech",
                     *, cues: list[dict] | None = None, scene_seconds: list[float] | None = None,
                     sections: list[dict] | None = None) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    size = len(voice_track)
    music, arp_left, arp_right = _music_bed_v3(size, style, sections)
    # Bed level relative to the voice.  V3's adaptive arrangement is denser than
    # V2's loop, so the bus is trimmed rather than the presets re-tuned one by one.
    bed = music * 0.72
    arp = (arp_left * 0.9, arp_right * 0.9)
    duck = _sidechain(voice_track)
    sfx_left = np.zeros(size, dtype=np.float32)
    sfx_right = np.zeros(size, dtype=np.float32)
    send = np.zeros(size, dtype=np.float32)
    for cue in cues or []:
        sound = SFX.get(str(cue.get("kind", "")))
        if sound is None:
            continue
        begin = int(float(cue.get("at", 0)) * SAMPLE_RATE)
        if begin < 0 or begin >= size:
            continue
        end = min(size, begin + len(sound))
        gain = float(cue.get("gain", 0.55))
        left, right = _pan(sound[:end - begin], float(cue.get("pan", 0.0)))
        # Foley sits under the voice: the first V3 render reached a mix/voice
        # ratio of 9.2 because the bus trim had been dropped.  A fixed trim plus a
        # deeper duck keeps a sub/impact as punctuation, not as a second voice.
        window = 0.30 + 0.35 * duck[begin:end]
        sfx_left[begin:end] += left * gain * 0.17 * window
        sfx_right[begin:end] += right * gain * 0.17 * window
        send[begin:end] += sound[:end - begin] * gain * float(cue.get("send", 0.2))
    wet_left = _reverb(send, 0.9)
    wet_right = _reverb(np.roll(send, 72), 0.9)
    voice = _process_voice(voice_track)
    total = size / SAMPLE_RATE
    t = np.arange(size, dtype=np.float32) / SAMPLE_RATE
    fade = np.minimum(np.clip(t / 1.4, 0, 1), np.clip((total - t) / 1.8, 0, 1))
    bed = bed * duck * fade
    room = _room_tone(size) * fade
    # A shared reverb bus: the dry Foley stays tight, the wet signal sits behind it.
    # A 6.7 ms delay on the bed gives it width without moving the voice; arpeggios
    # and Foley go to their own side.  A phone speaker still gets the mono sum.
    delay = int(0.0067 * SAMPLE_RATE)
    delayed = np.concatenate([np.zeros(delay, dtype=np.float32), bed[:-delay]]) if delay < size else bed
    side = (bed - delayed) * 0.22
    left = voice * 0.94 + bed - side + arp[0] * 0.72 + sfx_left + wet_left * 0.34 + room
    right = voice * 0.94 + bed + side + arp[1] * 0.72 + sfx_right + wet_right * 0.34 + room
    stereo = np.stack([left, right], axis=1).astype(np.float32)
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak > 0.95:
        stereo *= 0.95 / peak
    stems = {
        "voice_dry": np.asarray(voice_track, dtype=np.float32),
        "voice": voice.astype(np.float32),
        "music": bed.astype(np.float32),
        "arp": (arp[0] + arp[1]).astype(np.float32) * 0.5,
        "sfx": (sfx_left + sfx_right).astype(np.float32) * 0.5,
        "room": room.astype(np.float32),
        "duck": duck.astype(np.float32),
    }
    return stereo, stems
