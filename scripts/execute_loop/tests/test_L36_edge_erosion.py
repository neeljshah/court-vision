"""test_L36_edge_erosion.py — Unit tests for L36_edge_erosion.py

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L36_edge_erosion.py -v
"""
from __future__ import annotations

import json
import sys
import types
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path; stub heavy NBA API import
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))

_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

import scripts.execute_loop.L36_edge_erosion as L36  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso(delta_days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=delta_days)).isoformat()


def _make_ledger(
    n: int,
    book: str = "prizepicks",
    stat: str = "pts",
    side: str = "over",
    line: float = 10.0,
    n_won: int | None = None,
    stake: float = 10.0,
    pnl_win: float = 9.09,   # ~-110 odds win
    pnl_loss: float = -10.0,
    model_edge_pp: float = 5.0,
) -> pd.DataFrame:
    """Build a stub bets DataFrame matching L07 BetRow column schema."""
    if n_won is None:
        n_won = n  # all winning by default

    rows = []
    for i in range(n):
        won = i < n_won
        rows.append({
            "bet_id": f"bet-{i:05d}",
            "placed_at_iso": _iso(2),
            "book": book,
            "market": f"player_prop_{stat}",
            "player": "TestPlayer",
            "stat": stat,
            "line": line,
            "side": side,
            "stake": stake,
            "odds": -110,
            "model_q50": 12.0,
            "model_p_side": 0.55,
            "model_edge_pp": model_edge_pp,
            "test_mode": True,
            "status": "WON" if won else "LOST",
            "settled_at_iso": _iso(1),
            "actual_value": line + (1.0 if won else -1.0),
            "pnl": pnl_win if won else pnl_loss,
            "game_id": "game-001",
            "notes": "",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolate_quarantine(monkeypatch, tmp_path):
    """Redirect quarantine file and ledger dir to tmp_path for every test."""
    monkeypatch.setattr(L36, "_QUARANTINE_FILE", tmp_path / "quarantined_angles.json")
    monkeypatch.setattr(L36, "_LEDGER_DIR", tmp_path)
    yield


# ---------------------------------------------------------------------------
# Test 1 — 50 winning bets → status=OK
# ---------------------------------------------------------------------------
def test_all_winning_bets_ok(monkeypatch):
    """50 all-WON bets should yield positive observed_ev and status=OK."""
    df = _make_ledger(n=50, n_won=50, pnl_win=9.09, model_edge_pp=5.0)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)

    assert len(metrics) == 1
    m = metrics[0]
    assert m.angle_key == "prizepicks_pts_over_10"
    assert m.n_bets_in_window == 50
    assert m.observed_ev_pct > m.expected_ev_pct, (
        f"expected observed > model edge; got {m.observed_ev_pct} vs {m.expected_ev_pct}"
    )
    assert m.status == "OK"
    assert not L36.is_quarantined(m.angle_key)


# ---------------------------------------------------------------------------
# Test 2 — 50 losing bets → status=QUARANTINED and angle in quarantine list
# ---------------------------------------------------------------------------
def test_all_losing_bets_quarantined(monkeypatch):
    """50 all-LOST bets should yield negative EV and status=QUARANTINED."""
    df = _make_ledger(n=50, n_won=0, pnl_loss=-10.0, model_edge_pp=5.0)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)

    assert len(metrics) == 1
    m = metrics[0]
    assert m.observed_ev_pct < 2.0, f"Expected negative EV, got {m.observed_ev_pct}"
    assert m.p_value < 0.10, f"Expected p < 0.10, got {m.p_value}"
    assert m.status == "QUARANTINED"
    assert L36.is_quarantined(m.angle_key), "Angle should be in quarantine state"


# ---------------------------------------------------------------------------
# Test 3 — quarantine_angle persists to JSON; is_quarantined returns True
# ---------------------------------------------------------------------------
def test_quarantine_persists(tmp_path):
    """quarantine_angle should write JSON state and is_quarantined should read it."""
    key = "testbook_blk_under_0.5"
    assert not L36.is_quarantined(key)

    L36.quarantine_angle(key, reason="unit test", n_bets=45, observed_ev=-3.2)

    q_file = tmp_path / "quarantined_angles.json"
    assert q_file.exists(), "Quarantine JSON file should be created"

    state = json.loads(q_file.read_text(encoding="utf-8"))
    keys_in_state = [e["angle_key"] for e in state.get("angles", [])]
    assert key in keys_in_state
    assert L36.is_quarantined(key)


