"""Tests for scripts/auto_settle_daemon.py (R18_K8).

Covers:
  1. scan_new_q4_files() detects unseen q4 JSON files and ignores seen ones.
  2. settle_game() invokes pnl_ledger.settle_bet for an in-box player and
     pnl_ledger.void_bet for a DNP (player not in any quarter).
  3. OT-aware sum_quarter_box_full() folds q5+ stats into the totals.
  4. Idempotency — already-settled bets are skipped (status != "open").
  5. tick() updates the seen-set, writes an audit log line, and refreshes
     bankroll_state.json via R17_J4's tick().
"""
from __future__ import annotations

import csv
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.auto_settle_daemon as asd  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _write_q(qb_dir: Path, game_id: str, period: int,
              players: List[Dict[str, Any]]) -> Path:
    p = qb_dir / f"{game_id}_q{period}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"game_id": game_id, "period": period,
                "players": players, "teams": []},
                open(p, "w", encoding="utf-8"))
    return p


def _player(name: str, pid: int = 0, pts: float = 0, reb: float = 0,
             ast: float = 0, **extra) -> Dict[str, Any]:
    return {
        "player_name": name, "player_id": pid,
        "team_abbreviation": "TST",
        "pts": pts, "reb": reb, "ast": ast,
        "fg3m": 0, "stl": 0, "blk": 0, "to": 0,
        "min": "30:00", "comment": "",
        **extra,
    }


def _make_box(qb_dir: Path, game_id: str, periods=(1, 2, 3, 4),
               players_per_q=None) -> None:
    players_per_q = players_per_q or {}
    for q in periods:
        _write_q(qb_dir, game_id, q,
                  players_per_q.get(q, [_player("Test Player", pid=999,
                                                 pts=8, reb=3, ast=2)]))


# --------------------------------------------------------------------------- #
# Fakes for src.betting.pnl_ledger                                            #
# --------------------------------------------------------------------------- #
class FakeLedger:
    """In-memory replacement for src.betting.pnl_ledger."""
    def __init__(self) -> None:
        self.bets: List[Dict[str, Any]] = []
        self.bankroll = 1000.0
        self.settle_calls: List[tuple] = []
        self.void_calls: List[str] = []

    def add(self, **kw) -> str:
        bid = kw.pop("bet_id", str(uuid.uuid4()))
        row = {
            "bet_id": bid, "status": "open", "game_id": "", "player": "",
            "player_id": "", "stat": "pts", "line": "10.0", "side": "OVER",
            "american_odds": "-110", "stake": "10.0",
        }
        row.update(kw)
        self.bets.append(row)
        return bid

    def open_bets(self) -> List[Dict[str, Any]]:
        return [b for b in self.bets if b.get("status") == "open"]

    def settle_bet(self, bet_id: str, actual_stat: float) -> Dict[str, Any]:
        self.settle_calls.append((bet_id, actual_stat))
        target = next((b for b in self.bets if b["bet_id"] == bet_id), None)
        if target is None:
            raise KeyError(bet_id)
        if target["status"] != "open":
            raise ValueError(f"already {target['status']}")
        line = float(target["line"])
        side = target["side"]
        stake = float(target["stake"])
        if actual_stat == line:
            status, pnl = "push", 0.0
        else:
            won = (actual_stat > line) if side == "OVER" else (actual_stat < line)
            if won:
                status, pnl = "won", stake * 100 / 110
            else:
                status, pnl = "lost", -stake
        target["status"] = status
        target["actual_stat"] = f"{actual_stat:.2f}"
        target["profit_loss"] = f"{pnl:+.2f}"
        if status == "won":
            self.bankroll += stake + pnl
        elif status == "push":
            self.bankroll += stake
        target["bankroll_after"] = f"{self.bankroll:.2f}"
        return {"status": status, "profit_loss": pnl,
                 "bankroll_after": self.bankroll}

    def void_bet(self, bet_id: str) -> Dict[str, Any]:
        self.void_calls.append(bet_id)
        target = next((b for b in self.bets if b["bet_id"] == bet_id), None)
        if target is None:
            raise KeyError(bet_id)
        if target["status"] != "open":
            raise ValueError(f"already {target['status']}")
        stake = float(target["stake"])
        self.bankroll += stake
        target["status"] = "voided"
        target["profit_loss"] = "0.00"
        target["bankroll_after"] = f"{self.bankroll:.2f}"
        return {"status": "voided", "profit_loss": 0.0,
                 "bankroll_after": self.bankroll}


