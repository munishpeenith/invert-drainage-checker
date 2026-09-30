"""The only module that talks to a model, and the only place tokens are spent.

One call for the whole table, never per row. The Protocol exists so a locally
hosted model can be substituted for the hosted one without touching callers,
and so --dry-run can print the payload without sending it.
"""

from dataclasses import dataclass
from typing import Protocol

from extract.region import ScheduleRegion


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool
    cost_usd: float


@dataclass
class Completion:
    json_text: str
    usage: Usage


class ModelClient(Protocol):
    def extract_schedule(self, region: ScheduleRegion) -> Completion: ...


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        raise NotImplementedError

    def extract_schedule(self, region: ScheduleRegion) -> Completion:
        raise NotImplementedError


class DryRunClient:
    """Prints exactly what would be sent, sends nothing, abstains."""

    def extract_schedule(self, region: ScheduleRegion) -> Completion:
        raise NotImplementedError


def build_prompt(region: ScheduleRegion) -> tuple[str, str]:
    """Returns the cacheable system prompt and the per-drawing user prompt."""
    raise NotImplementedError


def log_usage(usage: Usage) -> None:
    raise NotImplementedError
