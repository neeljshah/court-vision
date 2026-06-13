"""tests/platform/test_nba_adapter.py — NBAAdapter unit + leak + interface tests.

Uses the real local corpus (skipped if absent).
(a) TRUNCATION-INVARIANCE: base rows byte-identical pre-T in truncated vs full.
(b) DETERMINISM: two identical builds produce identical FeatureBundle.
(c) BASE-COL CONTRACT: 8 cols; signal in (0,1); target binary; dates ascending.
(d) INTERFACE: adapter_interface_spec.check_adapter(NBAAdapter) → 0 FAILs.
(e) feature_bundle positional prefix == (hypothesis, seasons).
"""
from __future__ import annotations

import datetime as dt
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "data" / "domains" / "basketball_nba"
_FLOAT_TOL = 1e-6
EXPECTED_BASE_COLS = 8


def _hyp(name: str = "nba_test"):
    from src.loop.signal import Hypothesis
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


def _load_nba_adapter() -> Any:
    if not (CORPUS_DIR / "games.parquet").exists():
        pytest.skip("NBA corpus absent.")
    games_df = pd.read_parquet(CORPUS_DIR / "games.parquet")
    odds_df: Optional[pd.DataFrame] = None
    p = CORPUS_DIR / "odds.parquet"
    if p.exists():
        try:
            odds_df = pd.read_parquet(p)
        except Exception:
            pass
    from domains.basketball_nba.adapter import NBAAdapter
    return NBAAdapter(games_df=games_df, odds_df=odds_df)


def _seasons_list(games_df: pd.DataFrame) -> List[str]:
    return sorted(games_df["season"].unique().tolist())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adapter():
    return _load_nba_adapter()


@pytest.fixture(scope="module")
def games_df():
    if not (CORPUS_DIR / "games.parquet").exists():
        pytest.skip("NBA corpus absent.")
    return pd.read_parquet(CORPUS_DIR / "games.parquet")


@pytest.fixture(scope="module")
def bundle(adapter):
    return adapter.feature_bundle(_hyp("fixture_bundle"))


# ---------------------------------------------------------------------------
# (d) INTERFACE CONFORMANCE
# ---------------------------------------------------------------------------

class TestInterfaceConformance:
    def test_check_adapter_pass(self):
        from domains.basketball_nba.adapter import NBAAdapter
        from scripts.platformkit.adapter_interface_spec import check_adapter
        from scripts.platformkit.validate_adapter_types import Status
        fails = [r for r in check_adapter(NBAAdapter) if r.status == Status.FAIL]
        assert not fails, f"{len(fails)} interface FAIL(s): " + "; ".join(str(r) for r in fails)

    def test_sport_attr(self):
        from domains.basketball_nba.adapter import NBAAdapter
        assert NBAAdapter.sport == "basketball_nba"

    def test_required_methods(self):
        from domains.basketball_nba.adapter import NBAAdapter
        for m in ["list_events", "market_snapshot", "outcome",
                  "baseline_probability", "feature_bundle"]:
            assert callable(getattr(NBAAdapter, m, None)), f"method '{m}' missing"


# ---------------------------------------------------------------------------
# (e) feature_bundle positional prefix
# ---------------------------------------------------------------------------

def test_feature_bundle_positional_prefix():
    from domains.basketball_nba.adapter import NBAAdapter
    sig = inspect.signature(NBAAdapter.feature_bundle)
    pos = [n for n, p in sig.parameters.items()
           if n != "self"
           and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          inspect.Parameter.POSITIONAL_ONLY)]
    assert len(pos) >= 2 and pos[0] == "hypothesis" and pos[1] == "seasons", (
        f"Expected (hypothesis, seasons, ...) got {pos}")


# ---------------------------------------------------------------------------
# (c) BASE-COL CONTRACT
# ---------------------------------------------------------------------------

