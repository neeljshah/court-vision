"""test_L35_ruin.py — Unit tests for L35_risk_of_ruin (BUILD L35).

Tests cover:
  1. Normal distribution → 0 < p_ruin_30d < 0.2
  2. Negative drift → p_ruin_30d > 0.5
  3. estimate_daily_return_dist_from_ledger with controlled stub parquet/csv
  4. alert_on_high_ruin_risk → L22.send_alert called with severity="warning"
  5. <14 observations → fallback distribution (used_fallback=True)
  6. std=0 deterministic path → no errors, correct p_ruin
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── make project root importable ──────────────────────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_EXECUTE_LOOP = _TESTS_DIR.parent
_PROJECT_DIR = _EXECUTE_LOOP.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))


def _fresh_module(monkeypatch=None, overrides: dict | None = None):
    """Re-import L35_risk_of_ruin with a clean module cache."""
    for key in list(sys.modules.keys()):
        if "L35_risk_of_ruin" in key:
            del sys.modules[key]
    if monkeypatch and overrides:
        for k, v in overrides.items():
            monkeypatch.setenv(k, v)
    import scripts.execute_loop.L35_risk_of_ruin as m
    return m


@pytest.fixture(autouse=True)
def _clean_module():
    """Ensure module cache is cleared between tests."""
    for key in list(sys.modules.keys()):
        if "L35_risk_of_ruin" in key:
            del sys.modules[key]
    yield
    for key in list(sys.modules.keys()):
        if "L35_risk_of_ruin" in key:
            del sys.modules[key]


@pytest.fixture()
def mod():
    import scripts.execute_loop.L35_risk_of_ruin as m
    return m


# ── helper: build a stub bets CSV ────────────────────────────────────────────
def _make_bets_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write rows to a bets.csv for ledger tests."""
    import csv
    cols = [
        "bet_id", "placed_at_iso", "book", "market", "player", "stat",
        "line", "side", "stake", "odds", "model_q50", "model_p_side",
        "model_edge_pp", "test_mode", "status", "settled_at_iso",
        "actual_value", "pnl", "game_id", "notes",
    ]
    csv_path = tmp_path / "bets.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            row = {c: "" for c in cols}
            row.update(r)
            writer.writerow(row)
    return csv_path


