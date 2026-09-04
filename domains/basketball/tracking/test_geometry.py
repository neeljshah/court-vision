"""Focused tests for the basketball court-model mixin.

Run: python -m pytest domains/basketball/tracking/test_geometry.py -q
"""
import numpy as np
import pytest

from domains.basketball.tracking.geometry import BasketballGeometryMixin


def test_court_model_reuses_league_specific_paint_widths():
    ncaa = BasketballGeometryMixin.court_model("ncaa_basketball")
    wnba = BasketballGeometryMixin.court_model("wnba")

    assert np.allclose(ncaa, ((19.0, 0.0), (31.0, 0.0), (19.0, 19.0), (31.0, 19.0)))
    assert np.allclose(wnba, ((17.0, 0.0), (33.0, 0.0), (17.0, 19.0), (33.0, 19.0)))


def test_court_model_rejects_unknown_leagues():
    with pytest.raises(ValueError, match="unsupported basketball league"):
        BasketballGeometryMixin.court_model("nba")


def test_point_in_court_uses_94_by_50_foot_bounds():
    assert BasketballGeometryMixin.point_in_court(np.array((50.0, 94.0)))
    assert not BasketballGeometryMixin.point_in_court(np.array((50.1, 94.0)))
