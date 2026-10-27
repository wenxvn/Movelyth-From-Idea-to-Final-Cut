"""V3 craft layer: coverage beats, automatic Foley, frame composition.

These tests cover what a viewer would notice — the picture changing with the
sentence, sound landing on the animation, and a real subject in the frame —
without calling a model, TTS or Remotion.
"""
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from movelyth.craft import (
    _coverage_beats,
    composition_report,
    narrative_report,
    rhythm_report,
    sound_design_report,
)
from movelyth.media import SAMPLE_RATE, prosody_segments
from movelyth.models import Film, Layer, Scene
from movelyth.scenedsl import renderer_contract
from movelyth.sound import design_sound_events, soundtrack
from tests import factories


def _page(start: float, end: float, text: str = "一句话") -> dict:
    return {"start": start, "end": end, "text": text, "words": []}


def test_coverage_beats_group_sentences_into_two_to_four_beats():
    scene = {"frames": 750, "captions": [
        _page(0.2, 2.0), _page(2.1, 4.0), _page(4.2, 6.0), _page(8.0, 10.0), _page(10.2, 12.0),
        _page(12.4, 15.0), _page(16.0, 18.0), _page(18.2, 21.0), _page(22.0, 24.5),
    ]}
    beats = _coverage_beats(scene, 25.0)
    assert 2 <= len(beats) <= 4
    assert beats[0] == 0.0
    assert all(0 <= value < 25.0 for value in beats)


def test_rhythm_report_counts_beat_starts_as_coverage():
    pages = [_page(index * 2.0, index * 2.0 + 1.6) for index in range(8)]
    scene = {"id": "s", "frames": 480, "captions": pages,
             "actions_resolved": [{"target": "chart", "kind": "draw", "from": 0.0, "to": 0.1}]}
    report = rhythm_report({"scenes": [scene]}, 30)
    assert report["caption_pages"] == 8
    assert report["coverage_beats"] >= 2
    # Beat starts cover the pages that a single draw action could not.
    assert report["covered_pages"] > 1


def test_narrative_report_flags_announcements_and_uniform_sentences():
    scenes = [factories.scene(f"s{index}", "接下来我们看下一个概念，这句话长度也差不多。")
              for index in range(10)]
    film = Film.model_validate(factories.film(long_scenes=scenes, short_scenes=scenes))
    report = narrative_report(film)
    assert report["status"] == "review"
    assert any("报幕" in warning for warning in report["warnings"])
    assert any("句长" in warning for warning in report["warnings"])


def _write_frame(path: Path, *, subject: tuple[int, int, int, int], size=(640, 360)) -> str:
    image = Image.new("RGB", size, "#0a0f14")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle(subject, fill="#6fe6ef")
    image.save(path)
    return str(path)


def test_composition_report_measures_subject_and_flags_empty_frames(tmp_path):
    tall = _write_frame(tmp_path / "tall.jpg", subject=(200, 40, 440, 320))
    small = _write_frame(tmp_path / "small.jpg", subject=(280, 150, 360, 200))
    good = composition_report([tall], portrait=False)
    assert good["status"] == "ok"
    assert good["subject_height_median"] > 0.5
    bad = composition_report([small], portrait=False)
    assert bad["status"] == "review"
    assert any("主体高度" in warning for warning in bad["warnings"])


