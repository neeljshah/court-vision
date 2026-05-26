"""test_L08_drift.py — Unit tests for L08_drift_detector.py

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L08_drift.py -v
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure project root on path; stub heavy NBA API import
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))

# Stub the nba_api_headers_patch that L07 (and some execute_loop modules) import
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

import scripts.execute_loop.L08_drift_detector as L08  # noqa: E402
import scripts.execute_loop.L46_event_bus as L46  # noqa: E402

# Capture the real _load_expected_mae before any autouse fixture can patch it
_REAL_LOAD_EXPECTED_MAE = L08._load_expected_mae


# ---------------------------------------------------------------------------
# Helpers to build stub DataFrames
# ---------------------------------------------------------------------------
def _now_iso(delta_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=delta_days)
    return dt.isoformat()


def _make_bets_df(
    n: int,
    stat: str = "pts",
    actual_values: list[float] | None = None,
    model_q50: float = 25.0,
    n_won: int | None = None,
    days_old: int = 1,
) -> pd.DataFrame:
    """Build a minimal settled bets DataFrame for testing.

    actual_values: list of length n; if None, defaults to model_q50 + per-row error.
    n_won: how many rows are WON (rest LOST); defaults to round(n * 0.55).
    """
    if actual_values is None:
        actual_values = [model_q50] * n
    if n_won is None:
        n_won = round(n * 0.55)

    statuses = ["WON"] * n_won + ["LOST"] * (n - n_won)
    settled_iso = _now_iso(days_old)

    rows = []
    for i in range(n):
        rows.append({
            "bet_id": f"bet-{i:04d}",
            "market": f"player_prop_{stat}",
            "player": "TestPlayer",
            "stat": stat,
            "actual_value": actual_values[i],
            "model_q50": model_q50,
            "status": statuses[i],
            "settled_at_iso": settled_iso,
            "stake": 1.0,
            "odds": -110,
            "pnl": 0.9 if statuses[i] == "WON" else -1.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def patch_load_ledger(monkeypatch):
    """Default: ledger returns None (no file). Tests override as needed."""
    monkeypatch.setattr(L08, "_load_ledger", lambda: None)
    yield


@pytest.fixture(autouse=True)
def patch_expected_mae(monkeypatch):
    """Always use fallback constants so tests don't need walk_forward.json."""
    monkeypatch.setattr(L08, "_load_expected_mae", lambda: dict(L08._FALLBACK_MAE))
    yield


# ---------------------------------------------------------------------------
# Test 1 — 30 PTS rows, MAE ≈ 5.0 vs expected 4.62 → OK (z ≈ 0.58)
# ---------------------------------------------------------------------------
def test_compute_drift_ok(monkeypatch):
    """30 PTS rows with MAE ≈ 5.0 should produce status=OK (z < 1)."""
    # actual = model_q50 + 5.0 error on each row
    actual_vals = [25.0 + 5.0] * 30  # constant 5.0 abs error
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)

    dm = L08.compute_drift("pts", window_days=7)

    assert dm is not None
    assert dm.stat == "pts"
    assert dm.n_predictions == 30
    assert dm.observed_mae == pytest.approx(5.0, abs=0.01)
    assert dm.expected_mae == pytest.approx(4.62, abs=0.01)
    # z = (5.0 - 4.62) / (4.62 * 0.15) = 0.38 / 0.693 ≈ 0.549
    assert abs(dm.z_score) < 1.0, f"Expected z<1 (OK), got z={dm.z_score}"
    assert dm.status == "OK"


# ---------------------------------------------------------------------------
# Test 2 — 30 PTS rows, MAE ≈ 8.0 vs expected 4.62 → DRIFT (z ≈ 4.87)
# ---------------------------------------------------------------------------
def test_compute_drift_drift(monkeypatch):
    """30 PTS rows with MAE ≈ 8.0 should produce status=DRIFT (z >= 2)."""
    actual_vals = [25.0 + 8.0] * 30
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)

    dm = L08.compute_drift("pts", window_days=7)

    assert dm is not None
    assert dm.observed_mae == pytest.approx(8.0, abs=0.01)
    # z = (8.0 - 4.62) / (4.62 * 0.15) = 3.38 / 0.693 ≈ 4.87
    assert dm.z_score >= 2.0, f"Expected z>=2, got z={dm.z_score}"
    assert dm.status == "DRIFT"


# ---------------------------------------------------------------------------
# Test 3 — Empty / missing ledger → returns None
# ---------------------------------------------------------------------------
def test_compute_drift_no_ledger(monkeypatch):
    """When _load_ledger returns None, compute_drift should return None."""
    # patch_load_ledger fixture already sets _load_ledger to return None
    result = L08.compute_drift("pts", window_days=7)
    assert result is None


