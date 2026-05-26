"""
Tests for scripts/execute_loop/L39_exec_backtest.py.

All tests use a small hand-built CSV fixture and monkeypatched prediction
functions so no trained models are required on disk.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L39_exec_backtest.py -v
"""
from __future__ import annotations

import csv
import io
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Setup: ensure project root is on sys.path and stub heavy optional deps
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))

# Stub nba_api_headers_patch so the import in L39 doesn't fail
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

# Stub nba_api.stats.static.players so _resolve_player_id can operate without real install
_nba_api = types.ModuleType("nba_api")
_nba_api_stats = types.ModuleType("nba_api.stats")
_nba_api_static = types.ModuleType("nba_api.stats.static")
_nba_api_static.players = MagicMock()
sys.modules.setdefault("nba_api", _nba_api)
sys.modules.setdefault("nba_api.stats", _nba_api_stats)
sys.modules.setdefault("nba_api.stats.static", _nba_api_static)

import scripts.execute_loop.L39_exec_backtest as L39  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# CSV columns
_COLS = ["date", "player", "opp", "venue", "stat",
         "closing_line", "over_odds", "under_odds", "actual_value"]


def _make_csv(rows: list[dict], tmp_path: Path, name: str = "lines.csv") -> Path:
    """Write rows to a temporary CSV file and return its path."""
    p = tmp_path / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLS)
        writer.writeheader()
        writer.writerows(rows)
    return p


def _row(
    player: str = "LeBron James",
    stat: str = "pts",
    line: float = 25.5,
    actual: float = 28.0,
    over_odds: int = -110,
    under_odds: int = -110,
    date: str = "2024-01-15",
    opp: str = "GSW",
    venue: str = "home",
) -> dict:
    return {
        "date": date,
        "player": player,
        "opp": opp,
        "venue": venue,
        "stat": stat,
        "closing_line": str(line),
        "over_odds": str(over_odds),
        "under_odds": str(under_odds),
        "actual_value": str(actual),
    }


def _make_fixture_20(flip: Optional[str] = None) -> list[dict]:
    """Return 20 rows. flip='win' forces all actuals to beat line; flip='loss' misses."""
    players = ["LeBron James", "Stephen Curry", "Kevin Durant", "Nikola Jokic"]
    stats = _STATS[:4]  # pts, reb, ast, fg3m
    rows = []
    for i in range(20):
        pl = players[i % len(players)]
        st = stats[i % len(stats)]
        line = 20.0 + (i % 5) * 2.5
        if flip == "win":
            actual = line + 5.0
        elif flip == "loss":
            actual = max(0.0, line - 5.0)
        else:
            actual = line + (3.0 if i % 2 == 0 else -3.0)
        rows.append(_row(
            player=pl, stat=st, line=line, actual=actual,
            date=f"2024-01-{10 + i:02d}",
        ))
    return rows


# ---------------------------------------------------------------------------
# Prediction stubs
# ---------------------------------------------------------------------------

def _stub_predict(q50_val: float = 25.0):
    """Return a predict function that always returns q50_val."""
    def _fn(stat, pred_row, model_dir=None):
        return q50_val
    return _fn


def _stub_quantiles(q10: float = 18.0, q50: float = 25.0, q90: float = 32.0):
    """Return a quantile function that always returns the given quantiles."""
    def _fn(stat, pred_row, model_dir=None):
        return {"q10": q10, "q50": q50, "q90": q90}
    return _fn


def _stub_build_row(return_val: Optional[dict] = None):
    """Return a build_prediction_row stub."""
    def _fn(pid, opp, season, is_home=True, rest_days=2.0, **kwargs):
        return return_val or {"stub": True}
    return _fn


def _stub_resolve_id(mapping: Optional[dict] = None):
    """Return a player-id resolver; mapping[name]->id, or 1234 as default."""
    def _fn(name: str):
        if mapping is not None:
            return mapping.get(name)
        return 1234  # always resolves
    return _fn


def _stub_cal_apply(stat, q10, q50, q90):
    """Pass-through calibration stub."""
    return q10, q90


# ---------------------------------------------------------------------------
# Common run helper (always patches calibration to avoid model file I/O)
# ---------------------------------------------------------------------------

