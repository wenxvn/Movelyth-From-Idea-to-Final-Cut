from movelyth.media import ffmpeg
from movelyth.quality import encoded_stills, verify_video
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
