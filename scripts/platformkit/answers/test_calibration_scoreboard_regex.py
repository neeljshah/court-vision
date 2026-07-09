"""MICRO-FIX LANE mu -- _SCOREBOARD_ROW_RE rejects positive deltas.
resolver_registry.calibration_number() parses the pinned
vault/_Organized/_Index/_Calibration_Scoreboard.md row per sport. The
dBrier/dECE regex groups only allowed a leading '-' (e.g. "-0.00013"), so
a genuine positive delta like "+0.00500" (NBA's real dECE) failed the whole
row match -> calibration_number("nba") wrongly returned no_data even though
the pinned artifact has the row. Fix: groups now accept '+', '-', or bare.

Run: python -m pytest scripts/platformkit/answers/test_calibration_scoreboard_regex.py -q
"""
from __future__ import annotations

from scripts.platformkit.answers import resolver_registry as R

# Real row shape from vault/_Organized/_Index/_Calibration_Scoreboard.md (NBA row
# has a positive dECE "+0.00500"; other sports have all-negative deltas).
_POSITIVE_DELTA_ROW = (
    "| NBA | 4,846 | 0.21979 | 0.21966 | -0.00013 | 0.02614 | 0.03113 | +0.00500 "
    "| multi-feature WF logistic (fit_winprob) |\n"
)
_NEGATIVE_DELTA_ROW = (
    "| TENNIS | 9,006 | 0.22215 | 0.21966 | -0.00250 | 0.04843 | 0.01872 | -0.02971 "
    "| WF Platt recalibration (blend=0.3) |\n"
)


def test_positive_delta_row_parses():
    m = R._SCOREBOARD_ROW_RE.search(_POSITIVE_DELTA_ROW)
    assert m is not None
    assert m.group("d_brier") == "-0.00013"
    assert m.group("d_ece") == "+0.00500"


def test_negative_delta_row_still_parses():
    m = R._SCOREBOARD_ROW_RE.search(_NEGATIVE_DELTA_ROW)
    assert m is not None
    assert m.group("d_brier") == "-0.00250"
    assert m.group("d_ece") == "-0.02971"


def test_calibration_number_nba_returns_real_data_not_no_data():
    result = R.calibration_number("nba")
    assert result["status"] == "ok", result
    assert "as_of" in result
    assert result["improved_ece"] == 0.03113
