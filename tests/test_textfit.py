from movelyth.textfit import NO_LINE_START, caption_chunks, typography_issues, wrap


def test_wrap_keeps_every_character_and_never_starts_with_closing_punctuation():
    text = "矩阵的列是基向量的像，行列式给出面积缩放比例。"
    lines = wrap(text, 10)
    assert "".join(lines) == text
    assert all(line[0] not in NO_LINE_START for line in lines)
    # Kinsoku may let one line run one character long, never more.
    assert all(len(line) <= 11 for line in lines)


def test_wrap_avoids_a_one_character_orphan():
    lines = wrap("测" * 21, 10)
    assert len(lines) == 2
    assert len(lines[-1]) >= 3


def test_wrap_does_not_split_a_latin_word_or_a_number_from_its_unit():
    lines = wrap("通过 Remotion 渲染", 8)
    assert any("Remotion" in line for line in lines)
    assert "".join(line.strip() for line in lines).replace(" ", "") == "通过Remotion渲染"
    number = wrap("总共 1200 步", 6)
    assert any("1200" in line for line in number)


def test_caption_chunks_never_emit_a_two_character_page():
    text = "这是一个很长的句子，用来验证字幕分页不会出现孤零零的两个字。"
    pages = caption_chunks(text, 12)
    assert "".join(pages) == text
    assert all(len(page.strip("，。")) >= 3 for page in pages)


def test_caption_chunks_keeps_a_short_clause_on_one_page():
    assert caption_chunks("看见变化，理解结构。", 12) == ["看见变化，", "理解结构。"]


def test_typography_issues_reports_what_a_viewer_notices():
    assert typography_issues(["正常一行", "，开头"], 10)
    assert typography_issues(["开引号可以开头", "结尾不行（"], 10)
    assert typography_issues(["一行很长的文本内容超过容量很多很多很多很多", "好"], 10)
    assert typography_issues(["第一行内容", "第二行内容"], 10) == []
