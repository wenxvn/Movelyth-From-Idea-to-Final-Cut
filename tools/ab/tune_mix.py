"""Tune the bed/cue balance offline against the real narration of VID-000007.

Runs the same measurement as audioqc.ducking_report, so a change can be evaluated
in seconds instead of re-rendering a five-minute film.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
import movelyth.media as media  # noqa: E402

job = Path("workspace/VID-000007/audio/long")
voice = media.read_wav(job / "narration.wav")
timelines = __import__("json").loads(Path("workspace/VID-000007/timelines.json").read_text(encoding="utf-8"))
cut = timelines["long"]
starts, offset = [], 0.0
for scene in cut["scenes"]:
    starts.append(offset)
    offset += scene["frames"] / 30.0
cues = [{"at": c["at"], "kind": c["kind"], "gain": c["gain"]} for c in cut.get("cues", [])]

mix = media.soundtrack(voice, starts, "tech", cues=cues)
wet = mix.mean(axis=1)
window = media.SAMPLE_RATE // 20
frames = min(len(voice), len(wet)) // window
v = np.sqrt(np.mean(voice[:frames * window].reshape(frames, window) ** 2, axis=1))
m = np.sqrt(np.mean(wet[:frames * window].reshape(frames, window) ** 2, axis=1))
speech = v > 0.02
ratio = m[speech] / np.maximum(v[speech], 1e-6)
print("max", round(float(ratio.max()), 3), "p99", round(float(np.percentile(ratio, 99)), 3),
      "median", round(float(np.median(ratio)), 3))
print("bed rms", round(float(np.sqrt(np.mean((wet - voice * 0.92) ** 2))), 4),
      "voice rms", round(float(np.sqrt(np.mean(voice ** 2))), 4))
