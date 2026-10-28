"""Bounded content contracts: models produce data, never executable code.

The contracts here are the single source of truth for the Scene DSL v1
(see ``docs/scene-dsl.md``).  The TypeScript renderer mirrors these bounds and
``tests/test_scenedsl.py`` fails when the two sides drift apart.
"""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 2

VisualKind = Literal["matrix", "vectors", "projection", "wave", "network", "image_layers", "orbit"]
LayerKind = Literal["text", "shape", "math", "chart", "diagram", "timeline", "image", "procedural"]
Region = Literal["main", "side", "top", "bottom", "annotation", "full"]
LayoutKind = Literal["immersive", "diagram", "compare"]
ActionKind = Literal["appear", "fade", "move", "scale", "rotate", "highlight", "draw", "morph"]
ShapeKind = Literal["point", "line", "rect", "circle", "arrow", "polygon", "bracket"]
ChartKind = Literal["line", "bar", "scatter"]
StyleName = Literal["minimal", "tech", "documentary"]
Color = Literal["cyan", "amber", "coral", "mint"]
# How the previous scene hands over to this one.  "fade" is the safe default for
# older scripts; "cut" is a hard cut for a punchy beat.
TransitionKind = Literal["cut", "fade", "slide", "wipe", "dip", "zoom"]
# A slow, bounded camera move.  Long shots otherwise sit still while the voice talks.
CameraKind = Literal["none", "push", "pull", "pan_left", "pan_right"]
# Procedurally synthesised sound cues (no third-party audio, no licence risk).
CueKind = Literal["whoosh", "tick", "impact", "riser", "chime"]
#A shot's job in the story.  Used for music energy, pacing checks and the header.
SceneRole = Literal["hook", "mechanism", "example", "turn", "conclusion"]


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
    # Additional sources that support the same statement (corroboration, not a copy).
    evidence_refs: list[int] = Field(default_factory=list, max_length=3)
    excerpt: str = Field(min_length=4, max_length=280)
    scope: Literal["established", "illustrative", "uncertain"]
    # ``key`` claims must reach a scene; ``supporting`` ones may stay background.
    importance: Literal["key", "supporting"] = "key"


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
            for index in claim.evidence_refs:
                if index >= len(self.sources):
                    raise ValueError(f"claim {claim.claim_id} 的 evidence_refs 引用了不存在的来源")
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
    # Optional explicit x coordinates (same length as values) for scatter/line plots
    # that are not evenly spaced, e.g. polygon vertices on a real coordinate axis.
    x_values: list[float] = Field(default_factory=list, max_length=60)

    @field_validator("values", "x_values")
    @classmethod
    def finite_series(cls, values: list[float]) -> list[float]:
        return _finite(values, 1_000_000, "数据序列必须是绝对值不超过 1000000 的有限数")

    @model_validator(mode="after")
    def x_matches_y(self):
        if self.x_values and len(self.x_values) != len(self.values):
            raise ValueError("x_values 必须与 values 等长")
        return self


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


