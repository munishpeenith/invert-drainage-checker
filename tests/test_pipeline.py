"""End to end over the synthetic fixture, with no model and no API key.

The fixture plants known faults and the ground truth records what they are, so
this catches a regression anywhere between the PDF and the report.
"""

import json

import pytest

from app import cli
from check.engine import CheckContext, evaluate
from check.network import Network
from eval.fixtures import make_fixture
from extract.pdf_text import ScannedPdfError, read_pages
from extract.region import find_schedule
from parse import columns
from report import html, longsection
from rules.loader import PACK_DIR, load_pack


@pytest.fixture(scope="module")
def drawing(tmp_path_factory):
    directory = tmp_path_factory.mktemp("fixture")
    return make_fixture.write_pdf(directory / "synthetic_schedule.pdf")


@pytest.fixture(autouse=True)
def disposable_cache(tmp_path, monkeypatch):
    """Never touch the cache under the user's home directory from a test."""
    monkeypatch.setenv("INVERT_DB", str(tmp_path / "cache.sqlite"))


@pytest.fixture
def parsed(drawing):
    region = find_schedule(read_pages(drawing))[0]
    return columns.apply_mapping(region.rows, columns.infer_mapping(region.rows[0]))


# ------------------------------------------------------------------ extraction


def test_the_schedule_is_found_as_a_ruled_table(drawing):
    regions = find_schedule(read_pages(drawing))
    assert regions
    assert regions[0].from_table
    assert regions[0].rows


def test_a_pdf_with_no_text_is_refused_rather_than_guessed_at(tmp_path):
    from reportlab.pdfgen import canvas

    blank = tmp_path / "scan.pdf"
    canvas.Canvas(str(blank)).save()
    with pytest.raises(ScannedPdfError):
        read_pages(blank)


def test_every_run_in_the_ground_truth_is_recovered(parsed):
    expected = {record["ref"] for record in make_fixture.GROUND_TRUTH["runs"]}
    assert {run.ref for run in parsed.runs} == expected


def test_every_recovered_field_matches_the_ground_truth(parsed):
    by_ref = {run.ref: run for run in parsed.runs}
    for record in make_fixture.GROUND_TRUTH["runs"]:
        run = by_ref[record["ref"]]
        for name, wanted in record.items():
            assert getattr(run, name) == wanted, f"{record['ref']}.{name}"


def test_source_row_is_kept_for_every_record(parsed):
    # A finding that cannot be traced back to the text it came from cannot be
    # checked by the engineer disputing it.
    for run in parsed.runs:
        assert run.source_row.strip()


# ---------------------------------------------------------------------- checks


@pytest.fixture
def result(parsed):
    return evaluate(
        parsed,
        Network(parsed.runs),
        load_pack(PACK_DIR / "foul_gravity_v1.yaml"),
        "adoption",
        CheckContext(
            dwellings=12,
            properties=12,
            asset="sewer",
            system="foul",
            location_class="unrestricted_highway",
        ),
    )


def test_the_planted_flat_gradient_is_caught(result):
    # 1.001 falls 0.100m over 25m, which is 1 in 250 against a 1 in 150 minimum.
    failures = {
        f.run_ref for f in result.findings
        if f.verdict == "fail" and f.rule_id == "grad-min-adoption-150"
    }
    assert failures == {"1.001"}


def test_the_planted_stated_gradient_disagreement_is_caught(result):
    warnings = {
        f.run_ref for f in result.findings
        if f.verdict == "warn" and f.rule_id == "internal-stated-vs-computed"
    }
    assert "1.001" in warnings


def test_the_planted_continuity_break_is_caught(result):
    # 1.002 leaves MH3 at 56.750, above the 56.700 arriving at it.
    failures = {
        f.run_ref for f in result.findings
        if f.verdict == "fail" and f.rule_id == "internal-invert-continuity"
    }
    assert failures == {"1.002"}


