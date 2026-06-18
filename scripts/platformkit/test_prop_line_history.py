"""Per-file test for scripts.platformkit.prop_line_history (network-free, tmp file).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_line_history.py -q
"""
from __future__ import annotations

from scripts.platformkit.prop_line_history import (
    clv_vs_close, closing_snapshot, load_history, log_board_lines,
)


def _board():
    # One PRICED edge (real two-way) and one pick'em edge (no price -> skipped).
    return {
        "sport": "soccer_intl",
        "edges": [
            {
                "match": "AAA vs BBB", "player": "Test Player", "stat": "Shots",
                "line": 1.5, "side": "over", "source": "underdog",
                "over_price": 2.10, "under_price": 1.75,
            },
            {
                "match": "AAA vs BBB", "player": "Thin Guy", "stat": "Fouls",
                "line": 0.5, "side": "over", "source": "dfs",
                "over_price": None, "under_price": None,
            },
        ],
    }


def test_log_writes_priced_rows_only(tmp_path):
    hist = tmp_path / "prop_line_history.jsonl"
    res = log_board_lines(_board(), path=hist, now="2026-06-01T00:00:00+00:00")
    assert res["status"] == "ok"
    assert res["logged"] == 1  # pick'em skipped
    assert res["skipped"] == 1
    rows = load_history(hist)
    assert len(rows) == 1
    assert rows[0]["player"] == "Test Player"
    assert rows[0]["over_price"] == 2.10
    assert rows[0]["under_price"] == 1.75
    assert rows[0]["ts"] == "2026-06-01T00:00:00+00:00"


def test_no_dedup_time_series(tmp_path):
    hist = tmp_path / "prop_line_history.jsonl"
    log_board_lines(_board(), path=hist, now="2026-06-01T00:00:00+00:00")
    log_board_lines(_board(), path=hist, now="2026-06-02T00:00:00+00:00")
    # Time series: the same prop is appended again, not deduped.
    assert len(load_history(hist)) == 2


def test_closing_snapshot_is_latest_ts(tmp_path):
    hist = tmp_path / "prop_line_history.jsonl"
    log_board_lines(_board(), path=hist, now="2026-06-01T00:00:00+00:00")
    # A later log with a MOVED price -- this is the closing-line proxy.
    later = _board()
    later["edges"][0]["over_price"] = 1.95
    later["edges"][0]["under_price"] = 1.85
    log_board_lines(later, path=hist, now="2026-06-09T12:00:00+00:00")
    snap = closing_snapshot(
        load_history(hist), "AAA vs BBB", "Test Player", "Shots", 1.5, "underdog")
    assert snap is not None
    assert snap["ts"] == "2026-06-09T12:00:00+00:00"
    assert snap["over_price"] == 1.95  # the LATEST logged price wins
    assert snap["under_price"] == 1.85


def test_closing_snapshot_none_when_absent(tmp_path):
    hist = tmp_path / "prop_line_history.jsonl"
    log_board_lines(_board(), path=hist, now="2026-06-01T00:00:00+00:00")
    assert closing_snapshot(
        load_history(hist), "ZZZ vs YYY", "Nobody", "Shots", 1.5) is None


def test_clv_positive_when_better_number():
    # Closing two-way 1.91/1.91 -> fair over ~0.5. Taken OVER at 2.50 implies
    # taken_p = 0.40 < fair_close -> a BETTER number than the close -> CLV > 0.
    clv = clv_vs_close("over", 2.50, 1.91, 1.91)
    assert clv is not None
    assert clv > 0.0


def test_clv_negative_when_worse_number():
    # Taken OVER at 1.50 implies taken_p ~0.667 > fair_close ~0.5 -> worse -> CLV < 0.
    clv = clv_vs_close("over", 1.50, 1.91, 1.91)
    assert clv is not None
    assert clv < 0.0


def test_clv_sign_symmetric_under():
    # Same logic on the UNDER side: a high under price = better number = CLV > 0.
    assert clv_vs_close("under", 2.50, 1.91, 1.91) > 0.0
    assert clv_vs_close("under", 1.50, 1.91, 1.91) < 0.0


def test_clv_none_safe():
    assert clv_vs_close(None, 2.0, 1.91, 1.91) is None
    assert clv_vs_close("over", None, 1.91, 1.91) is None
    assert clv_vs_close("over", 2.0, None, 1.91) is None
    assert clv_vs_close("over", 1.0, 1.91, 1.91) is None  # taken <= 1.0
    assert clv_vs_close("sideways", 2.0, 1.91, 1.91) is None


def test_load_empty_is_list(tmp_path):
    assert load_history(tmp_path / "nope.jsonl") == []


def test_log_never_raises_on_garbage(tmp_path):
    hist = tmp_path / "h.jsonl"
    assert log_board_lines(None, path=hist)["status"].startswith(("ok", "error"))
    assert log_board_lines({"edges": [None, 1, "x"]}, path=hist)["status"] == "ok"
