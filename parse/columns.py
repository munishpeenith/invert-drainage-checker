"""Deterministic parsing of a ruled schedule once the columns are known.

This is the branch SPEC.md section 3 takes on a template cache hit, and it is
where most drawings should end up. A mapping of field to column index is either
inferred here from a recognisable header, or recalled from the cache having been
worked out by a model once. Either way the rows are then read by plain Python
and the extraction costs nothing.

Nothing here guesses. A cell that does not yield a number yields None, and a
row without both node references is not a pipe run and is dropped.
"""

import re

from parse.schema import Manhole, PipeRun, Schedule

ColumnMapping = dict[str, int]

# Header synonyms, longest and most specific first so "US IL" is not swallowed
# by "IL". Drawings are inconsistent about these and this list will grow; that
# is expected, and a header it cannot place falls through to the model.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ref": ("PIPE REF", "RUN REF", "PIPE NO", "REF", "RUN"),
    "us_node": ("US MH", "UPSTREAM MH", "US NODE", "FROM MH", "FROM", "US"),
    "ds_node": ("DS MH", "DOWNSTREAM MH", "DS NODE", "TO MH", "TO", "DS"),
    "diameter_mm": ("PIPE DIA", "DIAMETER", "DIA", "SIZE", "NOMINAL BORE"),
    "length_m": ("LENGTH", "PIPE LENGTH", "CHAINAGE"),
    "us_invert_m": ("US IL", "UPSTREAM INVERT", "US INVERT", "UPSTREAM IL"),
    "ds_invert_m": ("DS IL", "DOWNSTREAM INVERT", "DS INVERT", "DOWNSTREAM IL"),
    "stated_gradient_1_in": ("GRADIENT", "FALL", "SLOPE"),
    "cover_level_m": ("COVER LEVEL", "CL", "COVER"),
    "chamber_size_mm": ("CHAMBER SIZE", "MH SIZE", "CHAMBER"),
}

# The mapping is useless without these. Everything else is a bonus.
_ESSENTIAL = ("us_node", "ds_node")

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_GRADIENT = re.compile(r"1\s*(?::|IN)\s*(\d+(?:\.\d+)?)", re.I)


def infer_mapping(header: list[str]) -> ColumnMapping | None:
    """Map field names onto column indices from a recognisable header row.

    None when the header cannot be placed, which sends the region to a model.
    """
    cleaned = [_normalise(cell) for cell in header]
    mapping: ColumnMapping = {}
    taken: set[int] = set()

    for fieldname, synonyms in _SYNONYMS.items():
        for synonym in synonyms:
            for index, cell in enumerate(cleaned):
                if index in taken or not cell:
                    continue
                if cell == synonym or cell.startswith(synonym + " "):
                    mapping[fieldname] = index
                    taken.add(index)
                    break
            if fieldname in mapping:
                break

    if not all(key in mapping for key in _ESSENTIAL):
        return None
    return mapping


def apply_mapping(rows: list[list[str]], mapping: ColumnMapping) -> Schedule:
    """Read the body rows through a known mapping. The header row is skipped."""
    runs: list[PipeRun] = []
    chambers: dict[str, Manhole] = {}

    for row in rows[1:]:
        us_node = _cell(row, mapping.get("us_node"))
        ds_node = _cell(row, mapping.get("ds_node"))
        if not us_node or not ds_node:
            continue

        diameter, fused_invert = _diameter_and_invert(
            _cell(row, mapping.get("diameter_mm"))
        )
        us_invert = _number(_cell(row, mapping.get("us_invert_m")))
        if us_invert is None:
            us_invert = fused_invert

        runs.append(
            PipeRun(
                ref=_cell(row, mapping.get("ref")) or f"{us_node}-{ds_node}",
                us_node=us_node,
                ds_node=ds_node,
                diameter_mm=int(diameter) if diameter is not None else None,
                length_m=_number(_cell(row, mapping.get("length_m"))),
                us_invert_m=us_invert,
                ds_invert_m=_number(_cell(row, mapping.get("ds_invert_m"))),
                stated_gradient_1_in=_gradient(
                    _cell(row, mapping.get("stated_gradient_1_in"))
                ),
                source_row=" | ".join(cell for cell in row if cell),
                confidence="high",
            )
        )

        cover = _number(_cell(row, mapping.get("cover_level_m")))
        size = _number(_cell(row, mapping.get("chamber_size_mm")))
        if us_node not in chambers:
            chambers[us_node] = Manhole(
                ref=us_node,
                cover_level_m=cover,
                inverts_m=[us_invert] if us_invert is not None else [],
                chamber_size_mm=int(size) if size is not None else None,
                easting=None,
                northing=None,
            )
        elif cover is not None and chambers[us_node].cover_level_m is None:
            chambers[us_node].cover_level_m = cover

    return Schedule(runs=runs, manholes=list(chambers.values()))


def _normalise(cell: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", " ", (cell or "").upper())


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def _number(text: str) -> float | None:
    """First number in the cell, ignoring units such as mAOD and mm."""
    if not text:
        return None
    match = _NUMBER.search(text.replace(",", ""))
    return float(match.group()) if match else None


def _gradient(text: str) -> float | None:
    """N from "1:150", "1 in 150" or a bare 150."""
    if not text:
        return None
    match = _GRADIENT.search(text)
    if match:
        return float(match.group(1))
    return _number(text)


def _diameter_and_invert(text: str) -> tuple[float | None, float | None]:
    """Split the fused "150Ø - 57.432" shape SPEC.md section 3.2 warns about.

    A diameter is a whole number of millimetres and a level is a decimal in
    metres, so the two are told apart by shape rather than by position.
    """
    if not text:
        return None, None
    numbers = [float(match.group()) for match in _NUMBER.finditer(text)]
    diameter = next((n for n in numbers if n >= 50 and n == int(n)), None)
    invert = next((n for n in numbers if n != diameter and n != int(n)), None)
    return diameter, invert
