"""Speech backend adapter, pronunciation units and the independent content check.

Three things are kept apart on purpose:

* **the backend** — what produced the audio, with its real sample count, voice, model,
  parameters and where its boundaries came from;
* **the reading** — the written text versus what is actually spoken (numbers,
  abbreviations, formulas), with a mapping back to the written characters;
* **the check** — an independent transcription that looks for lost numbers, lost
  negations, repeated phrases and missing proper nouns.

A backend failure is never turned into a silent, empty success: it raises, and a
fallback (if one is configured) records that the voice changed so every downstream
cache is recomputed.
"""
from __future__ import annotations

import re

from pydantic import Field

from .models import Contract

# Boundary provenance, weakest last.  Only ``native`` boundaries may be treated as
# exact; the others carry their uncertainty into the caption timing.
BOUNDARY_SOURCES = ("native", "forced-alignment", "estimated")

# Chinese readings that are legitimately equivalent.  A normalisation may only fold
# *form*, never magnitude or sign: "0.5" and "零点五" are equal, "0.5" and "5" are not.
EQUIVALENT_READINGS = {
    "零点五": "0.5", "零点零五": "0.05", "一点五": "1.5", "两": "2", "两倍": "2倍",
    "负": "-", "百分之": "%", "半": "0.5",
}


class SpeechResult(Contract):
    """What a synthesis call actually produced."""

    backend: str = Field(min_length=1, max_length=32)
    voice: str = Field(min_length=1, max_length=64)
    model: str = Field(default="", max_length=64)
    sample_rate: int = Field(gt=0, le=192_000)
    samples: int = Field(ge=0)
    seconds: float = Field(ge=0)
    granularity: str = Field(default="sentence", max_length=16)
    rate: str = Field(default="+0%", max_length=12)
    pitch: str = Field(default="+0Hz", max_length=12)
    volume: str = Field(default="+0%", max_length=12)
    boundary_source: str = Field(default="native", max_length=24)
    boundaries: int = Field(default=0, ge=0)
    characters: int = Field(default=0, ge=0)
    cache_key: str = Field(default="", max_length=80)
    fallback_from: str = Field(default="", max_length=32)
    usage: dict = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        if self.boundary_source not in BOUNDARY_SOURCES:
            raise ValueError(f"boundary_source 只能是 {'/'.join(BOUNDARY_SOURCES)}")
        if self.granularity not in {"sentence", "clause", "paragraph"}:
            raise ValueError("granularity 只能是 sentence/clause/paragraph")


class SpeechSettings(Contract):
    """Speech configuration, separate from the text-agent roles."""

    backend: str = Field(default="edge", max_length=24)
    voice: str = Field(default="zh-CN-YunxiNeural", max_length=64)
    model: str = Field(default="", max_length=64)
    rate: str = Field(default="+0%", max_length=12)
    pitch: str = Field(default="+0Hz", max_length=12)
    volume: str = Field(default="+0%", max_length=12)
    granularity: str = Field(default="sentence", max_length=16)
    boundary_policy: str = Field(default="native", max_length=24)
    fallback_voice: str = Field(default="", max_length=64)
    # Controls the backend cannot honour must be refused, not silently ignored.
    supported_controls: list[str] = Field(default_factory=lambda: ["rate", "pitch", "volume"])

    def __init__(self, **data):
        super().__init__(**data)
        if self.granularity not in {"sentence", "clause", "paragraph"}:
            raise ValueError("speech.granularity 只能是 sentence/clause/paragraph")
        if self.boundary_policy not in {"native", "estimated", "strict"}:
            raise ValueError("speech.boundary_policy 只能是 native/estimated/strict")


