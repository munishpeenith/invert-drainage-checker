"""The three priority checks from SPEC.md section 4, plus abstention.

Each check gets a passing input, a failing input, and an input where a value
the rule needs is absent. The third case matters most: it is what proves the
tool abstains instead of guessing.
"""

import pytest

from check.engine import CheckContext, computed_gradient_1_in, evaluate
from check.network import Network
from tests.helpers import make_manhole, make_run, make_schedule


def run_checks(runs, pack, regime="adoption", context=None, manholes=None):
    schedule = make_schedule(runs, manholes)
    return evaluate(schedule, Network(runs), pack, regime, context or CheckContext())


def finding_for(result, rule_id, run_ref="R1"):
    return next(
        (
            f
            for f in result.findings
            if f.rule_id == rule_id and f.run_ref == run_ref
        ),
        None,
    )


# ----------------------------------------------------------- computed gradient


def test_gradient_is_length_over_fall():
    assert computed_gradient_1_in(30.0, 57.000, 56.800) == pytest.approx(150.0)


def test_a_level_run_has_no_gradient():
    assert computed_gradient_1_in(30.0, 57.000, 57.000) is None


def test_a_rising_run_has_no_gradient():
    assert computed_gradient_1_in(30.0, 56.800, 57.000) is None


# -------------------------------------------------------- 1. minimum gradient


def test_minimum_gradient_passes_at_the_limit(pack):
    # 30m falling 0.200m is exactly 1 in 150.
    result = run_checks(
        [make_run(length_m=30.0, us_invert_m=57.000, ds_invert_m=56.800)],
        pack,
        context=CheckContext(dwellings=12),
    )
    assert finding_for(result, "grad-min-adoption-150").verdict == "pass"


def test_minimum_gradient_fails_when_too_flat(pack):
    # 30m falling 0.100m is 1 in 300, flatter than the 1 in 150 minimum.
    result = run_checks(
        [make_run(length_m=30.0, us_invert_m=57.000, ds_invert_m=56.900)],
        pack,
        context=CheckContext(dwellings=12),
    )
    finding = finding_for(result, "grad-min-adoption-150")
    assert finding.verdict == "fail"
    assert finding.observed["gradient_1_in"] == pytest.approx(300.0)
    assert "B6.9" in finding.citation


def test_minimum_gradient_is_not_checked_when_dwellings_are_not_supplied(pack):
    result = run_checks([make_run()], pack, context=CheckContext())
    finding = finding_for(result, "grad-min-adoption-150")
    assert finding.verdict == "not_checked"
    assert finding.missing_fields == ["dwellings"]


def test_a_rule_for_another_diameter_produces_no_finding(pack):
    result = run_checks(
        [make_run(diameter_mm=225)], pack, context=CheckContext(dwellings=12)
    )
    assert finding_for(result, "grad-min-adoption-150") is None


def test_the_private_regime_does_not_see_adoption_rules(pack):
    result = run_checks(
        [make_run()], pack, regime="private", context=CheckContext(dwellings=12)
    )
    assert finding_for(result, "grad-min-adoption-150") is None


# --------------------------------------------------- 2. stated versus computed


def test_stated_matching_computed_passes(pack):
    result = run_checks(
        [
            make_run(
                length_m=30.0,
                us_invert_m=57.000,
                ds_invert_m=56.800,
                stated_gradient_1_in=150.0,
            )
        ],
        pack,
    )
    assert finding_for(result, "internal-stated-vs-computed").verdict == "pass"


def test_stated_disagreeing_with_computed_warns(pack):
    result = run_checks(
        [
            make_run(
                length_m=30.0,
                us_invert_m=57.000,
                ds_invert_m=56.800,
                stated_gradient_1_in=100.0,
            )
        ],
        pack,
    )
    finding = finding_for(result, "internal-stated-vs-computed")
    assert finding.verdict == "warn"
    assert finding.observed["gradient_delta_1_in"] == pytest.approx(50.0)


def test_stated_versus_computed_is_skipped_when_the_drawing_states_nothing(pack):
    result = run_checks([make_run(stated_gradient_1_in=None)], pack)
    assert finding_for(result, "internal-stated-vs-computed").verdict == "not_checked"


# ------------------------------------------------------- 3. invert continuity


def test_continuity_passes_when_the_outgoing_invert_sits_at_or_below(pack):
    arriving = make_run(
        ref="R1", us_node="MH1", ds_node="MH2", us_invert_m=57.000, ds_invert_m=56.800
    )
    leaving = make_run(
        ref="R2", us_node="MH2", ds_node="MH3", us_invert_m=56.800, ds_invert_m=56.600
    )
    result = run_checks([arriving, leaving], pack)
    assert finding_for(result, "internal-invert-continuity", "R2").verdict == "pass"


def test_continuity_fails_when_the_run_leaves_above_what_arrives(pack):
    arriving = make_run(
        ref="R1", us_node="MH1", ds_node="MH2", us_invert_m=57.000, ds_invert_m=56.800
    )
    leaving = make_run(
        ref="R2", us_node="MH2", ds_node="MH3", us_invert_m=56.900, ds_invert_m=56.700
    )
    result = run_checks([arriving, leaving], pack)
    finding = finding_for(result, "internal-invert-continuity", "R2")
    assert finding.verdict == "fail"
    assert finding.observed["invert_step_m"] == pytest.approx(0.100)


def test_continuity_compares_against_the_lowest_arriving_invert(pack):
    shallow = make_run(ref="R1", us_node="MH1", ds_node="MH3", ds_invert_m=56.900)
    deep = make_run(ref="R2", us_node="MH2", ds_node="MH3", ds_invert_m=56.700)
    leaving = make_run(
        ref="R3", us_node="MH3", ds_node="MH4", us_invert_m=56.800, ds_invert_m=56.600
    )
    result = run_checks([shallow, deep, leaving], pack)
    assert finding_for(result, "internal-invert-continuity", "R3").verdict == "fail"


