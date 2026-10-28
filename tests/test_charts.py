"""S1-02: the Python chart-scale mirror must match the renderer's arithmetic.

Tick labels are the deterministic evidence a release decision cites when a vision
model reports "the axis shows 3.11".  If the mirror drifts from ChartLayer.tsx that
evidence is wrong, so the test evaluates the renderer's own source in node.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from movelyth.charts import format_tick, nice_domain, nice_step, scene_tick_labels, tick_labels
from movelyth.models import Layer, Series

STUDIO = Path(__file__).parents[1] / "studio" / "src" / "components" / "ChartLayer.tsx"

CASES = [
    [3, 4, 4, 5, 4],
    [3, 4, 4, 5, 34],
    [0.1, 0.25, 0.7],
    [-4, 12.5],
    [11.25, 5, 1.25, 0],
    [1000, 3000],
    [0.0004, 0.0009],
    [7, 7],
]


def renderer_functions() -> str:
    source = STUDIO.read_text(encoding="utf-8")
    parts = []
    for name in ("niceStep", "niceDomain", "format"):
        match = re.search(rf"const {name} = [\s\S]*?\n}};", source)
        assert match, f"{name} not found in ChartLayer.tsx"
        parts.append(match.group(0))
    body = "\n".join(parts)
    body = body.replace(": {lo: number; hi: number; step: number}", "")
    body = body.replace(": number", "").replace(": string", "")
    return body


@pytest.mark.skipif(not shutil.which("node"), reason="node is required for the renderer parity check")
def test_python_scales_match_the_renderer_source():
    script = renderer_functions() + """
const cases = JSON.parse(process.argv[2]);
const out = cases.map((values) => {
  const domain = niceDomain(Math.min(...values), Math.max(...values));
  const ticks = [];
  for (let value = domain.lo; value <= domain.hi + 1e-9; value += domain.step) ticks.push(value);
  return {domain, labels: ticks.map((value) => format(value, domain.step))};
});
console.log(JSON.stringify(out));
"""
    path = Path(__file__).parent / ".chart-parity.mjs"
    path.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run([shutil.which("node"), str(path), json.dumps(CASES)],
                                capture_output=True, text=True, timeout=60, check=True)
    finally:
        path.unlink(missing_ok=True)
    expected = json.loads(result.stdout)
    for values, reference in zip(CASES, expected, strict=True):
        domain = nice_domain([float(value) for value in values])
        assert domain["lo"] == pytest.approx(reference["domain"]["lo"], abs=1e-9)
        assert domain["hi"] == pytest.approx(reference["domain"]["hi"], abs=1e-9)
        assert domain["step"] == pytest.approx(reference["domain"]["step"], rel=1e-12)
        assert tick_labels(values) == reference["labels"]


def test_teaching_sample_axis_labels():
    # The frozen sample A data: mean 4 -> 10 after one value becomes 34.
    assert tick_labels([3, 4, 4, 5, 34]) == ["0", "10", "20", "30", "40"]
    assert format_tick(-0.0, 1) == "0"


def test_nice_step_uses_one_two_five_rounding():
    assert nice_step(12) == 5
    assert nice_step(0.5) == 0.2
    assert nice_step(0) == 1


def test_scene_tick_labels_only_cover_chart_layers():
    chart = Layer(id="chart_a", type="chart", series=[Series(label="均值", values=[3, 4, 5])])
    text = Layer(id="text_a", type="text", text="结论")
    labels = scene_tick_labels([{"id": "l1", "layers": [chart.model_dump(), text.model_dump()]},
                                {"id": "l2", "layers": [text.model_dump()]}])
    assert set(labels) == {"l1"}
    # Span 2 with 1-2-5 rounding gives a 0.5 step, so labels carry one decimal.
    assert labels["l1"] == ["3.0", "3.5", "4.0", "4.5", "5.0"]
