"""Prepare an A/B copy of the approved VID-000004 script.

Only two node positions are moved: the approved script has two diagram nodes
overlapping by 65 units, which today's contract rejects (the label of one covers
the other).  Nothing else about the script changes, so a comparison against the
V1 delivery isolates the renderer, the transitions and the sound design.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
film = json.loads((root / "workspace/VID-000004/film.json").read_text(encoding="utf-8"))
for cut in ("long", "short"):
    for scene in film[cut]["scenes"]:
        for layer in scene["layers"]:
            if layer["type"] != "diagram":
                continue
            nodes = layer["nodes"]
            if len(nodes) != 3:
                continue
            nodes[0]["x"], nodes[0]["y"] = 260.0, 190.0
            nodes[1]["x"], nodes[1]["y"] = 720.0, 190.0
            nodes[2]["x"], nodes[2]["y"] = 500.0, 470.0
            print(cut, scene["id"], "re-laid out", [n["id"] for n in nodes])

# V2 direction fields: the approved script predates them, so set them explicitly to
# the values a V2 director would choose for this material.
transitions = ["fade", "wipe", "slide", "zoom", "fade", "dip", "wipe", "slide", "fade"]
for cut, plan in (("long", transitions), ("short", transitions)):
    for index, scene in enumerate(film[cut]["scenes"]):
        scene["transition"] = plan[index % len(plan)]
        scene["camera"] = "push" if index % 3 == 0 else ("pan_right" if index % 3 == 1 else "pull")
        if not scene.get("cues"):
            scene["cues"] = [{"at": "start", "kind": "whoosh" if index else "impact", "gain": 0.5}]
        if not scene.get("emphasis"):
            scene["emphasis"] = []

out = root / "workspace/ab/film-004-v2.json"
out.write_text(json.dumps(film, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", out)
