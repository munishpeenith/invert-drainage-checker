"""The deterministic parser. This is the path most drawings should take."""

from parse.columns import apply_mapping, infer_mapping

HEADER = [
    "Pipe Ref",
    "US MH",
    "DS MH",
    "Pipe Dia",
    "Length (m)",
    "US IL",
    "DS IL",
    "Gradient",
    "Cover Level",
]


def test_a_recognisable_header_maps_without_a_model():
    mapping = infer_mapping(HEADER)
    assert mapping["us_node"] == 1
    assert mapping["ds_node"] == 2
    assert mapping["us_invert_m"] == 5
    assert mapping["ds_invert_m"] == 6


def test_us_il_is_not_swallowed_by_a_looser_synonym():
    # "US IL" and "DS IL" share the substring "IL". Getting these the wrong way
    # round silently reverses every gradient in the drawing.
    mapping = infer_mapping(HEADER)
    assert mapping["us_invert_m"] != mapping["ds_invert_m"]


def test_an_unrecognisable_header_returns_none_so_a_model_is_called():
    assert infer_mapping(["Col A", "Col B", "Col C"]) is None


def test_a_header_without_node_references_is_not_a_schedule():
    assert infer_mapping(["Length", "Gradient", "Cover Level"]) is None


def test_rows_are_read_through_the_mapping():
    rows = [
        HEADER,
        ["1.000", "MH1", "MH2", "150", "30.00", "57.000", "56.800", "1:150", "60.000"],
    ]
    schedule = apply_mapping(rows, infer_mapping(HEADER))
    run = schedule.runs[0]
    assert (run.ref, run.us_node, run.ds_node) == ("1.000", "MH1", "MH2")
    assert run.diameter_mm == 150
    assert run.length_m == 30.0
    assert run.us_invert_m == 57.000
    assert run.stated_gradient_1_in == 150.0


def test_a_blank_cell_becomes_none_and_never_zero():
    rows = [
        HEADER,
        ["1.004", "MH5", "MH6", "225", "", "56.450", "56.300", "1:100", "59.000"],
    ]
    run = apply_mapping(rows, infer_mapping(HEADER)).runs[0]
    assert run.length_m is None


def test_a_row_without_both_node_references_is_not_a_run():
    rows = [
        HEADER,
        ["Notes", "", "", "", "", "", "", "", ""],
        ["1.000", "MH1", "MH2", "150", "30.00", "57.000", "56.800", "1:150", "60.000"],
    ]
    assert len(apply_mapping(rows, infer_mapping(HEADER)).runs) == 1


def test_levels_suffixed_maod_lose_the_unit_not_the_number():
    rows = [
        HEADER,
        ["1.000", "MH1", "MH2", "150", "30.00", "57.000 mAOD", "56.800mAOD",
         "1:150", "60.000"],
    ]
    run = apply_mapping(rows, infer_mapping(HEADER)).runs[0]
    assert (run.us_invert_m, run.ds_invert_m) == (57.000, 56.800)


def test_a_fused_diameter_and_invert_cell_is_split():
    # SPEC.md section 3.2 names "150Ø - 57.432" as a shape the parser must
    # survive. A whole number of millimetres is the diameter, a decimal in
    # metres is the level.
    rows = [
        HEADER,
        ["1.000", "MH1", "MH2", "150Ø - 57.432", "30.00", "", "56.800",
         "1:150", "60.000"],
    ]
    run = apply_mapping(rows, infer_mapping(HEADER)).runs[0]
    assert run.diameter_mm == 150
    assert run.us_invert_m == 57.432


def test_gradients_are_read_in_every_form_the_drawings_use():
    for cell, expected in (("1:150", 150.0), ("1 in 80", 80.0), ("150", 150.0)):
        rows = [
            HEADER,
            ["1.000", "MH1", "MH2", "150", "30.00", "57.000", "56.800", cell, "60.000"],
        ]
        run = apply_mapping(rows, infer_mapping(HEADER)).runs[0]
        assert run.stated_gradient_1_in == expected, cell


def test_chambers_are_collected_from_the_upstream_node():
    rows = [
        HEADER,
        ["1.000", "MH1", "MH2", "150", "30.00", "57.000", "56.800", "1:150", "60.000"],
        ["1.001", "MH2", "MH3", "150", "25.00", "56.800", "56.600", "1:125", "59.750"],
    ]
    schedule = apply_mapping(rows, infer_mapping(HEADER))
    covers = {chamber.ref: chamber.cover_level_m for chamber in schedule.manholes}
    assert covers == {"MH1": 60.000, "MH2": 59.750}