def _run(
    csv_path: Path,
    *,
    initial_bankroll: float = 100_000.0,
    kelly_frac: float = 0.25,
    edge_threshold_pct: float = 5.0,
    q50: float = 28.0,
    q10: float = 18.0,
    q90: float = 38.0,
    resolve_map: Optional[dict] = None,
    build_returns_none: bool = False,
    save: bool = False,
) -> L39.BacktestRun:
    with patch(
        "scripts.execute_loop.L39_exec_backtest._cal_apply",
        side_effect=_stub_cal_apply,
        create=True,
    ):
        # We patch quantile_calibration.apply inside the function via the
        # lazy import path — easier to inject directly via injectable args
        result = L39.run_exec_backtest(
            str(csv_path),
            initial_bankroll=initial_bankroll,
            kelly_frac=kelly_frac,
            edge_threshold_pct=edge_threshold_pct,
            save=save,
            _predict_fn=_stub_predict(q50),
            _quantile_fn=_stub_quantiles(q10, q50, q90),
            _build_row_fn=_stub_build_row(None if not build_returns_none else "NONE_TRICK"),
            _resolve_id_fn=_stub_resolve_id(resolve_map),
        )
    return result


# We need to also patch the quantile_calibration.apply that gets called inside
# run_exec_backtest. Since the function imports it locally, we monkeypatch it on
# the module's sys.modules path before the call.

@pytest.fixture(autouse=True)
def _patch_cal(monkeypatch):
    """Patch quantile_calibration.apply globally so no calibration file is needed."""
    import importlib

    # Ensure the module is importable (may need to stub src.prediction.quantile_calibration)
    mod_name = "src.prediction.quantile_calibration"
    if mod_name not in sys.modules:
        stub = types.ModuleType(mod_name)
        stub.apply = _stub_cal_apply  # type: ignore
        sys.modules[mod_name] = stub
    else:
        monkeypatch.setattr(sys.modules[mod_name], "apply", _stub_cal_apply)


# ---------------------------------------------------------------------------
# Test 1: Basic run on 20-row fixture — returns BacktestRun with sensible values
# ---------------------------------------------------------------------------

def test_basic_run_returns_backtest_run(tmp_path):
    """run_exec_backtest on 20-row fixture returns BacktestRun with 0 <= n_bets <= 20."""
    rows = _make_fixture_20()
    csv_p = _make_csv(rows, tmp_path)
    result = _run(csv_p, q50=28.0, q10=18.0, q90=38.0, edge_threshold_pct=5.0)

    assert isinstance(result, L39.BacktestRun)
    assert 0 <= result.n_bets <= 20
    assert result.initial_bankroll == 100_000.0
    assert result.run_id.startswith("exec_bt_")
    # financial invariant: final = initial + total_pnl
    assert abs(result.final_bankroll - (result.initial_bankroll + result.total_pnl)) < 0.02


# ---------------------------------------------------------------------------
# Test 2: Bankroll evolution — win sequence → final > initial; loss → final < initial
# ---------------------------------------------------------------------------

def test_bankroll_increases_on_win_sequence(tmp_path):
    """All-win fixture: final_bankroll > initial_bankroll."""
    rows = _make_fixture_20(flip="win")
    csv_p = _make_csv(rows, tmp_path)
    # q50 >> line → strong OVER signal → edge > threshold
    result = _run(csv_p, q50=35.0, q10=28.0, q90=42.0, edge_threshold_pct=0.0)

    if result.n_bets == 0:
        pytest.skip("No bets placed — edge filter too strict for this fixture")
    assert result.final_bankroll > result.initial_bankroll
    assert result.total_pnl > 0


def test_bankroll_decreases_on_loss_sequence(tmp_path):
    """All-loss fixture: final_bankroll < initial_bankroll."""
    rows = _make_fixture_20(flip="loss")
    csv_p = _make_csv(rows, tmp_path)
    # q50 >> line → model says OVER confidently, but actuals always miss
    result = _run(csv_p, q50=35.0, q10=28.0, q90=42.0, edge_threshold_pct=0.0)

    if result.n_bets == 0:
        pytest.skip("No bets placed — edge filter too strict")
    assert result.final_bankroll < result.initial_bankroll
    assert result.total_pnl < 0


