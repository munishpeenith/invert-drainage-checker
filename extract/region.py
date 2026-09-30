"""Locate the schedule region on a page and crop to it.

Cropping before any model call is the first and largest saving in the token
strategy, so this module decides what a model is allowed to see.
"""

from dataclasses import dataclass

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


@dataclass
class ScheduleRegion:
    page: int
    text: str
    header_row: str
    from_table: bool
    """False when extract_tables found nothing usable and raw lines were used."""


def find_schedule(pages: list[Page]) -> list[ScheduleRegion]:
    raise NotImplementedError
