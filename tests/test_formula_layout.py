from movelyth.models import Layer, Scene
from movelyth.scenedsl import formula_is_one_line, layout_errors, layout_warnings, text_capacity


def scene_with_math(text: str, region: str = "bottom") -> Scene:
    base = {"id": "l2", "heading": "把偏差记成账", "visual": "matrix", "labels": ["偏差"],
            "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0, "layout": "diagram",
            "narration": "把偏差平方相加，再除以样本数，就得到这一份账本上的损失值。"}
    return Scene.model_validate({**base, "layers": [
        {"id": "account", "type": "diagram", "region": "main",
         "nodes": [{"id": "a", "label": "偏差", "x": 100, "y": 100},
                   {"id": "b", "label": "损失", "x": 400, "y": 100}],
         "edges": [{"source": "a", "target": "b"}]},
        {"id": "definition", "type": "math", "region": region, "text": text, "emphasis": 3},
    ]})


def test_a_formula_is_one_expression_unless_the_director_wrote_rows():
    single = Layer.model_validate({"id": "m", "type": "math", "text": "L＝(4＋16)÷4＝5"})
    rows = Layer.model_validate({"id": "m", "type": "math", "text": "a=1\nb=2"})
    assert formula_is_one_line(single) is True
    assert formula_is_one_line(rows) is False
    assert formula_is_one_line(Layer.model_validate({"id": "t", "type": "text", "text": "说明"})) is False


def test_single_line_capacity_is_width_only():
    box = {"x": 0, "y": 440, "w": 660, "h": 240}
    assert text_capacity(box, 86, single_line=True) == 7
    tall = {"x": 0, "y": 0, "w": 660, "h": 900}
    # Wrapped capacity also uses the height, so a tall box holds more than one line.
    assert text_capacity(tall, 86, single_line=False) > text_capacity(tall, 86, single_line=True)


def test_math_padding_shrinks_the_usable_box():
    """Math layers sit in a padded surface: 14px vertical, 20px horizontal."""
    box = {"x": 760, "y": 745, "w": 1100, "h": 55}
    assert text_capacity(box, 34, single_line=True, math=True) == 0
    assert text_capacity(box, 34, single_line=True, math=False) > 0


def test_a_formula_too_long_for_one_line_is_rejected():
    """A formula that cannot fit even at the minimum size is clipped, so it is an error."""
    scene = scene_with_math("L＝Σ(wx－y)²÷(2n)＋Σ(wx－y)²÷(2n)＋Σ(wx－y)²÷(2n)")
    problems = layout_errors(scene, vertical=False)
    assert any("放不下" in p and "裁切" in p for p in problems)


def test_the_formula_that_actually_wrapped_now_fits_at_the_minimum_size():
    """'L＝(4＋16)÷4＝5' wrapped in a real render; at 34 px it fits on one line."""
    box = {"x": 85, "y": 440, "w": 660, "h": 240}
    scene = scene_with_math("L＝(4＋16)÷4＝5")
    assert len("L＝(4＋16)÷4＝5") <= text_capacity(box, 34, single_line=True)
    assert not any("放不下" in p for p in layout_errors(scene, vertical=False))
    # It is still reported as over the base size, so the renderer shrinks it.
    assert any("超出" in w for w in layout_warnings(scene, vertical=False))


def test_a_formula_in_a_short_band_is_rejected_even_when_narrow():
    """The `side` band is 55 px tall: a 34 px line needs 48 px plus padding."""
    scene = scene_with_math("-1 + (-1)×(-1) = 0", region="side")
    assert any("放不下" in p for p in layout_errors(scene, vertical=False))


def test_a_short_formula_is_not_warned_about():
    scene = scene_with_math("L＝5")
    assert not any("公式过长" in w for w in layout_warnings(scene, vertical=False))


def diagram_scene(nodes) -> Scene:
    base = {"id": "l5", "heading": "假设它等于负一", "visual": "matrix", "labels": ["矛盾"],
            "matrix": [1, 0, 0, 1], "color": "cyan", "source_index": 0, "layout": "diagram",
            "narration": "假设负一乘负一等于负一，代回前面的式子就得到负二等于零，这显然不成立。"}
    return Scene.model_validate({**base, "layers": [{"id": "chain", "type": "diagram",
                                                     "region": "main", "nodes": nodes,
                                                     "edges": []}]})


