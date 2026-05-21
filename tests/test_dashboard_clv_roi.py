"""Tests for CLV beat-rate and model ROI dashboard page logic."""
import importlib
import sys
import types

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Shared import helper (mirrors test_dashboard_pages.py pattern)
# ---------------------------------------------------------------------------

class _NullCtx:
    """Minimal context manager / attribute sink."""
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __getattr__(self, name): return lambda *a, **kw: None


def _make_st_stub() -> types.ModuleType:
    st = types.ModuleType("streamlit")
    st.set_page_config = lambda **_kw: None
    st.title = lambda *a, **kw: None
    st.subheader = lambda *a, **kw: None
    st.info = lambda *a, **kw: None
    st.dataframe = lambda *a, **kw: None
    st.metric = lambda *a, **kw: None
    st.columns = lambda n: [_NullCtx() for _ in range(n)]
    st.cache_data = lambda ttl=None: (lambda f: f)
    return st


def _import_logic(module_rel: str, func_names: list) -> dict:
    """Import specific functions from a dashboard page by patching streamlit."""
    st_stub = _make_st_stub()
    old_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = st_stub
    try:
        if module_rel in sys.modules:
            del sys.modules[module_rel]
        mod = importlib.import_module(module_rel)
        return {fn: getattr(mod, fn) for fn in func_names}
    finally:
        if old_st is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_st
        sys.modules.pop(module_rel, None)


# ---------------------------------------------------------------------------
# Test 1 — _compute_beat_rate returns empty df for empty input
# ---------------------------------------------------------------------------

def test_clv_beat_rate_empty():
    """_compute_beat_rate(pd.DataFrame()) returns an empty DataFrame."""
    fns = _import_logic("apps.dashboards.pages.clv_beat_rate", ["_compute_beat_rate"])
    _compute_beat_rate = fns["_compute_beat_rate"]

    result = _compute_beat_rate(pd.DataFrame())
    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ---------------------------------------------------------------------------
# Test 2 — _compute_beat_rate groups by stat correctly
# ---------------------------------------------------------------------------

def test_clv_beat_rate_by_stat():
    """_compute_beat_rate groups by stat and computes beat_rate correctly."""
    fns = _import_logic("apps.dashboards.pages.clv_beat_rate", ["_compute_beat_rate"])
    _compute_beat_rate = fns["_compute_beat_rate"]

    df = pd.DataFrame({
        "stat": ["pts", "pts", "pts", "reb", "reb"],
        "clv":  [0.02, -0.01, 0.03, 0.01, 0.01],
    })

    result = _compute_beat_rate(df, group_col="stat")

    assert not result.empty
    assert "beat_rate" in result.columns
    assert "n" in result.columns
    assert "mean_clv" in result.columns

    pts_row = result[result["stat"] == "pts"].iloc[0]
    assert pts_row["n"] == 3
    # 2 out of 3 pts bets beat (0.02 and 0.03 > 0; -0.01 not)
    assert pts_row["beat_rate"] == pytest.approx(2 / 3)

    reb_row = result[result["stat"] == "reb"].iloc[0]
    assert reb_row["n"] == 2
    assert reb_row["beat_rate"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 3 — _compute_roi returns empty df for empty input
# ---------------------------------------------------------------------------

def test_model_roi_empty():
    """_compute_roi(pd.DataFrame()) returns an empty DataFrame."""
    fns = _import_logic("apps.dashboards.pages.model_roi", ["_compute_roi"])
    _compute_roi = fns["_compute_roi"]

    result = _compute_roi(pd.DataFrame())
    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ---------------------------------------------------------------------------
# Test 4 — _compute_roi groups by stat and computes ROI correctly
# ---------------------------------------------------------------------------

def test_model_roi_groupby_stat():
    """_compute_roi groups by stat and computes total_pnl / roi_pct per stat."""
    fns = _import_logic("apps.dashboards.pages.model_roi", ["_compute_roi"])
    _compute_roi = fns["_compute_roi"]

    df = pd.DataFrame({
        "stat": ["pts", "pts", "reb", "reb", "reb"],
        "pnl":  [100.0, -50.0, 80.0, 80.0, -20.0],
    })

    result = _compute_roi(df)

    assert not result.empty
    assert "stat" in result.columns
    assert "n_bets" in result.columns
    assert "total_pnl" in result.columns
    assert "roi_pct" in result.columns
    assert "win_rate" in result.columns

    pts_row = result[result["stat"] == "pts"].iloc[0]
    assert pts_row["n_bets"] == 2
    assert pts_row["total_pnl"] == pytest.approx(50.0)
    # ROI = 50 / (2 * 100) * 100 = 25%
    assert pts_row["roi_pct"] == pytest.approx(25.0)
    assert pts_row["win_rate"] == pytest.approx(0.5)

    reb_row = result[result["stat"] == "reb"].iloc[0]
    assert reb_row["n_bets"] == 3
    assert reb_row["total_pnl"] == pytest.approx(140.0)
    # ROI = 140 / (3 * 100) * 100 ≈ 46.67%
    assert reb_row["roi_pct"] == pytest.approx(140 / 300 * 100)
