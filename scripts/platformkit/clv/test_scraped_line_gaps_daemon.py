"""Per-file tests for scraped_line_gaps_daemon -- offline (injected scan_fn)."""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv import scraped_line_gaps_daemon as D


def _scan_empty(*, min_clv_pct=0.5):
    return {"date": "2026-06-29", "min_clv_pct": min_clv_pct, "total_gaps": 0,
            "by_sport": {"mlb": {"gaps": [], "shoppable": 31, "max_books": 3},
                         "nba": {"gaps": [], "shoppable": 0, "max_books": 1}}}


def _scan_one_gap(*, min_clv_pct=0.5):
    gap = {"matchup": "A@B moneyline", "side": "home", "best_price": 2.20,
           "best_book": "fanduel", "fair_prob": 0.45, "fair_source": "pinnacle",
           "expected_clv_pct": 1.4, "sport": "mlb", "market": "moneyline",
           "line": None}
    return {"date": "2026-06-29", "min_clv_pct": min_clv_pct, "total_gaps": 1,
            "by_sport": {"mlb": {"gaps": [gap], "shoppable": 30, "max_books": 3}}}


def test_collect_empty_is_honest_zero():
    doc = D.collect(scan_fn=_scan_empty)
    assert doc["total_gaps"] == 0 and doc["gaps"] == []
    assert doc["shoppable_groups"] == 31
    assert doc["max_books"] == 3
    assert "edge" in doc["note"].lower()


def test_collect_surfaces_gap():
    doc = D.collect(scan_fn=_scan_one_gap)
    assert doc["total_gaps"] == 1
    assert doc["gaps"][0]["best_book"] == "fanduel"
    assert doc["gaps"][0]["market"] == "moneyline"


def test_write_and_atomic(tmp_path):
    doc = D.collect(scan_fn=_scan_one_gap)
    p = tmp_path / "scan.json"
    D.write_scan(doc, p)
    back = json.loads(p.read_text(encoding="ascii"))
    assert back["total_gaps"] == 1
    assert not (tmp_path / "scan.json.tmp").exists()


def test_append_catches_only_when_gap(tmp_path):
    log = tmp_path / "catches.jsonl"
    assert D.append_catches(D.collect(scan_fn=_scan_empty), log) == 0
    assert not log.exists()
    assert D.append_catches(D.collect(scan_fn=_scan_one_gap), log) == 1
    rows = [json.loads(x) for x in log.read_text(encoding="ascii").splitlines()]
    assert rows[0]["sport"] == "mlb" and "caught_at" in rows[0]


def test_run_max_ticks(tmp_path):
    n = D.run(interval_sec=0.0, scan_fn=_scan_one_gap, scan_path=tmp_path / "s.json",
              catch_path=tmp_path / "c.jsonl", sleep=lambda _s: None, max_ticks=3)
    assert n == 3
    assert len((tmp_path / "c.jsonl").read_text(encoding="ascii").splitlines()) == 3


def test_run_survives_scan_exception(tmp_path):
    def _boom(*, min_clv_pct=0.5):
        raise RuntimeError("dead feed")

    n = D.run(interval_sec=0.0, scan_fn=_boom, scan_path=tmp_path / "s.json",
              catch_path=tmp_path / "c.jsonl", sleep=lambda _s: None, max_ticks=2)
    assert n == 2
