from check.network import Network
from tests.helpers import make_run


def test_upstream_of_finds_the_run_arriving_at_this_runs_upstream_node():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2")
    second = make_run(ref="R2", us_node="MH2", ds_node="MH3")
    network = Network([first, second])

    assert network.upstream_of(second) == [first]
    assert network.upstream_of(first) == []


def test_chainage_accumulates_along_the_branch():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2", length_m=30.0)
    second = make_run(ref="R2", us_node="MH2", ds_node="MH3", length_m=25.0)
    third = make_run(ref="R3", us_node="MH3", ds_node="MH4", length_m=10.0)
    network = Network([first, second, third])

    assert network.chainage_m(first) == 0.0
    assert network.chainage_m(second) == 30.0
    assert network.chainage_m(third) == 55.0


def test_chainage_at_a_junction_takes_the_longest_path():
    long_branch = make_run(ref="R1", us_node="MH1", ds_node="MH3", length_m=40.0)
    short_branch = make_run(ref="R2", us_node="MH2", ds_node="MH3", length_m=10.0)
    outfall = make_run(ref="R3", us_node="MH3", ds_node="MH4", length_m=5.0)
    network = Network([long_branch, short_branch, outfall])

    assert network.chainage_m(outfall) == 40.0


def test_chainage_is_unknown_when_a_length_upstream_is_missing():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2", length_m=None)
    second = make_run(ref="R2", us_node="MH2", ds_node="MH3", length_m=25.0)
    network = Network([first, second])

    assert network.chainage_m(second) is None


def test_a_loop_returns_none_rather_than_recursing_forever():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2")
    second = make_run(ref="R2", us_node="MH2", ds_node="MH1")
    network = Network([first, second])

    assert network.chainage_m(first) is None
    assert network.chainage_m(second) is None


def test_branches_walk_from_each_head_to_the_outfall():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2")
    second = make_run(ref="R2", us_node="MH2", ds_node="MH3")
    network = Network([first, second])

    assert [[run.ref for run in branch] for branch in network.branches()] == [
        ["R1", "R2"]
    ]


def test_branches_terminate_on_a_loop():
    first = make_run(ref="R1", us_node="MH1", ds_node="MH2")
    second = make_run(ref="R2", us_node="MH2", ds_node="MH1")
    network = Network([first, second])

    assert network.branches() == []


def test_at_node_returns_everything_touching_the_chamber():
    arriving = make_run(ref="R1", us_node="MH1", ds_node="MH2", diameter_mm=225)
    leaving = make_run(ref="R2", us_node="MH2", ds_node="MH3", diameter_mm=150)
    network = Network([arriving, leaving])

    assert {run.ref for run in network.at_node("MH2")} == {"R1", "R2"}
