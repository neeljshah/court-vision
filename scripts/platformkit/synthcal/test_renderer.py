"""Focused rule-geometry tests for synthetic calibration templates."""
from scripts.platformkit.synthcal.renderer import court_keypoints, render_sample


def test_tennis_has_the_fourteen_rule_intersections():
    points = court_keypoints("tennis")
    assert len(points) == 14
    assert points["corner_78.0_36.0"] == (78.0, 36.0)
    assert points["service_60.0_31.5"] == (60.0, 31.5)
    assert points["t_18.0"] == (18.0, 18.0)


def test_soccer_and_basketball_named_points_are_rule_coordinates():
    assert court_keypoints("soccer")["centre"] == (52.5, 34.0)
    assert court_keypoints("basketball")["centre"] == (47.0, 25.0)
    assert court_keypoints("basketball")["lane_75.0_33.0"] == (75.0, 33.0)


def test_renderer_returns_visible_aligned_named_labels():
    item = render_sample("tennis", seed=7)
    assert item["image"].shape == (720, 1280, 3)
    assert len(item["names"]) == len(item["points"]) == len(item["visible"]) == 14
    assert item["visible"].sum() >= 4
