"""V2 craft layer: prosody, sentence pauses, pacing and sound cues.

These tests cover what a viewer would notice — pauses where the writing has them,
a rhythm that is not nine identical shots, cues that land on the real narration —
without calling TTS or rendering.
"""
import numpy as np
import pytest

from movelyth.media import SAMPLE_RATE, prosody_plan, sentence_spans, trim_silence
from movelyth.models import Cue, Film, Scene
from movelyth.quality import ScriptIssues
from movelyth.scenedsl import pacing_estimate, pacing_report, resolve_cues
from movelyth.sound import _process_voice, _sidechain, soundtrack
from tests import factories


def test_sentences_are_split_at_punctuation_and_long_clauses():
    text = ("第一句很短。第二句为了触发长句再切分，故意写得很长很长，"
            "里面包含多个分句，每一个分句都足够长，这样才会在逗号处再切一次，便于配音停顿。")
    spans = sentence_spans(text)
    assert len(spans) >= 4
    assert all(0 <= begin < end <= len(text) for begin, end in spans)
    assert "".join(text[begin:end] for begin, end in spans) == text
    assert all(len(text[begin:end]) <= 52 for begin, end in spans)


def test_emphasis_sentence_slows_down_and_gets_louder():
    narration = "这里有一个普通句子。斜率决定方向，这是重点。最后收尾。"
    plain = prosody_plan(narration, [])
    marked = prosody_plan(narration, ["斜率"])
    base = next(item for item in plain if "斜率" in item["text"])
    focus = next(item for item in marked if "斜率" in item["text"])
    assert int(focus["rate"].rstrip("%")) < int(base["rate"].rstrip("%"))
    assert int(focus["volume"].rstrip("%")) > int(base["volume"].rstrip("%"))
    assert focus["emphasis"] is True


def test_pause_after_sentence_depends_on_punctuation():
    plan = prosody_plan("这是一句陈述。这是问句吗？这是未完的，")
    assert plan[0]["pause_after"] > plan[2]["pause_after"]
    assert plan[1]["pause_after"] >= plan[0]["pause_after"]


def test_trim_silence_removes_engine_padding_and_reports_offset():
    audio = np.concatenate([np.zeros(int(0.2 * SAMPLE_RATE), dtype=np.float32),
                            np.full(int(0.5 * SAMPLE_RATE), 0.3, dtype=np.float32),
                            np.zeros(int(0.9 * SAMPLE_RATE), dtype=np.float32)])
    trimmed, offset = trim_silence(audio)
    assert offset == pytest.approx(0.15, abs=0.02)
    assert len(trimmed) < len(audio) * 0.6


def test_sidechain_ducks_early_and_returns_smoothly():
    voice = np.zeros(SAMPLE_RATE * 4, dtype=np.float32)
    voice[int(1.0 * SAMPLE_RATE):int(2.0 * SAMPLE_RATE)] = 0.2
    gain = _sidechain(voice)
    assert gain[int(1.0 * SAMPLE_RATE)] < 0.5          # ducks before the word lands
    assert gain[int(3.5 * SAMPLE_RATE)] > 0.85         # recovers during silence
    # No 20 ms on/off stepping: the largest jump between adjacent samples is tiny.
    assert float(np.max(np.abs(np.diff(gain)))) < 0.01


def test_process_voice_keeps_level_bounded():
    voice = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
    voice[:] = 0.05 * np.sin(2 * np.pi * 220 * np.arange(len(voice)) / SAMPLE_RATE)
    shaped = _process_voice(voice)
    assert shaped.shape == voice.shape
    assert float(np.max(np.abs(shaped))) < 0.98


def test_cue_lands_on_the_narration_word_it_names():
    scene = Scene.model_validate(factories.scene(
        "cued", "误差在下降，所以每一步都在靠近低点。", cues=[
            {"at": "narration:每一步", "kind": "tick", "gain": 0.5}]))
    resolved = resolve_cues(scene, duration=6.0)
    assert len(resolved) == 1
    # 0.35–0.75 of the scene: the phrase is late in the sentence, not at the start.
    assert 0.3 < resolved[0]["at"] / 6.0 < 1.0
    assert resolved[0]["kind"] == "tick"