class TestBaseColContract:
    def test_base_shape(self, bundle):
        assert bundle.base.shape[1] == EXPECTED_BASE_COLS, \
            f"Expected {EXPECTED_BASE_COLS} base cols, got {bundle.base.shape[1]}"

    def test_base_dtype_float(self, bundle):
        assert np.issubdtype(bundle.base.dtype, np.floating)

    def test_elo_cols_finite(self, bundle):
        assert np.all(np.isfinite(bundle.base[:, :3])), "NaN/inf in Elo base cols"

    def test_signal_col_in_open_unit_interval(self, bundle):
        sc = bundle.signal_col
        assert np.all(sc > 0.0) and np.all(sc < 1.0), \
            f"signal_col not in (0,1): min={sc.min():.4f} max={sc.max():.4f}"

    def test_target_binary(self, bundle):
        unique = set(np.unique(bundle.target).tolist())
        assert unique.issubset({0.0, 1.0}), f"target not binary; got {unique}"

    def test_dates_chronological(self, bundle):
        parsed = [dt.date.fromisoformat(d) for d in bundle.dates]
        assert all(a <= b for a, b in zip(parsed, parsed[1:])), "dates not ascending"

    def test_lengths_consistent(self, bundle):
        n = bundle.base.shape[0]
        assert bundle.signal_col.shape == (n,)
        assert bundle.target.shape == (n,)
        assert len(bundle.dates) == n

    def test_b2b_cols_binary(self, bundle):
        for ci, name in [(5, "home_b2b"), (6, "away_b2b")]:
            u = set(np.unique(bundle.base[:, ci]).tolist())
            assert u.issubset({0.0, 1.0}), f"{name} col not binary; got {u}"

    def test_rolling_win10_in_unit_interval(self, bundle):
        col = bundle.base[:, 7]
        assert np.all(col >= 0.0) and np.all(col <= 1.0), \
            f"rolling_win10 out of [0,1]: min={col.min():.3f} max={col.max():.3f}"

    def test_rest_days_nonneg(self, bundle):
        for ci in (3, 4):
            col = bundle.base[:, ci]
            finite = col[np.isfinite(col)]
            assert np.all(finite >= 0.0), f"rest_days col {ci} has negatives"

    def test_first_row_elo_at_mean(self, adapter):
        from domains.basketball_nba.elo_config import ELO_MEAN
        b = adapter.feature_bundle(_hyp("first_row"))
        assert abs(b.base[0, 0] - ELO_MEAN) < 1.0, \
            f"First-row elo_home should be ~{ELO_MEAN}, got {b.base[0, 0]}"

    def test_invalid_season_raises(self, games_df):
        from domains.basketball_nba.adapter import NBAAdapter
        a = NBAAdapter(games_df=games_df.copy())
        with pytest.raises(ValueError, match="no rows"):
            a.feature_bundle(_hyp("empty"), seasons=["9999-99"])


# ---------------------------------------------------------------------------
# (b) DETERMINISM
# ---------------------------------------------------------------------------

def test_determinism(games_df):
    from domains.basketball_nba.adapter import NBAAdapter
    odds_df: Optional[pd.DataFrame] = None
    p = CORPUS_DIR / "odds.parquet"
    if p.exists():
        try:
            odds_df = pd.read_parquet(p)
        except Exception:
            pass
    a1 = NBAAdapter(games_df=games_df.copy(), odds_df=odds_df)
    a2 = NBAAdapter(games_df=games_df.copy(), odds_df=odds_df)
    fb1 = a1.feature_bundle(_hyp("det1"))
    fb2 = a2.feature_bundle(_hyp("det2"))
    assert np.array_equal(fb1.base, fb2.base, equal_nan=True), "base not deterministic"
    assert np.array_equal(fb1.signal_col, fb2.signal_col), "signal_col not deterministic"
    assert np.array_equal(fb1.target, fb2.target), "target not deterministic"
    assert fb1.dates == fb2.dates, "dates not deterministic"


# ---------------------------------------------------------------------------
# (a) TRUNCATION-INVARIANCE
# ---------------------------------------------------------------------------

