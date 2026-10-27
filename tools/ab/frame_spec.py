"""Build a frame-list spec so transitions can be inspected frame by frame."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
job = ROOT / "workspace" / sys.argv[1]
out = (ROOT / sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
cut = sys.argv[3] if len(sys.argv) > 3 else "long"
frames = [int(value) for value in sys.argv[4].split(",")]

timelines = json.loads((job / "timelines.json").read_text(encoding="utf-8"))
film = json.loads((job / "film.json").read_text(encoding="utf-8"))
research = json.loads((job / "research.json").read_text(encoding="utf-8"))
assets = sorted(p.name for p in (job / "assets").glob("*") if p.suffix.lower() in {".png", ".jpg"})
props = {
    "title": film[cut]["title"], "episode": f"TR-{sys.argv[1]}", "fps": 30,
    "scenes": timelines[cut]["scenes"], "sources": research["sources"], "layers": assets,
    "cover": False, "coverCaption": film[cut].get("cover_caption", ""),
    "style": film[cut].get("style", "tech"), "schema_version": 1,
}
spec = {"browser": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "assets": str(job / "assets"), "props": props,
        "composition": "Landscape" if cut == "long" else "Portrait",
        "frames": frames, "output": str(out)}
(out / "frames.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
print(out / "frames.json")
