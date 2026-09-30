"""Plain SVG long section: chainage along x, levels up y, runs coloured by verdict.

A misread level shows as a pipe running the wrong way, so the drawing doubles
as a check on the parser.
"""

from check.engine import Result
from check.network import Network
from parse.schema import Schedule


def render_svg(schedule: Schedule, network: Network, result: Result) -> str:
    raise NotImplementedError
