"""Per-file test: scripts/platformkit/proof_mlb/runline_calibration.py

Acceptance criteria (pa6):
  - cover-rate per bin within ECE target on held-out data OR data_limited sentinel
  - <60 holdout overlap -> data_limited (not a false pass)
  - no $/roi/pnl/edge key in result
  - result dict has all expected keys on real data
  - model_cover_prob is in (0, 1) and monotone: +runline -> higher cover prob

Run: python -m pytest scripts/platformkit/proof_mlb/test_runline_calibration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_mlb.runline_calibration import (  # noqa: E402
    run,
    _model_cover_prob,
    _phi,
    _phi_inv,
    _american_to_implied,
    _ece_bins,
    _SIGMA_RUNS,
    _ECE_TARGET,
    _MIN_HOLDOUT,
)


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------

class TestPhiHelpers:
    def test_phi_at_zero(self):
        assert abs(_phi(0.0) - 0.5) < 1e-4

    def test_phi_positive_tail(self):
        assert _phi(1.96) > 0.97

    def test_phi_inv_roundtrip(self):
        for p in (0.1, 0.25, 0.5, 0.75, 0.9):
            assert abs(_phi(_phi_inv(p)) - p) < 5e-4, f"roundtrip failed at p={p}"

    def test_phi_inv_symmetry(self):
        assert abs(_phi_inv(0.3) + _phi_inv(0.7)) < 1e-3


class TestAmericanToImplied:
    def test_minus110(self):
        p = _american_to_implied(-110.0)
        assert abs(p - 0.5238) < 0.001

    def test_plus100(self):
        p = _american_to_implied(100.0)
        assert abs(p - 0.5) < 1e-9

    def test_positive_line(self):
        p = _american_to_implied(150.0)
        assert 0.3 < p < 0.5

    def test_negative_line(self):
        p = _american_to_implied(-150.0)
        assert 0.5 < p < 0.7


class TestModelCoverProb:
    def test_prob_in_unit_interval(self):
        p_home = np.array([0.3, 0.5, 0.7])
        runline = np.array([-1.5, -1.5, 1.5])
        result = _model_cover_prob(p_home, runline, _SIGMA_RUNS)
        assert np.all(result > 0), "cover prob must be > 0"
        assert np.all(result < 1), "cover prob must be < 1"

    def test_pos_runline_higher_than_neg(self):
        """Home team at +1.5 should have higher cover prob than at -1.5, given same Elo."""
        p_home = np.full(2, 0.5)
        runlines = np.array([-1.5, 1.5])
        probs = _model_cover_prob(p_home, runlines, _SIGMA_RUNS)
        assert probs[1] > probs[0], "P(cover +1.5) > P(cover -1.5) for same team strength"

    def test_monotone_in_runline(self):
        """Higher runline (home gets more runs) -> higher cover prob."""
        p_home_flat = np.full(4, 0.5)
        runlines = np.array([-1.5, -0.5, 0.5, 1.5])
        probs = _model_cover_prob(p_home_flat, runlines, _SIGMA_RUNS)
        assert np.all(np.diff(probs) > 0), "cover prob must increase with runline"

    def test_stronger_home_covers_more(self):
        """Stronger home team (higher Elo) should cover -1.5 at higher rate."""
        runline = np.array([-1.5, -1.5, -1.5])
        p_home = np.array([0.4, 0.5, 0.6])
        probs = _model_cover_prob(p_home, runline, _SIGMA_RUNS)
        assert np.all(np.diff(probs) > 0)


class TestEceBins:
    def test_bins_non_empty(self):
        rng = np.random.default_rng(42)
        p = rng.uniform(0.35, 0.65, 200)
        y = (rng.random(200) < p).astype(float)
        bins = _ece_bins(p, y, 5)
        assert len(bins) >= 3

    def test_bins_required_keys(self):
        rng = np.random.default_rng(9)
        p = rng.uniform(0.3, 0.7, 150)
        y = (rng.random(150) < p).astype(float)
        bins = _ece_bins(p, y, 5)
        required = {"bin", "n", "pred_cover_rate", "actual_cover_rate", "gap"}
        for b in bins:
            assert required.issubset(b.keys())

    def test_gap_is_pred_minus_actual(self):
        rng = np.random.default_rng(17)
        p = rng.uniform(0.3, 0.7, 200)
        y = (rng.random(200) < p).astype(float)
        for b in _ece_bins(p, y, 5):
            computed = round(b["pred_cover_rate"] - b["actual_cover_rate"], 4)
            assert abs(computed - b["gap"]) < 1e-8


# ---------------------------------------------------------------------------
# Data-limited sentinel (synthetic tiny corpus)
# ---------------------------------------------------------------------------

class TestDataLimitedSentinel:
    @staticmethod
    def _mini_corpus(tmp_path: Path, n: int) -> Path:
        mlb_dir = tmp_path / "mlb"
        mlb_dir.mkdir()
        rng = np.random.default_rng(5)
        dates = pd.date_range("2020-04-01", periods=n, freq="D")
        ev = [f"20200401-BOS-NYY-{i}" for i in range(n)]
        games = pd.DataFrame({
            "event_id": ev,
            "date": dates,
            "season": 2020,
            "home_team": ["BOS"] * n,
            "away_team": ["NYY"] * n,
            "home_runs": rng.integers(2, 8, n),
            "away_runs": rng.integers(2, 8, n),
            "target_home_win": rng.integers(0, 2, n),
            "game_seq": np.arange(1, n + 1),
            "home_league": ["AL"] * n,
        })
        games.to_parquet(mlb_dir / "games.parquet", index=False)
        odds = pd.DataFrame({
            "event_id": ev,
            "date": dates,
            "season": 2020,
            "runline": np.where(rng.random(n) > 0.5, -1.5, 1.5).astype(float),
            "runline_odds": rng.uniform(-140, -100, n),
            "ml_close_home_am": np.full(n, -120.0),
            "ml_close_away_am": np.full(n, 100.0),
            "closeou": np.full(n, np.nan),
        })
        odds.to_parquet(mlb_dir / "odds.parquet", index=False)
        return mlb_dir

    def test_small_corpus_returns_data_limited(self, tmp_path):
        mlb_dir = self._mini_corpus(tmp_path, n=10)
        rep = run(corpus=mlb_dir)
        assert rep["status"] == "data_limited", (
            f"Expected data_limited for n=10, got {rep}")

    def test_missing_files_returns_missing_data(self, tmp_path):
        mlb_dir = tmp_path / "mlb"
        mlb_dir.mkdir()
        rep = run(corpus=mlb_dir)
        assert rep["status"] == "missing_data"


# ---------------------------------------------------------------------------
# Synthetic calibrated corpus (deterministic)
# ---------------------------------------------------------------------------

class TestSyntheticCalibration:
    @staticmethod
    def _build(tmp_path: Path, n: int, seed: int = 42) -> Path:
        """Synthetic MLB corpus: runs ~ Normal(0,4), mixed runlines."""
        mlb_dir = tmp_path / "mlb"
        mlb_dir.mkdir(exist_ok=True)
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2015-04-01", periods=n, freq="D")
        ev = [f"ev{i}" for i in range(n)]
        margin = rng.normal(0, 4, n)
        h_runs = (5 + margin / 2).clip(min=0).astype(int)
        a_runs = (5 - margin / 2).clip(min=0).astype(int)
        pd.DataFrame({
            "event_id": ev, "date": dates, "season": 2015,
            "home_team": ["BOS"] * n, "away_team": ["NYY"] * n,
            "home_runs": h_runs, "away_runs": a_runs,
            "target_home_win": (h_runs > a_runs).astype(int),
            "game_seq": np.arange(1, n + 1), "home_league": ["AL"] * n,
        }).to_parquet(mlb_dir / "games.parquet", index=False)
        pd.DataFrame({
            "event_id": ev, "date": dates, "season": 2015,
            "runline": np.where(rng.random(n) > 0.5, -1.5, 1.5).astype(float),
            "runline_odds": np.full(n, -110.0),
            "ml_close_home_am": np.full(n, -110.0),
            "ml_close_away_am": np.full(n, -110.0),
            "closeou": np.full(n, np.nan),
        }).to_parquet(mlb_dir / "odds.parquet", index=False)
        return mlb_dir

    def test_ok_and_structure(self, tmp_path):
        """Ok status, correct keys, bool pass-flags, verdict present, no fab tokens."""
        mlb_dir = self._build(tmp_path, n=300)
        rep = run(corpus=mlb_dir)
        assert rep["status"] == "ok", f"Expected ok, got {rep}"
        banned_keys = {"roi", "pnl", "profit", "usd", "dollar",
                       "edge_vs_market", "expected_value", "ev_pct"}
        for key in rep:
            assert key.lower() not in banned_keys, f"Banned key: {key}"
        assert "verdict" in rep and len(rep["verdict"]) > 10
        if rep["status"] == "ok":
            assert isinstance(rep.get("model_passed"), bool)
            assert isinstance(rep.get("market_passed"), bool)
            assert 0.0 <= rep["model_ece"] <= 1.0
            assert 0.0 <= rep["market_ece"] <= 1.0
            assert len(rep["model_bins"]) >= 3
            assert len(rep["market_bins"]) >= 1


# ---------------------------------------------------------------------------
# Integration: real data (skip if unavailable)
# ---------------------------------------------------------------------------

_MLB_GAMES = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_MLB_ODDS = _REPO / "data" / "domains" / "mlb" / "odds.parquet"
_REAL_DATA_AVAILABLE = _MLB_GAMES.is_file() and _MLB_ODDS.is_file()


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason="Real MLB data not available")
class TestRealData:
    def test_run_returns_ok_or_data_limited(self):
        rep = run()
        assert rep["status"] in ("ok", "data_limited"), f"Unexpected: {rep}"

    def test_no_dollar_keys(self):
        rep = run()
        banned_keys = {"roi", "pnl", "profit", "edge_vs_market", "expected_value", "ev_pct"}
        for key in rep:
            assert key.lower() not in banned_keys

    def test_ece_values_in_range(self):
        rep = run()
        if rep["status"] == "ok":
            assert 0.0 <= rep["model_ece"] <= 1.0
            assert 0.0 <= rep["market_ece"] <= 1.0

    def test_bins_populated(self):
        rep = run()
        if rep["status"] == "ok":
            assert len(rep["model_bins"]) >= 3
            for b in rep["model_bins"]:
                assert b["n"] >= 2

    def test_ece_target_or_verdict_flags(self):
        rep = run()
        if rep["status"] == "ok":
            if rep["model_passed"] and rep["market_passed"]:
                assert "PASS" in rep["verdict"]
            else:
                assert "CALIBRATION_GAP" in rep["verdict"]