def _iso(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


# ── test 1: positive drift → p_ruin in (0, 0.2) ──────────────────────────────
def test_positive_drift_low_ruin(mod):
    dist = {"mean": 0.005, "std": 0.05, "n_observations": 30, "used_fallback": False}
    report = mod.run_simulation(
        initial_bankroll=100_000.0,
        daily_return_dist=dist,
        n_sims=10_000,
        n_days=30,
        ruin_threshold_pct=0.5,
    )
    assert 0.0 < report.p_ruin_30d < 0.2, (
        f"Expected 0 < p_ruin < 0.2, got {report.p_ruin_30d:.4f}"
    )
    assert report.mean_daily_return == pytest.approx(0.005)
    assert report.std_daily_return == pytest.approx(0.05)
    assert len(report.simulated_bankrolls) == 10_000
    assert report.used_fallback_dist is False


# ── test 2: negative drift → p_ruin > 0.5 ────────────────────────────────────
def test_negative_drift_high_ruin(mod):
    # mean=-0.03 over 60 days: E[bankroll]=100k*0.97^60≈16k → well below 50k ruin floor
    dist = {"mean": -0.03, "std": 0.05, "n_observations": 30, "used_fallback": False}
    report = mod.run_simulation(
        initial_bankroll=100_000.0,
        daily_return_dist=dist,
        n_sims=10_000,
        n_days=60,
        ruin_threshold_pct=0.5,
    )
    assert report.p_ruin_30d > 0.5, (
        f"Expected p_ruin > 0.5, got {report.p_ruin_30d:.4f}"
    )
    assert report.mean_daily_return == pytest.approx(-0.03)


# ── test 3: ledger estimation with controlled CSV ─────────────────────────────
def test_ledger_estimation_controlled(tmp_path, mod, monkeypatch):
    # Create 15 days of controlled daily pnl: fixed $500/day
    rows = []
    for d in range(15):
        rows.append({
            "status": "WON",
            "settled_at_iso": _iso(days_ago=d),
            "pnl": "500.0",
        })
    csv_path = _make_bets_csv(tmp_path, rows)

    # Patch module-level paths to point at tmp
    monkeypatch.setattr(mod, "_BETS_PARQUET", tmp_path / "bets.parquet")
    monkeypatch.setattr(mod, "_BETS_CSV", csv_path)
    monkeypatch.setattr(mod, "_HAS_PARQUET", False)

    # Patch bankroll state to known value
    state_path = tmp_path / "bankroll_state.json"
    state_path.write_text(json.dumps({"current_bankroll": 100_000.0}))
    monkeypatch.setattr(mod, "_BANKROLL_STATE", state_path)

    result = mod.estimate_daily_return_dist_from_ledger(window_days=30)

    # Each day: pnl=500, bankroll=100000 → return=0.005 per day
    assert result["used_fallback"] is False
    assert result["n_observations"] == 15
    assert result["mean"] == pytest.approx(0.005, abs=1e-6)
    # std should be 0 (all days identical pnl)
    assert result["std"] == pytest.approx(0.0, abs=1e-6)


# ── test 4: alert with p_ruin=0.10 → warning severity, send_alert called once ─
def test_alert_warning_severity(mod, monkeypatch):
    # Build a fake RuinReport with p_ruin=0.10
    report = mod.RuinReport(
        simulated_bankrolls=[100_000.0] * 10,
        p_ruin_30d=0.10,
        p_drawdown_50=0.08,
        expected_final=105_000.0,
        median_final=103_000.0,
        sharpe=0.8,
        observed_daily_returns_count=30,
        mean_daily_return=0.003,
        std_daily_return=0.04,
        used_fallback_dist=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    calls: list[dict] = []

    fake_L22 = MagicMock()
    fake_L22.send_alert.side_effect = lambda **kwargs: calls.append(kwargs) or True

    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L22_alerting", fake_L22)

    result = mod.alert_on_high_ruin_risk(report, threshold=0.05)

    assert result is True
    assert len(calls) == 1
    call = calls[0]
    assert call["level"] == "warning"
    assert call["channel"] == "drawdown"
    assert "ruin" in call["title"].lower()


# ── test 5: fewer than 14 days → fallback distribution ───────────────────────
def test_few_days_uses_fallback(tmp_path, mod, monkeypatch):
    # Only 5 days of data
    rows = []
    for d in range(5):
        rows.append({
            "status": "LOST",
            "settled_at_iso": _iso(days_ago=d),
            "pnl": "-200.0",
        })
    csv_path = _make_bets_csv(tmp_path, rows)

    monkeypatch.setattr(mod, "_BETS_PARQUET", tmp_path / "bets.parquet")
    monkeypatch.setattr(mod, "_BETS_CSV", csv_path)
    monkeypatch.setattr(mod, "_HAS_PARQUET", False)

    state_path = tmp_path / "bankroll_state.json"
    state_path.write_text(json.dumps({"current_bankroll": 100_000.0}))
    monkeypatch.setattr(mod, "_BANKROLL_STATE", state_path)

    result = mod.estimate_daily_return_dist_from_ledger(window_days=30)

    assert result["used_fallback"] is True
    assert result["mean"] == pytest.approx(mod._FALLBACK_MEAN, abs=1e-9)
    assert result["std"] == pytest.approx(mod._FALLBACK_STD, abs=1e-9)
    assert result["n_observations"] == 0


# ── test 6: std=0 deterministic path ─────────────────────────────────────────
def test_zero_std_deterministic(mod):
    # positive mean: bankroll grows → no ruin
    dist_pos = {"mean": 0.01, "std": 0.0, "n_observations": 30, "used_fallback": False}
    report_pos = mod.run_simulation(
        initial_bankroll=100_000.0,
        daily_return_dist=dist_pos,
        n_sims=10_000,
        n_days=30,
    )
    assert report_pos.p_ruin_30d == pytest.approx(0.0)
    assert report_pos.p_drawdown_50 == pytest.approx(0.0)
    assert report_pos.std_daily_return == pytest.approx(0.0)
    # expected final > initial
    assert report_pos.expected_final > 100_000.0

    # negative mean: bankroll shrinks → ruin very likely
    dist_neg = {"mean": -0.05, "std": 0.0, "n_observations": 30, "used_fallback": False}
    report_neg = mod.run_simulation(
        initial_bankroll=100_000.0,
        daily_return_dist=dist_neg,
        n_sims=10_000,
        n_days=30,
        ruin_threshold_pct=0.5,
    )
    # After 30 days at -5%/day: 100000 * 0.95^30 ≈ 21464 → well below 50k
    assert report_neg.p_ruin_30d == pytest.approx(1.0)
    assert report_neg.p_drawdown_50 == pytest.approx(1.0)


# ── bonus: report JSON truncates simulated_bankrolls to 1000 ─────────────────
def test_json_truncates_bankrolls(mod):
    dist = {"mean": 0.001, "std": 0.03, "n_observations": 20, "used_fallback": False}
    report = mod.run_simulation(
        initial_bankroll=100_000.0,
        daily_return_dist=dist,
        n_sims=5_000,
        n_days=30,
    )
    assert len(report.simulated_bankrolls) == 5_000
    d = mod._report_to_json(report)
    assert len(d["simulated_bankrolls"]) == 1000


# ── bonus: no ledger file → fallback dist ─────────────────────────────────────
def test_missing_ledger_returns_fallback(tmp_path, mod, monkeypatch):
    monkeypatch.setattr(mod, "_BETS_PARQUET", tmp_path / "nonexistent.parquet")
    monkeypatch.setattr(mod, "_BETS_CSV",     tmp_path / "nonexistent.csv")
    monkeypatch.setattr(mod, "_HAS_PARQUET",  False)

    result = mod.estimate_daily_return_dist_from_ledger(window_days=30)
    assert result["used_fallback"] is True


# ── bonus: L22 import error → alert returns False ────────────────────────────
def test_alert_l22_import_error_returns_false(mod, monkeypatch):
    report = mod.RuinReport(
        simulated_bankrolls=[],
        p_ruin_30d=0.15,
        p_drawdown_50=0.12,
        expected_final=90_000.0,
        median_final=92_000.0,
        sharpe=0.5,
        observed_daily_returns_count=20,
        mean_daily_return=0.001,
        std_daily_return=0.04,
        used_fallback_dist=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    # Simulate ImportError by temporarily removing the module
    monkeypatch.setitem(
        sys.modules, "scripts.execute_loop.L22_alerting", None
    )
    result = mod.alert_on_high_ruin_risk(report, threshold=0.05)
    assert result is False


# ── bonus: p_ruin > 0.20 → error severity ────────────────────────────────────
def test_alert_error_severity_above_20_pct(mod, monkeypatch):
    report = mod.RuinReport(
        simulated_bankrolls=[],
        p_ruin_30d=0.25,
        p_drawdown_50=0.20,
        expected_final=80_000.0,
        median_final=82_000.0,
        sharpe=-0.3,
        observed_daily_returns_count=25,
        mean_daily_return=-0.005,
        std_daily_return=0.06,
        used_fallback_dist=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    calls: list[dict] = []
    fake_L22 = MagicMock()
    fake_L22.send_alert.side_effect = lambda **kwargs: calls.append(kwargs) or True
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L22_alerting", fake_L22)

    result = mod.alert_on_high_ruin_risk(report, threshold=0.05)

    assert result is True
    assert calls[0]["level"] == "error"


# ── bonus: p_ruin below threshold → no alert ─────────────────────────────────
def test_no_alert_below_threshold(mod, monkeypatch):
    report = mod.RuinReport(
        simulated_bankrolls=[],
        p_ruin_30d=0.02,
        p_drawdown_50=0.01,
        expected_final=110_000.0,
        median_final=108_000.0,
        sharpe=1.5,
        observed_daily_returns_count=30,
        mean_daily_return=0.006,
        std_daily_return=0.03,
        used_fallback_dist=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    fake_L22 = MagicMock()
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L22_alerting", fake_L22)

    result = mod.alert_on_high_ruin_risk(report, threshold=0.05)
    assert result is False
    fake_L22.send_alert.assert_not_called()
