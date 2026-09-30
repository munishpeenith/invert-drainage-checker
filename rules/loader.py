"""Load and validate rule packs from YAML. Rules are data, not code."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Regime = Literal["private", "adoption", "any"]
Severity = Literal["fail", "warn"]


class Source(BaseModel):
    ref: str | None
    clause: str


class Rule(BaseModel):
    id: str
    regime: Regime
    applies_when: dict[str, Any]
    assert_: dict[str, Any]
    severity: Severity
    source: Source
    message: str


class RulePack(BaseModel):
    pack: str
    version: int
    last_verified: str
    sources: dict[str, dict[str, str]]
    rules: list[Rule]


def load_pack(path: Path) -> RulePack:
    raise NotImplementedError


def for_regime(pack: RulePack, regime: Regime) -> list[Rule]:
    raise NotImplementedError
