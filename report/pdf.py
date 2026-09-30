"""Optional PDF rendering of the check sheet via reportlab."""

from pathlib import Path

from check.engine import Result
from parse.schema import Schedule


def render(
    schedule: Schedule, result: Result, drawing_name: str, out: Path
) -> None:
    raise NotImplementedError
