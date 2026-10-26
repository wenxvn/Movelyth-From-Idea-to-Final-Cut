import numpy as np

from movelyth.audioqc import (
    asr_status,
    compare_transcript,
    ducking_report,
    key_term_report,
    silence_report,
    transcribe,
)
from movelyth.media import SAMPLE_RATE, write_wav


def tone(seconds: float, amplitude: float = 0.2) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_asr_is_optional_and_reports_its_boundary(tmp_path):
    audio = tmp_path / "voice.wav"
    write_wav(audio, tone(1.0))
    status = transcribe(audio, enabled=False)
    assert status["status"] == "disabled" and status["segments"] == []
    assert compare_transcript("矩阵的列是基向量的像", status)["status"] == "not-run"
    assert isinstance(asr_status()["installed"], bool)


def test_transcript_comparison_detects_missing_content():
    transcript = {"status": "completed", "text": "矩阵的列是基向量的像"}
    complete = compare_transcript("矩阵的列是基向量的像。", transcript)
    assert complete["status"] == "ok" and complete["coverage"] > 0.95
    missing = compare_transcript("矩阵的列是基向量的像，而且行列式给出面积缩放比例。", transcript)
    assert missing["status"] == "review" and missing["missing"]
    assert 0 < missing["coverage"] < 0.95


def test_long_silence_is_detected(tmp_path):
    audio = np.concatenate([tone(1.0), np.zeros(int(SAMPLE_RATE * 2.0), dtype=np.float32), tone(1.0)])
    path = tmp_path / "mix.wav"
    write_wav(path, np.stack([audio, audio], axis=1))
    report = silence_report(path)
    assert report["status"] == "review" and report["long_silences"]
    assert report["long_silences"][0]["end"] - report["long_silences"][0]["start"] >= 1.2
    assert report["long_silences"][0]["position"] == "internal"


def test_trailing_padding_is_not_reported_as_a_defect(tmp_path):
    audio = np.concatenate([tone(2.0), np.zeros(int(SAMPLE_RATE * 1.5), dtype=np.float32)])
    path = tmp_path / "mix.wav"
    write_wav(path, np.stack([audio, audio], axis=1))
    report = silence_report(path)
    assert report["status"] == "ok" and not report["long_silences"]
    assert report["edge_silences"][0]["position"] == "trailing"


def test_music_that_buries_the_voice_is_flagged(tmp_path):
    voice = tone(3.0, 0.2)
    dry = tmp_path / "narration.wav"
    write_wav(dry, voice)
    ducked = tmp_path / "ducked.wav"
    write_wav(ducked, np.stack([voice * 0.85 + 0.02, voice * 0.85 + 0.02], axis=1))
    assert ducking_report(dry, ducked)["status"] == "ok"
    loud = tmp_path / "loud.wav"
    write_wav(loud, np.stack([voice * 0.85 + 0.6, voice * 0.85 + 0.6], axis=1))
    report = ducking_report(dry, loud)
    assert report["status"] == "review" and report["max_mix_to_voice_ratio"] > 1.6


def test_ducking_reports_unavailable_instead_of_pretending(tmp_path):
    report = ducking_report(tmp_path / "missing.wav", tmp_path / "missing-mix.wav")
    assert report["status"] == "unavailable"


def test_key_terms_accept_an_alternate_spelling_and_flag_a_real_loss():
    transcript = {"status": "completed", "text": "我们用千问模型做实验"}
    kept = key_term_report("我们用千问模型做实验", transcript, ["Qwen|千问"])
    assert kept["status"] == "ok" and kept["found"] == ["Qwen|千问"]
    lost = key_term_report("这里用熵来度量不确定性", transcript, ["熵|熵值"])
    assert lost["status"] == "review"
    assert lost["lost"][0]["term"] == "熵|熵值"
    stale = key_term_report("我们用千问模型做实验", transcript, ["行列式"])
    assert stale["status"] == "review" and "配置可能已过期" in stale["lost"][0]["reason"]


def test_key_terms_are_not_checked_without_asr():
    report = key_term_report("这里用熵来度量", {"status": "disabled"}, ["熵"])
    assert report["status"] == "not-run" and report["lost"] == []
    assert key_term_report("任意", {"status": "completed", "text": "任意"}, [])["status"] == "not-configured"
