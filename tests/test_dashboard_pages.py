"""Tests for dashboard page logic (bets_today and bankroll)."""
import importlib
import os
import sys
import textwrap
import tempfile

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Import helpers — load the pure-logic functions without triggering Streamlit
# ---------------------------------------------------------------------------

def _import_logic(module_rel: str, func_names: list) -> dict:
    """Import specific functions from a dashboard page by patching streamlit."""
    # Provide a minimal streamlit stub so module-level st.* calls don't fail
    import types

    st_stub = types.ModuleType("streamlit")
    st_stub.set_page_config = lambda **_kw: None
    st_stub.title = lambda *a, **kw: None
    st_stub.info = lambda *a, **kw: None
    st_stub.dataframe = lambda *a, **kw: None
    st_stub.metric = lambda *a, **kw: None
    st_stub.columns = lambda n: [_NullCtx() for _ in range(n)]
    st_stub.plotly_chart = lambda *a, **kw: None
    # cache_data: return the function unchanged
    st_stub.cache_data = lambda ttl=None: (lambda f: f)

    # Also stub plotly so bankroll module doesn't require it at import time
    import types as _t
    plotly_stub = _t.ModuleType("plotly")
    plotly_stub.graph_objects = _t.ModuleType("plotly.graph_objects")

    class _FigStub:
        def add_trace(self, *a, **kw): pass
        def update_layout(self, **kw): pass

    class _ScatterStub:
        def __init__(self, *a, **kw): pass

    class _BarStub:
        def __init__(self, *a, **kw): pass

    plotly_stub.graph_objects.Figure = _FigStub
    plotly_stub.graph_objects.Scatter = _ScatterStub
    plotly_stub.graph_objects.Bar = _BarStub

    old_st = sys.modules.get("streamlit")
    old_plotly = sys.modules.get("plotly")
    old_go = sys.modules.get("plotly.graph_objects")
    sys.modules["streamlit"] = st_stub
    sys.modules["plotly"] = plotly_stub
    sys.modules["plotly.graph_objects"] = plotly_stub.graph_objects

    try:
        # Force re-import every time so module-level st calls use our stub
        if module_rel in sys.modules:
            del sys.modules[module_rel]
        mod = importlib.import_module(module_rel)
        return {fn: getattr(mod, fn) for fn in func_names}
    finally:
        # Restore
        if old_st is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_st
        if old_plotly is None:
            sys.modules.pop("plotly", None)
        else:
            sys.modules["plotly"] = old_plotly
        if old_go is None:
            sys.modules.pop("plotly.graph_objects", None)
        else:
            sys.modules["plotly.graph_objects"] = old_go
        # Remove the dashboard module so it doesn't pollute other tests
        sys.modules.pop(module_rel, None)


class _NullCtx:
    """Minimal context manager that ignores attribute access."""
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __getattr__(self, name): return lambda *a, **kw: None


# ---------------------------------------------------------------------------
# Test 1 — bets_today module imports
# ---------------------------------------------------------------------------

def test_bets_today_module_imports():
    """apps.dashboards.pages.bets_today is importable and exposes load_bets_for_date."""
    fns = _import_logic("apps.dashboards.pages.bets_today", ["load_bets_for_date"])
    assert callable(fns["load_bets_for_date"])


# ---------------------------------------------------------------------------
# Test 2 — bankroll module imports
# ---------------------------------------------------------------------------

def test_bankroll_module_imports():
    """apps.dashboards.pages.bankroll is importable and exposes compute_bankroll_series."""
    fns = _import_logic("apps.dashboards.pages.bankroll", ["compute_bankroll_series"])
    assert callable(fns["compute_bankroll_series"])


# ---------------------------------------------------------------------------
# Test 3 — load_bets returns empty df when ledger is missing
# ---------------------------------------------------------------------------

def test_load_bets_empty_when_no_ledger():
    """load_bets_for_date returns empty DataFrame when the ledger file does not exist."""
    fns = _import_logic("apps.dashboards.pages.bets_today", ["load_bets_for_date"])
    load_bets_for_date = fns["load_bets_for_date"]

    result = load_bets_for_date("/nonexistent/path/bet_ledger.csv", "2026-05-21")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ---------------------------------------------------------------------------
# Test 4 — compute_bankroll_series computes HWM correctly
# ---------------------------------------------------------------------------

def test_load_bankroll_computes_hwm():
    """compute_bankroll_series produces hwm == cummax(bankroll) over synthetic data."""
    fns = _import_logic("apps.dashboards.pages.bankroll", ["compute_bankroll_series"])
    compute_bankroll_series = fns["compute_bankroll_series"]

    csv_content = textwrap.dedent("""\
        date,player,pnl
        2026-05-01,LeBron James,50.0
        2026-05-02,Stephen Curry,-20.0
        2026-05-03,Kevin Durant,30.0
        2026-05-04,Giannis Antetokounmpo,-10.0
    """)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        tmp_path = f.name

    try:
        df = compute_bankroll_series(tmp_path, starting_bankroll=1000.0)
        assert not df.empty, "Expected non-empty DataFrame from synthetic data"
        assert "hwm" in df.columns
        assert "bankroll" in df.columns
        assert "cumulative_pnl" in df.columns
        assert "drawdown" in df.columns

        # HWM must equal cummax of bankroll
        expected_hwm = df["bankroll"].cummax().reset_index(drop=True)
        actual_hwm = df["hwm"].reset_index(drop=True)
        pd.testing.assert_series_equal(actual_hwm, expected_hwm, check_names=False)

        # Spot-check bankroll values
        assert df["bankroll"].iloc[0] == pytest.approx(1050.0)   # 1000 + 50
        assert df["bankroll"].iloc[1] == pytest.approx(1030.0)   # 1000 + 50 - 20
        assert df["bankroll"].iloc[2] == pytest.approx(1060.0)   # 1000 + 50 - 20 + 30
        assert df["bankroll"].iloc[3] == pytest.approx(1050.0)   # 1000 + 50 - 20 + 30 - 10
    finally:
        os.unlink(tmp_path)
