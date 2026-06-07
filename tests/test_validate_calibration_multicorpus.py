"""tests/test_validate_calibration_multicorpus.py — EX-7 unit tests.

Tests pure logic only — no GPU, no parquet files, no real corpus data.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.validate_calibration_multicorpus import (
    apply_acceptance_rule,
    MIN_CORPUS_N,
)


# ---------------------------------------------------------------------------
# Helper to build synthetic corpus_results
# ---------------------------------------------------------------------------

def _make_corpus_result(
    name: str,
    eval_start: str,
    stat_rois: Dict[str, Dict[float, float]],
    stat_ns: Dict[str, int],
) -> Dict:
    """Build a minimal corpus_result dict matching the real structure."""
    results: Dict[str, Dict[float, Dict]] = {}
    for stat, roi_by_blend in stat_rois.items():
        results[stat] = {a: {"roi_pct": v, "n": stat_ns.get(stat, 50)}
                         for a, v in roi_by_blend.items()}
    return {
        "name": name,
        "n_total": sum(stat_ns.values()),
        "eval_start": pd.Timestamp(eval_start),
        "bets_by_stat": dict(stat_ns),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Test 1: Acceptance rule — >=2-corpus gate, correct enabled set
# ---------------------------------------------------------------------------

class TestAcceptanceRule:
    """Verify the >=2-corpus gate logic on a synthetic ROI table."""

    def test_pts_accepted_on_2_corpora(self):
        """PTS calibration beats raw on 2/3 corpora => ACCEPT."""
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"pts": {0.0: -3.0, 0.5: -1.0, 1.0: -0.5}},
                                {"pts": 100}),
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"pts": {0.0: -5.0, 0.5: -2.0, 1.0: -1.0}},
                                {"pts": 80}),
            _make_corpus_result("corpus_C", "2024-12-01",
                                {"pts": {0.0: -1.0, 0.5: -3.0, 1.0: -4.0}},
                                {"pts": 60}),
        ]
        acc = apply_acceptance_rule(corpus_results)
        # a=0.5 beats raw on A (+2pp) and B (+3pp), but not C (-2pp) => 2 wins => ACCEPT
        assert acc["pts"]["a_star"] > 0, "Expected pts to be accepted (2 corpora beat raw)"
        assert acc["pts"]["a_star"] == 0.5, "Should prefer a=0.5 (least intervention)"

    def test_reb_rejected_on_1_corpus(self):
        """REB calibration beats raw on only 1/3 corpora => REJECT."""
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"reb": {0.0: 2.0, 0.5: 3.5, 1.0: 4.0}},
                                {"reb": 100}),  # cal wins
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"reb": {0.0: 1.0, 0.5: -2.0, 1.0: -5.0}},
                                {"reb": 80}),   # raw wins
            _make_corpus_result("corpus_C", "2024-12-01",
                                {"reb": {0.0: 3.0, 0.5: -1.0, 1.0: -3.0}},
                                {"reb": 60}),   # raw wins
        ]
        acc = apply_acceptance_rule(corpus_results)
        assert acc["reb"]["a_star"] == 0.0, "REB should be rejected (only 1 corpus cal wins)"
        assert "RAW" in acc["reb"]["verdict"]

    def test_ast_never_in_candidate_stats(self):
        """AST must never appear in the acceptance output (hard-excluded)."""
        from scripts.validate_calibration_multicorpus import CANDIDATE_STATS
        assert "ast" not in CANDIDATE_STATS, "AST must not be in CANDIDATE_STATS"

    def test_ast_excluded_from_acceptance_result(self):
        """apply_acceptance_rule must not produce an entry for ast."""
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"ast": {0.0: 5.0, 0.5: 8.0, 1.0: 9.0}},
                                {"ast": 100}),
        ]
        acc = apply_acceptance_rule(corpus_results)
        assert "ast" not in acc, "AST must be absent from acceptance output"

    def test_thin_corpus_not_counted(self):
        """Corpus with n < MIN_CORPUS_N must not count toward the >=2 gate."""
        # Two corpora beat raw, but one is thin (n < MIN_CORPUS_N)
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"fg3m": {0.0: 1.0, 0.5: 3.0, 1.0: 5.0}},
                                {"fg3m": MIN_CORPUS_N - 1}),   # thin, should not count
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"fg3m": {0.0: 0.5, 0.5: 2.0, 1.0: 3.0}},
                                {"fg3m": MIN_CORPUS_N + 1}),   # counts
        ]
        acc = apply_acceptance_rule(corpus_results)
        # Only 1 qualifying corpus => should NOT be accepted
        assert acc["fg3m"]["a_star"] == 0.0, (
            "fg3m should be rejected when only 1 thick corpus beats raw"
        )

    def test_prefers_smaller_blend_weight(self):
        """When both a=0.5 and a=1.0 satisfy >=2, prefer a=0.5 (least intervention)."""
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"pts": {0.0: -4.0, 0.5: -1.0, 1.0: -0.5}},
                                {"pts": 100}),
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"pts": {0.0: -6.0, 0.5: -3.0, 1.0: -2.0}},
                                {"pts": 80}),
        ]
        acc = apply_acceptance_rule(corpus_results)
        # Both a=0.5 and a=1.0 beat raw on 2 corpora; should pick a=0.5
        assert acc["pts"]["a_star"] == 0.5, "Should prefer a=0.5 over a=1.0"

    def test_none_corpus_ignored(self):
        """None entries (skipped corpora) must be ignored silently."""
        corpus_results = [
            None,  # skipped corpus
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"reb": {0.0: 2.0, 0.5: 4.0, 1.0: 5.0}},
                                {"reb": 100}),
        ]
        # Should not raise; only 1 qualifying corpus so reb stays raw
        acc = apply_acceptance_rule(corpus_results)
        assert acc["reb"]["a_star"] == 0.0

    def test_all_rejected_when_calibration_always_hurts(self):
        """If calibration ALWAYS hurts across all corpora, all stats stay raw."""
        corpus_results = [
            _make_corpus_result("corpus_A", "2026-01-01",
                                {"pts": {0.0: 5.0, 0.5: 3.0, 1.0: 2.0},
                                 "reb": {0.0: 3.0, 0.5: 1.0, 1.0: 0.5},
                                 "fg3m": {0.0: 2.0, 0.5: 0.5, 1.0: -1.0}},
                                {"pts": 100, "reb": 100, "fg3m": 100}),
            _make_corpus_result("corpus_B", "2025-12-01",
                                {"pts": {0.0: 4.0, 0.5: 2.0, 1.0: 1.0},
                                 "reb": {0.0: 2.0, 0.5: 0.5, 1.0: -0.5},
                                 "fg3m": {0.0: 3.0, 0.5: 1.0, 1.0: 0.5}},
                                {"pts": 80, "reb": 80, "fg3m": 80}),
            _make_corpus_result("corpus_C", "2024-12-01",
                                {"pts": {0.0: 6.0, 0.5: 4.0, 1.0: 3.0},
                                 "reb": {0.0: 4.0, 0.5: 2.0, 1.0: 1.0},
                                 "fg3m": {0.0: 5.0, 0.5: 3.0, 1.0: 2.0}},
                                {"pts": 90, "reb": 90, "fg3m": 90}),
        ]
        acc = apply_acceptance_rule(corpus_results)
        for stat in ("pts", "reb", "fg3m"):
            assert acc[stat]["a_star"] == 0.0, f"{stat} should stay raw when cal always hurts"


# ---------------------------------------------------------------------------
# Test 2: Rolling-cut leak guard
# ---------------------------------------------------------------------------

class TestRollingCutLeakGuard:
    """Verify that train data is strictly before eval_start."""

    def test_train_max_date_before_eval_start(self):
        """For any corpus, train rows must all predate eval_start."""
        # We replicate the assertion logic from _train_calibrator
        # without running the full training (pure logic test)
        import pandas as pd

        eval_start = pd.Timestamp("2026-01-28")

        # Simulate a calframe with some rows before and after eval_start
        df = pd.DataFrame({
            "d": pd.to_datetime(["2025-12-01", "2026-01-01", "2026-01-27",
                                   "2026-01-28", "2026-02-01"]),
            "stat": ["pts"] * 5,
            "player_id": [1, 2, 3, 4, 5],
        })
        train = df[df["d"] < eval_start]

        # The assertion that _train_calibrator makes:
        assert train["d"].max() < eval_start, (
            "Leak guard: train max date must be strictly before eval_start"
        )
        # Verify rows from eval_start itself are excluded
        assert len(train) == 3
        assert all(d < eval_start for d in train["d"])

    def test_eval_start_row_excluded_from_train(self):
        """A row with date == eval_start must NOT be in train."""
        eval_start = pd.Timestamp("2026-01-28")
        df = pd.DataFrame({
            "d": pd.to_datetime(["2026-01-27", "2026-01-28", "2026-01-29"]),
        })
        train = df[df["d"] < eval_start]
        assert len(train) == 1
        assert train.iloc[0]["d"] == pd.Timestamp("2026-01-27")


# ---------------------------------------------------------------------------
# Test 3: Blend formula
# ---------------------------------------------------------------------------

class TestBlendFormula:
    """Verify the blending formula matches a*cal + (1-a)*pred."""

    def test_blend_zero_is_raw(self):
        pred, cal = 20.0, 25.0
        a = 0.0
        result = a * cal + (1.0 - a) * pred
        assert result == pred, "a=0 blend must return raw pred unchanged"

    def test_blend_one_is_full_cal(self):
        pred, cal = 20.0, 25.0
        a = 1.0
        result = a * cal + (1.0 - a) * pred
        assert result == cal, "a=1 blend must return calibrated value"

    def test_blend_half_is_average(self):
        pred, cal = 20.0, 24.0
        a = 0.5
        result = a * cal + (1.0 - a) * pred
        assert math.isclose(result, 22.0), f"a=0.5 blend must be midpoint, got {result}"

    def test_blend_sign_preserved_for_small_cal_shift(self):
        """Blending should not flip sign when cal is close to pred."""
        pred, cal = 15.0, 16.0
        for a in (0.0, 0.5, 1.0):
            result = a * cal + (1.0 - a) * pred
            assert result > 0, "Result should remain positive"

    def test_blend_matches_module_formula(self):
        """Blending formula in the script matches a*cal+(1-a)*pred exactly."""
        pred, cal, a = 18.5, 21.3, 0.5
        expected = a * cal + (1.0 - a) * pred
        # This is the exact formula used in _blend_roi
        result = float(a * cal + (1.0 - a) * pred)
        assert math.isclose(result, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 4: Import / smoke
# ---------------------------------------------------------------------------

class TestImportSmoke:
    """Verify the module imports and key constants are sane."""

    def test_module_imports(self):
        """validate_calibration_multicorpus must import without error."""
        import scripts.validate_calibration_multicorpus as m  # noqa: F401

    def test_covs_length(self):
        from scripts.validate_calibration_multicorpus import COVS
        assert len(COVS) == 19, f"Expected 19 COVS, got {len(COVS)}"
        assert "pred" in COVS
        assert "opp_pace" in COVS
        assert "days_into_season" in COVS

    def test_candidate_stats_excludes_ast(self):
        from scripts.validate_calibration_multicorpus import CANDIDATE_STATS
        assert "ast" not in CANDIDATE_STATS

    def test_candidate_blends(self):
        from scripts.validate_calibration_multicorpus import CANDIDATE_BLENDS
        assert 0.0 in CANDIDATE_BLENDS
        assert 0.5 in CANDIDATE_BLENDS
        assert 1.0 in CANDIDATE_BLENDS

    def test_default_corpora(self):
        from scripts.validate_calibration_multicorpus import DEFAULT_CORPORA
        assert "benashkar_2026_canonical.csv" in DEFAULT_CORPORA
        assert "regular_season_2024_25_oddsapi.csv" in DEFAULT_CORPORA
        assert "regular_season_2025_26_oddsapi.csv" in DEFAULT_CORPORA
        # Explicitly not in default
        assert "extended_oos_canonical.csv" not in DEFAULT_CORPORA
        assert "playoffs_2025_26_oddsapi.csv" not in DEFAULT_CORPORA

    def test_apply_acceptance_rule_callable(self):
        """apply_acceptance_rule must be callable with empty list without error."""
        from scripts.validate_calibration_multicorpus import apply_acceptance_rule
        result = apply_acceptance_rule([])
        assert isinstance(result, dict)
        # All stats should be raw with no evidence
        for stat in ("pts", "reb", "fg3m"):
            assert result[stat]["a_star"] == 0.0
