"""Per-file tests for ingame_blend_families.py (LANE 4 step 2-3: candidate
family fitting + cross-corpus selection).

Covers: fit determinism (same input -> same params, every run), checkpoint
math (end_q1/half/end_q3 cumulative-score reconstruction), each family's
predict function shape, and score_family_by_checkpoint's per-checkpoint Brier
shape. See test_ingame_blend_no_leak.py for the no-leak PROPERTY tests (2026
rows/outcomes cannot move a fit restricted to 2024 rows) and the real-corpus
fitted-constants-match guard.

Hermetic (synthetic games/linescores DataFrames); no network.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_blend_families.py -q
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from domains.basketball_wnba.ingame_blend_families import (
    CHECKPOINTS,
    FAMILY_NAMES,
    Row,
    brier,
    build_corpus_with_p0,
    build_rows,
    fit_all_families,
    fit_anchored_params,
    fit_naive_k,
    fit_time_scaled_k,
    fraction_elapsed,
    minutes_remaining,
    predict_anchored,
    predict_family,
    predict_fixed,
    predict_naive,
    predict_time_scaled,
    score_family_by_checkpoint,
)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _synthetic_games(n_per_season: int = 20) -> pd.DataFrame:
    """Chronologically increasing games across 3 seasons, alternating winner so
    walk_forward_elo produces varied (non-degenerate) p0 values."""
    rows = []
    eid = 0
    for season, start in [("2024", "2024-05-03"), ("2025", "2025-05-02"), ("2026", "2026-04-25")]:
        base = pd.Timestamp(start)
        for i in range(n_per_season):
            home_win = 1.0 if i % 2 == 0 else 0.0
            hs, as_ = (85.0, 78.0) if home_win else (78.0, 85.0)
            rows.append({
                "event_id": str(eid), "date": base + pd.Timedelta(days=i),
                "season": season, "home_team": "Aces", "away_team": "Fever",
                "home_score": hs, "away_score": as_, "home_win": home_win,
                "neutral_site": False, "status_name": "STATUS_FINAL",
            })
            eid += 1
    return pd.DataFrame(rows)


def _synthetic_linescores(games_df: pd.DataFrame) -> pd.DataFrame:
    """One deterministic checkpoint row per game, consistent with the game's
    final home_win (leading team also leads at every checkpoint)."""
    rows = []
    for _, g in games_df.iterrows():
        lead = 6.0 if g["home_win"] >= 0.5 else -6.0
        rows.append({
            "event_id": str(g["event_id"]),
            "home_end_q1": 20.0 + lead / 4, "away_end_q1": 20.0 - lead / 4,
            "home_half": 40.0 + lead / 2, "away_half": 40.0 - lead / 2,
            "home_end_q3": 60.0 + lead * 0.75, "away_end_q3": 60.0 - lead * 0.75,
        })
    return pd.DataFrame(rows)


@pytest.fixture()
def games_and_lines():
    games = _synthetic_games()
    lines = _synthetic_linescores(games)
    return games, lines


# ---------------------------------------------------------------------------
# checkpoint math
# ---------------------------------------------------------------------------


def test_checkpoints_are_end_q1_half_end_q3():
    assert CHECKPOINTS == {"end_q1": (1, 0.0), "half": (2, 0.0), "end_q3": (3, 0.0)}


def test_build_rows_expands_one_game_into_three_checkpoint_rows(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    rows = build_rows(wf, lines)
    n_2024_games = int((games["season"] == "2024").sum())
    assert len(rows) == n_2024_games * 3  # 3 checkpoints per game


def test_build_rows_score_diff_matches_checkpoint_cumulative(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    rows = build_rows(wf.head(1), lines)
    ls = lines[lines["event_id"] == str(wf.iloc[0]["event_id"])].iloc[0]
    expected_diffs = {
        1: ls["home_end_q1"] - ls["away_end_q1"],
        2: ls["home_half"] - ls["away_half"],
        3: ls["home_end_q3"] - ls["away_end_q3"],
    }
    for r in rows:
        assert r.score_diff == pytest.approx(expected_diffs[r.period])


def test_build_rows_skips_games_without_linescores_match(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    empty_lines = lines.iloc[0:0]
    rows = build_rows(wf, empty_lines)
    assert rows == []


# ---------------------------------------------------------------------------
# minutes_remaining / fraction_elapsed reuse
# ---------------------------------------------------------------------------


def test_minutes_remaining_matches_seconds_conversion():
    # Q1 with full 10:00 (600s) left -> 2400s total remaining -> 40.0 minutes
    assert minutes_remaining(1, 600) == pytest.approx(40.0)


def test_minutes_remaining_floored_near_buzzer():
    mr = minutes_remaining(4, 0)
    assert mr == pytest.approx(25.0 / 60.0)
    assert mr > 0.0  # never zero -- 1/sqrt would diverge otherwise


def test_fraction_elapsed_reused_matches_ingame_blend():
    from domains.basketball_wnba.ingame_blend import fraction_elapsed as fe_direct
    for period, clock in [(1, 600), (2, 0), (3, 100), (4, 0), (5, 50)]:
        assert fraction_elapsed(period, clock) == fe_direct(period, clock)


# ---------------------------------------------------------------------------
# family predict shapes
# ---------------------------------------------------------------------------


def test_predict_naive_is_pure_sigmoid_of_k_times_diff():
    row = Row(p0=0.7, score_diff=10.0, period=2, clock_s=0.0, outcome=1.0)
    expected = 1.0 / (1.0 + math.exp(-0.2 * 10.0))
    assert predict_naive(row, k=0.2) == pytest.approx(expected)


def test_predict_naive_ignores_p0():
    row_a = Row(p0=0.1, score_diff=5.0, period=2, clock_s=0.0, outcome=1.0)
    row_b = Row(p0=0.9, score_diff=5.0, period=2, clock_s=0.0, outcome=1.0)
    assert predict_naive(row_a, k=0.3) == predict_naive(row_b, k=0.3)


def test_predict_time_scaled_zero_diff_is_half():
    row = Row(p0=0.5, score_diff=0.0, period=2, clock_s=0.0, outcome=1.0)
    assert predict_time_scaled(row, k=0.5) == pytest.approx(0.5)


def test_predict_anchored_w0_zero_collapses_to_time_scaled():
    row = Row(p0=0.9, score_diff=8.0, period=3, clock_s=100.0, outcome=1.0)
    a = predict_anchored(row, k=0.4, w0=0.0)
    ts = predict_time_scaled(row, k=0.4)
    assert a == pytest.approx(ts)


def test_predict_anchored_at_tipoff_zero_diff_recovers_p0_when_w0_one():
    row = Row(p0=0.63, score_diff=0.0, period=1, clock_s=600.0, outcome=1.0)
    p = predict_anchored(row, k=0.6, w0=1.0)
    assert p == pytest.approx(0.63, abs=1e-6)


def test_predict_family_dispatch_matches_direct_calls():
    from domains.basketball_wnba.ingame_blend_families import fit_all_families
    row = Row(p0=0.6, score_diff=4.0, period=2, clock_s=0.0, outcome=1.0)
    fitted = fit_all_families([row])
    assert predict_family("naive", row, fitted) == pytest.approx(predict_naive(row, fitted.naive_k))
    assert predict_family("time_scaled", row, fitted) == pytest.approx(
        predict_time_scaled(row, fitted.time_scaled_k))
    assert predict_family("anchored", row, fitted) == pytest.approx(
        predict_anchored(row, fitted.anchored_k, fitted.anchored_w0))
    assert predict_family("fixed", row, fitted) == pytest.approx(predict_fixed(row))


def test_predict_family_unknown_name_raises():
    from domains.basketball_wnba.ingame_blend_families import fit_all_families
    row = Row(p0=0.5, score_diff=0.0, period=1, clock_s=600.0, outcome=1.0)
    fitted = fit_all_families([row])
    with pytest.raises(ValueError):
        predict_family("nonexistent", row, fitted)


# ---------------------------------------------------------------------------
# fit determinism
# ---------------------------------------------------------------------------


def test_fit_naive_k_is_deterministic(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    rows = build_rows(wf, lines)
    k1 = fit_naive_k(rows)
    k2 = fit_naive_k(rows)
    assert k1 == k2


def test_fit_all_families_is_deterministic(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    rows = build_rows(wf, lines)
    f1 = fit_all_families(rows)
    f2 = fit_all_families(rows)
    assert f1 == f2


def test_fit_anchored_params_deterministic_grid_scan(games_and_lines):
    games, lines = games_and_lines
    wf = build_corpus_with_p0(games, "2024")
    rows = build_rows(wf, lines)
    k1, w1 = fit_anchored_params(rows)
    k2, w2 = fit_anchored_params(rows)
    assert (k1, w1) == (k2, w2)


# NOTE: the no-leak property tests (2026 rows/outcomes cannot move a fit
# restricted to 2024 rows) + the real-corpus fitted-constants match live in
# test_ingame_blend_no_leak.py (split out to keep both files under the LOC cap).


# ---------------------------------------------------------------------------
# brier() sanity + score_family_by_checkpoint shape
# ---------------------------------------------------------------------------


def test_brier_perfect_predictions_is_zero():
    assert brier([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_brier_empty_is_none():
    assert brier([], []) is None


def test_score_family_by_checkpoint_reports_n_and_brier_per_checkpoint(games_and_lines):
    games, lines = games_and_lines
    wf_2024 = build_corpus_with_p0(games, "2024")
    rows_2024 = build_rows(wf_2024, lines)
    fitted = fit_all_families(rows_2024)

    wf_2025 = build_corpus_with_p0(games, "2025")
    result = score_family_by_checkpoint("naive", wf_2025, lines, fitted)
    assert set(result.keys()) == set(CHECKPOINTS.keys())
    n_2025 = int((games["season"] == "2025").sum())
    for cp in CHECKPOINTS:
        assert result[cp]["n"] == n_2025
        assert result[cp]["brier"] is not None
        assert 0.0 <= result[cp]["brier"] <= 1.0


def test_all_family_names_are_scoreable(games_and_lines):
    games, lines = games_and_lines
    wf_2024 = build_corpus_with_p0(games, "2024")
    rows_2024 = build_rows(wf_2024, lines)
    fitted = fit_all_families(rows_2024)
    wf_2025 = build_corpus_with_p0(games, "2025")
    for fam in FAMILY_NAMES:
        result = score_family_by_checkpoint(fam, wf_2025, lines, fitted)
        for cp in CHECKPOINTS:
            assert result[cp]["brier"] is not None