def test_impact_cues_are_limited_per_cut():
    scenes = [factories.scene(f"s{index}", "这是一个用于测试的旁白句子，说明画面的真实含义。",
                              cues=[{"at": "start", "kind": "impact"}])
              for index in range(3)]
    cut = factories.film(long_scenes=scenes)["long"]
    from movelyth.models import Cut
    from movelyth.scenedsl import validate_cut_dsl

    problems = validate_cut_dsl(Cut.model_validate(cut), vertical=False)
    assert any("impact" in problem for problem in problems)


def test_emphasis_word_must_appear_in_narration():
    scene = factories.scene("focus", "这一段旁白里没有那个词，用来验证校验会报错。", emphasis=["斜率"])
    film = factories.film(long_scenes=[scene] + [
        factories.scene("b", "第二个镜头的旁白，用来让视觉签名不同。", layers=[factories.layer("v", procedural="vectors")]),
        factories.scene("c", "第三个镜头的旁白，用来让视觉签名不同。", layers=[factories.layer("p", procedural="projection")]),
    ])
    with pytest.raises(ScriptIssues) as error:
        from movelyth.models import Research
        from movelyth.quality import validate_script
        validate_script(Film.model_validate(film), Research.model_validate(factories.research_payload()), 180, 60)
    assert "emphasis" in str(error.value)


def test_pacing_flags_nine_identical_shots():
    scenes = [factories.scene(f"s{index}", "旁白" * 20,
                              layers=[factories.layer(f"v{index}", procedural=kind)])
              for index, kind in enumerate(["matrix", "vectors", "projection"] * 3)]
    cut = {"scenes": [{**scene, "frames": 810} for scene in scenes]}
    report = pacing_report(cut, 30)
    assert report["status"] == "review"
    assert report["uniform_shots"] == 9
    assert any("幻灯片" in warning for warning in report["warnings"])


def test_pacing_accepts_contrast_and_varied_transitions():
    lengths = [240, 720, 300, 810]
    scenes = []
    for index, frames in enumerate(lengths):
        scene = factories.scene(f"s{index}", "旁白" * 20,
                                layers=[factories.layer(f"v{index}", procedural=["matrix", "vectors",
                                                                                 "projection", "wave"][index])])
        scenes.append({**scene, "frames": frames, "transition": ["fade", "wipe", "slide", "dip"][index],
                       "cues_resolved": [{"at": 0.2, "kind": "tick", "gain": 0.5}]})
    report = pacing_report({"scenes": scenes}, 30)
    assert report["spread_ratio"] > 0.25
    assert report["cues"] == 4
    # The first scene has no incoming transition, so only the other three count.
    assert report["transition_variety"] == 3
    assert not any("幻灯片" in warning for warning in report["warnings"])


def test_estimate_before_tts_uses_character_count():
    cut = Film.model_validate(factories.film()).long
    report = pacing_estimate(cut)
    assert report["estimated"] is True
    assert report["shots"] == len(cut.scenes)


def test_soundtrack_mixes_cues_under_the_voice():
    voice = np.zeros(SAMPLE_RATE * 6, dtype=np.float32)
    voice[int(2.0 * SAMPLE_RATE):int(3.0 * SAMPLE_RATE)] = 0.08
    mix = soundtrack(voice, [0, 3], "tech", cues=[{"at": 2.0, "kind": "impact", "gain": 0.6}])
    assert mix.shape == (len(voice), 2)
    assert float(np.max(np.abs(mix))) < 0.98
    # The cue is audible on its own but stays below the voice it punctuates.
    at_cue = mix[int(2.05 * SAMPLE_RATE):int(2.25 * SAMPLE_RATE)].mean(axis=1)
    assert float(np.max(np.abs(at_cue))) < 0.3


def test_cue_contract_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Cue.model_validate({"at": "start", "kind": "explosion", "gain": 0.5})