@pytest.fixture
def fake_ledger(monkeypatch):
    fl = FakeLedger()
    monkeypatch.setattr(asd, "_ledger", fl)
    return fl


@pytest.fixture
def stub_bankroll_refresh(monkeypatch):
    """Avoid touching the real bankroll-monitor module."""
    calls = []
    def fake(start):
        calls.append(start)
        return {"as_of": "test", "current_bankroll": 1234.0}
    monkeypatch.setattr(asd, "refresh_bankroll", fake)
    return calls


# --------------------------------------------------------------------------- #
# 1. scan_new_q4_files                                                        #
# --------------------------------------------------------------------------- #
def test_scan_detects_new_q4_and_skips_seen(tmp_path):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500111")
    _make_box(qb, "0022500222")
    seen = set()
    new = asd.scan_new_q4_files(qb, seen)
    assert sorted(new) == ["0022500111", "0022500222"]
    # Mark 111 as seen, should now only return 222.
    new2 = asd.scan_new_q4_files(qb, {"0022500111"})
    assert new2 == ["0022500222"]


# --------------------------------------------------------------------------- #
# 2. settle_game on a normal made-bet path                                    #
# --------------------------------------------------------------------------- #
def test_settle_game_calls_settle_bet_for_matched_player(tmp_path,
                                                          fake_ledger):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500999", players_per_q={
        1: [_player("Nikola Jokic", pid=203999, pts=10, reb=4, ast=3)],
        2: [_player("Nikola Jokic", pid=203999, pts=8,  reb=3, ast=2)],
        3: [_player("Nikola Jokic", pid=203999, pts=6,  reb=2, ast=4)],
        4: [_player("Nikola Jokic", pid=203999, pts=11, reb=3, ast=2)],
    })
    # Q1-Q4 totals: pts=35.
    fake_ledger.add(bet_id="b1", game_id="0022500999", player="Nikola Jokic",
                     player_id="203999", stat="pts", line="25.5", side="OVER")
    out = asd.settle_game("0022500999", qb_dir=qb)
    assert out["n_periods"] == 4
    assert len(out["settled"]) == 1
    assert out["settled"][0]["status"] == "won"
    assert out["settled"][0]["actual_stat"] == pytest.approx(35.0)
    assert fake_ledger.settle_calls == [("b1", 35.0)]


# --------------------------------------------------------------------------- #
# 3. DNP -> void                                                              #
# --------------------------------------------------------------------------- #
def test_dnp_player_gets_voided(tmp_path, fake_ledger):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500777")   # only "Test Player" appears
    fake_ledger.add(bet_id="bDNP", game_id="0022500777",
                     player="Phantom Star", stat="pts",
                     line="20.5", side="OVER")
    out = asd.settle_game("0022500777", qb_dir=qb)
    assert len(out["voided"]) == 1
    assert out["voided"][0]["bet_id"] == "bDNP"
    assert out["voided"][0]["reason"] == "dnp"
    assert fake_ledger.void_calls == ["bDNP"]
    # Bet status now 'voided'.
    assert fake_ledger.bets[0]["status"] == "voided"


# --------------------------------------------------------------------------- #
# 4. OT — q5 stats fold into totals                                            #
# --------------------------------------------------------------------------- #
def test_ot_stats_are_included_in_totals(tmp_path, fake_ledger):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500444", players_per_q={
        1: [_player("OT Hero", pid=42, pts=5)],
        2: [_player("OT Hero", pid=42, pts=5)],
        3: [_player("OT Hero", pid=42, pts=5)],
        4: [_player("OT Hero", pid=42, pts=5)],
    })
    # OT period file (q5)
    _write_q(qb, "0022500444", 5,
              [_player("OT Hero", pid=42, pts=4, reb=2, ast=1)])
    totals = asd.sum_quarter_box_full("0022500444", qb_dir=qb)
    assert totals["OT Hero"]["pts"] == pytest.approx(24.0)
    # And settle path uses these OT-inclusive totals.
    fake_ledger.add(bet_id="bOT", game_id="0022500444",
                     player="OT Hero", stat="pts",
                     line="23.5", side="OVER")
    out = asd.settle_game("0022500444", qb_dir=qb)
    assert out["n_periods"] == 5
    assert out["settled"][0]["actual_stat"] == pytest.approx(24.0)
    assert out["settled"][0]["status"] == "won"


