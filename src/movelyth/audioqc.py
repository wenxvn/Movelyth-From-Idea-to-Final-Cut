"""Local-first audio quality checks: optional ASR, silence and ducking.

Nothing here claims that a video "sounds right".  Each report states what was
actually measured, what engine ran, and which limitations remain.
"""
from __future__ import annotations

import difflib
import importlib.util
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from .media import SAMPLE_RATE, ffmpeg

PUNCTUATION = re.compile(r"[\s，。！？；：、,.!?;:\"'“”‘’（）()《》〈〉【】\[\]—\-…·]")


def _read_mono(path: Path) -> np.ndarray:
    """Read PCM WAV of any channel count down to mono float32."""
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        width = stream.getsampwidth()
        if width != 2:
            raise ValueError("仅支持 16-bit PCM 音频")
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)
        return data


def normalize(text: str) -> str:
    return PUNCTUATION.sub("", text)


def asr_status() -> dict:
    available = importlib.util.find_spec("faster_whisper") is not None
    return {"engine": "faster-whisper", "installed": available,
            "note": "未安装时不会把 ASR 记为已检查" if not available else "可本地运行，首次使用需下载模型"}


_MODELS: dict[str, object] = {}


def _model(size: str):
    """Load a Whisper model once per process; loading dominates short clips."""
    if size not in _MODELS:
        from faster_whisper import WhisperModel

        _MODELS[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODELS[size]


def transcribe(audio: Path, *, enabled: bool, model_size: str = "small", language: str = "zh") -> dict:
    """Optional, pluggable local ASR.  Never fails the whole production."""
    status = asr_status()
    if not enabled:
        return {"status": "disabled", **status, "segments": [], "text": "",
                "limitations": ["未启用 ASR；字幕与配音一致性只经过时间轴检查"]}
    if not status["installed"]:
        return {"status": "unavailable", **status, "segments": [], "text": "",
                "limitations": ["未安装 faster-whisper，未执行语音转写"]}
    try:
        model = _model(model_size)
        segments, info = model.transcribe(
            str(audio), language=language, vad_filter=True,
            # Bias toward simplified Chinese so the transcript can be compared with the script.
            initial_prompt="以下是普通话的简体中文句子。",
        )
        rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
                for s in segments]
        return {"status": "completed", **status, "model": model_size, "language": info.language,
                "segments": rows, "text": "".join(row["text"] for row in rows),
                "limitations": ["ASR 结果受模型大小与背景音乐影响，公式和专有名词可能误识别",
                                "小模型可能输出繁体或近音字，覆盖率下降不等于配音有错"]}
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        return {"status": "error", **status, "segments": [], "text": "",
                "error": f"{type(exc).__name__}: {exc}",
                "limitations": ["ASR 执行失败，未据此判定配音正确"]}


def compare_transcript(script: str, transcript: dict) -> dict:
    """Character-level coverage and obvious omissions/duplications."""
    if transcript.get("status") != "completed" or not transcript.get("text"):
        return {"status": "not-run", "coverage": None, "missing": [], "repeats": [],
                "reason": "没有可用的 ASR 文本"}
    original, heard = normalize(script), normalize(transcript["text"])
    if not original:
        return {"status": "not-run", "coverage": None, "missing": [], "repeats": []}
    matcher = difflib.SequenceMatcher(None, original, heard, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    coverage = matched / len(original)
    missing, repeats = [], []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"} and i2 - i1 >= 8:
            missing.append(original[i1:i2][:40])
    for size in (8, 12):
        seen = {}
        for index in range(0, max(1, len(heard) - size + 1)):
            gram = heard[index:index + size]
            seen[gram] = seen.get(gram, 0) + 1
        repeats = [gram for gram, count in seen.items() if count >= 3][:5]
        if repeats:
            break
    return {"status": "ok" if coverage >= 0.9 and not missing else "review",
            "coverage": round(coverage, 3), "missing": missing, "repeats": repeats,
            "missing_min_chars": 8,
            "limitations": ["字符覆盖率不能证明发音正确或语序自然；ASR 的形近/近音字会拉低覆盖率"]}


def silence_report(audio: Path, *, noise_db: int = -45, min_seconds: float = 1.2) -> dict:
    """Detect long internal silences that usually mean a broken narration splice.

    Leading/trailing silence is expected (scene padding and fades) and is
    reported separately instead of being treated as a defect.
    """
    command = [ffmpeg(), "-hide_banner", "-nostats", "-i", str(audio), "-af",
               f"silencedetect=noise={noise_db}dB:d={min_seconds}", "-f", "null", "-"]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, check=False)
    starts = [float(v) for v in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(v) for v in re.findall(r"silence_end: (-?[\d.]+)", proc.stderr)]
    total = _duration(audio)
    spans = []
    for start, end in zip(starts, ends):
        position = "internal"
        if start <= 0.05:
            position = "leading"
        elif total and end >= total - 0.05:
            position = "trailing"
        spans.append({"start": round(max(0.0, start), 2), "end": round(end, 2), "position": position})
    internal = [span for span in spans if span["position"] == "internal"]
    return {"status": "review" if internal else "ok", "long_silences": internal,
            "edge_silences": [span for span in spans if span["position"] != "internal"],
            "threshold_db": noise_db, "minimum_seconds": min_seconds,
            "note": "只检测长静音，不能说明配音清晰或发音正确"}


