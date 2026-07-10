"""Per-file tests for domains.mlb.umpire_assignment_gate.

Offline only: pure synthetic pandas DataFrames/dicts, no parquet/jsonl reads,
no network.

Run ONLY this file:
  python -m pytest domains/mlb/test_umpire_assignment_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.umpire_assignment_gate import (
    MIN_GAMES_THRESHOLD,
    UMPIRE_TERM_SCALE,
    assemble_gate_corpus,
    climatology_total,
    derive_outcome_from_ticks,
    parse_home_plate_assignments,
    parse_umpire_profile,
    score_corpus,
    select_pregame_market_total,
    shuffle_scorable_umpire_terms,
)


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def test_parse_home_plate_assignments_filters_and_keeps_earliest_capture():
    raw = pd.DataFrame([
        {"game_pk": 1, "game_date": "2026-07-09", "home_team": "AAA", "away_team": "BBB",
         "official_type": "Home Plate", "umpire_id": 10, "umpire_name": "X",
         "captured_at": "2026-07-09T12:00:00Z"},
        {"game_pk": 1, "game_date": "2026-07-09", "home_team": "AAA", "away_team": "BBB",
         "official_type": "Home Plate", "umpire_id": 10, "umpire_name": "X",
         "captured_at": "2026-07-08T06:00:00Z"},  # earlier snapshot, same game
        {"game_pk": 1, "game_date": "2026-07-09", "home_team": "AAA", "away_team": "BBB",
         "official_type": "First Base", "umpire_id": 20, "umpire_name": "Y",
         "captured_at": "2026-07-08T06:00:00Z"},
    ])
    out = parse_home_plate_assignments(raw)
    assert len(out) == 1
    assert out.iloc[0]["captured_at"] == "2026-07-08T06:00:00Z"


def test_parse_umpire_profile_weighted_league_mean():
    claim = {"ranking": [
        {"umpire_id": "1", "value": 0.30, "n": 100},
        {"umpire_id": "2", "value": 0.20, "n": 100},
    ]}
    profile, league_mean = parse_umpire_profile(claim)
    assert profile == {"1": 0.30, "2": 0.20}
    assert league_mean == 0.25


# --------------------------------------------------------------------------- #
# outcome derivation
# --------------------------------------------------------------------------- #
def test_derive_outcome_completed_game():
    ticks = [
        {"captured_at": "t1", "inning": 1, "outs": 0, "score_home": 0, "score_away": 0},
        {"captured_at": "t2", "inning": 9, "outs": 3, "score_home": 4, "score_away": 6},
    ]
    out = derive_outcome_from_ticks(ticks)
    assert out["total_runs"] == 10.0
    assert out["completed"] is True


def test_derive_outcome_in_progress_game_not_completed():
    ticks = [{"captured_at": "t1", "inning": 3, "outs": 2, "score_home": 1, "score_away": 0}]
    out = derive_outcome_from_ticks(ticks)
    assert out["completed"] is False


def test_derive_outcome_empty_ticks_returns_none():
    assert derive_outcome_from_ticks([]) is None


# --------------------------------------------------------------------------- #
# market selection: the pregame-leak check
# --------------------------------------------------------------------------- #
def test_select_pregame_market_total_excludes_post_commence_rows():
    commence = "2026-07-08T22:40Z"
    records = [
        {"captured_at": "2026-07-09T00:00:18+00:00", "line": 9.5, "devigged_prob": 0.51},  # AFTER commence
        {"captured_at": "2026-07-08T20:00:00Z", "line": 8.5, "devigged_prob": 0.49},        # BEFORE commence
        {"captured_at": "2026-07-08T21:30:00Z", "line": 9.0, "devigged_prob": 0.50},        # BEFORE, later
    ]
    best = select_pregame_market_total(records, commence)
    assert best["line"] == 9.0  # latest of the two pre-commence rows


def test_select_pregame_market_total_none_when_all_rows_postdate_commence():
    commence = "2026-07-08T22:40Z"
    records = [{"captured_at": "2026-07-09T00:00:18+00:00", "line": 9.5, "devigged_prob": 0.51}]
    assert select_pregame_market_total(records, commence) is None


def test_select_pregame_market_total_none_when_commence_unknown():
    assert select_pregame_market_total([{"captured_at": "x", "line": 9.0}], None) is None


# --------------------------------------------------------------------------- #
# climatology fallback
# --------------------------------------------------------------------------- #
def test_climatology_total_falls_back_to_full_corpus_when_too_few_prior_rows():
    games = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 5 + ["2026-07-01"] * 5),
        "home_runs": [4] * 10, "away_runs": [4] * 10,
    })
    # only the 5 Jan rows are strictly before 2026-02-01 -- below the 30-row floor
    assert climatology_total(games, "2026-02-01") == 8.0


# --------------------------------------------------------------------------- #
# corpus assembly: leak flag + candidate math + baseline fallback
# --------------------------------------------------------------------------- #
def test_assemble_gate_corpus_flags_post_commence_capture_as_not_leak_free():
    assignments = pd.DataFrame([{
        "game_pk": 1, "game_date": "2026-07-09", "home_team": "AAA", "away_team": "BBB",
        "umpire_id": 10, "umpire_name": "X", "captured_at": "2026-07-09T23:52:19Z",
    }])
    profile, league_mean = {"10": 0.31}, 0.28
    outcomes = {1: {"total_runs": 9.0, "completed": True}}
    market_by_game = {1: {"line": 8.5, "captured_at": "2026-07-08T20:00:00Z"}}
    commence_by_game = {1: "2026-07-08T22:40Z"}  # captured_at above is AFTER this

    df = assemble_gate_corpus(assignments, profile, league_mean, outcomes,
                               market_by_game, commence_by_game, climatology_fn=lambda gd: 8.5)
    row = df.iloc[0]
    assert bool(row["pregame_leak_free"]) is False
    assert bool(row["scorable"]) is False  # completed but not pregame-leak-free
    expected_term = 0.31 - 0.28
    assert row["ump_term"] == expected_term
    assert row["candidate_pred"] == 8.5 - expected_term * UMPIRE_TERM_SCALE


def test_assemble_gate_corpus_falls_back_to_climatology_when_no_market_row():
    assignments = pd.DataFrame([{
        "game_pk": 2, "game_date": "2026-07-09", "home_team": "AAA", "away_team": "BBB",
        "umpire_id": 99, "umpire_name": "Z", "captured_at": "2026-07-08T10:00:00Z",
    }])
    outcomes = {2: {"total_runs": 7.0, "completed": True}}
    df = assemble_gate_corpus(assignments, profile={}, league_mean=0.28, outcomes=outcomes,
                               market_by_game={2: None}, commence_by_game={2: "2026-07-08T22:40Z"},
                               climatology_fn=lambda gd: 8.75)
    row = df.iloc[0]
    assert row["baseline_source"] == "climatology"
    assert row["baseline_pred"] == 8.75
    assert row["ump_term"] == 0.0  # umpire missing from profile -> no guess
    assert bool(row["pregame_leak_free"]) is True  # captured well before commence


# --------------------------------------------------------------------------- #
# planted null
# --------------------------------------------------------------------------- #
def test_shuffle_preserves_totals_and_ump_term_multiset():
    df = pd.DataFrame({
        "total_runs": [8, 9, 10], "baseline_pred": [8.5, 8.5, 8.5],
        "ump_term": [0.01, -0.02, 0.03], "scorable": [True, True, True],
    })
    out = shuffle_scorable_umpire_terms(df, seed=1)
    assert list(out["total_runs"]) == [8, 9, 10]
    assert sorted(out["ump_term"]) == sorted([0.01, -0.02, 0.03])


# --------------------------------------------------------------------------- #
# score_corpus verdicts
# --------------------------------------------------------------------------- #
def _synthetic_corpus(n: int, real_effect: bool, seed: int = 0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    baseline_pred = rng.normal(8.5, 1.0, n)
    ump_term = rng.uniform(-0.05, 0.05, n)
    candidate_pred = baseline_pred - ump_term * UMPIRE_TERM_SCALE
    if real_effect:
        total_runs = candidate_pred + rng.normal(0, 0.05, n)  # candidate nearly exact
    else:
        total_runs = baseline_pred + rng.normal(0, 1.0, n)  # ump_term carries no signal
    return pd.DataFrame({
        "total_runs": total_runs, "baseline_pred": baseline_pred, "candidate_pred": candidate_pred,
        "ump_term": ump_term, "completed": True, "pregame_leak_free": True, "scorable": True,
    })


def test_score_corpus_zero_scorable_is_underpowered():
    df = pd.DataFrame({
        "completed": [False], "pregame_leak_free": [False], "scorable": [False],
        "total_runs": [np.nan], "baseline_pred": [8.5], "candidate_pred": [8.5], "ump_term": [0.0],
    })
    res = score_corpus(df)
    assert res["verdict"] == "UNDERPOWERED"
    assert res["n_scorable"] == 0
    assert res["real_rmse_delta"] is None


def test_score_corpus_underpowered_below_threshold_even_with_good_rmse():
    df = _synthetic_corpus(n=13, real_effect=True)
    res = score_corpus(df)
    assert res["n_scorable"] == 13 < MIN_GAMES_THRESHOLD
    assert res["verdict"] == "UNDERPOWERED"
    assert res["real_rmse_delta"] is not None


def test_score_corpus_pure_noise_rejects_above_threshold():
    df = _synthetic_corpus(n=MIN_GAMES_THRESHOLD + 50, real_effect=False, seed=3)
    res = score_corpus(df)
    assert res["verdict"] == "REJECT"


def test_score_corpus_ships_with_strong_planted_effect_above_threshold():
    df = _synthetic_corpus(n=MIN_GAMES_THRESHOLD + 50, real_effect=True, seed=7)
    res = score_corpus(df)
    assert res["verdict"] == "SHIP_REVIEW"
    assert res["real_rmse_delta"] < res["null_rmse_delta"]
