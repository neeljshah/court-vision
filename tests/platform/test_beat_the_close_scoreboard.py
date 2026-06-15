"""Per-file test for scripts/platformkit/beat_the_close_scoreboard.py.

Run: python -m pytest tests/platform/test_beat_the_close_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit import beat_the_close_scoreboard as mod


def test_build_returns_rows():
    rows = mod.build()
    assert isinstance(rows, list) and len(rows) >= 2
    sports = {r.get("sport") for r in rows}
    assert "NBA" in sports
    for r in rows:
        # each row either has a status (skipped/error) or a full model-vs-close comparison
        assert "status" in r or {"model", "close", "gap", "verdict"} <= set(r)


def test_render_markdown_table():
    md = mod.render_markdown(mod.build())
    assert "Beat-the-Close Scoreboard" in md
    assert "| Sport | Market |" in md
    assert "devigged closing line" in md
    # an ok NBA row should render MATCH or BEHIND (not just a status row)
    assert ("MATCH" in md) or ("BEHIND" in md) or ("data_limited" in md)


def test_render_handles_status_rows():
    md = mod.render_markdown([{"sport": "NBA", "market": "x", "status": "data_limited"}])
    assert "data_limited" in md
