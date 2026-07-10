"""Per-file test for domains.mlb.carryover_asof.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_carryover_asof.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb import carryover_asof as C


def _pitch(game_pk, date, pitcher, home, away, topbot, inning, outs, ab, pn):
    return {"game_pk": game_pk, "game_date": date, "pitcher": pitcher,
            "home_team": home, "away_team": away, "inning_topbot": topbot,
            "inning": inning, "outs_when_up": outs, "at_bat_number": ab, "pitch_number": pn}


def _synthetic_pitch_df() -> pd.DataFrame:
    """2 games for pitcher 111 (home SP, team HOU): G1 on day 1 (3 pitches),
    G2 on day 6 (2 pitches) -- G2's carryover should see G1's 3 pitches + 5
    rest days. A reliever (222) also throws in G1 but must be excluded from
    the starter's own pitch count. Away side (team TEX) pitcher 333 starts
    both games too, isolating the two teams' LAG-1 independently."""
    rows = [
        # G1: HOU (home) pitches in Top half; starter 111 throws first, reliever 222 finishes.
        _pitch(1, "2023-04-01", 111, "HOU", "TEX", "Top", 1, 0, 1, 1),
        _pitch(1, "2023-04-01", 111, "HOU", "TEX", "Top", 1, 1, 2, 1),
        _pitch(1, "2023-04-01", 222, "HOU", "TEX", "Top", 5, 0, 20, 1),  # reliever, later inning
        # G1: TEX (away) pitches in Bot half; starter 333.
        _pitch(1, "2023-04-01", 333, "HOU", "TEX", "Bot", 1, 0, 1, 1),
        # G2 (5 days later): HOU starter 111 again, TEX starter 333 again.
        _pitch(2, "2023-04-06", 111, "HOU", "TEX", "Top", 1, 0, 1, 1),
        _pitch(2, "2023-04-06", 111, "HOU", "TEX", "Top", 1, 0, 1, 2),
        _pitch(2, "2023-04-06", 333, "HOU", "TEX", "Bot", 1, 0, 1, 1),
    ]
    return pd.DataFrame(rows)


def _games_current() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "E1", "date": "2023-04-01", "home_team": "HOU", "away_team": "TEX", "season": 2023},
        {"event_id": "E2", "date": "2023-04-06", "home_team": "HOU", "away_team": "TEX", "season": 2023},
    ])


def test_build_starts_excludes_reliever_pitches():
    starts = C.build_starts(_synthetic_pitch_df())
    g1_home = starts[(starts["game_pk"] == 1) & (starts["pitch_team"] == "HOU")].iloc[0]
    assert g1_home["pitcher"] == 111
    assert g1_home["n_pitches"] == 2  # only the starter's own 2 pitches, reliever's 1 excluded


def test_lag1_pitch_count_and_rest_days(tmp_path):
    path = C.build_carryover_asof(
        "2023", pitch_df=_synthetic_pitch_df(), games_current=_games_current(),
        out_path=tmp_path / "out.parquet")
    out = pd.read_parquet(path)
    e1 = out[out["event_id"] == "E1"].iloc[0]
    assert pd.isna(e1["home_sp_prior_pitch_count_asof"])  # pitcher 111's first start on-disk

    e2 = out[out["event_id"] == "E2"].iloc[0]
    assert e2["home_sp_prior_pitch_count_asof"] == 2.0  # G1's 2 starter pitches carried forward
    assert e2["home_sp_rest_days_asof"] == 5.0
    assert e2["away_sp_prior_pitch_count_asof"] == 1.0
    assert e2["sp_prior_pitch_count_diff_asof"] == 1.0  # home(2) - away(1)


def test_unmatched_schedule_rows_are_dropped_not_fabricated(tmp_path):
    """A game with no games_current schedule-key match (e.g. an exhibition)
    must be dropped entirely, never guessed into a fake event_id."""
    pitch_df = _synthetic_pitch_df()
    gc = _games_current().iloc[:1]  # only E1 known; E2's schedule row is absent
    path = C.build_carryover_asof("2023", pitch_df=pitch_df, games_current=gc, out_path=tmp_path / "out.parquet")
    out = pd.read_parquet(path)
    assert set(out["event_id"]) == {"E1"}


def test_empty_input_yields_empty_output_columns(tmp_path):
    empty = pd.DataFrame(columns=C._PITCH_COLS)
    path = C.build_carryover_asof("2023", pitch_df=empty, games_current=_games_current(),
                                   out_path=tmp_path / "out.parquet")
    out = pd.read_parquet(path)
    assert list(out.columns) == C.OUTPUT_COLS
    assert len(out) == 0