def _duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as stream:
            return stream.getnframes() / float(stream.getframerate() or 1)
    except (OSError, wave.Error):
        return 0.0


def ducking_report(voice: Path, mix: Path) -> dict:
    """Check that the music bed stays below the voice while narration plays."""
    if not voice.is_file() or not mix.is_file():
        return {"status": "unavailable", "reason": "缺少原声或混音文件"}
    dry = _read_mono(voice)
    wet = _read_mono(mix)
    count = min(len(dry), len(wet))
    if count < SAMPLE_RATE:
        return {"status": "unavailable", "reason": "音频过短"}
    dry, wet = dry[:count], wet[:count]
    window = SAMPLE_RATE // 20
    frames = count // window
    voice_rms = np.sqrt(np.mean(dry[:frames * window].reshape(frames, window) ** 2, axis=1))
    mix_rms = np.sqrt(np.mean(wet[:frames * window].reshape(frames, window) ** 2, axis=1))
    speech = voice_rms > 0.02
    if not speech.any():
        return {"status": "unavailable", "reason": "未检测到清晰语音段"}
    ratio = mix_rms[speech] / np.maximum(voice_rms[speech], 1e-6)
    excess = float(np.max(ratio)) if len(ratio) else 1.0
    return {"status": "ok" if excess < 1.6 else "review",
            "max_mix_to_voice_ratio": round(excess, 3),
            "mean_mix_to_voice_ratio": round(float(np.mean(ratio)), 3),
            "speech_frames": int(speech.sum()), "total_frames": int(frames),
            "note": "混音/原声能量比，高于 1.6 提示配乐可能盖住人声；不能替代实听"}


def key_term_report(script: str, transcript: dict, terms: list[str]) -> dict:
    """Check that terms whose misreading changes the meaning survived ASR.

    Each entry lists accepted spellings separated by ``|`` (``"Qwen|千问"``), so a
    correct reading spelled differently is not reported as lost.  A lost term is a
    review signal, not a hard failure: a small ASR model mis-hears terms that were
    spoken correctly, and the report says so.
    """
    cleaned = [str(term).strip() for term in terms if str(term).strip()]
    if not cleaned:
        return {"status": "not-configured", "checked": [], "lost": [], "found": [],
                "note": "未配置 key_terms；关键术语没有单独检查"}
    if transcript.get("status") != "completed" or not transcript.get("text"):
        return {"status": "not-run", "checked": cleaned, "lost": [], "found": [],
                "reason": "没有可用的 ASR 文本，无法核对术语"}
    heard = normalize(transcript["text"])
    written = normalize(script)
    found, lost = [], []
    for term in cleaned:
        variants = [normalize(part) for part in term.split("|") if normalize(part)]
        if not variants:
            continue
        # A term missing from the script is a configuration issue, not a TTS defect.
        if not any(variant in written for variant in variants):
            lost.append({"term": term, "reason": "旁白里没有出现该术语，配置可能已过期"})
        elif any(variant in heard for variant in variants):
            found.append(term)
        else:
            lost.append({"term": term, "reason": "ASR 转写里没有找到该术语或其可接受写法"})
    return {"status": "ok" if not lost else "review", "checked": cleaned,
            "found": found, "lost": lost,
            "limitations": ["术语核对依赖 ASR；未通过只说明需要复听，不等于配音读错"]}


def content_check(script: str, asr: dict, *, terms: list[str] | None = None) -> dict:
    """Independent check of numbers, units, negations, terms and formulas.

    This is separate from character coverage: a sentence can be 95% covered and still
    have lost the word "不" or turned 0.5 into 5.
    """
    from .speech import reading_units, verify_reading

    if asr.get("status") != "completed" or not asr.get("text"):
        return {"status": "not-run", "units": 0, "missing": [], "changed": [],
                "reason": "ASR 未启用或没有转写文本；语音内容未做独立核对"}
    units = reading_units(script, terms=terms)
    result = verify_reading(units, asr["text"])
    key_units = [unit for unit in units if unit.importance == "key"]
    return {"status": result["status"], "units": len(units), "key_units": len(key_units),
            "missing": result["missing"], "changed": result["changed"],
            "limitations": result["limitations"]}


def audio_qc(voice: Path, mix: Path, script: str, *, config: dict) -> dict:
    asr = transcribe(voice, enabled=bool(config.get("asr_enabled", False)),
                     model_size=str(config.get("asr_model", "small")))
    return {
        "asr": asr,
        "transcript_check": compare_transcript(script, asr),
        "content_check": content_check(script, asr, terms=config.get("key_terms") or []),
        "key_terms": key_term_report(script, asr, config.get("key_terms") or []),
        "silence": silence_report(mix),
        "ducking": ducking_report(voice, mix),
        "listened_by_human": False,
        "note": "机器检查只覆盖静音、能量比与可选 ASR；人工实听仍需单独记录",
    }
