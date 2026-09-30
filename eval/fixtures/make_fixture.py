"""Generate a synthetic drainage schedule PDF and its ground truth.

Real drawings cannot be committed, and the public planning portal drawings that
can be are not reproducible in a test run. This generator gives the test suite
a drawing with known contents, including deliberate faults, so the whole
pipeline can be exercised without a real project drawing and without a model.

It is a stand-in for the eval fixtures, not a substitute. The measured accuracy
the README reports must come from real drawings, because a synthetic table is
laid out exactly the way the parser expects and proves nothing about the ones
that are not.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent

HEADER = [
    "Pipe Ref",
    "US MH",
    "DS MH",
    "Pipe Dia",
    "Length (m)",
    "US IL",
    "DS IL",
    "Gradient",
    "Cover Level",
]

# Each row carries a known verdict, listed in the ground truth below.
ROWS = [
    ["1.000", "MH1", "MH2", "150", "30.00", "57.000", "56.800", "1:150", "60.000"],
    ["1.001", "MH2", "MH3", "150", "25.00", "56.800", "56.700", "1:150", "59.750"],
    ["1.002", "MH3", "MH4", "150", "20.00", "56.750", "56.600", "1:133", "59.500"],
    ["1.003", "MH4", "MH5", "225", "18.00", "56.600", "56.450", "1:120", "59.250"],
    ["1.004", "MH5", "MH6", "225", "", "56.450", "56.300", "1:100", "59.000"],
]

GROUND_TRUTH = {
    "runs": [
        {
            "ref": row[0],
            "us_node": row[1],
            "ds_node": row[2],
            "diameter_mm": int(row[3]),
            "length_m": float(row[4]) if row[4] else None,
            "us_invert_m": float(row[5]),
            "ds_invert_m": float(row[6]),
            "stated_gradient_1_in": float(row[7].split(":")[1]),
        }
        for row in ROWS
    ],
    "expected": {
        "1.000": "sound, 1 in 150 exactly",
        "1.001": "1 in 250 computed against 1 in 150 stated, too flat and inconsistent",
        "1.002": "leaves MH3 at 56.750 above the 56.700 arriving, continuity break",
        "1.003": "225mm, outside the 150mm gradient rule",
        "1.004": "no length stated, so no gradient can be computed",
    },
}


def write_pdf(path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=landscape(A3))
    table = Table([HEADER] + ROWS, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                # Ruled lines are what let pdfplumber resolve cells, which is
                # what keeps this fixture on the deterministic path.
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    document.build(
        [
            Paragraph("SYNTHETIC DRAINAGE LAYOUT, FOUL", styles["Heading2"]),
            Paragraph(
                "Drawn: Invert test fixture. Not a real drawing and not from "
                "any planning portal.",
                styles["Normal"],
            ),
            Spacer(1, 12),
            Paragraph("MANHOLE AND PIPE SCHEDULE", styles["Heading3"]),
            table,
            Spacer(1, 12),
            Paragraph(
                "ALL DIMENSIONS IN MILLIMETERS UNLESS NOTED AND NOT TO BE "
                "SCALED FROM DRAWINGS",
                styles["Normal"],
            ),
        ]
    )
    return path


def write_ground_truth(path: Path) -> Path:
    path.write_text(json.dumps(GROUND_TRUTH, indent=2, sort_keys=True) + "\n")
    return path


def main() -> int:
    pdf = write_pdf(FIXTURES / "synthetic_schedule.pdf")
    truth = write_ground_truth(FIXTURES / "synthetic_schedule.json")
    print(f"wrote {pdf}")
    print(f"wrote {truth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
