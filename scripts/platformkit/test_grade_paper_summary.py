"""Per-file tests: UNITS-ONLY grade scoreboard (grade_paper_summary).

Run ONLY this file (full suite freezes the box):
    python -m pytest scripts/platformkit/test_grade_paper_summary.py -q

Asserts: no $ pnl/roi/stake key in grade_bucket or grade_summary; void rows are
excluded from the decided sample (never a 0-fill win); net_units is a unit count.
"""
from __future__ import annotations

import json

from scripts.platformkit.grade_paper_summary import (
    grade_bucket,
    grade_summary,
    row_market,
)

_BANNED = {"pnl", "total_pnl", "total_stake", "paper_roi", "roi", "bankroll",
           "stake", "profit", "dollars"}


def _row(outcome, unit_result, clv_pct=None, sport="nba", market=None,
         clv_is_proxy=False):
    r = {"graded": True, "outcome": outcome, "unit_result": unit_result,
         "clv_pct": clv_pct, "sport": sport, "clv_is_proxy": clv_is_proxy}
    if market is not None:
        r["market"] = market
    return r


def test_grade_bucket_units_only_no_dollars():
    rows = [_row("win", 1.5, clv_pct=2.0), _row("loss", -1.0, clv_pct=-1.0)]
    b = grade_bucket(rows)
    assert not (_BANNED & set(b)), "grade_bucket leaked $ keys: %s" % (_BANNED & set(b))
    assert b["n_decided"] == 2 and b["n_wins"] == 1
    assert abs(b["net_units"] - 0.5) < 1e-9


def test_void_excluded_from_decided_never_a_win():
    rows = [_row("win", 1.0), _row("void", None)]
    b = grade_bucket(rows)
    assert b["n_total"] == 2
    assert b["n_void"] == 1
    assert b["n_decided"] == 1  # void NOT counted as decided
    assert b["hit_rate"] == 100.0  # 1 win / 1 decided, void did not inflate it


def test_row_market_reads_field_not_force_moneyline():
    assert row_market({"market": "spread"}) == "spread"
    assert row_market({"market_type": "total"}) == "total"
    assert row_market({}) == "moneyline"


def test_grade_bucket_median_prefers_true_close_over_proxy():
    rows = [
        _row("win", 1.0, clv_pct=2.0, clv_is_proxy=False),
        _row("loss", -1.0, clv_pct=-1.0, clv_is_proxy=False),
        _row("win", 1.0, clv_pct=40.0, clv_is_proxy=True),  # fat proxy outlier
    ]
    b = grade_bucket(rows)
    assert b["n_proxy"] == 1
    assert b["basis"] == "true_close"
    assert abs(b["median_clv_pct"] - 0.5) < 1e-6      # median of [2.0, -1.0]
    assert b["mean_clv_pct"] > 10.0                     # context mean sees the +40


def test_grade_bucket_median_falls_back_to_proxy_only(tmp_path):
    rows = [
        _row("win", 1.0, clv_pct=3.0, clv_is_proxy=True),
        _row("loss", -1.0, clv_pct=5.0, clv_is_proxy=True),
    ]
    b = grade_bucket(rows)
    assert b["n_proxy"] == 2
    assert b["basis"] == "proxy_only"
    assert abs(b["median_clv_pct"] - 4.0) < 1e-6


def test_grade_bucket_no_clv_rows_has_null_median_and_basis():
    rows = [_row("win", 1.0), _row("loss", -1.0)]  # no clv_pct at all
    b = grade_bucket(rows)
    assert b["n_with_clv"] == 0
    assert b["median_clv_pct"] is None
    assert b["basis"] is None


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def test_grade_summary_no_dollar_keys(tmp_path):
    ledger = _write(tmp_path / "clv_ledger.jsonl", [
        _row("win", 1.0, clv_pct=1.0, sport="nba"),
        _row("loss", -1.0, clv_pct=-2.0, sport="mlb"),
        _row("void", None, sport="nba"),
    ])
    s = grade_summary(ledger)
    assert not (_BANNED & set(s)), "summary leaked $ keys: %s" % (_BANNED & set(s))
    for bucket in list(s["by_sport"].values()) + list(s["by_market"].values()):
        assert not (_BANNED & set(bucket))
    assert s["n_total"] == 3 and s["n_void"] == 1 and s["n_decided"] == 2


def test_grade_summary_empty(tmp_path):
    s = grade_summary(tmp_path / "nope.jsonl")
    assert s["n_total"] == 0 and s["by_sport"] == {}
