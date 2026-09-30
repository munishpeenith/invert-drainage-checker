"""SQLite cache of column mappings and whole parses.

Two keys. The template key is a fingerprint of the header row plus the title
block originator, and returns the column mapping a model previously worked out.
The content key is a hash of the extracted table text, and returns the parse
outright. Together they make model cost a function of new drawing formats
rather than of drawings.
"""

from pathlib import Path

from parse.schema import Schedule

ColumnMapping = dict[str, int]

DEFAULT_DB = Path.home() / ".invert" / "cache.sqlite"


def template_key(header_row: str, originator: str | None) -> str:
    raise NotImplementedError


def content_key(table_text: str) -> str:
    raise NotImplementedError


def get_mapping(key: str, db: Path = DEFAULT_DB) -> ColumnMapping | None:
    raise NotImplementedError


def put_mapping(key: str, mapping: ColumnMapping, db: Path = DEFAULT_DB) -> None:
    raise NotImplementedError


def get_parse(key: str, db: Path = DEFAULT_DB) -> Schedule | None:
    raise NotImplementedError


def put_parse(key: str, schedule: Schedule, db: Path = DEFAULT_DB) -> None:
    raise NotImplementedError
