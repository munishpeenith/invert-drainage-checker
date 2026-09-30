"""Load and validate rule packs from YAML. Rules are data, not code."""

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Regime = Literal["private", "adoption", "any"]
Severity = Literal["fail", "warn"]

PACK_DIR = Path(__file__).parent


class Source(BaseModel):
    ref: str | None = None
    clause: str


class Rule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    regime: Regime
    applies_when: dict[str, Any] = Field(default_factory=dict)
    # "assert" is reserved in Python, so the field is spelled with a trailing
    # underscore and aliased back to the name the YAML uses.
    assert_: dict[str, Any] = Field(alias="assert")
    severity: Severity
    source: Source
    message: str


class RulePack(BaseModel):
    pack: str
    version: int
    last_verified: date
    sources: dict[str, dict[str, str]]
    rules: list[Rule]

    def citation(self, source: Source) -> str:
        """Document, edition and clause, as printed beside a finding."""
        if source.ref is None:
            return source.clause
        meta = self.sources.get(source.ref, {})
        document = meta.get("document", source.ref)
        edition = meta.get("edition")
        head = f"{document} ({edition})" if edition else document
        return f"{head}, {source.clause}"


def load_pack(path: Path) -> RulePack:
    with path.open() as handle:
        raw = yaml.safe_load(handle)
    return RulePack.model_validate(raw)


def for_regime(pack: RulePack, regime: Regime) -> list[Rule]:
    return [rule for rule in pack.rules if rule.regime in (regime, "any")]
