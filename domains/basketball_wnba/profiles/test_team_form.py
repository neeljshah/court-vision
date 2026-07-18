"""Per-file test for domains.basketball_wnba.profiles.ingredients_team_form
-- synthetic espn_scoreboard-shaped frame only (no parquet reads): hand-
computed win_pct/home-away split/net_ppg/last10_win_pct, plus the season
filter (a 2025 game for a team that ONLY appears in 2025 must never surface).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_team_form.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_wnba.profiles.ingredients_team_form import BUILDERS


def _synthetic_frame() -> pd.DataFrame:
    rows = [
        # Team X home win, Team Y away loss
        {"date": "2026-01-01", "season": "2026", "home_team": "Team X", "away_team": "Team Y",
         "home_score": 100, "away_score": 70, "home_win": 1.0},
        # Team X away win (home_win=0 -> away side won), Team Y home loss
        {"date": "2026-01-03", "season": "2026", "home_team": "Team Y", "away_team": "Team X",
         "home_score": 60, "away_score": 80, "home_win": 0.0},
        # Team X home win, Team Y away loss
        {"date": "2026-01-05", "season": "2026", "home_team": "Team X", "away_team": "Team Y",
         "home_score": 90, "away_score": 85, "home_win": 1.0},
        # Team Y home win, Team X away loss
        {"date": "2026-01-07", "season": "2026", "home_team": "Team Y", "away_team": "Team X",
         "home_score": 95, "away_score": 65, "home_win": 1.0},
        # A 2025 game for a THIRD team pair -- must be excluded by the season filter
        {"date": "2025-06-01", "season": "2025", "home_team": "Team Z", "away_team": "Team W",
         "home_score": 50, "away_score": 40, "home_win": 1.0},
    ]
    return pd.DataFrame(rows)


def test_season_filter_excludes_non_2026_teams():
    df = _synthetic_frame()
    out = BUILDERS["win_pct"](df)
    assert "Team Z" not in set(out["entity_id"])
    assert "Team W" not in set(out["entity_id"])


def test_win_pct_and_home_away_splits_hand_computed():
    df = _synthetic_frame()
    win_pct = BUILDERS["win_pct"](df).set_index("entity_id")
    home_ppg = BUILDERS["home_ppg"](df).set_index("entity_id")
    away_ppg = BUILDERS["away_ppg"](df).set_index("entity_id")
    diff = BUILDERS["home_away_ppg_diff"](df).set_index("entity_id")
    net_ppg = BUILDERS["net_ppg"](df).set_index("entity_id")
    last10 = BUILDERS["last10_win_pct"](df).set_index("entity_id")

    # Team X: wins G1(home),G2(away) ; loss G3(home)? no -- recheck: G1 home
    # win, G2 away win, G3 home win, G4 away loss => 3 wins / 4 games
    assert win_pct.loc["Team X", "raw_value"] == pytest.approx(0.75)
    assert win_pct.loc["Team X", "n"] == 4

    # home games for X: G1(for=100), G3(for=90) -> home_ppg=95.0, n=2
    assert home_ppg.loc["Team X", "raw_value"] == pytest.approx(95.0)
    assert home_ppg.loc["Team X", "n"] == 2
    # away games for X: G2(for=80), G4(for=65) -> away_ppg=72.5, n=2
    assert away_ppg.loc["Team X", "raw_value"] == pytest.approx(72.5)
    assert away_ppg.loc["Team X", "n"] == 2
    assert diff.loc["Team X", "raw_value"] == pytest.approx(22.5)

    # net_ppg: pts_for=[100,80,90,65]=335, pts_against=[70,60,85,95]=310 -> (335-310)/4=6.25
    assert net_ppg.loc["Team X", "raw_value"] == pytest.approx(6.25)

    # only 4 games total -> last10 window == full season
    assert last10.loc["Team X", "raw_value"] == pytest.approx(0.75)
    assert last10.loc["Team X", "n"] == 4


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
