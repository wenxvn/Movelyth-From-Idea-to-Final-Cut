"""Shared offline fixtures: real TTS/FFmpeg/Remotion replaced by deterministic stubs."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import numpy as np
import pytest

from movelyth.media import write_wav
from movelyth.pipeline import Studio
from tests.factories import layer


def make_studio(tmp_path, provider=None) -> Studio:
    config = Path(__file__).parents[1] / "movelyth.toml"
    text = config.read_text(encoding="utf-8")
    text = text.replace("long_seconds = 180", "long_seconds = 20").replace("short_seconds = 60", "short_seconds = 10")
    text = text.replace("long_min_seconds = 120", "long_min_seconds = 10").replace("long_max_seconds = 300", "long_max_seconds = 40")
    text = text.replace("short_min_seconds = 45", "short_min_seconds = 5").replace("short_max_seconds = 90", "short_max_seconds = 20")
    (tmp_path / "movelyth.toml").write_text(text, encoding="utf-8")
    return Studio(tmp_path, provider=provider)


def fake_render_run(command, *, cwd=None, timeout=600, log=None):
    if "render.mjs" in str(command[1]):
        spec = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        result = {}
        for cut in spec["cuts"]:
            out = Path(cut["output"])
            out.mkdir(parents=True, exist_ok=True)
            silent = out / "silent.mp4"
            silent.write_bytes(b"silent-video")
            cover = out / "cover.png"
            cover.write_bytes(b"png")
            stills = []
            for index, _scene in enumerate(cut["props"]["scenes"]):
                still = out / f"scene-{index + 1:02d}.jpg"
                still.write_bytes(b"jpg")
                stills.append(str(still))
            entry = {"video": str(silent), "cover": str(cover), "stills": stills,
                     "frames": sum(scene["frames"] for scene in cut["props"]["scenes"]),
                     "width": 1920 if cut["name"] == "long" else 1080,
                     "height": 1080 if cut["name"] == "long" else 1920, "fps": 30,
                     "fingerprint": "test", "hashes": {}}
            if spec.get("previewSeconds"):
                preview = out / "preview.mp4"
                preview.write_bytes(b"preview")
                entry["preview"] = str(preview)
            result[cut["name"]] = entry
        Path(spec["result"]).write_text(json.dumps(result), encoding="utf-8")
        return CompletedProcess(command, 0, "", "")
    Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
    Path(command[-1]).write_bytes(b"final-video")
    return CompletedProcess(command, 0, "", "")


def fake_prepare_cut(cut, config, cache, output, *, portrait):
    output.mkdir(parents=True, exist_ok=True)
    voice, mix = output / "narration.wav", output / "mix.wav"
    write_wav(voice, np.zeros(24000, dtype=np.float32))
    write_wav(mix, np.zeros((24000, 2), dtype=np.float32))
    seconds = float(config["short_seconds"] if portrait else config["long_seconds"])
    frames = max(1, round(seconds * config["fps"] / len(cut["scenes"])))
    scenes = []
    for raw in cut["scenes"]:
        scenes.append({**raw, "frames": frames,
                       "captions": [{"start": 0.2, "end": 1.0, "text": raw["narration"][:12]}],
                       "layers": raw.get("layers") or [layer()], "actions_resolved": [],
                       "caption_timing": "tts-word-boundaries", "layout_warnings": []})
    return {"title": cut["title"], "scenes": scenes, "frames": frames * len(scenes),
            "seconds": seconds, "mix": str(mix), "voice": str(voice),
            "style": cut.get("style", "tech")}, [voice, mix]


@pytest.fixture
def offline_pipeline(tmp_path, monkeypatch):
    def fake_assets(output):
        output.mkdir(parents=True, exist_ok=True)
        paths = []
        for rank in (1, 4, 12, 32):
            path = output / f"svd-{rank}.png"
            path.write_bytes(b"png")
            paths.append(path)
        return ["svd-1.png", "svd-4.png", "svd-12.png", "svd-32.png"], paths, {"1": {"mse": 0.1}}

    monkeypatch.setattr("movelyth.pipeline.prepare_cut", fake_prepare_cut)
    monkeypatch.setattr("movelyth.pipeline.image_layers", fake_assets)
    monkeypatch.setattr("movelyth.pipeline.run", fake_render_run)
    # The stub snapshot has to contain the claim excerpt: S1-04 verifies that the
    # excerpt really appears in the fetched text instead of trusting the model.
    monkeypatch.setattr("movelyth.sources.collect_sources", lambda sources, directory: [
        {"url": source["url"], "status": "retrieved", "content_sha256": "0" * 64,
         "retrieved_at": "2026-10-25T00:00:00+08:00", "title": source["label"],
         "excerpt": source["supports"] + " columns are images of basis vectors"} for source in sources])
    monkeypatch.setattr("movelyth.pipeline.verify_video", lambda *a, **k: {
        "passed": True, "checks": {"full_decode": True}, "duration": 60.0, "width": 1920, "height": 1080,
        "fps": 30.0, "mean_sample_motion": 1.0, "audio_listened": False, "asr_checked": False,
        "full_motion_aesthetic_review": False})
    def fake_mux(video, mix, output, log=None):
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"muxed")
        return {"target": {"integrated_lufs": -14.0}, "measurement": {"status": "measured"}, "mode": "linear"}

    monkeypatch.setattr("movelyth.pipeline.mux_with_loudness", fake_mux)
    monkeypatch.setattr("movelyth.pipeline.motion_report",
                        lambda video, scenes, fps, portrait=False: {
                            "status": "ok", "sample_fps": 4, "grid": [8, 6], "frames": 240,
                            "still_share_by_scene": {}, "frozen_scenes": [], "full_frame_runs": []})
    def fake_stills(video, cut, fps, directory, portrait):
        directory.mkdir(parents=True, exist_ok=True)
        result = []
        for index in range(len(cut["scenes"])):
            path = directory / f"scene-{index}.jpg"
            path.write_bytes(b"jpg")
            result.append(str(path))
        return result

    monkeypatch.setattr("movelyth.pipeline.encoded_stills", fake_stills)
    monkeypatch.setattr("movelyth.pipeline.contact_sheet", lambda stills, output, portrait: output.write_bytes(b"jpg"))
    monkeypatch.setattr("movelyth.pipeline.audio_qc", lambda voice, mix, script, config: {
        "asr": {"status": "disabled"}, "transcript_check": {"status": "not-run"},
        "silence": {"status": "ok"}, "ducking": {"status": "ok"}, "listened_by_human": False})
    return tmp_path


