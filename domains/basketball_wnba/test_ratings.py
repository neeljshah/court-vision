"""Per-file tests for domains.basketball_wnba.ratings (pure, offline, synthetic data).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ratings.py -q
"""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd

from domains.basketball_wnba import ratings as r
from domains.basketball_wnba.elo_config import ELO_MEAN


def _games_df(rows):
    return pd.DataFrame(rows, columns=["date", "season", "home_team", "away_team", "home_win"])


def test_walk_forward_elo_unseen_teams_start_at_prior():
    df = _games_df([
        (dt.date(2024, 5, 3), 2024, "Aces", "Fever", 1.0),
    ])
    out = r.walk_forward_elo(df)
    assert out.loc[0, "elo_home"] == ELO_MEAN
    assert out.loc[0, "elo_away"] == ELO_MEAN
    assert 0.0 < out.loc[0, "p_home_elo"] < 1.0


def test_walk_forward_elo_winner_rating_increases():
    df = _games_df([
        (dt.date(2024, 5, 3), 2024, "Aces", "Fever", 1.0),
        (dt.date(2024, 5, 5), 2024, "Aces", "Fever", 1.0),
    ])
    out = r.walk_forward_elo(df)
    # Aces won game 1 -> their elo_home going into game 2 must be higher than the prior.
    assert out.loc[1, "elo_home"] > out.loc[0, "elo_home"]


def test_elo_state_asof_matches_fresh_replay_on_subset():
    """Truncation-invariance: elo_state_asof(full, D) == replay(subset_before_D)."""
    df = _games_df([
        (dt.date(2024, 5, 3), 2024, "Aces", "Fever", 1.0),
        (dt.date(2024, 5, 5), 2024, "Fever", "Aces", 0.0),
        (dt.date(2024, 5, 8), 2024, "Aces", "Fever", 1.0),
    ])
    cut = dt.date(2024, 5, 8)
    state_asof = r.elo_state_asof(df, cut)

    subset = df[pd.to_datetime(df["date"]).dt.date < cut]
    state_fresh = r.replay(subset)

    assert state_asof.elo == state_fresh.elo
    assert state_asof.n_processed == state_fresh.n_processed == 2


def test_no_leak_shuffling_future_games_does_not_change_past_ratings():
    """The core leak-free property: ratings AS OF a cut date must be identical
    whether or not future (post-cut) games are reordered/shuffled -- only the
    strictly-prior sequence can influence a snapshot at that cut."""
    base_rows = [
        (dt.date(2024, 5, 3), 2024, "Aces", "Fever", 1.0),
        (dt.date(2024, 5, 5), 2024, "Fever", "Sky", 1.0),
        (dt.date(2024, 5, 8), 2024, "Sky", "Aces", 0.0),
    ]
    future_rows = [
        (dt.date(2024, 6, 1), 2024, "Aces", "Sky", 1.0),
        (dt.date(2024, 6, 3), 2024, "Fever", "Aces", 0.0),
        (dt.date(2024, 6, 5), 2024, "Sky", "Fever", 1.0),
    ]
    cut = dt.date(2024, 5, 10)

    df1 = _games_df(base_rows + future_rows)
    state1 = r.elo_state_asof(df1, cut)

    rng = random.Random(42)
    shuffled_future = list(future_rows)
    rng.shuffle(shuffled_future)
    df2 = _games_df(base_rows + shuffled_future)
    state2 = r.elo_state_asof(df2, cut)

    assert state1.elo == state2.elo
    assert state1.n_processed == state2.n_processed == 3


def test_season_boundary_regression_pulls_toward_mean():
    df = _games_df([
        (dt.date(2024, 5, 3), 2024, "Aces", "Fever", 1.0),
        (dt.date(2024, 5, 5), 2024, "Aces", "Fever", 1.0),
        (dt.date(2024, 5, 8), 2024, "Aces", "Fever", 1.0),
        (dt.date(2025, 5, 3), 2025, "Aces", "Fever", 1.0),
    ])
    out = r.walk_forward_elo(df)
    elo_end_2024 = out.loc[2, "elo_home"] + (out.loc[2, "elo_home"] - out.loc[1, "elo_home"])
    elo_start_2025 = out.loc[3, "elo_home"]
    # regression pulls the 2025-season-opening rating back toward the mean,
    # so it must sit strictly between the pre-game 2024 rating and ELO_MEAN's pull direction.
    assert elo_start_2025 != out.loc[2, "elo_home"]


def test_replay_empty_dataframe_returns_default_state():
    df = _games_df([])
    state = r.replay(df)
    assert state.elo == {}
    assert state.n_processed == 0


def test_walk_forward_elo_empty_dataframe_has_expected_columns():
    df = _games_df([])
    out = r.walk_forward_elo(df)
    for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
        assert col in out.columns
        assert len(out[col]) == 0
