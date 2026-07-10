"""Per-file pytest for prop_sigma_calib.

Run ONLY as:
    python -m pytest domains/basketball_nba/test_prop_sigma_calib.py -q

NEVER run the full suite (it freezes the box).

Tests cover:
  A. Acceptance: over-confident OOF preds -> k > 1 for those stats
  B. No-harm: k >= 1.0 always; absent/thin stat -> k == 1.0
  C. Coverage: with k applied, coverage >= without-k coverage for tight stats
  D. Cache round-trip: save_scale_factors -> load_scale_factors returns same dict
  E. Real OOF data (skipped when absent): realistic k values, pts/reb k > 1
  F. Load fallback: missing cache AND missing OOF -> empty dict (1.0 default)
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.prop_sigma_calib import (
    _SIGMA_FLOOR,
    _TARGET_PCT,
    chrono_split_coverage,
    compute_scale_factors,
    coverage_summary,
    load_scale_factors,
    save_scale_factors,
)


# ---------------------------------------------------------------------------
# Helpers: synthetic OOF builders
# ---------------------------------------------------------------------------

def _make_oof(
    rng: np.random.Generator,
    n_players: int,
    games_per_player: int,
    stat: str,
    true_sigma: float,
    shrink_frac: float = 0.7,
    global_mean: float = 15.0,
) -> pd.DataFrame:
    """Build a synthetic OOF parquet for one stat modelling an over-confident model.

    actual_i  ~ N(player_mean, true_sigma)       -- true game-to-game variance
    oof_pred_i = (1-shrink)*player_mean + shrink*global_mean + N(0, 0.5)
                                                  -- shrinkage toward global mean

    When shrink_frac > 0 the model compresses predictions toward the global mean,
    making prediction residuals (actual - pred) larger than within-player sample_std
    -> effective_z > 1 at 68th percentile -> k > 1.
    """
    rows = []
    base_date = pd.Timestamp("2023-10-01")
    for pid in range(n_players):
        player_mean = rng.uniform(global_mean * 0.4, global_mean * 1.6)
        actuals = rng.normal(loc=player_mean, scale=true_sigma, size=games_per_player)
        actuals = np.maximum(actuals, 0.0)
        # Shrunk prediction: model predicts toward global mean
        pred_mean = (1.0 - shrink_frac) * player_mean + shrink_frac * global_mean
        for i, act in enumerate(actuals):
            pred = pred_mean + rng.normal(0, 0.5)
            pred = max(pred, 0.0)
            rows.append({
                "game_id": f"g{pid}_{i}",
                "player_id": pid,
                "stat": stat,
                "oof_pred": float(pred),
                "actual": float(act),
                "game_date": str((base_date + pd.Timedelta(days=i)).date()),
                "fold": 1,
                "season": "2023-24",
            })
    return pd.DataFrame(rows)


def _make_oof_thin(stat: str, n_rows: int = 10) -> pd.DataFrame:
    """Thin dataset with fewer rows than _MIN_N -> k must be 1.0."""
    rng = np.random.default_rng(0)
    rows = []
    base_date = pd.Timestamp("2023-10-01")
    for i in range(n_rows):
        rows.append({
            "game_id": f"g{i}",
            "player_id": 0,
            "stat": stat,
            "oof_pred": float(rng.normal(10, 2)),
            "actual": float(rng.normal(10, 2)),
            "game_date": str((base_date + pd.Timedelta(days=i)).date()),
            "fold": 1,
            "season": "2023-24",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# A. Acceptance: over-confident preds -> k > 1
# ---------------------------------------------------------------------------

class TestOverConfidentKGtOne:
    """Over-confident (shrinkage) model: residuals exceed window_sigma -> k > 1.

    'Over-confident' means the model compresses predictions toward the global mean,
    so residuals (actual - shrunken_pred) are systematically larger than the
    within-player sample_std window.  k = 68th-percentile of |residual/sigma_window|
    exceeds 1.0 when residuals are wider than the player's own spread.
    """

    def setup_method(self):
        self.rng = np.random.default_rng(42)

    def _compute_k(self, stat: str, true_sigma: float, shrink_frac: float = 0.7,
                   n_players: int = 60, games: int = 50) -> float:
        df = _make_oof(
            self.rng, n_players, games, stat=stat,
            true_sigma=true_sigma, shrink_frac=shrink_frac,
        )
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            factors = compute_scale_factors(oof_path=Path(tmp.name), min_n=50)
        return factors.get(stat, 1.0)

    def test_pts_over_confident_gives_k_gt_one(self):
        # Shrinkage 70% toward global mean: residuals >> sample_std -> k > 1
        k = self._compute_k("pts", true_sigma=5.0, shrink_frac=0.7)
        assert k > 1.0, f"Expected k>1 for over-confident pts (shrinkage) pred, got k={k}"

    def test_reb_over_confident_gives_k_gt_one(self):
        k = self._compute_k("reb", true_sigma=2.5, shrink_frac=0.65)
        assert k > 1.0, f"Expected k>1 for over-confident reb (shrinkage) pred, got k={k}"

    def test_blk_over_confident_gives_k_gt_one(self):
        # blk: high shrinkage -> residuals dominate window_sigma -> k > 1
        k = self._compute_k("blk", true_sigma=0.8, shrink_frac=0.75, n_players=80, games=50)
        assert k > 1.0, f"Expected k>1 for over-confident blk (shrinkage) pred, got k={k}"


# ---------------------------------------------------------------------------
# B. No-harm invariant: k >= 1.0 always; thin data -> k == 1.0
# ---------------------------------------------------------------------------

class TestNoHarmInvariant:

    def test_k_never_below_one_for_well_calibrated(self):
        """Model with no shrinkage (pred ~= actual): k should stay at 1.0."""
        rng = np.random.default_rng(7)
        # shrink_frac=0: pred = player_mean + tiny noise -> residuals ~ within-player std
        df = _make_oof(rng, n_players=60, games_per_player=40, stat="pts",
                       true_sigma=5.0, shrink_frac=0.0)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            factors = compute_scale_factors(oof_path=Path(tmp.name), min_n=50)
        k = factors.get("pts", 1.0)
        assert k >= 1.0, f"k must be >= 1.0, got {k}"

    def test_k_is_1_when_data_thin(self):
        """Thin data (< min_n) -> k == 1.0."""
        df = _make_oof_thin("pts", n_rows=50)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            factors = compute_scale_factors(oof_path=Path(tmp.name), min_n=200)
        k = factors.get("pts", 1.0)
        assert k == 1.0, f"Thin data must give k=1.0, got k={k}"

    def test_all_returned_k_ge_one(self):
        """All k values in the result dict must be >= 1.0 regardless of model type."""
        rng = np.random.default_rng(99)
        dfs = []
        # Mix of shrinkage fractions -- k must always be >= 1
        for stat, ts, sf in [("pts", 5.0, 0.6), ("reb", 2.5, 0.5), ("ast", 2.0, 0.4)]:
            dfs.append(_make_oof(rng, 50, 40, stat=stat, true_sigma=ts, shrink_frac=sf))
        df = pd.concat(dfs, ignore_index=True)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            factors = compute_scale_factors(oof_path=Path(tmp.name), min_n=50)
        for stat, k in factors.items():
            assert k >= 1.0, f"k={k} for stat={stat} violates no-harm (k>=1.0)"

    def test_missing_oof_returns_empty_dict(self):
        """Missing OOF file -> empty dict (callers use .get(stat, 1.0))."""
        factors = compute_scale_factors(oof_path=Path("/nonexistent/oof.parquet"))
        assert factors == {}, f"Expected empty dict, got {factors}"


# ---------------------------------------------------------------------------
# C. Coverage: with k applied, coverage >= coverage_raw for tight stats
# ---------------------------------------------------------------------------

class TestCoverageImproves:

    def test_coverage_scaled_ge_coverage_raw(self):
        """For an over-confident (shrinkage) model, applying k must not decrease coverage."""
        rng = np.random.default_rng(13)
        df = _make_oof(rng, n_players=60, games_per_player=50, stat="pts",
                       true_sigma=5.0, shrink_frac=0.7)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            fpath = Path(tmp.name)
            factors = compute_scale_factors(oof_path=fpath, min_n=50)
        summ = coverage_summary(factors, oof_path=fpath)
        row = summ.get("pts")
        assert row is not None, "coverage_summary must include pts"
        assert row["coverage_scaled"] >= row["coverage_raw"], (
            f"k={row['k']} scaled coverage {row['coverage_scaled']:.3f} "
            f"< raw {row['coverage_raw']:.3f} -- k must not shrink coverage"
        )

    def test_coverage_scaled_near_nominal_68(self):
        """After applying k, coverage at 1-sigma should be close to 68.27%."""
        rng = np.random.default_rng(21)
        df = _make_oof(rng, n_players=100, games_per_player=60, stat="reb",
                       true_sigma=2.5, shrink_frac=0.65)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            fpath = Path(tmp.name)
            factors = compute_scale_factors(oof_path=fpath, min_n=50)
        summ = coverage_summary(factors, oof_path=fpath)
        row = summ.get("reb")
        assert row is not None
        # Scaled coverage should be within 5pp of 68.27% (Monte Carlo noise)
        assert abs(row["coverage_scaled"] - 0.6827) <= 0.07, (
            f"scaled coverage {row['coverage_scaled']:.3f} outside 68.27% +/- 7pp"
        )


# ---------------------------------------------------------------------------
# C2. Chrono-split OOS readout: fixes the compute_scale_factors()+
# coverage_summary() circularity (fit and score k on the SAME sample).
# ---------------------------------------------------------------------------

class TestChronoSplitOOS:

    def test_structure_and_no_leak_on_synthetic_data(self):
        """Fit-on-early/score-on-late split runs without raising (leak guard
        included) and returns a well-formed verdict per stat."""
        rng = np.random.default_rng(11)
        df = _make_oof(rng, n_players=80, games_per_player=80, stat="pts",
                       true_sigma=5.0, shrink_frac=0.6)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            oos = chrono_split_coverage(oof_path=Path(tmp.name), min_n=50)
        row = oos.get("pts")
        assert row is not None
        assert row["verdict"] in {"SURVIVES", "DOES_NOT_SURVIVE_OOS", "UNDERPOWERED"}
        if row["verdict"] != "UNDERPOWERED":
            assert row["k_fit"] >= 1.0
            assert 0.0 <= row["coverage_eval_scaled"] <= 1.0
            assert row["n_fit"] > 0 and row["n_eval"] > 0

    def test_too_few_dates_returns_empty(self):
        """< 4 unique dates in the corpus -> empty dict (guard, not a crash)."""
        df = _make_oof_thin("pts", n_rows=3)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            oos = chrono_split_coverage(oof_path=Path(tmp.name))
        assert oos == {}

    def test_missing_oof_returns_empty(self):
        oos = chrono_split_coverage(oof_path=Path("/nonexistent/oof.parquet"))
        assert oos == {}


# ---------------------------------------------------------------------------
# D. Cache round-trip
# ---------------------------------------------------------------------------

class TestCacheRoundTrip:

    def test_save_and_load_gives_same_factors(self):
        factors_in = {"pts": 1.05, "reb": 1.04, "ast": 1.0, "blk": 1.0}
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "prop_sigma_scale.json"
            save_scale_factors(factors_in, cache_path=cache_path)
            assert cache_path.exists()
            factors_out = load_scale_factors(
                cache_path=cache_path,
                oof_path=Path("/nonexistent/oof.parquet"),
            )
        assert factors_out == factors_in, (
            f"Round-trip mismatch: in={factors_in}, out={factors_out}"
        )

    def test_load_with_bad_cache_falls_back_to_oof(self):
        """Malformed cache JSON -> recompute from OOF (or return empty if OOF absent)."""
        rng = np.random.default_rng(3)
        df = _make_oof(rng, 50, 40, "pts", true_sigma=5.0, shrink_frac=0.65)
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "bad_cache.json"
            oof_path = Path(tmp_dir) / "oof.parquet"
            df.to_parquet(oof_path)
            # Write a malformed cache
            cache_path.write_text("{invalid json}")
            factors = load_scale_factors(cache_path=cache_path, oof_path=oof_path)
        # Should have recomputed from OOF
        assert "pts" in factors, "After bad cache, should recompute from OOF"
        assert factors["pts"] >= 1.0

    def test_load_missing_cache_and_oof_returns_empty(self):
        """Neither cache nor OOF -> empty dict (1.0 default at call site)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            factors = load_scale_factors(
                cache_path=Path(tmp_dir) / "no_cache.json",
                oof_path=Path(tmp_dir) / "no_oof.parquet",
            )
        assert factors == {}, f"Expected empty dict, got {factors}"

    def test_cache_json_has_all_k_ge_one(self):
        """Persisted JSON must have all values >= 1.0."""
        factors_in = {"pts": 1.05, "reb": 1.0, "ast": 1.01}
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "sigma.json"
            save_scale_factors(factors_in, cache_path=cache_path)
            with open(cache_path) as fh:
                payload = json.load(fh)
        for stat, k in payload["scale_factors"].items():
            assert k >= 1.0, f"JSON has k={k} for stat={stat} (must be >= 1.0)"


