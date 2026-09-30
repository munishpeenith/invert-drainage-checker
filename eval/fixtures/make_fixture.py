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


# A second fixture whose header no synonym in parse/columns.py places, so
# infer_mapping returns None and the region goes to a model. This is the only
# way to exercise the model path, and it is deliberately awkward in the way
# real drawings are: the nodes are called chambers rather than manholes, the
# diameter is a bore, and nothing says US or DS.
AWKWARD_HEADER = [
    "Item",
    "Chamber Upper",
    "Chamber Lower",
    "Bore",
    "Run Length",
    "Invert Level Upper",
    "Invert Level Lower",
    "Gradient",
    "Cover Level",
]

AWKWARD_ROWS = [
    ["A1", "S1/1", "S1/2", "225Ø - 41.900", "32.40", "", "41.630", "1 in 120", "44.850"],
    ["A2", "S1/2", "S1/3", "225Ø - 41.630", "28.10", "", "41.400", "1 in 122", "44.600"],
    ["A3", "S1/3", "S1/4", "300Ø - 41.400", "19.75", "", "41.250", "1 in 132", "44.300"],
]

AWKWARD_GROUND_TRUTH = {
    "runs": [
        {
            "ref": "A1", "us_node": "S1/1", "ds_node": "S1/2", "diameter_mm": 225,
            "length_m": 32.40, "us_invert_m": 41.900, "ds_invert_m": 41.630,
            "stated_gradient_1_in": 120.0,
        },
        {
            "ref": "A2", "us_node": "S1/2", "ds_node": "S1/3", "diameter_mm": 225,
            "length_m": 28.10, "us_invert_m": 41.630, "ds_invert_m": 41.400,
            "stated_gradient_1_in": 122.0,
        },
        {
            "ref": "A3", "us_node": "S1/3", "ds_node": "S1/4", "diameter_mm": 300,
            "length_m": 19.75, "us_invert_m": 41.400, "ds_invert_m": 41.250,
            "stated_gradient_1_in": 132.0,
        },
    ],
    "expected": {
        "A1": "upstream invert is fused into the bore cell, not in its own column",
        "A2": "same, and the run is sound",
        "A3": "300mm, computed 1 in 131.7 against 1 in 132 stated, within rounding",
    },
}


def write_awkward_pdf(path: Path) -> Path:
    return _build(path, AWKWARD_HEADER, AWKWARD_ROWS, "SURFACE WATER DRAINAGE")


def write_pdf(path: Path) -> Path:
    return _build(path, HEADER, ROWS, "SYNTHETIC DRAINAGE LAYOUT, FOUL")


def _build(path: Path, header: list[str], rows: list[list[str]], title: str) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=landscape(A3))
    table = Table([header] + rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                # Ruled lines are what let pdfplumber resolve cells, which is
                # what keeps a fixture on the deterministic path.
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    document.build(
        [
            Paragraph(title, styles["Heading2"]),
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


def write_ground_truth(path: Path, truth: dict) -> Path:
    path.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n")
    return path


def main() -> int:
    for path in (
        write_pdf(FIXTURES / "synthetic_schedule.pdf"),
        write_ground_truth(FIXTURES / "synthetic_schedule.json", GROUND_TRUTH),
        write_awkward_pdf(FIXTURES / "awkward_schedule.pdf"),
        write_ground_truth(FIXTURES / "awkward_schedule.json", AWKWARD_GROUND_TRUTH),
    ):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
