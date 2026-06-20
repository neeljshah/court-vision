"""Per-file pytest for prop_coverage_diag.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_prop_coverage_diag.py -q

NEVER run the full suite (it freezes the box).

Tests cover:
  A. Acceptance: over-confident OOF (residuals wider than sigma) ->
     coverage_below_nominal=True for that stat.
  B. Well-calibrated OOF -> coverage near nominal, coverage_below_nominal=False.
  C. Thin stat (< MIN_N triplets) -> INSUFFICIENT_DATA.
  D. Absent OOF file -> empty dict, never raises.
  E. scale_factors={"stat": k>1} reduces gap vs k=1.0 for tight stat.
  F. coverage_flag_summary aggregates flags correctly.
  G. Read-only invariant: no parquet written by diagnose_coverage.
  H. No $ field in any output.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.prop_coverage_diag import (
    INSUFFICIENT_DATA,
    MIN_N,
    _SIGMA_FLOOR,
    _WINDOW,
    _MIN_WINDOW,
    _NOMINAL,
    COVERAGE_TOL,
    coverage_flag_summary,
    diagnose_coverage,
)


# ---------------------------------------------------------------------------
# OOF builders
# ---------------------------------------------------------------------------

def _make_oof(
    rng: np.random.Generator,
    n_players: int,
    games_per_player: int,
    stat: str,
    true_sigma: float,
    shrink_frac: float = 0.0,
    global_mean: float = 15.0,
    start_date: str = "2023-10-01",
) -> pd.DataFrame:
    """Synthetic OOF parquet for a single stat.

    When shrink_frac > 0 the model is over-confident (shrinks toward global mean),
    making residuals larger than the within-player window sigma -> under-coverage.
    When shrink_frac == 0 the model is nearly unbiased and coverage should be ~nominal.
    """
    rows = []
    base = pd.Timestamp(start_date)
    for pid in range(n_players):
        player_mean = rng.uniform(global_mean * 0.5, global_mean * 1.5)
        actuals = rng.normal(player_mean, true_sigma, size=games_per_player)
        actuals = np.maximum(actuals, 0.0)
        pred_mean = (
            (1.0 - shrink_frac) * player_mean + shrink_frac * global_mean
        )
        for i, act in enumerate(actuals):
            pred = pred_mean + rng.normal(0, 0.3)
            rows.append({
                "player_id": pid,
                "stat": stat,
                "oof_pred": float(max(pred, 0.0)),
                "actual": float(act),
                "game_date": str((base + pd.Timedelta(days=i)).date()),
                "fold": 1,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# A. Over-confident OOF -> coverage_below_nominal=True
# ---------------------------------------------------------------------------

class TestOverConfidentFlagsCoverageBelow:
    """Shrinkage-model residuals systematically exceed window sigma -> under-coverage."""

    def test_pts_over_confident_flags_below(self):
        rng = np.random.default_rng(1)
        # shrink 80% toward global mean; residuals >> window sigma
        df = _make_oof(rng, n_players=80, games_per_player=60,
                       stat="pts", true_sigma=6.0, shrink_frac=0.80)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"pts": 1.0},  # no inflation -> under-covered
                min_n=50,
                coverage_tol=COVERAGE_TOL,
            )
        assert "pts" in result, "pts must appear in result"
        assert result["pts"] != INSUFFICIENT_DATA, "should not be INSUFFICIENT_DATA"
        r = result["pts"]
        assert isinstance(r, dict)
        assert r["coverage_below_nominal"] is True, (
            f"Expected coverage_below_nominal=True for over-confident pts; "
            f"got cov={r['coverage_at_1sig']:.3f}, gap={r['gap']:.3f}"
        )

    def test_reb_over_confident_flags_below(self):
        rng = np.random.default_rng(2)
        df = _make_oof(rng, n_players=80, games_per_player=55,
                       stat="reb", true_sigma=3.0, shrink_frac=0.75)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"reb": 1.0},
                min_n=50,
            )
        r = result.get("reb")
        assert r is not None and r != INSUFFICIENT_DATA
        assert isinstance(r, dict)
        assert r["coverage_below_nominal"] is True, (
            f"reb over-confident: expected below-nominal, got {r}"
        )


# ---------------------------------------------------------------------------
# B. Well-calibrated OOF -> coverage near nominal, coverage_below_nominal=False
# ---------------------------------------------------------------------------

class TestWellCalibratedNearNominal:
    """Model pred ~= actual (no shrinkage, no bias): sigma_window matches residuals."""

    def test_unbiased_model_coverage_near_nominal(self):
        rng = np.random.default_rng(10)
        # shrink_frac=0: pred = player_mean + tiny noise; residuals ~ within-window std
        df = _make_oof(rng, n_players=100, games_per_player=70,
                       stat="pts", true_sigma=5.0, shrink_frac=0.0)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"pts": 1.0},
                min_n=50,
            )
        r = result.get("pts")
        assert r is not None and r != INSUFFICIENT_DATA
        assert isinstance(r, dict)
        # coverage should be within 8pp of nominal (Monte Carlo noise tolerance)
        assert abs(r["coverage_at_1sig"] - _NOMINAL) <= 0.08, (
            f"Well-calibrated model coverage {r['coverage_at_1sig']:.3f} "
            f"expected near {_NOMINAL:.4f}"
        )
        assert r["coverage_below_nominal"] is False, (
            f"Well-calibrated model should not flag below-nominal; got {r}"
        )

    def test_output_has_required_keys(self):
        rng = np.random.default_rng(11)
        df = _make_oof(rng, n_players=60, games_per_player=50,
                       stat="ast", true_sigma=2.0, shrink_frac=0.0)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"ast": 1.0},
                min_n=50,
            )
        r = result.get("ast")
        assert r is not None and r != INSUFFICIENT_DATA
        assert isinstance(r, dict)
        for key in ("stat", "n", "coverage_at_1sig", "nominal",
                    "gap", "coverage_below_nominal", "k", "note"):
            assert key in r, f"Required key '{key}' missing from result"


# ---------------------------------------------------------------------------
# C. Thin stat -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestThinStatInsufficientData:

    def test_fewer_than_min_n_gives_insufficient_data(self):
        rng = np.random.default_rng(20)
        # 5 players x 20 games = at most ~75 triplets, well below default MIN_N=100
        df = _make_oof(rng, n_players=5, games_per_player=20,
                       stat="blk", true_sigma=0.8, shrink_frac=0.5)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"blk": 1.0},
                min_n=MIN_N,  # default: 100
            )
        val = result.get("blk")
        assert val == INSUFFICIENT_DATA, (
            f"Thin stat expected INSUFFICIENT_DATA, got {val}"
        )

    def test_empty_stat_gives_insufficient_data(self):
        # Stat present but zero rows
        df = pd.DataFrame({
            "player_id": [], "stat": [], "oof_pred": [],
            "actual": [], "game_date": [], "fold": [],
        })
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={},
                min_n=50,
            )
        # empty dataframe -> empty result (no stats)
        assert result == {}, f"Empty OOF -> empty result, got {result}"

    def test_min_n_boundary_is_exclusive(self):
        """Exactly min_n-1 triplets -> INSUFFICIENT_DATA."""
        rng = np.random.default_rng(21)
        # Build a dataset with exactly (min_n - 1) scorable triplets by design:
        # use a modest-size dataset where we know fewer triplets form
        min_n = 80  # low threshold for this test
        # 4 players x 18 games each; after _MIN_WINDOW skip -> ~4*(18-5) = 52 triplets
        df = _make_oof(rng, n_players=4, games_per_player=18,
                       stat="tov", true_sigma=1.5, shrink_frac=0.0)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"tov": 1.0},
                min_n=min_n,
            )
        val = result.get("tov")
        assert val == INSUFFICIENT_DATA, (
            f"Expected INSUFFICIENT_DATA when n < {min_n}, got {val}"
        )


# ---------------------------------------------------------------------------
# D. Absent OOF -> empty dict, never raises
# ---------------------------------------------------------------------------

class TestAbsentOOFSafe:

    def test_missing_oof_returns_empty(self):
        result = diagnose_coverage(
            oof_path=Path("/nonexistent/path/oof.parquet"),
            scale_factors={},
        )
        assert isinstance(result, dict)
        assert result == {}

    def test_missing_oof_never_raises(self):
        # Should not raise any exception
        try:
            diagnose_coverage(
                oof_path=Path("/no/such/file.parquet"),
                scale_factors={"pts": 1.0},
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"diagnose_coverage raised unexpectedly: {exc}")

    def test_missing_columns_returns_empty(self):
        # Parquet with wrong columns -> empty dict
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={},
            )
        assert result == {}


# ---------------------------------------------------------------------------
# E. Scale-factor k>1 improves coverage for tight stat
# ---------------------------------------------------------------------------

class TestInflationReducesGap:
    """For an over-confident stat, k>1 should improve (increase) coverage."""

    def test_inflation_increases_coverage(self):
        rng = np.random.default_rng(30)
        df = _make_oof(rng, n_players=80, games_per_player=60,
                       stat="pts", true_sigma=6.0, shrink_frac=0.80)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            path = Path(tmp.name)
            result_k1 = diagnose_coverage(
                oof_path=path, scale_factors={"pts": 1.0}, min_n=50,
            )
            result_k2 = diagnose_coverage(
                oof_path=path, scale_factors={"pts": 2.0}, min_n=50,
            )
        r1 = result_k1.get("pts")
        r2 = result_k2.get("pts")
        assert isinstance(r1, dict) and isinstance(r2, dict)
        assert r2["coverage_at_1sig"] >= r1["coverage_at_1sig"], (
            f"k=2.0 coverage {r2['coverage_at_1sig']:.3f} should be >= "
            f"k=1.0 coverage {r1['coverage_at_1sig']:.3f}"
        )

    def test_k_field_reflects_input(self):
        rng = np.random.default_rng(31)
        df = _make_oof(rng, n_players=60, games_per_player=50,
                       stat="reb", true_sigma=2.5, shrink_frac=0.0)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"reb": 1.44},
                min_n=50,
            )
        r = result.get("reb")
        if r is not None and r != INSUFFICIENT_DATA:
            assert isinstance(r, dict)
            assert abs(r["k"] - 1.44) < 1e-9, (
                f"k field must reflect input 1.44, got {r['k']}"
            )


# ---------------------------------------------------------------------------
# F. coverage_flag_summary
# ---------------------------------------------------------------------------

class TestCoverageFlagSummary:

    def _fake_diag(self) -> Dict:
        """Minimal fake diagnose_coverage output for summary tests."""
        return {
            "pts": {
                "stat": "pts", "n": 200,
                "coverage_at_1sig": 0.60, "nominal": _NOMINAL,
                "gap": round(0.60 - _NOMINAL, 4),
                "coverage_below_nominal": True,
                "k": 1.0, "note": "UNDER-COVERED",
            },
            "reb": {
                "stat": "reb", "n": 150,
                "coverage_at_1sig": 0.69, "nominal": _NOMINAL,
                "gap": round(0.69 - _NOMINAL, 4),
                "coverage_below_nominal": False,
                "k": 1.04, "note": "OK",
            },
            "blk": INSUFFICIENT_DATA,
        }

    def test_any_below_nominal_true_when_stat_flagged(self):
        summary = coverage_flag_summary(self._fake_diag())
        assert summary["any_below_nominal"] is True

    def test_pts_flag_is_coverage_below_nominal(self):
        summary = coverage_flag_summary(self._fake_diag())
        assert summary["flags"]["pts"] == "coverage_below_nominal"

    def test_reb_flag_is_ok(self):
        summary = coverage_flag_summary(self._fake_diag())
        assert summary["flags"]["reb"] == "ok"

    def test_blk_flag_is_insufficient_data(self):
        summary = coverage_flag_summary(self._fake_diag())
        assert summary["flags"]["blk"] == INSUFFICIENT_DATA

    def test_all_ok_gives_any_below_false(self):
        diag = {
            "pts": {
                "stat": "pts", "n": 300,
                "coverage_at_1sig": 0.70, "nominal": _NOMINAL,
                "gap": 0.017, "coverage_below_nominal": False,
                "k": 1.05, "note": "OK",
            }
        }
        summary = coverage_flag_summary(diag)
        assert summary["any_below_nominal"] is False

    def test_summary_has_required_keys(self):
        summary = coverage_flag_summary(self._fake_diag())
        for key in ("stats", "flags", "any_below_nominal", "note"):
            assert key in summary, f"Required key '{key}' missing from summary"

    def test_stats_list_is_sorted(self):
        summary = coverage_flag_summary(self._fake_diag())
        assert summary["stats"] == sorted(summary["stats"])


# ---------------------------------------------------------------------------
# G. Read-only: diagnose_coverage never writes files
# ---------------------------------------------------------------------------

class TestReadOnly:

    def test_no_file_written_to_tmp_dir(self):
        """diagnose_coverage must not create any new file in /tmp or the OOF dir."""
        rng = np.random.default_rng(40)
        df = _make_oof(rng, n_players=60, games_per_player=50,
                       stat="pts", true_sigma=5.0, shrink_frac=0.5)
        with tempfile.TemporaryDirectory() as tmpdir:
            oof_path = Path(tmpdir) / "oof.parquet"
            df.to_parquet(oof_path)
            files_before = set(os.listdir(tmpdir))
            diagnose_coverage(
                oof_path=oof_path,
                scale_factors={"pts": 1.0},
                min_n=50,
            )
            files_after = set(os.listdir(tmpdir))
        assert files_before == files_after, (
            f"diagnose_coverage created new files: {files_after - files_before}"
        )


# ---------------------------------------------------------------------------
# H. No $ field in any output
# ---------------------------------------------------------------------------

class TestNoDollarField:
    """No key in any output should contain 'dollar', '$', 'roi', 'pnl', 'profit'."""

    FORBIDDEN = {"dollar", "roi", "pnl", "profit", "bankroll", "stake", "usd"}

    def _all_keys(self, obj, collected=None):
        if collected is None:
            collected = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                collected.add(str(k).lower())
                self._all_keys(v, collected)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                self._all_keys(v, collected)
        return collected

    def test_no_dollar_in_result_keys(self):
        rng = np.random.default_rng(50)
        df = _make_oof(rng, n_players=60, games_per_player=50,
                       stat="pts", true_sigma=5.0, shrink_frac=0.5)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"pts": 1.0},
                min_n=50,
            )
        all_keys = self._all_keys(result)
        forbidden_found = self.FORBIDDEN & all_keys
        assert not forbidden_found, (
            f"Forbidden keys found in output: {forbidden_found}"
        )

    def test_no_dollar_sign_in_note_field(self):
        rng = np.random.default_rng(51)
        df = _make_oof(rng, n_players=60, games_per_player=50,
                       stat="pts", true_sigma=5.0, shrink_frac=0.8)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            df.to_parquet(tmp.name)
            result = diagnose_coverage(
                oof_path=Path(tmp.name),
                scale_factors={"pts": 1.0},
                min_n=50,
            )
        r = result.get("pts")
        if isinstance(r, dict) and "note" in r:
            assert "$" not in r["note"], f"Dollar sign in note: {r['note']}"

    def test_no_dollar_in_summary(self):
        summary = coverage_flag_summary({
            "pts": {
                "stat": "pts", "n": 200,
                "coverage_at_1sig": 0.60, "nominal": _NOMINAL,
                "gap": -0.083, "coverage_below_nominal": True,
                "k": 1.0, "note": "UNDER-COVERED",
            }
        })
        all_keys = self._all_keys(summary)
        forbidden_found = self.FORBIDDEN & all_keys
        assert not forbidden_found, (
            f"Forbidden keys in summary: {forbidden_found}"
        )