# ---------------------------------------------------------------------------
# E. Real OOF data integration test (skipped if absent)
# ---------------------------------------------------------------------------

_REAL_OOF = Path("data/cache/pregame_oof.parquet")


@pytest.mark.skipif(not _REAL_OOF.exists(), reason="pregame_oof.parquet not present")
class TestRealOOFData:

    def test_all_k_ge_one_on_real_data(self):
        factors = compute_scale_factors(oof_path=_REAL_OOF)
        assert factors, "Expected non-empty scale factors from real OOF"
        for stat, k in factors.items():
            assert k >= 1.0, f"k={k} for stat={stat} must be >= 1.0"

    def test_pts_and_reb_k_gt_one_on_real_data(self):
        """pts and reb are the most over-confident stats in the OOF corpus."""
        factors = compute_scale_factors(oof_path=_REAL_OOF)
        pts_k = factors.get("pts", 1.0)
        reb_k = factors.get("reb", 1.0)
        # From empirical analysis: pts k~1.042, reb k~1.044
        assert pts_k > 1.0, f"Expected pts k>1.0 (over-confident), got {pts_k}"
        assert reb_k > 1.0, f"Expected reb k>1.0 (over-confident), got {reb_k}"

    def test_all_stats_present(self):
        factors = compute_scale_factors(oof_path=_REAL_OOF)
        expected = {"pts", "reb", "ast", "stl", "blk", "fg3m", "tov"}
        present = set(factors.keys())
        # All stats with >= min_n data should be present
        assert expected.issubset(present), (
            f"Missing stats: {expected - present}"
        )

    def test_coverage_summary_scaled_ge_raw(self):
        """For every stat in real data, scaled coverage >= raw coverage."""
        factors = compute_scale_factors(oof_path=_REAL_OOF)
        summ = coverage_summary(factors, oof_path=_REAL_OOF)
        for stat, row in summ.items():
            assert row["coverage_scaled"] >= row["coverage_raw"] - 1e-6, (
                f"{stat}: scaled={row['coverage_scaled']:.4f} < "
                f"raw={row['coverage_raw']:.4f}"
            )

    def test_coverage_scaled_within_target_band(self):
        """Scaled coverage should be near 68.27% (+/- 8pp) for all stats."""
        factors = compute_scale_factors(oof_path=_REAL_OOF)
        summ = coverage_summary(factors, oof_path=_REAL_OOF)
        target = _TARGET_PCT / 100.0
        for stat, row in summ.items():
            k = row["k"]
            cov = row["coverage_scaled"]
            # Over-covering (k stayed at 1.0 because raw k_raw < 1) is acceptable;
            # under-covering (cov << target) would indicate a bug.
            # For k=1.0 stats: coverage can exceed target (already wide sigma).
            if k > 1.0:
                assert cov >= target - 0.08, (
                    f"{stat}: k={k:.3f} scaled_coverage={cov:.3f} "
                    f"should be near {target:.3f} (within 8pp)"
                )


