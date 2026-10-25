"""Bounded content contracts: models produce data, never executable code.

The contracts here are the single source of truth for the Scene DSL v1
(see ``docs/scene-dsl.md``).  The TypeScript renderer mirrors these bounds and
``tests/test_scenedsl.py`` fails when the two sides drift apart.
"""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1

VisualKind = Literal["matrix", "vectors", "projection", "wave", "network", "image_layers", "orbit"]
LayerKind = Literal["text", "shape", "math", "chart", "diagram", "image", "procedural"]
Region = Literal["main", "side", "top", "bottom", "annotation", "full"]
LayoutKind = Literal["immersive", "diagram", "compare"]
ActionKind = Literal["appear", "fade", "move", "scale", "rotate", "highlight", "draw", "morph"]
ShapeKind = Literal["point", "line", "rect", "circle", "arrow", "polygon", "bracket"]
ChartKind = Literal["line", "bar", "scatter"]
StyleName = Literal["minimal", "tech", "documentary"]
Color = Literal["cyan", "amber", "coral", "mint"]


def _finite(values: list[float], limit: float, message: str) -> list[float]:
    if any(not math.isfinite(v) or abs(v) > limit for v in values):
        raise ValueError(message)
    return values


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(Contract):
    label: str = Field(min_length=2, max_length=160)
    url: str = Field(pattern=r"^https://", max_length=600)
    supports: str = Field(min_length=5, max_length=450)


class Claim(Contract):
    """A claim mapped to the evidence that supports it (not a paper workflow)."""

    claim_id: str = Field(pattern=r"^c[0-9]{1,2}$")
    statement: str = Field(min_length=5, max_length=240)
    source_index: int = Field(ge=0, le=5)
    excerpt: str = Field(min_length=4, max_length=280)
    scope: Literal["established", "illustrative", "uncertain"]


class Research(Contract):
    title: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=5, max_length=200)
    angle: str = Field(min_length=5, max_length=400)
    facts: list[str] = Field(min_length=3, max_length=10)
    sources: list[Source] = Field(min_length=1, max_length=6)
    cautions: list[str] = Field(max_length=8)
    next_ideas: list[str] = Field(min_length=2, max_length=6)
    claims: list[Claim] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def claims_point_at_sources(self):
        for claim in self.claims:
            if claim.source_index >= len(self.sources):
                raise ValueError(f"claim {claim.claim_id} 引用了不存在的来源")
        return self


class Beat(Contract):
    """A narrative beat. ``at`` is start/end/a 0–1 fraction/narration:substring."""

    at: str = Field(min_length=1, max_length=48)
    purpose: str = Field(min_length=2, max_length=60)

    @field_validator("at")
    @classmethod
    def bounded_time_reference(cls, value: str) -> str:
        if value in {"start", "end"}:
            return value
        if value.startswith("narration:"):
            if not 1 <= len(value.removeprefix("narration:")) <= 32:
                raise ValueError("narration: 后需为 1–32 字的旁白片段")
            return value
        try:
            fraction = float(value)
        except ValueError as exc:
            raise ValueError("节拍时间需为 start/end/0–1 小数/narration:片段") from exc
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("节拍时间小数必须在 0–1 之间")
        return value


class Series(Contract):
    label: str = Field(min_length=1, max_length=16)
    values: list[float] = Field(min_length=2, max_length=60)
    unit: str = Field(default="", max_length=8)

    @field_validator("values")
    @classmethod
    def finite_series(cls, values: list[float]) -> list[float]:
        return _finite(values, 1_000_000, "数据序列必须是绝对值不超过 1000000 的有限数")