# ---------------------------------------------------------------------------
# Test 4 — 10 rows (< 30) → status=LOW_N
# ---------------------------------------------------------------------------
def test_compute_drift_low_n(monkeypatch):
    """Fewer than 30 rows should produce status=LOW_N."""
    actual_vals = [25.0 + 8.0] * 10  # big error but too few samples
    df = _make_bets_df(n=10, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)

    dm = L08.compute_drift("pts", window_days=7)

    assert dm is not None
    assert dm.n_predictions == 10
    assert dm.status == "LOW_N"


# ---------------------------------------------------------------------------
# Test 5 — daily_drift_report writes JSON with required keys, round-trip
# ---------------------------------------------------------------------------
def test_daily_drift_report_writes_json(monkeypatch, tmp_path):
    """daily_drift_report should write a JSON file with all required keys."""
    # Redirect ledger dir so we write to tmp_path
    monkeypatch.setattr(L08, "_LEDGER_DIR", tmp_path)

    # Provide enough data for a few stats
    actual_vals = [25.0 + 5.0] * 30
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)

    report = L08.daily_drift_report(window_days=7)

    # Required top-level keys
    for key in ("generated_at", "window_days", "metrics", "n_drift", "n_warn", "n_ok"):
        assert key in report, f"Missing key: {key}"

    assert isinstance(report["metrics"], list)
    assert report["window_days"] == 7
    assert isinstance(report["n_drift"], int)
    assert isinstance(report["n_warn"], int)
    assert isinstance(report["n_ok"], int)

    # JSON file on disk
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = tmp_path / f"drift_report_{today}.json"
    assert json_path.exists(), f"Expected JSON file at {json_path}"

    # Round-trip
    with json_path.open() as fh:
        loaded = json.load(fh)

    assert loaded["window_days"] == 7
    assert "metrics" in loaded
    assert "generated_at" in loaded
    assert "n_drift" in loaded
    assert "n_warn" in loaded
    assert "n_ok" in loaded


# ---------------------------------------------------------------------------
# Test 6 — alert_on_drift with one DRIFT metric → L22.send_drift_alert called once
# ---------------------------------------------------------------------------
def test_alert_on_drift_calls_l22(monkeypatch):
    """alert_on_drift should call send_drift_alert once for a DRIFT metric."""
    from dataclasses import replace

    drift_metric = L08.DriftMetric(
        stat="pts",
        window_days=7,
        n_predictions=35,
        observed_mae=8.0,
        expected_mae=4.62,
        observed_hit_rate=0.52,
        expected_hit_rate=0.55,
        z_score=4.87,
        status="DRIFT",
    )

    send_mock = MagicMock(return_value=True)

    # Inject mock L22 module into sys.modules so the import inside alert_on_drift works
    fake_l22 = types.ModuleType("scripts.execute_loop.L22_alerting")
    fake_l22.send_drift_alert = send_mock
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L22_alerting", fake_l22)

    count = L08.alert_on_drift([drift_metric])

    assert count == 1
    send_mock.assert_called_once_with("pts", 8.0, 4.62, 7)


# ---------------------------------------------------------------------------
# Test 7 — walk_forward.json missing → uses fallback constants
# ---------------------------------------------------------------------------
def test_load_expected_mae_fallback(monkeypatch, tmp_path):
    """When walk_forward.json does not exist, fallback dict is used."""
    # Point _WF_JSON to a non-existent path and call the real implementation.
    monkeypatch.setattr(L08, "_WF_JSON", tmp_path / "does_not_exist.json")
    result = _REAL_LOAD_EXPECTED_MAE()

    assert isinstance(result, dict)
    for stat in L08._FALLBACK_MAE:
        assert stat in result
        assert result[stat] == L08._FALLBACK_MAE[stat]


# ---------------------------------------------------------------------------
# Bonus Test 8 — walk_forward.json with by_stat key overrides fallback
# ---------------------------------------------------------------------------
def test_load_expected_mae_from_json(monkeypatch, tmp_path):
    """walk_forward.json with by_stat dict should override fallback for known stats."""
    wf_path = tmp_path / "prop_pergame_walk_forward.json"
    wf_path.write_text(json.dumps({"by_stat": {"pts": 3.99, "reb": 1.75}}))

    # Redirect _WF_JSON and call the real implementation (captured before autouse patching).
    monkeypatch.setattr(L08, "_WF_JSON", wf_path)
    result = _REAL_LOAD_EXPECTED_MAE()

    assert result["pts"] == pytest.approx(3.99)
    assert result["reb"] == pytest.approx(1.75)
    # Unmentioned stats stay at fallback
    assert result["ast"] == pytest.approx(L08._FALLBACK_MAE["ast"])


