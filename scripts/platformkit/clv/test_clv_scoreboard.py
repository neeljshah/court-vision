"""Tests for clv_scoreboard -- per-channel CLV truth table.

Per-file: python -m pytest scripts/platformkit/clv/test_clv_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import clv_scoreboard as S


def _row(bet_id, channel, status="settled", clv_status="no_close",
         clv_pct=None, unit_result=0.0, settled_at="2026-06-25T00:00:00Z",
         closing=None):
    r = {"bet_id": bet_id, "channel": channel, "status": status,
         "clv_status": clv_status, "clv_pct": clv_pct,
         "unit_result": unit_result, "settled_at": settled_at, "sport": "mlb"}
    if closing is not None:
        r["closing_decimal_home"] = closing
    return r


def test_dedup_keeps_latest_settled():
    led = [
        _row("b1", "paper", unit_result=-1.0, settled_at="2026-06-25T01:00:00Z"),
        _row("b1", "paper", unit_result=-1.0, settled_at="2026-06-25T02:00:00Z"),
    ]
    b = S.scoreboard(led)
    assert b["total_settled"] == 1  # twin collapsed


def test_measurable_split_and_coverage():
    led = [
        # measurable moneyline: 2 rows, both true_close
        _row("m1", "moneyline", clv_status="true_close", clv_pct=2.0,
             unit_result=1.0, closing=2.0),
        _row("m2", "moneyline", clv_status="true_close", clv_pct=-1.0,
             unit_result=-1.0, closing=2.0),
        # props: no close
        _row("p1", "paper", clv_status="no_close", unit_result=1.0),
        _row("p2", "paper", clv_status="no_close", unit_result=-1.0),
    ]
    b = S.scoreboard(led)
    assert b["total_settled"] == 4
    assert b["total_measurable"] == 2
    ml = b["channels"]["moneyline"]
    assert ml["n_measurable"] == 2
    assert ml["coverage_pct"] == 100.0
    assert ml["mean_clv_pct"] == 0.5  # (2 + -1)/2
    assert ml["beat_close_pct"] == 50.0
    pp = b["channels"]["paper"]
    assert pp["n_measurable"] == 0
    assert pp["coverage_pct"] == 0.0
    assert pp["mean_clv_pct"] is None  # no CLV for props
    assert pp["beat_close_pct"] is None


def test_no_closing_lines_verdict():
    led = [_row("p%d" % i, "paper", unit_result=1.0) for i in range(5)]
    b = S.scoreboard(led)
    assert b["total_measurable"] == 0
    assert "NO closing lines" in b["verdict"] or "unprovable" in b["verdict"]


def test_significant_positive_clv_flagged():
    # tight positive cluster -> CI excludes 0 -> significant + positive
    led = [
        _row("m%d" % i, "moneyline", clv_status="true_close",
             clv_pct=3.0 + (i % 2) * 0.2, unit_result=1.0, closing=2.0,
             settled_at="2026-06-25T%02d:00:00Z" % i)
        for i in range(12)
    ]
    b = S.scoreboard(led)
    ml = b["channels"]["moneyline"]
    assert ml["clv_significant"] is True
    assert ml["mean_clv_pct"] > 0
    assert "SIGNAL" in b["verdict"]


def test_render_runs():
    led = [_row("m1", "moneyline", clv_status="true_close", clv_pct=1.0,
                unit_result=1.0, closing=2.0)]
    txt = S.render(S.scoreboard(led))
    assert "CLV SCOREBOARD" in txt and "VERDICT" in txt