# ---------------------------------------------------------------------------
# Test 4 — unquarantine with wrong token raises ValueError
# ---------------------------------------------------------------------------
def test_unquarantine_bad_token():
    """unquarantine_angle with wrong token must raise ValueError."""
    key = "draftkings_reb_over_5.5"
    L36.quarantine_angle(key, reason="bad-token test")

    with pytest.raises(ValueError, match="Invalid token"):
        L36.unquarantine_angle(key, "wrong_token")

    # Still quarantined after bad-token attempt
    assert L36.is_quarantined(key)


# ---------------------------------------------------------------------------
# Test 5 — unquarantine with correct token removes angle
# ---------------------------------------------------------------------------
def test_unquarantine_correct_token():
    """unquarantine_angle with UNQUARANTINE_OK should remove the angle."""
    key = "fanduel_stl_over_1.5"
    L36.quarantine_angle(key, reason="to be removed")
    assert L36.is_quarantined(key)

    L36.unquarantine_angle(key, "UNQUARANTINE_OK")

    assert not L36.is_quarantined(key)


# ---------------------------------------------------------------------------
# Test 6 — quarantine same angle twice → only one entry in JSON
# ---------------------------------------------------------------------------
def test_quarantine_idempotent(tmp_path):
    """Calling quarantine_angle twice on the same key must not duplicate entries."""
    key = "betmgm_ast_under_3"
    L36.quarantine_angle(key, reason="first call", n_bets=30)
    L36.quarantine_angle(key, reason="second call", n_bets=35)

    q_file = tmp_path / "quarantined_angles.json"
    state = json.loads(q_file.read_text(encoding="utf-8"))
    matching = [e for e in state["angles"] if e["angle_key"] == key]
    assert len(matching) == 1, f"Expected 1 entry, found {len(matching)}"
    # First call's reason is preserved
    assert matching[0]["reason"] == "first call"


# ---------------------------------------------------------------------------
# Test 7 — fewer than min_n bets → INSUFFICIENT
# ---------------------------------------------------------------------------
def test_insufficient_bets(monkeypatch):
    """Fewer than min_n settled bets → status=INSUFFICIENT."""
    df = _make_ledger(n=20, n_won=20)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)

    assert len(metrics) == 1
    assert metrics[0].status == "INSUFFICIENT"
    assert metrics[0].n_bets_in_window == 20


# ---------------------------------------------------------------------------
# Test 8 — WARN: ev below (expected - 5) but not < 2 and p not < 0.10
# ---------------------------------------------------------------------------
def test_warn_status(monkeypatch):
    """Angle with ev below expected-5 but not QUARANTINED threshold → WARN."""
    # ~55% win rate on -110 → slightly positive EV but below model expectation
    n = 50
    n_won = 27  # ~54% hit rate, small positive EV
    df = _make_ledger(n=n, n_won=n_won, model_edge_pp=15.0)  # expected=15%, obs will be ~2-5%
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)
    assert len(metrics) == 1
    m = metrics[0]
    # Observed EV should be below expected_ev - 5
    assert m.observed_ev_pct < m.expected_ev_pct - 5.0, (
        f"Expected obs_ev < exp_ev-5; obs={m.observed_ev_pct:.2f} exp={m.expected_ev_pct:.2f}"
    )
    assert m.status == "WARN"


# ---------------------------------------------------------------------------
# Test 9 — daily_edge_report writes JSON with required keys
# ---------------------------------------------------------------------------
def test_daily_edge_report_structure(monkeypatch, tmp_path):
    """daily_edge_report should return and write a JSON with required keys."""
    df = _make_ledger(n=50, n_won=35)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    report = L36.daily_edge_report()

    required_keys = {
        "generated_at", "window_n", "n_angles", "n_quarantined",
        "n_warn", "n_ok", "n_insufficient", "metrics", "quarantine_list",
    }
    for key in required_keys:
        assert key in report, f"Missing key: {key}"

    assert isinstance(report["metrics"], list)
    assert isinstance(report["n_quarantined"], int)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = tmp_path / f"edge_erosion_report_{today}.json"
    assert report_path.exists(), f"Report file not found at {report_path}"

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["window_n"] == 50
    assert "metrics" in loaded


# ---------------------------------------------------------------------------
# Test 10 — multiple angles in ledger, each gets own metric
# ---------------------------------------------------------------------------
def test_multiple_angles(monkeypatch):
    """Ledger with two distinct angles should produce two AngleMetric rows."""
    df_over = _make_ledger(n=50, stat="pts", side="over", line=10.0, n_won=40)
    df_under = _make_ledger(n=50, stat="blk", side="under", line=0.5, n_won=0)
    combined = pd.concat([df_over, df_under], ignore_index=True)
    monkeypatch.setattr(L36, "_load_bets", lambda: combined)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)
    keys = {m.angle_key for m in metrics}

    assert "prizepicks_pts_over_10" in keys
    assert "prizepicks_blk_under_0.5" in keys
    assert len(metrics) == 2

    blk_metric = next(m for m in metrics if "blk" in m.angle_key)
    assert blk_metric.status == "QUARANTINED"
    pts_metric = next(m for m in metrics if "pts" in m.angle_key)
    assert pts_metric.status == "OK"