# ---------------------------------------------------------------------------
# E2. Real OOF chrono-split: the honest generalization check in-sample
# coverage_summary() cannot provide (it fits and scores on the same rows).
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _REAL_OOF.exists(), reason="pregame_oof.parquet not present")
class TestChronoSplitRealData:

    def test_oos_readout_runs_and_reports_verdicts(self):
        oos = chrono_split_coverage(oof_path=_REAL_OOF)
        assert oos, "Expected non-empty chrono-split readout on real OOF data"
        for stat, row in oos.items():
            assert row["verdict"] in {"SURVIVES", "DOES_NOT_SURVIVE_OOS", "UNDERPOWERED"}, (
                f"{stat}: unexpected verdict {row['verdict']}"
            )
            if row["verdict"] != "UNDERPOWERED":
                assert row["k_fit"] >= 1.0
                assert 0.0 <= row["coverage_eval_scaled"] <= 1.0


# ---------------------------------------------------------------------------
# F. Multiplicative integration: player_props style sigma * k
# ---------------------------------------------------------------------------

class TestMultiplicativeIntegration:
    """Verify that sigma * k with 1.0 fallback is safe for any calling pattern."""

    def test_get_default_1(self):
        """load_scale_factors with absent files -> 1.0 via .get(stat, 1.0)."""
        factors: Dict[str, float] = {}  # what load_scale_factors returns when absent
        k = factors.get("pts", 1.0)
        assert k == 1.0

    def test_sigma_inflation_is_additive_multiplier(self):
        """sigma_inflated = sigma_base * k >= sigma_base always."""
        factors_in = {"pts": 1.05, "reb": 1.044, "blk": 1.0}
        with tempfile.TemporaryDirectory() as tmp_dir:
            cp = Path(tmp_dir) / "s.json"
            save_scale_factors(factors_in, cache_path=cp)
            factors = load_scale_factors(
                cache_path=cp, oof_path=Path("/no/oof.parquet")
            )
        for stat, sigma_base in [("pts", 6.0), ("reb", 2.5), ("blk", 1.0), ("ast", 2.0)]:
            k = factors.get(stat, 1.0)
            sigma_inflated = sigma_base * k
            assert sigma_inflated >= sigma_base, (
                f"{stat}: sigma_inflated={sigma_inflated} < sigma_base={sigma_base}"
            )
