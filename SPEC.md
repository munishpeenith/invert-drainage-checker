# Invert — build spec

## 1. What it does

Input: a UK drainage drawing PDF containing a manhole schedule and a pipe schedule.

Output: an HTML report (and optionally a PDF) containing
- a header stating the drawing, the regime applied, the rule set version and its verification date
- counts of pass / fail / verify / not checked
- a table of every pipe run, with the gradient recomputed from the levels alongside the gradient the drawing states
- findings for the non-passing runs only, each citing its clause
- a long section with runs coloured by verdict

Runtime target: under two seconds for a cached parse, under fifteen cold.

## 2. Why the schedule and not the geometry

Drainage is the only civils discipline where the engineer writes every number into a
table. Levels, highways and utilities live in the drawn geometry and cannot be read
reliably from a PDF. That is why v1 is drainage, and it is a scoping decision rather
than a limitation. Say so in the README.

## 3. Pipeline

```
PDF
 └─ extract/     pdfplumber: page text with coordinates, locate the schedule region
     └─ template cache hit?  ──yes──> deterministic column mapping (no model call)
         └─ no ──> parse/    model call, structured output, pydantic validation
                    └─ on success, save the column mapping to the cache
 └─ check/       deterministic engine, rules loaded from rules/*.yaml
 └─ report/      HTML + SVG long section; PDF via reportlab
```

### 3.1 extract/

`pdfplumber` for words with coordinates and `extract_tables()` first. Locate the
schedule by finding header keywords (`MH REFERENCE`, `INVERT`, `COVER`, `GRADIENT`,
`US IL`, `DS IL`, `LENGTH`). Crop to that region and keep only its text.

Sending only the schedule region rather than the whole page typically removes 80 to 90
per cent of the payload before any model call.

If `extract_tables()` returns nothing usable, fall back to raw text lines for the
cropped region and let the model do more work. Decide this fallback path early; it is
where evenings are lost.

If the page yields no text at all, the PDF is scanned. Refuse it with a clear message.
Do not OCR in v1.

### 3.2 parse/

One model call for the whole table, never per row. Constrain the response to a JSON
schema. Use the cheapest model that passes the eval; extraction is not reasoning.

Records:

```python
class PipeRun(BaseModel):
    ref: str
    us_node: str
    ds_node: str
    diameter_mm: int | None
    length_m: float | None
    us_invert_m: float | None
    ds_invert_m: float | None
    stated_gradient_1_in: float | None
    source_row: str            # verbatim text the record came from
    confidence: Literal["high", "low"]

class Manhole(BaseModel):
    ref: str
    cover_level_m: float | None
    inverts_m: list[float]     # a chamber often has several
    chamber_size_mm: int | None
    easting: float | None
    northing: float | None
```

`source_row` is not optional. Every record must be traceable back to the text it came
from, so a disputed finding can be checked in seconds.

Known cell shapes the parser must survive:
- `150Ø - 57.432` — diameter and invert level fused in one cell
- a chamber listing three inverts in one cell, where the stated depth refers to the deepest
- blank cells where a value should be
- references as `FW1`, `S1/1`, `MH01`, `1.000`
- levels as bare numbers or suffixed `mAOD`

On pydantic validation failure: retry once with the validation errors appended to the
prompt, then abstain. Never coerce a malformed record into a valid-looking one.

### 3.3 Template cache

SQLite. Key on a fingerprint of the header row text plus the title block originator.
Value is the column mapping the model worked out.

Consequence worth stating in the README: **model cost is per new drawing format, not
per drawing.** A consultancy issuing forty revisions of one drawing set pays for one
extraction.

Also cache on a hash of the extracted table text, so an unchanged schedule on a new
revision reuses the parse outright.

### 3.4 check/

Load rules from YAML. For each run, select the rules whose `applies_when` matches,
evaluate `assert`, emit a finding on failure. The engine knows nothing about drainage.

Computed gradient is `length_m / (us_invert_m - ds_invert_m)`, expressed as 1 in N.

Invert continuity compares a run's upstream invert against the downstream invert of
the run arriving at the same node. Requires ordering the runs into a network first,
which is the most interesting bit of logic in the project.

