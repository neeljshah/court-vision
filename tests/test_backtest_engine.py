"""
test_backtest_engine.py — Contract tests for src/prediction/prop_backtester.py.

All tests are deterministic: they never depend on data files existing
or their contents. Monkeypatching is used to isolate file I/O.
"""
import pytest

from src.prediction import prop_backtester
from src.prediction.prop_backtester import (
    STATS,
    VALIDATION_MIN_BETS,
    VALIDATION_MIN_ROI,
    BacktestResult,
    backtest_all_stats,
    backtest_props,
    load_historical_results,
    validation_gate,
)

_EXPECTED_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}

# ---------------------------------------------------------------------------
# 1. Module constants
# ---------------------------------------------------------------------------

def test_stats_constant():
    assert set(STATS) == _EXPECTED_STATS


def test_validation_constants():
    assert VALIDATION_MIN_ROI == 0.03
    assert VALIDATION_MIN_BETS == 50


# ---------------------------------------------------------------------------
# 2. BacktestResult dataclass
# ---------------------------------------------------------------------------

def test_backtest_result_dataclass():
    r = BacktestResult(
        stat="pts",
        seasons=["2024-25"],
        n_predictions=100,
        n_bets=60,
        wins=35,
        losses=25,
        win_rate=0.583,
        roi_pct=4.5,
        mae=2.1,
        avg_edge=0.07,
    )
    assert r.stat == "pts"
    assert r.seasons == ["2024-25"]
    assert r.n_predictions == 100
    assert r.n_bets == 60
    assert r.wins == 35
    assert r.losses == 25
    assert r.win_rate == 0.583
    assert r.roi_pct == 4.5
    assert r.mae == 2.1
    assert r.avg_edge == 0.07
    # defaults
    assert r.edge_buckets == {}
    assert r.passed_gate is False


# ---------------------------------------------------------------------------
# 3. load_historical_results smoke test
# ---------------------------------------------------------------------------

def test_load_historical_results_returns_list():
    result = load_historical_results()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 4. backtest_props — empty data path
# ---------------------------------------------------------------------------

def test_backtest_props_empty_data(monkeypatch):
    monkeypatch.setattr(prop_backtester, "load_historical_results", lambda *a, **k: [])

    r = backtest_props(stat="pts")

    assert isinstance(r, BacktestResult)
    assert r.stat == "pts"
    assert r.n_predictions == 0
    assert r.n_bets == 0
    assert r.passed_gate is False


# ---------------------------------------------------------------------------
# 5. backtest_props — synthetic winning bets
# ---------------------------------------------------------------------------

def test_backtest_props_counts_bets(monkeypatch):
    # predicted=110 > line=100 → edge=0.10 > default 0.04 → bet placed as over
    # actual=120 > line=100 → win
    synthetic = [
        {"stat": "pts", "predicted": 110.0, "actual": 120.0, "line": 100.0},
        {"stat": "pts", "predicted": 110.0, "actual": 120.0, "line": 100.0},
        {"stat": "pts", "predicted": 110.0, "actual": 120.0, "line": 100.0},
    ]
    monkeypatch.setattr(prop_backtester, "load_historical_results", lambda *a, **k: synthetic)
    # suppress file-write side effect
    monkeypatch.setattr(prop_backtester, "_save_backtest", lambda r: None)

    r = backtest_props(stat="pts")

    assert r.n_predictions == 3
    assert r.n_bets == 3
    assert r.wins == 3
    assert r.win_rate == 1.0
    # n_bets=3 < VALIDATION_MIN_BETS=50 → gate must stay False
    assert r.passed_gate is False


# ---------------------------------------------------------------------------
# 6. backtest_all_stats — covers all 7 stats
# ---------------------------------------------------------------------------

def test_backtest_all_stats_covers_all(monkeypatch):
    monkeypatch.setattr(prop_backtester, "load_historical_results", lambda *a, **k: [])
    monkeypatch.setattr(prop_backtester, "_save_backtest", lambda r: None)

    results = backtest_all_stats()

    assert set(results.keys()) == _EXPECTED_STATS
    for stat, r in results.items():
        assert isinstance(r, BacktestResult), f"{stat} did not return a BacktestResult"


# ---------------------------------------------------------------------------
# 7. validation_gate — returns False when cache file is absent
# ---------------------------------------------------------------------------

def test_validation_gate_false_when_no_cache(monkeypatch, tmp_path):
    # Point _RESULTS_CACHE at a path that does not exist
    monkeypatch.setattr(
        prop_backtester, "_RESULTS_CACHE", str(tmp_path / "nonexistent.json")
    )
    assert validation_gate("pts") is False
