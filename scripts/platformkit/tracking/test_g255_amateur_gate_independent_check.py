import numpy as np

from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as g252
from scripts.platformkit.tracking import g255_amateur_gate_independent_check as subject


def test_g255_uses_g252_fixed_measurement_constants() -> None:
    assert (g252.SAMPLE_SPACING_PX, g252.SEARCH_RADIUS_PX, g252.CANNY_LOW, g252.CANNY_HIGH) == (4.0, 24, 50, 150)


def test_g255_geometry_names_only_withheld_groups() -> None:
    groups = subject.withheld_geometry()
    assert set(groups) == {"control_arc", "control_sideline", "amateur_arc", "amateur_paint"}
    assert len(groups["amateur_paint"]) == 4


def test_g255_normal_search_retains_no_candidate() -> None:
    edges = np.zeros((21, 21), dtype=np.uint8)
    curve = np.float32(((2.0, 10.0), (18.0, 10.0)))
    samples, distances = subject._measure_curve(edges, curve)
    assert samples == 4
    assert distances == []
