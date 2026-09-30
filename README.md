# Invert

> ALL DIMENSIONS IN MILLIMETERS UNLESS NOTED AND NOT TO BE SCALED FROM DRAWINGS

That note appears on every UK engineering drawing. It justifies this tool's
central design decision in twelve words, and it came from the industry rather
than from me: **the numbers that matter are written down, so read those and
never measure the picture.**

Invert reads the manhole and pipe schedules out of a UK drainage drawing PDF,
checks every pipe run against Approved Document H or the Water UK adoption
guidance, and produces a check sheet with a long section showing failing runs.

## What it does, and who loses time to this today

A drainage engineer checking a colleague's drawing works through the schedule
by hand: recompute each gradient from the invert levels and the length, compare
it against the gradient the drawing states, confirm no pipe leaves a chamber
above the pipe arriving at it, then look each diameter and gradient up against
the applicable standard. On a fifty-run drawing that is an afternoon, it is
done again at every revision, and the failure mode is not getting a hard sum
wrong but skipping an easy one on the fortieth row.

The errors this catches are not subtle ones. They are a level edited without
updating the next run, or a gradient left behind when a length changed. They
are obvious once pointed at and invisible in a table of two hundred numbers.

```bash
invert check drawing.pdf --regime adoption --dwellings 12
```

```
5 runs checked against foul-gravity v1, verified 2026-09-30
  2 fail, 1 verify, 18 pass, 7 not checked, 25 not supported
  FAIL 1.001: 150mm foul sewer serving ten or more dwellings requires a
              gradient no flatter than 1:150
  FAIL 1.002: This run leaves the chamber above the invert arriving at it,
              so flow would have to run uphill
report: drawing.report.html
```

## The feasibility call

**The model never decides anything.** Its only job is turning an unfamiliar
schedule layout into structured records. Every fall, gradient, comparison,
threshold lookup and pass or fail verdict is plain deterministic Python in
`check/engine.py`, driven by rules that live in `rules/*.yaml` as data.

This is the whole point of the project. A language model asked "does this
comply" produces a fluent answer with no audit trail, and an engineer cannot
check it without redoing the work. A model asked "what are the columns in this
table" produces something a schema can validate and a human can eyeball against
the source row. The second question is worth asking. The first is the bug.

Three consequences follow, and they are what the design is organised around.

**It does not measure the drawing.** No dimension is derived from geometry and
nothing is estimated. Where a value cannot be recovered the run is reported as
**not checked**, naming the missing field. Abstention is a feature; silent
guessing is a defect, because a wrong number produces a wrong verdict that
reads exactly as authoritative as a right one.

**Every finding cites its clause.** A check that cannot name the document and
clause it enforces does not ship. The citation is what lets an engineer verify
the tool instead of trusting it.

**Most drawings never reach a model at all.** A schedule with a recognisable
header is read by `parse/columns.py` deterministically. A layout nobody has
placed before costs one model call, and the column mapping it works out is
cached against a fingerprint of the header, so the cost is per drawing format
rather than per drawing. A consultancy issuing forty revisions of one drawing
set pays for one extraction.

## Results

**Not yet measured, and deliberately not quoted.**

The harness exists. `python eval/score.py` reports field-level extraction
accuracy, abstention rate, how often the tool abstained wrongly, cost and
latency, against any drawing placed in `eval/fixtures/` beside hand-written
ground truth. It runs today against the synthetic fixtures.

What it does not yet have is real drawings. A number produced against a
synthetic table laid out the way the parser expects would measure the fixture
generator, not the parser, and publishing it would be worse than publishing
nothing: it invites a reader to trust a figure that has never met a real
consultant's drawing.

The numbers go in this section once the eval set holds five or more drawings
from public planning portals, each with ground truth read off it by hand. Until
then the claim is only that the pipeline runs end to end and catches the faults
planted in the fixtures.

## How it fails

**Scanned PDFs are refused, not attempted.** A page yielding no text raises
`ScannedPdfError` with an explanation. There is no OCR, because an OCR error on
a level is indistinguishable from a real level.

**Superseded standards.** The rule pack carries a `last_verified` date and the
report prints it. Nothing watches for revisions to the underlying documents, so
a pack can silently go stale. Water UK's guidance superseded Sewers for
Adoption 7 in England in 2020, and the same will happen again.

**The two regimes are not interchangeable and are never inferred.** The same
pipe is judged differently depending on whether the sewer is offered for
adoption or stays private. `--regime` is mandatory and appears in the report
header. Getting it wrong produces confidently wrong verdicts.

**Context the drawing does not state is not assumed.** How many dwellings a
sewer serves, and what a pipe runs under, are not in the schedule. Omit them
and the dependent checks report as not checked and name the field. They do not
default to a convenient value.

**Multi-invert chambers.** A chamber listing several inverts is parsed as a
list, and the deterministic parser attributes cover levels to the upstream node
of each run. A chamber whose levels are stated only in a separate manhole
schedule will be read less completely than one stated inline.

