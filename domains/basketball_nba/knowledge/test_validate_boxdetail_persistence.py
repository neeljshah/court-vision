"""Tests for domains.basketball_nba.knowledge.validate_boxdetail_persistence."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge.validate_boxdetail_persistence import (
    _load_team_games, _margin_relation, _persistence_split_half, _verdict, hypothesis,
)


def _toy_espn_box() -> pd.DataFrame:
    # Teams A/B/C: A always high fast_break_pts + wins big, B always low +
    # loses big, C in between -> a real, monotone split-half persistence AND
    # a real margin relation (pearsonr needs >=3 team-points to be defined).
    # STARS row must be excluded entirely.
    rows = []
    for i, d in enumerate(pd.date_range("2026-01-01", periods=8, freq="10D")):
        rows.append({
            "date": d, "home_abbr": "A", "away_abbr": "B",
            "home_score": 120.0, "away_score": 95.0,
            "home_fast_break_pts": 22.0 + i * 0.1, "away_fast_break_pts": 6.0,
            "home_paint_pts": 40.0, "away_paint_pts": 40.0,
            "home_tov_pts": 15.0, "away_tov_pts": 15.0,
        })
        rows.append({
            "date": d, "home_abbr": "C", "away_abbr": "B",
            "home_score": 108.0, "away_score": 95.0,
            "home_fast_break_pts": 14.0, "away_fast_break_pts": 6.0,
            "home_paint_pts": 40.0, "away_paint_pts": 40.0,
            "home_tov_pts": 15.0, "away_tov_pts": 15.0,
        })
    rows.append({
        "date": pd.Timestamp("2026-02-15"), "home_abbr": "STARS", "away_abbr": "STRIPES",
        "home_score": 200.0, "away_score": 190.0,
        "home_fast_break_pts": 50.0, "away_fast_break_pts": 45.0,
        "home_paint_pts": 60.0, "away_paint_pts": 60.0,
        "home_tov_pts": 20.0, "away_tov_pts": 20.0,
    })
    return pd.DataFrame(rows)


def test_load_team_games_excludes_allstar_and_melts_both_sides():
    tg = _load_team_games(_toy_espn_box())
    assert set(tg["team"].unique()) == {"A", "B", "C"}
    assert len(tg) == 32  # 16 games x 2 sides, all-star row dropped
    a_row = tg[(tg["team"] == "A")].iloc[0]
    assert a_row["margin"] == 25.0  # 120 - 95


def test_persistence_and_margin_detect_real_signal_for_fast_break():
    tg = _load_team_games(_toy_espn_box())
    persist = _persistence_split_half(tg, "fast_break_pts")
    margin = _margin_relation(tg, "fast_break_pts")
    # A > C > B in fast_break_pts, same ranking both halves + same margin
    # ranking (A wins by 25, C wins by 13, B always loses) -> strong r.
    assert persist["n"] == 3  # A, B, C
    assert persist["r"] > 0.9
    assert margin["r"] > 0.9


def test_flat_stat_is_null_not_confirmed():
    tg = _load_team_games(_toy_espn_box())
    persist = _persistence_split_half(tg, "paint_pts")  # constant 40.0 both sides
    # constant series -> pearsonr degenerates to nan; must not crash and must
    # not be reported as CONFIRMED.
    verdict = _verdict(persist["p"], persist["r"], 0.001, 0.3)
    assert verdict in ("NOT_TESTABLE", "NULL_LOCAL")


def test_hypothesis_shape_and_verdict_values_are_json_safe():
    tg = _load_team_games(_toy_espn_box())
    h = hypothesis(tg, "fast_break_pts")
    assert h["hypothesis"] == "boxdetail_fast_break_pts_persistence_and_margin"
    assert h["verdict"] in ("CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE")
    assert isinstance(h["note"], str) and "persistence" in h["note"]


def test_verdict_requires_both_legs():
    assert _verdict(0.001, 0.3, 0.001, 0.3) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.3, 0.001, 0.3) == "NULL_LOCAL"  # persistence fails
    assert _verdict(0.001, 0.3, 0.5, 0.3) == "NULL_LOCAL"  # margin fails
    assert _verdict(np.nan, np.nan, 0.001, 0.3) == "NOT_TESTABLE"


if __name__ == "__main__":
    test_load_team_games_excludes_allstar_and_melts_both_sides()
    test_persistence_and_margin_detect_real_signal_for_fast_break()
    test_flat_stat_is_null_not_confirmed()
    test_hypothesis_shape_and_verdict_values_are_json_safe()
    test_verdict_requires_both_legs()
    print("OK: validate_boxdetail_persistence self-checks pass.")
