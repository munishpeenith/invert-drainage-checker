"""Order the runs into a network so continuity and chainage can be computed.

Invert continuity needs to know which run arrives at the node a given run
leaves, which means the runs have to be ordered from their node references
before any check that spans two runs can run at all.

A schedule is not guaranteed to describe a sane network. References can be
misread, and a drawing can genuinely contain a loop. Every traversal here is
guarded against cycles and returns None rather than raising, so a malformed
network degrades to not checked instead of taking the run down.
"""

from collections import defaultdict

from parse.schema import PipeRun


class Network:
    def __init__(self, runs: list[PipeRun]) -> None:
        self.runs = list(runs)
        self._arriving_at: dict[str, list[PipeRun]] = defaultdict(list)
        self._leaving_from: dict[str, list[PipeRun]] = defaultdict(list)
        for run in self.runs:
            self._arriving_at[run.ds_node].append(run)
            self._leaving_from[run.us_node].append(run)
        self._chainage: dict[str, float | None] = {}

    def upstream_of(self, run: PipeRun) -> list[PipeRun]:
        """Runs that discharge into the node this run leaves."""
        return list(self._arriving_at.get(run.us_node, []))

    def downstream_of(self, run: PipeRun) -> list[PipeRun]:
        return list(self._leaving_from.get(run.ds_node, []))

    def at_node(self, node: str) -> list[PipeRun]:
        return list(self._arriving_at.get(node, [])) + list(
            self._leaving_from.get(node, [])
        )

    def heads(self) -> list[PipeRun]:
        return [run for run in self.runs if not self.upstream_of(run)]

    def outfalls(self) -> list[PipeRun]:
        return [run for run in self.runs if not self.downstream_of(run)]

    def chainage_m(self, run: PipeRun) -> float | None:
        """Distance to this run's upstream end from the head of its branch.

        Where several branches meet, the longest path wins, which is what puts
        a junction at one chainage on the long section. None when any length on
        the path is missing, or when the path loops.
        """
        return self._chainage_for(run, set())

    def branches(self) -> list[list[PipeRun]]:
        """One path per head run, following the network down to an outfall."""
        paths: list[list[PipeRun]] = []
        for head in self.heads():
            path = [head]
            seen = {id(head)}
            current = head
            while True:
                onward = self.downstream_of(current)
                if not onward:
                    break
                current = onward[0]
                if id(current) in seen:
                    break
                path.append(current)
                seen.add(id(current))
            paths.append(path)
        return paths

    def _chainage_for(self, run: PipeRun, visiting: set[int]) -> float | None:
        key = run.ref
        if key in self._chainage:
            return self._chainage[key]
        if id(run) in visiting:
            return None
        visiting.add(id(run))
        upstream = self.upstream_of(run)
        if not upstream:
            value: float | None = 0.0
        else:
            value = None
            for feeder in upstream:
                if feeder.length_m is None:
                    value = None
                    break
                reach = self._chainage_for(feeder, visiting)
                if reach is None:
                    value = None
                    break
                candidate = reach + feeder.length_m
                value = candidate if value is None else max(value, candidate)
        visiting.discard(id(run))
        self._chainage[key] = value
        return value
