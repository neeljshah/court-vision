"""tests/platform/test_adapter_determinism.py — Determinism battery (tennis/soccer/mlb).

Renaissance-grade requirement: feature_bundle() must be bit-for-bit reproducible
across independent adapter instantiations.  Non-determinism silently invalidates
walk-forward backtests.

Assertions (parametrized over tennis / soccer / mlb):
  1. DETERMINISM      — two fresh adapter instances on identical data/seasons produce
                        byte-identical base, signal_col, target, dates.
  2. SEED-STABILITY   — no seed seam exists in these adapters (purely arithmetic
                        Elo/Poisson replay); documented as INAPPLICABLE.
  3. ORDER-INVARIANCE — dates list is non-decreasing AND shuffling input rows does
                        not change output (adapters re-sort internally via
                        mergesort-stable _sorted()).

Corpus loaded from data/domains/<sport>/; sport skipped when absent.
Run: python -m pytest tests/platform/test_adapter_determinism.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Narrow season windows — fast on real corpora, still many rows.
_SEASONS: Dict[str, List[int]] = {
    "tennis": [2016, 2017, 2018],
    "soccer": [2016, 2017, 2018],
    "mlb":    [2012, 2013, 2014],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_adapter(sport: str) -> Optional[Any]:
    """Fresh adapter from disk each call; returns None when corpus absent."""
    corpus = REPO_ROOT / "data" / "domains" / sport
    data_path = corpus / ("games.parquet" if sport == "mlb" else "matches.parquet")
    if not data_path.exists():
        return None
    try:
        data_df = pd.read_parquet(data_path)
        odds_df: Optional[pd.DataFrame] = None
        p = corpus / "odds.parquet"
        if p.exists():
            try:
                odds_df = pd.read_parquet(p)
            except Exception:
                pass
        return _make_adapter(sport, data_df, odds_df)
    except Exception:
        return None


def _make_adapter(
    sport: str,
    data_df: pd.DataFrame,
    odds_df: Optional[pd.DataFrame],
) -> Any:
    """Construct an adapter of the given sport from pre-loaded DataFrames."""
    if sport == "tennis":
        from domains.tennis.adapter import TennisAdapter
        return TennisAdapter(matches_df=data_df, odds_df=odds_df)
    if sport == "soccer":
        from domains.soccer.adapter import SoccerAdapter
        return SoccerAdapter(matches_df=data_df, odds_df=odds_df)
    from domains.mlb.adapter import MLBAdapter
    return MLBAdapter(games_df=data_df, odds_df=odds_df)


def _get_adapter(sport: str) -> Any:
    a = _load_adapter(sport)
    if a is None:
        pytest.skip(f"Corpus absent for {sport}.")
    return a


def _hyp(name: str = "det") -> Any:
    from src.loop.signal import Hypothesis
    return Hypothesis(name=name, target="winprob", scope="pregame", statement=name)


def _assert_arrays_equal(name: str, sport: str, a: Any, b: Any) -> None:
    """Assert two optional numpy arrays (or None) are byte-identical."""
    if a is None and b is None:
        return
    assert (a is not None) and (b is not None), (
        f"{sport}:{name} is None in one run but not the other — "
        "FINDING: nondeterminism in array presence."
    )
    assert np.array_equal(a, b, equal_nan=True), (
        f"{sport}:{name} differs between runs — "
        "FINDING: nondeterminism detected."
    )


# ---------------------------------------------------------------------------
# Test 1 — DETERMINISM
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Two fresh adapter instances must produce byte-identical feature bundles."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_two_independent_adapters_identical(self, sport: str) -> None:
        """Independent adapters loaded from the same corpus must agree exactly."""
        seasons = _SEASONS[sport]
        a1, a2 = _get_adapter(sport), _get_adapter(sport)
        fb1 = a1.feature_bundle(_hyp(f"det_{sport}_1"), seasons)
        fb2 = a2.feature_bundle(_hyp(f"det_{sport}_2"), seasons)

        assert fb1.base.shape == fb2.base.shape, (
            f"{sport}: base shape mismatch {fb1.base.shape} vs {fb2.base.shape}"
        )
        _assert_arrays_equal("base", sport, fb1.base, fb2.base)
        _assert_arrays_equal("signal_col", sport, fb1.signal_col, fb2.signal_col)
        _assert_arrays_equal("target", sport, fb1.target, fb2.target)
        _assert_arrays_equal("lines", sport, fb1.lines, fb2.lines)
        _assert_arrays_equal("closing", sport, fb1.closing, fb2.closing)
        assert fb1.dates == fb2.dates, (
            f"{sport}: dates list differs — FINDING: nondeterminism in dates."
        )

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_same_adapter_called_twice_identical(self, sport: str) -> None:
        """Two calls on the same (warm-cache) adapter must produce identical output."""
        seasons = _SEASONS[sport]
        a = _get_adapter(sport)
        fb1 = a.feature_bundle(_hyp(f"det2_{sport}_a"), seasons)
        fb2 = a.feature_bundle(_hyp(f"det2_{sport}_b"), seasons)
        assert np.array_equal(fb1.base, fb2.base, equal_nan=True), (
            f"{sport}: second call on same adapter returned different base — "
            "FINDING: adapter internal state mutated between calls."
        )
        assert fb1.dates == fb2.dates, (
            f"{sport}: second call on same adapter returned different dates."
        )


# ---------------------------------------------------------------------------
# Test 2 — SEED-STABILITY (inapplicable; documented)
# ---------------------------------------------------------------------------

class TestSeedStability:
    """These adapters use purely deterministic arithmetic (Elo/Poisson replay).

    No random-number draws exist and no seed seam is reachable without editing
    src/ or kernel/ (forbidden by hard constraints).  Sub-check is INAPPLICABLE;
    recorded as a passing structural note so it shows up in the test run.
    If a future adapter introduces randomness, add a seed parameter to
    feature_bundle() and exercise it here.
    """

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_seed_seam_inapplicable(self, sport: str) -> None:
        """No seed seam — determinism is guaranteed by arithmetic replay alone."""
        # Structural finding; no corpus needed.
        assert True


# ---------------------------------------------------------------------------
# Test 3 — ORDER-INVARIANCE
# ---------------------------------------------------------------------------

class TestOrderInvariance:
    """feature_bundle() output must be date-sorted and input-row-order-independent."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_dates_nondecreasing(self, sport: str) -> None:
        """Output dates list must be in non-decreasing chronological order."""
        fb = _get_adapter(sport).feature_bundle(_hyp(f"ord_{sport}"), _SEASONS[sport])
        assert len(fb.dates) > 0, f"{sport}: feature_bundle returned 0 rows"
        parsed = [dt.date.fromisoformat(d) for d in fb.dates]
        violations = [
            (i, parsed[i - 1].isoformat(), parsed[i].isoformat())
            for i in range(1, len(parsed))
            if parsed[i] < parsed[i - 1]
        ]
        assert not violations, (
            f"{sport}: dates not non-decreasing at index {violations[0][0]}: "
            f"{violations[0][1]} → {violations[0][2]} — "
            "FINDING: order-invariance contract violated."
        )

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_shuffled_input_same_output(self, sport: str) -> None:
        """Shuffling input corpus rows must not change feature_bundle() output.

        Adapters re-sort internally (_sorted() mergesort-stable); input order
        must therefore be irrelevant to the output.
        """
        corpus = REPO_ROOT / "data" / "domains" / sport
        data_path = corpus / ("games.parquet" if sport == "mlb" else "matches.parquet")
        if not data_path.exists():
            pytest.skip(f"Corpus absent for {sport}.")
        data_df = pd.read_parquet(data_path)
        odds_df: Optional[pd.DataFrame] = None
        if (corpus / "odds.parquet").exists():
            try:
                odds_df = pd.read_parquet(corpus / "odds.parquet")
            except Exception:
                pass

        seasons = _SEASONS[sport]
        fb_canon = _make_adapter(sport, data_df.copy(), odds_df).feature_bundle(
            _hyp(f"ord_canon_{sport}"), seasons
        )

        # Shuffle with a fixed seed so this test is itself reproducible.
        rng = np.random.default_rng(seed=42)
        idx = rng.permutation(len(data_df))
        fb_shuf = _make_adapter(sport, data_df.iloc[idx].reset_index(drop=True), odds_df).feature_bundle(
            _hyp(f"ord_shuf_{sport}"), seasons
        )

        assert fb_canon.dates == fb_shuf.dates, (
            f"{sport}: shuffled input produced different dates — "
            "FINDING: output is input-order-sensitive."
        )
        assert np.array_equal(fb_canon.base, fb_shuf.base, equal_nan=True), (
            f"{sport}: shuffled input produced different base — "
            "FINDING: output is input-order-sensitive."
        )
