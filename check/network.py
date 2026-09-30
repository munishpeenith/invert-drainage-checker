"""Order the runs into a network so continuity and chainage can be computed.

Invert continuity needs to know which run arrives at the node a given run
leaves, which means the runs have to be ordered from their node references
before any check that spans two runs can run at all.
"""

from parse.schema import PipeRun


class Network:
    def __init__(self, runs: list[PipeRun]) -> None:
        raise NotImplementedError

    def upstream_of(self, run: PipeRun) -> list[PipeRun]:
        raise NotImplementedError

    def chainage_m(self, run: PipeRun) -> float | None:
        """Cumulative length from the head of the branch, for the long section."""
        raise NotImplementedError

    def branches(self) -> list[list[PipeRun]]:
        raise NotImplementedError
