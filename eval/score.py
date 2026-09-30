"""Field-level extraction accuracy against hand-written ground truth.

Reports the five numbers the README carries: extraction accuracy, abstention
rate, false positives on checks, cost per drawing cold and cached, and latency
cold and cached. Built before anything is tuned.
"""

from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class Score:
    fields_total: int
    fields_correct: int
    abstained: int
    abstained_wrongly: int
    cost_usd_cold: float
    cost_usd_cached: float
    latency_s_cold: float
    latency_s_cached: float


def score_all(fixtures: Path = FIXTURES) -> Score:
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
