"""Per-task budget and run accounting.

Two things were missing before: a limit that is checked *before* a call, and a
record that separates what was used from what it cost.  A failed call still spends
tokens, so usage is recorded even when the stage raises.  Money that is not known is
``None``: it is never silently reported as 0, and an estimate is never presented as
the amount paid.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .models import Contract
from .util import atomic_json, now, read_json

COUNTERS = ("model_calls", "input_tokens", "output_tokens", "tts_characters",
            "tts_seconds", "render_minutes", "wall_seconds")

# Initial values, frozen per task before a run.  They are generous enough for the
# existing repair loop (research + 2 director calls + review per attempt) while still
# stopping a runaway task; they are not a platform quota.
DEFAULT_LIMITS: dict[str, float] = {
    "model_calls": 40,
    "input_tokens": 1_000_000,
    "output_tokens": 400_000,
    "tts_characters": 12_000,
    "tts_seconds": 600,
    "render_minutes": 30,
    "wall_seconds": 7200,
}


class BudgetExceeded(RuntimeError):
    """The task budget is exhausted; stop before spending more."""


class Usage(Contract):
    """What one stage actually consumed. Missing measurements stay ``None``."""

    model_calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    tts_characters: int | None = Field(default=None, ge=0)
    tts_seconds: float | None = Field(default=None, ge=0)
    render_seconds: float | None = Field(default=None, ge=0)
    gpu_seconds: float | None = Field(default=None, ge=0)
    cpu_seconds: float | None = Field(default=None, ge=0)

    def counters(self) -> dict[str, float]:
        values = {"model_calls": float(self.model_calls)}
        for name in ("input_tokens", "output_tokens", "tts_characters", "tts_seconds"):
            value = getattr(self, name)
            if value is not None:
                values[name] = float(value)
        if self.render_seconds is not None:
            values["render_minutes"] = self.render_seconds / 60
        return values


class Cost(Contract):
    """Estimate, actual amount and price version are deliberately separate fields."""

    estimate: float | None = Field(default=None, ge=0)
    actual: float | None = Field(default=None, ge=0)
    currency: str = Field(default="", max_length=8)
    price_version: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=200)


class RunRecord(Contract):
    stage: str = Field(min_length=1, max_length=40)
    status: str = Field(min_length=1, max_length=20)
    started_at: str
    ended_at: str
    seconds: float = Field(ge=0)
    input_hash: str = Field(default="", max_length=80)
    calls: int = Field(default=0, ge=0)
    cache: bool = False
    retries: int = Field(default=0, ge=0)
    error_type: str = Field(default="", max_length=60)
    detail: str = Field(default="", max_length=300)
    usage: Usage = Field(default_factory=Usage)
    cost: Cost = Field(default_factory=Cost)


class BudgetState(Contract):
    limits: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_LIMITS))
    used: dict[str, float] = Field(default_factory=dict)
    reserved: dict[str, float] = Field(default_factory=dict)
    blocked_reason: str = Field(default="", max_length=300)
    currency: str = Field(default="", max_length=8)
    price_version: str = Field(default="", max_length=40)

    def remaining(self) -> dict[str, float]:
        return {name: round(self.limits.get(name, 0) - self.used.get(name, 0)
                            - self.reserved.get(name, 0), 3) for name in self.limits}

    def check(self, amounts: dict[str, float] | None = None) -> None:
        """Raise before a call when a limit would be crossed by ``amounts``."""
        amounts = amounts or {}
        over = []
        for name, amount in amounts.items():
            limit = self.limits.get(name)
            if limit is None:
                continue
            if self.used.get(name, 0) + self.reserved.get(name, 0) + amount > limit:
                over.append(f"{name} {self.used.get(name, 0) + self.reserved.get(name, 0):.0f}"
                            f"+{amount:.0f} > {limit:.0f}")
        if over:
            self.blocked_reason = "预算不足：" + "；".join(over)
            raise BudgetExceeded(self.blocked_reason)

    def reserve(self, **amounts: float) -> None:
        self.check(amounts)
        for name, amount in amounts.items():
            self.reserved[name] = round(self.reserved.get(name, 0) + amount, 3)

    def settle(self, actual: dict[str, float], *, reserved: dict[str, float] | None = None) -> None:
        for name in list((reserved or {}).keys()):
            self.reserved[name] = 0.0
        for name, amount in actual.items():
            self.used[name] = round(self.used.get(name, 0) + amount, 3)

    def exhausted(self) -> bool:
        return any(self.used.get(name, 0) >= limit for name, limit in self.limits.items())


def budget_from_config(config: dict) -> BudgetState:
    section = config.get("budget") or {}
    limits = dict(DEFAULT_LIMITS)
    for name in COUNTERS:
        if name in section:
            limits[name] = float(section[name])
    return BudgetState(limits=limits, currency=str(section.get("currency") or ""),
                       price_version=str(section.get("price_version") or ""))


def provider_snapshot(provider) -> dict:
    """Calls and tokens so far, so a stage's usage is a difference, not a guess."""
    return {"calls": int(getattr(provider, "call_count", 0) or 0),
            "usage": dict(getattr(provider, "usage_total", None)
                          or getattr(provider, "last_usage", None) or {})}


def usage_since(provider, before: dict) -> Usage:
    """Provider-reported usage during one stage; a missing field stays ``None``."""
    after = provider_snapshot(provider)
    delta = {key: after["usage"].get(key, 0) - before.get("usage", {}).get(key, 0)
             for key in set(after["usage"]) | set(before.get("usage", {}))}

    def number(value):
        return int(value) if isinstance(value, (int, float)) and value >= 0 else None

    return Usage(model_calls=max(0, after["calls"] - before.get("calls", 0)),
                 input_tokens=number(delta.get("prompt_tokens", delta.get("input_tokens"))),
                 output_tokens=number(delta.get("completion_tokens", delta.get("output_tokens"))))


def usage_from_provider(provider) -> Usage:
    return usage_since(provider, {"calls": 0, "usage": {}})


class BudgetLedger:
    """The budget and run records for one episode, kept beside its workspace."""

    def __init__(self, job: Path, state: BudgetState):
        self.job = job
        self.path = job / "budget.json"
        self.runs = job / "runs.jsonl"
        self.state = state

    @classmethod
    def load(cls, job: Path, config: dict) -> "BudgetLedger":
        ledger = cls(job, budget_from_config(config))
        if ledger.path.is_file():
            try:
                ledger.state = BudgetState.model_validate(read_json(ledger.path))
            except (OSError, ValueError):
                ledger.state = budget_from_config(config)
        return ledger

    def save(self) -> None:
        atomic_json(self.path, self.state.model_dump())

    def record(self, record: RunRecord) -> None:
        self.job.mkdir(parents=True, exist_ok=True)
        line = record.model_dump_json()
        with self.runs.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")

    def summary(self) -> dict:
        return {"limits": self.state.limits, "used": self.state.used,
                "remaining": self.state.remaining(), "blocked_reason": self.state.blocked_reason,
                "currency": self.state.currency, "price_version": self.state.price_version,
                "note": "未知费用为 null；estimate 与 actual 分开记录"}


def now_pair() -> tuple[str, str]:
    stamp = now()
    return stamp, stamp
