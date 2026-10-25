"""Bounded content contracts: models produce data, never executable code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VisualKind = Literal["matrix", "vectors", "projection", "wave", "network", "image_layers", "orbit"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Source(Contract):
    label: str = Field(min_length=2, max_length=160)
    url: str = Field(pattern=r"^https://", max_length=600)
    supports: str = Field(min_length=5, max_length=450)


class Research(Contract):
    title: str = Field(min_length=2, max_length=80)
    question: str = Field(min_length=5, max_length=200)
    angle: str = Field(min_length=5, max_length=400)
    facts: list[str] = Field(min_length=3, max_length=10)
    sources: list[Source] = Field(min_length=1, max_length=6)
    cautions: list[str] = Field(max_length=8)
    next_ideas: list[str] = Field(min_length=2, max_length=6)


class Scene(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    heading: str = Field(min_length=2, max_length=24)
    narration: str = Field(min_length=15, max_length=500)
    visual: VisualKind
    labels: list[str] = Field(min_length=1, max_length=3)
    # Every matrix scene uses these actual coefficients. Other visuals keep identity.
    matrix: list[float] = Field(min_length=4, max_length=4)
    color: Literal["cyan", "amber", "coral", "mint"]
    source_index: int = Field(ge=0, le=5)

    @field_validator("labels")
    @classmethod
    def label_lengths(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 22 for v in values):
            raise ValueError("每个画面标签需为 1–22 字")
        return values

    @field_validator("matrix")
    @classmethod
    def finite_matrix(cls, values: list[float]) -> list[float]:
        import math

        if any(not math.isfinite(v) or abs(v) > 4 for v in values):
            raise ValueError("矩阵系数必须是绝对值不超过 4 的有限数")
        return values


class Cut(Contract):
    title: str = Field(min_length=2, max_length=50)
    description: str = Field(min_length=20, max_length=1200)
    tags: list[str] = Field(min_length=2, max_length=8)
    scenes: list[Scene] = Field(min_length=3, max_length=14)

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


class Review(Contract):
    passed: bool
    issues: list[str] = Field(max_length=15)
    strengths: list[str] = Field(max_length=6)
    warnings: list[str] = Field(default_factory=list, max_length=10)


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
