from scripts.platformkit.tracking.g74_offframe_evidence import evenly_spaced, is_off_frame, wilson_interval


def test_geometric_flag_wilson_and_spread_selection() -> None:
    assert is_off_frame((-1.0, 10.0, 20.0, 30.0), 1280, 720) == (True, ["x_min_lt_0"])
    assert is_off_frame((0.0, 0.0, 1280.0, 720.0), 1280, 720) == (False, [])
    assert is_off_frame((20.0, 30.0, 10.0, -1.0), 1280, 720) == (True, ["y_min_lt_0"])
    low, high = wilson_interval(0, 100)
    assert low == 0.0 and 0.036 < high < 0.037
    selected = evenly_spaced([{"row": index} for index in range(100)], 12)
    assert [item["row"] for item in selected] == [4, 12, 20, 29, 37, 45, 54, 62, 70, 79, 87, 95]
