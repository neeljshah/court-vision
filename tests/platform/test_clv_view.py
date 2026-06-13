"""tests/platform/test_clv_view.py — CLV dashboard row-shaper tests.

Routes all ledger IO through tmp_path; no network, no slow loads.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.frontend import clv as C
from scripts.platformkit.frontend import clv_view as V

_BANNED = ("guaranteed", "profit", "beat the market", "+ev edge", "lock")

_EXPECTED_KEYS = {
    "sport", "event_id", "market", "side", "bet_decimal",
    "close_decimal", "clv_pct", "ev_delta_usd", "line_clv", "settled",
}


def _seed(tmp_path) -> None:
    pid1 = C.append_pick("nba", "E1", "ml", "home", bet_odds=2.5, root=tmp_path)
    C.settle_pick(pid1, close_odds=2.2, root=tmp_path, sport="nba")
    C.append_pick("soccer", "E2", "ou", "over", bet_odds=2.0, root=tmp_path)


def test_clv_board_rows_shape(tmp_path):
    _seed(tmp_path)
    rows = V.clv_board_rows(root=tmp_path)
    assert len(rows) == 2
    for r in rows:
        assert _EXPECTED_KEYS.issubset(r.keys())
    settled = [r for r in rows if r["settled"]]
    assert len(settled) == 1
    assert settled[0]["clv_pct"] is not None


def test_clv_dashboard_shape(tmp_path):
    _seed(tmp_path)
    dash = V.clv_dashboard(root=tmp_path)
    assert set(dash.keys()) == {"clv"}
    assert isinstance(dash["clv"], list)
    assert len(dash["clv"]) == 2


def test_clv_view_renders_without_crashing(tmp_path):
    _seed(tmp_path)
    board_html = pytest.importorskip(
        "scripts.platformkit.frontend.board_html",
        reason="board_html unavailable in this tree",
    )
    dash = V.clv_dashboard(root=tmp_path)
    html_str = board_html.render_board_html(dash, honest_note=V._HONEST_NOTE)
    assert "<table" in html_str
    assert "nba" in html_str
    # CLV rows must not blow up the generic renderer.
    assert "<!DOCTYPE html>" in html_str


def test_no_banned_words(tmp_path):
    # Scope: the strings WE emit (honest_note + row data). board_html's own
    # static CSS (e.g. "inline-block") is third-party and not CLV content.
    _seed(tmp_path)
    import json as _json
    emitted = (V._HONEST_NOTE + " " + _json.dumps(V.clv_dashboard(root=tmp_path),
                                                  default=str)).lower()
    for w in _BANNED:
        assert w not in emitted, f"banned substring {w!r} leaked into output"
