"""Per-file test for domains.basketball_wnba.profiles.ingredients_schedule_rest
-- synthetic frames only (no parquet reads): team-grain rest hand-computed
values + floor exclusion, player-grain rest-split delta hand-computed +
compound-floor exclusion + bootstrap CI determinism, and the leak-freeness
identity check (a team's FIRST game in the corpus must have NaN rest, never
zero-filled, and must never enter any aggregate).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_schedule_rest.py -q
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES
from domains.basketball_wnba.profiles.ingredients_schedule_rest import BUILDERS, _team_game_rest


def _make_dates(n: int, deltas: list[int]) -> list[date]:
    d = date(2026, 1, 1)
    out = [d]
    for i in range(n - 1):
        d = d + timedelta(days=deltas[i % len(deltas)])
        out.append(d)
    return out


def _synthetic_frame() -> pd.DataFrame:
    # Team 1 / Player A: 13 dates -> 12 known-rest games, gaps alternate
    # 2 (short) / 4 (long) -- 6 short + 6 long, both clear the n>=5 floor.
    dates1 = _make_dates(13, [2, 4])
    rows = []
    for i, d in enumerate(dates1):
        is_short = i % 2 == 1  # i=1,3,5,7,9,11 land on a rest=2 gap; i=2,4,..12 on rest=4
        rows.append({
            "game_id": f"g1_{i}", "game_date": d, "team_id": 1, "player_id": 100, "player_name": "Player A",
            "is_home": True, "played": True,
            "minutes": 30.0, "pts": 30 if is_short else 15, "fga": 20,
            "fgm": 15 if is_short else 5, "fg3m": 2,
        })
    # Team 2: 4 dates, rest sequence [NaN, 2, 1, 4] -- clean team-grain hand computation.
    dates2 = [date(2026, 2, 1), date(2026, 2, 3), date(2026, 2, 4), date(2026, 2, 8)]
    for i, d in enumerate(dates2):
        rows.append({
            "game_id": f"g2_{i}", "game_date": d, "team_id": 2, "player_id": 200, "player_name": "Player B",
            "is_home": False, "played": True, "minutes": 20.0, "pts": 10, "fga": 10, "fgm": 5, "fg3m": 0,
        })
    return pd.DataFrame(rows)


def test_team_game_rest_first_game_is_nan_never_zero_filled():
    """Leak-free identity check: a team's first game has no prior game, so
    rest_days must be NaN, never 0 or dropped-then-reappearing as a number."""
    tg = _team_game_rest(_synthetic_frame())
    first_team1 = tg[tg["team_id"] == 1].sort_values("game_date").iloc[0]
    assert pd.isna(first_team1["rest_days"])
    first_team2 = tg[tg["team_id"] == 2].sort_values("game_date").iloc[0]
    assert pd.isna(first_team2["rest_days"])


def test_team_grain_hand_computed_and_floor_exclusion():
    df = _synthetic_frame()
    avg = BUILDERS["avg_rest_days"](df).set_index("entity_id")
    b2b = BUILDERS["b2b_rate"](df).set_index("entity_id")
    short = BUILDERS["short_rest_rate"](df).set_index("entity_id")

    # team 2: rest=[2,1,4] (first game's NaN excluded) -> n=3
    assert avg.loc["2", "n"] == 3
    assert avg.loc["2", "raw_value"] == pytest.approx(7.0 / 3.0)
    assert b2b.loc["2", "raw_value"] == pytest.approx(1.0 / 3.0)  # only rest=1 qualifies
    assert short.loc["2", "raw_value"] == pytest.approx(2.0 / 3.0)  # rest=2 and rest=1 both <=2
    assert b2b.loc["2", "ingredients"]["b2b_count"] == 1

    # team 1: 12 known-rest games (6 short-gap=2, 6 long-gap=4) -> n=12
    assert avg.loc["1", "n"] == 12
    assert avg.loc["1", "raw_value"] == pytest.approx((2.0 + 4.0) / 2.0)  # mean of alternating 2/4 gaps = 3.0

    # floor=10 (declared in attribute_registry): team 1 (n=12) qualifies, team 2 (n=3) does not
    floor = ATTRIBUTES["avg_rest_days"]["floor"]
    qualified = avg[avg["n"] >= floor]
    assert set(qualified.index) == {"1"}


def test_player_rest_split_hand_computed_delta_and_ci_determinism():
    df = _synthetic_frame()
    out_pts = BUILDERS["rest_split_pts_per36"](df).set_index("entity_id")
    out_efg = BUILDERS["rest_split_efg"](df).set_index("entity_id")

    # Player A: short games pts_per36=36*30/30=36 (constant), long games=36*15/30=18 (constant)
    row = out_pts.loc["100"]
    assert row["raw_value"] == pytest.approx(18.0)
    assert row["n"] == 6  # min(n_short=6, n_long=6)
    assert row["ingredients"]["n_short"] == 6
    assert row["ingredients"]["n_long"] == 6
    # zero within-group variance -> bootstrap CI collapses to the point delta exactly
    assert row["ingredients"]["delta_ci95"] == pytest.approx([18.0, 18.0])

    # efg: short=(15+1)/20=0.8, long=(5+1)/20=0.3 -> delta=0.5
    assert out_efg.loc["100", "raw_value"] == pytest.approx(0.5)

    # Player B only has 4 games all on the same team, never split into both
    # a short AND a long group of >=1 each in a way that clears the floor --
    # floor=5 must exclude it (n_short/n_long too small).
    floor = ATTRIBUTES["rest_split_pts_per36"]["floor"]
    qualified = out_pts[out_pts["n"] >= floor]
    assert "200" not in qualified.index


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
