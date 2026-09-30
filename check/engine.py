"""Deterministic rule evaluation. Knows nothing about drainage.

No model is consulted here and none ever should be. The engine selects the
rules whose applies_when matches, evaluates assert, and emits a finding. A run
missing a field a rule needs is reported as not checked, naming the field.
"""

from dataclasses import dataclass
from typing import Any, Literal

from parse.schema import Schedule
from rules.loader import Regime, Rule

Verdict = Literal["pass", "fail", "warn", "not_checked"]


@dataclass
class Finding:
    run_ref: str
    rule_id: str
    verdict: Verdict
    message: str
    citation: str
    observed: dict[str, Any]
    missing_fields: list[str]


@dataclass
class Result:
    findings: list[Finding]
    counts: dict[Verdict, int]
    regime: Regime
    pack_version: int
    pack_last_verified: str


def computed_gradient_1_in(
    length_m: float, us_invert_m: float, ds_invert_m: float
) -> float | None:
    """Returns N in 1 in N. None when the run is level or rises."""
    raise NotImplementedError


def evaluate(schedule: Schedule, rules: list[Rule], regime: Regime) -> Result:
    raise NotImplementedError