def _write_wav(path: Path, audio: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes((np.clip(audio, -0.98, 0.98) * 32767).astype("<i2").tobytes())
    return path


def test_sound_design_events_follow_actions_and_keep_director_cues():
    scene = {
        "id": "s1", "frames": 300, "transition": "wipe", "camera": "pan_right", "role": "hook",
        "actions_resolved": [{"target": "chart", "kind": "draw", "from": 0.1, "to": 0.3},
                             {"target": "note", "kind": "highlight", "from": 0.6, "to": 0.7}],
        "captions": [_page(0.3, 2.0), _page(2.2, 4.0), _page(4.2, 6.0)],
        "layers": [{"id": "chart", "type": "chart", "region": "main"},
                   {"id": "note", "type": "text", "region": "side"}],
        "emphasis": ["重点"],
    }
    director = [{"at": 3.0, "kind": "impact", "gain": 0.4, "pan": 0.0, "send": 0.2,
                 "priority": 9, "source": "director"}]
    events = design_sound_events([scene], fps=30, scene_starts=[0.0], lead=0.0,
                                 duration=10.0, extra=director)
    sources = {event["source"] for event in events}
    assert "director" in sources
    assert "auto" in sources or "action-end" in sources
    assert any(event["kind"] == "swipe" for event in events)
    # Everything is inside the film, and a scene marker sits at the start.
    assert all(0 <= event["at"] <= 10.0 for event in events)
    assert any(abs(event["at"]) < 0.1 for event in events)


def test_sound_design_density_is_capped_on_a_dense_cut():
    scenes = [{
        "id": f"s{index}", "frames": 120, "transition": "wipe", "camera": "push", "role": "mechanism",
        "actions_resolved": [{"target": "chart", "kind": "draw", "from": 0.1, "to": 0.2},
                             {"target": "note", "kind": "appear", "from": 0.4, "to": 0.5},
                             {"target": "note", "kind": "highlight", "from": 0.7, "to": 0.8}],
        "captions": [_page(0.1, 1.0), _page(1.1, 2.0), _page(2.1, 3.0), _page(3.1, 3.9)],
        "layers": [{"id": "chart", "type": "chart", "region": "main"},
                   {"id": "note", "type": "text", "region": "side"}],
        "emphasis": [],
    } for index in range(10)]
    duration = 40.0
    events = design_sound_events(scenes, fps=30, scene_starts=[index * 4.0 for index in range(10)],
                                 lead=0.0, duration=duration, max_per_minute=12)
    assert len(events) <= max(12, int(duration / 60 * 12))
    gaps = [b["at"] - a["at"] for a, b in zip(events, events[1:])]
    assert min(gaps) >= 0.30


def test_soundtrack_v3_stereo_widens_and_keeps_cues_under_the_voice(tmp_path):
    voice = np.zeros(SAMPLE_RATE * 8, dtype=np.float32)
    voice[int(2.0 * SAMPLE_RATE):int(4.0 * SAMPLE_RATE)] = 0.08
    mix = soundtrack(voice, [0.0, 4.0], "tech",
                        cues=[{"at": 2.05, "kind": "impact", "gain": 0.4, "pan": 0.2, "send": 0.3}],
                        sections=[{"start": 0.0, "end": 4.0, "energy": 0.5, "role": "mechanism"},
                                  {"start": 4.0, "end": 8.0, "energy": 0.8, "role": "turn"}])
    assert mix.shape == (len(voice), 2)
    correlation = float(np.corrcoef(mix[:, 0], mix[:, 1])[0, 1])
    assert correlation < 0.999          # stereo is not a duplicated mono track
    assert correlation > 0.4            # and stays mono-compatible
    cue = mix[int(2.05 * SAMPLE_RATE):int(2.35 * SAMPLE_RATE)].mean(axis=1)
    assert float(np.max(np.abs(cue))) < 0.5


def test_prosody_splits_clauses_and_marks_the_emphasis_phrase():
    narration = "先给偏差记账。预测减去目标，得到负二和负四；直接相加会让正负偏差互相抵消，所以这里先平方，再求平均。"
    segments = prosody_segments(narration, ["偏差"], config={"voice_rate": "+0%", "max_retries": 0})
    assert "".join(segment["text"] for segment in segments) == narration
    assert any(segment["emphasis"] for segment in segments)
    clause = next(segment for segment in segments if "得到负二和负四" in segment["text"])
    marked = next(segment for segment in segments if segment["emphasis"])
    assert int(marked["rate"].rstrip("%")) < int(clause["rate"].rstrip("%"))
    assert sum(1 for segment in segments if segment["pause_after"] >= 0.15) >= 2


def test_renderer_contract_exposes_v3_fields():
    contract = renderer_contract()
    assert "insight_bands" in contract
    assert set(contract["scene_roles"]) == {"hook", "mechanism", "example", "turn", "conclusion"}
    assert contract["type_scale"]["caption"] >= 60


def test_scene_v3_fields_are_bounded_and_hero_must_exist():
    base = factories.scene("v3")
    scene = Scene.model_validate({**base, "chapter": "记账", "role": "turn", "metric": "5",
                                 "takeaway": "先把偏差平方", "hero": "visual"})
    assert scene.role == "turn"
    with pytest.raises(ValueError, match="hero"):
        Scene.model_validate({**base, "hero": "missing"})
    with pytest.raises(ValueError):
        Scene.model_validate({**base, "role": "climax"})
    with pytest.raises(ValueError, match="highlight"):
        Layer.model_validate({**factories.chart_layer("c"), "highlight": [1.0]})
    ok = Layer.model_validate({**factories.chart_layer("c"), "highlight": [0.0, 2.0],
                               "annotations": [{"x": 2.0, "text": "终点"}]})
    assert ok.annotations[0].text == "终点"


def test_storyboard_sheet_carries_direction_fields(tmp_path):
    """A preview sheet that drops the new fields cannot be reviewed."""
    from movelyth.pipeline import Studio

    class Stub:
        config = {"studio": {"fps": 30}}

    cut = {"scenes": [{
        "id": "s1", "frames": 300, "heading": "测试", "layout": "diagram",
        "chapter": "记账", "role": "turn", "takeaway": "先平方", "metric": "5", "hero": "c",
        "layers": [{"id": "c", "type": "chart", "region": "main", "annotations": [{"x": 1.0, "text": "终点"}],
                    "highlight": [0.0, 1.0]}],
        "transition": "wipe", "camera": "push", "emphasis": [], "cues_resolved": [],
        "beat_times": [], "actions_resolved": [], "caption_timing": "tts-word-boundaries",
        "layout_warnings": [],
    }]}
    rows = Studio._storyboard_scenes(Stub(), cut)
    assert rows[0]["role"] == "turn"
    assert rows[0]["metric"] == "5"
    assert rows[0]["layers"][0]["annotations"][0]["text"] == "终点"


def test_sound_design_report_reads_events_and_flags_sparse_tracks(tmp_path):
    mix = _write_wav(tmp_path / "mix.wav", np.zeros(SAMPLE_RATE, dtype=np.float32))
    cut = {"scenes": [{"id": "s1", "frames": 1800, "transition": "fade", "camera": "push",
                       "actions_resolved": []}],
           "sound_events": [{"at": 1.0, "kind": "tick", "source": "auto"}]}
    report = sound_design_report(cut, mix)
    assert report["events"] == 1
    assert report["status"] == "review"
    assert any("密度" in warning for warning in report["warnings"])