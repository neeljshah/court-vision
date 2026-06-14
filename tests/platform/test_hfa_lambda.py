"""tests.platform.test_hfa_lambda — Tests for HFA lambda correction (walk_forward_hfa).

Covers:
  test_h_starts_at_prior     : h=1.0 for first match (no prior data)
  test_no_future_leak        : for each match i, h used == h computed from matches[:i]
  test_mass_preserving       : lam_home_adj * lam_away_adj == lam_home_base * lam_away_base
  test_h_gt1_with_real_data  : median h > 1.0 after warmup (on real corpus)
  test_home_adj_gt_base      : when h>1, lam_home_adj > lam_home_base
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List

import pandas as pd
import pytest

from domains.soccer.config import ALPHA, PRIOR_GF, PRIOR_GA
from domains.soccer.hfa_lambda import walk_forward_hfa

# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

_MATCHES_6 = [
    # date, div, home_team, away_team, fthg, ftag
    ("2024-08-10", "E0", "Arsenal",   "Chelsea",    2, 1),
    ("2024-08-10", "E0", "Liverpool",  "Everton",    3, 0),
    ("2024-08-17", "E0", "Chelsea",    "Liverpool",  1, 2),
    ("2024-08-17", "E0", "Everton",    "Arsenal",    0, 3),
    ("2024-08-24", "E0", "Arsenal",    "Liverpool",  1, 1),
    ("2024-08-24", "E0", "Chelsea",    "Everton",    2, 2),
]


def _make_df(rows: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=["date", "div", "home_team", "away_team", "fthg", "ftag"],
    )
    df["date"] = pd.to_datetime(df["date"])
    df["event_id"] = [
        f"{r[0]}-{r[1]}-{r[2].lower()}-{r[3].lower()}"
        for r in rows
    ]
    return df


MATCHES_6 = _make_df(_MATCHES_6)


# ---------------------------------------------------------------------------
# Real corpus fixture (skip if parquet absent)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARQUET = _REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet"
_HAVE_PARQUET = _PARQUET.exists()

real_data = pytest.mark.skipif(not _HAVE_PARQUET, reason="matches.parquet not found")


@pytest.fixture(scope="module")
def real_hfa():
    """Walk-forward HFA result on the full real corpus (cached for the module)."""
    df = pd.read_parquet(_PARQUET)
    return walk_forward_hfa(df)


# ---------------------------------------------------------------------------
# 1. h=1.0 for the first match
# ---------------------------------------------------------------------------


class TestHStartsAtPrior:
    def test_h_starts_at_one_single_match(self):
        """A single-match corpus → h=1.0 (no prior data)."""
        single = _make_df([("2024-01-01", "E0", "HomeFC", "AwayFC", 2, 1)])
        result = walk_forward_hfa(single)
        assert len(result) == 1
        assert result["h"].iloc[0] == 1.0, (
            f"Expected h=1.0 for first match, got {result['h'].iloc[0]}"
        )

    def test_h_starts_at_one_multi_match(self):
        """In a multi-match corpus the very first match also gets h=1.0."""
        result = walk_forward_hfa(MATCHES_6)
        assert result["h"].iloc[0] == 1.0, (
            f"First match h should be 1.0, got {result['h'].iloc[0]}"
        )

    def test_h_changes_after_first_match(self):
        """After at least one match with fthg != ftag, h should drift from 1.0."""
        # With fthg=2, ftag=0 the first match, ew_home > ew_away → h > 1.0 at match 2
        skewed = _make_df([
            ("2024-01-01", "E0", "A", "B", 3, 0),   # big home win
            ("2024-01-08", "E0", "A", "B", 1, 1),
        ])
        result = walk_forward_hfa(skewed)
        # first match: h=1.0 (pre-match)
        assert result["h"].iloc[0] == 1.0
        # second match: ew_home updated with 3, ew_away with 0 → h > 1.0
        h2 = result["h"].iloc[1]
        assert h2 > 1.0, f"Expected h>1.0 after a 3-0 home win, got {h2}"


# ---------------------------------------------------------------------------
# 2. No future leak (the hard correctness test)
# ---------------------------------------------------------------------------


class TestNoFutureLeak:
    def test_no_future_leak(self):
        """For each match i, the h used equals h recomputed from matches[:i].

        Algorithm: replicate the expanding-window EW update in isolation
        (using the same sorted-order walk_forward_goals output for the actual
        goals) and verify that every stored h value matches the ground-truth
        prior-only estimate.

        This is the definitive leak-free assertion — any future-data leakage
        would show up as a mismatch between the single-pass h and the
        ground-truth expanding-window h.
        """
        result = walk_forward_hfa(MATCHES_6)

        # Ground-truth: replay the exact EW update that hfa_lambda uses,
        # using the SORTED goals from walk_forward_goals (same row order).
        from domains.soccer.ratings import walk_forward_goals
        wf = walk_forward_goals(MATCHES_6)

        ew_home = PRIOR_GF
        ew_away = PRIOR_GA
        expected_hs: List[float] = []

        for i in range(len(wf)):
            # Snapshot h BEFORE updating with match i
            exp_h = ew_home / ew_away if ew_away > 0.0 else 1.0
            expected_hs.append(exp_h)
            # Update after snapshot (post-match)
            fthg = float(wf["fthg"].iloc[i])
            ftag = float(wf["ftag"].iloc[i])
            if math.isfinite(fthg) and math.isfinite(ftag):
                ew_home += ALPHA * (fthg - ew_home)
                ew_away += ALPHA * (ftag - ew_away)

        for i, (stored_h, exp_h) in enumerate(zip(result["h"].tolist(), expected_hs)):
            assert abs(stored_h - exp_h) < 1e-12, (
                f"Future-leak assertion failed at row {i}: "
                f"stored h={stored_h:.10f}, ground-truth h={exp_h:.10f}"
            )

    def test_no_future_leak_longer(self):
        """Same leak test with a longer 20-match synthetic corpus."""
        import random
        rng = random.Random(42)
        rows: list[tuple] = []
        teams = ["T1", "T2", "T3", "T4"]
        for k in range(20):
            date = f"2024-{(k // 4) + 1:02d}-{(k % 4) * 7 + 1:02d}"
            h, a = rng.sample(teams, 2)
            fthg = rng.randint(0, 4)
            ftag = rng.randint(0, 3)
            rows.append((date, "E0", h, a, fthg, ftag))

        df = _make_df(rows)
        result = walk_forward_hfa(df)

        from domains.soccer.ratings import walk_forward_goals
        wf = walk_forward_goals(df)

        ew_home = PRIOR_GF
        ew_away = PRIOR_GA

        for i in range(len(wf)):
            exp_h = ew_home / ew_away if ew_away > 0.0 else 1.0
            stored_h = float(result["h"].iloc[i])
            assert abs(stored_h - exp_h) < 1e-12, (
                f"Leak at row {i}: stored={stored_h:.12f}, expected={exp_h:.12f}"
            )
            fthg = float(wf["fthg"].iloc[i])
            ftag = float(wf["ftag"].iloc[i])
            if math.isfinite(fthg) and math.isfinite(ftag):
                ew_home += ALPHA * (fthg - ew_home)
                ew_away += ALPHA * (ftag - ew_away)


# ---------------------------------------------------------------------------
# 3. Mass-preserving
# ---------------------------------------------------------------------------


class TestMassPreserving:
    def test_mass_preserving_synthetic(self):
        """lam_home_adj * lam_away_adj == lam_home_base * lam_away_base (float tol 1e-12)."""
        result = walk_forward_hfa(MATCHES_6)
        for i, row in result.iterrows():
            base_product = float(row["lam_home_base"]) * float(row["lam_away_base"])
            adj_product = float(row["lam_home_adj"]) * float(row["lam_away_adj"])
            assert abs(adj_product - base_product) < 1e-12, (
                f"Mass not preserved at row {i}: "
                f"base_product={base_product:.12f}, adj_product={adj_product:.12f}"
            )

    def test_mass_preserving_first_row(self):
        """When h=1.0 (first match), adj == base exactly."""
        single = _make_df([("2024-01-01", "E0", "H", "A", 1, 0)])
        result = walk_forward_hfa(single)
        row = result.iloc[0]
        assert row["h"] == 1.0
        assert row["lam_home_adj"] == row["lam_home_base"]
        assert row["lam_away_adj"] == row["lam_away_base"]

    @real_data
    def test_mass_preserving_real_data(self, real_hfa):
        """Mass is preserved across all rows of the real corpus."""
        base_product = real_hfa["lam_home_base"] * real_hfa["lam_away_base"]
        adj_product = real_hfa["lam_home_adj"] * real_hfa["lam_away_adj"]
        diff = (adj_product - base_product).abs()
        assert diff.max() < 1e-10, (
            f"Mass not preserved: max |diff|={diff.max():.2e} at index {diff.idxmax()}"
        )


# ---------------------------------------------------------------------------
# 4. Median h > 1.0 after warmup (real data)
# ---------------------------------------------------------------------------


class TestHGt1WithRealData:
    @real_data
    def test_h_gt1_median_after_warmup(self, real_hfa):
        """After 20-match warmup, median h > 1.0 (home advantage is real)."""
        h_after_warmup = real_hfa["h"].values[20:]
        import numpy as np
        median_h = float(np.median(h_after_warmup))
        assert median_h > 1.0, (
            f"Expected median h > 1.0 after warmup (home advantage), got {median_h:.4f}. "
            "The HFA correction has no effect if h <= 1.0."
        )

    @real_data
    def test_h_converges_near_empirical_ratio(self, real_hfa):
        """Final h should be within a reasonable range of the empirical ratio."""
        import numpy as np
        # Empirical home/away means from real corpus
        df = pd.read_parquet(_PARQUET)
        emp_h = float(df["fthg"].mean()) / float(df["ftag"].mean())

        # h should converge toward the empirical ratio; check final 10% of corpus
        n = len(real_hfa)
        tail_h = real_hfa["h"].values[n * 9 // 10:]
        median_tail = float(np.median(tail_h))
        # Should be within 30% of empirical ratio
        assert 0.7 * emp_h <= median_tail <= 1.3 * emp_h, (
            f"Final h={median_tail:.4f} not within 30% of empirical ratio {emp_h:.4f}"
        )


# ---------------------------------------------------------------------------
# 5. lam_home_adj > lam_home_base when h > 1
# ---------------------------------------------------------------------------


class TestHomeAdjGtBase:
    def test_home_adj_gt_base_when_h_gt1(self):
        """For all rows where h > 1, lam_home_adj > lam_home_base."""
        result = walk_forward_hfa(MATCHES_6)
        for i, row in result.iterrows():
            h = float(row["h"])
            if h > 1.0:
                lh_base = float(row["lam_home_base"])
                lh_adj = float(row["lam_home_adj"])
                assert lh_adj > lh_base, (
                    f"Row {i}: h={h:.4f}>1 but lam_home_adj={lh_adj:.6f} "
                    f"<= lam_home_base={lh_base:.6f}"
                )

    def test_away_adj_lt_base_when_h_gt1(self):
        """For all rows where h > 1, lam_away_adj < lam_away_base."""
        result = walk_forward_hfa(MATCHES_6)
        for i, row in result.iterrows():
            h = float(row["h"])
            if h > 1.0:
                la_base = float(row["lam_away_base"])
                la_adj = float(row["lam_away_adj"])
                assert la_adj < la_base, (
                    f"Row {i}: h={h:.4f}>1 but lam_away_adj={la_adj:.6f} "
                    f">= lam_away_base={la_base:.6f}"
                )

    def test_symmetry_at_h_equals_one(self):
        """When h=1 (first match), adj == base for both sides."""
        result = walk_forward_hfa(MATCHES_6)
        first = result.iloc[0]
        assert first["h"] == 1.0
        assert first["lam_home_adj"] == first["lam_home_base"]
        assert first["lam_away_adj"] == first["lam_away_base"]

    @real_data
    def test_home_adj_gt_base_real_data(self, real_hfa):
        """On real data, rows with h>1 always have lam_home_adj > lam_home_base."""
        gt1 = real_hfa[real_hfa["h"] > 1.0]
        assert (gt1["lam_home_adj"] > gt1["lam_home_base"]).all(), (
            "Some rows with h>1 have lam_home_adj <= lam_home_base"
        )

    @real_data
    def test_away_adj_lt_base_real_data(self, real_hfa):
        """On real data, rows with h>1 always have lam_away_adj < lam_away_base."""
        gt1 = real_hfa[real_hfa["h"] > 1.0]
        assert (gt1["lam_away_adj"] < gt1["lam_away_base"]).all(), (
            "Some rows with h>1 have lam_away_adj >= lam_away_base"
        )


# ---------------------------------------------------------------------------
# 6. Output schema
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_required_columns_present(self):
        """Output must contain all required columns."""
        result = walk_forward_hfa(MATCHES_6)
        required = {"event_id", "date", "h", "lam_home_base", "lam_away_base",
                    "lam_home_adj", "lam_away_adj"}
        missing = required - set(result.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_row_count_matches_input(self):
        """Output has same number of rows as input."""
        result = walk_forward_hfa(MATCHES_6)
        assert len(result) == len(MATCHES_6)

    def test_all_lambdas_positive(self):
        """All lambda values must be strictly positive."""
        result = walk_forward_hfa(MATCHES_6)
        assert (result["lam_home_base"] > 0).all()
        assert (result["lam_away_base"] > 0).all()
        assert (result["lam_home_adj"] > 0).all()
        assert (result["lam_away_adj"] > 0).all()

    def test_h_positive(self):
        """h must be strictly positive."""
        result = walk_forward_hfa(MATCHES_6)
        assert (result["h"] > 0).all()
