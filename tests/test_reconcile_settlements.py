"""Tests for scripts/reconcile_settlements.py (R24_Q8).

Coverage:
  1. All-match case — no mismatches reported.
  2. OVER WIN matches.
  3. UNDER WIN matches.
  4. PUSH detected when stat == line.
  5. False-loss (ledger says lost but expected won) flagged.
  6. False-win (ledger says won but expected lost) flagged.
  7. Missing boxscore handled gracefully.
  8. Synthetic rows (Player_<id> / team=SYN) excluded by default.
  9. Push misclassified as won/lost is flagged.
 10. DNP player who got settled gets `player_dnp_but_settled`.
 11. Actual stat disagreement (boxscore moved by >0.5) flagged.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import scripts.reconcile_settlements as recon  # noqa: E402


# --------------------------------------------------------------------------- #
# Test helpers                                                                #
# --------------------------------------------------------------------------- #
LEDGER_COLS = [
    "bet_id", "placed_at", "game_id", "player_id", "player", "team",
    "stat", "line", "side", "book", "american_odds", "stake",
    "model_pred", "model_prob", "model_edge", "kelly_pct",
    "status", "settled_at", "actual_stat", "profit_loss", "bankroll_after",
    "strategy",
]


def _write_q(qb_dir: Path, game_id: str, period: int,
              players: List[Dict[str, Any]]) -> Path:
    qb_dir.mkdir(parents=True, exist_ok=True)
    p = qb_dir / f"{game_id}_q{period}.json"
    json.dump({"game_id": game_id, "period": period,
                "players": players, "teams": []},
                open(p, "w", encoding="utf-8"))
    return p


def _player(name: str, pid: int = 1, pts: float = 0, reb: float = 0,
             ast: float = 0, fg3m: float = 0, stl: float = 0,
             blk: float = 0, to: float = 0) -> Dict[str, Any]:
    return {
        "player_name": name, "player_id": pid,
        "team_abbreviation": "TST",
        "pts": pts, "reb": reb, "ast": ast,
        "fg3m": fg3m, "stl": stl, "blk": blk, "to": to,
    }


def _make_box(qb_dir: Path, game_id: str,
               players_per_q: Dict[int, List[Dict[str, Any]]]) -> None:
    for q, pl in players_per_q.items():
        _write_q(qb_dir, game_id, q, pl)


def _bet(bet_id: str, *, game_id: str, player: str, stat: str,
          line: float, side: str, status: str,
          actual_stat: float, placed_at: str = None,
          team: str = "TST", player_id: str = "1") -> Dict[str, Any]:
    placed_at = placed_at or _dt.datetime.utcnow().isoformat(timespec="seconds")
    return {
        "bet_id":         bet_id,
        "placed_at":      placed_at,
        "game_id":        game_id,
        "player_id":      player_id,
        "player":         player,
        "team":           team,
        "stat":           stat,
        "line":           f"{line:.2f}",
        "side":           side.upper(),
        "book":           "DK",
        "american_odds":  "-110",
        "stake":          "50.00",
        "model_pred":     "",
        "model_prob":     "",
        "model_edge":     "",
        "kelly_pct":      "",
        "status":         status,
        "settled_at":     placed_at,
        "actual_stat":    f"{actual_stat:.4f}",
        "profit_loss":    "0.00",
        "bankroll_after": "1000.00",
        "strategy":       "default",
    }


def _write_ledger(path: Path, bets: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLS, extrasaction="ignore")
        w.writeheader()
        for b in bets:
            w.writerow(b)


@pytest.fixture
def tmp_env(tmp_path):
    """Return (ledger_path, qb_dir) inside a fresh tmp dir."""
    return tmp_path / "pnl_ledger.csv", tmp_path / "qb"


# --------------------------------------------------------------------------- #
# 1. All-match case                                                           #
# --------------------------------------------------------------------------- #
def test_all_match_reports_zero_mismatches(tmp_env):
    ledger, qb = tmp_env
    # Jokic scores 30 total across 4 quarters.
    _make_box(qb, "0022500001", {
        1: [_player("Nikola Jokic", pid=203999, pts=8)],
        2: [_player("Nikola Jokic", pid=203999, pts=7)],
        3: [_player("Nikola Jokic", pid=203999, pts=8)],
        4: [_player("Nikola Jokic", pid=203999, pts=7)],
    })
    bets = [
        _bet("b1", game_id="0022500001", player="Nikola Jokic",
              player_id="203999", stat="pts", line=25.5,
              side="OVER", status="won", actual_stat=30.0),
    ]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_real_settled"] == 1
    assert r["n_matched"] == 1
    assert r["n_mismatched"] == 0
    assert r["mismatch_categories"].get("ok") == 1


# --------------------------------------------------------------------------- #
# 2. OVER WIN                                                                 #
# --------------------------------------------------------------------------- #
def test_over_win_matches(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500002", {
        1: [_player("Devin Booker", pid=1, pts=15)],
        2: [_player("Devin Booker", pid=1, pts=15)],
        3: [_player("Devin Booker", pid=1, pts=10)],
        4: [_player("Devin Booker", pid=1, pts=10)],
    })  # total 50
    bets = [_bet("b2", game_id="0022500002", player="Devin Booker",
                  stat="pts", line=29.5, side="OVER",
                  status="won", actual_stat=50.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 0
    assert r["n_matched"] == 1


# --------------------------------------------------------------------------- #
# 3. UNDER WIN                                                                #
# --------------------------------------------------------------------------- #
def test_under_win_matches(tmp_env):
    ledger, qb = tmp_env
    # Player only scores 12, UNDER 25.5 wins.
    _make_box(qb, "0022500003", {
        1: [_player("Cold Shooter", pid=1, pts=4)],
        2: [_player("Cold Shooter", pid=1, pts=4)],
        3: [_player("Cold Shooter", pid=1, pts=2)],
        4: [_player("Cold Shooter", pid=1, pts=2)],
    })  # total 12
    bets = [_bet("b3", game_id="0022500003", player="Cold Shooter",
                  stat="pts", line=25.5, side="UNDER",
                  status="won", actual_stat=12.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 0
    assert r["n_matched"] == 1


# --------------------------------------------------------------------------- #
# 4. PUSH when stat == line                                                   #
# --------------------------------------------------------------------------- #
def test_push_when_stat_equals_line(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500004", {
        1: [_player("Even Stevens", pid=1, pts=6)],
        2: [_player("Even Stevens", pid=1, pts=6)],
        3: [_player("Even Stevens", pid=1, pts=6)],
        4: [_player("Even Stevens", pid=1, pts=7)],
    })  # total 25
    bets = [_bet("b4", game_id="0022500004", player="Even Stevens",
                  stat="pts", line=25.0, side="OVER",
                  status="push", actual_stat=25.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 0
    assert r["mismatch_categories"].get("ok") == 1


# --------------------------------------------------------------------------- #
# 5. False-loss flagged                                                       #
# --------------------------------------------------------------------------- #
def test_false_loss_flagged(tmp_env):
    ledger, qb = tmp_env
    # Player scored 30, OVER 25.5 should have WON; ledger says LOST.
    _make_box(qb, "0022500005", {
        1: [_player("Wrong Loss", pid=1, pts=10)],
        2: [_player("Wrong Loss", pid=1, pts=10)],
        3: [_player("Wrong Loss", pid=1, pts=5)],
        4: [_player("Wrong Loss", pid=1, pts=5)],
    })
    bets = [_bet("b5", game_id="0022500005", player="Wrong Loss",
                  stat="pts", line=25.5, side="OVER",
                  status="lost", actual_stat=30.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 1
    assert r["mismatch_categories"].get("expected_won_got_lost") == 1
    assert r["mismatches"][0]["bet_id"] == "b5"
    assert r["mismatches"][0]["expected_status"] == "won"
    assert r["mismatches"][0]["ledger_status"] == "lost"


# --------------------------------------------------------------------------- #
# 6. False-win flagged                                                        #
# --------------------------------------------------------------------------- #
def test_false_win_flagged(tmp_env):
    ledger, qb = tmp_env
    # Player only scored 10, UNDER 25.5 should win OR OVER should LOSE.
    # Ledger says OVER won. -> expected lost, got won.
    _make_box(qb, "0022500006", {
        1: [_player("Fake Win", pid=1, pts=3)],
        2: [_player("Fake Win", pid=1, pts=3)],
        3: [_player("Fake Win", pid=1, pts=2)],
        4: [_player("Fake Win", pid=1, pts=2)],
    })
    bets = [_bet("b6", game_id="0022500006", player="Fake Win",
                  stat="pts", line=25.5, side="OVER",
                  status="won", actual_stat=10.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 1
    assert r["mismatch_categories"].get("expected_lost_got_won") == 1


# --------------------------------------------------------------------------- #
# 7. Missing boxscore handled                                                  #
# --------------------------------------------------------------------------- #
def test_missing_boxscore_handled(tmp_env):
    ledger, qb = tmp_env
    qb.mkdir(parents=True, exist_ok=True)   # exists but empty
    bets = [_bet("b7", game_id="0022500777", player="Ghost Player",
                  stat="pts", line=25.5, side="OVER",
                  status="won", actual_stat=30.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["mismatch_categories"].get("boxscore_missing") == 1
    # Boxscore_missing is reported as a mismatch (can't verify), n_verified=0.
    assert r["n_verified"] == 0
    assert r["n_mismatched"] == 1


# --------------------------------------------------------------------------- #
# 8. Synthetic rows excluded                                                  #
# --------------------------------------------------------------------------- #
def test_synthetic_rows_excluded_by_default(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500008", {
        1: [_player("Real Star", pid=1, pts=8)],
        2: [_player("Real Star", pid=1, pts=8)],
        3: [_player("Real Star", pid=1, pts=8)],
        4: [_player("Real Star", pid=1, pts=8)],
    })
    bets = [
        # 1 real bet
        _bet("real", game_id="0022500008", player="Real Star",
              stat="pts", line=25.5, side="OVER",
              status="won", actual_stat=32.0),
        # 2 synthetic — Player_<id> + team=SYN
        _bet("syn1", game_id="0022500099", player="Player_12345",
              stat="pts", line=25.5, side="OVER",
              status="won", actual_stat=30.0, team="SYN", player_id="12345"),
        _bet("syn2", game_id="0022500099", player="Player_67890",
              stat="pts", line=25.5, side="UNDER",
              status="lost", actual_stat=30.0, team="SYN", player_id="67890"),
    ]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_in_window"] == 3
    assert r["n_real_settled"] == 1            # only the real one
    assert r["all_synthetic"] is False
    assert r["n_matched"] == 1
    assert r["n_mismatched"] == 0


# --------------------------------------------------------------------------- #
# 9. Push misclassified as won                                                #
# --------------------------------------------------------------------------- #
def test_push_misclassified_as_won_is_flagged(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500009", {
        1: [_player("Tie Game", pid=1, pts=6)],
        2: [_player("Tie Game", pid=1, pts=6)],
        3: [_player("Tie Game", pid=1, pts=6)],
        4: [_player("Tie Game", pid=1, pts=7)],
    })  # total 25
    bets = [_bet("b9", game_id="0022500009", player="Tie Game",
                  stat="pts", line=25.0, side="OVER",
                  status="won", actual_stat=25.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_mismatched"] == 1
    assert r["mismatch_categories"].get("expected_push_got_won") == 1


# --------------------------------------------------------------------------- #
# 10. DNP-but-settled flagged                                                  #
# --------------------------------------------------------------------------- #
def test_dnp_player_but_settled_is_flagged(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500010", {
        1: [_player("Other Guy", pid=99, pts=10)],
        2: [_player("Other Guy", pid=99, pts=10)],
        3: [_player("Other Guy", pid=99, pts=10)],
        4: [_player("Other Guy", pid=99, pts=10)],
    })
    bets = [_bet("b10", game_id="0022500010", player="Phantom Star",
                  player_id="555", stat="pts", line=25.5, side="OVER",
                  status="lost", actual_stat=0.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["mismatch_categories"].get("player_dnp_but_settled") == 1


# --------------------------------------------------------------------------- #
# 11. Actual stat disagreement flagged                                        #
# --------------------------------------------------------------------------- #
def test_actual_stat_disagreement(tmp_env):
    ledger, qb = tmp_env
    # Box says 30, ledger says actual=20 — boxscore moved >0.5 after settle.
    _make_box(qb, "0022500011", {
        1: [_player("Late Score", pid=1, pts=10)],
        2: [_player("Late Score", pid=1, pts=10)],
        3: [_player("Late Score", pid=1, pts=5)],
        4: [_player("Late Score", pid=1, pts=5)],
    })
    bets = [_bet("b11", game_id="0022500011", player="Late Score",
                  stat="pts", line=25.5, side="OVER",
                  status="lost", actual_stat=20.0)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["mismatch_categories"].get("actual_stat_disagreement") == 1
    rec = r["mismatches"][0]
    assert rec["boxscore_actual_stat"] == pytest.approx(30.0)
    assert rec["ledger_actual_stat"] == pytest.approx(20.0)
    assert rec["delta_actual_stat"] == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# 12. Window filter — bets older than --days are excluded                     #
# --------------------------------------------------------------------------- #
def test_old_bets_excluded_by_window(tmp_env):
    ledger, qb = tmp_env
    _make_box(qb, "0022500012", {
        1: [_player("Old Game", pid=1, pts=8)],
        2: [_player("Old Game", pid=1, pts=8)],
        3: [_player("Old Game", pid=1, pts=8)],
        4: [_player("Old Game", pid=1, pts=8)],
    })
    old_ts = (_dt.datetime.utcnow() - _dt.timedelta(days=30)).isoformat(timespec="seconds")
    bets = [_bet("b_old", game_id="0022500012", player="Old Game",
                  stat="pts", line=25.5, side="OVER",
                  status="won", actual_stat=32.0, placed_at=old_ts)]
    _write_ledger(ledger, bets)
    r = recon.reconcile(days=7, ledger_path=ledger, qb_dir=qb)
    assert r["n_total_settled"] == 1
    assert r["n_in_window"] == 0
    assert r["n_real_settled"] == 0
