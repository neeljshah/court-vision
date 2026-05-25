"""tests/test_pnl_ledger.py — tier 2-8 (loop 5).

Eight tests covering the manual P&L ledger.
"""
from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
from datetime import datetime
from unittest import mock

import pytest


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    """Fresh ledger that writes into tmp_path. Module-level paths repointed."""
    import src.betting.pnl_ledger as L
    importlib.reload(L)
    monkeypatch.setattr(L, "LEDGER_CSV",   str(tmp_path / "pnl_ledger.csv"))
    monkeypatch.setattr(L, "BANKROLL_CSV", str(tmp_path / "pnl_bankroll.csv"))
    monkeypatch.setattr(L, "LOCK_PATH",    str(tmp_path / "pnl_ledger.csv.lock"))
    return L


# --------------------------------------------------------------------------- #
# 1. place_bet creates row + deducts stake from bankroll.                     #
# --------------------------------------------------------------------------- #
def test_place_bet_creates_row_and_deducts_stake(ledger):
    ledger.record_bankroll(1000.0, "seed")
    bid = ledger.place_bet(
        game_id="0022500123", player="Nikola Jokic", stat="pts",
        line=28.5, side="OVER", book="DK", odds=-115, stake=50.0,
        model_pred=31.0, kelly_pct=4.5,
    )
    assert isinstance(bid, str) and len(bid) == 36  # UUID4 format
    rows = ledger.all_bets()
    assert len(rows) == 1
    r = rows[0]
    assert r["bet_id"] == bid
    assert r["status"] == "open"
    assert float(r["stake"]) == 50.0
    assert r["side"] == "OVER"
    # Bankroll dropped by stake.
    assert ledger.current_bankroll() == 950.0


# --------------------------------------------------------------------------- #
# 2. settle WON: profit = stake * payout, bankroll += stake + profit.         #
# --------------------------------------------------------------------------- #
def test_settle_bet_won_payout_and_bankroll(ledger):
    ledger.record_bankroll(1000.0, "seed")
    bid = ledger.place_bet(
        game_id="g1", player="P", stat="pts", line=20.0, side="OVER",
        book="DK", odds=-110, stake=110.0,
    )
    # bankroll now 890
    out = ledger.settle_bet(bid, actual_stat=25.0)
    assert out["status"] == "won"
    # payout = 110 * (100/110) = 100. bankroll back to 890 + 110 stake + 100 win = 1100
    assert out["profit_loss"] == pytest.approx(100.0, abs=0.01)
    assert out["bankroll_after"] == pytest.approx(1100.0, abs=0.01)


# --------------------------------------------------------------------------- #
# 3. settle LOST: profit = -stake (stake was already deducted at place time). #
# --------------------------------------------------------------------------- #
def test_settle_bet_lost_no_bankroll_change_on_settle(ledger):
    ledger.record_bankroll(1000.0, "seed")
    bid = ledger.place_bet(
        game_id="g", player="P", stat="reb", line=10.0, side="OVER",
        book="FD", odds=+120, stake=50.0,
    )
    # bankroll after place = 950
    out = ledger.settle_bet(bid, actual_stat=8.0)
    assert out["status"] == "lost"
    assert out["profit_loss"] == pytest.approx(-50.0, abs=0.01)
    # No credit on loss; bankroll stays at 950 (stake already deducted).
    assert out["bankroll_after"] == pytest.approx(950.0, abs=0.01)


# --------------------------------------------------------------------------- #
# 4. settle PUSH: stake returned, profit = 0.                                  #
# --------------------------------------------------------------------------- #
def test_settle_bet_push_returns_stake(ledger):
    ledger.record_bankroll(1000.0, "seed")
    bid = ledger.place_bet(
        game_id="g", player="P", stat="ast", line=7.0, side="UNDER",
        book="MGM", odds=-110, stake=30.0,
    )
    out = ledger.settle_bet(bid, actual_stat=7.0)
    assert out["status"] == "push"
    assert out["profit_loss"] == 0.0
    assert out["bankroll_after"] == pytest.approx(1000.0, abs=0.01)