**Hydraulics are not implemented.** Self-cleansing velocity and proportional
depth of flow need design flows Invert does not compute. Those rules report as
**not supported**, which is deliberately a different verdict from **not
checked**: the first is a limitation of the tool, the second is a gap in the
drawing, and conflating them buries the ones you can act on. On a five-run
fixture the unsupported findings outnumber the real ones five to one.

**The model fabricates when a field has no column, and the prompt alone will
not stop it.** Given a schedule with no chamber size column, the extraction
model filled `chamber_size_mm` with the pipe diameter from the same row. Three
runs then failed the chamber size clause against a drawing that says nothing
about chamber sizes, and the failures cited a real document and a real clause,
so they read as authoritative. Tightening the prompt fixed that instance.

The prompt is not the defence. `parse/validate.py` now drops values that cannot
physically exist before they reach the check engine: a chamber no wider than
the pipe entering it, an invert above its own cover level, a non-positive
length or diameter. The rule that depends on a dropped value then reports as
not checked, which is the correct answer. The guard deliberately does not
touch values that are merely non-compliant: a chamber wider than its pipe but
below the standard minimum is a genuine failure and belongs to the engine.

This generalises, and it is the strongest argument for the architecture. A
model asked for a value that is not there will supply one. The only reliable
protection is that nothing it returns is trusted to decide anything, and that
impossible values are caught structurally rather than instructed against.

**The tables-and-figures boundary.** Invert reads what the schedule states. A
drawing that carries a critical constraint only in a note, or only in the drawn
geometry, is outside what this tool can see, and it will not tell you so.

## Data handling

Nothing leaves the machine unless a model call is made, and a model call is
made only for a schedule layout that has not been seen before. What it would be
sent is the cropped schedule region, never the whole page and never the
drawing: `--dry-run` prints exactly that text and sends nothing.

The API key is read from the environment. `.env` is gitignored and `.env.example`
documents the variable without holding a value. No key is ever read from a
tracked file.

To run fully offline, point `parse/client.py` at a locally hosted model through
the `ModelClient` protocol, or stay on the deterministic path, which needs no
network at all.

No real project drawing is committed. `samples/*.pdf` and `eval/fixtures/*.pdf`
are gitignored; the fixture generator and the hand-written ground truth are
committed instead, because they are reproducible and the PDFs are not.

## What production would need

- An eval set of real drawings graded by a chartered engineer, which is the
  gap between the results table above and a defensible claim
- A watch on revisions to Approved Document H and the Water UK guidance, with
  the report refusing to run silently on a stale pack rather than merely
  printing its date
- Human sign-off before any output reaches a design. A check sheet is an input
  to an engineer's judgement, never a substitute for it
- Query logging for audit, so a finding can be reconstructed months later
- Hydraulic calculation, to turn the not-supported rules into real checks

## Scope

The drainage rule pack is implemented because drainage is the only civils
discipline where the engineer writes every number into a table. Levels,
highways and utilities live in the drawn geometry and cannot be read reliably
from a PDF. That is a scoping decision, not a limitation of the approach: the
engine knows nothing about drainage, so another discipline is a YAML file, not
a rewrite.

Deliberately absent: vector database, agent framework, Docker, task queue,
authentication, user accounts, cloud deployment with uploads. This is a local
CLI and a thin local UI. The restraint is the point.

## Running it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
python eval/fixtures/make_fixture.py
invert check eval/fixtures/synthetic_schedule.pdf --regime adoption --dwellings 12
```

`invert usage` reports tokens and cost spent. Exit codes are 0 for nothing
failed, 1 for at least one failing run, and 2 for a drawing that could not be
read, so it can be run over a batch.

The API key is read from `.env` or from the environment. It is only needed for
a schedule layout that has not been seen before; the fixtures and any drawing
in a known format run without one.

`import anthropic` takes around twenty seconds on an Intel Mac, almost all of
it in the Bedrock and Vertex submodules the SDK loads eagerly. The import is
therefore made inside `AnthropicClient.__init__` rather than at module scope,
so the deterministic path never pays it and startup stays fast.

Do not name the virtual environment `.venv` on macOS. A venv directory whose
name begins with a dot is created with the `UF_HIDDEN` flag, files written
inside it inherit the flag, and Python's `site` module skips hidden `.pth`
files. The editable install then silently fails to register and every import of
a project module raises `ModuleNotFoundError`. `chflags -R nohidden` clears it,
but naming the directory `venv` avoids it outright.

## Layout

```
extract/   pdf_text.py  region.py  template_cache.py
parse/     schema.py  columns.py  client.py  validate.py
rules/     foul_gravity_v1.yaml  loader.py
check/     engine.py  network.py
report/    html.py  longsection.py  pdf.py
eval/      fixtures/  score.py
app/       cli.py  server.py
```

`parse/columns.py` is the one addition to the layout in `SPEC.md`: the
deterministic branch the pipeline takes on a template cache hit needed a home
of its own.

## Sources

- Approved Document H (2015 edition), foul and surface water drainage
- Water UK, *Design and Construction Guidance* v2.3, Appendix C to the Sewerage
  Sector Guidance under the Code for Adoption Agreements (2020), which
  superseded Sewers for Adoption 7th edition in England