# ---------------------------------------------------------------------------
# Test 11 — no ledger returns empty list (no crash)
# ---------------------------------------------------------------------------
def test_no_ledger_returns_empty(monkeypatch):
    """When no ledger exists, compute_angle_metrics should return [] gracefully."""
    monkeypatch.setattr(L36, "_load_bets", lambda: None)
    metrics = L36.compute_angle_metrics()
    assert metrics == []


# ---------------------------------------------------------------------------
# Test 12 — L22 soft import failure is swallowed during quarantine
# ---------------------------------------------------------------------------
def test_quarantine_l22_import_error_swallowed(monkeypatch):
    """If L22 is not importable, quarantine_angle should still succeed silently."""
    # Inject a broken L22 module
    monkeypatch.setitem(sys.modules, "scripts.execute_loop.L22_alerting", None)

    key = "test_l22_fail_pts_over_20"
    L36.quarantine_angle(key, reason="L22 import error test", n_bets=40)
    assert L36.is_quarantined(key)


# ---------------------------------------------------------------------------
# Test 13 — unquarantine non-existent angle is a no-op (no crash)
# ---------------------------------------------------------------------------
def test_unquarantine_nonexistent_is_noop():
    """Unquarantining a key that is not quarantined should not crash."""
    key = "nonexistent_angle_key"
    assert not L36.is_quarantined(key)
    L36.unquarantine_angle(key, "UNQUARANTINE_OK")  # should not raise
    assert not L36.is_quarantined(key)


# ---------------------------------------------------------------------------
# Test 14 — angle key derivation from BetRow-compatible row
# ---------------------------------------------------------------------------
def test_angle_key_derivation():
    """_angle_key_from_row should produce the expected key format."""
    row = pd.Series({
        "book": "PrizePicks",
        "stat": "BLK",
        "side": "Under",
        "line": 0.5,
    })
    key = L36._angle_key_from_row(row)
    assert key == "prizepicks_blk_under_0.5"


# ---------------------------------------------------------------------------
# Test 15 — window_n truncation: ledger with 100 bets, window=50 uses last 50
# ---------------------------------------------------------------------------
def test_window_truncation(monkeypatch):
    """compute_angle_metrics with window_n=50 should only use the last 50 rows."""
    # First 50 bets: all LOST (older), next 50: all WON (recent)
    df_old = _make_ledger(n=50, n_won=0, pnl_loss=-10.0)
    df_old["settled_at_iso"] = _iso(10)  # older
    df_new = _make_ledger(n=50, n_won=50, pnl_win=9.09)
    df_new["settled_at_iso"] = _iso(1)  # recent
    combined = pd.concat([df_old, df_new], ignore_index=True)
    monkeypatch.setattr(L36, "_load_bets", lambda: combined)

    metrics = L36.compute_angle_metrics(window_n=50, min_n=30)
    assert len(metrics) == 1
    m = metrics[0]
    # Window should be the 50 most-recent (all WON) rows → positive EV
    assert m.n_bets_in_window == 50
    assert m.observed_ev_pct > 0, f"Expected positive EV from recent wins, got {m.observed_ev_pct}"
    assert m.status == "OK"


# ---------------------------------------------------------------------------
# Test 16 — per_stat_erosion breakdown in daily_edge_report (3 distinct stats)
# ---------------------------------------------------------------------------
def test_per_stat_breakdown_in_report(monkeypatch):
    """daily_edge_report should include per_stat_erosion with one entry per distinct stat."""
    df_pts = _make_ledger(n=50, stat="pts", side="over", line=20.0, n_won=40)
    df_reb = _make_ledger(n=50, stat="reb", side="over", line=5.5, n_won=35)
    df_ast = _make_ledger(n=50, stat="ast", side="under", line=3.0, n_won=0)
    combined = pd.concat([df_pts, df_reb, df_ast], ignore_index=True)
    monkeypatch.setattr(L36, "_load_bets", lambda: combined)

    report = L36.daily_edge_report()

    assert "per_stat_erosion" in report, "Report missing per_stat_erosion key"
    stat_entries = report["per_stat_erosion"]
    stat_names = {e["stat"] for e in stat_entries}

    assert "pts" in stat_names, f"Missing 'pts' in per_stat_erosion: {stat_names}"
    assert "reb" in stat_names, f"Missing 'reb' in per_stat_erosion: {stat_names}"
    assert "ast" in stat_names, f"Missing 'ast' in per_stat_erosion: {stat_names}"
    assert len(stat_entries) == 3, f"Expected 3 stat entries, got {len(stat_entries)}"

    # ast had 0 wins → should be eroded
    ast_entry = next(e for e in stat_entries if e["stat"] == "ast")
    assert ast_entry["n_eroded"] >= 1, "ast angle should be marked as eroded"

    # Each entry must have the required fields
    required = {
        "stat", "n_angles", "n_eroded", "avg_observed_ev_pct",
        "worst_angle_key", "worst_observed_ev_pct", "worst_expected_ev_pct", "worst_status",
    }
    for entry in stat_entries:
        missing = required - entry.keys()
        assert not missing, f"per_stat_erosion entry missing fields: {missing}"


