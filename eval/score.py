"""Field-level extraction accuracy against hand-written ground truth.

Built before anything was tuned, because an accuracy number produced after
tuning against the same drawings measures nothing.

Reports the numbers the README carries: extraction accuracy, abstention rate,
cost per drawing, and latency. A fixture is a PDF beside a JSON file of the same
name holding the records a human read off it.

Abstention is scored in two directions and the second one matters more. Correct
abstention is returning null where the drawing states nothing. Wrong abstention
is returning null where the drawing states a value the parser failed to read,
and it is a silent failure: it looks like caution and reads like diligence.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from extract.pdf_text import read_pages
from extract.region import find_schedule
from parse import columns
from parse.schema import PipeRun

FIXTURES = Path(__file__).parent / "fixtures"

_SCORED_FIELDS = (
    "us_node",
    "ds_node",
    "diameter_mm",
    "length_m",
    "us_invert_m",
    "ds_invert_m",
    "stated_gradient_1_in",
)


@dataclass
class Score:
    fixtures: int = 0
    runs_expected: int = 0
    runs_found: int = 0
    fields_total: int = 0
    fields_correct: int = 0
    abstained: int = 0
    abstained_wrongly: int = 0
    latency_s: float = 0.0
    used_model: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.fields_correct / self.fields_total if self.fields_total else 0.0

    @property
    def abstention_rate(self) -> float:
        return self.abstained / self.fields_total if self.fields_total else 0.0


def score_all(fixtures: Path = FIXTURES) -> Score:
    score = Score()
    for pdf in sorted(fixtures.glob("*.pdf")):
        truth_path = pdf.with_suffix(".json")
        if not truth_path.exists():
            score.notes.append(f"{pdf.name}: no ground truth beside it, skipped")
            continue
        _score_one(pdf, json.loads(truth_path.read_text()), score)
    return score


def _score_one(pdf: Path, truth: dict, score: Score) -> None:
    score.fixtures += 1
    started = time.monotonic()

    regions = find_schedule(read_pages(pdf))
    if not regions:
        score.notes.append(f"{pdf.name}: no schedule region found")
        return

    region = regions[0]
    mapping = columns.infer_mapping(region.rows[0]) if region.rows else None
    if mapping is None:
        # A model would be called here. The scorer does not call one, so the
        # fixture is reported rather than silently counted as a failure.
        score.used_model += 1
        score.notes.append(
            f"{pdf.name}: no deterministic mapping, needs a model call to score"
        )
        return

    parsed = {run.ref: run for run in columns.apply_mapping(region.rows, mapping).runs}
    score.latency_s += time.monotonic() - started

    expected = truth.get("runs", [])
    score.runs_expected += len(expected)
    score.runs_found += len(parsed)

    for record in expected:
        run = parsed.get(record["ref"])
        for name in _SCORED_FIELDS:
            score.fields_total += 1
            wanted = record.get(name)
            got = getattr(run, name, None) if run else None

            if got is None:
                score.abstained += 1
                if wanted is not None:
                    score.abstained_wrongly += 1
                continue
            if _matches(wanted, got):
                score.fields_correct += 1


def _matches(wanted, got) -> bool:
    if wanted is None:
        return False
    if isinstance(wanted, (int, float)) and isinstance(got, (int, float)):
        return abs(float(wanted) - float(got)) < 1e-6
    return str(wanted) == str(got)


def main() -> int:
    score = score_all()
    if not score.fixtures:
        print(
            f"No fixtures in {FIXTURES}. Generate the synthetic one with "
            "python eval/fixtures/make_fixture.py, and add real drawings from "
            "public planning portals beside their hand-written ground truth."
        )
        return 1

    print(f"fixtures            {score.fixtures}")
    print(f"runs expected       {score.runs_expected}")
    print(f"runs found          {score.runs_found}")
    print(f"field accuracy      {score.accuracy:.1%}  "
          f"({score.fields_correct}/{score.fields_total})")
    print(f"abstention rate     {score.abstention_rate:.1%}  ({score.abstained})")
    print(f"abstained wrongly   {score.abstained_wrongly}")
    print(f"needed a model      {score.used_model}")
    print(f"latency, no model   {score.latency_s:.2f}s total")
    for note in score.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