Any run with a `None` in a field a rule needs is reported as not checked, naming the
missing field.

### 3.5 report/

HTML template, deterministic. No model involvement. A checking report is an audit
record and must be byte-identical for identical input.

Long section: chainage along x from cumulative run lengths, levels up y, ground line
through cover levels, manhole shafts vertical, runs coloured by verdict. Plain SVG
generated from the records.

A misread level shows up immediately as a pipe running the wrong way, so the drawing
doubles as a check on the parser. Worth a line in the README.

## 4. Checks for v1

Priority order. The first three are the minimum viable set.

1. **Minimum gradient** for diameter, flow and regime
2. **Stated against computed gradient** — flag disagreement beyond rounding
3. **Invert continuity** — a run leaving a chamber above the invert arriving at it
4. Minimum pipe diameter for what the run serves
5. Cover depth to pipe crown by location class (location supplied by the user, never assumed)
6. Manhole and inspection chamber spacing
7. Chamber size against the largest connecting pipe
8. Self-cleansing velocity
9. Maximum proportional depth of flow

Checks 8 and 9 need hydraulic calculation and design flows. Leave them for last and
be willing to ship without them.

## 5. Two regimes

The same pipe is judged differently depending on whether the sewer is offered for
adoption or stays private.

- **Adoption**: Water UK *Design and Construction Guidance* v2.3, under the Code for Adoption Agreements
- **Private**: *Approved Document H*

The tool must be told which applies and must print it in the report header. Never
infer it. This is the requirement that forces the rule registry to exist, so it is
worth making visible in the UI.

## 6. Token strategy

Four layers, cheapest first.

1. Send the cropped schedule region, not the page
2. Template cache: a known layout costs nothing
3. Content hash: an unchanged table reuses the previous parse
4. Small model, one batched call, JSON schema output, prompt caching on the system prompt

Instrument every call: input tokens, output tokens, model, cache hit or miss, cost.
Log to SQLite. The README reports cost per drawing cold versus cached.

## 7. Evaluation

Build this before tuning anything.

`eval/fixtures/` holds five drawings with hand-written ground truth records.
`eval/score.py` runs extraction and reports field-level accuracy, plus how often the
tool abstained and how often it abstained wrongly.

Five numbers in the README:
- extraction accuracy, field level
- abstention rate
- false positives on checks, confirmed against a human read
- cost per drawing, cold and cached
- latency, cold and cached

Most portfolio projects report none of these. This is the cheapest available
differentiator.

## 8. Layout

```
invert/
  extract/     pdf_text.py  region.py  template_cache.py
  parse/       schema.py  client.py  validate.py
  rules/       foul_gravity_v1.yaml  loader.py
  check/       engine.py  network.py
  report/      html.py  longsection.py  pdf.py
  eval/        fixtures/  score.py
  app/         cli.py  server.py
  samples/     public planning-portal drawings
  tests/
  CLAUDE.md  SPEC.md  README.md
```

## 9. README structure

The README is the deliverable, more than the code is. Sections, in order:

1. **What it does** and who loses time to the problem today
2. **The feasibility call** — what the model does, what it deliberately does not, and why
3. **Results** — the five numbers
4. **How it fails** — superseded standards, multi-invert chambers, scanned PDFs,
   the two regimes, tables and figures, and why it never scales the drawing
5. **Data handling** — what leaves the machine, how to run it fully offline
6. **What production would need** — an eval set graded by a chartered engineer, a
   watch on standard revisions, human sign-off before anything reaches a design,
   query logging for audit
7. **Scope** — drainage rule pack implemented; other disciplines are a config file each

Open with the note that appears on every UK engineering drawing:

> ALL DIMENSIONS IN MILLIMETERS UNLESS NOTED AND NOT TO BE SCALED FROM DRAWINGS

It justifies the central design decision in twelve words, and it came from the
industry rather than from the author.

## 10. Sources

- Approved Document H (2015 edition), foul and surface water drainage
- Water UK, *Design and Construction Guidance* v2.3, Appendix C to the Sewerage Sector
  Guidance under the Code for Adoption Agreements (2020), which superseded
  Sewers for Adoption 7th edition in England
- Test drawings: public planning application documents from local authority portals