# ---------------------------------------------------------------------------
# Test 17 — erosion detected publishes event to L46
# ---------------------------------------------------------------------------
def test_erosion_detected_publishes_event(monkeypatch):
    """High-erosion data (all LOST, model_edge_pp=15) should publish edge_erosion.detected."""
    # All-LOST bets with high model edge → extreme erosion
    df = _make_ledger(n=50, stat="pts", n_won=0, pnl_loss=-10.0, model_edge_pp=15.0)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    received: list = []
    mock_bus = MagicMock()
    mock_bus.publish.side_effect = lambda name, source, payload: received.append(
        {"name": name, "source": source, "payload": payload}
    )

    L36.set_event_bus(mock_bus)
    try:
        L36.compute_angle_metrics(window_n=50, min_n=30)
    finally:
        L36.set_event_bus(None)  # always reset so other tests are unaffected

    assert len(received) >= 1, "Expected at least one edge_erosion.detected event"
    evt = received[0]
    assert evt["name"] == "edge_erosion.detected"
    assert evt["source"] == "L36"
    payload = evt["payload"]
    assert payload["stat"] == "pts"
    assert payload["severity"] in ("WARN", "QUARANTINED")
    assert payload["erosion_pct"] > 0
    required_keys = {
        "stat", "current_edge", "baseline_edge", "erosion_pct",
        "threshold", "severity", "window_days", "detected_at",
    }
    assert required_keys <= payload.keys(), f"Missing payload keys: {required_keys - payload.keys()}"


# ---------------------------------------------------------------------------
# Test 18 — no erosion publishes nothing
# ---------------------------------------------------------------------------
def test_no_erosion_publishes_nothing(monkeypatch):
    """All-winning bets with positive EV should not publish any edge_erosion events."""
    df = _make_ledger(n=50, stat="pts", n_won=50, pnl_win=9.09, model_edge_pp=5.0)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    mock_bus = MagicMock()
    L36.set_event_bus(mock_bus)
    try:
        L36.compute_angle_metrics(window_n=50, min_n=30)
    finally:
        L36.set_event_bus(None)

    mock_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Test 19 — publish failure does not break report generation
# ---------------------------------------------------------------------------
def test_publish_failure_does_not_break_report(monkeypatch):
    """If the L46 bus raises on publish, daily_edge_report should still return successfully."""
    df = _make_ledger(n=50, stat="pts", n_won=0, pnl_loss=-10.0, model_edge_pp=15.0)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    exploding_bus = MagicMock()
    exploding_bus.publish.side_effect = RuntimeError("bus exploded")

    L36.set_event_bus(exploding_bus)
    try:
        report = L36.daily_edge_report()
    finally:
        L36.set_event_bus(None)

    # Report must still be returned correctly despite bus failure
    assert "n_angles" in report
    assert report["n_angles"] >= 1
    assert "per_stat_erosion" in report


# ---------------------------------------------------------------------------
# Test 20 — atomic write: report file written via .tmp sibling (no partial writes)
# ---------------------------------------------------------------------------
def test_atomic_write(monkeypatch, tmp_path):
    """daily_edge_report should write via .tmp file + os.replace (atomic)."""
    import os

    df = _make_ledger(n=50, n_won=35)
    monkeypatch.setattr(L36, "_load_bets", lambda: df)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = tmp_path / f"edge_erosion_report_{today}.json"
    tmp_path_sibling = report_path.with_suffix(".tmp.json")

    written_via_tmp = []
    original_replace = os.replace

    def spy_replace(src, dst):
        if "edge_erosion_report" in str(dst):
            written_via_tmp.append((src, dst))
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)

    report = L36.daily_edge_report()

    # The file must exist and be valid JSON
    assert report_path.exists(), "Report file should exist after daily_edge_report()"
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert "metrics" in loaded

    # os.replace must have been called (proving atomic pattern)
    assert len(written_via_tmp) >= 1, "Expected os.replace call for atomic report write"
    # tmp file must no longer exist (was replaced/moved)
    assert not tmp_path_sibling.exists(), ".tmp file should be gone after os.replace"
