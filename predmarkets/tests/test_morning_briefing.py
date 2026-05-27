"""Unit tests for the morning briefing renderer — no network."""

from __future__ import annotations

from datetime import date

from predmarkets.morning_briefing import _render_markdown


def test_render_handles_no_pending() -> None:
    md = _render_markdown(
        snap_date=date(2026, 5, 27),
        settle={"checked": 0, "graded": 0, "still_pending": 0},
        snapshot={"skipped": True},
        scan={"venues": {}},
        pnl={"graded": 0, "wins": 0, "losses": 0, "hit_rate": None,
             "pnl_dollars": 0.0, "roi": None, "pending": 0,
             "last_7d": {"graded": 0, "wins": 0, "losses": 0,
                         "pnl_dollars": 0.0, "roi": None}},
        ledger_path="/tmp/x.csv",
    )
    assert "# Predmarkets Morning Briefing — 2026-05-27" in md
    assert "No pending rows" in md
    assert "Skipped (--skip-snapshot)" in md
    assert "ROI=n/a" in md  # roi=None should render as n/a, not crash


def test_render_includes_top_edges() -> None:
    md = _render_markdown(
        snap_date=date(2026, 5, 27),
        settle={"checked": 5, "graded": 2, "still_pending": 3},
        snapshot={"skipped": True},
        scan={"venues": {
            "polymarket": {
                "scanned": 1500, "edges": 3, "placed": 2,
                "skipped_zero_stake": 1, "skipped_duplicate": 0,
                "top_edges": [
                    {"side": "YES", "price": 0.30, "model_prob": 0.40,
                     "edge_pp": 0.10, "stake_dollars": 10.0,
                     "expected_value_dollars": 1.5,
                     "category": "Crypto",
                     "question": "Will BTC hit $X?"},
                ],
            },
        }},
        pnl={"graded": 4, "wins": 3, "losses": 1, "hit_rate": 0.75,
             "pnl_dollars": 12.5, "roi": 0.30, "pending": 3,
             "last_7d": {"graded": 4, "wins": 3, "losses": 1,
                         "pnl_dollars": 12.5, "roi": 0.30}},
        ledger_path="/tmp/x.csv",
    )
    assert "Edges found: **3**" in md
    assert "Will BTC hit $X?" in md
    assert "ROI=30.0%" in md
    assert "hit_rate=75.0%" in md
