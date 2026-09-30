"""Render the check sheet. Deterministic, no model involvement.

A checking report is an audit record and must be byte-identical for identical
input, so nothing here may depend on time, ordering of a set, or a model.
"""

from pathlib import Path

from check.engine import Result
from parse.schema import Schedule


def render(
    schedule: Schedule,
    result: Result,
    drawing_name: str,
    long_section_svg: str,
) -> str:
    raise NotImplementedError


def write(html: str, out: Path) -> None:
    raise NotImplementedError
