"""pdfplumber wrapper: words with coordinates, and table extraction per page."""

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


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

    def lines(self, tolerance: float = 2.5) -> list[str]:
        """Words grouped into visual rows, for the fallback path in region.py."""
        rows: list[tuple[float, list[Word]]] = []
        for word in sorted(self.words, key=lambda w: (w.top, w.x0)):
            for top, bucket in rows:
                if abs(word.top - top) <= tolerance:
                    bucket.append(word)
                    break
            else:
                rows.append((word.top, [word]))
        return [
            " ".join(w.text for w in sorted(bucket, key=lambda w: w.x0))
            for _, bucket in rows
        ]


class ScannedPdfError(Exception):
    """Raised when a page yields no text. v1 refuses rather than guessing."""


def read_pages(path: Path) -> list[Page]:
    pages: list[Page] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            words = [
                Word(
                    text=word["text"],
                    x0=float(word["x0"]),
                    x1=float(word["x1"]),
                    top=float(word["top"]),
                    bottom=float(word["bottom"]),
                    page=number,
                )
                for word in page.extract_words()
            ]
            pages.append(
                Page(number=number, words=words, tables=page.extract_tables() or [])
            )

    if not any(page.words for page in pages):
        raise ScannedPdfError(
            f"{path.name} contains no extractable text, so it is a scan. "
            "Invert does not read scanned drawings. Supply the vector PDF the "
            "drawing was issued from."
        )
    return pages
