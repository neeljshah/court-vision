"""Per-file test for scripts.platformkit.prop_paper (network-free, tmp ledger).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_paper.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.prop_paper import (
    grade_open, prop_summary, record_board, load_ledger,
)


def _board():
    # One reliable+ok edge (priced over) and one thin edge.
    return {
        "sport": "soccer_intl",
        "edges": [
            {
                "player": "Test Player", "matched_name": "Test Player",
                "match": "AAA vs BBB", "team": "AAA", "stat": "Shots",
                "line": 1.5, "side": "over", "model_p_over": 0.62,
                "reliable": True, "ev_flag": "ok", "source": "book",
                "over_price": 1.91, "under_price": 1.91, "as_of": "2026-06-01",
            },
            {
                "player": "Thin Guy", "matched_name": "Thin Guy",
                "match": "AAA vs BBB", "team": "AAA", "stat": "Fouls",
                "line": 0.5, "side": "over", "model_p_over": 0.55,
                "reliable": False, "ev_flag": "uncalibrated_thin",
                "source": "dfs", "over_price": None, "under_price": None,
                "as_of": "2026-06-01",
            },
        ],
    }


def _realized_df():
    # Test Player resolves to P1; in event E9 dated AFTER as_of they had 3 shots.
    return pd.DataFrame(
        [
            {"event_id": "E9", "player_id": "P1", "player": "Test Player",
             "team_abbr": "AAA", "date": "2026-06-02", "totalShots": 3.0,
             "shotsOnTarget": 1.0, "yellowCards": 0.0, "redCards": 0.0},
        ]
    )


def test_only_reliable_records_one(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    res = record_board(_board(), only_reliable=True, ledger_path=led)
    assert res["status"] == "ok"
    assert res["recorded"] == 1
    assert res["below_bar"] == 1
    rows = load_ledger(led)
    assert len(rows) == 1
    assert rows[0]["player"] == "Test Player"
    assert rows[0]["executed"] is False
    assert rows[0]["channel"] == "paper"
    assert rows[0]["market"] == "prop"
    assert rows[0]["status"] == "open"


def test_record_is_idempotent(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    res2 = record_board(_board(), only_reliable=True, ledger_path=led)
    assert res2["recorded"] == 0
    assert res2["skipped_existing"] == 1
    assert len(load_ledger(led)) == 1


def test_record_dedups_across_changing_as_of(tmp_path):
    # The dedup fix: re-recording the SAME prop with a DIFFERENT as_of (as a cadence
    # loop does every refresh) must add NOTHING -- as_of is not part of the key.
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    board2 = _board()
    for e in board2["edges"]:
        e["as_of"] = "2026-06-09"  # later refresh -> fresh taken-line timestamp
    res2 = record_board(board2, only_reliable=True, ledger_path=led)
    assert res2["recorded"] == 0
    assert res2["skipped_existing"] == 1
    rows = load_ledger(led)
    assert len(rows) == 1
    # The STORED as_of is the FIRST-sight value (the line we actually took).
    assert rows[0]["as_of"] == "2026-06-01"


def test_only_reliable_false_records_thin_too(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    res = record_board(_board(), only_reliable=False, ledger_path=led)
    assert res["recorded"] == 2
    assert len(load_ledger(led)) == 2


def test_grade_settles_a_win(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df(), ledger_path=led)
    assert g["status"] == "ok"
    assert g["graded"] == 1
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert len(settled) == 1
    # 3 shots > 1.5 over -> win; paper P&L at 1.91 = +0.91.
    assert settled[0]["result"] == "win"
    assert settled[0]["realized"] == 3.0
    assert abs(settled[0]["paper_pnl"] - 0.91) < 1e-6


def test_grade_is_idempotent(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led)
    g2 = grade_open(realized_df=_realized_df(), ledger_path=led)
    assert g2["graded"] == 0
    assert g2["already_settled"] == 1


def test_summary_returns_n_and_hit_rate(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led)
    s = prop_summary(ledger_path=led)
    assert s["status"] == "ok"
    assert s["overall"]["n"] == 1
    assert s["overall"]["hit_rate"] == 1.0
    assert "Shots" in s["by_stat"]
    assert "TODO" in s["note"]


def test_priced_settled_bet_gets_clv_from_history(tmp_path):
    # A canned line history whose CLOSING (latest-ts) over price is SHORTER (1.60)
    # than the taken 1.91 -> the taken bet got a BETTER number -> clv_pct > 0.
    led = tmp_path / "prop_ledger.jsonl"
    hist = tmp_path / "prop_line_history.jsonl"
    rows = [
        {"match": "AAA vs BBB", "player": "Test Player", "stat": "Shots",
         "line": 1.5, "over_price": 1.91, "under_price": 1.91, "source": "book",
         "ts": "2026-06-01T00:00:00+00:00"},
        # Closing line (latest ts): over shortened, under lengthened.
        {"match": "AAA vs BBB", "player": "Test Player", "stat": "Shots",
         "line": 1.5, "over_price": 1.60, "under_price": 2.40, "source": "book",
         "ts": "2026-06-02T11:00:00+00:00"},
    ]
    with hist.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    record_board(_board(), only_reliable=True, ledger_path=led)
    g = grade_open(realized_df=_realized_df(), ledger_path=led, history_path=hist)
    assert g["graded"] == 1
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert settled[0]["clv_pct"] is not None
    assert settled[0]["clv_pct"] > 0.0  # took 1.91 vs a 1.60 close = better number
    # Summary surfaces CLV over priced bets.
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n_clv"] == 1
    assert s["overall"]["mean_clv_pct"] > 0.0
    assert s["overall"]["pct_beat_close"] == 100.0


def test_clv_none_without_history(tmp_path):
    # No history file -> priced bet still settles, clv_pct stays None (no fake CLV).
    led = tmp_path / "prop_ledger.jsonl"
    record_board(_board(), only_reliable=True, ledger_path=led)
    grade_open(realized_df=_realized_df(), ledger_path=led,
               history_path=tmp_path / "absent.jsonl")
    settled = [r for r in load_ledger(led) if r.get("status") == "settled"]
    assert settled[0]["clv_pct"] is None
    s = prop_summary(ledger_path=led)
    assert s["overall"]["n_clv"] == 0
    assert s["overall"]["mean_clv_pct"] is None


def test_public_fns_never_raise_on_garbage(tmp_path):
    led = tmp_path / "prop_ledger.jsonl"
    assert record_board(None, ledger_path=led)["status"].startswith(("ok", "error"))
    assert record_board({"edges": [{}]}, only_reliable=False,
                        ledger_path=led)["status"] == "ok"
    assert grade_open(realized_df=None, ledger_path=led)["status"] in (
        "ok", "no_realized_data")
    assert prop_summary(ledger_path=led)["status"] == "ok"
