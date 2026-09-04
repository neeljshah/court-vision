from scripts.platformkit.tracking.g284_detector_recall_bound import distribution, on_court


def test_g270_inclusive_court_boundary_is_preserved():
    assert on_court({"court_x_ft": 0, "court_y_ft": 0})
    assert on_court({"court_x_ft": 50, "court_y_ft": 94})
    assert not on_court({"court_x_ft": 50.01, "court_y_ft": 94})
    assert not on_court({"court_x_ft": 50, "court_y_ft": 94.01})


def test_distribution_retains_per_frame_spread():
    summary = distribution([1.0, 2.0, 3.0, 4.0])
    assert summary == {"n": 4, "min": 1.0, "q25": 1.75, "median": 2.5, "mean": 2.5, "q75": 3.25, "max": 4.0}
