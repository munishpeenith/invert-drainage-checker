"""Record builders for the tests. Defaults describe one sound 150mm run."""

from parse.schema import Manhole, PipeRun, Schedule


def make_run(
    ref: str = "R1",
    us_node: str = "MH1",
    ds_node: str = "MH2",
    diameter_mm: int | None = 150,
    length_m: float | None = 30.0,
    us_invert_m: float | None = 57.000,
    ds_invert_m: float | None = 56.800,
    stated_gradient_1_in: float | None = None,
) -> PipeRun:
    return PipeRun(
        ref=ref,
        us_node=us_node,
        ds_node=ds_node,
        diameter_mm=diameter_mm,
        length_m=length_m,
        us_invert_m=us_invert_m,
        ds_invert_m=ds_invert_m,
        stated_gradient_1_in=stated_gradient_1_in,
        source_row=f"{ref} {us_node} {ds_node}",
        confidence="high",
    )


def make_manhole(
    ref: str = "MH1",
    cover_level_m: float | None = 60.000,
    inverts_m: list[float] | None = None,
    chamber_size_mm: int | None = 1200,
) -> Manhole:
    return Manhole(
        ref=ref,
        cover_level_m=cover_level_m,
        inverts_m=inverts_m if inverts_m is not None else [57.000],
        chamber_size_mm=chamber_size_mm,
        easting=None,
        northing=None,
    )


def make_schedule(runs: list[PipeRun], manholes: list[Manhole] | None = None) -> Schedule:
    return Schedule(runs=runs, manholes=manholes if manholes is not None else [])
