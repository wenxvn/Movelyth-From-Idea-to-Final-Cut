"""One project clock: seconds → frames → samples, with the rounding defined once.

Every stage used to round for itself (``math.ceil(seconds * fps)`` in media.py, a
different expression in scenedsl, ``round()`` in the renderer).  A few milliseconds
per scene is invisible; twenty scenes of it is a visible drift between the audio and
the picture.  These helpers are the only place rounding happens, and each scene owns
a half-open sample range ``[start_sample, end_sample)`` so consecutive scenes never
share or skip a sample.
"""
from __future__ import annotations

import math

DEFAULT_FPS = 30
EPSILON = 1e-9


def seconds_to_frames(seconds: float, fps: int = DEFAULT_FPS) -> int:
    """Smallest frame count that still covers ``seconds`` (a scene never cuts audio)."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("时长必须是非负有限数")
    # 1e-4 frame ≈ 3 µs: absorbs float noise from a product of seconds and fps without
    # hiding a real sub-frame rounding-up (a scene must cover all of its audio).
    return max(1, math.ceil(seconds * fps - 1e-4))


def frames_to_seconds(frames: int, fps: int = DEFAULT_FPS) -> float:
    if frames < 0:
        raise ValueError("帧数必须是非负整数")
    return frames / fps


def frames_to_samples(frames: int, fps: int = DEFAULT_FPS, sample_rate: int = 24000) -> int:
    """Samples for a whole number of frames; the scene boundary is a frame boundary."""
    return round(frames / fps * sample_rate)


def seconds_to_samples(seconds: float, sample_rate: int = 24000) -> int:
    return round(seconds * sample_rate)


def samples_to_seconds(samples: int, sample_rate: int = 24000) -> float:
    return samples / sample_rate


def scene_spans(scene_frames: list[int], *, fps: int = DEFAULT_FPS,
                sample_rate: int = 24000) -> list[dict]:
    """Contiguous sample ranges for consecutive scenes, plus their start times.

    ``sum(span['samples']) == spans[-1]['end_sample']`` by construction, so the cut's
    total sample count is exactly the sum of its scenes and no scene can drift.
    """
    spans, cursor = [], 0
    for index, frames in enumerate(scene_frames):
        samples = frames_to_samples(frames, fps, sample_rate)
        spans.append({
            "scene_index": index,
            "frames": frames,
            "samples": samples,
            "start_sample": cursor,
            "end_sample": cursor + samples,
            "start_seconds": samples_to_seconds(cursor, sample_rate),
            "end_seconds": samples_to_seconds(cursor + samples, sample_rate),
        })
        cursor += samples
    return spans


def frame_at(seconds: float, fps: int = DEFAULT_FPS) -> int:
    """Frame index containing ``seconds`` (floor), for event → frame mapping."""
    return max(0, math.floor(seconds * fps + EPSILON))


def sample_at(seconds: float, sample_rate: int = 24000) -> int:
    return max(0, round(seconds * sample_rate))
