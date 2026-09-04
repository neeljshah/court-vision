"""Focused checks for the arithmetic-only G285b matcher."""
from scripts.platformkit.tracking.g285b_locate_then_match import evenly_spaced_indices, match_frame, wilson


def test_nearest_neighbour_distances_are_symmetric() -> None:
    locations = [{"foot_x_px": 0.0, "foot_y_px": 0.0}, {"foot_x_px": 100.0, "foot_y_px": 0.0}]
    footpoints = [{"foot_x_px": 30.0, "foot_y_px": 40.0}, {"foot_x_px": 90.0, "foot_y_px": 0.0}]
    assert match_frame(locations, footpoints) == ([50.0, 10.0], [50.0, 10.0])


def test_wilson_uses_named_binomial_denominator() -> None:
    lower, upper = wilson(4, 10)
    assert round(lower, 6) == 0.168180
    assert round(upper, 6) == 0.687326


def test_selection_is_inclusive_and_evenly_spaced() -> None:
    assert evenly_spaced_indices(54) == [0, 4, 8, 11, 15, 19, 23, 27, 30, 34, 38, 42, 45, 49, 53]
