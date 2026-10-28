"""S2-03: stems, event onsets, tails, ducking and stem balance."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from movelyth.agents import MockProvider
from movelyth.media import SAMPLE_RATE, read_wav
from movelyth.mix import (
    ducking_report,
    mix_report,
    onset_report,
    stem_balance,
    stem_stats,
    tail_report,
    voice_presence,
    write_stems,
)
from movelyth.policy import decide, mix_checks
from tests.conftest import make_studio
from tests.factories import film, research_payload, review_payload


def tone(seconds: float, level: float = 0.2, *, start: float = 0.0, freq: float = 220.0) -> np.ndarray:
    size = int(seconds * SAMPLE_RATE)
    signal = np.zeros(size, dtype=np.float32)
    begin = int(start * SAMPLE_RATE)
    t = np.arange(size - begin, dtype=np.float32) / SAMPLE_RATE
    signal[begin:] = level * np.sin(2 * np.pi * freq * t)
    return signal


def stems(**overrides) -> dict[str, np.ndarray]:
    base = {"voice": tone(4.0, 0.3), "music": tone(4.0, 0.02),
            "sfx": np.zeros(int(4 * SAMPLE_RATE), dtype=np.float32),
            "duck": np.ones(int(4 * SAMPLE_RATE), dtype=np.float32)}
    base.update(overrides)
    return base


# --------------------------------------------------------------------- stems

def test_stem_stats_report_peak_rms_and_clipping():
    stats = stem_stats(tone(1.0, 0.5))
    assert stats["seconds"] == 1.0 and stats["clipped"] == 0
    assert stats["peak_db"] == pytest.approx(-6.02, abs=0.1)
    loud = np.ones(SAMPLE_RATE, dtype=np.float32)
    assert stem_stats(loud)["clipped"] > 0


def test_voice_presence_is_measured_on_the_voice_stem():
    assert voice_presence(tone(3.0, 0.2))["present"] is True
    silent = voice_presence(np.zeros(SAMPLE_RATE * 3, dtype=np.float32))
    assert silent["present"] is False and silent["audible_share"] == 0.0


def test_music_cannot_hide_a_missing_voice():
    """M04: the mix has energy, but the voice stem is silent."""
    report = mix_report(stems(voice=np.zeros(int(4 * SAMPLE_RATE), dtype=np.float32),
                              music=tone(4.0, 0.3)))
    assert report["passed"] is False
    assert any("人声" in problem for problem in report["problems"])


# --------------------------------------------------------------------- events

def test_an_event_that_landed_is_found_and_a_dropped_one_is_reported():
    sfx = np.zeros(int(4 * SAMPLE_RATE), dtype=np.float32)
    sfx[int(2.0 * SAMPLE_RATE):int(2.0 * SAMPLE_RATE) + 800] = 0.4
    report = onset_report(sfx, [{"at": 2.0, "kind": "impact"}, {"at": 3.5, "kind": "chime"}])
    assert report["checked"] == 2 and report["found"] == 1
    assert report["missing"][0]["at"] == 3.5
    assert "只证明该时刻有能量变化" in report["note"]


def test_an_event_outside_the_mix_is_reported():
    report = onset_report(tone(1.0), [{"at": 9.0, "kind": "impact"}])
    assert report["missing"] and "混音之外" in report["missing"][0]["reason"]


# ---------------------------------------------------------------------- tails

def test_a_cut_tail_is_detected():
    signal = np.concatenate([np.zeros(1000, dtype=np.float32), np.full(SAMPLE_RATE, 0.4, dtype=np.float32)])
    report = tail_report(signal)
    assert report["ok"] is False and "截断" in report["note"]


def test_a_faded_tail_passes():
    t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    signal = (0.4 * np.exp(-t * 6)).astype(np.float32)
    assert tail_report(signal)["ok"] is True


# ------------------------------------------------------------------- ducking

def test_a_slow_ducking_envelope_passes():
    envelope = 0.3 + 0.6 * np.abs(np.sin(np.arange(SAMPLE_RATE * 4) / SAMPLE_RATE))
    assert ducking_report(envelope.astype(np.float32))["ok"] is True


def test_fast_ducking_oscillation_is_reported_as_pumping():
    fast = (0.5 + 0.4 * np.sin(np.arange(SAMPLE_RATE * 4) * 2 * np.pi * 20 / SAMPLE_RATE)).astype(np.float32)
    report = ducking_report(fast)
    assert report["ok"] is False and "抽吸" in report["note"]


# ------------------------------------------------------------------- balance

def test_a_stem_louder_than_the_voice_is_a_problem():
    report = stem_balance({"voice": tone(2.0, 0.1), "music": tone(2.0, 0.6)})
    assert report["ok"] is False and any("music" in problem for problem in report["problems"])


def test_a_balanced_mix_has_no_stem_problems():
    assert stem_balance({"voice": tone(2.0, 0.3), "music": tone(2.0, 0.1)})["ok"] is True


# ---------------------------------------------------------------- persistence

def test_stems_are_written_and_readable(tmp_path):
    paths = write_stems(stems(), tmp_path / "stems")
    assert set(paths) >= {"voice", "music", "sfx", "duck"}
    audio = read_wav(Path(paths["voice"]))
    assert len(audio) == int(4 * SAMPLE_RATE)
    manifest = json.loads((tmp_path / "stems" / "stems.json").read_text(encoding="utf-8"))
    assert manifest["sample_rate"] == SAMPLE_RATE and "voice_dry" in manifest["note"]


# ------------------------------------------------------------------- policy

def test_a_missing_voice_stem_blocks_the_release():
    report = mix_report(stems(voice=np.zeros(int(4 * SAMPLE_RATE), dtype=np.float32)))
    checks = mix_checks(report, cut="long")
    voice = next(check for check in checks if check.check_id == "audio.long.voice-stem")
    assert voice.status == "fail" and voice.severity == "critical"
    assert decide(checks).decision == "blocked"


def test_a_missing_mix_report_is_only_an_unknown():
    checks = mix_checks({}, cut="long")
    assert checks[0].status == "unknown" and checks[0].required is False
    assert decide(checks).decision == "ready"


# ------------------------------------------------------------------ pipeline

def test_the_pipeline_records_the_mix_report_and_its_absence(offline_pipeline):
    """The offline cut is stubbed, so no stems exist: that must be an explicit unknown."""
    provider = MockProvider({"research": research_payload(), "director": film(),
                             "reviewer": review_payload()})
    studio = make_studio(offline_pipeline, provider)
    try:
        episode = studio.create("分轨记录测试")
        result = studio.produce(episode["id"])
        quality = json.loads((Path(result["delivery"]) / "质检报告.json").read_text(encoding="utf-8"))
        assert "mix" in quality["technical"]["long"]
        unknown = [check for check in quality["release_decision"]["warnings"]
                   if check["check_id"] == "audio.long.mix"]
        assert unknown and unknown[0]["status"] == "unknown"
        assert unknown[0]["required"] is False
    finally:
        studio.close()


def test_prepare_cut_writes_stems_when_it_runs(tmp_path, monkeypatch):
    """The real prepare_cut path writes stems; TTS is replaced by a deterministic stub."""
    from movelyth import media

    def fake_voice(text, config, cache, *, rate=None, pitch=None, volume=None, adapter="edge"):
        audio = np.zeros(int(0.4 * SAMPLE_RATE * max(1, len(text) // 4)), dtype=np.float32)
        boundaries = [{"text": text[: max(1, len(text) // 2)], "start": 0.0,
                       "end": 0.2 * len(text) / 4}]
        return audio, boundaries, []

    monkeypatch.setattr("movelyth.media.voice", fake_voice)
    cut = {"title": "分轨测试", "style": "tech", "scenes": [
        {"id": "one", "heading": "测试镜头", "narration": "这是一句用于测试分轨的旁白内容，长度足够。",
         "visual": "matrix", "labels": ["观察"], "matrix": [1, 0, 0, 1], "color": "cyan",
         "source_index": 0, "layout": "diagram", "beats": [], "layers": [], "actions": [],
         "visual_intent": "测试"}]}
    config = {"fps": 30, "voice": "zh-CN-YunxiNeural", "voice_rate": "+0%", "max_retries": 0,
              "speech_replace": {}}
    data, paths = media.prepare_cut(cut, config, tmp_path / "cache", tmp_path / "out", portrait=False)
    assert "mix_report" in data and data["stems"]
    assert (tmp_path / "out" / "stems" / "voice.wav").is_file()
    assert data["mix_report"]["voice"]["present"] in {True, False}
    assert data["speech"]["boundary_sources"]
