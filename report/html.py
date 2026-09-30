"""Render the check sheet. Deterministic, no model involvement.

A checking report is an audit record and must be byte-identical for identical
input, so nothing here may depend on the time of day, on the ordering of a set,
or on a model. There is deliberately no "generated at" stamp: it would make two
runs of the same drawing differ, and the drawing revision is what matters.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment

from check.engine import Result
from parse.schema import Schedule
from report.longsection import VERDICT_COLOURS

VERDICT_LABELS: dict[str, str] = {
    "pass": "Pass",
    "fail": "Fail",
    "warn": "Verify",
    "not_checked": "Not checked",
    "not_supported": "Not supported",
}

_TEMPLATE = """<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invert check sheet: {{ drawing }}</title>
<style>
:root { color-scheme: light; }
body { margin: 0; padding: 2rem 1.5rem 4rem; background: #f6f7f9; color: #17202a;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.45rem; margin: 0 0 .35rem; }
h2 { font-size: 1.1rem; margin: 2.4rem 0 .8rem; }
.meta { color: #4b5563; font-size: .88rem; margin: 0 0 1.6rem; }
.meta strong { color: #17202a; }
.warning { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px;
  padding: .7rem .9rem; font-size: .86rem; color: #7c2d12; margin: 0 0 1.6rem; }
.counts { display: flex; flex-wrap: wrap; gap: .6rem; margin: 0 0 1rem; padding: 0; list-style: none; }
.counts li { background: #fff; border: 1px solid #e3e7ed; border-radius: 8px;
  padding: .5rem .85rem; font-size: .85rem; }
.counts b { display: block; font-size: 1.3rem; font-weight: 600; }
.panel { background: #fff; border: 1px solid #e3e7ed; border-radius: 10px; overflow: hidden; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { text-align: right; padding: .48rem .7rem; border-bottom: 1px solid #eef1f5; white-space: nowrap; }
th { background: #fafbfc; font-weight: 600; color: #374151; text-align: right; }
th:first-child, td:first-child, th.l, td.l { text-align: left; }
tbody tr:last-child td { border-bottom: 0; }
.tag { display: inline-block; padding: .1rem .5rem; border-radius: 999px;
  font-size: .76rem; font-weight: 600; color: #fff; }
.absent { color: #9aa3af; }
.mismatch { color: #b02a1f; font-weight: 600; }
.finding { border-bottom: 1px solid #eef1f5; padding: .85rem 1rem; }
.finding:last-child { border-bottom: 0; }
.finding p { margin: .35rem 0 0; }
.finding .cite { font-size: .8rem; color: #4b5563; margin-top: .3rem; }
.finding .obs { font-size: .78rem; color: #6b7280; font-family: ui-monospace, Menlo, monospace; }
.ls-tick { font: 9px ui-monospace, Menlo, monospace; fill: #94a3b8; }
.ls-node { font: 9px ui-monospace, Menlo, monospace; fill: #475569; }
.longsection + .longsection { margin-top: .5rem; }
.legend { display: flex; gap: 1rem; flex-wrap: wrap; font-size: .8rem;
  color: #4b5563; margin: .7rem 0 0; }
.legend span::before { content: ""; display: inline-block; width: 22px; height: 3px;
  vertical-align: middle; margin-right: .4rem; border-radius: 2px; background: currentColor; }
footer { color: #6b7280; font-size: .8rem; margin-top: 2.5rem; }
</style>
</head>
<body>
<main>
<h1>Drainage check sheet</h1>
<p class="meta">
  <strong>{{ drawing }}</strong><br>
  Regime: <strong>{{ regime_label }}</strong> &middot;
  Rule set: <strong>{{ result.pack }} v{{ result.pack_version }}</strong>,
  verified <strong>{{ result.pack_last_verified }}</strong>
</p>

<p class="warning">
  Every verdict is produced by comparison against the rule set named above. No
  finding is a substitute for a chartered engineer's review, and a drawing that
  passes every check here has not been designed, only checked against the
  clauses this tool implements.
</p>

<ul class="counts">
{%- for verdict in order %}
  <li><b>{{ result.counts.get(verdict, 0) }}</b>{{ labels[verdict] }}</li>
{%- endfor %}
  <li><b>{{ schedule.runs | length }}</b>Runs</li>
</ul>

<h2>Pipe runs</h2>
<div class="panel scroll">
<table>
<thead><tr>
  <th class="l">Run</th><th class="l">From</th><th class="l">To</th>
  <th>Dia (mm)</th><th>Length (m)</th><th>US IL</th><th>DS IL</th>
  <th>Computed</th><th>Stated</th><th class="l">Verdict</th>
</tr></thead>
<tbody>
{%- for row in rows %}
  <tr>
    <td class="l">{{ row.ref }}</td>
    <td class="l">{{ row.us_node }}</td>
    <td class="l">{{ row.ds_node }}</td>
    <td>{{ row.diameter }}</td>
    <td>{{ row.length }}</td>
    <td>{{ row.us_invert }}</td>
    <td>{{ row.ds_invert }}</td>
    <td class="{{ 'mismatch' if row.disagrees else '' }}">{{ row.computed }}</td>
    <td class="{{ 'mismatch' if row.disagrees else '' }}">{{ row.stated }}</td>
    <td class="l"><span class="tag" style="background:{{ colours[row.verdict] }}">
      {{ labels[row.verdict] }}</span></td>
  </tr>
{%- endfor %}
</tbody>
</table>
</div>

<h2>Findings</h2>
{%- if findings %}
<div class="panel">
{%- for finding in findings %}
  <div class="finding">
    <span class="tag" style="background:{{ colours[finding.verdict] }}">
      {{ labels[finding.verdict] }}</span>
    <strong>{{ finding.run_ref }}</strong>
    <span class="obs">{{ finding.rule_id }}</span>
    <p>{{ finding.message }}</p>
    <p class="cite">{{ finding.citation }}</p>
    {%- if finding.observed %}
    <p class="obs">{{ observed[loop.index0] }}</p>
    {%- endif %}
  </div>
{%- endfor %}
</div>
{%- else %}
<div class="panel"><div class="finding">
  <p>No run failed a check and none needs verifying.</p>
</div></div>
{%- endif %}

{%- if not_checked %}
<h2>Not checked</h2>
<div class="panel">
{%- for finding in not_checked %}
  <div class="finding">
    <strong>{{ finding.run_ref }}</strong>
    <span class="obs">{{ finding.rule_id }}</span>
    <p>{{ finding.message }}</p>
  </div>
{%- endfor %}
</div>
{%- endif %}

<h2>Long section</h2>
{%- if long_section %}
<div class="panel">{{ long_section }}</div>
<p class="legend">
{%- for verdict in order %}
  <span style="color:{{ colours[verdict] }}">{{ labels[verdict] }}</span>
{%- endfor %}
</p>
<p class="meta">Levels are those the schedule states. A run drawn rising to the
right is a misread level or a drawing error, and either way is worth opening the
PDF for.</p>
{%- else %}
<div class="panel"><div class="finding">
  <p>No run carries enough level and length information to be drawn.</p>
</div></div>
{%- endif %}

<footer>
  Produced by Invert from the schedule text. Nothing was scaled from the
  drawing, and no value was inferred where the schedule was silent.
</footer>
</main>
</body>
</html>
"""


def _number(value: Any, places: int) -> str:
    if value is None:
        return "&mdash;"
    return f"{value:.{places}f}"


def render(
    schedule: Schedule,
    result: Result,
    drawing_name: str,
    long_section_svg: str,
) -> str:
    environment = Environment(autoescape=True)
    environment.filters["number"] = _number
    template = environment.from_string(_TEMPLATE)

    rows = []
    for run in schedule.runs:
        facts = result.run_facts.get(run.ref, {})
        computed = facts.get("computed_gradient_1_in")
        delta = facts.get("gradient_delta_1_in")
        rows.append(
            {
                "ref": run.ref,
                "us_node": run.us_node,
                "ds_node": run.ds_node,
                "diameter": _plain(run.diameter_mm, 0),
                "length": _plain(run.length_m, 2),
                "us_invert": _plain(run.us_invert_m, 3),
                "ds_invert": _plain(run.ds_invert_m, 3),
                "computed": _gradient(computed),
                "stated": _gradient(run.stated_gradient_1_in),
                "disagrees": delta is not None and delta > 1.0,
                "verdict": result.run_verdicts.get(run.ref, "not_checked"),
            }
        )

    findings = [f for f in result.findings if f.verdict in ("fail", "warn")]
    not_checked = [f for f in result.findings if f.verdict == "not_checked"]

    return template.render(
        drawing=drawing_name,
        regime_label=(
            "Adoption, Water UK Design and Construction Guidance"
            if result.regime == "adoption"
            else "Private, Approved Document H"
        ),
        result=result,
        schedule=schedule,
        rows=rows,
        findings=findings,
        observed=[_observed(f.observed) for f in findings],
        not_checked=not_checked,
        long_section=_raw(long_section_svg),
        colours=VERDICT_COLOURS,
        labels=VERDICT_LABELS,
        order=["fail", "warn", "pass", "not_checked", "not_supported"],
    )


def _raw(svg: str):
    from markupsafe import Markup

    return Markup(svg) if svg else ""


def _plain(value: Any, places: int) -> str:
    return "not stated" if value is None else f"{value:.{places}f}"


def _gradient(value: float | None) -> str:
    return "not stated" if value is None else f"1 in {value:.1f}"


def _observed(observed: dict[str, Any]) -> str:
    parts = []
    for key, value in observed.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.3f}")
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def write(html: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