class TestTruncationInvariance:
    def test_truncation_invariance(self, games_df):
        from domains.basketball_nba.adapter import NBAAdapter
        seasons = _seasons_list(games_df)
        if len(seasons) < 2:
            pytest.skip("Need >=2 seasons.")
        split = len(seasons) // 2
        odds_df: Optional[pd.DataFrame] = None
        p = CORPUS_DIR / "odds.parquet"
        if p.exists():
            try:
                odds_df = pd.read_parquet(p)
            except Exception:
                pass
        a_e = NBAAdapter(games_df=games_df.copy(), odds_df=odds_df)
        a_f = NBAAdapter(games_df=games_df.copy(), odds_df=odds_df)
        fb_e = a_e.feature_bundle(_hyp("trunc_e"), seasons=seasons[:split])
        fb_f = a_f.feature_bundle(_hyp("trunc_f"), seasons=seasons)
        assert fb_f.base.shape[0] > fb_e.base.shape[0], "full should have more rows"

        def _idx_map(fb) -> Dict[str, List[int]]:
            m: Dict[str, List[int]] = {}
            for i, d in enumerate(fb.dates):
                m.setdefault(d, []).append(i)
            return m

        em, fm = _idx_map(fb_e), _idx_map(fb_f)
        common = sorted(set(em) & set(fm))
        assert len(common) >= 5, f"Only {len(common)} common dates."
        mismatches: List[str] = []
        for d in common:
            for ie, if_ in zip(em[d], fm[d]):
                if not np.allclose(fb_e.base[ie], fb_f.base[if_],
                                   atol=_FLOAT_TOL, equal_nan=True):
                    delta = float(np.nanmax(np.abs(fb_e.base[ie] - fb_f.base[if_])))
                    mismatches.append(f"date={d} max_delta={delta:.2e}")
        assert not mismatches, (
            f"TRUNCATION-INVARIANCE VIOLATED on {len(mismatches)} rows "
            f"(first: {mismatches[0]})"
        )

    def test_early_dates_bounded(self, games_df):
        from domains.basketball_nba.adapter import NBAAdapter
        seasons = _seasons_list(games_df)
        if len(seasons) < 2:
            pytest.skip("Need >=2 seasons.")
        early = seasons[: len(seasons) // 2]
        a = NBAAdapter(games_df=games_df.copy())
        fb_e = a.feature_bundle(_hyp("date_bound"), seasons=early)
        max_year = max(int(s.split("-")[0]) + 1 for s in early)
        oob = [d for d in fb_e.dates if dt.date.fromisoformat(d).year > max_year]
        assert not oob, f"Early bundle has dates beyond year {max_year}: {oob[:3]}"


# ---------------------------------------------------------------------------
# NO-LEAK perturbation
# ---------------------------------------------------------------------------

def test_no_leak_perturbation(games_df):
    from domains.basketball_nba.adapter import NBAAdapter
    from domains.basketball_nba.ratings import _sorted as _ratings_sorted
    odds_df: Optional[pd.DataFrame] = None
    p = CORPUS_DIR / "odds.parquet"
    if p.exists():
        try:
            odds_df = pd.read_parquet(p)
        except Exception:
            pass
    adp = NBAAdapter(games_df=games_df.copy(), odds_df=odds_df)
    orig = adp.feature_bundle(_hyp("leak_orig"))
    n = orig.base.shape[0]
    assert n >= 2

    i = n - 1
    last_id = str(_ratings_sorted(games_df.copy()).iloc[-1]["game_id"])
    gmod = games_df.copy()
    matched = gmod[gmod["game_id"].astype(str) == last_id].index.tolist()
    assert len(matched) == 1
    g_idx = matched[0]
    gmod.at[g_idx, "home_win"] = 1.0 - float(gmod.at[g_idx, "home_win"])

    adp2 = NBAAdapter(games_df=gmod, odds_df=odds_df)
    pert = adp2.feature_bundle(_hyp("leak_pert"))
    assert pert.base.shape[0] == n
    assert orig.target[i] != pert.target[i], "Target did not change — test setup invalid"

    for j in range(i):
        assert np.array_equal(orig.base[j], pert.base[j], equal_nan=True), (
            f"NO-LEAK VIOLATED at j={j} date={orig.dates[j]}\n"
            f"  orig: {orig.base[j]}\n  pert: {pert.base[j]}"
        )
        assert orig.signal_col[j] == pert.signal_col[j], \
            f"NO-LEAK VIOLATED signal_col j={j}"
