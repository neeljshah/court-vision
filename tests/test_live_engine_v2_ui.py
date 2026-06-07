"""tests/test_live_engine_v2_ui.py — Phase D regression set: alert_dedup + dashboard."""
from __future__ import annotations

import time

import pytest

from src.live.alert_dedup import AlertDedup


# ── alert_dedup ─────────────────────────────────────────────────────────
def test_alert_dedup_emit_first_then_cooldown_digest():
    ad = AlertDedup(cooldown_sec=10.0, delta_floor=0.0,
                    digest_window_sec=2.0)
    a, msg1, sev1 = ad.maybe_alert(
        player="Jokic", stat="pts", side="over", line=24.5, book="pin",
        odds=-110, projection_old=25.0, projection_new=30.0,
        ev_new=0.08, severity="medium")
    assert a == "emit"
    assert "Jokic" in msg1
    # Second alert for the same key within cooldown → digest.
    a2, key2, _ = ad.maybe_alert(
        player="Jokic", stat="pts", side="over", line=24.5, book="pin",
        odds=-110, projection_old=30.0, projection_new=32.0,
        ev_new=0.10, severity="medium")
    assert a2 == "digest"
    assert key2 == "medium"


def test_alert_dedup_drops_below_delta_floor():
    ad = AlertDedup(delta_floor=0.5)
    a, reason, _ = ad.maybe_alert(
        player="X", stat="pts", side="over", line=20, book="pin",
        odds=-110, projection_old=20.0, projection_new=20.2,
        ev_new=0.05, severity="medium")
    assert a == "drop"
    assert reason == "delta_below_floor"


def test_alert_dedup_drops_below_min_severity():
    ad = AlertDedup(min_severity="high")
    a, reason, _ = ad.maybe_alert(
        player="X", stat="pts", side="over", line=20, book="pin",
        odds=-110, projection_old=None, projection_new=25.0,
        ev_new=0.05, severity="medium")
    assert a == "drop"
    assert reason == "below_min_severity"


def test_alert_dedup_digest_window_flushes():
    ad = AlertDedup(cooldown_sec=10.0, delta_floor=0.0,
                    digest_window_sec=0.05)
    ad.maybe_alert(
        player="P", stat="pts", side="over", line=20, book="pin",
        odds=-110, projection_old=20.0, projection_new=25.0,
        ev_new=0.06, severity="medium")
    ad.maybe_alert(   # goes into digest because cooldown active
        player="P", stat="pts", side="over", line=20, book="pin",
        odds=-110, projection_old=25.0, projection_new=27.0,
        ev_new=0.08, severity="medium")
    time.sleep(0.08)
    digests = ad.pending_digests()
    assert len(digests) == 1
    sev, body = digests[0]
    assert sev == "medium"
    assert "DIGEST" in body


def test_alert_dedup_format_includes_delta_and_ev():
    ad = AlertDedup(delta_floor=0.0)
    a, msg, _ = ad.maybe_alert(
        player="Jokic", stat="reb", side="under", line=12.5, book="pin",
        odds=-105, projection_old=14.0, projection_new=11.0,
        ev_new=0.07, ev_old=0.02, severity="high")
    assert a == "emit"
    assert "REB UNDER 12.5" in msg
    assert "Δ-3.0" in msg or "Δ-3" in msg
    assert "EV +7.0%" in msg
    assert "was +2.0%" in msg


# ── dashboard render ────────────────────────────────────────────────────
def test_dashboard_renders_with_no_data():
    pytest.importorskip("rich")
    from scripts.live_dashboard_v2 import DashboardApp
    app = DashboardApp()
    out = app.render_snapshot_text()
    assert "Waiting" in out or "snapshot" in out.lower()


def test_dashboard_renders_with_seeded_state():
    pytest.importorskip("rich")
    from scripts.live_dashboard_v2 import DashboardApp
    app = DashboardApp()
    # Manually seed the state without going through the bus.
    app.state.on_snapshot({"game_id": "0042400315", "snapshot": {
        "game_id": "0042400315", "game_status": "LIVE",
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 95, "away_score": 90, "period": 3,
        "clock": "PT05M30.00S",
        "players": [{"player_id": 1, "name": "Jokic", "team": "DEN",
                     "pts": 22, "min": 28, "pf": 4}],
    }})
    app.state.on_pbp("pbp.foul", {
        "period": 3, "clock": "PT05M30S", "description": "P.FOUL",
        "player_name": "Jokic",
    })
    app.state.on_bet({
        "game_id": "0042400315", "player_id": 1, "name": "Jokic",
        "team": "DEN", "stat": "pts", "side": "over", "line": 24.5,
        "book": "pin", "odds": -110, "ev": 0.08, "kelly": 0.10,
        "tier": "S", "projected_final": 34.0,
    })
    app.state.on_alert("high", "[HIGH][NEW_EDGE] Jokic PTS OVER 24.5 — EV +8.0%")
    out = app.render_snapshot_text()
    assert "Jokic" in out
    assert "DEN" in out and "LAL" in out
    assert "foul" in out.lower()
