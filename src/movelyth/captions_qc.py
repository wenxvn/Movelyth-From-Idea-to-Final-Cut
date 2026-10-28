"""Caption and on-screen-text quality: reading speed, lines, width and collisions.

Captions, the embedded subtitle track and the SRT are generated from one cue list, so
this module checks that list rather than a copy of it.  Thresholds are per target
orientation and are calibrated for phone viewing; they are project settings, not
platform rules.
"""
from __future__ import annotations

from .fonts import font_report, text_width_ratio
from .scenedsl import caption_band, regions

# Characters per second a viewer can comfortably read, by cut.  Chinese captions are
# denser than Latin ones; 8–9 cps is the range used for phone viewing.
READING_SPEED = {"long": 9.0, "short": 8.0}
MIN_SECONDS = {"long": 1.0, "short": 0.9}
MAX_LINES = 2
MAX_WIDTH_RATIO = 0.92
CAPTION_SIZE = {"long": 66, "short": 62}


def cue_report(scene: dict, cut: str, *, orientation: str) -> dict:
    """Check every caption page of one scene."""
    problems, warnings = [], []
    speed = READING_SPEED.get(cut, 9.0)
    minimum = MIN_SECONDS.get(cut, 1.0)
    size = CAPTION_SIZE.get(cut, 66)
    band = caption_band(orientation)
    pages = scene.get("captions") or []
    previous_end = 0.0
    for index, page in enumerate(pages):
        text = str(page.get("text") or "")
        seconds = max(1e-3, float(page["end"]) - float(page["start"]))
        where = f"镜头 {scene.get('id')} 字幕第 {index + 1} 页"
        if not text.strip():
            problems.append(f"{where}是空白页")
            continue
        rate = len(text) / seconds
        if rate > speed:
            problems.append(f"{where} {rate:.1f} 字/秒，超过 {speed} 字/秒上限")
        if seconds < minimum:
            problems.append(f"{where}只显示 {seconds:.2f}s，短于 {minimum}s")
        if float(page["start"]) < previous_end - 1e-6:
            problems.append(f"{where}与上一页时间交叠")
        previous_end = float(page["end"])
        report = font_report(text, style="body", size=size)
        if report["missing"]:
            problems.append(f"{where}缺字：{''.join(report['missing'][:5])}")
        if report["width"] is None:
            warnings.append(f"{where}的字体不可用，宽度未验证")
        else:
            ratio = round(report["width"] / max(1, band["w"]), 4)
            if ratio > MAX_WIDTH_RATIO:
                problems.append(f"{where}宽度占 {ratio:.0%}，超出安全区")
        lines = text.count("\n") + 1
        if lines > MAX_LINES:
            problems.append(f"{where}有 {lines} 行，超过 {MAX_LINES} 行")
    return {"problems": problems, "warnings": warnings, "pages": len(pages)}


def collision_report(scene: dict, *, orientation: str) -> list[str]:
    """Captions and the footer must not sit under a chart's own labels.

    The chart draws its axis labels and annotations inside the main region, so the
    check is geometric: the caption band and the footer band must not overlap any
    content region that carries text.
    """
    problems = []
    boxes = regions(orientation, scene.get("layout") or "diagram")
    band = caption_band(orientation)
    footer_top = band["y"] + band["h"]
    for layer in scene.get("layers") or []:
        if layer.get("type") not in {"chart", "diagram", "timeline", "text", "math", "image"}:
            continue
        box = boxes.get(layer.get("region") or "main")
        if not box:
            continue
        overlap = (box["y"] < band["y"] + band["h"] and band["y"] < box["y"] + box["h"]
                   and box["x"] < band["x"] + band["w"] and band["x"] < box["x"] + box["w"])
        if overlap:
            problems.append(f"镜头 {scene.get('id')} 的 {layer.get('id')} 区域与字幕带重叠")
        if box["y"] + box["h"] > footer_top + 4 and layer.get("region") != "full":
            problems.append(f"镜头 {scene.get('id')} 的 {layer.get('id')} 越过了页脚线")
    return problems


def text_layer_report(scene: dict, *, orientation: str, cut: str) -> dict:
    """Measured width of on-screen text, so shrinking is reported instead of guessed."""
    problems, warnings = [], []
    boxes = regions(orientation, scene.get("layout") or "diagram")
    for layer in scene.get("layers") or []:
        text = str(layer.get("text") or "").strip()
        if not text or layer.get("type") not in {"text", "math"}:
            continue
        box = boxes.get(layer.get("region") or "main") or boxes["main"]
        size = 46 if layer.get("type") == "text" else 44
        ratio = text_width_ratio(text, box["w"], size=size)
        if ratio is None:
            warnings.append(f"镜头 {scene.get('id')} 的 {layer.get('id')} 字体不可用，宽度未验证")
            continue
        if ratio > 1.0:
            problems.append(f"镜头 {scene.get('id')} 的 {layer.get('id')} 单行宽度占 {ratio:.0%}，会换行或缩小")
        report = font_report(text, style="body", size=size)
        if report["missing"]:
            problems.append(f"镜头 {scene.get('id')} 的 {layer.get('id')} 缺字：{''.join(report['missing'][:5])}")
    return {"problems": problems, "warnings": warnings}


def srt_matches_cues(cut: dict, srt_text: str) -> dict:
    """The delivered SRT must carry exactly the cue text the viewer sees."""
    from .textfit import normalize_for_compare  # local import: keeps this module cheap

    cue_text = [str(page.get("text") or "") for scene in cut.get("scenes") or []
                for page in scene.get("captions") or []]
    srt_lines = [line.strip() for line in srt_text.splitlines()
                 if line.strip() and not line.strip().isdigit() and "-->" not in line]
    expected = [normalize_for_compare(text) for text in cue_text]
    actual = [normalize_for_compare(line) for line in srt_lines]
    missing = [text for text in expected if text not in actual]
    return {"passed": not missing and len(expected) == len(actual),
            "cues": len(expected), "srt_lines": len(actual), "missing": missing[:5]}
