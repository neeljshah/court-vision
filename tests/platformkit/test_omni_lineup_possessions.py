"""Tests for scripts.platformkit.omni.lineup_possessions.

Covers what THIS module builds: the independent 5-on-floor validation, the
possession-clock join (incl. a period boundary), and idempotent rerun. The
raw substitution-walk itself is NOT re-tested here -- it is reused from
data/cache/team_system/lineups/stints_2024_25.parquet (built + tested by
domains/basketball_nba/lineups/pbp_lineups.py /
domains/basketball_nba/lineups/test_pbp_lineups.py); duplicating that test
here would be redundant.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_lineup_possessions.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.omni.lineup_possessions import (
    K_SHRINK,
    _out_path,
    _shrink,
    _stints_path,
    build_team_is_home,
    fit_lineup_rates,
    fit_player_rates,
    join_possessions,
    lookup_rate,
    validate_stints,
)


def _synthetic_stints() -> pd.DataFrame:
    # Game G1: two teams (100, 200), periods 1 and 2, clean 5-on-floor.
    # Team 100 subs once mid-period-1 at elapsed=300s.
    rows = [
        {"game_id": "G1", "team_id": 100, "period": 1, "lineup_key": "1,2,3,4,5",
         "n_on_court": 5, "start_s": 0.0, "end_s": 300.0},
        {"game_id": "G1", "team_id": 100, "period": 1, "lineup_key": "1,2,3,4,6",
         "n_on_court": 5, "start_s": 300.0, "end_s": 720.0},
        {"game_id": "G1", "team_id": 100, "period": 2, "lineup_key": "1,2,3,4,6",
         "n_on_court": 5, "start_s": 0.0, "end_s": 720.0},
        {"game_id": "G1", "team_id": 200, "period": 1, "lineup_key": "11,12,13,14,15",
         "n_on_court": 5, "start_s": 0.0, "end_s": 720.0},
        {"game_id": "G1", "team_id": 200, "period": 2, "lineup_key": "11,12,13,14,15",
         "n_on_court": 5, "start_s": 0.0, "end_s": 720.0},
        # Game G2: bad seed (6 on court) -- must quarantine.
        {"game_id": "G2", "team_id": 300, "period": 1, "lineup_key": "21,22,23,24,25,26",
         "n_on_court": 6, "start_s": 0.0, "end_s": 720.0},
        {"game_id": "G2", "team_id": 400, "period": 1, "lineup_key": "31,32,33,34,35",
         "n_on_court": 5, "start_s": 0.0, "end_s": 720.0},
    ]
    return pd.DataFrame(rows)


def _synthetic_boxscores() -> pd.DataFrame:
    rows = [
        {"game_id": "G1", "player_id": 1, "is_home": True},
        {"game_id": "G1", "player_id": 11, "is_home": False},
    ]
    return pd.DataFrame(rows)


def test_validate_stints_quarantines_bad_seed_game() -> None:
    stints = _synthetic_stints()
    valid, quarantined, pass_rate = validate_stints(stints)
    assert quarantined == {"G2"}
    assert valid == {"G1"}
    assert pass_rate == 0.5


def test_build_team_is_home_resolves_from_first_player() -> None:
    stints = _synthetic_stints()
    stints_g1 = stints[stints["game_id"] == "G1"]
    box = _synthetic_boxscores()
    team_is_home = build_team_is_home(stints_g1, box)
    lookup = dict(zip(team_is_home["team_id"], team_is_home["is_home"]))
    assert lookup[100] == True  # noqa: E712 -- pandas nullable BooleanDtype scalar
    assert lookup[200] == False  # noqa: E712


def test_join_possessions_across_period_boundary_and_substitution() -> None:
    stints = _synthetic_stints()
    stints_g1 = stints[stints["game_id"] == "G1"]
    box = _synthetic_boxscores()
    team_is_home = build_team_is_home(stints_g1, box)

    # Possession 1: period 1, clock_start=500 (remaining) -> elapsed=220s,
    # BEFORE the 300s sub -> team 100 lineup should still be 1,2,3,4,5.
    # Possession 2: period 1, clock_start=100 (remaining) -> elapsed=620s,
    # AFTER the sub -> lineup should be 1,2,3,4,6.
    # Possession 3: period 2, clock_start=700 -> elapsed=20s, period boundary
    # reset check -- team 100 lineup carries over as 1,2,3,4,6.
    possessions = pd.DataFrame([
        {"game_id": "G1", "period": 1, "clock_start": 500.0, "off_is_home": True},
        {"game_id": "G1", "period": 1, "clock_start": 100.0, "off_is_home": True},
        {"game_id": "G1", "period": 2, "clock_start": 700.0, "off_is_home": True},
    ])
    out, stats = join_possessions(possessions, stints_g1, team_is_home)

    assert stats["n_total_possessions"] == 3
    assert stats["n_matched"] == 3
    assert stats["join_rate"] == 1.0
    lineups = out.sort_values("possession_key")["off_lineup_ids"].tolist()
    assert lineups == ["1,2,3,4,5", "1,2,3,4,6", "1,2,3,4,6"]
    def_lineups = out["def_lineup_ids"].unique().tolist()
    assert def_lineups == ["11,12,13,14,15"]


def test_join_possessions_idempotent_rerun() -> None:
    stints = _synthetic_stints()
    stints_g1 = stints[stints["game_id"] == "G1"]
    box = _synthetic_boxscores()
    team_is_home = build_team_is_home(stints_g1, box)
    possessions = pd.DataFrame([
        {"game_id": "G1", "period": 1, "clock_start": 500.0, "off_is_home": True},
    ])
    out1, _ = join_possessions(possessions, stints_g1, team_is_home)
    out2, _ = join_possessions(possessions, stints_g1, team_is_home)
    pd.testing.assert_frame_equal(out1.reset_index(drop=True), out2.reset_index(drop=True))


def test_stints_path_and_out_path_format_season() -> None:
    assert _stints_path("2025-26").name == "stints_2025_26.parquet"
    assert _out_path("2025-26").name == "possession_lineups_2025_26.parquet"


# ---------------------------------------------------------------------------
# SPINE-3: lineup/player rate fitting + fallback ladder
# ---------------------------------------------------------------------------

def _synthetic_rating_frame() -> pd.DataFrame:
    # Team 100 lineup A (200 poss, mean 1.2) and lineup B (1 poss, mean 3.0
    # -- thin sample, should shrink hard toward team 100's mean).
    rows = [{"off_lineup_ids": "1,2,3,4,5", "off_team": 100, "points": 1.2}] * 200
    rows += [{"off_lineup_ids": "6,7,8,9,10", "off_team": 100, "points": 3.0}]
    return pd.DataFrame(rows)


def test_shrink_math_matches_formula() -> None:
    out = _shrink(mean=3.0, n=1.0, prior=1.2)
    assert out == (1.0 * 3.0 + K_SHRINK * 1.2) / (1.0 + K_SHRINK)


def test_fit_lineup_rates_shrinks_thin_lineup_toward_team_mean() -> None:
    df = _synthetic_rating_frame()
    table, team_rates, league_mean = fit_lineup_rates(df, "off_lineup_ids", "off_team")
    team_mean = team_rates[100]
    # thin lineup B (n=1) should land very close to the team mean, not 3.0
    assert abs(table["6,7,8,9,10"] - team_mean) < 0.05
    # thick lineup A (n=200) should barely move off its own raw mean
    assert abs(table["1,2,3,4,5"] - 1.2) < 0.05


def test_fit_player_rates_expands_lineup_ids_to_players() -> None:
    df = _synthetic_rating_frame()
    table, team_rates, _league_mean = fit_player_rates(df, "off_lineup_ids", "off_team")
    # player "1" appears in all 200 lineup-A possessions -> shrinks near 1.2
    assert abs(table[("1", 100)] - 1.2) < 0.05
    # player "6" appears in the single lineup-B possession -> shrinks hard to team mean
    assert abs(table[("6", 100)] - team_rates[100]) < 0.05


def test_lookup_rate_fallback_ladder() -> None:
    lineup_table = {"1,2,3,4,5": 1.10}
    player_table = {("1", 100): 1.05, ("2", 100): 1.15}
    team_rates = {100: 1.08}
    league_mean = 1.0

    # rung 1: lineup seen -> lineup rate
    rate, tier = lookup_rate("1,2,3,4,5", 100, lineup_table, player_table, team_rates, league_mean)
    assert (rate, tier) == (1.10, "lineup")

    # rung 2: lineup unseen, some players known -> player-average (team mean fills gaps)
    rate, tier = lookup_rate("1,2,99,98,97", 100, lineup_table, player_table, team_rates, league_mean)
    assert tier == "player"
    assert rate == (1.05 + 1.15 + 1.08 + 1.08 + 1.08) / 5

    # rung 3: lineup unseen AND all players unseen -> team mean
    rate, tier = lookup_rate("50,51,52,53,54", 100, lineup_table, player_table, team_rates, league_mean)
    assert (rate, tier) == (1.08, "team")

    # rung 3b: lineup missing entirely (NaN) -> team mean
    rate, tier = lookup_rate(float("nan"), 100, lineup_table, player_table, team_rates, league_mean)
    assert (rate, tier) == (1.08, "team")

    # unknown team falls back to league mean
    rate, tier = lookup_rate(None, 999, lineup_table, player_table, team_rates, league_mean)
    assert (rate, tier) == (1.0, "team")
