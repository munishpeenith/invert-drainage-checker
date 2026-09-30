"""The guard against impossible values reaching the check engine.

Every case here is one a model actually produced or plausibly could. A value
that cannot exist means the parse is wrong, and the tool must abstain rather
than fail the drawing against a real clause.
"""

from parse.validate import sanity
from tests.helpers import make_manhole, make_run, make_schedule


def test_a_chamber_no_wider_than_its_pipe_is_dropped():
    # Haiku 4.5 did exactly this: given a schedule with no chamber size column,
    # it copied the pipe diameter into chamber_size_mm, and three runs failed
    # the chamber size clause against a drawing that says no such thing.
    schedule = make_schedule(
        [make_run(ref="A1", us_node="S1/1", ds_node="S1/2", diameter_mm=225)],
        [make_manhole(ref="S1/1", chamber_size_mm=225)],
    )
    cleaned, notes = sanity(schedule)
    assert cleaned.manholes[0].chamber_size_mm is None
    assert len(notes) == 1
    assert "225mm pipe" in notes[0]


def test_a_chamber_below_the_standard_but_wider_than_its_pipe_is_left_alone():
    # This one is a genuine compliance failure and belongs to the check engine.
    # The guard must not quietly swallow it.
    schedule = make_schedule(
        [make_run(ref="A1", us_node="S1/1", ds_node="S1/2", diameter_mm=225)],
        [make_manhole(ref="S1/1", chamber_size_mm=900)],
    )
    cleaned, notes = sanity(schedule)
    assert cleaned.manholes[0].chamber_size_mm == 900
    assert notes == []


def test_a_plausible_chamber_survives():
    schedule = make_schedule(
        [make_run(ref="A1", us_node="S1/1", ds_node="S1/2", diameter_mm=225)],
        [make_manhole(ref="S1/1", chamber_size_mm=1200)],
    )
    cleaned, notes = sanity(schedule)
    assert cleaned.manholes[0].chamber_size_mm == 1200
    assert notes == []


def test_an_invert_above_its_cover_level_drops_the_cover():
    schedule = make_schedule(
        [make_run(ref="A1", us_node="MH1", ds_node="MH2")],
        [make_manhole(ref="MH1", cover_level_m=57.000, inverts_m=[59.000])],
    )
    cleaned, notes = sanity(schedule)
    assert cleaned.manholes[0].cover_level_m is None
    assert "above cover level" in notes[0]


def test_a_normal_chamber_keeps_its_cover_level():
    schedule = make_schedule(
        [make_run(ref="A1", us_node="MH1", ds_node="MH2")],
        [make_manhole(ref="MH1", cover_level_m=60.000, inverts_m=[57.000])],
    )
    cleaned, notes = sanity(schedule)
    assert cleaned.manholes[0].cover_level_m == 60.000
    assert notes == []


def test_a_non_positive_length_is_dropped():
    schedule = make_schedule([make_run(ref="A1", length_m=0.0)])
    cleaned, notes = sanity(schedule)
    assert cleaned.runs[0].length_m is None
    assert "not positive" in notes[0]


def test_a_non_positive_diameter_is_dropped():
    schedule = make_schedule([make_run(ref="A1", diameter_mm=-150)])
    cleaned, notes = sanity(schedule)
    assert cleaned.runs[0].diameter_mm is None


def test_a_sound_schedule_is_returned_untouched():
    schedule = make_schedule(
        [make_run()], [make_manhole(ref="MH1", chamber_size_mm=1200)]
    )
    cleaned, notes = sanity(schedule)
    assert notes == []
    assert cleaned.runs[0].length_m == 30.0
