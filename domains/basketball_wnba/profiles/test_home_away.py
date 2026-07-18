"""Per-file test for domains.basketball_wnba.profiles.ingredients_home_away
-- synthetic boxscore-shaped frame only (no parquet reads): hand-computed
home/away pts_per36 + efg and their diffs, DNP exclusion, and the compound
floor (home_games>=8 AND away_games>=8) exclusion.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_home_away.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES
from domains.basketball_wnba.profiles.ingredients_home_away import BUILDERS


def _rows(player_id: int, name: str, is_home: bool, n: int, pts: float, minutes: float,
          fga: float, fgm: float, fg3m: float, played: bool = True) -> list[dict]:
    return [{
        "player_id": player_id, "player_name": name, "is_home": is_home, "played": played,
        "minutes": minutes, "pts": pts, "fga": fga, "fgm": fgm, "fg3m": fg3m,
    } for _ in range(n)]


def _synthetic_frame() -> pd.DataFrame:
    rows = []
    # Player A: 8 home + 8 away -> clears the 8/8 floor.
    rows += _rows(10, "Player A", True, 8, pts=30, minutes=30, fga=20, fgm=15, fg3m=2)
    rows += _rows(10, "Player A", False, 8, pts=20, minutes=30, fga=20, fgm=8, fg3m=2)
    # a DNP row (played=False) for Player A -- must never enter either split.
    rows += _rows(10, "Player A", True, 1, pts=0, minutes=0, fga=0, fgm=0, fg3m=0, played=False)
    # Player B: only 3 home games -> fails the home_games>=8 half of the floor.
    rows += _rows(20, "Player B", True, 3, pts=10, minutes=20, fga=10, fgm=5, fg3m=0)
    rows += _rows(20, "Player B", False, 8, pts=10, minutes=20, fga=10, fgm=5, fg3m=0)
    return pd.DataFrame(rows)


def test_dnp_rows_excluded_from_game_counts():
    df = _synthetic_frame()
    out = BUILDERS["home_pts_per36"](df).set_index("entity_id")
    assert out.loc["10", "ingredients"]["n_home"] == 8  # not 9 -- the DNP row never counts


def test_hand_computed_home_away_and_diffs():
    df = _synthetic_frame()
    home_pts = BUILDERS["home_pts_per36"](df).set_index("entity_id")
    away_pts = BUILDERS["away_pts_per36"](df).set_index("entity_id")
    home_efg = BUILDERS["home_efg"](df).set_index("entity_id")
    away_efg = BUILDERS["away_efg"](df).set_index("entity_id")
    diff_pts = BUILDERS["home_away_pts_per36_diff"](df).set_index("entity_id")
    diff_efg = BUILDERS["home_away_efg_diff"](df).set_index("entity_id")

    assert home_pts.loc["10", "raw_value"] == pytest.approx(36.0)  # 36*30/30
    assert away_pts.loc["10", "raw_value"] == pytest.approx(24.0)  # 36*20/30
    assert diff_pts.loc["10", "raw_value"] == pytest.approx(12.0)
    assert diff_pts.loc["10", "n"] == 8  # min(n_home=8, n_away=8)

    assert home_efg.loc["10", "raw_value"] == pytest.approx(0.8)   # (15+1)/20
    assert away_efg.loc["10", "raw_value"] == pytest.approx(0.45)  # (8+1)/20
    assert diff_efg.loc["10", "raw_value"] == pytest.approx(0.35)


def test_compound_floor_excludes_home_games_below_8():
    df = _synthetic_frame()
    out = BUILDERS["home_pts_per36"](df).set_index("entity_id")
    assert out.loc["20", "n"] == 3  # min(n_home=3, n_away=8)
    floor = ATTRIBUTES["home_pts_per36"]["floor"]
    qualified = out[out["n"] >= floor]
    assert "20" not in qualified.index
    assert "10" in qualified.index


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