# --------------------------------------------------------------------------- #
# 5. Idempotency — already-settled bet is skipped on a second pass.            #
# --------------------------------------------------------------------------- #
def test_already_settled_bets_are_not_resettled(tmp_path, fake_ledger):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500555", players_per_q={
        q: [_player("Repeat Guy", pid=7, pts=5)] for q in (1, 2, 3, 4)
    })
    fake_ledger.add(bet_id="bA", game_id="0022500555",
                     player="Repeat Guy", stat="pts",
                     line="15.5", side="UNDER")
    # First pass settles.
    asd.settle_game("0022500555", qb_dir=qb)
    assert fake_ledger.bets[0]["status"] == "lost"
    # Second pass: open_bets() returns [], so no new settle calls.
    settle_calls_before = list(fake_ledger.settle_calls)
    out2 = asd.settle_game("0022500555", qb_dir=qb)
    assert out2["settled"] == []
    assert out2["voided"] == []
    assert fake_ledger.settle_calls == settle_calls_before


# --------------------------------------------------------------------------- #
# 6. tick() — full cycle: detect, settle, persist seen, refresh bankroll.      #
# --------------------------------------------------------------------------- #
def test_tick_full_cycle_persists_seen_and_refreshes_bankroll(
        tmp_path, fake_ledger, stub_bankroll_refresh, monkeypatch):
    qb = tmp_path / "qb"
    seen = tmp_path / "seen.json"
    audit = tmp_path / "auto_settle.md"
    monkeypatch.setattr(asd, "LOG_MD", audit)
    _make_box(qb, "0022500123", players_per_q={
        q: [_player("Tick Guy", pid=1, pts=7)] for q in (1, 2, 3, 4)
    })
    # Pre-create empty seen.json so this counts as a non-first-run (which
    # would otherwise seed-and-skip every existing q4 file).
    json.dump([], open(seen, "w"))
    fake_ledger.add(bet_id="bTick", game_id="0022500123",
                     player="Tick Guy", stat="pts",
                     line="20.5", side="OVER")

    cycle = asd.tick(qb_dir=qb, seen_path=seen, start_bankroll=1000.0)
    # 1) one new q4, one game, one bet settled (28 pts > 20.5 -> won)
    assert cycle["new_q4_files"] == ["0022500123"]
    assert cycle["totals"]["settled"] == 1
    # 2) seen set persisted
    persisted = set(json.load(open(seen)))
    assert "0022500123" in persisted
    # 3) bankroll refresh was called
    assert stub_bankroll_refresh == [1000.0]
    # 4) audit log has a line for this game
    assert audit.exists()
    contents = audit.read_text(encoding="utf-8")
    assert "0022500123" in contents
    assert "bTick"[:8] in contents

    # Second tick: nothing new -> no settle calls added, no extra refresh.
    refresh_count_before = len(stub_bankroll_refresh)
    cycle2 = asd.tick(qb_dir=qb, seen_path=seen, start_bankroll=1000.0)
    assert cycle2["new_q4_files"] == []
    assert len(stub_bankroll_refresh) == refresh_count_before


# --------------------------------------------------------------------------- #
# 7. void_dnp_bets convenience wrapper                                         #
# --------------------------------------------------------------------------- #
def test_void_dnp_bets_helper(tmp_path, fake_ledger):
    qb = tmp_path / "qb"
    _make_box(qb, "0022500456")
    fake_ledger.add(bet_id="bX", game_id="0022500456",
                     player="No Show", stat="pts",
                     line="10.5", side="OVER")
    voided = asd.void_dnp_bets("0022500456", qb_dir=qb)
    assert len(voided) == 1
    assert voided[0]["bet_id"] == "bX"
