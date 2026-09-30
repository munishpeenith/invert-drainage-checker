"""Thin local UI over the same pipeline as the CLI. Local only, no auth, no uploads.

The drawing is named by path and read from disk where it already sits. Nothing
is uploaded, nothing is stored, and the server binds to the loopback interface.
The regime and the location class are form fields with no default, for the same
reason the CLI requires them: neither is ever inferred.
"""

from pathlib import Path

from app.cli import LOCATION_CLASSES

_FORM = """<!DOCTYPE html>
<html lang="en-GB"><head><meta charset="utf-8"><title>Invert</title>
<style>
body {{ font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif;
  max-width: 640px; margin: 3rem auto; padding: 0 1.5rem; color: #17202a; }}
label {{ display: block; margin: 1rem 0 .25rem; font-weight: 600; font-size: .9rem; }}
input, select {{ width: 100%; padding: .5rem; font: inherit;
  border: 1px solid #cbd5e1; border-radius: 6px; }}
button {{ margin-top: 1.5rem; padding: .6rem 1.2rem; font: inherit; font-weight: 600;
  background: #17202a; color: #fff; border: 0; border-radius: 6px; }}
.note {{ color: #4b5563; font-size: .85rem; }}
</style></head><body>
<h1>Invert</h1>
<p class="note">Checks a UK drainage schedule against Approved Document H or the
Water UK adoption guidance. The drawing is read from the path you give and is
never uploaded or stored.</p>
<form method="post" action="/check">
  <label>Drawing path</label>
  <input name="pdf" placeholder="/path/to/drawing.pdf" required>
  <label>Regime</label>
  <select name="regime" required>
    <option value="">Choose. This is never inferred.</option>
    <option value="adoption">Adoption, Water UK guidance</option>
    <option value="private">Private, Approved Document H</option>
  </select>
  <label>Location class</label>
  <select name="location_class">
    <option value="">Not supplied, so cover depth is not checked</option>
    {options}
  </select>
  <label>Dwellings served</label>
  <input name="dwellings" type="number" min="0">
  <button type="submit">Check</button>
</form>
</body></html>
"""


def create_app():
    from fastapi import Form, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi import FastAPI

    from check.engine import CheckContext, evaluate
    from check.network import Network
    from extract.pdf_text import ScannedPdfError, read_pages
    from extract.region import find_schedule
    from parse import columns
    from report import html as html_report
    from report import longsection
    from rules.loader import PACK_DIR, load_pack

    app = FastAPI(title="Invert")
    options = "".join(
        f'<option value="{value}">{value.replace("_", " ")}</option>'
        for value in LOCATION_CLASSES
    )

    @app.get("/", response_class=HTMLResponse)
    def form() -> str:
        return _FORM.format(options=options)

    @app.post("/check", response_class=HTMLResponse)
    def check(
        pdf: str = Form(...),
        regime: str = Form(...),
        location_class: str = Form(""),
        dwellings: str = Form(""),
    ) -> str:
        path = Path(pdf).expanduser()
        if not path.exists():
            raise HTTPException(404, f"{path} does not exist")
        try:
            pages = read_pages(path)
        except ScannedPdfError as error:
            raise HTTPException(422, str(error)) from error

        regions = find_schedule(pages)
        if not regions or not regions[0].rows:
            raise HTTPException(
                422,
                "No schedule table could be resolved. The command line tool can "
                "fall back to a model for an unfamiliar layout.",
            )
        region = regions[0]
        mapping = columns.infer_mapping(region.rows[0])
        if mapping is None:
            raise HTTPException(422, "Unfamiliar column layout. Use the CLI.")

        schedule = columns.apply_mapping(region.rows, mapping)
        network = Network(schedule.runs)
        pack = load_pack(PACK_DIR / "foul_gravity_v1.yaml")
        result = evaluate(
            schedule,
            network,
            pack,
            regime,
            CheckContext(
                location_class=location_class or None,
                dwellings=int(dwellings) if dwellings else None,
            ),
        )
        svg = longsection.render_svg(schedule, network, result)
        return html_report.render(schedule, result, path.name, svg)

    return app


def main() -> int:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
