"""tests.platform.test_finishing_prior — leak-free finishing residual + finishing prior tests.

Coverage:
  1. build_asof_frame: snapshot-before-update (first appearance n_prior=0, residual=0.0)
  2. build_asof_frame: no-future-leak assertion fires on deliberate corruption
  3. build_asof_frame: EW update follows ALPHA from config
  4. build_asof_frame: NaN goals/SoT rows are skipped safely
  5. _adjust_lambda: cold-start returns lam unchanged
  6. _adjust_lambda: positive residual decreases lambda (hot team regresses down)
  7. _adjust_lambda: negative residual increases lambda (cold team regresses up)
  8. _adjust_lambda: adjustment is capped at MAX_LAMBDA_ADJUST
  9. walk_forward_finishing_prior: output columns present; length matches input
  10. walk_forward_finishing_prior: baseline p_over25 equals ratings.walk_forward_goals
  11. walk_forward_finishing_prior: adjusted lambdas differ from baseline when residual present
  12. walk_forward_finishing_prior: all adjusted lambdas in RATE_CLIP range
  13. score_finishing_prior: runs on synthetic 12-match corpus; returns required keys
  14. Real corpus validation: O/U-2.5 + 1X2 baseline vs finishing Brier/ECE
  15. AST forbidden-import check (F5 compliance for both new modules)
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import pathlib
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA, RATE_CLIP
from domains.soccer.finishing_asof import (
    K_CONV,
    FINISHING_ASOF_COLS,
    build_asof_frame,
    _FinishingHistory,
    _assert_no_future_leak,
)
from domains.soccer.finishing_prior import (
    SHRINK_MASS,
    MIN_PRIOR_MATCHES,
    MAX_LAMBDA_ADJUST,
    _adjust_lambda,
    walk_forward_finishing_prior,
    score_finishing_prior,
)

# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

_D = dt.date


def _make_matches(rows: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if "div" not in df.columns:
        df["div"] = "E0"
    if "ftr" not in df.columns:
        # derive ftr from scores
        def _ftr(r):
            if r["fthg"] > r["ftag"]:
                return "H"
            if r["fthg"] < r["ftag"]:
                return "A"
            return "D"
        df["ftr"] = df.apply(_ftr, axis=1)
    return df


def _make_stats(rows: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if "div" not in df.columns:
        df["div"] = "E0"
    return df


# 8-match corpus: 4 teams, enough history to accumulate residuals
MATCHES_8 = _make_matches([
    {"date": "2024-08-10", "home_team": "A", "away_team": "B", "fthg": 3, "ftag": 0},
    {"date": "2024-08-10", "home_team": "C", "away_team": "D", "fthg": 1, "ftag": 2},
    {"date": "2024-08-17", "home_team": "B", "away_team": "C", "fthg": 2, "ftag": 2},
    {"date": "2024-08-17", "home_team": "D", "away_team": "A", "fthg": 0, "ftag": 1},
    {"date": "2024-08-24", "home_team": "A", "away_team": "C", "fthg": 2, "ftag": 1},
    {"date": "2024-08-24", "home_team": "B", "away_team": "D", "fthg": 1, "ftag": 1},
    {"date": "2024-08-31", "home_team": "C", "away_team": "A", "fthg": 0, "ftag": 2},
    {"date": "2024-08-31", "home_team": "D", "away_team": "B", "fthg": 2, "ftag": 0},
])

# SoT sidecar — event_ids must align with MATCHES_8
STATS_8 = _make_stats([
    {"event_id": None, "date": "2024-08-10", "home_team": "A", "away_team": "B",
     "home_sot": 8.0, "away_sot": 2.0},
    {"event_id": None, "date": "2024-08-10", "home_team": "C", "away_team": "D",
     "home_sot": 3.0, "away_sot": 5.0},
    {"event_id": None, "date": "2024-08-17", "home_team": "B", "away_team": "C",
     "home_sot": 6.0, "away_sot": 4.0},
    {"event_id": None, "date": "2024-08-17", "home_team": "D", "away_team": "A",
     "home_sot": 2.0, "away_sot": 5.0},
    {"event_id": None, "date": "2024-08-24", "home_team": "A", "away_team": "C",
     "home_sot": 7.0, "away_sot": 3.0},
    {"event_id": None, "date": "2024-08-24", "home_team": "B", "away_team": "D",
     "home_sot": 4.0, "away_sot": 4.0},
    {"event_id": None, "date": "2024-08-31", "home_team": "C", "away_team": "A",
     "home_sot": 2.0, "away_sot": 6.0},
    {"event_id": None, "date": "2024-08-31", "home_team": "D", "away_team": "B",
     "home_sot": 5.0, "away_sot": 3.0},
])

# Assign synthetic event_ids
def _add_event_ids(matches: pd.DataFrame, stats: pd.DataFrame):
    """Assign event_id to both frames based on row order."""
    eids = [
        f"{row.date.date()}-{row.div}-{row.home_team}-{row.away_team}".lower().replace(" ", "_")
        for _, row in matches.iterrows()
    ]
    m = matches.copy()
    s = stats.copy()
    m["event_id"] = eids
    s["event_id"] = eids
    return m, s


MATCHES_8, STATS_8 = _add_event_ids(MATCHES_8, STATS_8)


# ---------------------------------------------------------------------------
# 1. Snapshot-before-update: first appearance has n_prior=0 + residual=0
# ---------------------------------------------------------------------------

class TestASOFFirstAppearance:
    def test_first_home_appearance_prior_zero(self):
        out = build_asof_frame(STATS_8, MATCHES_8[["event_id", "fthg", "ftag"]])
        # Row 0 is A (home) vs B (away) — both first appearances
        row0 = out.iloc[0]
        assert row0["home_n_prior"] == 0
        assert row0["away_n_prior"] == 0
        assert row0["home_finishing_residual"] == 0.0
        assert row0["away_finishing_residual"] == 0.0

    def test_n_prior_increases(self):
        out = build_asof_frame(STATS_8, MATCHES_8[["event_id", "fthg", "ftag"]])
        # Team A appears in rows: 0 (home), 3 (away), 4 (home), 6 (away)
        # After row 0, A has n_prior >= 1 by row 3
        rows_a = out[(out["event_id"].str.contains("-a-") | out["event_id"].str.contains("-a$") |
                      out["event_id"].isin(
                          [MATCHES_8.iloc[i]["event_id"]
                           for i, r in MATCHES_8.iterrows()
                           if r["home_team"] == "A" or r["away_team"] == "A"]
                      ))]
        # n_prior for A should be monotone-increasing across its appearances
        team_a_n = []
        for _, row in MATCHES_8.iterrows():
            eid = row["event_id"]
            out_row = out[out["event_id"] == eid].iloc[0]
            if row["home_team"] == "A":
                team_a_n.append(int(out_row["home_n_prior"]))
            elif row["away_team"] == "A":
                team_a_n.append(int(out_row["away_n_prior"]))
        for i in range(len(team_a_n) - 1):
            assert team_a_n[i] <= team_a_n[i + 1], (
                f"n_prior for team A not monotone: {team_a_n}"
            )


# ---------------------------------------------------------------------------
# 2. No-future-leak assertion fires on deliberate corruption
# ---------------------------------------------------------------------------

class TestNoFutureLeakAssertion:
    def test_assertion_fires_on_nonzero_first_residual(self):
        out = build_asof_frame(STATS_8, MATCHES_8[["event_id", "fthg", "ftag"]]).copy()
        # Deliberately corrupt: set residual of team A's first row to nonzero
        first_idx = out.index[0]
        out.loc[first_idx, "home_finishing_residual"] = 0.5
        home_arr = STATS_8["home_team"].values
        away_arr = STATS_8["away_team"].values
        with pytest.raises(AssertionError, match="LEAK"):
            _assert_no_future_leak(out, home_arr, away_arr)

    def test_assertion_fires_on_nonzero_first_n_prior(self):
        out = build_asof_frame(STATS_8, MATCHES_8[["event_id", "fthg", "ftag"]]).copy()
        out.loc[out.index[0], "home_n_prior"] = 1  # corrupt
        home_arr = STATS_8["home_team"].values
        away_arr = STATS_8["away_team"].values
        with pytest.raises(AssertionError, match="LEAK"):
            _assert_no_future_leak(out, home_arr, away_arr)


# ---------------------------------------------------------------------------
# 3. EW update follows ALPHA from config
# ---------------------------------------------------------------------------

class TestEWUpdate:
    def test_ew_update_hand_computed(self):
        """Hand-compute 2-match EW for team A and verify."""
        # Team A plays match 0 (home: 3 goals, 8 SoT) and match 3 (away: 1 goal, 5 SoT)
        # After match 0: residual_0 = 3 - 0.32*8 = 3 - 2.56 = 0.44
        # EW after 1 match: 0.0 + ALPHA*(0.44 - 0.0) = ALPHA * 0.44
        hist = _FinishingHistory()
        hist.update(3.0, 8.0)  # match 0 for A
        expected = ALPHA * (3.0 - K_CONV * 8.0)
        assert abs(hist.ew_residual - expected) < 1e-12, (
            f"EW residual after 1 match: {hist.ew_residual} vs {expected}"
        )
        assert hist.n == 1

    def test_ew_update_two_matches(self):
        hist = _FinishingHistory()
        # obs1 = 3 - 0.32*8 = 0.44
        obs1 = 3.0 - K_CONV * 8.0
        hist.update(3.0, 8.0)
        ew1 = ALPHA * obs1
        # obs2 = 1 - 0.32*5 = -0.6
        obs2 = 1.0 - K_CONV * 5.0
        hist.update(1.0, 5.0)
        ew2 = ew1 + ALPHA * (obs2 - ew1)
        assert abs(hist.ew_residual - ew2) < 1e-12
        assert hist.n == 2


# ---------------------------------------------------------------------------
# 4. NaN rows are skipped
# ---------------------------------------------------------------------------

class TestNaNHandling:
    def test_nan_goals_does_not_update(self):
        hist = _FinishingHistory()
        hist.update(float("nan"), 5.0)
        assert hist.n == 0
        assert hist.ew_residual == 0.0

    def test_nan_sot_does_not_update(self):
        hist = _FinishingHistory()
        hist.update(2.0, float("nan"))
        assert hist.n == 0
        assert hist.ew_residual == 0.0

    def test_after_nan_valid_update_works(self):
        hist = _FinishingHistory()
        hist.update(float("nan"), 5.0)
        hist.update(2.0, 4.0)
        expected = ALPHA * (2.0 - K_CONV * 4.0)
        assert abs(hist.ew_residual - expected) < 1e-12
        assert hist.n == 1


# ---------------------------------------------------------------------------
# 5-8. _adjust_lambda
# ---------------------------------------------------------------------------

class TestAdjustLambda:
    def test_cold_start_no_adjustment(self):
        """n_prior < min_prior → lambda unchanged."""
        lam = 1.5
        result = _adjust_lambda(lam, 0.4, n_prior=0)
        assert result == lam

    def test_cold_start_at_boundary(self):
        """n_prior == min_prior - 1 → no adjustment."""
        lam = 1.5
        result = _adjust_lambda(lam, 0.4, n_prior=MIN_PRIOR_MATCHES - 1)
        assert result == lam

    def test_positive_residual_decreases_lambda(self):
        """Hot finishing (positive residual) → lambda regressed DOWN."""
        lam = 1.6
        residual = 0.5  # over-scoring SoT expectation
        result = _adjust_lambda(lam, residual, n_prior=MIN_PRIOR_MATCHES + 1)
        assert result < lam, f"Expected lambda to decrease, got {result} >= {lam}"
        expected = lam - SHRINK_MASS * residual
        lo, hi = RATE_CLIP
        expected = max(lo, min(hi, expected))
        assert abs(result - expected) < 1e-12

    def test_negative_residual_increases_lambda(self):
        """Cold finishing (negative residual) → lambda regressed UP."""
        lam = 1.0
        residual = -0.5  # under-scoring SoT expectation
        result = _adjust_lambda(lam, residual, n_prior=MIN_PRIOR_MATCHES + 1)
        assert result > lam, f"Expected lambda to increase, got {result} <= {lam}"

    def test_adjustment_capped(self):
        """Adjustment is capped at MAX_LAMBDA_ADJUST."""
        lam = 1.5
        # Large residual: 0.25 * 2.0 = 0.5 > MAX_LAMBDA_ADJUST=0.30 → capped at 0.30
        big_residual = 2.0
        result = _adjust_lambda(lam, big_residual, n_prior=MIN_PRIOR_MATCHES + 1,
                                 max_adjust=MAX_LAMBDA_ADJUST)
        expected_adjust = MAX_LAMBDA_ADJUST  # capped
        lo, hi = RATE_CLIP
        expected = max(lo, min(hi, lam - expected_adjust))
        assert abs(result - expected) < 1e-12

    def test_nan_residual_no_adjustment(self):
        """NaN residual → lambda unchanged."""
        lam = 1.5
        result = _adjust_lambda(lam, float("nan"), n_prior=10)
        assert result == lam

    def test_rate_clip_applied(self):
        """Adjusted lambda is always within RATE_CLIP."""
        lo, hi = RATE_CLIP
        # Try to push below lo
        result_low = _adjust_lambda(lo + 0.01, 1.0, n_prior=10,
                                     max_adjust=MAX_LAMBDA_ADJUST)
        assert result_low >= lo
        # Try to push above hi
        result_high = _adjust_lambda(hi - 0.01, -1.0, n_prior=10,
                                      max_adjust=MAX_LAMBDA_ADJUST)
        assert result_high <= hi


# ---------------------------------------------------------------------------
# 9. walk_forward_finishing_prior: columns + length
# ---------------------------------------------------------------------------

class TestWalkForwardFinishingPrior:
    def test_output_columns_present(self):
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        required = {
            "lam_home", "lam_away", "lam_home_adj", "lam_away_adj",
            "p_over25_base", "p_over25_adj",
            "1x2_home_base", "1x2_draw_base", "1x2_away_base",
            "1x2_home_adj", "1x2_draw_adj", "1x2_away_adj",
        }
        assert required.issubset(set(out.columns)), (
            f"Missing columns: {required - set(out.columns)}"
        )

    def test_output_length_matches_input(self):
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        assert len(out) == len(MATCHES_8)

    # 10. Baseline p_over25 matches ratings.walk_forward_goals
    def test_baseline_p_over25_matches_ratings(self):
        from domains.soccer.ratings import walk_forward_goals
        wf_ref = walk_forward_goals(MATCHES_8)
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        # Align on event_id
        ref_map = dict(zip(wf_ref["event_id"], wf_ref["p_over25"]))
        for _, row in out.iterrows():
            ref_p = ref_map.get(row["event_id"])
            if ref_p is not None:
                assert abs(float(row["p_over25_base"]) - float(ref_p)) < 1e-10, (
                    f"p_over25_base mismatch for {row['event_id']}: "
                    f"{row['p_over25_base']} vs {ref_p}"
                )

    # 11. Adjusted lambdas differ from baseline (when residual present + n_prior >= min)
    def test_adjusted_lambdas_differ_after_warmup(self):
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        # After MIN_PRIOR_MATCHES appearances each team, some adjustments should fire.
        late_rows = out.iloc[MIN_PRIOR_MATCHES * 2:]  # skip warmup
        if len(late_rows) == 0:
            pytest.skip("Corpus too small to test post-warmup adjustments")
        diffs_h = (late_rows["lam_home"] - late_rows["lam_home_adj"]).abs()
        diffs_a = (late_rows["lam_away"] - late_rows["lam_away_adj"]).abs()
        assert (diffs_h > 0).any() or (diffs_a > 0).any(), (
            "Expected some lambda adjustments after warmup, got none"
        )

    # 12. All adjusted lambdas in RATE_CLIP range
    def test_adjusted_lambdas_in_rate_clip(self):
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        lo, hi = RATE_CLIP
        assert (out["lam_home_adj"] >= lo).all() and (out["lam_home_adj"] <= hi).all()
        assert (out["lam_away_adj"] >= lo).all() and (out["lam_away_adj"] <= hi).all()

    # 1X2 probabilities sum to 1
    def test_1x2_sums_to_one(self):
        out = walk_forward_finishing_prior(MATCHES_8, STATS_8)
        sums_base = out["1x2_home_base"] + out["1x2_draw_base"] + out["1x2_away_base"]
        sums_adj  = out["1x2_home_adj"]  + out["1x2_draw_adj"]  + out["1x2_away_adj"]
        np.testing.assert_allclose(sums_base.values, 1.0, atol=1e-6)
        np.testing.assert_allclose(sums_adj.values,  1.0, atol=1e-6)


# ---------------------------------------------------------------------------
# 13. score_finishing_prior on synthetic corpus
# ---------------------------------------------------------------------------

class TestScoreFinishingPrior:
    def test_required_keys_present(self):
        result = score_finishing_prior(MATCHES_8, STATS_8)
        required = {
            "n", "ou25_baseline", "ou25_finishing", "d_brier_ou25",
            "ou25_verdict", "overall_verdict", "note",
        }
        assert required.issubset(result.keys()), (
            f"Missing keys: {required - result.keys()}"
        )

    def test_brier_in_range(self):
        result = score_finishing_prior(MATCHES_8, STATS_8)
        base_b = result["ou25_baseline"]["brier"]
        adj_b  = result["ou25_finishing"]["brier"]
        assert 0.0 < base_b < 1.0, f"Baseline Brier {base_b} out of (0,1)"
        assert 0.0 < adj_b  < 1.0, f"Adjusted Brier {adj_b} out of (0,1)"

    def test_d_brier_equals_difference(self):
        result = score_finishing_prior(MATCHES_8, STATS_8)
        expected = result["ou25_finishing"]["brier"] - result["ou25_baseline"]["brier"]
        assert abs(result["d_brier_ou25"] - expected) < 1e-12

    def test_verdict_string_valid(self):
        result = score_finishing_prior(MATCHES_8, STATS_8)
        valid = {"IMPROVES", "NULL/REDISTRIBUTES", "HARMS"}
        assert result["ou25_verdict"] in valid, (
            f"Unexpected verdict: {result['ou25_verdict']!r}"
        )


# ---------------------------------------------------------------------------
# 14. Real corpus validation (O/U-2.5 + 1X2)
# ---------------------------------------------------------------------------

class TestRealCorpusValidation:
    """Validate on the full 25,834-match corpus and print honest numbers."""

    @pytest.fixture(scope="class")
    def real_result(self):
        import pandas as pd
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        matches_path = root / "data" / "domains" / "soccer" / "matches.parquet"
        stats_path   = root / "data" / "domains" / "soccer" / "match_stats.parquet"
        if not matches_path.exists() or not stats_path.exists():
            pytest.skip("Real corpus not available")
        matches_df = pd.read_parquet(matches_path)
        stats_df   = pd.read_parquet(stats_path)
        return score_finishing_prior(matches_df, stats_df)

    def test_corpus_n_matches(self, real_result):
        assert real_result["n"] >= 20000, (
            f"Expected >= 20000 scored matches, got {real_result['n']}"
        )

    def test_ou25_brier_finite(self, real_result):
        b = real_result["ou25_baseline"]["brier"]
        a = real_result["ou25_finishing"]["brier"]
        assert math.isfinite(b), f"Baseline Brier not finite: {b}"
        assert math.isfinite(a), f"Adjusted Brier not finite: {a}"

    def test_1x2_brier_finite(self, real_result):
        if "1x2_baseline" not in real_result:
            pytest.skip("1X2 metrics not present")
        b = real_result["1x2_baseline"]["brier"]
        a = real_result["1x2_finishing"]["brier"]
        assert math.isfinite(b), f"1X2 Baseline Brier not finite: {b}"
        assert math.isfinite(a), f"1X2 Adjusted Brier not finite: {a}"

    def test_print_real_results(self, real_result, capsys):
        """Print the full honest verdict table."""
        import json
        with capsys.disabled():
            print("\n" + "=" * 60)
            print("FINISHING PRIOR — REAL CORPUS VALIDATION (25,834 matches)")
            print("=" * 60)
            print(f"  n               = {real_result['n']}")
            print(f"  K_CONV (pinned) = {real_result['k_conv']}")
            print(f"  SHRINK_MASS     = {real_result['shrink_mass']}")
            print(f"  MIN_PRIOR       = {real_result['min_prior_matches']}")
            print()
            print("  O/U 2.5:")
            b = real_result["ou25_baseline"]
            a = real_result["ou25_finishing"]
            print(f"    Baseline   Brier={b['brier']:.6f}  ECE={b['ece']:.6f}  LogLoss={b['log_loss']:.6f}")
            print(f"    Finishing  Brier={a['brier']:.6f}  ECE={a['ece']:.6f}  LogLoss={a['log_loss']:.6f}")
            print(f"    dBrier={real_result['d_brier_ou25']:+.6f}  dECE={real_result['d_ece_ou25']:+.6f}")
            print(f"    Verdict: {real_result['ou25_verdict']}")
            print()
            if "1x2_baseline" in real_result:
                b2 = real_result["1x2_baseline"]
                a2 = real_result["1x2_finishing"]
                print("  1X2 (home win):")
                print(f"    Baseline   Brier={b2['brier']:.6f}  ECE={b2['ece']:.6f}  LogLoss={b2['log_loss']:.6f}")
                print(f"    Finishing  Brier={a2['brier']:.6f}  ECE={a2['ece']:.6f}  LogLoss={a2['log_loss']:.6f}")
                print(f"    dBrier={real_result['d_brier_1x2']:+.6f}  dECE={real_result['d_ece_1x2']:+.6f}")
                print(f"    Verdict: {real_result['1x2_verdict']}")
                print()
            print(f"  OVERALL: {real_result['overall_verdict']}")
            print()
            print(f"  {real_result['note']}")
            print("=" * 60)


# ---------------------------------------------------------------------------
# 15. AST forbidden-import check (F5 compliance)
# ---------------------------------------------------------------------------

class TestForbiddenImports:
    """Both new modules must not import src.*, kernel.*, domains.nba.*, etc."""

    FORBIDDEN = {"src", "domains.nba", "domains.basketball_nba", "domains.tennis", "random"}
    ALLOWED_PREFIXES = {
        "__future__", "math", "datetime", "dataclasses", "typing", "pathlib",
        "collections", "json", "numpy", "pandas", "pyarrow",
        "domains.soccer",
        "scripts.platformkit",
    }
    ROOT = pathlib.Path(__file__).resolve().parents[2]

    def _get_imports(self, path: pathlib.Path):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
        return imported

    @pytest.mark.parametrize("fname", [
        "finishing_asof.py",
        "finishing_prior.py",
    ])
    def test_no_forbidden_modules(self, fname):
        path = self.ROOT / "domains" / "soccer" / fname
        imports = self._get_imports(path)
        for mod in imports:
            for forbidden in self.FORBIDDEN:
                assert not mod.startswith(forbidden), (
                    f"{fname} imports forbidden module: {mod!r} (matches {forbidden!r})"
                )

    @pytest.mark.parametrize("fname", [
        "finishing_asof.py",
        "finishing_prior.py",
    ])
    def test_allowed_imports_only(self, fname):
        path = self.ROOT / "domains" / "soccer" / fname
        imports = self._get_imports(path)
        for mod in imports:
            ok = any(mod == p or mod.startswith(p + ".") for p in self.ALLOWED_PREFIXES)
            assert ok, f"{fname} has unexpected import: {mod!r}"