# ---------------------------------------------------------------------------
# Bonus Test 9 — expected_mae <= 0 guard (z=0, status=OK)
# ---------------------------------------------------------------------------
def test_expected_mae_zero_guard(monkeypatch):
    """If expected_mae is 0 (or <= 0), z should be 0 and status OK."""
    actual_vals = [25.0 + 10.0] * 30  # huge error
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)
    # Override expected MAE to zero
    monkeypatch.setattr(L08, "_load_expected_mae", lambda: {"pts": 0.0, **{k: 1.0 for k in L08._FALLBACK_MAE if k != "pts"}})

    dm = L08.compute_drift("pts", window_days=7)

    assert dm is not None
    assert dm.z_score == 0.0
    assert dm.status == "OK"


# ---------------------------------------------------------------------------
# Bonus Test 10 — rows with missing model_q50 are skipped
# ---------------------------------------------------------------------------
def test_nan_model_q50_skipped(monkeypatch):
    """Rows where model_q50 is NaN/empty should be excluded from MAE calc."""
    import math

    rows = []
    settled_iso = _now_iso(1)
    for i in range(20):
        rows.append({
            "bet_id": f"bet-{i:04d}",
            "market": "player_prop_pts",
            "player": "TestPlayer",
            "stat": "pts",
            "actual_value": 30.0,
            "model_q50": float("nan"),   # invalid — should be skipped
            "status": "WON" if i % 2 == 0 else "LOST",
            "settled_at_iso": settled_iso,
            "stake": 1.0,
            "odds": -110,
            "pnl": 0.9,
        })
    # Add 30 valid rows
    for i in range(30):
        rows.append({
            "bet_id": f"bet-valid-{i:04d}",
            "market": "player_prop_pts",
            "player": "TestPlayer",
            "stat": "pts",
            "actual_value": 30.0,
            "model_q50": 27.0,           # 3.0 error
            "status": "WON",
            "settled_at_iso": settled_iso,
            "stake": 1.0,
            "odds": -110,
            "pnl": 0.9,
        })

    df = pd.DataFrame(rows)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)

    dm = L08.compute_drift("pts", window_days=7)

    assert dm is not None
    # Only the 30 valid rows contribute to MAE
    assert dm.observed_mae == pytest.approx(3.0, abs=0.01)


# ---------------------------------------------------------------------------
# Bonus Test 11 — alert_on_drift with L22 ImportError is graceful
# ---------------------------------------------------------------------------
def test_alert_on_drift_no_l22(monkeypatch):
    """If L22_alerting is not importable, alert_on_drift returns 0 gracefully."""
    # Remove any cached L22 module
    monkeypatch.delitem(sys.modules, "scripts.execute_loop.L22_alerting", raising=False)

    # Make the import fail
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _blocking_import(name, *args, **kwargs):
        if "L22_alerting" in name:
            raise ImportError("L22 not available")
        return original_import(name, *args, **kwargs)

    drift_metric = L08.DriftMetric(
        stat="pts",
        window_days=7,
        n_predictions=35,
        observed_mae=8.0,
        expected_mae=4.62,
        observed_hit_rate=0.52,
        expected_hit_rate=0.55,
        z_score=4.87,
        status="DRIFT",
    )

    # Patch via sys.modules removal — when L22 is absent, ImportError is raised
    if "scripts.execute_loop.L22_alerting" in sys.modules:
        monkeypatch.delitem(sys.modules, "scripts.execute_loop.L22_alerting")

    # Use a monkeypatch import that blocks L22
    with patch.dict(sys.modules, {"scripts.execute_loop.L22_alerting": None}):
        count = L08.alert_on_drift([drift_metric])

    assert count == 0


