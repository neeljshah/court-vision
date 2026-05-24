"""tests/test_live_alerts.py — cycle 88k (loop 5).

Offline tests for scripts/live_alerts.py. We never hit cdn.nba.com, never
play the terminal bell (ring_bell=False), and never touch the user's real
data/bets/ or data/alerts/ — every test routes through tmp_path via the
project_dir override.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from typing import List

import pytest

PROJECT_DIR_REAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR_REAL not in sys.path:
    sys.path.insert(0, PROJECT_DIR_REAL)

import scripts.live_alerts as la  # noqa: E402


# ── shared fixtures ──────────────────────────────────────────────────────────

DATE = "2026-05-24"


def _player(name, *, pid=1001, team="LAL", min_=20.0, pts=12, reb=4, ast=3,
            fg3m=2, stl=1, blk=0, tov=1, pf=2, starter=True):
    return {
        "player_id": pid, "name": name, "team": team,
        "min": min_, "pts": pts, "reb": reb, "ast": ast,
        "fg3m": fg3m, "stl": stl, "blk": blk, "tov": tov, "pf": pf,
        "is_starter": starter,
    }


def _snapshot(*, game_id="0022400999", period=2, clock="6:00",
              home="LAL", away="DEN", home_score=55, away_score=50,
              players=None, status="LIVE"):
    return {
        "game_id":     game_id,
        "captured_at": "2026-05-24T20:00:00+00:00",
        "game_status": status,
        "period":      period,
        "clock":       clock,
        "home_team":   home,
        "away_team":   away,
        "home_score":  home_score,
        "away_score":  away_score,
        "players":     players or [],
    }


def _write_snapshot(tmp_path, snap, ts=1000):
    live_dir = tmp_path / "data" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    path = live_dir / f"{snap['game_id']}_{ts}.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    return str(path)


def _write_bets(tmp_path, rows: List[dict]):
    bets_dir = tmp_path / "data" / "bets"
    bets_dir.mkdir(parents=True, exist_ok=True)
    path = bets_dir / f"{DATE}.csv"
    cols = ["timestamp", "date", "player", "stat", "line", "side",
            "model", "edge", "prob", "odds", "ev_per_dollar",
            "kelly_pct", "kelly_stake", "bankroll"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            full = {c: "" for c in cols}
            full.update(r)
            w.writerow(full)
    return str(path)


def _write_predictions(tmp_path, rows: List[dict]):
    pred_dir = tmp_path / "data" / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    path = pred_dir / f"{DATE}.csv"
    cols = ["date", "game_id", "player_id", "player", "team", "opp",
            "venue", "stat", "pred"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            full = {c: "" for c in cols}
            full.update(r)
            w.writerow(full)
    return str(path)


def _bet(player, stat, line, side="OVER", odds=-110, ev=0.04, ts="2026-05-24T18:00:00"):
    return {
        "timestamp": ts, "date": DATE, "player": player, "stat": stat,
        "line": line, "side": side, "model": line + 1.5, "edge": 1.5,
        "prob": 0.55, "odds": odds, "ev_per_dollar": ev,
        "kelly_pct": "2.0", "kelly_stake": "20.0", "bankroll": "1000",
    }


# ── 1. EDGE_FLIP ─────────────────────────────────────────────────────────────

def test_edge_flip_fires_when_live_proj_crosses_below_line(tmp_path, monkeypatch):
    """Pregame pred 31 PTS, OVER 28.5 (+EV). Live proj 26 → bet flipped.

    We monkeypatch _project_snapshot_rows to return a deterministic projection
    of 26 PTS for our test player — no need to invoke the full projector.
    """
    _write_bets(tmp_path, [_bet("Jokic", "PTS", 28.5, "OVER")])
    _write_predictions(tmp_path, [
        {"player": "Jokic", "stat": "pts", "pred": 31.0},
    ])
    snap_path = _write_snapshot(
        tmp_path, _snapshot(players=[_player("Jokic", pts=15, team="DEN")]))

    monkeypatch.setattr(la, "_project_snapshot_rows", lambda snap: [
        {"name": "Jokic", "stat": "pts", "projected_final": 26.0},
    ])
    stream = io.StringIO()
    alerts = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"EDGE_FLIP"}, ring_bell=False, stream=stream,
        snapshot_paths=[snap_path],
    )
    assert len(alerts) == 1
    assert alerts[0]["type"] == "EDGE_FLIP"
    assert alerts[0]["player"] == "Jokic"
    assert "Jokic" in stream.getvalue()
    # The log file should now have exactly one JSON line.
    log_path = tmp_path / "data" / "alerts" / f"{DATE}.log"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["type"] == "EDGE_FLIP"


# ── 2. PROJECTION_SHIFT honors threshold ─────────────────────────────────────

def test_projection_shift_only_fires_when_delta_exceeds_threshold(tmp_path, monkeypatch):
    """Pregame=20 PTS, live=22.5 (delta 2.5). Threshold 3.0 → no alert.
    Same setup with threshold 2.0 → alert."""
    _write_bets(tmp_path, [_bet("Curry", "PTS", 22.5, "OVER")])
    _write_predictions(tmp_path, [{"player": "Curry", "stat": "pts", "pred": 20.0}])
    snap_path = _write_snapshot(
        tmp_path, _snapshot(players=[_player("Curry", pts=12)]))

    monkeypatch.setattr(la, "_project_snapshot_rows", lambda snap: [
        {"name": "Curry", "stat": "pts", "projected_final": 22.5},
    ])
    # threshold 3.0 → no shift (delta=2.5)
    alerts_strict = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"PROJECTION_SHIFT"}, threshold=3.0,
        ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[snap_path],
    )
    assert alerts_strict == []

    # Reset state file so the next call doesn't see prior keys.
    state = tmp_path / "data" / "alerts" / f"{DATE}_state.json"
    if state.exists():
        state.unlink()

    # threshold 2.0 → fires
    alerts_loose = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"PROJECTION_SHIFT"}, threshold=2.0,
        ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[snap_path],
    )
    assert len(alerts_loose) == 1
    assert alerts_loose[0]["type"] == "PROJECTION_SHIFT"
    assert abs(alerts_loose[0]["delta"] - 2.5) < 1e-6


# ── 3. FOUL_TROUBLE only for bet-on players ──────────────────────────────────

def test_foul_trouble_fires_for_bet_player_with_4_fouls(tmp_path):
    _write_bets(tmp_path, [_bet("Embiid", "PTS", 28.5, "OVER")])
    snap = _snapshot(players=[
        _player("Embiid", pf=4, team="PHI"),
        _player("Maxey", pf=5, team="PHI"),     # has 5 fouls but no bet
    ])
    snap_path = _write_snapshot(tmp_path, snap)
    alerts = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"FOUL_TROUBLE"}, ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[snap_path],
    )
    assert len(alerts) == 1
    assert alerts[0]["player"] == "Embiid"
    assert alerts[0]["pf"] == 4


# ── 4. BLOWOUT_RISK requires Q4 and 20+ margin ───────────────────────────────

def test_blowout_risk_fires_when_margin_20_in_q4(tmp_path):
    _write_bets(tmp_path, [_bet("Booker", "PTS", 24.5, "OVER")])
    booker = _player("Booker", team="PHX", pts=20)
    # Q4, margin 22 (home 110 - away 88) → blowout
    snap_q4 = _snapshot(period=4, clock="8:00",
                          home="PHX", away="SAS",
                          home_score=110, away_score=88,
                          players=[booker])
    p1 = _write_snapshot(tmp_path, snap_q4, ts=1000)
    alerts = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"BLOWOUT_RISK"}, ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[p1],
    )
    assert len(alerts) == 1
    assert alerts[0]["type"] == "BLOWOUT_RISK"
    assert alerts[0]["margin"] == 22

    # Same situation in Q2 with bigger margin → no blowout alert.
    state = tmp_path / "data" / "alerts" / f"{DATE}_state.json"
    if state.exists():
        state.unlink()
    snap_q2 = _snapshot(period=2, clock="2:00",
                          home="PHX", away="SAS",
                          home_score=70, away_score=40,
                          players=[booker])
    p2 = _write_snapshot(tmp_path, snap_q2, ts=2000)
    alerts2 = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"BLOWOUT_RISK"}, ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[p2],
    )
    assert alerts2 == []


# ── 5. State persistence: already-fired alerts don't repeat ──────────────────

def test_already_fired_alert_does_not_re_fire(tmp_path):
    _write_bets(tmp_path, [_bet("Tatum", "PTS", 30.5, "OVER")])
    snap = _snapshot(players=[_player("Tatum", pf=5, team="BOS")])
    snap_path = _write_snapshot(tmp_path, snap)
    first = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"FOUL_TROUBLE"}, ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[snap_path],
    )
    assert len(first) == 1
    # Second call with the same conditions → no NEW alerts.
    second = la.process_once(
        date_str=DATE, project_dir=str(tmp_path),
        types={"FOUL_TROUBLE"}, ring_bell=False, stream=io.StringIO(),
        snapshot_paths=[snap_path],
    )
    assert second == []
    # The state file should record exactly one fired alert key.
    state_path = tmp_path / "data" / "alerts" / f"{DATE}_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["fired"]) == 1


# ── 6. Daemon honors --interval (mock sleep) ─────────────────────────────────

def test_daemon_honors_interval_via_mock_sleep(tmp_path):
    """run_daemon should call sleep_fn(interval) between ticks and respect max_ticks."""
    _write_bets(tmp_path, [])    # no bets, no alerts — we're only checking loop control
    sleeps: list = []
    ticks = la.run_daemon(
        interval=7.5, max_ticks=3, project_dir=str(tmp_path),
        sleep_fn=lambda s: sleeps.append(s),
        ring_bell=False, stream=io.StringIO(),
        types={"FOUL_TROUBLE"},   # cheap detector
    )
    assert ticks == 3
    # Sleep happens AFTER each tick except possibly the last — we accept either
    # 2 or 3 sleeps depending on loop ordering. Each MUST be the interval.
    assert all(abs(s - 7.5) < 1e-9 for s in sleeps)
    assert 2 <= len(sleeps) <= 3