def speech_settings(config: dict) -> SpeechSettings:
    """Read ``[speech]`` when present, otherwise inherit the legacy studio voice.

    A pre-v2 ``movelyth.toml`` has no ``[speech]`` section at all; it must keep working
    with exactly the same voice and rate as before.
    """
    studio = config.get("studio") or {}
    section = config.get("speech") or {}
    merged = {
        "backend": section.get("backend", "edge"),
        "voice": section.get("voice", studio.get("voice", "zh-CN-YunxiNeural")),
        "model": section.get("model", ""),
        "rate": section.get("rate", studio.get("voice_rate", "+0%")),
        "pitch": section.get("pitch", studio.get("voice_pitch", "+0Hz")),
        "volume": section.get("volume", studio.get("voice_volume", "+0%")),
        "granularity": section.get("granularity", "sentence"),
        "boundary_policy": section.get("boundary_policy", "native"),
        "fallback_voice": section.get("fallback_voice", ""),
        "supported_controls": section.get("supported_controls") or ["rate", "pitch", "volume"],
    }
    settings = SpeechSettings(**merged)
    for control in ("rate", "pitch", "volume"):
        if control not in settings.supported_controls and merged[control] not in {"+0%", "+0Hz"}:
            raise ValueError(f"当前语音后端 {settings.backend} 不支持 {control}；"
                             f"请移除 speech.{control} 或改用支持它的后端（不会静默忽略）")
    return settings


def cache_key(*, text: str, settings: SpeechSettings, reading: str | None = None,
              granularity: str | None = None, version: int = 0) -> str:
    """Cache identity includes the reading, backend, voice and synthesis granularity."""
    from .util import fingerprint

    return fingerprint({
        "text": text, "reading": reading if reading is not None else text,
        "backend": settings.backend, "voice": settings.voice, "model": settings.model,
        "rate": settings.rate, "pitch": settings.pitch, "volume": settings.volume,
        "granularity": granularity or settings.granularity, "version": version,
    })


def describe(backend: str, audio, boundaries: list[dict], *, settings: SpeechSettings,
             text: str, reading: str, sample_rate: int, cache: str = "",
             fallback_from: str = "", boundary_source: str = "native") -> SpeechResult:
    """Build the record of one synthesis, from the real audio, not from the request."""
    samples = int(getattr(audio, "shape", [0])[0]) if getattr(audio, "shape", None) else 0
    return SpeechResult(
        backend=backend, voice=settings.voice, model=settings.model, sample_rate=sample_rate,
        samples=samples, seconds=round(samples / sample_rate, 3) if sample_rate else 0.0,
        granularity=settings.granularity, rate=settings.rate, pitch=settings.pitch,
        volume=settings.volume, boundary_source=boundary_source,
        boundaries=len(boundaries or []), characters=len(reading or text),
        cache_key=cache, fallback_from=fallback_from,
        usage={"characters": len(reading or text), "seconds": round(samples / sample_rate, 3)
               if sample_rate else 0.0})


# --------------------------------------------------------------- pronunciation

NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
UNIT_PATTERN = re.compile(r"(毫秒|秒|分钟|小时|天|年|倍|%|％|个|次|米|千米|公里|克|千克|公斤|"
                          r"度|摄氏度|像素|帧|GB|MB|KB|Hz|kHz|ms|s|min|h)")
NEGATIONS = ("不", "没", "无", "非", "未", "别", "勿", "莫")
FORMULA_HINTS = re.compile(r"[A-Za-zα-ωΑ-Ω]\s*[=≈<>≤≥+\-×÷*/^]|[=≈<>≤≥]")
LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9.+#-]{1,}")


class ReadingUnit(Contract):
    """One thing in the narration whose misreading changes the meaning."""

    kind: str = Field(pattern=r"^(number|unit|negation|term|formula)$")
    written: str = Field(min_length=1, max_length=60)
    spoken: str = Field(default="", max_length=60)
    importance: str = Field(default="key", pattern=r"^(key|supporting)$")


