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


def _readable(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"])
        lines.append(f"{where}: {item['msg']}")
    return "\n".join(lines)


def to_json(schedule: Schedule) -> str:
    return json.dumps(schedule.model_dump(), indent=2, sort_keys=True)
