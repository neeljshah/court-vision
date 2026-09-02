import numpy as np

from scripts.platformkit.g60_clay_horizontals import VerticalGuide, above_court


def test_above_court_uses_only_the_solver_derived_horizon() -> None:
    guide = VerticalGuide(top=300.0, left=np.zeros(4), right=np.zeros(4))
    assert above_court(np.array((0.0, 299.0, 100.0, 299.0)), guide)
    assert not above_court(np.array((0.0, 300.0, 100.0, 300.0)), guide)