# ---------------------------------------------------------------------------
# Test 12 — _atomic_write_json replaces existing file with new content
# ---------------------------------------------------------------------------
def test_atomic_write_replaces_existing_file(tmp_path):
    """Write v1, then write v2; the file must contain v2."""
    target = tmp_path / "drift_report_test.json"

    v1 = {"version": 1, "data": "first"}
    v2 = {"version": 2, "data": "second"}

    L08._atomic_write_json(target, v1)
    assert target.exists()
    with target.open(encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["version"] == 1

    L08._atomic_write_json(target, v2)
    with target.open(encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["version"] == 2, "File should contain v2 after second write"
    assert loaded["data"] == "second"


# ---------------------------------------------------------------------------
# Test 13 — _atomic_write_json leaves original unchanged on failure + cleans tmp
# ---------------------------------------------------------------------------
def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    """If os.replace raises, the original file is unchanged and .tmp is cleaned up."""
    import os as _os

    target = tmp_path / "drift_report_test.json"
    original_payload = {"version": "original", "safe": True}

    # Write initial content the normal way so there is an existing file to protect.
    L08._atomic_write_json(target, original_payload)

    # Monkeypatch os.replace to raise after the temp file is written.
    def _failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(_os, "replace", _failing_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        L08._atomic_write_json(target, {"version": "corrupted"})

    # Original file must still contain the original content.
    with target.open(encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["version"] == "original", "Original file must be untouched after failed write"

    # No leftover .tmp files in the directory.
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leftover .tmp files found: {tmp_files}"


# ---------------------------------------------------------------------------
# Test 14 — drifty data: subscriber receives drift.detected event
# ---------------------------------------------------------------------------
def test_drift_detected_publishes_event(monkeypatch, tmp_path):
    """When drift is detected, daily_drift_report publishes drift.detected via L46."""
    # Reset the default bus so this test starts clean
    L46.get_default_bus().clear_subscribers()

    received: list = []
    L46.subscribe("drift.detected", received.append, layer="test_L14")

    # 30 PTS rows with MAE ≈ 8.0 → DRIFT (z ≈ 4.87)
    actual_vals = [25.0 + 8.0] * 30
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)
    monkeypatch.setattr(L08, "_LEDGER_DIR", tmp_path)
    # Ensure L08 uses the real (live) L46 module
    import scripts.execute_loop.L46_event_bus as _live_l46
    monkeypatch.setattr(L08, "_L46", _live_l46)

    L08.daily_drift_report(window_days=7)

    # Clean up subscription
    L46.get_default_bus().clear_subscribers()

    assert len(received) >= 1, "Expected at least one drift.detected event"
    evt = received[0]
    assert evt.name == "drift.detected"
    assert evt.source == "L8"
    payload = evt.payload
    assert payload["stat"] == "pts"
    assert payload["severity"] == "error"
    assert isinstance(payload["drift_metric"], float)
    assert isinstance(payload["threshold"], float)
    assert isinstance(payload["window_days"], int)
    assert "detected_at" in payload


# ---------------------------------------------------------------------------
# Test 15 — clean data: no event published when no drift
# ---------------------------------------------------------------------------
def test_no_drift_publishes_nothing(monkeypatch, tmp_path):
    """When all stats are OK or LOW_N, no drift.detected event is published."""
    L46.get_default_bus().clear_subscribers()

    received: list = []
    L46.subscribe("drift.detected", received.append, layer="test_L15")

    # 30 PTS rows with MAE ≈ 5.0 vs expected 4.62 → z ≈ 0.55 → OK
    actual_vals = [25.0 + 5.0] * 30
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)
    monkeypatch.setattr(L08, "_LEDGER_DIR", tmp_path)
    import scripts.execute_loop.L46_event_bus as _live_l46
    monkeypatch.setattr(L08, "_L46", _live_l46)

    L08.daily_drift_report(window_days=7)

    L46.get_default_bus().clear_subscribers()

    # The pts stat is OK; all other stats have NO_DATA — none trigger an event
    assert len(received) == 0, f"Expected 0 events for clean data, got {len(received)}"


# ---------------------------------------------------------------------------
# Test 16 — L46 publish failure: report still completes normally
# ---------------------------------------------------------------------------
def test_publish_failure_does_not_break_report(monkeypatch, tmp_path):
    """If L46.publish raises, daily_drift_report still returns a valid report."""
    # Build a mock L46 module whose publish always raises
    fake_l46 = types.ModuleType("scripts.execute_loop.L46_event_bus_mock")
    fake_l46.publish = MagicMock(side_effect=RuntimeError("bus exploded"))
    monkeypatch.setattr(L08, "_L46", fake_l46)

    # Drifty data so publish is actually attempted
    actual_vals = [25.0 + 8.0] * 30
    df = _make_bets_df(n=30, stat="pts", actual_values=actual_vals, model_q50=25.0)
    monkeypatch.setattr(L08, "_load_ledger", lambda: df)
    monkeypatch.setattr(L08, "_LEDGER_DIR", tmp_path)

    # Should not raise despite the publish failure
    report = L08.daily_drift_report(window_days=7)

    assert "metrics" in report
    assert "n_drift" in report
    assert report["n_drift"] >= 1, "PTS should still be flagged as DRIFT"
