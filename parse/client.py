"""The only module that talks to a model, and the only place tokens are spent.

One call for the whole table, never per row, with the response constrained to a
JSON schema. The Protocol exists so a locally hosted model can be substituted
without touching callers, and so --dry-run can print the payload without
sending it.

The model's only job here is turning an unfamiliar layout into records. It is
never asked whether anything complies. That judgement is deterministic Python
in check/engine.py and must stay there.
"""

import os
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from extract import template_cache
from extract.region import ScheduleRegion

# SPEC.md section 3.2: the cheapest model that passes the eval, because
# extraction is not reasoning. Override with INVERT_MODEL to try another.
DEFAULT_MODEL = "claude-haiku-4-5"

# US dollars per million tokens, input and output. Cached reads bill at roughly
# a tenth of the input rate. Checked against the published price list on
# 2026-09-30; a stale figure here only affects the reported cost, never a
# verdict, but it is worth re-checking when the README numbers are refreshed.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}
_CACHE_READ_MULTIPLIER = 0.1

_SYSTEM_PROMPT = """\
You read UK drainage drawing schedules and return structured records. You are a
transcriber, not an engineer. You never judge whether a design complies, and you
never correct a value you think is wrong.

Rules, in order of importance.

1. Transcribe only what the text states. If a value is absent, illegible or
   ambiguous, return null for it. Never infer a level from a gradient, a
   gradient from levels, or a diameter from context. A null is always better
   than a plausible guess, because a wrong number produces a wrong verdict that
   reads as authoritative.
2. source_row must be the verbatim text the record came from, so a disputed
   record can be traced back in seconds.
3. Set confidence to "low" when a cell was fused, split, unclear, or when you
   had to choose between readings. Otherwise "high".

Cell shapes that occur and what to do with them.

- "150Ø - 57.432" fuses a diameter and an invert level. Split it: diameter_mm
  150, invert 57.432.
- A chamber cell listing several inverts belongs in inverts_m as a list. Where
  the drawing states a depth it refers to the deepest invert.
- Levels appear bare or suffixed mAOD. Return the number only.
- References take many forms: FW1, S1/1, MH01, 1.000. Return them verbatim,
  including leading zeros and trailing decimals.
- Gradients appear as "1:150", "1 in 150" or a bare 150. Return the N only.
- A blank cell is null, not zero.
- chamber_size_mm is the plan size of the chamber itself, typically 1200mm or
  larger. It is not the pipe diameter. If the schedule has no chamber size
  column, every chamber_size_mm is null. Never copy a value from one field into
  another because the second has no column of its own.

Every pipe run needs a upstream and downstream node reference. If a row has no
identifiable node references it is not a pipe run, so leave it out.\
"""

_SCHEDULE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "runs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "us_node": {"type": "string"},
                    "ds_node": {"type": "string"},
                    "diameter_mm": {"type": ["integer", "null"]},
                    "length_m": {"type": ["number", "null"]},
                    "us_invert_m": {"type": ["number", "null"]},
                    "ds_invert_m": {"type": ["number", "null"]},
                    "stated_gradient_1_in": {"type": ["number", "null"]},
                    "source_row": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                },
                "required": [
                    "ref",
                    "us_node",
                    "ds_node",
                    "diameter_mm",
                    "length_m",
                    "us_invert_m",
                    "ds_invert_m",
                    "stated_gradient_1_in",
                    "source_row",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "manholes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "cover_level_m": {"type": ["number", "null"]},
                    "inverts_m": {"type": "array", "items": {"type": "number"}},
                    "chamber_size_mm": {"type": ["integer", "null"]},
                    "easting": {"type": ["number", "null"]},
                    "northing": {"type": ["number", "null"]},
                },
                "required": [
                    "ref",
                    "cover_level_m",
                    "inverts_m",
                    "chamber_size_mm",
                    "easting",
                    "northing",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["runs", "manholes"],
    "additionalProperties": False,
}


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


class DryRun(Exception):
    """Raised by DryRunClient. Carries nothing: the payload has been printed."""


class ModelClient(Protocol):
    def extract_schedule(
        self, region: ScheduleRegion, correction: str | None = None
    ) -> Completion: ...


def build_prompt(region: ScheduleRegion) -> tuple[str, str]:
    """Returns the cacheable system prompt and the per-drawing user prompt.

    The system prompt is byte-stable so it caches. Everything that varies with
    the drawing goes in the user prompt, after the cache breakpoint.
    """
    note = (
        "This region came from a ruled table, so the column order in the header "
        "row is reliable."
        if region.from_table
        else "This region came from raw text lines because no ruled table could "
        "be resolved. Column positions are approximate and you must work out "
        "the columns from the header and the shape of the values."
    )
    user = (
        f"{note}\n\n"
        f"Header row:\n{region.header_row}\n\n"
        f"Schedule region, page {region.page}:\n{region.text}"
    )
    return _SYSTEM_PROMPT, user


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> float:
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    input_rate, output_rate = rates
    fresh = max(input_tokens - cached_tokens, 0)
    return (
        fresh * input_rate
        + cached_tokens * input_rate * _CACHE_READ_MULTIPLIER
        + output_tokens * output_rate
    ) / 1_000_000


class AnthropicClient:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        import anthropic

        self.model = model or os.environ.get("INVERT_MODEL", DEFAULT_MODEL)
        # No key passed means the SDK resolves it from the environment, which is
        # where it belongs. Nothing here ever reads a key from a tracked file.
        self._client = (
            anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        )

    def extract_schedule(
        self, region: ScheduleRegion, correction: str | None = None
    ) -> Completion:
        system, user = build_prompt(region)
        if correction:
            user = f"{user}\n\n{correction}"

        response = self._client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": _SCHEDULE_SCHEMA}
            },
        )

        text = next(
            (block.text for block in response.content if block.type == "text"), ""
        )
        cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        usage = Usage(
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_hit=cached > 0,
            cost_usd=estimate_cost(
                self.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
                cached,
            ),
        )
        log_usage(usage)
        return Completion(json_text=text, usage=usage)


class DryRunClient:
    """Prints exactly what would be sent, sends nothing, abstains."""

    def __init__(self, stream=None) -> None:
        self.stream = stream or sys.stdout

    def extract_schedule(
        self, region: ScheduleRegion, correction: str | None = None
    ) -> Completion:
        system, user = build_prompt(region)
        print("--- system prompt ---", file=self.stream)
        print(system, file=self.stream)
        print("\n--- user prompt ---", file=self.stream)
        print(user, file=self.stream)
        if correction:
            print(f"\n{correction}", file=self.stream)
        print(
            f"\n--- end. {len(system) + len(user)} characters, nothing sent. ---",
            file=self.stream,
        )
        raise DryRun


def log_usage(usage: Usage) -> None:
    template_cache.record_usage(
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_hit=usage.cache_hit,
        cost_usd=usage.cost_usd,
    )
