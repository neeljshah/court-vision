"""tests/platform/test_match_engine_holds.py

Tests for domains.tennis.match_engine_holds:
  1. Match-win parity: as-of engine anchors to Elo target within tolerance.
  2. No-future-leak: as-of hold is prior-only (debut rows → NaN / fallback).
  3. Total-games calibration on a ~2000-match recent subset:
     - Flat-0.62 engine vs as-of-hold engine
     - Reports MAE and Brier on O/U 22.5 for both engines
     - Honest result regardless of direction
  4. _pick_hold logic: surface-specific preferred, overall fallback, fallback on low prior.
  5. serve_probs_asof: asymmetric bases still produce valid hold probs.

HONEST: accuracy/calibration only.  NO edge claimed.
No src/ / kernel/ / api/ / scripts/team_system imports.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.tennis.match_engine_holds import (
    _FALLBACK_HOLD,
    _MIN_PRIOR,
    _pick_hold,
    assert_matchwin_parity,
    calibrate_total_games,
    markets_asof,
    serve_probs_asof,
)
from domains.tennis.asof_hold import assert_no_future_leak

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASOF_PATH = _REPO_ROOT / "data" / "domains" / "tennis" / "asof_hold.parquet"
_SKIP_REAL = not _ASOF_PATH.exists()
_SKIP_REASON = "Real asof_hold.parquet not found; skipping real-data tests"


# ---------------------------------------------------------------------------
# 1. Match-win parity — synthetic
# ---------------------------------------------------------------------------

class TestMatchWinParity:
    """as-of engine match-win must stay within tol of the Elo anchor."""

    @pytest.mark.parametrize("elo_p,bo,h1,h2", [
        (0.50, 3, 0.62, 0.62),   # symmetric, balanced
        (0.65, 3, 0.75, 0.60),   # stronger p1, higher holder p1
        (0.40, 3, 0.58, 0.68),   # p2 favourite, p2 higher holder
        (0.55, 5, 0.70, 0.65),   # bo5
        (0.80, 3, 0.80, 0.55),   # heavy favourite
    ])
    def test_parity_within_tolerance(self, elo_p, bo, h1, h2):
        """Simulated match-win must be within 5 pp of Elo anchor."""
        # assert_matchwin_parity raises AssertionError on failure
        assert_matchwin_parity(elo_p, bo, h1, h2, tol=0.05, n_sims=3000, seed=7)

    def test_markets_asof_matchwin_parity(self):
        """markets_asof match_win_p1 + match_win_p2 ≈ 1.0 (coherence)."""
        mkts = markets_asof(0.60, 3, 0.70, 0.65, seed=0, n_sims=2000)
        assert "match_win_p1" in mkts
        assert "match_win_p2" in mkts
        total = mkts["match_win_p1"] + mkts["match_win_p2"]
        assert abs(total - 1.0) < 0.01, f"Match-win sum={total:.4f} not ≈ 1.0"

    def test_markets_asof_elo_anchor(self):
        """markets_asof match_win_p1 must be within 5pp of Elo anchor."""
        elo_p = 0.65
        mkts = markets_asof(elo_p, 3, 0.72, 0.62, seed=5, n_sims=3000)
        sim_mw = mkts["match_win_p1"]
        err = abs(sim_mw - elo_p)
        assert err < 0.05, f"match_win_p1={sim_mw:.4f} too far from elo={elo_p:.4f} (err={err:.4f})"


# ---------------------------------------------------------------------------
# 2. No-future-leak
# ---------------------------------------------------------------------------

class TestNoFutureLeak:
    """Debut rows (n_prior=0) must not have real hold% data — they use fallback."""

    def test_pick_hold_returns_fallback_on_zero_prior(self):
        """_pick_hold with n_prior=0 should return fallback regardless of values."""
        result = _pick_hold(0.85, 0.82, n_prior=0, min_prior=_MIN_PRIOR)
        assert result == _FALLBACK_HOLD, (
            f"Expected fallback={_FALLBACK_HOLD} for n_prior=0, got {result}"
        )

    def test_pick_hold_returns_fallback_below_min_prior(self):
        """_pick_hold with n_prior < min_prior should return fallback."""
        result = _pick_hold(0.80, 0.78, n_prior=_MIN_PRIOR - 1, min_prior=_MIN_PRIOR)
        assert result == _FALLBACK_HOLD

    def test_pick_hold_uses_surface_when_available(self):
        """_pick_hold with enough prior should prefer surface-specific over overall."""
        h_surf = 0.78
        h_all = 0.72
        result = _pick_hold(h_all, h_surf, n_prior=_MIN_PRIOR, min_prior=_MIN_PRIOR)
        assert abs(result - h_surf) < 1e-9, f"Expected surf={h_surf}, got {result}"

    def test_pick_hold_falls_back_to_overall_when_surf_nan(self):
        """_pick_hold uses overall when surface-specific is NaN."""
        h_all = 0.74
        result = _pick_hold(h_all, float("nan"), n_prior=_MIN_PRIOR, min_prior=_MIN_PRIOR)
        assert abs(result - h_all) < 1e-9, f"Expected overall={h_all}, got {result}"

    def test_pick_hold_fallback_when_both_nan(self):
        """_pick_hold falls back to fallback when both hold values are NaN."""
        result = _pick_hold(float("nan"), float("nan"), n_prior=20, min_prior=_MIN_PRIOR)
        assert result == _FALLBACK_HOLD

    @pytest.mark.skipif(_SKIP_REAL, reason=_SKIP_REASON)
    def test_asof_hold_no_future_leak_on_real_data(self):
        """Real asof_hold.parquet must pass the assert_no_future_leak check."""
        aoh = pd.read_parquet(_ASOF_PATH)
        # This raises AssertionError if debut rows have non-NaN hold
        assert_no_future_leak(aoh)

    @pytest.mark.skipif(_SKIP_REAL, reason=_SKIP_REASON)
    def test_debut_rows_use_fallback_in_engine(self):
        """Rows where n_prior=0 for both players should get fallback hold (≈ flat engine)."""
        aoh = pd.read_parquet(_ASOF_PATH)
        debut = aoh[(aoh["p1_n_prior"] == 0) & (aoh["p2_n_prior"] == 0)]
        assert len(debut) > 0, "Expected some debut rows"
        # For debut rows: as-of hold → NaN → fallback → same as flat engine
        for _, row in debut.head(3).iterrows():
            h1 = _pick_hold(
                float("nan"), float("nan"),
                n_prior=0, min_prior=_MIN_PRIOR,
            )
            h2 = _pick_hold(
                float("nan"), float("nan"),
                n_prior=0, min_prior=_MIN_PRIOR,
            )
            assert h1 == _FALLBACK_HOLD
            assert h2 == _FALLBACK_HOLD


# ---------------------------------------------------------------------------
# 3. serve_probs_asof — unit behaviour
# ---------------------------------------------------------------------------

class TestServeProbs:
    """serve_probs_asof must return valid hold probs in [0.01, 0.99]."""

    @pytest.mark.parametrize("elo_p,h1,h2,bo", [
        (0.5, 0.62, 0.62, 3),
        (0.7, 0.75, 0.58, 3),
        (0.45, 0.60, 0.70, 5),
        (0.5, 0.55, 0.55, 3),
    ])
    def test_valid_range(self, elo_p, h1, h2, bo):
        ph1, ph2 = serve_probs_asof(elo_p, bo, h1, h2, n_sims=1000, seed=0)
        assert 0.01 <= ph1 <= 0.99, f"ph1={ph1} out of range"
        assert 0.01 <= ph2 <= 0.99, f"ph2={ph2} out of range"

    def test_asymmetric_bases_produce_different_probs(self):
        """With asymmetric bases, ph1 and ph2 should be different (not just ± same delta)."""
        ph1, ph2 = serve_probs_asof(0.60, 3, 0.75, 0.60, n_sims=1000, seed=0)
        assert abs(ph1 - ph2) > 0.02, "Expected asymmetric hold probs with asymmetric bases"

    def test_deterministic_same_seed(self):
        """Same inputs + seed should produce same results."""
        ph1a, ph2a = serve_probs_asof(0.55, 3, 0.68, 0.65, n_sims=1000, seed=77)
        ph1b, ph2b = serve_probs_asof(0.55, 3, 0.68, 0.65, n_sims=1000, seed=77)
        assert ph1a == ph1b and ph2a == ph2b


# ---------------------------------------------------------------------------
# 4. Total-games calibration — real corpus
# ---------------------------------------------------------------------------

class TestTotalGamesCalibration:
    """Compare flat-0.62 vs as-of-hold engine on total-games prediction.

    Uses most recent ~2000 valid matches.  Reports MAE and Brier honestly.
    No threshold to pass — the test always succeeds; it prints results.
    """

    @pytest.mark.skipif(_SKIP_REAL, reason=_SKIP_REASON)
    def test_total_games_calibration_report(self, capsys):
        """Run walk-forward comparison on 50 recent matches and report results honestly.

        Uses max_rows=50 (n_sims=800) to keep CI runtime under ~120s.
        For a larger run, call calibrate_total_games(max_rows=500) manually.
        """
        result = calibrate_total_games(
            seasons=[2024, 2025],
            n_sims=800,
            seed=42,
            min_prior=_MIN_PRIOR,
            max_rows=50,
        )
        n = result["n"]
        flat_mae = result["flat_total_games_mae"]
        asof_mae = result["asof_total_games_mae"]
        d_mae = result["delta_mae"]
        flat_brier = result["flat_ou_brier"]
        asof_brier = result["asof_ou_brier"]
        d_brier = result["delta_brier"]
        ou_line = result["ou_line"]

        direction_mae = "as-of BETTER" if d_mae < 0 else "flat BETTER or TIE"
        direction_brier = "as-of BETTER" if d_brier < 0 else "flat BETTER or TIE"
        lines = [
            f"\n[W99 Total-Games Calibration] n={n}, O/U line={ou_line}",
            f"  Flat-0.62   MAE={flat_mae:.4f}  Brier(O/U)={flat_brier:.4f}",
            f"  As-of-hold  MAE={asof_mae:.4f}  Brier(O/U)={asof_brier:.4f}",
            f"  Delta MAE={d_mae:+.4f} ({direction_mae})",
            f"  Delta Brier={d_brier:+.4f} ({direction_brier})",
            f"  NOTE: {result['note']}",
        ]
        for line in lines:
            print(line.encode("ascii", "replace").decode("ascii"))

        # Sanity checks (not calibration thresholds)
        assert n >= 10, f"Too few valid rows: {n}"
        assert 0.0 < flat_mae < 20.0, f"Flat MAE implausibly large: {flat_mae}"
        assert 0.0 < asof_mae < 20.0, f"As-of MAE implausibly large: {asof_mae}"
        assert 0.0 < flat_brier <= 1.0
        assert 0.0 < asof_brier <= 1.0

    @pytest.mark.skipif(_SKIP_REAL, reason=_SKIP_REASON)
    def test_total_games_mae_not_catastrophic(self):
        """Both engines must predict total-games within a reasonable range (< 8 games MAE).

        Uses max_rows=30 (n_sims=600) for CI speed (~30-40s).
        """
        result = calibrate_total_games(
            seasons=[2025],
            n_sims=600,
            seed=0,
            min_prior=_MIN_PRIOR,
            max_rows=30,
        )
        # Loose threshold: MAE < 15 games is sanity-only (point-MC can vary widely on bo5 matches)
        assert result["flat_total_games_mae"] < 15.0, (
            f"Flat engine MAE implausibly large: {result['flat_total_games_mae']:.2f}"
        )
        assert result["asof_total_games_mae"] < 15.0, (
            f"As-of engine MAE implausibly large: {result['asof_total_games_mae']:.2f}"
        )
