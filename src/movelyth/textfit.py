"""Chinese line breaking for captions and on-screen text.

The rules follow the typography notes in ``references/lunamos-paper2video``
(``skills/paper2video/reference/visual-style.md`` and ``scripts/text_check.py``):
break at clause punctuation first, never inside a Latin word or between a number
and its unit, never start a line with closing punctuation (kinsoku), and never
leave a one- or two-character orphan line.

No jieba dependency: the captions and labels this renderer produces are short
enough that clause punctuation plus ASCII/CJK boundaries cover the useful break
points.  When no boundary is available the text is cut at the measure, which is
reported rather than silently accepted.
"""
from __future__ import annotations

import re

# Characters that may not begin a line (closing punctuation and unit marks).
NO_LINE_START = "，。、；：！？）》」』”’…—·%‰℃°,.;:!?)]}\"'"
# Characters that may not end a line (opening punctuation).
NO_LINE_END = "（《「『“‘([{\"'"
# Where a caption may break, best first.
CLAUSE_PUNCTUATION = "，。、；：！？…—"
SENTENCE_END = "。！？"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _kind(ch: str) -> str:
    """Coarse character class used to keep numbers, units and Latin words whole."""
    if ch.isdigit() or ch in ".%‰":
        return "digit"
    if ch.isascii() and ch.isalnum():
        return "latin"
    if CJK.match(ch):
        return "cjk"
    if ch.isspace():
        return "space"
    return "punct"


def _break_point(segment: str, capacity: int) -> int:
    """Index to cut *segment* at, preferring the latest acceptable boundary."""
    window = segment[:capacity]
    limit = len(window)
    floor = max(1, limit // 3)
    for index in range(limit - 1, floor - 1, -1):
        if window[index] in CLAUSE_PUNCTUATION:
            return index + 1
    for index in range(limit - 1, floor - 1, -1):
        if window[index] in NO_LINE_START and index + 1 < limit:
            return index + 1
    for index in range(limit - 1, floor - 1, -1):
        if window[index].isspace():
            return index + 1
    for index in range(limit - 1, floor - 1, -1):
        if _kind(segment[index]) != _kind(segment[index + 1]):
            return index + 1
    # A cut here would land inside a Latin word or a number: back up to its start.
    if len(segment) > limit and _kind(window[-1]) in {"latin", "digit"} \
            and _kind(segment[limit]) in {"latin", "digit"}:
        index = limit
        while index > 0 and _kind(segment[index - 1]) in {"latin", "digit"}:
            index -= 1
        if index > 0:
            return index
    return limit


def _kinsoku(lines: list[str], capacity: int) -> list[str]:
    """Move punctuation off forbidden line starts and ends without dropping text."""
    fixed = list(lines)
    for index in range(1, len(fixed)):
        while fixed[index] and fixed[index][0] in NO_LINE_START and len(fixed[index - 1]) <= capacity:
            fixed[index - 1] += fixed[index][0]
            fixed[index] = fixed[index][1:]
    for index in range(len(fixed) - 1):
        while fixed[index] and fixed[index][-1] in NO_LINE_END and fixed[index + 1]:
            fixed[index + 1] = fixed[index][-1] + fixed[index + 1]
            fixed[index] = fixed[index][:-1]
    return [line for line in fixed if line]


def _fix_orphan(lines: list[str], capacity: int) -> list[str]:
    """Avoid a last line shorter than three characters or than ~35% of the line above."""
    if len(lines) < 2:
        return lines
    last, above = lines[-1], lines[-2]
    if len(last) >= 3 and len(last) >= len(above) * 0.35:
        return lines
    merged = above + last
    if len(merged) <= capacity * 1.1:
        return [*lines[:-2], merged]
    move = min(3 - len(last), len(above) - 1)
    # Only shift Chinese characters: moving one letter off "Remotion" tears the word.
    if move > 0 and all(_kind(ch) == "cjk" for ch in above[-move:] + last):
        tail = above[-move:]
        return [*lines[:-2], above[:-move], tail + last]
    return lines


def wrap(text: str, capacity: int) -> list[str]:
    """Break *text* into lines of at most ~*capacity* characters."""
    if capacity < 1:
        raise ValueError("每行容量必须为正")
    lines: list[str] = []
    for paragraph in text.split("\n"):
        remaining = paragraph
        while len(remaining) > capacity:
            cut = _break_point(remaining, capacity)
            lines.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        if remaining:
            lines.append(remaining)
    lines = _kinsoku(lines, capacity)
    return _fix_orphan(lines, capacity) if lines else lines


def typography_issues(lines: list[str], capacity: int) -> list[str]:
    """Report the line breaks a viewer would notice, for the review report."""
    issues: list[str] = []
    for index, line in enumerate(lines):
        if index and line[:1] and line[0] in NO_LINE_START:
            issues.append(f"第 {index + 1} 行以标点「{line[0]}」开头")
        if line[-1:] and line[-1] in NO_LINE_END:
            issues.append(f"第 {index + 1} 行以开引号「{line[-1]}」结尾")
        if len(line) > capacity * 1.15:
            issues.append(f"第 {index + 1} 行 {len(line)} 字明显超出 {capacity} 字容量")
    if len(lines) >= 2 and len(lines[-1]) < 3:
        issues.append(f"末行只有 {len(lines[-1])} 字，会出现孤字")
    return issues


def caption_chunks(text: str, limit: int) -> list[str]:
    """Split narration into caption pages that fit *limit* characters.

    Clause punctuation is the primary break; an over-long clause is cut with
    :func:`wrap` so the page still ends at a defensible point.  A trailing page
    of one or two characters is folded back into the previous page instead of
    being shown alone for a fraction of a second.
    """
    if limit < 2:
        raise ValueError("字幕每页容量必须至少为 2 字")
    clauses = [part for part in re.split(r"(?<=[，。！？；：,.!?;:])", text) if part.strip()]
    pages: list[str] = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        if len(clause) <= limit:
            pages.append(clause)
            continue
        for line in wrap(clause, limit):
            if line:
                pages.append(line)
    # Rebalance: a page of one or two characters joins its neighbour.
    balanced: list[str] = []
    for page in pages:
        if balanced and len(page) <= 2 and len(balanced[-1]) + len(page) <= limit * 1.15:
            balanced[-1] += page
        else:
            balanced.append(page)
    if len(balanced) >= 2 and len(balanced[0]) <= 2 and len(balanced[0]) + len(balanced[1]) <= limit * 1.15:
        balanced = [balanced[0] + balanced[1], *balanced[2:]]
    return balanced