def reading_units(narration: str, *, terms: list[str] | None = None) -> list[ReadingUnit]:
    """Extract numbers (with sign and unit), negations, terms and formulas."""
    units: list[ReadingUnit] = []
    for match in NUMBER_PATTERN.finditer(narration):
        written = match.group(0)
        tail = narration[match.end():match.end() + 4].lstrip()
        unit_match = UNIT_PATTERN.match(tail)
        spoken = written
        if unit_match:
            spoken = written + unit_match.group(1)
        units.append(ReadingUnit(kind="number", written=spoken))
        if unit_match:
            units.append(ReadingUnit(kind="unit", written=unit_match.group(1)))
    for word in NEGATIONS:
        if word in narration:
            units.append(ReadingUnit(kind="negation", written=word))
    for term in terms or []:
        variants = [part.strip() for part in str(term).split("|") if part.strip()]
        if any(variant in narration for variant in variants):
            units.append(ReadingUnit(kind="term", written="|".join(variants)))
    for token in sorted(set(LATIN_TOKEN.findall(narration))):
        if len(token) >= 2:
            units.append(ReadingUnit(kind="term", written=token, importance="supporting"))
    if FORMULA_HINTS.search(narration):
        formula = FORMULA_HINTS.search(narration).group(0)
        units.append(ReadingUnit(kind="formula", written=formula.strip()))
    return units


CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_NUMERAL = re.compile(r"[一二两三四五六七八九]?十[一二三四五六七八九]?|[零〇一二两三四五六七八九]")


def _fold_cn_numeral(match: re.Match) -> str:
    text = match.group(0)
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CN_DIGITS.get(left, 1) if left else 1
        units = CN_DIGITS.get(right, 0) if right else 0
        return str(tens * 10 + units)
    return str(CN_DIGITS.get(text, text))


def canonical_reading(text: str) -> str:
    """Fold only form: equivalent readings of the same value become one string.

    Chinese numerals and spoken decimals fold to digits ("十二" → "12", "零点五" → "0.5")
    so a correct reading is not reported as a lost number.  Signs and magnitudes are
    never folded: that is the whole point of the check.
    """
    result = text
    for spoken, written in sorted(EQUIVALENT_READINGS.items(), key=lambda item: -len(item[0])):
        result = result.replace(spoken, written)
    return CN_NUMERAL.sub(_fold_cn_numeral, result)


def magnitude_sign(text: str) -> tuple[int, int]:
    """(sign, magnitude) of the first number in ``text``; (0, 0) when there is none."""
    match = NUMBER_PATTERN.search(canonical_reading(text))
    if not match:
        return 0, 0
    try:
        value = float(match.group(0))
    except ValueError:
        return 0, 0
    return (-1 if value < 0 else 1), len(match.group(0).replace("-", "").replace(".", ""))


def verify_reading(units: list[ReadingUnit], heard: str) -> dict:
    """Check the transcribed speech for lost numbers, units, negations and terms.

    Equivalence is allowed for *form* only.  When the transcription contains the same
    number of numbers as the script, they are compared position by position: a flipped
    sign or a changed magnitude is then reported as *changed*, not as a mishearing.
    Normalisation never folds a sign or a magnitude away.
    """
    normalized = canonical_reading(heard)
    heard_numbers = [match.group(0) for match in NUMBER_PATTERN.finditer(normalized)]
    written_numbers = [unit.written for unit in units if unit.kind == "number"]
    paired = len(heard_numbers) == len(written_numbers) and written_numbers
    missing, changed = [], []
    number_index = -1
    for unit in units:
        variants = [canonical_reading(part) for part in unit.written.split("|")]
        if any(variant in normalized for variant in variants if variant):
            if unit.kind == "number":
                number_index += 1
            continue
        if unit.kind == "number":
            number_index += 1
            if paired and 0 <= number_index < len(heard_numbers):
                sign, digits = magnitude_sign(unit.written)
                heard_sign, heard_digits = magnitude_sign(heard_numbers[number_index])
                if sign and heard_sign and sign != heard_sign:
                    changed.append({"written": unit.written, "heard": heard_numbers[number_index],
                                    "reason": "正负号被改变"})
                    continue
                if digits and heard_digits and digits != heard_digits:
                    changed.append({"written": unit.written, "heard": heard_numbers[number_index],
                                    "reason": "数字位数/量级被改变"})
                    continue
            missing.append({"written": unit.written, "kind": unit.kind})
        else:
            missing.append({"written": unit.written, "kind": unit.kind})
    return {"status": "ok" if not missing and not changed else "review",
            "missing": missing[:10], "changed": changed[:10],
            "limitations": ["独立识别有误听；未命中只表示需要复听，不等于配音读错",
                            "等价读法（0.5 / 零点五）会被折叠，正负号与量级不会被折叠"]}