def test_the_sound_run_is_not_flagged(result):
    # It reads as not checked overall, correctly: the fixture's schedule states
    # no chamber sizes, so that rule abstains. What matters is that nothing
    # about the run itself was found wanting.
    flagged = [
        f for f in result.findings
        if f.run_ref == "1.000" and f.verdict in ("fail", "warn")
    ]
    assert flagged == []
    assert finding_verdict(result, "1.000", "grad-min-adoption-150") == "pass"
    assert finding_verdict(result, "1.000", "internal-stated-vs-computed") == "pass"


def finding_verdict(result, run_ref, rule_id):
    return next(
        f.verdict for f in result.findings
        if f.run_ref == run_ref and f.rule_id == rule_id
    )


def test_the_run_without_a_length_is_not_checked_rather_than_passed(result):
    assert result.run_verdicts["1.004"] == "not_checked"


def test_no_finding_ships_without_a_citation(result):
    for finding in result.findings:
        assert finding.citation.strip(), finding.rule_id


# ---------------------------------------------------------------------- report


def test_the_report_renders_with_the_findings_and_the_long_section(parsed, result):
    svg = longsection.render_svg(parsed, Network(parsed.runs), result)
    document = html.render(parsed, result, "synthetic_schedule.pdf", svg)
    assert "<svg" in document
    assert "1.001" in document
    assert "B6.9" in document
    assert "{{" not in document and "{%" not in document


def test_the_report_is_byte_identical_for_identical_input(parsed, result):
    # A check sheet is an audit record. Two runs of the same drawing that
    # differ by so much as a timestamp cannot be compared.
    network = Network(parsed.runs)
    svg = longsection.render_svg(parsed, network, result)
    first = html.render(parsed, result, "synthetic_schedule.pdf", svg)
    second = html.render(parsed, result, "synthetic_schedule.pdf", svg)
    assert first == second


def test_the_long_section_is_well_formed_xml(parsed, result):
    from xml.dom import minidom

    svg = longsection.render_svg(parsed, Network(parsed.runs), result)
    minidom.parseString(svg)


# ------------------------------------------------------------------------- cli


def test_the_cli_writes_a_report_and_exits_one_when_a_run_fails(drawing, tmp_path):
    out = tmp_path / "report.html"
    code = cli.main(
        [
            "check", str(drawing),
            "--regime", "adoption",
            "--dwellings", "12",
            "--out", str(out),
        ]
    )
    assert code == 1
    assert out.exists()
    assert "Drainage check sheet" in out.read_text()


def test_the_cli_refuses_a_missing_file(tmp_path):
    assert cli.main(["check", str(tmp_path / "nope.pdf"), "--regime", "adoption"]) == 2


def test_dry_run_prints_the_payload_and_sends_nothing(drawing, tmp_path, capsys):
    # The fixture parses deterministically, so a dry run should say so rather
    # than print a prompt: there is nothing a model would be sent.
    out = tmp_path / "report.html"
    cli.main(
        ["check", str(drawing), "--regime", "adoption", "--dry-run", "--out", str(out)]
    )
    assert "sk-ant" not in capsys.readouterr().out


def test_the_second_run_of_the_same_drawing_costs_nothing(drawing, tmp_path):
    from extract import template_cache

    out = tmp_path / "report.html"
    args = ["check", str(drawing), "--regime", "adoption", "--out", str(out)]
    cli.main(args)
    cli.main(args)
    # No model was ever called, so the ledger stays empty.
    assert template_cache.usage_total()["calls"] == 0


def test_the_ground_truth_file_matches_the_generator():
    # The committed JSON is what the scorer reads. If the generator changes and
    # the JSON is not regenerated, every accuracy number afterwards is wrong.
    committed = json.loads(
        (make_fixture.FIXTURES / "synthetic_schedule.json").read_text()
    )
    assert committed == json.loads(json.dumps(make_fixture.GROUND_TRUTH))
