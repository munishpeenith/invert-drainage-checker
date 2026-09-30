"""Optional PDF rendering of the check sheet via reportlab.

The same records and the same verdicts as the HTML, laid out for printing and
for attaching to a transmittal. Deterministic for the same reason: it is an
audit record.
"""

from pathlib import Path

from check.engine import Result
from parse.schema import Schedule
from report.html import VERDICT_LABELS
from report.longsection import VERDICT_COLOURS

_COLUMNS = [
    "Run",
    "From",
    "To",
    "Dia",
    "Length",
    "US IL",
    "DS IL",
    "Computed",
    "Stated",
    "Verdict",
]


def render(
    schedule: Schedule, result: Result, drawing_name: str, out: Path
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Drainage check sheet", styles["Heading1"]),
        Paragraph(drawing_name, styles["Heading3"]),
        Paragraph(
            f"Regime: {result.regime}. Rule set {result.pack} v"
            f"{result.pack_version}, verified {result.pack_last_verified}.",
            styles["Normal"],
        ),
        Spacer(1, 6),
        Paragraph(
            "Every verdict is a comparison against the rule set named above. "
            "No finding is a substitute for a chartered engineer's review.",
            styles["Italic"],
        ),
        Spacer(1, 14),
    ]

    rows = [_COLUMNS]
    styling = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5dbe3")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f7")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (3, 1), (-2, -1), "RIGHT"),
    ]
    for index, run in enumerate(schedule.runs, start=1):
        facts = result.run_facts.get(run.ref, {})
        verdict = result.run_verdicts.get(run.ref, "not_checked")
        rows.append(
            [
                run.ref,
                run.us_node,
                run.ds_node,
                _plain(run.diameter_mm, 0),
                _plain(run.length_m, 2),
                _plain(run.us_invert_m, 3),
                _plain(run.ds_invert_m, 3),
                _gradient(facts.get("computed_gradient_1_in")),
                _gradient(run.stated_gradient_1_in),
                VERDICT_LABELS[verdict],
            ]
        )
        styling.append(
            (
                "TEXTCOLOR",
                (9, index),
                (9, index),
                colors.HexColor(VERDICT_COLOURS[verdict]),
            )
        )

    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle(styling))
    story.append(table)

    findings = [f for f in result.findings if f.verdict in ("fail", "warn")]
    story.append(PageBreak())
    story.append(Paragraph("Findings", styles["Heading2"]))
    if not findings:
        story.append(
            Paragraph("No run failed a check and none needs verifying.", styles["Normal"])
        )
    for finding in findings:
        story.append(
            Paragraph(
                f"<b>{VERDICT_LABELS[finding.verdict]} &middot; {finding.run_ref}</b> "
                f"({finding.rule_id})",
                styles["Normal"],
            )
        )
        story.append(Paragraph(finding.message, styles["Normal"]))
        story.append(Paragraph(f"<i>{finding.citation}</i>", styles["Normal"]))
        story.append(Spacer(1, 8))

    SimpleDocTemplate(str(out), pagesize=landscape(A4)).build(story)


def _plain(value, places: int) -> str:
    return "" if value is None else f"{value:.{places}f}"


def _gradient(value: float | None) -> str:
    return "" if value is None else f"1 in {value:.1f}"
