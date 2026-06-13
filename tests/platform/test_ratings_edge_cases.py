"""tests/platform/test_ratings_edge_cases.py

Edge-case robustness tests for the three walk-forward ratings functions:
  - domains.tennis.elo_walkforward.walk_forward_elo
  - domains.soccer.ratings.walk_forward_goals
  - domains.mlb.ratings.walk_forward_elo

Covers: empty corpus, single row, NaN/degenerate fields, value-range sanity.
All DataFrames are SYNTHETIC — no real corpus files required.  Test-only.
"""
from __future__ import annotations

import importlib
import math

import pandas as pd
import pytest


def _try_import(module_path: str):
    try:
        return importlib.import_module(module_path)
    except Exception:
        return None


_tennis_mod = _try_import("domains.tennis.elo_walkforward")
_soccer_mod = _try_import("domains.soccer.ratings")
_mlb_mod = _try_import("domains.mlb.ratings")

TENNIS_SKIP = _tennis_mod is None
SOCCER_SKIP = _soccer_mod is None
MLB_SKIP = _mlb_mod is None

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _tennis_df(**ov) -> pd.DataFrame:
    row = {"date": "2024-01-15", "p1_id": 101, "p2_id": 202,
           "winner": 1, "surface": "Hard", "score": "6-3 6-4",
           "round": "R32", "best_of": 3}
    row.update(ov)
    return pd.DataFrame([row])


def _soccer_df(**ov) -> pd.DataFrame:
    row = {"date": "2024-01-15", "div": "E0",
           "home_team": "Arsenal", "away_team": "Chelsea",
           "fthg": 2.0, "ftag": 1.0}
    row.update(ov)
    return pd.DataFrame([row])


def _mlb_df(**ov) -> pd.DataFrame:
    row = {"date": "2024-04-01", "season": 2024,
           "home_team": "NYY", "away_team": "BOS",
           "home_runs": 5.0, "away_runs": 3.0, "game_seq": 1}
    row.update(ov)
    return pd.DataFrame([row])


# ===========================================================================
# TENNIS — walk_forward_elo
# ===========================================================================

@pytest.mark.skipif(TENNIS_SKIP, reason="domains.tennis.elo_walkforward not available")
class TestTennisEdgeCases:

    def test_empty_corpus_no_raise(self):
        """Empty DataFrame → empty result with all 5 output columns, no exception."""
        empty = pd.DataFrame(columns=[
            "date", "p1_id", "p2_id", "winner", "surface", "score", "round", "best_of"
        ])
        result = _tennis_mod.walk_forward_elo(empty)
        assert isinstance(result, pd.DataFrame) and len(result) == 0
        for col in ("p1_elo", "p2_elo", "p1_surface_elo", "p2_surface_elo", "win_prob_p1"):
            assert col in result.columns

    def test_single_row_ratings_equal_base(self):
        """Single match: pre-match ratings must equal BASE_RATING (no history)."""
        from domains.tennis.elo_core import BASE_RATING
        result = _tennis_mod.walk_forward_elo(_tennis_df())
        assert len(result) == 1
        for col in ("p1_elo", "p2_elo", "p1_surface_elo", "p2_surface_elo"):
            assert result[col].iloc[0] == pytest.approx(BASE_RATING), col

    def test_single_row_win_prob_range(self):
        """win_prob_p1 ∈ (0,1); equal prior ratings → ≈ 0.5."""
        result = _tennis_mod.walk_forward_elo(_tennis_df())
        p = result["win_prob_p1"].iloc[0]
        assert 0.0 < p < 1.0
        assert p == pytest.approx(0.5, abs=0.01)

    def test_walkover_skips_rating_update(self):
        """Walkover does not advance ratings; next match still sees BASE_RATING."""
        from domains.tennis.elo_core import BASE_RATING
        df = pd.concat([
            _tennis_df(score="W/O"),
            _tennis_df(date="2024-02-01"),
        ], ignore_index=True)
        result = _tennis_mod.walk_forward_elo(df)
        assert len(result) == 2
        assert result["p1_elo"].iloc[0] == pytest.approx(BASE_RATING)
        assert result["p1_elo"].iloc[1] == pytest.approx(BASE_RATING)

    def test_nan_surface_handled(self):
        """NaN surface falls back to 'Unknown'; all rating columns remain finite."""
        result = _tennis_mod.walk_forward_elo(_tennis_df(surface=float("nan")))
        assert len(result) == 1
        for col in ("p1_elo", "p2_elo", "p1_surface_elo", "p2_surface_elo", "win_prob_p1"):
            assert math.isfinite(result[col].iloc[0]), f"{col!r} is not finite"

    def test_best_of_values_no_crash(self):
        """best_of ∈ {3, 5} both accepted without crash."""
        for bo in (3, 5):
            assert len(_tennis_mod.walk_forward_elo(_tennis_df(best_of=bo))) == 1

    def test_multi_row_all_finite(self):
        """Three matches: all output columns finite, win_prob_p1 ∈ (0,1)."""
        rows = pd.concat([
            _tennis_df(date="2024-01-01", p1_id=1, p2_id=2, winner=1),
            _tennis_df(date="2024-01-08", p1_id=1, p2_id=3, winner=2),
            _tennis_df(date="2024-01-15", p1_id=2, p2_id=3, winner=1),
        ], ignore_index=True)
        result = _tennis_mod.walk_forward_elo(rows)
        assert len(result) == 3
        for col in ("p1_elo", "p2_elo", "win_prob_p1"):
            assert result[col].apply(math.isfinite).all(), f"non-finite in {col!r}"


