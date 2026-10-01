"""Locate the schedule region on a page and crop to it.

Cropping before any model call is the first and largest saving in the token
strategy, so this module decides what a model is allowed to see. Sending the
schedule region rather than the whole page typically removes most of the
payload, and the part it removes is the title block, the notes and the drawn
geometry, none of which the parser wants.

Two paths exist and the record says which was taken. extract_tables gives ruled
cells and is what a well-formed schedule yields. Where the schedule is drawn
with lines that pdfplumber cannot resolve into a table, the fallback keeps the
raw text rows and leaves more work to the model.
"""

import re
from dataclasses import dataclass, field

from extract.pdf_text import Page

HEADER_KEYWORDS: tuple[str, ...] = (
    "MH REFERENCE",
    "INVERT",
    "COVER",
    "GRADIENT",
    "US IL",
    "DS IL",
    "LENGTH",
)

# Enough keywords to be a schedule header rather than a stray note.
_MIN_KEYWORDS = 2

_ORIGINATOR = re.compile(
    r"(?:drawn|originator|client|consultant)\s*[:\-]?\s*(.{2,40})", re.I
)


@dataclass
class ScheduleRegion:
    page: int
    text: str
    header_row: str
    from_table: bool
    """False when extract_tables found nothing usable and raw lines were used."""
    rows: list[list[str]] = field(default_factory=list)
    """Cells, header first, when they came from a ruled table.

    Empty on the fallback path. A deterministic parse needs real cell
    boundaries, and guessing them from spacing is how columns get swapped, so
    the fallback goes to the model instead.
    """


def _score(text: str) -> int:
    upper = text.upper()
    return sum(1 for keyword in HEADER_KEYWORDS if keyword in upper)


def _row_text(row: list[str | None]) -> str:
    return " | ".join((cell or "").replace("\n", " ").strip() for cell in row)


def find_schedule(pages: list[Page]) -> list[ScheduleRegion]:
    """Every region on every page that looks like a schedule, best first."""
    regions: list[ScheduleRegion] = []

    for page in pages:
        for table in page.tables:
            if not table:
                continue
            header_index = _best_row(table)
            if header_index is None:
                continue
            header = _row_text(table[header_index])
            cells = [
                [(cell or "").replace("\n", " ").strip() for cell in row]
                for row in table[header_index:]
                if any(row)
            ]
            if len(cells) < 2:
                # Header and nothing under it. A real drawing sheet carries
                # several tables, and on the Copeland sample the merged banner
                # spanning two side-by-side schedules scores highest on keywords
                # while holding no data at all. A region with no body rows is
                # not a schedule, whatever its header says.
                continue
            body = [_row_text(row) for row in table[header_index:] if any(row)]
            regions.append(
                ScheduleRegion(
                    page=page.number,
                    text="\n".join(body),
                    header_row=header,
                    from_table=True,
                    rows=cells,
                )
            )

    if regions:
        # Keyword score first, then the region carrying the most rows, so a
        # fragment never beats the full schedule it was cut from.
        return sorted(
            regions, key=lambda r: (_score(r.header_row), len(r.rows)), reverse=True
        )

    # Fallback. No usable table anywhere, so keep the text rows from the header
    # down and let the model work out the columns.
    for page in pages:
        lines = page.lines()
        scores = [_score(line) for line in lines]
        if not scores or max(scores) < _MIN_KEYWORDS:
            continue
        start = scores.index(max(scores))
        body = _take_while_tabular(lines[start:])
        regions.append(
            ScheduleRegion(
                page=page.number,
                text="\n".join(body),
                header_row=lines[start],
                from_table=False,
            )
        )

    return sorted(regions, key=lambda r: _score(r.header_row), reverse=True)


def _best_row(table: list[list[str | None]]) -> int | None:
    """Index of the header row, or None when no row names enough columns."""
    best_index, best_score = None, 0
    for index, row in enumerate(table[:5]):
        score = _score(_row_text(row))
        if score > best_score:
            best_index, best_score = index, score
    return best_index if best_score >= _MIN_KEYWORDS else None


def _take_while_tabular(lines: list[str]) -> list[str]:
    """Header plus the rows under it, stopping where the table clearly ends."""
    kept = [lines[0]]
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            break
        # A schedule row carries numbers. Two blank-of-digits lines in a row
        # means the notes have started.
        if not any(character.isdigit() for character in stripped):
            break
        kept.append(line)
    return kept


def originator(pages: list[Page]) -> str | None:
    """Title block originator, used to key the template cache.

    Best effort. None is a valid answer and simply makes the cache key weaker.
    """
    for page in pages:
        for line in page.lines():
            match = _ORIGINATOR.search(line)
            if match:
                return match.group(1).strip()
    return None
