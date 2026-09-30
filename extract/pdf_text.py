"""pdfplumber wrapper: words with coordinates, and table extraction per page."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int


@dataclass
class Page:
    number: int
    words: list[Word]
    tables: list[list[list[str | None]]]


class ScannedPdfError(Exception):
    """Raised when a page yields no text. v1 refuses rather than guessing."""


def read_pages(path: Path) -> list[Page]:
    raise NotImplementedError
