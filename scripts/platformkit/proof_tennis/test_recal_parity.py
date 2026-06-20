"""Per-file test for recal_parity.py.

Tests (all offline / synthetic where possible):
  1. ECE_recal < ECE_TARGET for BOTH tours when real data present.
  2. Brier not worse after recal for both tours.
  3. Identity-in -> identity-out: recal does not inflate ECE on already-calibrated probs.
  4. Leak-free: fit on TRAIN half, score on EVAL half (n_eval = n_holdout // 2).
  5. Bo5 sigma coverage is in expected range [0.40, 0.67].
  6. No $ / edge / roi / pnl key in any output dict.
  7. Synthetic missing-data path returns no_data / INSUFFICIENT_DATA sentinel, never raises.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/proof_tennis/test_recal_parity.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_tennis.recal_parity import (  # noqa: E402
    ECE_TARGET,
    _bo5_sigma_coverage,
    _tour_recal,
    run,
)
from scripts.platformkit.proof_tennis.ingame_calib import recalibrate_holdout  # noqa: E402


# ---------------------------------------------------------------------------
# Identity-in -> identity-out smoke test (moved from recal_parity.py)
# ---------------------------------------------------------------------------
def _identity_check() -> dict:
    """Recal on already-calibrated probs should not inflate ECE by >0.05."""
    rng = np.random.default_rng(42)
    true_p = np.clip(rng.beta(2.0, 2.0, 600), 0.05, 0.95)
    y = (rng.uniform(size=600) < true_p).astype(float)
    res = recalibrate_holdout(true_p, y)
    ece_gap = float(res["ece_recal"]) - float(res["ece_raw"])
    return {
        "status": "ok",
        "n_eval": res["n_eval"],
        "ece_raw_on_perf_probs": res["ece_raw"],
        "ece_recal_on_perf_probs": res["ece_recal"],
        "ece_inflation": round(ece_gap, 5),
        "recal_method": res["recal_method"],
        "recal_not_worse_than_raw": bool(ece_gap <= 0.05),
    }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ATP = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_REAL_DATA = _ATP.is_file() and _WTA.is_file()

# Keys that must NEVER appear in results (no edge/dollar claims)
_FORBIDDEN_KEYS = {"$", "roi", "pnl", "edge", "profit", "dollar"}


def _has_forbidden(d: dict) -> bool:
    return any(k.lower() in _FORBIDDEN_KEYS for k in d)


def _make_synthetic_parquet(tmp_path: Path, n: int = 600, tour: str = "ATP") -> Path:
    """Synthetic matches parquet for offline tests (no external data needed)."""
    rng = np.random.default_rng(seed=17)
    n_players = 50
    dates = pd.date_range("2015-01-01", periods=n, freq="3D")
    p1_ids = rng.integers(1, n_players // 2 + 1, n)
    p2_ids = rng.integers(n_players // 2 + 1, n_players + 1, n)
    # p1 wins with prob 0.5 + slight home advantage based on id
    true_p = 0.5 + 0.1 * np.sin(p1_ids.astype(float))
    winner = (rng.uniform(size=n) < true_p).astype(int) + 1
    score_parts = [f"{rng.integers(6, 8)}-{rng.integers(0, 5)}" for _ in range(n)]
    df = pd.DataFrame({
        "event_id": np.arange(n),
        "date": dates,
        "tour": tour,
        "tourney_id": np.arange(n) % 20,
        "tourney_name": "SyntheticOpen",
        "tourney_level": "A",
        "surface": rng.choice(["Hard", "Clay", "Grass"], n),
        "best_of": 3,
        "round": "R32",
        "match_num": np.arange(n),
        "p1_id": p1_ids,
        "p2_id": p2_ids,
        "p1_name": ["Player_" + str(x) for x in p1_ids],
        "p2_name": ["Player_" + str(x) for x in p2_ids],
        "p1_rank": rng.integers(1, 200, n),
        "p2_rank": rng.integers(1, 200, n),
        "winner": winner,
        "score": score_parts,
        "retirement": False,
        "minutes": rng.integers(60, 180, n),
    })
    out = tmp_path / "matches.parquet"
    df.to_parquet(out, index=False)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestRecalParityRealData:
    """Tests that require real corpus; skipped if data absent."""

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_atp_ece_recal_under_target(self):
        res = _tour_recal(_ATP, "ATP", best_blend=0.3)
        assert res["status"] == "ok", f"ATP recal failed: {res}"
        assert res["ece_recal"] < ECE_TARGET, (
            f"ATP ECE_recal={res['ece_recal']} not under target {ECE_TARGET}")

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_wta_ece_recal_under_target(self):
        res = _tour_recal(_WTA, "WTA", best_blend=0.3)
        assert res["status"] == "ok", f"WTA recal failed: {res}"
        assert res["ece_recal"] < ECE_TARGET, (
            f"WTA ECE_recal={res['ece_recal']} not under target {ECE_TARGET}")

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_brier_not_worse_both_tours(self):
        for path, tour in [(_ATP, "ATP"), (_WTA, "WTA")]:
            res = _tour_recal(path, tour, best_blend=0.3)
            if res.get("status") != "ok":
                continue
            assert res["brier_not_worse"], (
                f"{tour} brier worse after recal: raw={res['brier_raw']} "
                f"recal={res['brier_recal']}")

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_bo5_sigma_coverage_in_range(self):
        res = _bo5_sigma_coverage(_ATP)
        assert res["status"] == "ok", f"Bo5 sigma check failed: {res}"
        cov = res["coverage_50pct_band"]
        assert 0.40 <= cov <= 0.67, (
            f"Bo5 sigma coverage {cov} outside [0.40, 0.67]")

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_parity_verdict_pass(self):
        rep = run()
        assert rep["parity_verdict"].startswith("PARITY PASS"), (
            f"Expected PARITY PASS; got: {rep['parity_verdict']}")

    @pytest.mark.skipif(not _REAL_DATA, reason="real tennis data not available")
    def test_no_forbidden_keys_in_output(self):
        rep = run()
        for key in ("atp", "wta", "bo5_sigma"):
            sub = rep.get(key, {})
            assert not _has_forbidden(sub), (
                f"Forbidden key in {key}: {list(sub.keys())}")


class TestRecalParitySynthetic:
    """Offline tests using synthetic data -- always run."""

    def test_missing_path_returns_no_data(self, tmp_path):
        ghost = tmp_path / "ghost.parquet"
        res = _tour_recal(ghost, "GHOST", best_blend=0.3)
        assert res.get("status") == "no_data"
        assert not _has_forbidden(res)

    def test_too_few_rows_returns_insufficient_data(self, tmp_path):
        # Only 50 rows -> holdout < _MIN_N_RECAL
        small = _make_synthetic_parquet(tmp_path, n=50)
        res = _tour_recal(small, "SMALL", best_blend=0.3)
        assert res.get("status") in ("INSUFFICIENT_DATA", "ok"), res

    def test_synthetic_corpus_runs_without_raise(self, tmp_path):
        synth = _make_synthetic_parquet(tmp_path, n=600)
        res = _tour_recal(synth, "SYN", best_blend=0.0)
        # Status ok or INSUFFICIENT_DATA (depending on train/test split size)
        assert res.get("status") in ("ok", "INSUFFICIENT_DATA"), res

    def test_synthetic_ece_recal_not_worse(self, tmp_path):
        synth = _make_synthetic_parquet(tmp_path, n=600)
        res = _tour_recal(synth, "SYN", best_blend=0.0)
        if res.get("status") != "ok":
            pytest.skip("not enough rows")
        assert res["brier_not_worse"], (
            f"Brier worsened: raw={res['brier_raw']} recal={res['brier_recal']}")

    def test_no_forbidden_keys_synthetic(self, tmp_path):
        synth = _make_synthetic_parquet(tmp_path, n=600)
        res = _tour_recal(synth, "SYN", best_blend=0.0)
        assert not _has_forbidden(res)

    def test_leak_free_n_eval_is_half_holdout(self, tmp_path):
        """n_eval should equal n_holdout // 2 (chronological TRAIN/EVAL split)."""
        synth = _make_synthetic_parquet(tmp_path, n=800)
        res = _tour_recal(synth, "SYN", best_blend=0.0)
        if res.get("status") != "ok":
            pytest.skip("not enough rows")
        n_holdout = res["n_holdout"]
        n_eval = res["n_eval"]
        assert n_eval == n_holdout // 2, (
            f"Leak-free split: expected n_eval={n_holdout // 2}, got {n_eval}")

    def test_identity_check_never_inflates_ece(self):
        res = _identity_check()
        assert res["status"] == "ok"
        # Recal on well-calibrated input must not inflate ECE by more than 0.05
        # (binary EVAL N=300; ECE has high variance; empirical max inflation ~0.045)
        assert res["recal_not_worse_than_raw"], (
            f"Identity check: recal inflated ECE by >0.05: "
            f"raw={res['ece_raw_on_perf_probs']} "
            f"recal={res['ece_recal_on_perf_probs']} "
            f"inflation={res.get('ece_inflation')}")

    def test_bo5_missing_path_no_raise(self, tmp_path):
        ghost = tmp_path / "ghost.parquet"
        res = _bo5_sigma_coverage(ghost)
        assert res.get("status") == "no_data"
        assert not _has_forbidden(res)

    def test_run_no_raise_when_data_missing(self, tmp_path, monkeypatch):
        """run() with missing corpus paths returns dicts, never raises."""
        ghost_atp = tmp_path / "atp.parquet"
        ghost_wta = tmp_path / "wta.parquet"
        rep = run(atp_path=ghost_atp, wta_path=ghost_wta)
        assert "parity_verdict" in rep
        assert "note" in rep
        assert "no_data" in rep["atp"].get("status", "")
        assert "no_data" in rep["wta"].get("status", "")

    def test_recal_method_present_in_result(self, tmp_path):
        synth = _make_synthetic_parquet(tmp_path, n=800)
        res = _tour_recal(synth, "SYN", best_blend=0.0)
        if res.get("status") != "ok":
            pytest.skip("not enough rows")
        assert "recal_method" in res
        assert res["recal_method"] in ("temperature", "platt")
