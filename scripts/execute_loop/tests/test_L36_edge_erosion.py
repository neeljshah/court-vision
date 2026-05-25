"""test_L36_edge_erosion.py — Unit tests for L36_edge_erosion.py

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L36_edge_erosion.py -v
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
