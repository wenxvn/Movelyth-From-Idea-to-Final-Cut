"""S2-02: speech settings, pronunciation units and the independent content check."""
from __future__ import annotations

import pytest

from movelyth.audioqc import content_check
from movelyth.policy import audio_checks, decide
from movelyth.speech import (
    SpeechResult,
    SpeechSettings,
    cache_key,
    canonical_reading,
    describe,
    magnitude_sign,
    reading_units,
    speech_settings,
    verify_reading,
)

# ------------------------------------------------------------------- settings

def test_legacy_config_inherits_the_studio_voice():
    settings = speech_settings({"studio": {"voice": "zh-CN-XiaoxiaoNeural", "voice_rate": "+8%"}})
    assert settings.backend == "edge" and settings.voice == "zh-CN-XiaoxiaoNeural"
    assert settings.rate == "+8%" and settings.granularity == "sentence"


def test_the_speech_section_overrides_only_what_it_names():
    settings = speech_settings({"studio": {"voice": "zh-CN-YunxiNeural", "voice_rate": "+0%"},
                                "speech": {"voice": "zh-CN-YunyangNeural", "granularity": "clause"}})
    assert settings.voice == "zh-CN-YunyangNeural" and settings.granularity == "clause"
    assert settings.rate == "+0%"


def test_an_unsupported_control_is_refused_not_ignored():
    with pytest.raises(ValueError, match="不支持 pitch"):
        speech_settings({"studio": {"voice_pitch": "+20Hz"},
                         "speech": {"supported_controls": ["rate", "volume"]}})


def test_invalid_granularity_is_rejected():
    with pytest.raises(ValueError, match="granularity"):
        SpeechSettings(granularity="paragraph-ish")


def test_the_cache_key_separates_backend_granularity_and_reading():
    base = SpeechSettings(voice="v", rate="+0%")
    first = cache_key(text="原文", settings=base)
    assert first == cache_key(text="原文", settings=base)
    assert first != cache_key(text="原文", settings=base, granularity="paragraph")
    assert first != cache_key(text="原文", settings=base, reading="改写后的读法")
    other = SpeechSettings(voice="v", rate="+0%", backend="qwen")
    assert first != cache_key(text="原文", settings=other)


def test_a_speech_result_records_the_real_audio():
    import numpy as np

    audio = np.zeros(24000, dtype=np.float32)
    result = describe("edge", audio, [{"text": "词", "start": 0.0, "end": 0.4}],
                      settings=SpeechSettings(voice="v"), text="原文", reading="原文",
                      sample_rate=24000, cache="abc")
    assert result.samples == 24000 and result.seconds == 1.0
    assert result.boundary_source == "native" and result.boundaries == 1
    assert result.usage["characters"] == 2


def test_an_estimated_boundary_is_not_called_native():
    import numpy as np

    result = describe("edge", np.zeros(1200, dtype=np.float32), [],
                      settings=SpeechSettings(voice="v"), text="a", reading="a",
                      sample_rate=24000, boundary_source="estimated")
    assert result.boundary_source == "estimated"


def test_a_fallback_records_the_voice_it_replaced():
    result = SpeechResult(backend="edge", voice="backup", sample_rate=24000, samples=10,
                          seconds=0.0, fallback_from="primary")
    assert result.fallback_from == "primary"


# --------------------------------------------------------------- reading units

def test_numbers_keep_their_sign_magnitude_and_unit():
    units = reading_units("误差从 0.5 降到 -0.05，耗时 12 毫秒。")
    written = [unit.written for unit in units if unit.kind == "number"]
    assert "0.5" in written and "-0.05" in written and "12毫秒" in written
    assert any(unit.kind == "unit" and unit.written == "毫秒" for unit in units)


def test_negations_terms_and_formulas_are_extracted():
    units = reading_units("它并不是 A = B，Qwen 也不会自动运行。", terms=["Qwen|千问"])
    kinds = {unit.kind for unit in units}
    assert {"negation", "term", "formula"} <= kinds


def test_equivalent_readings_fold_only_the_form():
    assert canonical_reading("零点五") == "0.5"
    assert magnitude_sign("0.5") == (1, 2)
    assert magnitude_sign("-0.05") == (-1, 3)
    assert magnitude_sign("没有数字") == (0, 0)


def test_a_correctly_spoken_number_passes():
    units = reading_units("误差是 0.5 秒。")
    result = verify_reading(units, "误差是零点五秒。")
    assert result["status"] == "ok"


def test_a_lost_sign_is_reported_as_changed_not_missing():
    units = reading_units("温度是 -5 度。")
    result = verify_reading(units, "温度是 5 度。")
    assert result["changed"] and "正负号" in result["changed"][0]["reason"]
    assert not result["missing"]


def test_a_magnitude_change_is_reported_as_changed():
    units = reading_units("误差是 0.5 秒。")
    result = verify_reading(units, "误差是 5 秒。")
    assert result["changed"] and "量级" in result["changed"][0]["reason"]


def test_a_lost_negation_is_reported_as_missing():
    units = reading_units("这个结论不正确。")
    result = verify_reading(units, "这个结论正确。")
    assert result["missing"] and result["missing"][0]["written"] == "不"


# ------------------------------------------------------------- content check

def test_content_check_is_not_run_without_asr():
    result = content_check("误差是 0.5 秒。", {"status": "disabled"})
    assert result["status"] == "not-run" and "ASR" in result["reason"]


def test_content_check_reports_changed_numbers():
    asr = {"status": "completed", "text": "误差是 5 秒"}
    result = content_check("误差是 0.5 秒。", asr)
    assert result["status"] == "review" and result["changed"]


def test_a_changed_number_blocks_the_release():
    report = {"asr": {"status": "completed"}, "transcript_check": {"status": "ok"},
              "content_check": {"status": "review", "changed": [
                  {"written": "0.5", "heard_digits": 1, "reason": "数字位数/量级被改变"}],
                  "missing": [], "units": 3}}
    checks = audio_checks(report, cut="long")
    content = next(check for check in checks if check.check_id == "audio.long.content")
    assert content.status == "fail" and content.severity == "critical"
    assert decide(checks).decision == "blocked"


def test_a_lost_term_only_asks_for_a_listen():
    report = {"asr": {"status": "completed"}, "transcript_check": {"status": "ok"},
              "content_check": {"status": "review", "changed": [],
                                "missing": [{"written": "Qwen", "kind": "term"}], "units": 3}}
    checks = audio_checks(report, cut="long")
    content = next(check for check in checks if check.check_id == "audio.long.content")
    assert content.status == "unknown" and content.required is False
    assert decide(checks).decision == "ready"


def test_chinese_numerals_fold_to_digits_but_signs_do_not():
    units = reading_units("耗时 12 毫秒，误差 -0.05。")
    assert verify_reading(units, "耗时十二毫秒，误差负零点零五")["status"] == "ok"
    # The same reading with the sign dropped is a changed number, not a mishearing.
    result = verify_reading(units, "耗时十二毫秒，误差零点零五")
    assert result["changed"] and "正负号" in result["changed"][0]["reason"]
