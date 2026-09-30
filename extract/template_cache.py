"""SQLite cache of column mappings and whole parses, and the token ledger.

Two keys. The template key is a fingerprint of the header row plus the title
block originator, and returns the column mapping a model previously worked out.
The content key is a hash of the extracted table text, and returns the parse
outright. Together they make model cost a function of new drawing formats
rather than of drawings: a consultancy issuing forty revisions of one drawing
set pays for one extraction.

The usage table lives here too, because cost is a design concern and the
README reports it.
"""

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from parse.schema import Schedule

ColumnMapping = dict[str, int]

DEFAULT_DB = Path.home() / ".invert" / "cache.sqlite"


def resolve(db: Path | None = None) -> Path:
    """Explicit path, else INVERT_DB, else the default under the home directory.

    Resolved per call rather than at import, so a test can point the cache
    somewhere disposable without the import order mattering.
    """
    if db is not None:
        return db
    override = os.environ.get("INVERT_DB")
    return Path(override) if override else DEFAULT_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS template (
    key TEXT PRIMARY KEY,
    mapping TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parsed (
    key TEXT PRIMARY KEY,
    schedule TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    cost_usd REAL NOT NULL
);
"""


@contextmanager
def connect(db: Path | None = None):
    db = resolve(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    try:
        connection.executescript(_SCHEMA)
        yield connection
        connection.commit()
    finally:
        connection.close()


def _normalise(text: str) -> str:
    """Collapse whitespace and case so cosmetic edits do not miss the cache."""
    return re.sub(r"\s+", " ", text).strip().upper()


def template_key(header_row: str, originator: str | None) -> str:
    material = f"{_normalise(header_row)}||{_normalise(originator or '')}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def content_key(table_text: str) -> str:
    return hashlib.sha256(_normalise(table_text).encode("utf-8")).hexdigest()


def get_mapping(key: str, db: Path | None = None) -> ColumnMapping | None:
    with connect(db) as connection:
        row = connection.execute(
            "SELECT mapping FROM template WHERE key = ?", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def put_mapping(key: str, mapping: ColumnMapping, db: Path | None = None) -> None:
    with connect(db) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO template (key, mapping) VALUES (?, ?)",
            (key, json.dumps(mapping, sort_keys=True)),
        )


def get_parse(key: str, db: Path | None = None) -> Schedule | None:
    with connect(db) as connection:
        row = connection.execute(
            "SELECT schedule FROM parsed WHERE key = ?", (key,)
        ).fetchone()
    return Schedule.model_validate_json(row[0]) if row else None


def put_parse(key: str, schedule: Schedule, db: Path | None = None) -> None:
    with connect(db) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO parsed (key, schedule) VALUES (?, ?)",
            (key, schedule.model_dump_json()),
        )


def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool,
    cost_usd: float,
    db: Path | None = None,
) -> None:
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO usage (model, input_tokens, output_tokens, cache_hit, "
            "cost_usd) VALUES (?, ?, ?, ?, ?)",
            (model, input_tokens, output_tokens, int(cache_hit), cost_usd),
        )


def usage_total(db: Path | None = None) -> dict[str, float]:
    with connect(db) as connection:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0), COALESCE(SUM(cost_usd), 0) FROM usage"
        ).fetchone()
    return {
        "calls": row[0],
        "input_tokens": row[1],
        "output_tokens": row[2],
        "cost_usd": row[3],
    }
