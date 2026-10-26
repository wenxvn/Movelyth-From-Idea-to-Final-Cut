from movelyth.media import ffmpeg
from movelyth.quality import (
    encoded_stills,
    loudness_filter,
    measure_loudness,
    motion_report,
    mux_with_loudness,
    verify_video,
)
from movelyth.util import run


def create_media(path, *, sound):
    run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000" if sound else
         "anullsrc=sample_rate=48000:channel_layout=stereo", "-t", "2", "-c:v", "libx264",
         "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], timeout=30)


def test_real_decoded_file_passes_and_wrong_dimensions_fail(tmp_path):
    path = tmp_path / "tone.mp4"
    create_media(path, sound=True)
    report = verify_video(path, width=320, height=180, fps=10, seconds=2)
    assert report["passed"], report
    wrong = verify_video(path, width=1080, height=1920, fps=10, seconds=2)
    assert not wrong["passed"] and not wrong["checks"]["dimensions"]
    approximate = {"target_seconds": 1.8, "minimum_seconds": 1.5, "maximum_seconds": 2.5,
                   "target_is_approximate": True}
    allowed = verify_video(path, width=320, height=180, fps=10, seconds=2, policy=approximate)
    assert allowed["passed"] and allowed["checks"]["requested_duration_range"]
    forbidden = verify_video(path, width=320, height=180, fps=10, seconds=2,
                              policy={**approximate, "maximum_seconds": 1.9})
    assert not forbidden["passed"] and not forbidden["checks"]["requested_duration_range"]


def test_silent_audio_stream_does_not_pass_as_sound(tmp_path):
    path = tmp_path / "silent.mp4"
    create_media(path, sound=False)
    report = verify_video(path, width=320, height=180, fps=10, seconds=2)
    assert not report["passed"] and not report["checks"]["audible"]


def test_review_frames_are_extracted_from_encoded_video(tmp_path):
    from PIL import Image, ImageChops

    path = tmp_path / "actual.mp4"
    create_media(path, sound=True)
    frames = encoded_stills(path, {"scenes": [{"frames": 10}, {"frames": 10}]}, 10,
                             tmp_path / "frames", portrait=False)
    with Image.open(frames[0]) as first, Image.open(frames[1]) as second:
        assert first.size == second.size == (960, 540)
        assert ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox() is not None


def test_review_frames_are_sampled_after_scene_actions_finish():
    """A still taken mid-animation can show a deliberately half-built scene."""
    from movelyth.quality import review_frame_fraction

    assert review_frame_fraction({}) == 0.55
    assert review_frame_fraction({"actions_resolved": [{"from": 0.1, "to": 0.4}]}) == 0.55
    assert review_frame_fraction({"actions_resolved": [{"from": 0.76, "to": 1.0}]}) == 0.96
    late = review_frame_fraction({"actions_resolved": [{"from": 0.2, "to": 0.8}]})
    assert 0.8 < late <= 0.96


def test_two_pass_loudness_reaches_the_platform_target(tmp_path):
    video = tmp_path / "render.mp4"
    create_media(video, sound=True)
    mix = tmp_path / "mix.wav"
    run([ffmpeg(), "-y", "-v", "error", "-i", str(video), "-vn", "-af", "volume=-20dB",
         "-ac", "2", "-ar", "48000", str(mix)], timeout=60)
    output = tmp_path / "final.mp4"
    report = mux_with_loudness(video, mix, output)
    assert report["mode"] == "linear"
    checked = verify_video(output, width=320, height=180, fps=10, seconds=2, loudness_target=-14.0)
    assert checked["checks"]["loudness_matches_target"], checked["loudness"]
    assert checked["checks"]["true_peak_below_ceiling"], checked["loudness"]


def test_a_silent_mix_falls_back_to_dynamic_normalisation(tmp_path):
    mix = tmp_path / "silent.wav"
    run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi",
         "-i", "anullsrc=sample_rate=48000:channel_layout=stereo", "-t", "1", str(mix)], timeout=30)
    measured = measure_loudness(mix)
    assert "measured_I" not in loudness_filter(measured)
    assert "linear=true" not in loudness_filter(measured)


def test_motion_report_finds_a_frozen_scene(tmp_path):
    frozen = tmp_path / "frozen.mp4"
    run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=#122531:s=320x180:r=10:d=6",
         "-vf", "drawbox=x=100:y=60:w=80:h=60:color=white:t=fill", "-c:v", "libx264",
         "-threads", "1", "-pix_fmt", "yuv420p", str(frozen)], timeout=60)
    report = motion_report(frozen, [{"id": "s1", "frames": 60}], 10, portrait=False)
    assert report["still_share_by_scene"]["s1"] == 1.0
    assert report["frozen_scenes"][0]["scene"] == "s1"
    assert report["full_frame_runs"] == []


def test_motion_report_flags_a_whole_frame_drift(tmp_path):
    moving = tmp_path / "moving.mp4"
    run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10:duration=6",
         "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(moving)], timeout=60)
    report = motion_report(moving, [{"id": "s1", "frames": 60}], 10, portrait=False)
    assert report["status"] == "review"
    assert report["full_frame_runs"]
    assert report["still_share_by_scene"]["s1"] < 0.2