class DiagramNode(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    label: str = Field(min_length=1, max_length=18)
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=640)

    @field_validator("x", "y")
    @classmethod
    def finite_position(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("节点坐标必须为有限数")
        return value


class DiagramEdge(Contract):
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    target: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    label: str = Field(default="", max_length=12)


class Layer(Contract):
    """One bounded visual layer inside a scene.

    Only enumerations, numbers and short strings are accepted.  File paths,
    URLs, code and unbounded lists are rejected by construction.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    type: LayerKind
    region: Region = "main"
    text: str = Field(default="", max_length=120)
    shape: ShapeKind = "rect"
    chart: ChartKind = "line"
    procedural: str = Field(default="", max_length=16)
    series: list[Series] = Field(default_factory=list, max_length=4)
    nodes: list[DiagramNode] = Field(default_factory=list, max_length=12)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=24)
    steps: list[str] = Field(default_factory=list, max_length=6)
    points: list[float] = Field(default_factory=list, max_length=64)
    data_ref: str = Field(default="", max_length=32)
    unit: str = Field(default="", max_length=8)
    axis: str = Field(default="", max_length=16)
    source_note: str = Field(default="", max_length=60)
    color: Color = "cyan"
    emphasis: int = Field(default=1, ge=1, le=3)

    @field_validator("points")
    @classmethod
    def finite_points(cls, values: list[float]) -> list[float]:
        return _finite(values, 1000, "图形坐标必须是绝对值不超过 1000 的有限数")

    @field_validator("steps")
    @classmethod
    def short_steps(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 24 for v in values):
            raise ValueError("每个步骤标签需为 1–24 字")
        return values

    @field_validator("data_ref")
    @classmethod
    def safe_data_reference(cls, value: str) -> str:
        if value and not __import__("re").fullmatch(r"[a-z][a-z0-9_]{0,23}", value):
            raise ValueError("data_ref 只能是小写标识符，不能是路径或 URL")
        return value

    @field_validator("procedural")
    @classmethod
    def known_procedural(cls, value: str) -> str:
        if value and value not in set(VisualKind.__args__):
            raise ValueError("procedural 必须是已知的程序动画类型")
        return value

    @model_validator(mode="after")
    def type_specific_bounds(self):
        if self.type == "procedural" and not self.procedural:
            raise ValueError("procedural 图层必须指定 procedural 类型")
        if self.type in {"text", "math"} and not self.text.strip():
            raise ValueError(f"{self.type} 图层需要 text")
        if self.type == "chart" and not self.series and not self.data_ref:
            raise ValueError("chart 图层需要 series 或本地 data_ref")
        if self.type == "image" and not self.data_ref:
            raise ValueError("image 图层需要本地素材 data_ref")
        if self.type == "diagram":
            if len(self.nodes) < 2:
                raise ValueError("diagram 图层至少需要两个节点")
            identifiers = {node.id for node in self.nodes}
            if len(identifiers) != len(self.nodes):
                raise ValueError("diagram 节点 id 不能重复")
            if any(edge.source not in identifiers or edge.target not in identifiers
                   for edge in self.edges):
                raise ValueError("diagram 连线引用了不存在的节点")
        return self


class Action(Contract):
    """A reviewable animation primitive.  Time references resolve against real TTS."""

    target: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    kind: ActionKind
    start: str = Field(min_length=1, max_length=48)
    end: str = Field(min_length=1, max_length=48)
    dx: float = Field(default=0, ge=-1, le=1)
    dy: float = Field(default=0, ge=-1, le=1)
    scale: float = Field(default=1, ge=0.2, le=3)
    degrees: float = Field(default=0, ge=-360, le=360)

    @field_validator("start", "end")
    @classmethod
    def time_reference(cls, value: str) -> str:
        return Beat.bounded_time_reference(value)

    @field_validator("dx", "dy", "scale", "degrees")
    @classmethod
    def finite_motion(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("动画参数必须为有限数")
        return value


class Scene(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    heading: str = Field(min_length=2, max_length=24)
    narration: str = Field(min_length=15, max_length=500)
    # Legacy field kept for old tasks: it is the default procedural visual.
    visual: VisualKind
    labels: list[str] = Field(min_length=1, max_length=3)
    # Every matrix scene uses these actual coefficients. Other visuals keep identity.
    matrix: list[float] = Field(min_length=4, max_length=4)
    color: Color
    source_index: int = Field(ge=0, le=5)
    layout: LayoutKind = "diagram"
    beats: list[Beat] = Field(default_factory=list, max_length=6)
    layers: list[Layer] = Field(default_factory=list, max_length=6)
    actions: list[Action] = Field(default_factory=list, max_length=12)
    visual_intent: str = Field(default="", max_length=240)

    @field_validator("labels")
    @classmethod
    def label_lengths(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 22 for v in values):
            raise ValueError("每个画面标签需为 1–22 字")
        return values

    @field_validator("matrix")
    @classmethod
    def finite_matrix(cls, values: list[float]) -> list[float]:
        return _finite(values, 4, "矩阵系数必须是绝对值不超过 4 的有限数")

    @model_validator(mode="after")
    def layers_and_actions_are_consistent(self):
        if not self.layers:
            return self
        identifiers = {layer.id for layer in self.layers}
        if len(identifiers) != len(self.layers):
            raise ValueError(f"镜头 {self.id} 的图层 id 不能重复")
        if any(action.target not in identifiers for action in self.actions):
            raise ValueError(f"镜头 {self.id} 的动画引用了不存在的图层")
        return self


class Cut(Contract):
    title: str = Field(min_length=2, max_length=50)
    description: str = Field(min_length=20, max_length=1200)
    tags: list[str] = Field(min_length=2, max_length=8)
    scenes: list[Scene] = Field(min_length=3, max_length=14)
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    style: StyleName = "tech"
    # Optional platform-specific title candidates; the user still picks and uploads.
    title_candidates: list[str] = Field(default_factory=list, max_length=4)
    cover_caption: str = Field(default="", max_length=24)

    @field_validator("title_candidates")
    @classmethod
    def bounded_titles(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 50 for v in values):
            raise ValueError("标题候选需为 1–50 字")
        return values

    @field_validator("scenes")
    @classmethod
    def unique_scenes(cls, values: list[Scene]) -> list[Scene]:
        if len({s.id for s in values}) != len(values):
            raise ValueError("同一 cut 的 scene id 不能重复")
        return values


class Film(Contract):
    title: str = Field(min_length=2, max_length=80)
    thesis: str = Field(min_length=8, max_length=300)
    long: Cut
    short: Cut


class Finding(Contract):
    category: Literal["factual", "visual_mismatch", "visual_defect", "audio_defect", "warning"]
    scene_id: str = Field(default="", max_length=32)
    detail: str = Field(min_length=4, max_length=300)


class Review(Contract):
    passed: bool
    issues: list[str] = Field(max_length=15)
    strengths: list[str] = Field(max_length=6)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    findings: list[Finding] = Field(default_factory=list, max_length=15)


def strict_schema(model: type[BaseModel]) -> dict:
    """Require every property for structured-output providers, including nested objects."""
    schema = model.model_json_schema()

    def visit(item):
        if isinstance(item, dict):
            if item.get("type") == "object":
                item["additionalProperties"] = False
                item["required"] = list(item.get("properties", {}))
            for value in item.values():
                visit(value)
        elif isinstance(item, list):
            for value in item:
                visit(value)

    visit(schema)
    return schema