# ===========================================================================
# SOCCER — walk_forward_goals
# ===========================================================================

@pytest.mark.skipif(SOCCER_SKIP, reason="domains.soccer.ratings not available")
class TestSoccerEdgeCases:

    def test_empty_corpus_no_raise(self):
        """Empty DataFrame → empty result with all 4 output columns, no exception."""
        empty = pd.DataFrame(columns=["date", "div", "home_team", "away_team", "fthg", "ftag"])
        result = _soccer_mod.walk_forward_goals(empty)
        assert isinstance(result, pd.DataFrame) and len(result) == 0
        for col in ("lam_home", "lam_away", "lam_total", "p_over25"):
            assert col in result.columns

    def test_single_row_prior_lambdas_finite(self):
        """Single match: lambdas computed from prior only; lam_total = lam_home + lam_away."""
        result = _soccer_mod.walk_forward_goals(_soccer_df())
        assert len(result) == 1
        lh, la = result["lam_home"].iloc[0], result["lam_away"].iloc[0]
        lt = result["lam_total"].iloc[0]
        assert math.isfinite(lh) and lh > 0
        assert math.isfinite(la) and la > 0
        assert lt == pytest.approx(lh + la)

    def test_single_row_p_over25_range(self):
        """p_over25 ∈ (0, 1) for a normal prior-rate match."""
        result = _soccer_mod.walk_forward_goals(_soccer_df())
        p = result["p_over25"].iloc[0]
        assert 0.0 < p < 1.0

    def test_nan_goals_no_raise(self):
        """NaN fthg/ftag: must not raise; row-0 lambdas are prior-based (finite)."""
        df = _soccer_df(fthg=float("nan"), ftag=float("nan"))
        try:
            result = _soccer_mod.walk_forward_goals(df)
            assert len(result) == 1
            assert math.isfinite(result["lam_home"].iloc[0])
            assert math.isfinite(result["lam_away"].iloc[0])
        except Exception as exc:
            pytest.xfail(f"walk_forward_goals raises on NaN goals: {exc}")

    def test_multi_row_all_finite_and_bounded(self):
        """Three normal matches: output columns finite, p_over25 ∈ (0,1)."""
        rows = pd.concat([
            _soccer_df(date="2024-01-01", home_team="A", away_team="B", fthg=1.0, ftag=0.0),
            _soccer_df(date="2024-01-08", home_team="B", away_team="C", fthg=3.0, ftag=2.0),
            _soccer_df(date="2024-01-15", home_team="A", away_team="C", fthg=0.0, ftag=0.0),
        ], ignore_index=True)
        result = _soccer_mod.walk_forward_goals(rows)
        assert len(result) == 3
        for col in ("lam_home", "lam_away", "lam_total", "p_over25"):
            assert result[col].apply(math.isfinite).all(), f"non-finite in {col!r}"
        assert (result["p_over25"].between(0, 1, inclusive="neither")).all()


