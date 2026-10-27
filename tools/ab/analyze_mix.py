"""Locate where the mix exceeds the voice, so a loud cue is not guessed at."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from movelyth.audioqc import _read_mono  # noqa: E402

job = Path("workspace/VID-000007/audio/long")
voice = _read_mono(job / "narration.wav")
mix = _read_mono(job / "mix.wav")
count = min(len(voice), len(mix))
window = 24000 // 20
frames = count // window
v = np.sqrt(np.mean(voice[:frames * window].reshape(frames, window) ** 2, axis=1))
m = np.sqrt(np.mean(mix[:frames * window].reshape(frames, window) ** 2, axis=1))
ratio = m / np.maximum(v, 1e-6)
speech = v > 0.02
order = np.flatnonzero(speech)[np.argsort(ratio[speech])[::-1][:10]]
print("top spikes (time s, ratio, voice rms, mix rms):")
for index in order:
    print(f"  {index * window / 24000:7.2f}s  {ratio[index]:6.2f}  {v[index]:.3f}  {m[index]:.3f}")
print("voice rms percentiles", np.percentile(v[speech], [10, 50, 90]).round(3))
print("mix/voice median", round(float(np.median(ratio[speech])), 3))