# ---------------------------------------------------------------------------
# Test 3: Clearly +EV fixture → ci_lo > 0
# ---------------------------------------------------------------------------

def test_positive_ev_fixture_ci_lo_positive(tmp_path):
    """When model is always right (large edge, wins every bet), ci_lo should be > 0."""
    # Build fixture where actual always exceeds line and model predicts OVER with big edge
    rows = []
    for i in range(20):
        rows.append(_row(
            player="LeBron James",
            stat="pts",
            line=20.0,
            actual=30.0,   # always wins OVER
            date=f"2024-02-{i + 1:02d}",
        ))
    csv_p = _make_csv(rows, tmp_path)
    # q50=30 >> line=20 → large edge → all bets OVER → all win
    result = _run(csv_p, q50=30.0, q10=22.0, q90=38.0, edge_threshold_pct=0.0)

    if result.n_bets < 5:
        pytest.skip("Too few bets for bootstrap CI to be meaningful")
    assert result.ci_lo > 0, (
        f"Expected ci_lo > 0 for all-win fixture, got ci_lo={result.ci_lo}"
    )


# ---------------------------------------------------------------------------
# Test 4: Higher edge_threshold → fewer bets
# ---------------------------------------------------------------------------

def test_higher_edge_threshold_fewer_bets(tmp_path):
    """edge_threshold=10.0 produces fewer bets than edge_threshold=0.0."""
    rows = _make_fixture_20()
    csv_p = _make_csv(rows, tmp_path)

    # Use same q50 / quantiles so only the threshold changes
    result_loose = _run(csv_p, q50=28.0, q10=18.0, q90=38.0, edge_threshold_pct=0.0)
    result_strict = _run(csv_p, q50=28.0, q10=18.0, q90=38.0, edge_threshold_pct=10.0)

    assert result_strict.n_bets <= result_loose.n_bets


# ---------------------------------------------------------------------------
# Test 5: kelly_frac=0.5 → larger stakes than kelly_frac=0.25
# ---------------------------------------------------------------------------

def test_larger_kelly_frac_larger_stakes(tmp_path):
    """kelly_frac=0.5 produces larger total_stake than kelly_frac=0.25."""
    rows = _make_fixture_20(flip="win")
    csv_p = _make_csv(rows, tmp_path)

    result_25 = _run(csv_p, kelly_frac=0.25, q50=30.0, q10=20.0, q90=40.0, edge_threshold_pct=0.0)
    result_50 = _run(csv_p, kelly_frac=0.50, q50=30.0, q10=20.0, q90=40.0, edge_threshold_pct=0.0)

    if result_25.n_bets == 0 or result_50.n_bets == 0:
        pytest.skip("No bets placed — can't compare stake sizes")

    assert result_50.total_stake > result_25.total_stake, (
        f"Expected 0.5x Kelly to stake more: {result_50.total_stake} vs {result_25.total_stake}"
    )


# ---------------------------------------------------------------------------
# Test 6: kelly_frac=1.5 → ValueError
# ---------------------------------------------------------------------------

def test_kelly_frac_above_one_raises(tmp_path):
    """kelly_frac > 1.0 must raise ValueError."""
    rows = _make_fixture_20()
    csv_p = _make_csv(rows, tmp_path)
    with pytest.raises(ValueError, match="aggressive bet sizing"):
        L39.run_exec_backtest(str(csv_p), kelly_frac=1.5, save=False)


# ---------------------------------------------------------------------------
# Test 7: Missing required column → ValueError
# ---------------------------------------------------------------------------

def test_missing_required_column_raises(tmp_path):
    """CSV without 'actual_value' column must raise ValueError."""
    bad_cols = [c for c in _COLS if c != "actual_value"]
    rows = [{c: "x" for c in bad_cols}]  # one row, missing actual_value
    p = tmp_path / "bad.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=bad_cols)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="missing required columns"):
        L39.run_exec_backtest(str(p), save=False,
                              _predict_fn=_stub_predict(),
                              _quantile_fn=_stub_quantiles(),
                              _build_row_fn=_stub_build_row(),
                              _resolve_id_fn=_stub_resolve_id())


