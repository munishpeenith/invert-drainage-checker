"""Deterministic rule evaluation. Knows nothing about drainage.

No model is consulted here and none ever should be. The engine turns each run
into a flat dictionary of facts, selects the rules whose applies_when matches,
evaluates assert, and emits a finding. Every threshold and every comparison
lives in the YAML, so adding a check never means editing this file.

Three outcomes are possible for a rule against a run, and keeping them distinct
is the whole point. The rule does not apply, and nothing is said. The rule
applies and the comparison is decided, giving a pass or a failure. Or a value
the rule needs is absent, in which case the run is reported as not checked and
the missing field is named. The engine never fills a gap with an assumption.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from check.network import Network
from parse.schema import Manhole, PipeRun, Schedule
from rules.loader import Regime, Rule, RulePack, Source, for_regime

Verdict = Literal["pass", "fail", "warn", "not_checked", "not_supported"]

# not_supported ranks below pass so it never becomes a run's verdict. A rule
# this version cannot evaluate says nothing about the run, and letting it
# colour the long section would hide the runs that genuinely were not checked.
_SEVERITY_OF_VERDICT: dict[Verdict, int] = {
    "not_supported": -1,
    "pass": 0,
    "not_checked": 1,
    "warn": 2,
    "fail": 3,
}

# Quantities v1 never derives. A rule blocked only by these is reported as not
# supported, which is a limitation of the tool. A rule blocked by anything else
# is reported as not checked, which is a gap in the drawing. Conflating the two
# buries the second under the first.
_UNSUPPORTED_FACTS: frozenset[str] = frozenset(
    {
        "velocity_m_s_at_third_flow",
        "velocity_m_s_pipe_full",
        "proportional_depth",
        "us_node_type",
        "ds_node_type",
        "clear_opening_mm",
    }
)

_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


@dataclass
class CheckContext:
    """Everything the schedule does not state and the tool must be told.

    None means not supplied, and a rule needing it reports not checked. None
    never means zero, and nothing here is ever inferred from the drawing.
    """

    location_class: str | None = None
    system: str | None = None
    asset: str | None = None
    wc_count: int | None = None
    dwellings: int | None = None
    properties: int | None = None
    peak_flow_l_s: float | None = None
    design_flow_l_s: float | None = None


@dataclass
class Finding:
    run_ref: str
    rule_id: str
    verdict: Verdict
    message: str
    citation: str
    observed: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class Result:
    findings: list[Finding]
    counts: dict[str, int]
    run_verdicts: dict[str, Verdict]
    regime: Regime
    pack: str
    pack_version: int
    pack_last_verified: str


def computed_gradient_1_in(
    length_m: float, us_invert_m: float, ds_invert_m: float
) -> float | None:
    """Returns N in 1 in N. None when the run is level or rises.

    A level or rising run has no gradient to express this way. Returning None
    rather than infinity or a negative keeps the fact absent, so the rules that
    need it report not checked and the continuity rule reports the real fault.
    """
    fall = us_invert_m - ds_invert_m
    if fall <= 0:
        return None
    return length_m / fall


def build_facts(
    run: PipeRun,
    network: Network,
    manholes: dict[str, Manhole],
    context: CheckContext,
) -> dict[str, Any]:
    """Flatten one run, its neighbours and the supplied context into facts."""
    facts: dict[str, Any] = {
        "diameter_mm": run.diameter_mm,
        "length_m": run.length_m,
        "us_invert_m": run.us_invert_m,
        "ds_invert_m": run.ds_invert_m,
        "stated_gradient_1_in": run.stated_gradient_1_in,
        "spacing_m": run.length_m,
        "location_class": context.location_class,
        "system": context.system,
        "asset": context.asset,
        "wc_count": context.wc_count,
        "dwellings": context.dwellings,
        "properties": context.properties,
        "peak_flow_l_s": context.peak_flow_l_s,
        "design_flow_l_s": context.design_flow_l_s,
        # Hydraulics are not computed in v1. Absent, so the rules needing them
        # report not checked rather than passing silently.
        "velocity_m_s_at_third_flow": None,
        "velocity_m_s_pipe_full": None,
        "proportional_depth": None,
        # Chamber type is not stated in the schedule and is never inferred from
        # a reference prefix, so the spacing rules abstain.
        "us_node_type": None,
        "ds_node_type": None,
        "clear_opening_mm": None,
    }

    computed = None
    if (
        run.length_m is not None
        and run.us_invert_m is not None
        and run.ds_invert_m is not None
    ):
        computed = computed_gradient_1_in(run.length_m, run.us_invert_m, run.ds_invert_m)
    facts["computed_gradient_1_in"] = computed

    # The computed value governs where both exist. The schedule states a
    # gradient but the levels are what will be built.
    facts["gradient_1_in"] = (
        computed if computed is not None else run.stated_gradient_1_in
    )

    if computed is not None and run.stated_gradient_1_in is not None:
        facts["gradient_delta_1_in"] = abs(computed - run.stated_gradient_1_in)
    else:
        facts["gradient_delta_1_in"] = None

    # Continuity. Where several runs arrive, the outgoing invert must sit at or
    # below the lowest of them, so the lowest is the one to compare against.
    arriving = [
        feeder.ds_invert_m
        for feeder in network.upstream_of(run)
        if feeder.ds_invert_m is not None
    ]
    if arriving:
        lowest = min(arriving)
        facts["upstream_run_ds_invert_m"] = lowest
        facts["invert_step_m"] = (
            run.us_invert_m - lowest if run.us_invert_m is not None else None
        )
    else:
        facts["upstream_run_ds_invert_m"] = None
        facts["invert_step_m"] = None

    chamber = manholes.get(run.us_node)
    facts["chamber_size_mm"] = chamber.chamber_size_mm if chamber else None
    if (
        chamber is not None
        and chamber.cover_level_m is not None
        and run.us_invert_m is not None
        and run.diameter_mm is not None
    ):
        crown = run.us_invert_m + run.diameter_mm / 1000.0
        facts["cover_to_crown_m"] = chamber.cover_level_m - crown
    else:
        facts["cover_to_crown_m"] = None

    connecting = [
        other.diameter_mm
        for other in network.at_node(run.us_node)
        if other.diameter_mm is not None
    ]
    facts["max_connecting_diameter_mm"] = max(connecting) if connecting else None

    return facts


def evaluate(
    schedule: Schedule,
    network: Network,
    pack: RulePack,
    regime: Regime,
    context: CheckContext | None = None,
) -> Result:
    context = context or CheckContext()
    rules = for_regime(pack, regime)
    manholes = {chamber.ref: chamber for chamber in schedule.manholes}

    findings: list[Finding] = []
    run_verdicts: dict[str, Verdict] = {}

    for run in schedule.runs:
        facts = build_facts(run, network, manholes, context)
        worst: Verdict = "pass"
        for rule in rules:
            finding = _apply(rule, run, facts, pack)
            if finding is None:
                continue
            findings.append(finding)
            if _SEVERITY_OF_VERDICT[finding.verdict] > _SEVERITY_OF_VERDICT[worst]:
                worst = finding.verdict
        run_verdicts[run.ref] = worst

    counts = Counter(finding.verdict for finding in findings)
    return Result(
        findings=findings,
        counts={verdict: counts.get(verdict, 0) for verdict in _SEVERITY_OF_VERDICT},
        run_verdicts=run_verdicts,
        regime=regime,
        pack=pack.pack,
        pack_version=pack.version,
        pack_last_verified=pack.last_verified.isoformat(),
    )


def _apply(
    rule: Rule, run: PipeRun, facts: dict[str, Any], pack: RulePack
) -> Finding | None:
    citation = pack.citation(rule.source)

    applies, missing = _applies(rule, facts)
    if applies is False:
        return None
    if applies is None:
        return _abstention(run, rule, citation, missing, {})

    holds, missing, observed = _holds(rule, facts)
    if holds is None:
        return _abstention(run, rule, citation, missing, observed)
    return Finding(
        run_ref=run.ref,
        rule_id=rule.id,
        verdict="pass" if holds else rule.severity,
        message=rule.message.strip(),
        citation=citation,
        observed=observed,
    )


def _abstention(
    run: PipeRun,
    rule: Rule,
    citation: str,
    missing: list[str],
    observed: dict[str, Any],
) -> Finding:
    # A rule is unsupported either because the quantity it asserts on is one
    # v1 never derives, or because the only things missing are such quantities.
    # The first case has to be tested on the assertion rather than on what is
    # missing, because an applies_when gate can fail first and mask it: the
    # velocity rules are blocked by a missing design flow, but supplying one
    # would not help, since no velocity is computed either way.
    unsupported_assert = bool(rule.assert_) and set(rule.assert_) <= _UNSUPPORTED_FACTS
    unsupported_missing = bool(missing) and set(missing) <= _UNSUPPORTED_FACTS

    if unsupported_assert or unsupported_missing:
        verdict: Verdict = "not_supported"
        blocked = sorted(set(rule.assert_) if unsupported_assert else set(missing))
        message = f"Not supported in this version. {', '.join(blocked)} is not derived."
    else:
        verdict = "not_checked"
        message = f"Not checked. {', '.join(missing)} not available."
    return Finding(
        run_ref=run.ref,
        rule_id=rule.id,
        verdict=verdict,
        message=message,
        citation=citation,
        observed=observed,
        missing_fields=missing,
    )


def _applies(rule: Rule, facts: dict[str, Any]) -> tuple[bool | None, list[str]]:
    """Tri-state. True applies, False does not, None cannot be determined.

    A predicate known to be false settles it, whatever else is missing, because
    a rule that does not apply cannot be not checked.
    """
    missing: list[str] = []
    for key, spec in rule.applies_when.items():
        if key == "has":
            missing.extend(name for name in spec if facts.get(name) is None)
            continue
        if key == "between":
            pair = ("us_node_type", "ds_node_type")
            absent = [name for name in pair if facts.get(name) is None]
            if absent:
                missing.extend(absent)
                continue
            if [facts[name] for name in pair] != list(spec):
                return False, []
            continue

        value = facts.get(key)
        if value is None:
            missing.append(key)
            continue
        outcome = _compare(value, spec) if isinstance(spec, dict) else (value == spec)
        if outcome is False:
            return False, []
        if outcome is None:
            missing.append(key)

    if missing:
        return None, sorted(set(missing))
    return True, []


def _holds(
    rule: Rule, facts: dict[str, Any]
) -> tuple[bool | None, list[str], dict[str, Any]]:
    observed: dict[str, Any] = {}
    missing: list[str] = []
    decided_false = False

    for field_name, spec in rule.assert_.items():
        value = facts.get(field_name)
        observed[field_name] = value
        if value is None:
            missing.append(field_name)
            continue
        outcome, needs = _eval_assert(value, spec, facts, observed)
        missing.extend(needs)
        if outcome is False:
            decided_false = True
        elif outcome is None and not needs:
            missing.append(field_name)

    if decided_false:
        return False, [], observed
    if missing:
        return None, sorted(set(missing)), observed
    return True, [], observed


def _eval_assert(
    value: Any, spec: Any, facts: dict[str, Any], observed: dict[str, Any]
) -> tuple[bool | None, list[str]]:
    if not isinstance(spec, dict):
        return value == spec, []

    for op, operand in spec.items():
        if op == "gte_by_location":
            location = facts.get("location_class")
            if location is None or location not in operand:
                return None, ["location_class"]
            observed["threshold"] = operand[location]
            return value >= operand[location], []

        if op == "gte_by_band":
            pipe = facts.get("max_connecting_diameter_mm")
            if pipe is None:
                return None, ["max_connecting_diameter_mm"]
            threshold = _band_threshold(operand, pipe)
            if threshold is None:
                return None, ["max_connecting_diameter_mm"]
            observed["threshold"] = threshold
            return value >= threshold, []

        compare = _OPS.get(op)
        if compare is None:
            raise ValueError(f"unknown operator in rule pack: {op}")

        if isinstance(operand, list):
            if not isinstance(value, (list, tuple)) or len(value) != len(operand):
                return None, []
            observed["threshold"] = operand
            return all(compare(v, o) for v, o in zip(value, operand)), []

        observed["threshold"] = operand
        return compare(value, operand), []

    return True, []


def _band_threshold(bands: list[dict[str, Any]], pipe_mm: float) -> float | None:
    for band in bands:
        if "pipe_lt" in band and pipe_mm < band["pipe_lt"]:
            return band["min"]
        if "pipe_lte" in band and pipe_mm <= band["pipe_lte"]:
            return band["min"]
    return None


def _compare(value: Any, spec: dict[str, Any]) -> bool | None:
    for op, operand in spec.items():
        compare = _OPS.get(op)
        if compare is None:
            raise ValueError(f"unknown operator in rule pack: {op}")
        if not compare(value, operand):
            return False
    return True
