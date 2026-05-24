"""tests/test_live_edge_eval.py — cycle 88j (loop 5).

Offline unit tests for scripts/live_edge_eval.py — the mid-game bet
re-evaluator. Both the live snapshot and the cycle-88b project_final()
function are mocked; no nba_api / model / disk I/O beyond tmp_path
round-trip of CSVs.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import live_edge_eval as lee   # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _bet(player="Nikola Jokic", stat="PTS", line=28.5, side="OVER",
         odds=-110, pregame=31.2):
    """Build one bet-log row (cycle-68 lowercase-keys variant)."""
    return {
        "player": player,
        "stat": stat,
        "line": str(line),
        "side": side,
        "odds": str(odds),
        "model": str(pregame),
        "edge": "2.7",
        "prob": "0.55",
        "ev_per_dollar": "0.05",
        "kelly_pct": "1.0",
        "kelly_stake": "10.0",
    }


def _snap(players, period=3, clock="6:00", status="LIVE", game_id="0099900001"):
    """Build a minimal cycle-88 live snapshot."""
    return {
        "game_id": game_id,
        "captured_at": "2026-05-24T20:42:00+00:00",
        "game_status": status,
        "period": period,
        "clock": clock,
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 78, "away_score": 70,
        "players": players,
    }


def _player(name, **stats):
    """Player record with sensible defaults for any missing stat."""
    base = {"player_id": 1, "name": name, "team": "DEN",
            "min": 22.0, "pts": 0, "reb": 0, "ast": 0,
            "fg3m": 0, "stl": 0, "blk": 0, "tov": 0, "pf": 0,
            "is_starter": True}
    base.update(stats)
    return base


# ── 1. player not in any snapshot → "NOT PLAYING" action ─────────────────────

def test_player_not_in_snapshot():
    """Bet on a player nobody's tracking → action="NOT PLAYING"."""
    bet = _bet(player="Mystery Guy", stat="PTS", line=20.0, side="OVER")
    snapshots = [_snap([_player("Nikola Jokic", pts=18)])]
    result = lee.evaluate_bet(bet, snapshots)
    assert result["action"] == "NOT PLAYING"
    assert result["current"] is None
    assert result["proj_final"] is None
    assert result["new_ev"] is None


# ── 2. FINAL game → projection equals current ────────────────────────────────

def test_final_game_projection_equals_current(monkeypatch):
    """When game_status='FINAL', proj_final == current and projector NOT called."""
    bet = _bet(player="Paolo Banchero", stat="PTS", line=28.5, side="OVER")
    players = [_player("Paolo Banchero", pts=31)]
    snapshots = [_snap(players, period=4, clock="0:00", status="FINAL")]

    # If the projector gets called the test fails — final should not need it.
    def _boom(*a, **kw):
        raise AssertionError("project_final should not be called on FINAL game")
    monkeypatch.setattr(lee.pig, "project_final", _boom)

    result = lee.evaluate_bet(bet, snapshots)
    assert result["current"] == 31.0
    assert result["proj_final"] == 31.0
    # Game ended OVER 28.5 → realized winner is OVER. Action should be
    # LET IT RIDE since the bet hit.
    assert result["action"] == "LET IT RIDE"
    assert "FINAL" in result["game_status"]


# ── 3. OVER with proj_final >> line → LET IT RIDE ────────────────────────────

def test_over_bet_still_let_it_ride(monkeypatch):
    """proj_final 3+ stat-units above line → strong +EV → LET IT RIDE."""
    bet = _bet(player="Nikola Jokic", stat="PTS", line=28.5, side="OVER",
               odds=-110, pregame=31.2)
    players = [_player("Nikola Jokic", pts=18, pf=1)]
    snapshots = [_snap(players, period=3, clock="0:00", status="LIVE")]

    # Mock the projector to return a large final.
    monkeypatch.setattr(lee.pig, "project_final",
                        lambda current_stat, *a, **kw: 35.0)

    result = lee.evaluate_bet(bet, snapshots)
    assert result["proj_final"] == 35.0
    assert result["current"] == 18.0
    assert result["new_edge"] == pytest.approx(35.0 - 28.5)   # +6.5
    assert result["new_ev"] > lee.LET_IT_RIDE_THRESHOLD
    assert result["action"] == "LET IT RIDE"


# ── 4. OVER with proj_final << line → HEDGE ──────────────────────────────────

def test_over_bet_now_hedge(monkeypatch):
    """proj_final well below line → -EV → HEDGE."""
    bet = _bet(player="LeBron James", stat="AST", line=8.5, side="OVER",
               odds=-110, pregame=9.1)
    players = [_player("LeBron James", ast=3, pf=2)]
    snapshots = [_snap(players, period=3, clock="6:00", status="LIVE")]

    monkeypatch.setattr(lee.pig, "project_final",
                        lambda current_stat, *a, **kw: 6.5)

    result = lee.evaluate_bet(bet, snapshots)
    assert result["proj_final"] == 6.5
    assert result["new_edge"] == pytest.approx(6.5 - 8.5)   # -2.0
    assert result["new_ev"] < lee.HEDGE_THRESHOLD
    assert result["action"] == "HEDGE"


