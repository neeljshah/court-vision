"""tests/test_bankroll_monitor.py - R17_J4.

Tests the pure metric-computation function and the IO helpers
(atomic JSON write, dashboard render, alert log) using
in-memory DataFrames so no real ledger is touched.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bankroll_monitor_daemon import (  # noqa: E402
    append_alerts,
    atomic_write_json,
    compute_metrics,
    render_dashboard,
    tick,
)


NOW = datetime(2026, 5, 26, 18, 0, 0, tzinfo=timezone.utc)


def _row(**kw):
    base = dict(
        bet_id="x", placed_at=NOW.isoformat(), game_id="g1", player_id=1,
        player="P", team="SAS", stat="pts", line=10.0, side="OVER",
        book="pin", american_odds=-110, stake=10.0, model_pred=11.0,
        model_prob=0.55, model_edge=0.05, kelly_pct=0.02,
        status="won", settled_at=NOW.isoformat(), actual_stat=12.0,
        profit_loss=9.09, bankroll_after=1009.09, strategy="default",
    )
    base.update(kw)
    return base


def _df(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Metric tests                                                                #
# --------------------------------------------------------------------------- #
def test_current_bankroll_settled_vs_pending():
    """Pending stakes must NOT subtract from current_bankroll; only settled P&L does."""
    df = _df([
        _row(status="won", profit_loss=50.0, stake=50.0),
        _row(status="lost", profit_loss=-25.0, stake=25.0),
        _row(status="pending", profit_loss=0.0, stake=100.0, kelly_pct=0.05),
    ])
    m = compute_metrics(df, start_bankroll=1000.0, now=NOW)
    assert m["current_bankroll"] == pytest.approx(1025.0)
    assert m["pending_exposure"] == pytest.approx(100.0)
    assert m["available_bankroll"] == pytest.approx(925.0)
    assert m["n_open_positions"] == 1


def test_daily_weekly_monthly_pnl_windows():
    """Window-based P&L sums only settled bets in the window."""
    rows = [
        _row(placed_at=(NOW - timedelta(days=60)).isoformat(), profit_loss=100.0, status="won"),
        _row(placed_at=(NOW - timedelta(days=10)).isoformat(), profit_loss=50.0, status="won"),
        _row(placed_at=(NOW - timedelta(days=3)).isoformat(), profit_loss=-30.0, status="lost"),
        _row(placed_at=NOW.isoformat(), profit_loss=20.0, status="won"),
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert m["daily_pnl"] == pytest.approx(20.0)
    # Monday-based week: NOW is Tuesday 2026-05-26; window covers Mon-now (3-days-ago is Sat, outside)
    assert m["weekly_pnl"] == pytest.approx(20.0)
    # Month-to-date covers all of May 2026
    assert m["monthly_pnl"] == pytest.approx(40.0)  # -30 + 20 + 50 only if 10 days ago is within May
    # full session
    assert m["current_bankroll"] == pytest.approx(1000.0 + 140.0)


def test_max_drawdown():
    """Peak-to-trough on the cumulative bankroll curve."""
    # 1000 -> 1100 (+100) -> 800 (-300) -> 900 (+100)
    # peak=1100, trough=800, DD=300, DD_pct = 300/1100 = 0.2727
    rows = [
        _row(placed_at=(NOW - timedelta(days=4)).isoformat(), profit_loss=100.0, status="won"),
        _row(placed_at=(NOW - timedelta(days=3)).isoformat(), profit_loss=-300.0, status="lost"),
        _row(placed_at=(NOW - timedelta(days=2)).isoformat(), profit_loss=100.0, status="won"),
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert m["max_drawdown"] == pytest.approx(300.0)
    assert m["max_drawdown_pct"] == pytest.approx(300.0 / 1100.0, abs=1e-4)


def test_position_concentration():
    """max_stake_in_one_game / current_bankroll on the PENDING side."""
    rows = [
        _row(status="won", profit_loss=50.0),               # bankroll = 1050
        _row(status="pending", stake=200.0, game_id="g1", kelly_pct=0.01),
        _row(status="pending", stake=50.0, game_id="g1", kelly_pct=0.01),  # same game
        _row(status="pending", stake=100.0, game_id="g2", kelly_pct=0.01),
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    # g1 totals 250, g2 totals 100 -> max=250
    assert m["max_stake_in_one_game"] == pytest.approx(250.0)
    assert m["position_concentration_pct"] == pytest.approx(250.0 / 1050.0, abs=1e-4)


def test_kelly_overhang():
    """Sum of kelly_pct on pending bets."""
    rows = [
        _row(status="pending", kelly_pct=0.10, stake=10.0),
        _row(status="pending", kelly_pct=0.12, stake=10.0),
        _row(status="won", kelly_pct=0.50, profit_loss=10.0),  # excluded
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert m["kelly_overhang"] == pytest.approx(0.22)


# --------------------------------------------------------------------------- #
# Alarm tests                                                                 #
# --------------------------------------------------------------------------- #
def test_alarm_kelly_overhang_urgent():
    rows = [_row(status="pending", kelly_pct=0.35, stake=10.0)]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    levels = {a["level"] for a in m["alarms"]}
    rules = {a["rule"] for a in m["alarms"]}
    assert "URGENT" in levels
    assert "kelly_overhang > 30%" in rules


def test_alarm_position_concentration_warn():
    rows = [
        _row(status="pending", stake=200.0, kelly_pct=0.01, game_id="g1"),
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert any(a["rule"] == "position_concentration > 15%" for a in m["alarms"])


def test_alarm_daily_loss_circuit_breaker():
    rows = [
        _row(placed_at=NOW.isoformat(), profit_loss=-250.0, status="lost", stake=250.0),
    ]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    stop_alarms = [a for a in m["alarms"] if a["level"] == "STOP"]
    assert any("daily_pnl" in a["rule"] for a in stop_alarms)


def test_alarm_max_drawdown_stop():
    rows = [
        _row(placed_at=(NOW - timedelta(days=5)).isoformat(), profit_loss=500.0, status="won"),
        _row(placed_at=(NOW - timedelta(days=4)).isoformat(), profit_loss=-600.0, status="lost"),
    ]
    # peak 1500, trough 900 -> DD=600/1500=0.40
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert m["max_drawdown_pct"] > 0.30
    assert any(a["rule"] == "max_drawdown > 30%" for a in m["alarms"])


def test_no_alarms_when_clean():
    rows = [_row(status="pending", kelly_pct=0.02, stake=20.0)]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    assert m["alarms"] == []


# --------------------------------------------------------------------------- #
# IO tests                                                                    #
# --------------------------------------------------------------------------- #
def test_atomic_write_json(tmp_path):
    """JSON state must arrive atomically: no .tmp file left behind, content matches."""
    out = tmp_path / "state.json"
    atomic_write_json(out, {"a": 1, "b": "hi"})
    assert out.exists()
    assert not out.with_suffix(".json.tmp").exists()
    assert json.loads(out.read_text()) == {"a": 1, "b": "hi"}


def test_dashboard_render_contains_key_fields():
    rows = [_row(status="pending", stake=50.0, kelly_pct=0.025)]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    md = render_dashboard(m)
    assert "Bankroll Dashboard" in md
    assert "$1000.00" in md  # start bankroll
    assert "Pending exposure" in md
    assert "Kelly overhang" in md


def test_append_alerts_creates_log(tmp_path):
    rows = [_row(status="pending", kelly_pct=0.40, stake=10.0)]
    m = compute_metrics(_df(rows), start_bankroll=1000.0, now=NOW)
    p = tmp_path / "risk_alerts.md"
    append_alerts(p, m)
    assert p.exists()
    assert "URGENT" in p.read_text()


def test_tick_end_to_end(tmp_path):
    """Full tick with a temp ledger file -> state.json, dashboard.md written."""
    led = tmp_path / "ledger.csv"
    state = tmp_path / "state.json"
    dash = tmp_path / "dashboard.md"
    alerts = tmp_path / "alerts.md"
    df = _df([
        _row(status="won", profit_loss=50.0),
        _row(status="pending", stake=50.0, kelly_pct=0.025, game_id="g1"),
    ])
    df.to_csv(led, index=False)

    m = tick(start_bankroll=1000.0, ledger_path=led,
             state_path=state, dashboard_path=dash, alerts_path=alerts)
    assert state.exists() and dash.exists()
    assert m["current_bankroll"] == pytest.approx(1050.0)
    assert m["pending_exposure"] == pytest.approx(50.0)
    assert m["available_bankroll"] == pytest.approx(1000.0)
