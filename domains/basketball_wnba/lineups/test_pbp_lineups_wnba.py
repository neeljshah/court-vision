"""Per-file test on a SYNTHETIC fixture (no real data required): asserts the
adapter seams named in ../PBP_CENSUS.md -- starter-flag cast (started:bool ->
starter), str->int id cast, sub in/out windowing, and 10-min quarter
arithmetic -- all work by driving build_game_stints_wnba end to end on a tiny
2-team, 1-sub, 1-period synthetic game.

Run: python -m pytest domains/basketball_wnba/lineups/test_pbp_lineups_wnba.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_wnba.lineups.pbp_lineups_wnba import (
    _adapt_box_df,
    _wnba_period_length_s,
    build_game_stints_wnba,
    coverage_invariant,
)

_HOME, _AWAY = 100, 200
_HOME_STARTERS = [1, 2, 3, 4, 5]
_AWAY_STARTERS = [11, 12, 13, 14, 15]


def _synthetic_box_df() -> pd.DataFrame:
    rows = []
    for pid in _HOME_STARTERS:
        rows.append({"game_id": "G1", "team_id": "100", "player_id": str(pid), "started": True, "is_home": True})
    rows.append({"game_id": "G1", "team_id": "100", "player_id": "6", "started": False, "is_home": True})
    for pid in _AWAY_STARTERS:
        rows.append({"game_id": "G1", "team_id": "200", "player_id": str(pid), "started": True, "is_home": False})
    return pd.DataFrame(rows)


def _synthetic_game_json() -> dict:
    actions = []
    n = 1
    # filler non-sub actions so every starter is seen in PBP (the box-seed
    # guard rejects a starter set unless all 5 ids also appear in this
    # team's own actions -- personId 5/6 get covered by the sub itself).
    for pid in [1, 2, 3, 4] + _AWAY_STARTERS:
        actions.append({"actionNumber": n, "actionType": "rebound", "period": 1, "clock": "PT09M00.00S",
                         "personId": pid, "teamId": _HOME if pid < 10 else _AWAY})
        n += 1
    actions.append({"actionNumber": n, "actionType": "substitution", "subType": "out", "period": 1,
                     "clock": "PT05M00.00S", "personId": 5, "teamId": _HOME})
    n += 1
    actions.append({"actionNumber": n, "actionType": "substitution", "subType": "in", "period": 1,
                     "clock": "PT05M00.00S", "personId": 6, "teamId": _HOME})
    return {"game": {"gameId": "G1", "actions": actions}}


def test_period_length_is_wnba_10min_quarters_5min_ot() -> None:
    assert _wnba_period_length_s(1) == 600.0
    assert _wnba_period_length_s(4) == 600.0
    assert _wnba_period_length_s(5) == 300.0  # OT


def test_adapt_box_df_casts_started_bool_and_str_ids() -> None:
    adapted = _adapt_box_df(_synthetic_box_df())
    assert adapted["team"].tolist() == ["100"] * 6 + ["200"] * 5
    assert adapted["starter"].dtype == bool
    assert adapted["player_id"].dtype == "int64"


def test_build_game_stints_wnba_clean_sub_windowing_and_quarter_arithmetic() -> None:
    box_df = _adapt_box_df(_synthetic_box_df())
    stints, notes = build_game_stints_wnba(_synthetic_game_json(), box_df)
    assert notes == [], f"expected a clean box-seeded game, got quality notes: {notes}"

    df = pd.DataFrame(stints)
    assert (df["n_on_court"] == 5).all()

    per_team = df.groupby("team_id")["elapsed_s"].sum()
    assert len(per_team) == 2
    for team_id, total_s in per_team.items():
        assert abs(total_s - 600.0) < 1e-6, f"team {team_id} total stint seconds {total_s} != 600 (WNBA 10-min quarter)"

    home = df[df["team_id"] == _HOME].sort_values("start_s")
    assert len(home) == 2, "one sub-out/sub-in pair must split the home team into exactly 2 stints"
    assert home.iloc[0]["lineup_key"] == "1,2,3,4,5"
    assert home.iloc[1]["lineup_key"] == "1,2,3,4,6"
    assert home.iloc[0]["end_s"] == home.iloc[1]["start_s"] == 300.0  # PT05M00S into a 600s quarter

    away = df[df["team_id"] == _AWAY]
    assert len(away) == 1, "no subs -> away team stays one stint for the whole quarter"

    cov = coverage_invariant(df)
    assert (cov["pct_clean"] == 1.0).all()


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
