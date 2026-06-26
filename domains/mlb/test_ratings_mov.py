"""domains/mlb/test_ratings_mov.py -- hermetic unit tests for ratings_mov.

All tests are self-contained: tiny in-memory DataFrames, no network, no disk.
Run with: python -m pytest domains/mlb/test_ratings_mov.py -q
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from domains.mlb.config import ELO_MEAN, ELO_K
from domains.mlb.ratings_mov import _mov_mult, walk_forward_elo_mov


# ---------------------------------------------------------------------------
# _mov_mult -- degenerate-damp fix (FAIL-BEFORE / PASS-AFTER)
# ---------------------------------------------------------------------------


def test_mov_mult_zero_offset_zero_elodiff_returns_one():
    """mov_offset=0.0 + elo_diff_hfa=0.0 -> damp=0 -> was ZeroDivisionError."""
    result = _mov_mult(3.0, 0.0, mov_scale=1.0, mov_offset=0.0)
    assert result == 1.0


def test_mov_mult_negative_offset_zero_elodiff_returns_one():
    """mov_offset=-1.0 + elo_diff_hfa=0.0 -> damp=-1.0 -> was negative."""
    result = _mov_mult(3.0, 0.0, 1.0, mov_offset=-1.0)
    assert result == 1.0


def test_mov_mult_negative_offset_small_elodiff_still_nonpositive_returns_one():
    """mov_offset=-5.0, elo_diff_hfa=10.0 -> damp=-5.0+0.01=-4.99 -> still <=0."""
    result = _mov_mult(3.0, 10.0, 1.0, mov_offset=-5.0)
    assert result == 1.0


# ---------------------------------------------------------------------------
# _mov_mult -- valid behavior
# ---------------------------------------------------------------------------


def test_mov_mult_zero_scale_returns_one():
    """mov_scale <= 0 always returns 1.0 regardless of other args."""
    assert _mov_mult(10.0, 500.0, mov_scale=0.0, mov_offset=2.2) == 1.0
    assert _mov_mult(10.0, 500.0, mov_scale=-1.0, mov_offset=2.2) == 1.0
    assert _mov_mult(0.0, 0.0, mov_scale=0.0, mov_offset=0.0) == 1.0


def test_mov_mult_positive_for_valid_inputs():
    """Default-ish positive inputs produce a strictly positive multiplier."""
    result = _mov_mult(3.0, 50.0, mov_scale=1.5, mov_offset=2.2)
    assert result > 0.0


def test_mov_mult_increases_with_run_margin():
    """Larger |run_diff| -> larger multiplier (log is monotone)."""
    small = _mov_mult(1.0, 0.0, mov_scale=1.0, mov_offset=2.2)
    large = _mov_mult(8.0, 0.0, mov_scale=1.0, mov_offset=2.2)
    assert large > small


def test_mov_mult_decreases_with_elo_diff():
    """Larger |elo_diff_hfa| -> larger damp -> smaller multiplier."""
    close = _mov_mult(5.0, 0.0, mov_scale=1.0, mov_offset=2.2)
    blowout = _mov_mult(5.0, 500.0, mov_scale=1.0, mov_offset=2.2)
    assert blowout < close


def test_mov_mult_formula_explicit():
    """Verify the exact formula for a known, positive-damp case."""
    run_diff = 4.0
    elo_diff = 200.0
    mov_scale = 1.0
    mov_offset = 2.2
    damp = mov_offset + abs(elo_diff) * 0.001
    expected = math.log(abs(run_diff) + 1.0) * mov_scale / damp
    assert abs(_mov_mult(run_diff, elo_diff, mov_scale, mov_offset) - expected) < 1e-12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_games(records):
    """Build a minimal games DataFrame from a list of dicts."""
    return pd.DataFrame(records)


def _two_team_df(home_wins: bool, season: int = 2015) -> pd.DataFrame:
    """One game between NYY and BOS."""
    return _make_games([{
        "date": f"{season}-04-01",
        "home_team": "NYY",
        "away_team": "BOS",
        "season": season,
        "home_runs": 5.0 if home_wins else 2.0,
        "away_runs": 2.0 if home_wins else 5.0,
    }])


# ---------------------------------------------------------------------------
# walk_forward_elo_mov -- leak-free contract
# ---------------------------------------------------------------------------


def test_first_game_pregame_elo_is_mean():
    """First chronological game must have pre-game elo_home == elo_away == ELO_MEAN."""
    df = _two_team_df(home_wins=True)
    out = walk_forward_elo_mov(df)
    row = out.iloc[0]
    assert row["elo_home"] == ELO_MEAN
    assert row["elo_away"] == ELO_MEAN


def test_pregame_columns_present():
    """Output must include the 4 pre-game columns."""
    df = _two_team_df(home_wins=True)
    out = walk_forward_elo_mov(df)
    for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
        assert col in out.columns, f"missing column: {col}"


# ---------------------------------------------------------------------------
# walk_forward_elo_mov -- mov_scale=0 reproduces baseline update exactly
# ---------------------------------------------------------------------------


def test_baseline_update_exact_with_mov_scale_zero():
    """With mov_scale=0, the Elo delta after one game equals K*(s_home - p_home)."""
    df = _two_team_df(home_wins=True, season=2015)
    out = walk_forward_elo_mov(df, mov_scale=0.0)

    row = out.iloc[0]
    p = row["p_home_elo"]
    s_home = 1.0  # home won

    expected_delta = ELO_K * (s_home - p)

    # To observe post-game ratings we need a second game in the same season.
    df2 = _make_games([
        {
            "date": "2015-04-01",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 5.0,
            "away_runs": 2.0,
        },
        {
            "date": "2015-04-02",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 3.0,
            "away_runs": 1.0,
        },
    ])
    out2 = walk_forward_elo_mov(df2, mov_scale=0.0)

    pre_g1_home = out2.iloc[0]["elo_home"]   # == ELO_MEAN
    pre_g2_home = out2.iloc[1]["elo_home"]   # post-game-1 home rating
    actual_delta = pre_g2_home - pre_g1_home

    # Use p from the first row of out2 for the comparison
    p_g1 = out2.iloc[0]["p_home_elo"]
    expected_delta2 = ELO_K * (1.0 - p_g1)

    assert abs(actual_delta - expected_delta2) < 1e-9


# ---------------------------------------------------------------------------
# walk_forward_elo_mov -- zero-sum rating update
# ---------------------------------------------------------------------------


def test_home_winner_rises_away_loser_falls_equal_magnitude():
    """Home winner's rating rises; away loser's falls by same magnitude (zero-sum)."""
    df2 = _make_games([
        {
            "date": "2015-04-01",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 5.0,
            "away_runs": 2.0,
        },
        {
            "date": "2015-04-02",
            "home_team": "BOS",
            "away_team": "NYY",
            "season": 2015,
            "home_runs": 3.0,
            "away_runs": 1.0,
        },
    ])
    out = walk_forward_elo_mov(df2, mov_scale=0.0)

    # After game 1: NYY improved, BOS fell by same amount.
    pre1_home = out.iloc[0]["elo_home"]   # NYY pre-game-1
    pre1_away = out.iloc[0]["elo_away"]   # BOS pre-game-1

    # Game 2: BOS is home, NYY is away.
    pre2_home = out.iloc[1]["elo_home"]   # BOS pre-game-2 (= post-game-1)
    pre2_away = out.iloc[1]["elo_away"]   # NYY pre-game-2 (= post-game-1)

    delta_nyyup = pre2_away - pre1_home     # NYY rose (as game-1 home winner)
    delta_bosdown = pre2_home - pre1_away   # BOS fell (as game-1 away loser)

    # delta_nyyup > 0; delta_bosdown < 0; magnitudes equal
    assert delta_nyyup > 0.0
    assert delta_bosdown < 0.0
    assert abs(abs(delta_nyyup) - abs(delta_bosdown)) < 1e-9


# ---------------------------------------------------------------------------
# walk_forward_elo_mov -- output is in chronological order
# ---------------------------------------------------------------------------


def test_output_in_chronological_order():
    """Output rows are sorted by (date, home_team, away_team) ascending."""
    df = _make_games([
        {
            "date": "2015-04-03",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 4.0,
            "away_runs": 2.0,
        },
        {
            "date": "2015-04-01",
            "home_team": "BOS",
            "away_team": "NYY",
            "season": 2015,
            "home_runs": 3.0,
            "away_runs": 1.0,
        },
    ])
    out = walk_forward_elo_mov(df, mov_scale=0.0)
    dates = out["date"].tolist()
    assert dates == sorted(dates), "output not in chronological order"


# ---------------------------------------------------------------------------
# walk_forward_elo_mov -- MOV multiplier amplifies update vs baseline
# ---------------------------------------------------------------------------


def test_mov_multiplier_amplifies_update():
    """With mov_scale > 0, the rating change after a blowout is larger than baseline."""
    df2 = _make_games([
        {
            "date": "2015-04-01",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 10.0,
            "away_runs": 1.0,
        },
        {
            "date": "2015-04-02",
            "home_team": "NYY",
            "away_team": "BOS",
            "season": 2015,
            "home_runs": 3.0,
            "away_runs": 1.0,
        },
    ])
    base = walk_forward_elo_mov(df2, mov_scale=0.0)
    mov  = walk_forward_elo_mov(df2, mov_scale=1.0, mov_offset=2.2)

    delta_base = base.iloc[1]["elo_home"] - base.iloc[0]["elo_home"]
    delta_mov  = mov.iloc[1]["elo_home"]  - mov.iloc[0]["elo_home"]

    # Blowout (9-run margin) with positive mov_scale should amplify
    assert delta_mov > delta_base
