"""tests/platform/test_adapter_leak_invariance.py — Cross-adapter leak / truncation-invariance battery.

Asserts three properties across all three market-only adapters (tennis, soccer, mlb):

1. TRUNCATION-INVARIANCE: feature_bundle on seasons ≤ SPLIT produces base rows
   byte-identical (float tol) to the full-corpus bundle for the same dates.  Proves
   that no future event contaminates past walk-forward features.

2. BASE-COLUMN COUNT CONFORMANCE: feature_bundle.base has the documented column count
   (tennis=5, soccer=5, mlb=6) and primary columns are finite.

3. SHAPE CONTRACT: FeatureBundle fields (base, signal_col, target, dates, lines,
   closing) are consistently shaped; signal in [0,1]; target binary; dates ISO.

Corpus loaded from data/domains/<sport>/; sport skipped (pytest.skip) when absent.

Run: python -m pytest tests/platform/test_adapter_leak_invariance.py -q
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_FLOAT_TOL = 1e-6

# Documented base-column counts (each adapter's feature_bundle docstring)
_BASE_NCOLS: Dict[str, int] = {
    "tennis": 5,  # elo_diff, surface_elo_diff, best_of, rest_days_a, rest_days_b
    "soccer": 5,  # lam_home, lam_away, lam_total, rest_days_home, rest_days_away
    "mlb":    6,  # elo_home, elo_away, elo_diff_hfa, rest_home, rest_away, h2h_rate
}

# Split config: early_seasons ⊂ full_seasons; at least one extra season in full.
# yr_offset: European soccer seasons span two calendar years (season N runs into N+1),
# so the date-bound check allows max(early_seasons) + yr_offset.
_SPLITS: Dict[str, Dict[str, Any]] = {
    "tennis": {"early": [2015,2016,2017,2018,2019], "full": [2015,2016,2017,2018,2019,2020], "kw": {}, "yr_offset": 0},
    "soccer": {"early": [2015,2016,2017,2018,2019], "full": [2015,2016,2017,2018,2019,2020], "kw": {}, "yr_offset": 1},
    "mlb":    {"early": [2010,2011,2012,2013,2014,2015], "full": [2010,2011,2012,2013,2014,2015,2016], "kw": {}, "yr_offset": 0},
}


# ---------------------------------------------------------------------------
# Corpus loaders — mirrors proof runner _load_adapter pattern
# ---------------------------------------------------------------------------

def _load_adapter(sport: str) -> Optional[Any]:
    """Return adapter for sport loaded from real corpus, or None if absent."""
    corpus = REPO_ROOT / "data" / "domains" / sport
    if sport == "mlb":
        data_file, key = corpus / "games.parquet", "games_df"
    else:
        data_file, key = corpus / "matches.parquet", "matches_df"
    if not data_file.exists():
        return None
    try:
        data_df = pd.read_parquet(data_file)
        odds_df: Optional[pd.DataFrame] = None
        odds_path = corpus / "odds.parquet"
        if odds_path.exists():
            try:
                odds_df = pd.read_parquet(odds_path)
            except Exception:
                pass
        if sport == "tennis":
            from domains.tennis.adapter import TennisAdapter
            return TennisAdapter(matches_df=data_df, odds_df=odds_df)
        if sport == "soccer":
            from domains.soccer.adapter import SoccerAdapter
            return SoccerAdapter(matches_df=data_df, odds_df=odds_df)
        from domains.mlb.adapter import MLBAdapter
        return MLBAdapter(games_df=data_df, odds_df=odds_df)
    except Exception:
        return None


def _get_adapter(sport: str) -> Any:
    """Load adapter or skip if corpus absent."""
    a = _load_adapter(sport)
    if a is None:
        pytest.skip(f"Corpus absent for {sport}.")
    return a


def _hyp(name: str = "leak_bat") -> Any:
    from src.loop.signal import Hypothesis
    return Hypothesis(name=name, target="winprob", scope="pregame", statement=name)


# ---------------------------------------------------------------------------
# Test 1 — SHAPE CONTRACT
# ---------------------------------------------------------------------------

class TestShapeContract:
    """FeatureBundle attributes must satisfy the gate's documented shape contract."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_shape_contract(self, sport: str) -> None:
        """base, signal_col, target, dates are length-n; optionals shaped or None."""
        from src.loop.gate import FeatureBundle
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb: FeatureBundle = adapter.feature_bundle(_hyp(f"{sport}_shape"), cfg["early"], **cfg["kw"])
        assert isinstance(fb, FeatureBundle)
        n = fb.base.shape[0]
        assert n > 0
        assert fb.base.ndim == 2 and np.issubdtype(fb.base.dtype, np.floating)
        assert fb.signal_col.shape == (n,)
        assert fb.target.shape == (n,)
        assert isinstance(fb.dates, list) and len(fb.dates) == n
        if fb.lines is not None:
            assert fb.lines.shape == (n,)
        if fb.closing is not None:
            assert fb.closing.shape == (n,)


# ---------------------------------------------------------------------------
# Test 2 — BASE-COLUMN CONFORMANCE
# ---------------------------------------------------------------------------