# --------------------------------------------------------------------------- #
# 5. pnl_summary aggregates across 10 fixture bets.                            #
# --------------------------------------------------------------------------- #
def test_pnl_summary_aggregates_fixture(ledger):
    ledger.record_bankroll(2000.0, "seed")
    # 10 bets: 6 wins, 3 losses, 1 push. All -110 odds, stake $50.
    bets = []
    for i in range(10):
        bid = ledger.place_bet(
            game_id=f"g{i}", player=f"P{i}", stat="pts",
            line=20.0, side="OVER", book="DK", odds=-110, stake=50.0,
        )
        bets.append(bid)
    # Settle 6 wins (actual=25), 3 losses (actual=15), 1 push (actual=20).
    for bid in bets[:6]:
        ledger.settle_bet(bid, 25.0)
    for bid in bets[6:9]:
        ledger.settle_bet(bid, 15.0)
    ledger.settle_bet(bets[9], 20.0)

    s = ledger.pnl_summary()
    assert s["n_bets"] == 10
    assert s["n_settled"] == 10
    assert s["won"] == 6 and s["lost"] == 3 and s["push"] == 1
    # win_rate = wins / decisive (wins+losses) = 6/9
    assert s["win_rate"] == pytest.approx(6 / 9, abs=1e-4)
    # profit = 6 * (50 * 100/110) - 3 * 50 = 272.73 - 150 = 122.73
    expected_profit = round(6 * (50 * 100 / 110) - 3 * 50, 2)
    assert s["total_profit"] == pytest.approx(expected_profit, abs=0.05)
    assert s["total_staked"] == 500.0
    assert s["roi"] == pytest.approx(expected_profit / 500.0, abs=1e-3)


# --------------------------------------------------------------------------- #
# 6. open_bets returns only status=open.                                       #
# --------------------------------------------------------------------------- #
def test_open_bets_only_open(ledger):
    ledger.record_bankroll(1000.0, "seed")
    b1 = ledger.place_bet(game_id="g", player="A", stat="pts",
                          line=20, side="OVER", book="DK", odds=-110, stake=20)
    b2 = ledger.place_bet(game_id="g", player="B", stat="pts",
                          line=20, side="OVER", book="DK", odds=-110, stake=20)
    b3 = ledger.place_bet(game_id="g", player="C", stat="pts",
                          line=20, side="OVER", book="DK", odds=-110, stake=20)
    ledger.settle_bet(b1, 30.0)  # won
    ledger.settle_bet(b2, 10.0)  # lost
    ob = ledger.open_bets()
    assert len(ob) == 1
    assert ob[0]["bet_id"] == b3


# --------------------------------------------------------------------------- #
# 7. auto-settle from gamelog actuals (mocked).                                #
# --------------------------------------------------------------------------- #
def test_auto_settle_uses_gamelog_actuals(ledger, tmp_path):
    ledger.record_bankroll(1000.0, "seed")
    # Plant a fake gamelog JSON: player 999, May 24 2026, 28 PTS.
    gamelog_dir = tmp_path / "gamelogs"
    gamelog_dir.mkdir()
    gl_path = gamelog_dir / "gamelog_999_2025-26.json"
    gl_path.write_text(json.dumps([
        {"GAME_DATE": "May 24, 2026", "PTS": 28, "REB": 9, "AST": 5,
         "MIN": 34.0, "FG3M": 3, "STL": 1, "BLK": 0, "TOV": 2},
    ]))

    bid = ledger.place_bet(
        game_id="0022500999", player="Test Player", stat="pts",
        line=25.5, side="OVER", book="DK", odds=-110, stake=40.0,
        player_id="999",
    )
    # Override the placed_at date so the auto-settle date filter picks it up.
    rows = ledger.all_bets()
    rows[0]["placed_at"] = "2026-05-24T12:00:00"
    ledger._atomic_write_rows(ledger.LEDGER_CSV, ledger.LEDGER_COLS, rows)

    results = ledger.auto_settle_date("2026-05-24", gamelog_dir=str(gamelog_dir))
    assert len(results) == 1
    r = results[0]
    assert r["status"] == "won"
    assert r["actual"] == 28.0
    assert r["profit_loss"] == pytest.approx(40 * 100 / 110, abs=0.05)


# --------------------------------------------------------------------------- #
# 8. Concurrent writes: file locking prevents corruption.                      #
# --------------------------------------------------------------------------- #
def test_concurrent_writes_no_corruption(ledger):
    ledger.record_bankroll(10000.0, "seed")
    N_THREADS = 8
    PER_THREAD = 5

    def worker(tid: int):
        for i in range(PER_THREAD):
            ledger.place_bet(
                game_id=f"g{tid}_{i}", player=f"P{tid}_{i}", stat="pts",
                line=20.0, side="OVER", book="DK", odds=-110, stake=10.0,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = ledger.all_bets()
    # All writes survived; nothing dropped from CSV corruption.
    assert len(rows) == N_THREADS * PER_THREAD
    # All bet_ids unique (no duplicates from torn writes).
    bids = {r["bet_id"] for r in rows}
    assert len(bids) == N_THREADS * PER_THREAD
    # Bankroll matches: seed 10000 - 40 stakes * 10 = 9600.
    assert ledger.current_bankroll() == pytest.approx(9600.0, abs=0.01)
