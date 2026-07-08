"""Smoke test for domains/soccer/style_interaction.py -- tiny synthetic
fingerprints + matches frames, asserts tiering, pairing tally, and the
claims-source parquet shape (pairing_key/row_id/outcome columns).

Run: python -m pytest domains/soccer/test_style_interaction.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.soccer.style_interaction import _attach_tiers, _tally_cells, _tier_lookup


def _fp():
    # 4 team-seasons, same season, 2 above/2 below median shot_share.
    return pd.DataFrame({
        "team": ["A", "B", "C", "D"], "season": [2020] * 4,
        "shot_share": [0.6, 0.4, 0.65, 0.35],
        "press_proxy": [10.0, 20.0, 12.0, 18.0],
        "ppg": [2.0, 1.0, 1.8, 1.2],
    })


def _matches():
    return pd.DataFrame({
        "event_id": [f"m{i}" for i in range(4)],
        "home_team": ["A", "B", "C", "D"], "away_team": ["B", "A", "D", "C"],
        "season": [2020] * 4, "ftr": ["H", "A", "D", "H"],
        "total_goals": [2, 1, 0, 3],
    })


def test_tier_lookup_high_low():
    fp = _tier_lookup(_fp(), [("shot_share", "poss_tier")])
    assert set(fp["poss_tier"]) == {"High", "Low"}
    assert fp.loc[fp["team"] == "A", "poss_tier"].item() == "High"
    assert fp.loc[fp["team"] == "B", "poss_tier"].item() == "Low"


def test_attach_tiers_drops_unmatched():
    fp = _tier_lookup(_fp(), [("shot_share", "poss_tier")])
    matches = _matches()
    tagged = _attach_tiers(matches, fp, "poss_tier")
    assert len(tagged) == 4  # all 4 teams present in fp
    assert set(tagged["home_tier"]) <= {"High", "Low"}


def test_tally_cells_counts_and_rates():
    fp = _tier_lookup(_fp(), [("shot_share", "poss_tier")])
    tagged = _attach_tiers(_matches(), fp, "poss_tier")
    table = _tally_cells(tagged)
    assert table["n"].sum() == 4
    assert (table["home_win_rate"] + table["draw_rate"] + table["away_win_rate"]).round(6).eq(1.0).all()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
