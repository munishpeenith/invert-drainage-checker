# Invert — project context

A rule-driven checker for UK drainage drawings. It reads the manhole and pipe
schedules out of a drawing PDF, checks every pipe run against Approved Document H
and the Water UK adoption guidance, and produces a check sheet plus a long section
with failing runs marked.

Built as a portfolio project for an AI Solution Engineer application. Read `SPEC.md`
before making architectural decisions.

## The one rule that governs everything

**The model never decides anything.**

The model's only jobs are turning an unfamiliar schedule layout into structured
records, and wording the explanation attached to a finding. Every fall, gradient,
comparison, threshold lookup and pass/fail verdict is plain deterministic Python.

If you find yourself about to ask a model whether something complies, stop. That is
the bug. This separation is the point of the project and it is what the work is
being judged on.

## Second rule: never measure the drawing

The tool reads values the schedule states. It does not derive dimensions from
geometry, and it does not estimate. UK engineering drawings carry the note
"not to be scaled from drawings" for a reason, and the tool honours it.

If a value cannot be recovered, the run is reported as **not checked**, with the
reason. Abstention is a feature. Silent guessing is a defect.

## Third rule: every finding cites its clause

A check that cannot name the document and clause it enforces does not ship. The
citation is what lets an engineer verify the tool instead of trusting it.

## Conventions

- Python 3.11, type hints throughout, pydantic for every record that crosses a boundary
- British English in all user-facing strings, comments and docs ("minimise", "metre")
- No em dashes anywhere in output text or documentation
- Rules live in `rules/*.yaml` as data. Adding a check must never mean editing the engine
- One pytest case per rule, minimum: one passing input, one failing input, one unparseable
- Money and tokens are a design concern, not an afterthought. See the token strategy in SPEC.md

## Do not add

Vector database, LangChain or similar framework, Docker, task queue, auth system,
user accounts, cloud deployment with uploads. This is a local CLI plus a thin local
UI. Restraint is deliberate and is mentioned in the README.

## Data handling

Never commit a real project drawing. Test fixtures come from public local authority
planning portals only, and the README says so. The tool must be runnable fully
offline with a locally hosted model, and must offer a `--dry-run` that prints exactly
what text would be sent to a model without sending it.

## Definition of done for v1

`invert check samples/<file>.pdf` produces an HTML report containing the run table,
the findings with clauses, and the long section SVG. Three checks minimum
(minimum gradient, stated vs computed, invert continuity) plus abstention. Tests green.
README written. Measured extraction accuracy reported against the eval fixtures.
