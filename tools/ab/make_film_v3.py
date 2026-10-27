"""Derive a V3-directed copy of the approved VID-000004 script.

The narration, data and layers are unchanged.  Only direction metadata is added:
chapter / role / takeaway / metric / hero, plus explicit chart annotations and one
highlight range.  This isolates what the V3 renderer does with the new fields.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
film = json.loads((ROOT / "workspace/ab/film-004-v2.json").read_text(encoding="utf-8"))

DIRECTION = {
    "l1": dict(chapter="没接住", role="hook", metric="0",
               takeaway="预测线还停在零，先看清差在哪", hero="samples",
               cues=[{"at": "start", "kind": "impact", "gain": 0.4}]),
    "l2": dict(chapter="记账", role="mechanism", metric="5",
               takeaway="先把偏差平方，再求平均", hero="account",
               cues=[]),
    "l3": dict(chapter="换坐标纸", role="mechanism", metric="5",
               takeaway="当前点在左坡，损失是五", hero="bowl",
               cues=[]),
    "l4": dict(chapter="迈步", role="mechanism", metric="1",
               takeaway="新参数 = 旧参数 − 学习率 × 梯度", hero="update",
               cues=[]),
    "l5": dict(chapter="重算", role="mechanism", metric="0.31",
               takeaway="每步重新算梯度，损失继续下降", hero="trajectory",
               cues=[]),
    "l6": dict(chapter="跨过头", role="turn", metric="25.3",
               takeaway="学习率太大，损失反而上升", hero="overshoot",
               cues=[{"at": "narration:从零跳到五", "kind": "riser", "gain": 0.34}]),
    "l7": dict(chapter="多参数", role="example", metric="方向",
               takeaway="梯度把所有参数的方向合在一起", hero="direction",
               cues=[]),
    "l8": dict(chapter="波动", role="example", metric="4",
               takeaway="单次抽样可能偏，平均方向仍可靠", hero="sampling",
               cues=[]),
    "l9": dict(chapter="回到直线", role="conclusion", metric="闭环",
               takeaway="损失给目标，梯度给方向，学习率给步幅", hero="loop",
               cues=[{"at": "narration:不断重算", "kind": "chime", "gain": 0.28}]),
    # Portrait short: a different edit of the same story.
    "s1": dict(chapter="没接住", role="hook", metric="0",
               takeaway="预测线贴着横轴，差在哪", hero="prediction", cues=[]),
    "s2": dict(chapter="看斜率", role="mechanism", metric="负",
               takeaway="斜率告诉参数该往哪边调", hero="bowl", cues=[]),
    "s3": dict(chapter="步子", role="turn", metric="大小",
               takeaway="步子太大，损失反而上升", hero="small", cues=[]),
    "s4": dict(chapter="重算", role="conclusion", metric="闭环",
               takeaway="每步重新判断，才逐步靠近", hero="loop", cues=[]),
}

# Explicit chart annotations: x is a real sample, text is the judgement.
ANNOTATIONS = {
    ("l1", "samples"): [{"x": 2.0, "text": "4 · 目标"}],
    ("l5", "trajectory"): [{"x": 3.0, "text": "0.08 · 接近零"}],
    ("l6", "overshoot"): [{"x": 2.0, "text": "25.3 · 越走越远"}],
}
HIGHLIGHT = {("l6", "overshoot"): [1.0, 2.0]}

for cut in ("long", "short"):
    for scene in film[cut]["scenes"]:
        direction = DIRECTION.get(scene["id"])
        if not direction:
            continue
        scene.update({key: value for key, value in direction.items()})
        for layer in scene["layers"]:
            layer.setdefault("annotations", [])
            layer.setdefault("highlight", [])
            key = (scene["id"], layer["id"])
            if key in ANNOTATIONS:
                layer["annotations"] = ANNOTATIONS[key]
            if key in HIGHLIGHT:
                layer["highlight"] = HIGHLIGHT[key]
        # The portrait edit draws the loss samples as a scatter; the narration
        # calls it a curve, so V3 connects the samples.
        if scene["id"] == "s2":
            for layer in scene["layers"]:
                if layer["id"] == "bowl":
                    layer["chart"] = "line"

out = ROOT / "workspace/ab/film-004-v3.json"
out.write_text(json.dumps(film, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", out)
