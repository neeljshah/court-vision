"""Per-file test for prop_settler -- settle OPEN player-prop bets on the stat outcome.

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/bestbets/test_prop_settler.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.bestbets import prop_settler as S


def _open_prop(player="Aaron Judge", stat="Hits", line=1.5, side="over",
               taken_decimal=1.9, sport="mlb", bet_id="prop|x"):
    leg = "home" if side == "over" else "away"
    return {"sport": sport, "matchup": "NYY @ BOS", "side": leg, "prop_side": side,
            "market_type": "prop", "market": "prop|%s|%s|%s|%s" % (player, stat, line, side),
            "prop_player": player, "prop_stat": stat, "line": line,
            "taken_book": "underdog", "taken_decimal": taken_decimal, "model_prob": 0.6,
            "stake_units": 1.0, "status": "open", "executed": False, "bet_id": bet_id,
            "game_date": "2026-06-21", "ts": "t0"}


def test_prop_outcome_over_under_push():
    assert S.prop_outcome("over", 1.5, 2) == "win"
    assert S.prop_outcome("over", 1.5, 1) == "loss"
    assert S.prop_outcome("under", 1.5, 1) == "win"
    assert S.prop_outcome("under", 1.5, 2) == "loss"
    assert S.prop_outcome("over", 2.0, 2.0) == "push"
    assert S.prop_outcome("under", 2.0, 2.0) == "push"
    assert S.prop_outcome("bogus", 1.5, 2) is None
    assert S.prop_outcome("over", None, 2) is None


def test_settle_prop_row_win_units_and_no_clv():
    row = _open_prop(line=1.5, side="over", taken_decimal=2.0)
    s = S.settle_prop_row(row, realized=3)  # 3 hits > 1.5 -> over wins
    assert s["status"] == "settled" and s["outcome"] == "win"
    assert s["unit_result"] == 1.0          # (2.0-1)*1u
    assert s["realized_stat"] == 3.0
    assert s["clv_pct"] is None and s["clv_status"] == "no_close"  # no prop close
    assert s["executed"] is False
    assert "pnl" not in s and "stake" not in s  # no $ field
    # D2 (settle-path bypass): the previously-bypassing prop path must now
    # ALWAYS carry close_source, even when no close was captured.
    assert s["close_source"] == "none_available"


def test_settle_prop_row_true_close_stamps_close_source():
    """A prop row with a captured two-way close carries close_source == the
    real book, not the missing key that settlement_correctness_audit's
    close_source_coverage previously counted as 'missing_key' for every prop."""
    row = _open_prop(line=1.5, side="over", taken_decimal=2.0)
    close_fn = lambda _row: {"over_dec": 1.9, "under_dec": 2.0, "source": "draftkings"}
    s = S.settle_prop_row(row, realized=3, close_fn=close_fn)
    assert s["clv_status"] == "true_close"
    assert s["close_source"] == "draftkings"


def test_settle_prop_row_loss_and_push():
    assert S.settle_prop_row(_open_prop(line=1.5, side="over"), 1)["outcome"] == "loss"
    assert S.settle_prop_row(_open_prop(line=2.0, side="over"), 2)["outcome"] == "push"
    push = S.settle_prop_row(_open_prop(line=2.0, side="over"), 2)
    assert push["unit_result"] == 0.0


def _write(ledger, rows):
    with ledger.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_settle_open_props_injected_resolver(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [_open_prop(player="A", line=1.5, side="over", bet_id="prop|a"),
                    _open_prop(player="B", line=0.5, side="under", bet_id="prop|b")])
    # A gets 2 hits (over 1.5 -> win); B unresolved (None -> pending)
    def realized(row):
        return 2.0 if row.get("prop_player") == "A" else None
    out = S.settle_open_props(ledger, realized_fn=realized)
    assert out["n_open_props"] == 2 and out["n_settled_now"] == 1 and out["n_pending"] == 1
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    settled = [r for r in rows if r.get("status") == "settled"]
    assert len(settled) == 1 and settled[0]["prop_player"] == "A"
    assert settled[0]["outcome"] == "win"


def test_settle_open_props_idempotent(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [_open_prop(player="A", line=1.5, side="over", bet_id="prop|a")])
    S.settle_open_props(ledger, realized_fn=lambda r: 2.0)
    out2 = S.settle_open_props(ledger, realized_fn=lambda r: 2.0)
    assert out2["n_settled_now"] == 0  # already settled -> skipped
    rows = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert sum(1 for l in rows if json.loads(l).get("status") == "settled") == 1


def test_non_prop_rows_ignored(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    game_ml = {"sport": "mlb", "matchup": "NYY @ BOS", "side": "home",
               "taken_decimal": 2.0, "stake_units": 1.0, "status": "open", "bet_id": "g1"}
    _write(ledger, [game_ml])
    out = S.settle_open_props(ledger, realized_fn=lambda r: 5.0)
    assert out["n_open_props"] == 0 and out["n_settled_now"] == 0  # game ML not touched