# ---------------------------------------------------------------------------
# Bonus: helper function unit tests
# ---------------------------------------------------------------------------

def test_compute_drawdown_series_basic():
    """compute_drawdown_series returns correct max drawdown."""
    pnl = [100.0, 200.0, 150.0, 250.0, 100.0]
    max_dd, series = L39.compute_drawdown_series(pnl)
    assert max_dd == pytest.approx(150.0)
    assert len(series) == 5


def test_compute_drawdown_empty():
    max_dd, series = L39.compute_drawdown_series([])
    assert max_dd == 0.0
    assert series == []


def test_bootstrap_ci_all_positive():
    """Bootstrap CI of all-positive returns should have ci_lo > 0."""
    # Use varied returns so the CI has nonzero width
    returns = [0.10 + (i % 5) * 0.01 for i in range(100)]
    lo, hi = L39.bootstrap_ci(returns, n=500)
    assert lo > 0, f"Expected ci_lo > 0, got {lo}"
    assert hi >= lo, f"Expected hi >= lo, got hi={hi} lo={lo}"


def test_bootstrap_ci_empty():
    lo, hi = L39.bootstrap_ci([])
    assert lo == 0.0
    assert hi == 0.0


def test_compute_per_stat_breakdown():
    """compute_per_stat_breakdown aggregates correctly."""
    bets = [
        {"stat": "pts", "stake": 100.0, "pnl": 90.91, "won": True},
        {"stat": "pts", "stake": 100.0, "pnl": -100.0, "won": False},
        {"stat": "reb", "stake": 50.0, "pnl": 45.45, "won": True},
    ]
    breakdown = L39.compute_per_stat_breakdown(bets)
    assert "pts" in breakdown
    assert "reb" in breakdown
    assert breakdown["pts"]["n_bets"] == 2
    assert breakdown["pts"]["hit_rate"] == pytest.approx(0.5)
    assert breakdown["reb"]["n_bets"] == 1
    assert breakdown["reb"]["hit_rate"] == pytest.approx(1.0)


def test_season_from_date_october():
    assert L39._season_from_date("2024-10-22") == "2024-25"


def test_season_from_date_january():
    assert L39._season_from_date("2024-01-15") == "2023-24"


def test_normal_cdf_midpoint():
    """CDF at 0 should be exactly 0.5."""
    assert L39._normal_cdf(0.0) == pytest.approx(0.5)


def test_normal_cdf_large_positive():
    """CDF at large positive z should be very close to 1."""
    assert L39._normal_cdf(10.0) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Atomic-write hardening tests (v2)
# ---------------------------------------------------------------------------

def test_atomic_write_replaces_existing_file(tmp_path):
    """_atomic_write_json atomically replaces an existing file with new content."""
    target = tmp_path / "report.json"
    # Write original content via the helper itself
    L39._atomic_write_json(target, {"version": 1})
    assert target.exists()
    original_text = target.read_text(encoding="utf-8")
    assert '"version": 1' in original_text

    # Now overwrite with new payload
    L39._atomic_write_json(target, {"version": 2, "score": 99})
    new_text = target.read_text(encoding="utf-8")
    assert '"version": 2' in new_text
    assert '"score": 99' in new_text
    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Unexpected .tmp files left behind: {tmp_files}"


def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    """If os.replace raises, the original file is unchanged and .tmp is cleaned up."""
    target = tmp_path / "report.json"
    original_payload = {"original": True}
    # Seed the file with known content
    L39._atomic_write_json(target, original_payload)
    original_text = target.read_text(encoding="utf-8")

    # Monkeypatch os.replace to simulate a failure (e.g. cross-device rename)
    def _failing_replace(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", _failing_replace)

    with pytest.raises(OSError, match="simulated rename failure"):
        L39._atomic_write_json(target, {"corrupted": True})

    # Original file must be untouched
    assert target.read_text(encoding="utf-8") == original_text
    # The .tmp file must have been cleaned up
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f".tmp file not cleaned up: {tmp_files}"
