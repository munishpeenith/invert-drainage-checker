"""invert check <pdf> --regime {adoption,private} [options]

The regime is never inferred. Neither is the location class, nor what a run
serves. Both are supplied by the user or the checks that need them report as
not checked.

Exit codes: 0 nothing failed, 1 at least one run failed a check, 2 the drawing
could not be read. The distinction matters if this is ever run over a batch.
"""

import argparse
import os
import sys
from pathlib import Path

from check.engine import CheckContext, evaluate
from check.network import Network
from extract import template_cache
from extract.pdf_text import ScannedPdfError, read_pages
from extract.region import find_schedule, originator
from parse import columns
from parse.client import AnthropicClient, DryRun, DryRunClient
from parse.schema import Schedule
from parse.validate import AbstainedError, parse_schedule, sanity
from report import html, longsection
from rules.loader import PACK_DIR, load_pack

LOCATION_CLASSES = (
    "garden_or_path",
    "driveway_weight_restricted",
    "limited_access_street",
    "agricultural_or_open_space",
    "unrestricted_highway",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invert",
        description="Check a UK drainage drawing schedule against the rule pack.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check a drawing and write a report")
    check.add_argument("pdf", type=Path)
    check.add_argument(
        "--regime",
        required=True,
        choices=("adoption", "private"),
        help="Adoption applies the Water UK guidance, private applies "
        "Approved Document H. Never inferred from the drawing.",
    )
    check.add_argument("--out", type=Path, default=None, help="HTML report path")
    check.add_argument("--pdf-report", action="store_true", help="also write a PDF")
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="print exactly what would be sent to a model, and send nothing",
    )
    check.add_argument(
        "--no-cache", action="store_true", help="ignore the parse cache and re-extract"
    )
    check.add_argument("--model", default=None, help="override the model")

    context = check.add_argument_group(
        "context the drawing does not state",
        "Omitted values are not assumed. The checks that need them report as "
        "not checked and name the field.",
    )
    context.add_argument("--location-class", choices=LOCATION_CLASSES, default=None)
    context.add_argument("--system", choices=("foul", "surface_water"), default=None)
    context.add_argument("--asset", choices=("sewer", "lateral_drain"), default=None)
    context.add_argument("--wc-count", type=int, default=None)
    context.add_argument("--dwellings", type=int, default=None)
    context.add_argument("--properties", type=int, default=None)
    context.add_argument("--peak-flow", type=float, default=None, dest="peak_flow_l_s")

    sub.add_parser("usage", help="report tokens and cost spent so far")

    return parser


def load_dotenv(start: Path | None = None) -> None:
    """Read .env into the environment if it is there. No dependency, no echo.

    A variable already set in the environment always wins, so an exported key
    is never silently replaced by a stale file. Values are not logged anywhere,
    because the one variable this exists for is a credential.
    """
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / ".env"
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            value = value.strip().strip("'\"")
            if name and value and name not in os.environ:
                os.environ[name] = value
        return


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    load_dotenv(Path(__file__).parent)
    args = build_parser().parse_args(argv)
    if args.command == "usage":
        return _usage()
    return _check(args)


def _usage() -> int:
    total = template_cache.usage_total()
    print(f"calls          {total['calls']}")
    print(f"input tokens   {total['input_tokens']}")
    print(f"output tokens  {total['output_tokens']}")
    print(f"cost           ${total['cost_usd']:.4f}")
    return 0


def _check(args) -> int:
    if not args.pdf.exists():
        print(f"invert: {args.pdf} does not exist", file=sys.stderr)
        return 2

    try:
        pages = read_pages(args.pdf)
    except ScannedPdfError as error:
        print(f"invert: {error}", file=sys.stderr)
        return 2

    regions = find_schedule(pages)
    if not regions:
        print(
            f"invert: no schedule found in {args.pdf.name}. Looked for a table "
            "headed with references, levels, lengths and gradients.",
            file=sys.stderr,
        )
        return 2
    region = regions[0]

    try:
        schedule = _load_schedule(region, pages, args)
    except DryRun:
        return 0
    except AbstainedError as error:
        print(f"invert: {error}", file=sys.stderr)
        return 2

    if not schedule.runs:
        print("invert: the schedule parsed but contains no pipe runs", file=sys.stderr)
        return 2

    pack = load_pack(PACK_DIR / "foul_gravity_v1.yaml")
    network = Network(schedule.runs)
    result = evaluate(
        schedule,
        network,
        pack,
        args.regime,
        CheckContext(
            location_class=args.location_class,
            system=args.system,
            asset=args.asset,
            wc_count=args.wc_count,
            dwellings=args.dwellings,
            properties=args.properties,
            peak_flow_l_s=args.peak_flow_l_s,
        ),
    )

    svg = longsection.render_svg(schedule, network, result)
    document = html.render(schedule, result, args.pdf.name, svg)
    out = args.out or args.pdf.with_suffix(".report.html")
    html.write(document, out)

    if args.pdf_report:
        from report import pdf as pdf_report

        pdf_report.render(schedule, result, args.pdf.name, out.with_suffix(".pdf"))

    _summarise(result, out)
    return 1 if result.counts.get("fail", 0) else 0


def _load_schedule(region, pages, args) -> Schedule:
    """Cheapest path first. The model is the last resort, not the first.

    An unchanged schedule is reused outright. A recognisable or previously
    learned column layout is read by plain Python. Only a layout nobody has
    placed before costs anything.
    """
    key = template_cache.content_key(region.text)
    template = template_cache.template_key(region.header_row, originator(pages))

    if not args.no_cache and not args.dry_run:
        cached = template_cache.get_parse(key)
        if cached is not None:
            return cached

    if region.rows:
        mapping = None
        if not args.no_cache:
            mapping = template_cache.get_mapping(template)
        if mapping is None:
            mapping = columns.infer_mapping(region.rows[0])
        if mapping is not None:
            schedule = columns.apply_mapping(region.rows, mapping)
            if schedule.runs:
                if not args.dry_run:
                    template_cache.put_mapping(template, mapping)
                    template_cache.put_parse(key, schedule)
                return schedule

    # Nothing deterministic fits, so the layout is new and a model earns its
    # keep working the columns out once.
    client = DryRunClient() if args.dry_run else AnthropicClient(model=args.model)
    schedule, notes = sanity(parse_schedule(client, region))
    for note in notes:
        print(f"invert: dropped an impossible value. {note}", file=sys.stderr)
    template_cache.put_parse(key, schedule)
    return schedule


def _summarise(result, out: Path) -> None:
    counts = result.counts
    print(f"{len(result.run_verdicts)} runs checked against {result.pack} "
          f"v{result.pack_version}, verified {result.pack_last_verified}")
    print(
        f"  {counts.get('fail', 0)} fail, {counts.get('warn', 0)} verify, "
        f"{counts.get('pass', 0)} pass, {counts.get('not_checked', 0)} not checked, "
        f"{counts.get('not_supported', 0)} not supported"
    )
    for finding in result.findings:
        if finding.verdict == "fail":
            print(f"  FAIL {finding.run_ref}: {finding.message.splitlines()[0]}")
    print(f"report: {out}")


if __name__ == "__main__":
    raise SystemExit(main())
