"""Lightweight local run metrics: one CSV row per stage, no monitoring service."""
from __future__ import annotations

import csv
import time
from pathlib import Path

from .util import now

HEADER = ["recorded_at", "episode", "stage", "state", "seconds", "cache", "output_bytes", "detail"]


class Metrics:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, episode: int, stage: str, state: str, *, seconds: float, cache: bool,
               outputs: list[Path] | None = None, detail: str = "") -> dict:
        size = 0
        for output in outputs or []:
            try:
                size += output.stat().st_size
            except OSError:
                continue
        row = {"recorded_at": now(), "episode": f"VID-{episode:06d}", "stage": stage,
               "state": state, "seconds": round(seconds, 2), "cache": "hit" if cache else "miss",
               "output_bytes": size, "detail": detail[:200]}
        new = not self.path.exists()
        with self.path.open("a", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADER)
            if new:
                writer.writeheader()
            writer.writerow(row)
        return row

    def timer(self):
        return time.perf_counter()
