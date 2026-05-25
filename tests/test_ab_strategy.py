"""tests/test_ab_strategy.py — tier4-14 (loop 5).

Eight tests covering the A/B strategy framework.
"""
from __future__ import annotations

import csv
import importlib
import os

import pytest


@pytest.fixture
def ab(monkeypatch, tmp_path):
    """Fresh ab_strategy + pnl_ledger that write into tmp_path."""
    import src.betting.pnl_ledger as L
    importlib.reload(L)
    monkeypatch.setattr(L, "LEDGER_CSV",   str(tmp_path / "pnl_ledger.csv"))
    monkeypatch.setattr(L, "BANKROLL_CSV", str(tmp_path / "pnl_bankroll.csv"))
    monkeypatch.setattr(L, "LOCK_PATH",    str(tmp_path / "pnl_ledger.csv.lock"))

    import src.betting.ab_strategy as AB
    importlib.reload(AB)
    # Repoint AB's reference to the freshly-reloaded ledger module.
    monkeypatch.setattr(AB, "_pnl", L)
    monkeypatch.setattr(AB, "STRATEGIES_CSV", str(tmp_path / "ab_strategies.csv"))
    L.record_bankroll(100_000.0, "seed")  # plenty of global bankroll
    return AB, L


# 1
def test_register_strategy_creates_csv_entry(ab, tmp_path):
    AB, _ = ab
    rec = AB.register_strategy("pregame_only", 1000.0, 0.05)
    assert rec["strategy"] == "pregame_only"
    assert os.path.exists(str(tmp_path / "ab_strategies.csv"))
    rows = AB.list_strategies()
    assert len(rows) == 1 and rows[0]["strategy"] == "pregame_only"
    assert float(rows[0]["bankroll"]) == 1000.0


# 2
def test_place_strategy_bet_within_bankroll(ab):
    AB, L = ab
    AB.register_strategy("endQ3", 1000.0, 0.10)
    bid = AB.place_strategy_bet(
        "endQ3", game_id="g1", player="P", stat="pts", line=20.0,
        side="OVER", book="DK", odds=-110, stake=50.0,
    )
    assert isinstance(bid, str) and len(bid) == 36
    bets = L.all_bets()
    assert len(bets) == 1
    assert bets[0]["strategy"] == "endQ3"


# 3
def test_strategy_bankroll_exceeded_rejects(ab):
    AB, _ = ab
    AB.register_strategy("small", 500.0, 0.05)  # cap = $25
    with pytest.raises(ValueError, match="exceeds"):
        AB.place_strategy_bet(
            "small", game_id="g", player="P", stat="pts", line=10.0,
            side="OVER", book="DK", odds=-110, stake=100.0,
        )


# 4
def test_strategy_summary_aggregates_correctly(ab):
    AB, L = ab
    AB.register_strategy("midQ3", 1000.0, 0.10)
    for stake, won_amt in [(50.0, True), (50.0, False), (50.0, True)]:
        bid = AB.place_strategy_bet(
            "midQ3", game_id="g", player="P", stat="pts", line=20.0,
            side="OVER", book="DK", odds=-110, stake=stake,
        )
        # actual = 25 -> OVER wins; actual = 15 -> OVER loses.
        L.settle_bet(bid, 25.0 if won_amt else 15.0)
    s = AB.strategy_summary("midQ3")
    assert s["n_settled"] == 3
    assert s["won"] == 2 and s["lost"] == 1
    assert s["win_rate"] == round(2 / 3, 4)
    # Two wins at -110 = +45.45 each, one loss = -50 -> ~+40.9
    assert s["total_profit"] > 0


# 5
def test_ab_compare_produces_t_statistic(ab):
    AB, L = ab
    AB.register_strategy("A", 5000.0, 0.10)
    AB.register_strategy("B", 5000.0, 0.10)
    # Strategy A: 15 wins, 15 losses (split).
    for i in range(30):
        bid = AB.place_strategy_bet(
            "A", game_id="g", player="P", stat="pts", line=20.0,
            side="OVER", book="DK", odds=-110, stake=50.0,
        )
        L.settle_bet(bid, 25.0 if i % 2 == 0 else 15.0)
    # Strategy B: 20 wins, 10 losses (better).
    for i in range(30):
        bid = AB.place_strategy_bet(
            "B", game_id="g", player="P", stat="pts", line=20.0,
            side="OVER", book="DK", odds=-110, stake=50.0,
        )
        L.settle_bet(bid, 25.0 if i % 3 != 0 else 15.0)
    cmp = AB.ab_compare("A", "B")
    assert cmp["n_a"] == 30 and cmp["n_b"] == 30
    assert cmp["welch_t"] is not None
    assert cmp["p_value"] is not None
    assert cmp["winner"] == "B"


# 6
def test_schema_extension_preserves_old_rows(ab, tmp_path):
    AB, L = ab
    # Manually write an "old" ledger row missing the strategy column.
    old_row = {
        "bet_id": "old-1234", "placed_at": "2026-01-01T12:00:00",
        "game_id": "g0", "player_id": "", "player": "X", "team": "",
        "stat": "pts", "line": "20.00", "side": "OVER", "book": "DK",
        "american_odds": "-110", "stake": "50.00",
        "model_pred": "", "model_prob": "", "model_edge": "",
        "kelly_pct": "", "status": "won", "settled_at": "2026-01-01T15:00:00",
        "actual_stat": "25.0000", "profit_loss": "+45.45",
        "bankroll_after": "1045.45",
        # NO strategy column.
    }
    old_cols = [c for c in L.LEDGER_COLS if c != "strategy"]
    with open(L.LEDGER_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=old_cols)
        w.writeheader()
        w.writerow(old_row)
    # Default-tagged summary should pick it up.
    s = AB.strategy_summary("default")
    assert s["n_bets"] == 1
    assert s["won"] == 1


# 7
def test_two_strategies_no_contamination(ab):
    AB, L = ab
    AB.register_strategy("alpha", 1000.0, 0.10)
    AB.register_strategy("beta",  1000.0, 0.10)
    bid_a = AB.place_strategy_bet(
        "alpha", game_id="g", player="A", stat="pts", line=20.0,
        side="OVER", book="DK", odds=-110, stake=50.0,
    )
    bid_b = AB.place_strategy_bet(
        "beta", game_id="g", player="B", stat="pts", line=20.0,
        side="OVER", book="DK", odds=-110, stake=75.0,
    )
    L.settle_bet(bid_a, 25.0)
    L.settle_bet(bid_b, 15.0)
    sa = AB.strategy_summary("alpha")
    sb = AB.strategy_summary("beta")
    assert sa["won"] == 1 and sa["lost"] == 0
    assert sb["won"] == 0 and sb["lost"] == 1
    assert sa["total_profit"] > 0
    assert sb["total_profit"] < 0


# 8
def test_bankroll_reservation_independent(ab):
    AB, L = ab
    AB.register_strategy("A", 500.0, 1.0)
    AB.register_strategy("B", 500.0, 1.0)
    AB.place_strategy_bet(
        "A", game_id="g", player="P", stat="pts", line=20.0,
        side="OVER", book="DK", odds=-110, stake=400.0,
    )
    # B is untouched: still has $500 available.
    sb = AB.strategy_summary("B")
    assert sb["available"] == 500.00
    # A has $100 left.
    sa = AB.strategy_summary("A")
    assert sa["available"] == 100.00
    # Placing $200 in B should still succeed.
    bid = AB.place_strategy_bet(
        "B", game_id="g", player="P", stat="pts", line=20.0,
        side="OVER", book="DK", odds=-110, stake=200.0,
    )
    assert bid
