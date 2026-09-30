"""Plain SVG long section: chainage along x, levels up y, runs coloured by verdict.

A misread level shows as a pipe running the wrong way, so the drawing doubles
as a check on the parser. That is the reason it is worth drawing at all, and
the reason it is drawn from the parsed records rather than from the PDF.

Deterministic. Coordinates are rounded to one decimal place before they reach
the output, so the same records always produce the same bytes.
"""

from dataclasses import dataclass
from xml.sax.saxutils import escape

from check.engine import Result, Verdict
from check.network import Network
from parse.schema import Schedule

VERDICT_COLOURS: dict[Verdict, str] = {
    "fail": "#b02a1f",
    "warn": "#c07a12",
    "pass": "#1c7a45",
    "not_checked": "#6b7280",
    "not_supported": "#6b7280",
}

_WIDTH = 900.0
_HEIGHT = 260.0
_MARGIN_LEFT = 62.0
_MARGIN_RIGHT = 18.0
_MARGIN_TOP = 18.0
_MARGIN_BOTTOM = 42.0


@dataclass
class _Segment:
    ref: str
    x_start: float
    x_end: float
    level_start: float
    level_end: float
    verdict: Verdict


@dataclass
class _Node:
    ref: str
    chainage: float
    invert: float
    cover: float | None


def render_svg(schedule: Schedule, network: Network, result: Result) -> str:
    """One panel per branch. Returns an empty string when nothing is drawable."""
    covers = {
        chamber.ref: chamber.cover_level_m
        for chamber in schedule.manholes
        if chamber.cover_level_m is not None
    }
    panels = [
        panel
        for branch in network.branches()
        if (panel := _render_branch(branch, network, result, covers))
    ]
    if not panels:
        return ""
    return "\n".join(panels)


def _render_branch(branch, network, result, covers) -> str:
    segments: list[_Segment] = []
    nodes: dict[str, _Node] = {}

    for run in branch:
        chainage = network.chainage_m(run)
        if (
            chainage is None
            or run.length_m is None
            or run.us_invert_m is None
            or run.ds_invert_m is None
        ):
            # A run that cannot be placed is left out rather than guessed at.
            continue
        end = chainage + run.length_m
        segments.append(
            _Segment(
                ref=run.ref,
                x_start=chainage,
                x_end=end,
                level_start=run.us_invert_m,
                level_end=run.ds_invert_m,
                verdict=result.run_verdicts.get(run.ref, "not_checked"),
            )
        )
        nodes.setdefault(
            run.us_node,
            _Node(run.us_node, chainage, run.us_invert_m, covers.get(run.us_node)),
        )
        nodes[run.ds_node] = _Node(
            run.ds_node, end, run.ds_invert_m, covers.get(run.ds_node)
        )

    if not segments:
        return ""

    ordered = sorted(nodes.values(), key=lambda node: node.chainage)
    levels = [s.level_start for s in segments] + [s.level_end for s in segments]
    levels += [node.cover for node in ordered if node.cover is not None]

    x_min = min(s.x_start for s in segments)
    x_max = max(s.x_end for s in segments)
    y_min, y_max = min(levels), max(levels)
    if y_max - y_min < 0.5:
        # A flat run would otherwise be drawn on a hairline scale.
        centre = (y_max + y_min) / 2
        y_min, y_max = centre - 0.25, centre + 0.25

    plot_w = _WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
    plot_h = _HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    def sx(value: float) -> float:
        return round(_MARGIN_LEFT + (value - x_min) / x_span * plot_w, 1)

    def sy(value: float) -> float:
        return round(_MARGIN_TOP + (y_max - value) / y_span * plot_h, 1)

    parts: list[str] = [
        f'<svg class="longsection" viewBox="0 0 {_WIDTH:.0f} {_HEIGHT:.0f}" '
        f'width="100%" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Long section for {escape(ordered[0].ref)} '
        f'to {escape(ordered[-1].ref)}">',
        f'<rect x="0" y="0" width="{_WIDTH:.0f}" height="{_HEIGHT:.0f}" fill="#ffffff"/>',
    ]

    parts.append(_axes(sx, sy, x_min, x_max, y_min, y_max))

    ground = [node for node in ordered if node.cover is not None]
    if len(ground) > 1:
        points = " ".join(f"{sx(n.chainage)},{sy(n.cover)}" for n in ground)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#8b5a2b" '
            f'stroke-width="1.4" stroke-dasharray="5 3"/>'
        )

    for node in ordered:
        top = sy(node.cover) if node.cover is not None else _MARGIN_TOP
        parts.append(
            f'<line x1="{sx(node.chainage)}" y1="{top}" '
            f'x2="{sx(node.chainage)}" y2="{sy(node.invert)}" '
            f'stroke="#334155" stroke-width="2.6" stroke-linecap="square"/>'
        )
        parts.append(
            f'<text x="{sx(node.chainage)}" y="{_HEIGHT - _MARGIN_BOTTOM + 30:.1f}" '
            f'class="ls-node" text-anchor="middle">{escape(node.ref)}</text>'
        )

    for segment in segments:
        colour = VERDICT_COLOURS[segment.verdict]
        parts.append(
            f'<line x1="{sx(segment.x_start)}" y1="{sy(segment.level_start)}" '
            f'x2="{sx(segment.x_end)}" y2="{sy(segment.level_end)}" '
            f'stroke="{colour}" stroke-width="3.4" stroke-linecap="round">'
            f"<title>{escape(segment.ref)}: {segment.verdict}</title></line>"
        )

    parts.append("</svg>")
    return "".join(parts)


def _axes(sx, sy, x_min, x_max, y_min, y_max) -> str:
    plot_bottom = _HEIGHT - _MARGIN_BOTTOM
    parts = [
        f'<line x1="{_MARGIN_LEFT}" y1="{_MARGIN_TOP}" x2="{_MARGIN_LEFT}" '
        f'y2="{plot_bottom}" stroke="#cbd5e1" stroke-width="1"/>',
        f'<line x1="{_MARGIN_LEFT}" y1="{plot_bottom}" '
        f'x2="{_WIDTH - _MARGIN_RIGHT}" y2="{plot_bottom}" '
        f'stroke="#cbd5e1" stroke-width="1"/>',
    ]
    for index in range(5):
        level = y_min + (y_max - y_min) * index / 4
        y = sy(level)
        parts.append(
            f'<line x1="{_MARGIN_LEFT - 4}" y1="{y}" x2="{_WIDTH - _MARGIN_RIGHT}" '
            f'y2="{y}" stroke="#eef2f7" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{_MARGIN_LEFT - 8}" y="{y + 3.5:.1f}" class="ls-tick" '
            f'text-anchor="end">{level:.2f}</text>'
        )
    for index in range(5):
        chainage = x_min + (x_max - x_min) * index / 4
        parts.append(
            f'<text x="{sx(chainage)}" y="{plot_bottom + 15:.1f}" class="ls-tick" '
            f'text-anchor="middle">{chainage:.0f}m</text>'
        )
    return "".join(parts)
