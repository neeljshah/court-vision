import numpy as np

from scripts.platformkit.tracking.g223_line_error_structure import angle_offset, canonical_line


def test_canonical_sign_and_offset_are_invariant_to_selected_line_orientation():
    truth = np.array((0.0, 1.0, 0.0))
    selected = np.array((0.0, 1.0, -2.0))
    first, second = (0.0, 0.0), (10.0, 0.0)
    normal = canonical_line(selected, truth)
    reversed_normal = canonical_line(-selected, truth)
    assert np.allclose(normal, reversed_normal)
    angle, midpoint, endpoint_component, first_distance, second_distance = angle_offset(selected, truth, first, second)
    assert angle == 0.0
    assert midpoint == -2.0
    assert endpoint_component == 0.0
    assert first_distance == second_distance == -2.0
