"""Mix audit: stems, event onsets, tails, ducking and voice presence.

A mix is not "done" because it renders.  This module checks the things a listener would
notice and a waveform cannot prove:

* is there a voice, measured on the voice stem (not on the mix, where music hides it);
* does each planned sound event actually land at its time (onset measured in the mix);
* does a sound end abruptly (tail cut) or clip (pop);
* does the ducking pump audibly (gain reduction oscillating faster than speech);
* do the stems explain the mix level (a stem far louder than the voice is a warning).

Loudness and peak are measured on the encoded file elsewhere; these checks run on the
stems before encoding, so a defect is found before the expensive step.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .media import SAMPLE_RATE, write_wav
from .models import Contract
from .util import atomic_json

VOICE_FLOOR_DB = -45.0
ONSET_TOLERANCE = 0.12
TAIL_DB_DROP = -30.0


def _db(value: float) -> float:
    return 20.0 * float(np.log10(max(value, 1e-9)))


def stem_stats(signal: np.ndarray) -> dict:
    if signal.size == 0:
        return {"peak_db": None, "rms_db": None, "seconds": 0.0, "clipped": 0}
    mono = signal if signal.ndim == 1 else signal.mean(axis=1)
    return {"peak_db": round(_db(float(np.max(np.abs(mono)))), 2),
            "rms_db": round(_db(float(np.sqrt(np.mean(mono ** 2)))), 2),
            "seconds": round(len(mono) / SAMPLE_RATE, 3),
            "clipped": int(np.sum(np.abs(mono) > 0.999))}


def voice_presence(voice_stem: np.ndarray) -> dict:
    """Is there speech on the voice stem?  Measured there, never on the mix."""
    stats = stem_stats(voice_stem)
    if not voice_stem.size:
        return {"present": False, "reason": "人声轨为空", **stats}
    mono = voice_stem if voice_stem.ndim == 1 else voice_stem.mean(axis=1)
    frame = SAMPLE_RATE // 10
    frames = len(mono) // frame
    if frames < 1:
        return {"present": False, "reason": "人声轨过短", **stats}
    energy = np.sqrt(np.mean(mono[:frames * frame].reshape(frames, frame) ** 2, axis=1))
    audible = float(np.mean(energy > 10 ** (VOICE_FLOOR_DB / 20)))
    return {"present": audible > 0.05, "audible_share": round(audible, 3), **stats,
            "floor_db": VOICE_FLOOR_DB}


def onset_report(mix: np.ndarray, events: list[dict], *, tolerance: float = ONSET_TOLERANCE) -> dict:
    """Does each planned event actually produce energy at its time?

    The check is deliberately loose: it proves the sound is *there*, not that it is the
    right sound.  A missing onset means the cue was dropped or placed outside the mix.
    """
    if not mix.size:
        return {"checked": 0, "missing": [], "note": "混音为空"}
    mono = mix if mix.ndim == 1 else mix.mean(axis=1)
    frame = SAMPLE_RATE // 100
    frames = len(mono) // frame
    energy = np.sqrt(np.mean(mono[:frames * frame].reshape(frames, frame) ** 2, axis=1))
    missing, found = [], 0
    for event in events:
        at = float(event.get("at", 0))
        begin = max(0, int((at - tolerance) * 100))
        end = min(frames, int((at + tolerance) * 100) + 1)
        if begin >= end:
            missing.append({"at": at, "kind": event.get("kind"), "reason": "事件时间在混音之外"})
            continue
        window = energy[begin:end]
        baseline = float(np.median(energy[max(0, begin - 30):begin])) if begin else float(np.median(energy))
        peak = float(np.max(window)) if window.size else 0.0
        if peak > max(baseline * 1.35, 10 ** (-40 / 20)):
            found += 1
        else:
            missing.append({"at": at, "kind": event.get("kind"),
                            "reason": f"事件处能量 {peak:.4f} 未高于基线 {baseline:.4f}"})
    return {"checked": len(events), "found": found, "missing": missing[:10],
            "tolerance_seconds": tolerance,
            "note": "只证明该时刻有能量变化，不证明音色与语义正确"}


def tail_report(stem: np.ndarray, *, floor_ratio: float = 0.01) -> dict:
    """A stem that ends at full level was cut, not faded."""
    if not stem.size:
        return {"ok": True, "reason": "空轨"}
    mono = stem if stem.ndim == 1 else stem.mean(axis=1)
    window = max(1, int(0.02 * SAMPLE_RATE))
    tail = float(np.max(np.abs(mono[-window:])))
    overall = float(np.max(np.abs(mono)))
    if overall < 1e-6:
        return {"ok": True, "tail_ratio": 0.0}
    ratio = tail / overall
    return {"ok": ratio <= max(floor_ratio, 0.2), "tail_ratio": round(ratio, 4),
            "note": "结尾仍接近峰值说明尾音被截断" if ratio > max(floor_ratio, 0.2) else ""}


def ducking_report(duck: np.ndarray) -> dict:
    """Ducking that oscillates much faster than speech sounds like pumping."""
    if not duck.size:
        return {"ok": True, "reason": "没有侧链增益"}
    frame = SAMPLE_RATE // 50
    frames = len(duck) // frame
    if frames < 4:
        return {"ok": True, "reason": "侧链增益过短"}
    smoothed = duck[:frames * frame].reshape(frames, frame).mean(axis=1)
    crossings = int(np.sum(np.diff(np.sign(smoothed - np.mean(smoothed))) != 0))
    rate = crossings / (frames / 50)
    return {"ok": rate <= 6.0, "crossings_per_second": round(rate, 2),
            "min_gain": round(float(np.min(smoothed)), 3),
            "max_gain": round(float(np.max(smoothed)), 3),
            "note": "每秒超过 6 次增益翻转通常听起来像抽吸" if rate > 6.0 else ""}


def stem_balance(stems: dict[str, np.ndarray], *, tolerance_db: float = 6.0) -> dict:
    """Warn when a decorative stem is louder than the voice."""
    voice = stems.get("voice")
    if voice is None or not voice.size:
        return {"ok": False, "reason": "没有人声轨，无法比较"}
    voice_rms = _db(float(np.sqrt(np.mean((voice if voice.ndim == 1 else voice.mean(axis=1)) ** 2))))
    levels, problems = {}, []
    for name, stem in stems.items():
        if name in {"voice", "voice_dry", "duck"} or stem is None or not stem.size:
            continue
        mono = stem if stem.ndim == 1 else stem.mean(axis=1)
        level = _db(float(np.sqrt(np.mean(mono ** 2))))
        levels[name] = round(level, 2)
        if level > voice_rms + tolerance_db:
            problems.append(f"{name} 比人声高 {level - voice_rms:.1f} dB")
    return {"ok": not problems, "voice_rms_db": round(voice_rms, 2), "levels": levels,
            "problems": problems}


def mix_report(stems: dict[str, np.ndarray], events: list[dict] | None = None,
               mix: np.ndarray | None = None) -> dict:
    voice = stems.get("voice")
    # Onsets are measured on the Foley stem: an event that did not land leaves no
    # energy there, while measuring on the mix would hide it under music.
    events_signal = stems.get("sfx")
    if events_signal is None or not np.any(events_signal):
        events_signal = mix
    checks = {
        "voice": voice_presence(voice) if voice is not None else {"present": False,
                                                                  "reason": "缺少人声轨"},
        "stems": {name: stem_stats(signal) for name, signal in stems.items()},
        "balance": stem_balance(stems),
        "tails": {name: tail_report(signal) for name, signal in stems.items()
                  if name in {"voice", "music", "sfx"}},
        "ducking": ducking_report(stems.get("duck")) if stems.get("duck") is not None else None,
        "onsets": (onset_report(np.asarray(events_signal, dtype=np.float32), events or [])
                   if events_signal is not None else
                   {"checked": 0, "missing": [], "note": "没有音效轨或混音，未检查事件"}),
        "note": "这些都是机器检查：不能证明自然度、音色或语义正确",
    }
    problems = []
    if not checks["voice"].get("present"):
        problems.append("人声缺失或几乎全静音")
    if not checks["balance"].get("ok", True):
        problems.extend(checks["balance"].get("problems") or [])
    if checks["ducking"] and not checks["ducking"].get("ok", True):
        problems.append("侧链压摆在抽吸")
    checks["problems"] = problems
    checks["passed"] = not problems
    return checks


def write_stems(stems: dict[str, np.ndarray], directory: Path) -> dict[str, str]:
    """Persist each stem as a WAV so the mix can be re-listened to stem by stem."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, signal in stems.items():
        if signal is None or not signal.size:
            continue
        path = directory / f"{name}.wav"
        write_wav(path, np.asarray(signal, dtype=np.float32))
        paths[name] = str(path)
    atomic_json(directory / "stems.json", {"stems": paths,
                                           "sample_rate": SAMPLE_RATE,
                                           "note": "voice_dry 是未处理的旁白；voice 是处理后的旁白"})
    return paths


class StemRecord(Contract):
    """Where a stem came from, so a mix can be reproduced."""

    name: str
    path: str = ""
    sample_rate: int = SAMPLE_RATE
    start_seconds: float = 0.0
    gain_db: float = 0.0
    processing: str = ""
