"""Per-file test for domains.soccer.team_defense (network-free, in-memory df).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_team_defense.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.team_defense import (
    all_multipliers,
    league_baseline,
    opponent_multiplier,
    opponent_quantity_mapping,
    team_allowed_table,
)


def _row(event_id, date, team, ha, pid, **stats):
    base = {
        "event_id": event_id,
        "date": date,
        "team_abbr": team,
        "home_away": ha,
        "player_id": pid,
        "minutes": 90.0,
        "totalShots": 0.0,
        "shotsOnTarget": 0.0,
        "foulsCommitted": 0.0,
        "foulsSuffered": 0.0,
        "yellowCards": 0.0,
        "redCards": 0.0,
        "goalAssists": 0.0,
        "offsides": 0.0,
        "totalGoals": 0.0,
        "saves": 0.0,
    }
    base.update(stats)
    return base


def _df():
    # Event 1 (BEFORE as_of): WEA (weak D) vs STR. WEA's players shoot little (2),
    # STR shoots a lot (10) -> WEA "allowed" 10 shots, STR allowed 2.
    # Event 2 (BEFORE as_of): WEA vs OTH. WEA shoots 2, OTH shoots 10 -> WEA allowed 10.
    # So WEA is a high-conceding opponent for Shots (allowed ~10 vs league mean ~6).
    # Event 9 (ON/AFTER as_of): leak row -- must be ignored.
    rows = [
        # ---- Event 1 ----
        _row(1, "2026-06-01", "WEA", "home", "w1", totalShots=1, shotsOnTarget=0, foulsCommitted=3),
        _row(1, "2026-06-01", "WEA", "home", "w2", totalShots=1, shotsOnTarget=0, foulsCommitted=2),
        _row(1, "2026-06-01", "STR", "away", "s1", totalShots=6, shotsOnTarget=4, foulsCommitted=1),
        _row(1, "2026-06-01", "STR", "away", "s2", totalShots=4, shotsOnTarget=2, foulsCommitted=0),
        # ---- Event 2 ----
        _row(2, "2026-06-03", "WEA", "home", "w1", totalShots=1, shotsOnTarget=0, foulsCommitted=4),
        _row(2, "2026-06-03", "WEA", "home", "w2", totalShots=1, shotsOnTarget=0, foulsCommitted=1),
        _row(2, "2026-06-03", "OTH", "away", "o1", totalShots=5, shotsOnTarget=3, foulsCommitted=2),
        _row(2, "2026-06-03", "OTH", "away", "o2", totalShots=5, shotsOnTarget=2, foulsCommitted=1),
        # ---- Event 3 (STR vs OTH, balanced ~2 shots each) keeps league mean down ----
        _row(3, "2026-06-05", "STR", "home", "s1", totalShots=1, shotsOnTarget=1),
        _row(3, "2026-06-05", "STR", "home", "s2", totalShots=1, shotsOnTarget=0),
        _row(3, "2026-06-05", "OTH", "away", "o1", totalShots=1, shotsOnTarget=0),
        _row(3, "2026-06-05", "OTH", "away", "o2", totalShots=1, shotsOnTarget=1),
        # ---- Event 9 (LEAK: on/after as_of) -- STR concedes 100 shots, must be ignored ----
        _row(9, "2026-06-30", "STR", "home", "s1", totalShots=0),
        _row(9, "2026-06-30", "LEK", "away", "l1", totalShots=100),
    ]
    return pd.DataFrame(rows)


AS_OF = "2026-06-10"


def test_allowed_attribution_correct():
    # Team A's shots are counted as ALLOWED by team B in the same event.
    tbl = team_allowed_table(_df(), AS_OF)
    wea = tbl[(tbl["team_abbr"] == "WEA") & (tbl["stat"] == "Shots")].iloc[0]
    # WEA allowed STR's 10 (event1) and OTH's 10 (event2) -> mean 10, n=2.
    assert wea["allowed_mean"] == 10.0
    assert wea["n"] == 2
    # WEA's OWN shots were 2 each event -> for_mean 2.
    assert wea["for_mean"] == 2.0


def test_high_conceding_opponent_mult_above_one():
    # WEA concedes ~10 shots/match vs a lower league mean -> Shots mult > 1.
    m = opponent_multiplier(_df(), "WEA", "Shots", AS_OF)
    assert m > 1.0
    assert m <= 2.0


def test_shrinkage_pulls_thin_estimate_toward_one():
    df = _df()
    # OTH appears in 2 events allowing 10 (vs STR-heavy? no): OTH allowed WEA's 2 (ev2)
    # and STR's 2 (ev3) -> low n, ratio near/below mean. Compare big shrink vs small.
    strong = opponent_multiplier(df, "WEA", "Shots", AS_OF, shrink_k=0.0)
    weak = opponent_multiplier(df, "WEA", "Shots", AS_OF, shrink_k=1000.0)
    # Heavy shrink must sit closer to 1.0 than no shrink.
    assert abs(weak - 1.0) < abs(strong - 1.0)
    assert abs(weak - 1.0) < 0.05


def test_clamp_respected():
    df = _df()
    # Force a tight clamp; a high-conceding team must be capped at the ceiling.
    m = opponent_multiplier(df, "WEA", "Shots", AS_OF, shrink_k=0.0, clamp=(0.9, 1.1))
    assert 0.9 <= m <= 1.1
    assert m == 1.1


def test_leak_free_post_as_of_ignored():
    df = _df()
    # The leak event (STR concedes 100) is dated after as_of; STR's Shots-allowed
    # table must not reflect it.
    tbl = team_allowed_table(df, AS_OF)
    assert "LEK" not in set(tbl["team_abbr"])  # leak-only team never appears
    str_row = tbl[(tbl["team_abbr"] == "STR") & (tbl["stat"] == "Shots")]
    # STR allowed WEA's 2 (ev1) and OTH's 2 (ev3) -> mean 2, NOT inflated by the 100.
    assert str_row.iloc[0]["allowed_mean"] == 2.0


def test_unknown_team_returns_one():
    assert opponent_multiplier(_df(), "NOPE", "Shots", AS_OF) == 1.0


def test_unknown_stat_returns_one():
    assert opponent_multiplier(_df(), "WEA", "NotAStat", AS_OF) == 1.0


def test_fouls_drawn_uses_opponent_committed():
    # Fouls Drawn maps to the opponent's OWN foulsCommitted ("for" side of Fouls).
    mapping = opponent_quantity_mapping()
    assert mapping["Fouls Drawn"] == ("Fouls", "for")
    # WEA commits many fouls (3+2, 4+1 = 5 each match) -> drawing more vs WEA -> mult>1.
    m = opponent_multiplier(_df(), "WEA", "Fouls Drawn", AS_OF)
    assert m > 1.0


def test_saves_uses_opponent_shots_on_target():
    mapping = opponent_quantity_mapping()
    assert mapping["Saves"] == ("Shots On Target", "for")
    m = opponent_multiplier(_df(), "WEA", "Saves", AS_OF)
    assert 0.5 <= m <= 2.0


def test_all_multipliers_keys_and_defaults():
    out = all_multipliers(_df(), "WEA", AS_OF)
    assert set(out.keys()) == set(opponent_quantity_mapping().keys())
    for v in out.values():
        assert 0.5 <= v <= 2.0
    # Unknown team -> all default to 1.0.
    out2 = all_multipliers(_df(), "NOPE", AS_OF)
    assert all(v == 1.0 for v in out2.values())


def test_bad_input_never_raises():
    assert opponent_multiplier(None, "WEA", "Shots", AS_OF) == 1.0
    assert opponent_multiplier(pd.DataFrame(), "WEA", "Shots", AS_OF) == 1.0
    assert all_multipliers(None, "WEA", AS_OF)["Shots"] == 1.0
    assert team_allowed_table(None, AS_OF).empty
    assert league_baseline(_df(), "Shots", "bad-date") is None