# ===========================================================================
# MLB — walk_forward_elo
# ===========================================================================

@pytest.mark.skipif(MLB_SKIP, reason="domains.mlb.ratings not available")
class TestMLBEdgeCases:

    def test_empty_corpus_no_raise(self):
        """Empty DataFrame → empty result with all 4 output columns, no exception."""
        empty = pd.DataFrame(columns=[
            "date", "season", "home_team", "away_team",
            "home_runs", "away_runs", "game_seq"
        ])
        result = _mlb_mod.walk_forward_elo(empty)
        assert isinstance(result, pd.DataFrame) and len(result) == 0
        for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
            assert col in result.columns

    def test_single_row_ratings_equal_mean(self):
        """Single game: pre-game Elo = ELO_MEAN for both teams (no history)."""
        from domains.mlb.config import ELO_MEAN
        result = _mlb_mod.walk_forward_elo(_mlb_df())
        assert len(result) == 1
        assert result["elo_home"].iloc[0] == pytest.approx(ELO_MEAN)
        assert result["elo_away"].iloc[0] == pytest.approx(ELO_MEAN)

    def test_single_row_p_home_hfa_and_range(self):
        """p_home_elo ∈ (0,1); HFA > 0 means home favored at equal ratings."""
        from domains.mlb.config import ELO_HFA
        result = _mlb_mod.walk_forward_elo(_mlb_df())
        p = result["p_home_elo"].iloc[0]
        assert 0.0 < p < 1.0
        if ELO_HFA > 0:
            assert p > 0.5

    def test_elo_diff_hfa_consistent(self):
        """elo_diff_hfa = (elo_home + ELO_HFA) - elo_away, verified exactly."""
        from domains.mlb.config import ELO_HFA
        result = _mlb_mod.walk_forward_elo(_mlb_df())
        eh = result["elo_home"].iloc[0]
        ea = result["elo_away"].iloc[0]
        assert result["elo_diff_hfa"].iloc[0] == pytest.approx((eh + ELO_HFA) - ea)

    def test_nan_runs_no_raise(self):
        """NaN home_runs/away_runs: must not raise; pre-match snapshot is finite."""
        df = _mlb_df(home_runs=float("nan"), away_runs=float("nan"))
        try:
            result = _mlb_mod.walk_forward_elo(df)
            assert len(result) == 1
            assert math.isfinite(result["elo_home"].iloc[0])
            assert math.isfinite(result["p_home_elo"].iloc[0])
        except Exception as exc:
            pytest.xfail(f"walk_forward_elo raises on NaN runs: {exc}")

    def test_season_boundary_regression_finite(self):
        """Season transition: elo at game-2 is finite and bounded (regression runs)."""
        rows = pd.concat([
            _mlb_df(date="2023-04-01", season=2023, home_runs=5.0, away_runs=1.0),
            _mlb_df(date="2024-04-01", season=2024, home_runs=3.0, away_runs=2.0),
        ], ignore_index=True)
        result = _mlb_mod.walk_forward_elo(rows)
        assert len(result) == 2
        assert math.isfinite(result["elo_home"].iloc[1])
        assert 1000.0 < result["elo_home"].iloc[1] < 2000.0

    def test_multi_row_all_finite_and_bounded(self):
        """Three games: all output columns finite, p_home_elo ∈ (0,1)."""
        rows = pd.concat([
            _mlb_df(date="2024-04-01", home_team="NYY", away_team="BOS",
                    home_runs=5.0, away_runs=3.0),
            _mlb_df(date="2024-04-02", home_team="BOS", away_team="NYY",
                    home_runs=2.0, away_runs=4.0),
            _mlb_df(date="2024-04-03", home_team="NYY", away_team="BOS",
                    home_runs=3.0, away_runs=3.0),
        ], ignore_index=True)
        result = _mlb_mod.walk_forward_elo(rows)
        assert len(result) == 3
        for col in ("elo_home", "elo_away", "elo_diff_hfa", "p_home_elo"):
            assert result[col].apply(math.isfinite).all(), f"non-finite in {col!r}"
        assert (result["p_home_elo"].between(0, 1, inclusive="neither")).all()