def test_the_head_of_a_branch_produces_no_continuity_finding(pack):
    # Nothing discharges into a head run, so the rule does not apply. Reporting
    # it as not checked would mark every sound branch head as unverified.
    result = run_checks([make_run(ref="R1")], pack)
    assert finding_for(result, "internal-invert-continuity", "R1") is None


def test_a_missing_upstream_level_is_still_not_checked(pack):
    # The distinction the head-run case must not erase: something does
    # discharge here, but its level was not stated.
    arriving = make_run(ref="R1", us_node="MH1", ds_node="MH2", ds_invert_m=None)
    leaving = make_run(ref="R2", us_node="MH2", ds_node="MH3")
    result = run_checks([arriving, leaving], pack)
    finding = finding_for(result, "internal-invert-continuity", "R2")
    assert finding.verdict == "not_checked"
    assert "upstream_run_ds_invert_m" in finding.missing_fields


# ------------------------------------------------------------------ abstention


def test_a_run_missing_its_levels_is_never_passed(pack):
    result = run_checks(
        [make_run(us_invert_m=None, ds_invert_m=None)],
        pack,
        context=CheckContext(dwellings=12),
    )
    assert result.run_verdicts["R1"] == "not_checked"
    assert finding_for(result, "grad-min-adoption-150").verdict == "not_checked"


def test_hydraulic_rules_report_not_supported_because_v1_computes_no_flows(pack):
    # A limitation of the tool, not a gap in the drawing. The two are counted
    # separately so the second is not buried under the first.
    result = run_checks(
        [make_run()], pack, context=CheckContext(system="foul", design_flow_l_s=4.0)
    )
    assert finding_for(result, "velocity-min-foul").verdict == "not_supported"


def test_chamber_spacing_is_not_supported_because_chamber_type_is_never_inferred(pack):
    result = run_checks([make_run(length_m=60.0)], pack)
    finding = finding_for(result, "mh-spacing-adoption")
    assert finding.verdict == "not_supported"
    assert "us_node_type" in finding.missing_fields


def test_an_unsupported_rule_never_becomes_the_verdict_for_the_run(pack):
    # Every run trips several unsupported rules. If they counted, no run could
    # ever read as passing and the long section would be uniformly grey.
    result = run_checks(
        [
            make_run(
                ref="R1",
                us_node="MH1",
                ds_node="MH2",
                length_m=30.0,
                us_invert_m=57.000,
                ds_invert_m=56.800,
                stated_gradient_1_in=150.0,
            ),
            make_run(
                ref="R2",
                us_node="MH2",
                ds_node="MH3",
                length_m=25.0,
                us_invert_m=56.800,
                ds_invert_m=56.600,
                stated_gradient_1_in=125.0,
            ),
        ],
        pack,
        context=CheckContext(
            dwellings=12,
            properties=12,
            asset="sewer",
            system="foul",
            location_class="unrestricted_highway",
        ),
        manholes=[
            make_manhole(ref="MH1", cover_level_m=60.000),
            make_manhole(ref="MH2", cover_level_m=59.800),
        ],
    )
    assert result.run_verdicts["R2"] == "pass"
    assert result.counts["not_supported"] > 0


# ---------------------------------------------------------- derived quantities


def test_cover_to_crown_comes_from_the_upstream_chamber(pack):
    # Cover 60.000, invert 57.000, 150mm pipe, so crown is 57.150 and cover is
    # 2.850m, comfortably above the 1.20m unrestricted highway minimum.
    result = run_checks(
        [make_run()],
        pack,
        context=CheckContext(location_class="unrestricted_highway"),
        manholes=[make_manhole(ref="MH1", cover_level_m=60.000)],
    )
    finding = finding_for(result, "cover-min")
    assert finding.verdict == "pass"
    assert finding.observed["cover_to_crown_m"] == pytest.approx(2.850)


def test_shallow_cover_fails_against_the_supplied_location_class(pack):
    result = run_checks(
        [make_run(us_invert_m=59.500)],
        pack,
        context=CheckContext(location_class="unrestricted_highway"),
        manholes=[make_manhole(ref="MH1", cover_level_m=60.000)],
    )
    finding = finding_for(result, "cover-min")
    assert finding.verdict == "fail"
    assert finding.observed["threshold"] == 1.20


def test_cover_is_not_checked_when_the_location_class_is_not_supplied(pack):
    result = run_checks(
        [make_run()],
        pack,
        manholes=[make_manhole(ref="MH1", cover_level_m=60.000)],
    )
    finding = finding_for(result, "cover-min")
    assert finding.verdict == "not_checked"
    assert "location_class" in finding.missing_fields


# ---------------------------------------------------------------- the result


def test_the_result_carries_the_regime_and_pack_provenance(pack):
    result = run_checks([make_run()], pack)
    assert result.regime == "adoption"
    assert result.pack_version == 1
    assert result.pack_last_verified == "2026-09-30"


def test_counts_cover_every_finding(pack):
    result = run_checks([make_run()], pack, context=CheckContext(dwellings=12))
    assert sum(result.counts.values()) == len(result.findings)


def test_a_run_verdict_takes_the_worst_of_its_findings(pack):
    result = run_checks(
        [make_run(length_m=30.0, us_invert_m=57.000, ds_invert_m=56.900)],
        pack,
        context=CheckContext(dwellings=12),
    )
    assert result.run_verdicts["R1"] == "fail"
