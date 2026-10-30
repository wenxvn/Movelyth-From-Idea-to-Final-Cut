"""Caption and on-screen-text quality: reading speed, lines, width and collisions.

Captions, the embedded subtitle track and the SRT are generated from one cue list, so
this module checks that list rather than a copy of it.  Thresholds are per target
orientation and are calibrated for phone viewing; they are project settings, not
platform rules.
"""
from __future__ import annotations

import math

from .fonts import font_report, text_width_ratio
from .scenedsl import caption_band, regions

# Characters per second a viewer can comfortably read, by cut.  Chinese captions are
# denser than Latin ones; 8–9 cps is the range used for phone viewing.
READING_SPEED = {"long": 9.0, "short": 8.0}
MIN_SECONDS = {"long": 1.0, "short": 0.9}
MAX_LINES = 2
MAX_WIDTH_RATIO = 0.92
CAPTION_SIZE = {"long": 66, "short": 62}
MOBILE_REFERENCE_WIDTH = 390
MOBILE_LANDSCAPE_ROTATED_WIDTH = 844
MOBILE_MIN_TEXT_PX = 12.0  # internal review heuristic, not a platform requirement

_TYPE_TOKENS = {
    "tech": {"body": 46, "heading": 112},
    "minimal": {"body": 44, "heading": 104},
    "documentary": {"body": 44, "heading": 108},
}
_REGION_FACTORS = {"main": 1.0, "bottom": 0.92, "top": 0.82,
                   "side": 0.86, "annotation": 0.86, "full": 0.9}


def _round_js(value: float) -> int:
    return math.floor(value + 0.5)


def _char_em(character: str) -> float:
    code = ord(character)
    if code < 0x2000:
        return 0.56
    if code >= 0xFF00 or code >= 0x3000:
        return 1.0
    return 0.62


def _fit_estimated_font(text: str, box: dict, base: int, minimum: int,
                        *, single_line: bool = False, line_height: float = 1.34) -> int:
    """Mirror TextLayer.fitSize's box and character-width rules for a display estimate."""
    lines = text.split("\n")

    def fits(size: int) -> bool:
        if single_line and len(lines) == 1:
            width = sum(_char_em(character) * size for character in lines[0])
            return width <= box["w"] and size * line_height <= box["h"]
        rows = 0
        for line in lines:
            used = 0.0
            count = 1
            for character in line:
                width = _char_em(character) * size
                if used + width > box["w"] and used > 0:
                    count += 1
                    used = width
                else:
                    used += width
            rows += count
        return rows * size * line_height <= box["h"]

    size = base
    while size > minimum:
        if fits(size):
            return size
        size -= 2
    return minimum


def _text_layer_size(layer: dict, box: dict, *, orientation: str, style: str) -> int:
    tokens = _TYPE_TOKENS.get(style, _TYPE_TOKENS["tech"])
    factor = _REGION_FACTORS.get(layer.get("region", "main"), 0.9)
    emphasis = max(0, min(2, int(layer.get("emphasis", 1)) - 1))
    vertical = orientation == "portrait"
    text = str(layer.get("text") or "")
    if layer.get("type") == "math":
        base = _round_js((round(tokens["heading"] * 0.52) + emphasis * 16)
                         * factor * (1.06 if vertical else 1))
        inner = {"w": max(80, box["w"] - _round_js(base * 0.62)),
                 "h": max(40, box["h"] - _round_js(base * 0.42))}
        return _fit_estimated_font(text, inner, base, 38, single_line="\n" not in text)
    base = _round_js((tokens["body"] + emphasis * 8) * factor * (1.08 if vertical else 1))
    size = _fit_estimated_font(text, box, base, 28)
    if layer.get("region") == "top":
        return _round_js(size * 0.82)
    if box["h"] < 60:
        strip_base = min(24, math.floor(box["h"] / 1.2))
        return _fit_estimated_font(text, box, strip_base, 14, line_height=1.1)
    return size


def _diagram_label_sizes(layer: dict, box: dict) -> list[float]:
    nodes = layer.get("nodes") or []
    if not nodes:
        return []
    widths = {node["id"]: max(210, len(node["label"]) * 46 + 70) for node in nodes}
    min_x = min(node["x"] - widths[node["id"]] / 2 for node in nodes) - 48
    max_x = max(node["x"] + widths[node["id"]] / 2 for node in nodes) + 48
    min_y = min(node["y"] for node in nodes) - 104
    max_y = max(node["y"] for node in nodes) + 104
    box_width, box_height = max_x - min_x, max_y - min_y
    steps = [step for step in layer.get("steps") or []
             if not any(node["label"] in step or step in node["label"] for node in nodes)]
    content_height = box_height + (len(steps) * 52 + 26 if steps else 0)
    aspect = max(0.6, box["w"] / max(1, box["h"]))
    content_aspect = box_width / max(1, content_height)
    view_height = box_width / aspect if content_aspect > aspect else content_height
    scale = box["h"] / max(1, view_height)
    return [44 * scale, *([30 * scale] if steps else [])]


def mobile_readability_report(scene: dict, *, cut: str, orientation: str,
                              style: str = "tech") -> dict:
    """Estimate rendered text size at a representative phone width.

    This is a static layout heuristic. It does not claim that a viewer understood
    the scene or that every browser rasterizes fonts identically.
    """
    boxes = regions(orientation, scene.get("layout") or "diagram")
    if orientation == "portrait":
        profile = "portrait-feed-390px"
        scale = MOBILE_REFERENCE_WIDTH / 1080
    else:
        profile = "landscape-rotated-844px"
        scale = MOBILE_LANDSCAPE_ROTATED_WIDTH / 1920

    samples = []
    pages = scene.get("captions") or []
    if pages:
        samples.append({"kind": "caption", "px": CAPTION_SIZE.get(cut, 66) * scale})
    for layer in scene.get("layers") or []:
        layer_type = layer.get("type")
        box = boxes.get(layer.get("region") or "main") or boxes["main"]
        if layer_type in {"text", "math"}:
            size = _text_layer_size(layer, box, orientation=orientation, style=style)
            samples.append({"kind": layer_type, "id": layer.get("id"), "px": size * scale})
        elif layer_type == "chart":
            # ChartLayer's SVG font units are scaled by the containing region.
            aspect = max(0.7, min(3.4, box["w"] / max(1, box["h"])))
            canvas_width = _round_js(640 * aspect)
            unit = canvas_width / 1000
            chart_px = _round_js(15 * unit) * box["h"] / 640
            samples.append({"kind": "chart-label", "id": layer.get("id"), "px": chart_px * scale})
        elif layer_type == "diagram":
            sizes = _diagram_label_sizes(layer, box)
            if sizes:
                samples.append({"kind": "diagram-label", "id": layer.get("id"),
                                "px": min(sizes) * scale})

    small = [item for item in samples if float(item["px"]) < MOBILE_MIN_TEXT_PX]
    warnings = [f"镜头 {scene.get('id')} 的 {item['kind']} {item.get('id', '')} 在 {profile} 估算"
                f"约 {float(item['px']):.1f}px，低于项目 {MOBILE_MIN_TEXT_PX:.0f}px 复核线"
                for item in small]
    if not pages:
        warnings.append(f"镜头 {scene.get('id')} 没有字幕页，静音阅读线索有限")
    return {"profile": profile, "scale": round(scale, 4), "samples": samples,
            "small_text": small, "warnings": warnings,
            "method": "CSS/SVG 字号与版式盒估算；非平台规范、非实际理解评测"}


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
        if seconds + 1e-9 < minimum:
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
