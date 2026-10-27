"""Same-scene, 6 s apart frame difference: does the picture actually keep moving?"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ff = r"C:\Users\10556\AppData\Local\Programs\Python\Python311\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
out = Path(r"C:\Users\10556\AppData\Local\Temp\opencode\diffcheck")
out.mkdir(parents=True, exist_ok=True)

CASES = [
    ("V1", r"delivery/待上传/VID-000004_梯度下降为什么能让模型逐步减少错误？/r001/VID-000004_B站_横版.mp4", (3, 9)),
    ("V2", r"delivery-ab/待上传/VID-000014_梯度下降为什么能让模型逐步减少错误？/r010/VID-000014_B站_横版.mp4", (3, 9)),
]


def grab(video: str, seconds: float, tag: str) -> np.ndarray:
    path = out / f"{tag}.png"
    subprocess.run([ff, "-y", "-v", "error", "-ss", f"{seconds}", "-i", video, "-frames:v", "1",
                    str(path)], check=True)
    return np.asarray(Image.open(path).convert("L")).astype(np.float32)


for label, video, (a, b) in CASES:
    first = grab(video, a, f"{label}-{a}")
    second = grab(video, b, f"{label}-{b}")
    diff = np.abs(first[0:900, :] - second[0:900, :])
    print(f"{label}: mean |diff| between {a}s and {b}s = {diff.mean():.3f}, "
          f"pixels changed >4 = {(diff > 4).mean() * 100:.2f}%")