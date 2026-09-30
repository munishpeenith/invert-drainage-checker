"""Turn model output into validated records, or abstain.

One retry with the validation errors appended, then abstain. A malformed record
is never coerced into a valid-looking one, because a record that has been
quietly repaired is indistinguishable from one that was read correctly, and
every verdict downstream inherits the repair.
"""

import json

from pydantic import ValidationError

from extract.region import ScheduleRegion
from parse.client import ModelClient
from parse.schema import Schedule


class AbstainedError(Exception):
    """The parse could not be validated. The caller reports, it does not guess."""


def validate(json_text: str) -> Schedule:
    return Schedule.model_validate_json(json_text)


def retry_prompt(json_text: str, errors: str) -> str:
    return (
        "Your previous reply did not validate. Correct it and return the whole "
        "schedule again.\n\n"
        f"Previous reply:\n{json_text}\n\n"
        f"Validation errors:\n{errors}\n\n"
        "Where a value cannot be read, return null for it. Do not invent a "
        "value to satisfy the schema."
    )


def parse_schedule(client: ModelClient, region: ScheduleRegion) -> Schedule:
    """One call, one retry on validation failure, then abstain."""
    completion = client.extract_schedule(region)
    try:
        return validate(completion.json_text)
    except ValidationError as first_error:
        correction = retry_prompt(completion.json_text, _readable(first_error))

    retried = client.extract_schedule(region, correction=correction)
    try:
        return validate(retried.json_text)
    except ValidationError as second_error:
        raise AbstainedError(
            "The schedule could not be parsed into valid records after one "
            f"retry. Last validation errors:\n{_readable(second_error)}"
        ) from second_error


def sanity(schedule: Schedule) -> tuple[Schedule, list[str]]:
    """Null values that are physically impossible, and say what was dropped.

    A value that cannot exist is evidence the parse is wrong, not evidence the
    design is wrong. The difference matters: left in place, an impossible value
    produces a confident failure against a real clause, and the engineer sent
    to check it finds a drawing that says no such thing.

    This is not a compliance check and must not become one. A chamber narrower
    than the pipe entering it is impossible and is dropped here. A chamber
    wider than its pipe but below the standard minimum is a genuine failure and
    is left alone for check/engine.py to find.

    Written because Haiku 4.5, given a schedule with no chamber size column,
    copied the pipe diameter into chamber_size_mm and produced three false
    failures. The prompt now forbids it. This is here because a prompt is an
    instruction and not an enforcement.
    """
    notes: list[str] = []

    largest_pipe: dict[str, int] = {}
    for run in schedule.runs:
        if run.diameter_mm is None:
            continue
        for node in (run.us_node, run.ds_node):
            largest_pipe[node] = max(largest_pipe.get(node, 0), run.diameter_mm)

    for chamber in schedule.manholes:
        pipe = largest_pipe.get(chamber.ref)
        if (
            chamber.chamber_size_mm is not None
            and pipe is not None
            and chamber.chamber_size_mm <= pipe
        ):
            notes.append(
                f"{chamber.ref}: chamber size {chamber.chamber_size_mm}mm is not "
                f"larger than the {pipe}mm pipe at it, so it cannot be a chamber "
                "size. Dropped, and the chamber rules will report not checked."
            )
            chamber.chamber_size_mm = None

        if chamber.cover_level_m is not None:
            above = [level for level in chamber.inverts_m if level > chamber.cover_level_m]
            if above:
                notes.append(
                    f"{chamber.ref}: invert {max(above):.3f} is above cover level "
                    f"{chamber.cover_level_m:.3f}. Cover level dropped."
                )
                chamber.cover_level_m = None

    for run in schedule.runs:
        if run.length_m is not None and run.length_m <= 0:
            notes.append(f"{run.ref}: length {run.length_m} is not positive. Dropped.")
            run.length_m = None
        if run.diameter_mm is not None and run.diameter_mm <= 0:
            notes.append(f"{run.ref}: diameter {run.diameter_mm} is not positive. Dropped.")
            run.diameter_mm = None

    return schedule, notes


def _readable(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"])
        lines.append(f"{where}: {item['msg']}")
    return "\n".join(lines)


def to_json(schedule: Schedule) -> str:
    return json.dumps(schedule.model_dump(), indent=2, sort_keys=True)