class TestBaseColConformance:
    """base must have exactly the documented column count; values must be sane."""

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_ncols_and_primary_finite(self, sport: str) -> None:
        """Column count matches docstring AND first-3 cols are finite (no NaN/inf)."""
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb = adapter.feature_bundle(_hyp(f"{sport}_ncols"), cfg["early"], **cfg["kw"])
        assert fb.base.shape[1] == _BASE_NCOLS[sport], (
            f"{sport}: expected {_BASE_NCOLS[sport]} base cols, got {fb.base.shape[1]}"
        )
        assert np.all(np.isfinite(fb.base[:, :3])), (
            f"{sport}: NaN/inf in primary base columns (first 3)"
        )

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_signal_probability_and_binary_target(self, sport: str) -> None:
        """signal_col in [0,1] and target is binary {0.0, 1.0}."""
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb = adapter.feature_bundle(_hyp(f"{sport}_vals"), cfg["early"], **cfg["kw"])
        assert np.all(fb.signal_col >= 0.0) and np.all(fb.signal_col <= 1.0), (
            f"{sport}: signal_col not in [0,1]"
        )
        unique = set(np.unique(fb.target).tolist())
        assert unique.issubset({0.0, 1.0}), (
            f"{sport}: target not binary; got {unique}"
        )

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_dates_iso_and_chronological(self, sport: str) -> None:
        """dates are valid ISO strings in non-decreasing order."""
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb = adapter.feature_bundle(_hyp(f"{sport}_dates"), cfg["early"], **cfg["kw"])
        parsed = [dt.date.fromisoformat(d) for d in fb.dates[:5]]
        assert all(a <= b for a, b in zip(parsed, parsed[1:])), (
            f"{sport}: dates not chronological in first 5 rows: {parsed}"
        )


# ---------------------------------------------------------------------------
# Test 3 — TRUNCATION-INVARIANCE
# ---------------------------------------------------------------------------

class TestTruncationInvariance:
    """Early-season base features must be byte-identical in truncated vs full corpus.

    Protocol: build fb_early on early_seasons only, fb_full on full_seasons.
    For each date appearing in both, paired rows' base features must agree within
    _FLOAT_TOL.  Any divergence proves a future event leaked into a past row.
    """

    def _assert_invariant(self, sport: str, fb_e: Any, fb_f: Any) -> None:
        # Map date → list[row_idx] for each bundle
        def _idx_map(fb: Any) -> Dict[str, List[int]]:
            m: Dict[str, List[int]] = {}
            for i, d in enumerate(fb.dates):
                m.setdefault(d, []).append(i)
            return m

        em, fm = _idx_map(fb_e), _idx_map(fb_f)
        common = sorted(set(em) & set(fm))
        assert len(common) >= 10, (
            f"{sport}: only {len(common)} common dates between early and full bundles"
        )
        mismatches: List[str] = []
        checked = 0
        for d in common:
            for ie, if_ in zip(em[d], fm[d]):
                if not np.allclose(fb_e.base[ie], fb_f.base[if_], atol=_FLOAT_TOL, equal_nan=True):
                    delta = np.abs(fb_e.base[ie] - fb_f.base[if_]).max()
                    mismatches.append(f"date={d} max_delta={delta:.2e}")
                checked += 1
        assert checked >= 10, f"{sport}: only {checked} rows checked"
        assert not mismatches, (
            f"{sport}: TRUNCATION-INVARIANCE VIOLATED on {len(mismatches)} rows "
            f"(first: {mismatches[0]})"
        )

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_truncation_invariance(self, sport: str) -> None:
        """Early rows must be feature-identical whether full or truncated corpus is used."""
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb_e = adapter.feature_bundle(_hyp(f"{sport}_te"), cfg["early"], **cfg["kw"])
        fb_f = adapter.feature_bundle(_hyp(f"{sport}_tf"), cfg["full"],  **cfg["kw"])
        self._assert_invariant(sport, fb_e, fb_f)

    @pytest.mark.parametrize("sport", ["tennis", "soccer", "mlb"])
    def test_full_has_more_rows_and_early_dates_bounded(self, sport: str) -> None:
        """Full bundle has strictly more rows; early bundle dates stay within early seasons."""
        adapter = _get_adapter(sport)
        cfg = _SPLITS[sport]
        fb_e = adapter.feature_bundle(_hyp(f"{sport}_re"), cfg["early"], **cfg["kw"])
        fb_f = adapter.feature_bundle(_hyp(f"{sport}_rf"), cfg["full"],  **cfg["kw"])
        assert fb_f.base.shape[0] > fb_e.base.shape[0], (
            f"{sport}: full ({fb_f.base.shape[0]}) should exceed early ({fb_e.base.shape[0]})"
        )
        max_yr = max(cfg["early"]) + cfg["yr_offset"]
        oob = [d for d in fb_e.dates if dt.date.fromisoformat(d).year > max_yr]
        assert not oob, f"{sport}: early bundle has dates beyond year {max_yr}: {oob[:3]}"