class Annotation(Contract):
    """A short callout on a chart at a real x position.

    An annotation is data storytelling, not decoration: it must name a value that
    the series actually contains (the renderer snaps to the nearest sample), so a
    model cannot invent a point on the curve that does not exist.
    """

    x: float = Field(ge=-1_000_000, le=1_000_000)
    text: str = Field(min_length=1, max_length=20)

    @field_validator("x")
    @classmethod
    def finite_x(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("注释坐标必须是有限数")
        return value


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
    # Connect scattered points into a path (closed shape when the first and last
    # point coincide is up to the data).  Used for triangles, polygons and routes.
    connect: bool = False
    # A chart's story beats: up to four labelled points.  The renderer snaps each
    # x to the nearest real sample and refuses to draw a point that is not in the
    # data, so an annotation cannot claim a value the series does not contain.
    annotations: list[Annotation] = Field(default_factory=list, max_length=4)
    # An x interval that deserves emphasis (the "overshoot" region, the feasible
    # range).  Two finite numbers; ignored by non-chart layers.
    highlight: list[float] = Field(default_factory=list, max_length=2)
    # Semantic identity (v2).  ``subject_id`` follows the *thing* across scenes;
    # ``id`` only identifies this layer instance, and the same subject may be a card
    # in one scene and a point on a chart in the next.
    subject_id: str = Field(default="", max_length=24)
    state_before: str = Field(default="", max_length=40)
    state_after: str = Field(default="", max_length=40)
    visual_explanation: str = Field(default="", max_length=120)

    @field_validator("highlight")
    @classmethod
    def finite_highlight(cls, values: list[float]) -> list[float]:
        if values and len(values) != 2:
            raise ValueError("highlight 需要两个 x 值（区间起止）")
        return _finite(values, 1_000_000, "highlight 必须是有限数")

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

    @field_validator("subject_id")
    @classmethod
    def safe_subject_id(cls, value: str) -> str:
        if value and not __import__("re").fullmatch(r"[a-z][a-z0-9_]{0,23}", value):
            raise ValueError("subject_id 只能是小写标识符")
        return value

    @model_validator(mode="after")
    def state_needs_a_subject(self):
        if (self.state_before or self.state_after) and not self.subject_id:
            raise ValueError("声明了前后状态就必须给 subject_id，否则无法跨镜追踪同一对象")
        return self

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
        if self.type == "timeline" and len(self.steps) < 2:
            raise ValueError("timeline 图层至少需要两个步骤")
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


class Cue(Contract):
    """A sound effect placed on the real narration timeline.

    Only a bounded enumeration and a gain are accepted: the renderer synthesises
    the sound locally, so nothing here can point at a remote or unlicensed file.
    """

    at: str = Field(min_length=1, max_length=48)
    kind: CueKind
    gain: float = Field(default=0.6, ge=0, le=1)

    @field_validator("at")
    @classmethod
    def time_reference(cls, value: str) -> str:
        return Beat.bounded_time_reference(value)


class EventAnchor(Contract):
    """Where a semantic event sits: scene start/end, a fraction, or a phrase.

    Repeated phrases are disambiguated with ``occurrence`` (1-based) or an explicit
    character range, so "3" in "3 与 3 的平均" never binds to the wrong one.
    """

    kind: Literal["start", "end", "fraction", "narration"]
    fraction: float = Field(default=0.0, ge=0, le=1)
    text: str = Field(default="", max_length=48)
    occurrence: int = Field(default=1, ge=1, le=9)
    char_start: int | None = Field(default=None, ge=0, le=500)
    char_end: int | None = Field(default=None, ge=0, le=500)

    @model_validator(mode="after")
    def anchor_is_usable(self):
        if self.kind == "narration" and not self.text and self.char_start is None:
            raise ValueError("narration 锚点需要 text 或 char_start")
        if self.char_start is not None and self.char_end is not None and self.char_end <= self.char_start:
            raise ValueError("char_end 必须大于 char_start")
        return self


class SemanticEvent(Contract):
    """A named moment in a scene that other stages can bind to."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    kind: Literal["reveal", "transform", "compare", "conclude", "emphasis", "pause", "transition"]
    anchor: EventAnchor
    offset_seconds: float = Field(default=0.0, ge=-5, le=5)
    purpose: str = Field(default="", max_length=60)
    target: str = Field(default="", max_length=24)


class Scene(Contract):
    # The version this scene was written for.  A v1 scene is migrated by adding the
    # number only; v2-only fields under v1 are rejected instead of reinterpreted.
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
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
    # V2 direction fields.  All have defaults so an approved V1 script still renders.
    transition: TransitionKind = "fade"
    camera: CameraKind = "push"
    # Words in the narration that carry the point of this shot.  Used for caption
    # emphasis and for a slightly slower, louder delivery of that sentence.
    emphasis: list[str] = Field(default_factory=list, max_length=3)
    cues: list[Cue] = Field(default_factory=list, max_length=4)
    # V3 direction fields.  A short chapter label, the shot's narrative job, the
    # one sentence a viewer should remember, and the number/term that carries it.
    # All default to empty so V1/V2 approved scripts render unchanged.
    chapter: str = Field(default="", max_length=8)
    role: SceneRole = "mechanism"
    takeaway: str = Field(default="", max_length=30)
    metric: str = Field(default="", max_length=16)
    # The layer that should read as the hero.  Empty means "first drawing layer in
    # main", which is what every existing script already relies on visually.
    hero: str = Field(default="", max_length=24)
    # v2: which claims this scene carries, and why it holds or changes.
    claim_ids: list[str] = Field(default_factory=list, max_length=4)
    hold_reason: str = Field(default="", max_length=60)
    transition_reason: str = Field(default="", max_length=60)
    # v2: named semantic events.  They resolve against real TTS boundaries, so a
    # camera move or a sound can be bound to "the moment this is said" instead of a
    # hand-measured second.
    events: list[SemanticEvent] = Field(default_factory=list, max_length=8)

    @field_validator("labels")
    @classmethod
    def label_lengths(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 22 for v in values):
            raise ValueError("每个画面标签需为 1–22 字")
        return values

    @field_validator("claim_ids")
    @classmethod
    def claim_id_format(cls, values: list[str]) -> list[str]:
        if any(not __import__("re").fullmatch(r"c[0-9]{1,2}", value) for value in values):
            raise ValueError("claim_ids 只能引用 c1、c2 这样的主张编号")
        return values

    @field_validator("events")
    @classmethod
    def unique_event_ids(cls, values: list[SemanticEvent]) -> list[SemanticEvent]:
        identifiers = [event.id for event in values]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("同一镜头的事件 id 不能重复")
        return values

    @field_validator("emphasis")
    @classmethod
    def emphasis_words(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 12 for v in values):
            raise ValueError("emphasis 每个词需为 1–12 字")
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
        if self.hero and self.hero not in identifiers:
            raise ValueError(f"镜头 {self.id} 的 hero 引用了不存在的图层 {self.hero}")
        return self


V2_SCENE_FIELDS = {"events", "claim_ids", "hold_reason", "transition_reason"}
V2_LAYER_FIELDS = {"subject_id", "state_before", "state_after", "visual_explanation"}


def migrate_scene(data: dict) -> dict:
    """Accept a v1 scene as v1, and refuse to read v2 fields under the v1 version.

    Migration only adds the version number: it never invents claims, events or
    states, and it never reinterprets an old field with new meaning.
    """
    if not isinstance(data, dict):
        return data
    version = int(data.get("schema_version") or 1)
    if version > SCHEMA_VERSION:
        raise ValueError(f"脚本 schema_version={version} 高于当前实现 {SCHEMA_VERSION}")
    if version >= 2:
        return data
    offending = sorted(V2_SCENE_FIELDS & set(data))
    for layer in data.get("layers") or []:
        if isinstance(layer, dict):
            offending.extend(sorted(V2_LAYER_FIELDS & set(layer)))
    if offending:
        raise ValueError("schema_version=1 的脚本不能包含 v2 字段：" + "、".join(sorted(set(offending)))
                         + "；请把 schema_version 升到 2 或移除这些字段")
    return {**data, "schema_version": SCHEMA_VERSION}


def migrate_cut(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    scenes = [migrate_scene(scene) for scene in data.get("scenes") or []]
    return {**data, "scenes": scenes}


class Cut(Contract):
    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data):
        return migrate_cut(data)

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
    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data):
        if not isinstance(data, dict):
            return data
        return {**data, "long": migrate_cut(data.get("long") or {}),
                "short": migrate_cut(data.get("short") or {})}

    title: str = Field(min_length=2, max_length=80)
    thesis: str = Field(min_length=8, max_length=300)
    long: Cut
    short: Cut


class Budget(Contract):
    """An estimate with explicit unknowns: a missing cost stays ``None``, never 0."""

    model_calls: int = Field(ge=0, le=200)
    tts_characters: int = Field(ge=0, le=200_000)
    render_minutes: float = Field(ge=0, le=600)
    estimated_cost: float | None = Field(default=None, ge=0, le=10_000)
    currency: str = Field(default="", max_length=8)
    note: str = Field(default="", max_length=200)


class ProductionBrief(Contract):
    """What this episode is for, and which route can actually deliver it.

    Frozen for the task: a repair may change scenes, never the audience, the central
    question or the route.
    """

    version: str = Field(default="1", max_length=8)
    audience: str = Field(min_length=2, max_length=120)
    prior_knowledge: str = Field(min_length=2, max_length=200)
    question: str = Field(min_length=5, max_length=200)
    central_explanation: str = Field(min_length=5, max_length=400)
    boundaries: list[str] = Field(default_factory=list, max_length=8)
    route: Literal["program-graphics", "licensed-media", "generated-media", "spatial-demo",
                   "real-footage"]
    route_status: Literal["supported", "needs_extension", "unsupported"]
    effective_route: Literal["program-graphics", "licensed-media", "generated-media",
                             "spatial-demo", "real-footage"]
    route_reason: str = Field(min_length=2, max_length=400)
    substitutions: list[str] = Field(default_factory=list, max_length=4)
    orientations: list[Literal["landscape", "portrait"]] = Field(default_factory=lambda: ["landscape", "portrait"],
                                                                 min_length=1, max_length=2)
    long_seconds: int = Field(ge=20, le=900)
    short_seconds: int = Field(ge=10, le=300)
    style: Literal["minimal", "tech", "documentary"] = "tech"
    budget: Budget
    created_from: dict = Field(default_factory=dict)

    @field_validator("boundaries")
    @classmethod
    def bounded_lines(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 240 for value in values):
            raise ValueError("boundaries 每条需为 1–240 字")
        return values


class TopicCandidate(Contract):
    """A proposed topic for the optional "what should I make next" flow."""

    title: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=5, max_length=200)
    why_now: str = Field(min_length=5, max_length=240)
    visual_plan: list[str] = Field(min_length=1, max_length=6)
    capability: Literal["supported", "needs_extension", "unsupported"]
    risks: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("visual_plan")
    @classmethod
    def bounded_plan(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 160 for v in values):
            raise ValueError("visual_plan 每条需为 1–160 字")
        return values


class TopicPlan(Contract):
    candidates: list[TopicCandidate] = Field(min_length=1, max_length=5)
    notes: list[str] = Field(default_factory=list, max_length=5)


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
