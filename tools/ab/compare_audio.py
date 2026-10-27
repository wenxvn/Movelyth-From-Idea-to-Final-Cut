"""Compare narration pacing and pauses between the V1 delivery and the V2 rebuild."""
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
ff = r"C:\Users\10556\AppData\Local\Programs\Python\Python311\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"


def load(path: Path):
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1:
            raise SystemExit("need mono")
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768


def stats(audio: np.ndarray, label: str):
    sr = 24000
    window = int(0.02 * sr)
    frames = len(audio) // window
    rms = np.sqrt(np.mean(audio[:frames * window].reshape(frames, window) ** 2, axis=1))
    speech = rms > 0.02
    # Run-length of silence inside speech (internal pauses).
    pauses, run = [], 0
    for value in speech:
        if value:
            if run:
                pauses.append(run * 0.02)
            run = 0
        else:
            run += 1
    if run:
        pauses.append(run * 0.02)
    inner = [p for p in pauses[1:-1] if p >= 0.12]
    sentence_rms = []
    start = None
    for index, value in enumerate(speech):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start > 12:
                sentence_rms.append(float(np.sqrt(np.mean(rms[start:index] ** 2))))
            start = None
    print(f"{label}: {len(audio)/sr:6.1f}s  speech {speech.mean()*100:4.1f}%  "
          f"pauses>=0.12s {len(inner):3d} (median {np.median(inner) if inner else 0:.2f}s)  "
          f"loudest/quietest speech block {max(sentence_rms)/min(sentence_rms) if sentence_rms else 0:.1f}x")


v1 = Path(r"delivery/待上传/VID-000004_梯度下降为什么能让模型逐步减少错误？/r001/原声_B站_横版.mp3")
v2 = Path(r"delivery-ab/待上传/VID-000014_梯度下降为什么能让模型逐步减少错误？/r010/原声_B站_横版.mp3")
for path, label in ((v1, "V1 (VID-000004)"), (v2, "V2 (VID-000014)")):
    wav = path.with_suffix(".compare.wav")
    subprocess.run([ff, "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "24000",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    stats(load(wav), label)
    wav.unlink(missing_ok=True)