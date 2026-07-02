"""Per-file tests for best_price_scan_daemon -- fully offline (injected audit_fn)."""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv import best_price_scan_daemon as D


def _audit_empty(sports, *, min_clv_pct=0.5):
    return {"min_clv_pct": min_clv_pct, "total_value_bets": 0,
            "by_sport": {s: {"games_scanned": 5, "value_bets": [],
                             "shoppable_games": 0, "max_books": 1} for s in sports}}


def _audit_one_gap(sports, *, min_clv_pct=0.5):
    by = {}
    for i, s in enumerate(sports):
        vb = [{"matchup": "A@B", "side": "home", "best_price": 2.10,
               "best_book": "fanduel", "fair_prob": 0.45, "fair_source": "pinnacle",
               "expected_clv_pct": 1.2}] if i == 0 else []
        by[s] = {"games_scanned": 3, "value_bets": vb,
                 "shoppable_games": 2, "max_books": 3}
    return {"min_clv_pct": min_clv_pct, "total_value_bets": 1, "by_sport": by}


def test_collect_empty_is_honest_zero():
    doc = D.collect(("mlb", "soccer_intl"), audit_fn=_audit_empty)
    assert doc["total_gaps"] == 0
    assert doc["gaps"] == []
    assert doc["shoppable_games"] == 0
    assert doc["max_books"] == 1
    assert doc["component"] == D.COMPONENT
    assert "edge" in doc["note"].lower()  # no-$-edge framing present


def test_collect_surfaces_gap_with_sport_tag():
    doc = D.collect(("mlb", "soccer_intl"), audit_fn=_audit_one_gap)
    assert doc["total_gaps"] == 1
    g = doc["gaps"][0]
    assert g["sport"] == "mlb"
    assert g["best_book"] == "fanduel"
    assert g["expected_clv_pct"] == 1.2
    assert doc["max_books"] == 3


def test_write_scan_roundtrip(tmp_path):
    doc = D.collect(("mlb",), audit_fn=_audit_one_gap)
    p = tmp_path / "scan.json"
    D.write_scan(doc, p)
    back = json.loads(p.read_text(encoding="ascii"))
    assert back["total_gaps"] == 1
    assert not (tmp_path / "scan.json.tmp").exists()  # atomic replace cleaned up


def test_append_catches_only_when_gap(tmp_path):
    log = tmp_path / "catches.jsonl"
    empty = D.collect(("mlb",), audit_fn=_audit_empty)
    assert D.append_catches(empty, log) == 0
    assert not log.exists()  # efficient slate writes nothing
    gap = D.collect(("mlb",), audit_fn=_audit_one_gap)
    assert D.append_catches(gap, log) == 1
    rows = [json.loads(x) for x in log.read_text(encoding="ascii").splitlines()]
    assert len(rows) == 1
    assert rows[0]["sport"] == "mlb"
    assert "caught_at" in rows[0]


def test_run_max_ticks_and_should_stop(tmp_path):
    scan = tmp_path / "scan.json"
    log = tmp_path / "catches.jsonl"
    n = D.run(interval_sec=0.0, sports=("mlb",), audit_fn=_audit_one_gap,
              scan_path=scan, catch_path=log, sleep=lambda _s: None, max_ticks=3)
    assert n == 3
    assert scan.exists()
    # 3 ticks each caught the one gap -> 3 catch rows
    assert len(log.read_text(encoding="ascii").splitlines()) == 3

    stop = {"n": 0}

    def _should_stop():
        stop["n"] += 1
        return stop["n"] > 2

    m = D.run(interval_sec=0.0, sports=("mlb",), audit_fn=_audit_empty,
              scan_path=scan, catch_path=log, sleep=lambda _s: None,
              should_stop=_should_stop, max_ticks=99)
    assert m == 2  # stopped by should_stop before max_ticks


def test_run_survives_audit_exception(tmp_path):
    def _boom(sports, *, min_clv_pct=0.5):
        raise RuntimeError("dead feed")

    n = D.run(interval_sec=0.0, sports=("mlb",), audit_fn=_boom,
              scan_path=tmp_path / "s.json", catch_path=tmp_path / "c.jsonl",
              sleep=lambda _s: None, max_ticks=2)
    assert n == 2  # tick failure does not kill the loop
