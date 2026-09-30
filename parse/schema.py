"""Records that cross the parse boundary. Every other module consumes these."""

from typing import Literal

from pydantic import BaseModel


class PipeRun(BaseModel):
    ref: str
    us_node: str
    ds_node: str
    diameter_mm: int | None
    length_m: float | None
    us_invert_m: float | None
    ds_invert_m: float | None
    stated_gradient_1_in: float | None
    source_row: str
    confidence: Literal["high", "low"]


class Manhole(BaseModel):
    ref: str
    cover_level_m: float | None
    inverts_m: list[float]
    chamber_size_mm: int | None
    easting: float | None
    northing: float | None


class Schedule(BaseModel):
    runs: list[PipeRun]
    manholes: list[Manhole]
