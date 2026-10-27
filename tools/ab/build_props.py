"""Scratch A/B helper: render stills from an existing timeline without re-running the pipeline.

Not part of the product.  It exists so a renderer change can be compared against the
same approved script and the same TTS audio (workspace/ is git-ignored).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
job = ROOT / "workspace" / sys.argv[1]
out = (ROOT / sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
cut = sys.argv[3] if len(sys.argv) > 3 else "long"

timelines = json.loads((job / "timelines.json").read_text(encoding="utf-8"))
film = json.loads((job / "film.json").read_text(encoding="utf-8"))
research = json.loads((job / "research.json").read_text(encoding="utf-8"))
assets = sorted(p.name for p in (job / "assets").glob("*") if p.suffix.lower() in {".png", ".jpg"})

props = {
    "title": film[cut]["title"],
    "episode": f"AB-{sys.argv[1]}",
    "fps": 30,
    "scenes": timelines[cut]["scenes"],
    "sources": research["sources"],
    "layers": assets,
    "cover": False,
    "coverCaption": film[cut].get("cover_caption", ""),
    "style": film[cut].get("style", "tech"),
    "schema_version": 1,
}
spec = {
    "cuts": [{"name": cut, "composition": "Landscape" if cut == "long" else "Portrait",
              "props": props, "output": str(out / cut)}],
    "assets": str(job / "assets"),
    "browser": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "concurrency": 1,
    "result": str(out / "result.json"),
    "version": "ab-stills",
    "stillsOnly": True,
    "scale": 1,
}
spec_path = out / "spec.json"
spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
print(spec_path)