# ── 5. close-to-even bet → MONITOR ───────────────────────────────────────────

def test_close_to_even_monitor(monkeypatch):
    """proj_final right on the line → near-zero EV → MONITOR."""
    bet = _bet(player="Anthony Edwards", stat="PTS", line=24.5, side="OVER",
               odds=-110, pregame=25.0)
    players = [_player("Anthony Edwards", pts=12, pf=1)]
    snapshots = [_snap(players, period=3, clock="0:00", status="LIVE")]

    # Project exactly on the line → P(over)=0.5 → EV = 0.5 * 0.909 - 0.5 ≈ -0.045
    monkeypatch.setattr(lee.pig, "project_final",
                        lambda current_stat, *a, **kw: 24.5)

    result = lee.evaluate_bet(bet, snapshots)
    assert result["proj_final"] == 24.5
    assert result["new_edge"] == pytest.approx(0.0, abs=1e-9)
    # At -110 odds with p=0.5: EV ≈ -0.0455 — inside MONITOR band (>-0.05)
    assert lee.HEDGE_THRESHOLD < result["new_ev"] < lee.LET_IT_RIDE_THRESHOLD
    assert result["action"] == "MONITOR"


# ── 6. round-trip: load bet log + write updated CSV ──────────────────────────

def test_load_and_write_round_trip(tmp_path, monkeypatch):
    """Write a bet log, evaluate it, save updated CSV, reload it back."""
    # Write a cycle-68-style bet log with two rows.
    bet_path = tmp_path / "bets.csv"
    with open(bet_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "date", "player", "stat", "line", "side",
                    "model", "edge", "prob", "odds", "ev_per_dollar",
                    "kelly_pct", "kelly_stake", "bankroll"])
        w.writerow(["2026-05-24T19:00:00", "2026-05-24",
                    "Nikola Jokic", "PTS", "28.5", "OVER",
                    "31.2", "2.7", "0.55", "-110", "0.05",
                    "1.0", "10.0", "1000.00"])
        w.writerow(["2026-05-24T19:00:00", "2026-05-24",
                    "Stephen Curry", "FG3M", "4.5", "UNDER",
                    "3.5", "-1.0", "0.71", "-110", "0.35",
                    "5.0", "50.0", "1000.00"])

    bets = lee.load_bet_log(str(bet_path))
    assert len(bets) == 2
    assert bets[0]["player"] == "Nikola Jokic"
    assert bets[1]["stat"] == "FG3M"

    # Mock projector + snapshot.
    monkeypatch.setattr(lee.pig, "project_final",
                        lambda current_stat, *a, **kw: 32.0
                        if current_stat > 5 else 2.8)
    snapshots = [_snap([
        _player("Nikola Jokic", pts=18, pf=1),
        _player("Stephen Curry", fg3m=1, pf=1),
    ], period=3, clock="6:00", status="LIVE")]

    results = lee.evaluate_all(bets, snapshots)
    assert len(results) == 2

    out_path = tmp_path / "bets_live.csv"
    n = lee.write_updated_csv(str(out_path), results)
    assert n == 2

    # Read back & verify schema + values round-tripped.
    with open(out_path, "r", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        rows = list(rdr)
    assert len(rows) == 2
    assert rows[0]["player"] == "Nikola Jokic"
    assert float(rows[0]["proj_final"]) == pytest.approx(32.0)
    assert rows[0]["action"] in lee.ACTIONS
    assert rows[1]["player"] == "Stephen Curry"
    assert float(rows[1]["proj_final"]) == pytest.approx(2.8)
    # Stephen Curry UNDER 4.5 with proj 2.8 → strong +EV under → LET IT RIDE
    assert rows[1]["action"] == "LET IT RIDE"


# ── 7. bonus: pure helpers ───────────────────────────────────────────────────

def test_classify_action_bands():
    assert lee.classify_action(0.20) == "LET IT RIDE"
    assert lee.classify_action(0.05) == "LET IT RIDE"
    assert lee.classify_action(0.00) == "MONITOR"
    assert lee.classify_action(-0.04) == "MONITOR"
    assert lee.classify_action(-0.05) == "HEDGE"
    assert lee.classify_action(-0.30) == "HEDGE"


def test_remaining_sigma_shrinks_with_time():
    """Sigma at start of game > sigma at end (variance-additive intuition)."""
    s_start = lee.remaining_sigma("pts", period=1, clock_str="12:00")
    s_mid   = lee.remaining_sigma("pts", period=3, clock_str="0:00")  # 36/48
    s_end   = lee.remaining_sigma("pts", period=4, clock_str="0:00")
    assert s_start > s_mid > s_end
    # Sigma at end is the floor (10% of baseline).
    assert s_end == pytest.approx(lee._BASELINE_SIGMA["pts"] * 0.10)


def test_hit_probability_symmetry():
    """OVER and UNDER probs at the same line+sigma sum to 1."""
    p_o = lee.hit_probability(proj_final=25, line=22, side="OVER", sigma=3)
    p_u = lee.hit_probability(proj_final=25, line=22, side="UNDER", sigma=3)
    assert p_o + p_u == pytest.approx(1.0, abs=1e-9)
    assert p_o > 0.5  # proj 25 > line 22 → OVER more likely