def test_overlapping_diagram_nodes_are_rejected():
    """A real render drew '(-1)×(-1)=-1' as '(-1)×(' because the next node covered it."""
    scene = diagram_scene([{"id": "a", "label": "(-1)×(-1)=-1", "x": 200, "y": 140},
                           {"id": "b", "label": "代回 -1+(-1)=0", "x": 500, "y": 140}])
    problems = [p for p in layout_errors(scene, vertical=False) if "重叠" in p]
    assert problems and "a" in problems[0] and "b" in problems[0]


def test_a_small_box_overlap_is_tolerated_because_padding_keeps_text_clear():
    """19 units of box overlap never hides a label: each side has ~35 units of padding."""
    # a spans 189..811, b spans 790..1040: 21 units of overlap, no text covered.
    scene = diagram_scene([{"id": "a", "label": "(-1)×(-1)=-1", "x": 500, "y": 140},
                           {"id": "b", "label": "=0", "x": 915, "y": 140}])
    assert not [p for p in layout_errors(scene, vertical=False) if "重叠" in p]


def test_a_wide_diagram_is_a_warning_not_an_error():
    """The viewBox grows to include every node, so wide content shrinks instead of clipping."""
    scene = diagram_scene([{"id": "a", "label": "假设(-1)×(-1)=-1", "x": 120, "y": 120},
                           {"id": "b", "label": "代回 -1+(-1)=0", "x": 880, "y": 420}])
    assert layout_errors(scene, vertical=False) == []
    assert any("整体缩小" in w for w in layout_warnings(scene, vertical=False))


def test_nodes_on_separate_rows_are_accepted():
    scene = diagram_scene([{"id": "a", "label": "分配律", "x": 250, "y": 180},
                           {"id": "b", "label": "减法规则", "x": 250, "y": 440},
                           {"id": "c", "label": "符号法则", "x": 720, "y": 310}])
    assert layout_errors(scene, vertical=False) == []


def chart_scene(series, chart="bar") -> Scene:
    base = {"id": "l4", "heading": "反过来假设会崩", "visual": "matrix", "labels": ["矛盾"],
            "matrix": [1, 0, 0, 1], "color": "amber", "source_index": 0, "layout": "compare",
            "narration": "如果负一乘负一等于负一，代回就得到负二等于零，这显然不成立。"}
    return Scene.model_validate({**base, "layers": [
        {"id": "gap", "type": "chart", "region": "main", "chart": chart, "series": series},
        {"id": "note", "type": "text", "region": "side", "text": "两条路必须给出同一个值"}]})


def test_two_constant_bar_series_are_rejected():
    """A real render drew four bars where the narration compared two values."""
    scene = chart_scene([{"label": "右边应为", "values": [0.0, 0.0], "x_values": [0.0, 1.0]},
                         {"label": "代回得到", "values": [-2.0, -2.0], "x_values": [0.0, 1.0]}])
    problems = layout_errors(scene, vertical=False)
    assert any("同一个常数值" in p for p in problems)


def test_an_all_zero_series_is_rejected_as_meaningless():
    scene = chart_scene([{"label": "右边应为", "values": [0.0, 0.0], "x_values": [0.0, 1.0]},
                         {"label": "代回得到", "values": [0.0, -2.0], "x_values": [0.0, 1.0]}])
    assert any("等于没有数据" in p for p in layout_errors(scene, vertical=False))


def test_one_series_with_two_compared_values_is_accepted():
    scene = chart_scene([{"label": "两条路", "values": [0.0, -2.0], "x_values": [0.0, 1.0]}])
    assert layout_errors(scene, vertical=False) == []


def test_node_width_matches_the_renderer():
    """The Python check and the TSX box must agree, or the check is decorative."""
    from movelyth.scenedsl import NODE_HEIGHT, NODE_MIN_WIDTH, node_width

    assert node_width("矛盾") == NODE_MIN_WIDTH == 210
    assert len("(-1)×(-1)=-1") == 12
    assert node_width("(-1)×(-1)=-1") == 12 * 46 + 70 == 622
    assert NODE_HEIGHT == 112
