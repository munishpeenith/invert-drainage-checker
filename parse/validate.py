"""Turn model output into validated records, or abstain.

One retry with the validation errors appended, then abstain. A malformed record
is never coerced into a valid-looking one.
"""

from parse.schema import Schedule


class AbstainedError(Exception):
    """The parse could not be validated. The caller reports, it does not guess."""


def validate(json_text: str) -> Schedule:
    raise NotImplementedError


def retry_prompt(json_text: str, errors: str) -> str:
    raise NotImplementedError
