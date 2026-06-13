"""
tests/platform/test_board_html.py

Tests for scripts/platformkit/frontend/board_html.py.
Uses a synthetic board — does NOT import board.py.
"""
from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

import pytest

# ── ensure repo root is on the path ──────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.frontend.board_html import render_board_html, write_html

# ── synthetic fixtures ────────────────────────────────────────────────────────

_ROW_NBA = {
    "sport": "nba",
    "date": "2026-06-15",
    "home": "Celtics",
    "away": "Lakers",
    "model_prob": 0.62,
    "market_fair_prob": 0.58,
    "edge_vs_market": 0.04,
    "best_book": "FanDuel",
    "best_line": "-110",
    "clv_placeholder": None,
    "calibration_tag": "well-calibrated",
}

_ROW_SOCCER = {
    "sport": "soccer",
    "date": "2026-06-16",
    "home": "Arsenal",
    "away": "Chelsea",
    "model_prob": None,           # deliberately None to test "—" rendering
    "market_fair_prob": 0.45,
    "edge_vs_market": None,
    "best_book": None,
    "best_line": None,
    "clv_placeholder": None,
    "calibration_tag": None,
}

_BOARD: dict[str, list[dict]] = {
    "nba": [_ROW_NBA],
    "soccer": [_ROW_SOCCER],
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _html() -> str:
    return render_board_html(_BOARD)


# ── structural tests ──────────────────────────────────────────────────────────

class TestStructure:
    def test_returns_string(self):
        assert isinstance(_html(), str)

    def test_has_doctype(self):
        assert _html().startswith("<!DOCTYPE html>")

    def test_has_table_tag(self):
        h = _html()
        assert "<table>" in h

    def test_balanced_table_tags(self):
        h = _html()
        assert h.count("<table>") == h.count("</table>")

    def test_has_thead(self):
        h = _html()
        assert "<thead>" in h and "</thead>" in h

    def test_has_tbody(self):
        h = _html()
        assert "<tbody>" in h and "</tbody>" in h

    def test_has_html_and_body(self):
        h = _html()
        assert "<html" in h and "</html>" in h
        assert "<body>" in h and "</body>" in h


# ── column headers ────────────────────────────────────────────────────────────

class TestColumnHeaders:
    def test_sport_header(self):
        assert "Sport" in _html()

    def test_game_header(self):
        assert "Game" in _html()

    def test_date_header(self):
        assert "Date" in _html()

    def test_model_prob_header(self):
        assert "Model Prob" in _html()

    def test_market_fair_header(self):
        assert "Market Fair" in _html()

    def test_diff_header(self):
        assert "Diff" in _html()

    def test_best_book_header(self):
        assert "Best Book" in _html()

    def test_best_line_header(self):
        assert "Best Line" in _html()

    def test_calibration_header(self):
        assert "Calibration" in _html()


# ── row content ───────────────────────────────────────────────────────────────

class TestRowContent:
    def test_contains_home_team(self):
        assert "Celtics" in _html()

    def test_contains_away_team(self):
        assert "Lakers" in _html()

    def test_contains_soccer_home(self):
        assert "Arsenal" in _html()

    def test_contains_soccer_away(self):
        assert "Chelsea" in _html()

    def test_model_prob_formatted_as_pct(self):
        # 0.62 → "62.0%"
        assert "62.0%" in _html()

    def test_market_fair_formatted_as_pct(self):
        # 0.58 → "58.0%"
        assert "58.0%" in _html()

    def test_best_book_present(self):
        assert "FanDuel" in _html()

    def test_calibration_tag_present(self):
        assert "well-calibrated" in _html()

    def test_date_present(self):
        assert "2026-06-15" in _html()


# ── None rendering ────────────────────────────────────────────────────────────

class TestNoneRendering:
    def test_none_renders_as_dash(self):
        h = _html()
        # The em-dash sentinel must appear (None model_prob on soccer row)
        assert "—" in h

    def test_none_not_rendered_as_literal_none(self):
        # "None" should never appear as a cell value
        h = _html()
        # We allow the word in comments/code but NOT as bare cell text;
        # a simple check: no ">None<" pattern
        assert ">None<" not in h


# ── honest banner ─────────────────────────────────────────────────────────────

class TestHonestBanner:
    def test_banner_present(self):
        h = _html()
        assert "banner" in h  # CSS class exists

    def test_markets_efficient_phrase(self):
        h = _html()
        assert "markets are efficient" in h

    def test_no_model_edge_phrase(self):
        h = _html()
        assert "NO model edge is claimed" in h

    def test_clv_devig_mentioned(self):
        h = _html()
        assert "CLV" in h

    def test_default_honest_note_in_output(self):
        h = render_board_html(_BOARD)
        assert "line-shopping" in h

    def test_custom_honest_note_appears(self):
        h = render_board_html(_BOARD, honest_note="CUSTOM_DISCLAIMER_XYZ")
        assert "CUSTOM_DISCLAIMER_XYZ" in h


# ── forbidden edge-claim language ─────────────────────────────────────────────

_FORBIDDEN = [
    "guaranteed",
    "beat the market",
    "+EV edge",
    "sure thing",
    "it's a lock",
    "profit guaranteed",
]


class TestNoEdgeClaimLanguage:
    @pytest.mark.parametrize("phrase", _FORBIDDEN)
    def test_phrase_absent(self, phrase: str):
        h = _html()
        assert phrase.lower() not in h.lower(), (
            f"Forbidden phrase found in HTML: {phrase!r}"
        )


# ── write_html helper ─────────────────────────────────────────────────────────

class TestWriteHtml:
    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "sub", "board.html")
            write_html(_BOARD, out)
            assert os.path.isfile(out)

    def test_written_file_has_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "board.html")
            write_html(_BOARD, out)
            content = Path(out).read_text(encoding="utf-8")
            assert "<table>" in content

    def test_written_file_has_banner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "board.html")
            write_html(_BOARD, out)
            content = Path(out).read_text(encoding="utf-8")
            assert "NO model edge is claimed" in content


# ── edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_board_does_not_raise(self):
        h = render_board_html({})
        assert isinstance(h, str)
        assert "No games today" in h

    def test_empty_sport_list_skipped(self):
        h = render_board_html({"nba": [], "soccer": [_ROW_SOCCER]})
        # nba section should be absent, soccer present
        assert "Chelsea" in h

    def test_all_none_row_renders(self):
        null_row = {k: None for k in _ROW_NBA}
        h = render_board_html({"test": [null_row]})
        assert "<tr>" in h

    def test_negative_diff_renders(self):
        row = dict(_ROW_NBA, edge_vs_market=-0.05)
        h = render_board_html({"nba": [row]})
        assert "-5.0pp" in h

    def test_positive_diff_has_plus_sign(self):
        row = dict(_ROW_NBA, edge_vs_market=0.04)
        h = render_board_html({"nba": [row]})
        assert "+4.0pp" in h

    def test_html_injection_escaped(self):
        row = dict(_ROW_NBA, home="<script>alert(1)</script>")
        h = render_board_html({"nba": [row]})
        assert "<script>alert(1)</script>" not in h
        assert "&lt;script&gt;" in h
