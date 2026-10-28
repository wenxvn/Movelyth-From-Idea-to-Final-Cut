"""Font readiness and real text measurement.

A font check that only answers "is a font file present" says nothing about whether the
renderer actually used it.  This module loads the same candidates the renderer's theme
stack names, measures real glyph advances, and reports:

* which file/family was actually used for each requested style;
* characters the chosen font has no glyph for (a silent fallback inside Chrome);
* measured line width for a caption or label, so a layout decision is based on pixels
  rather than on a character-count estimate.

When no CJK font is available the report says so and the caller must treat text as
unverified instead of assuming it will look right.
"""
from __future__ import annotations

import functools
from pathlib import Path

from PIL import ImageFont

# Same order as the theme stack in studio/src/theme.ts, so the measurement matches
# what Chrome resolves first.
LATIN_FIRST = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
               "/System/Library/Fonts/PingFang.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
DISPLAY_FIRST = ["C:/Windows/Fonts/msyhbd.ttc", *LATIN_FIRST]
SERIF_FIRST = ["C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/simsunb.ttf", *LATIN_FIRST]
FONT_STACKS = {"body": LATIN_FIRST, "display": DISPLAY_FIRST, "serif": SERIF_FIRST}

# Glyphs that are safe to substitute: they are punctuation, not meaning.
SUBSTITUTABLE = set("，。、；：！？（）《》「」『』“”‘’…—·%‰℃°")


@functools.lru_cache(maxsize=8)
def load_font(style: str, size: int) -> tuple[ImageFont.FreeTypeFont | None, str]:
    """First loadable candidate for a style, with the path that was used."""
    for candidate in FONT_STACKS.get(style, LATIN_FIRST):
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size), candidate
            except OSError:
                continue
    return None, ""


@functools.lru_cache(maxsize=8)
def _codepoints(path: str, index: int = 0) -> frozenset[int] | None:
    """Code points the font actually maps, read from its cmap.

    ``PIL`` happily draws a missing character as a blank or a tofu box, so asking the
    font file is the only way to know whether a glyph exists.  ``fontTools`` is
    optional: without it coverage is reported as unknown rather than as complete.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    try:
        font = TTFont(path, fontNumber=index, lazy=True)
        cmap = font.getBestCmap() or {}
        return frozenset(cmap)
    except Exception:
        return None


def _coverage_missing(text: str, path: str) -> list[str] | None:
    """Characters absent from the font's cmap; ``None`` when coverage is unknown."""
    points = _codepoints(path)
    if points is None:
        return None
    missing = []
    for character in dict.fromkeys(text):
        if character.isspace() or character in SUBSTITUTABLE:
            continue
        if ord(character) not in points:
            missing.append(character)
    return missing


def font_report(text: str, *, style: str = "body", size: int = 66) -> dict:
    """Which font is really used, and which characters it cannot draw."""
    font, path = load_font(style, size)
    if font is None:
        return {"ok": False, "style": style, "used": "", "family": "",
                "reason": "没有可用的字体文件；文字尺寸与缺字均未验证",
                "missing": [], "fallback": True, "width": None}
    family = " ".join(part for part in font.getname() if part)
    missing = _coverage_missing(text, path)
    coverage = "cmap" if missing is not None else "unknown"
    if missing is None:
        # Without fontTools only an empty bitmap is detectable; say so instead of
        # claiming the font covers everything.
        missing = []
        for character in dict.fromkeys(text):
            if character.isspace() or character in SUBSTITUTABLE:
                continue
            try:
                mask = font.getmask(character)
            except Exception:
                missing.append(character)
                continue
            if mask.size[0] == 0 and mask.size[1] == 0:
                missing.append(character)
    width = font.getlength(text)
    return {"ok": not missing, "style": style, "used": path, "family": family,
            "size": size, "missing": missing[:20], "fallback": False,
            "coverage": coverage, "width": round(width, 1),
            "note": "宽度为真实字体度量；与浏览器渲染仍可能有 ±2% 差异"}


def measure(text: str, *, style: str = "body", size: int = 66) -> dict:
    report = font_report(text, style=style, size=size)
    return {"text": text[:40], "width": report["width"], "family": report["family"],
            "missing": report["missing"], "ok": report["ok"]}


def availability() -> dict:
    """Capability summary for doctor/quality reports."""
    result = {}
    for style in FONT_STACKS:
        font, path = load_font(style, 48)
        result[style] = {"used": path, "family": (" ".join(part for part in font.getname() if part)
                                                  if font else ""),
                         "ok": font is not None}
    result["ok"] = all(item["ok"] for item in result.values() if isinstance(item, dict))
    return result


def text_width_ratio(text: str, box_width: int, *, size: int, style: str = "body") -> float | None:
    """Measured text width as a share of the box; ``None`` when the font is unknown."""
    report = font_report(text, style=style, size=size)
    if report["width"] is None:
        return None
    return round(report["width"] / max(1, box_width), 4)
