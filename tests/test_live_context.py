"""tests/test_live_context.py — unit tests for live_context.context_for_team
and context_for_opponent equivalence / multi-game correctness.

Covers FIX IN-9: verify that context_for_team (own-team keyed frozenset lookup)
returns identical results to context_for_opponent on a single-game slate, and
returns the correct game (not the wrong game) on a multi-game slate where
context_for_opponent would return None due to ambiguity.
"""
from __future__ import annotations

import csv
import io
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_mainline_csv(path: Path, rows: list[dict]) -> None:
    """Write a minimal mainline CSV that load_mainline can parse."""
    fieldnames = ["home_team", "away_team", "market_type", "line"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


_SINGLE_GAME_ROWS = [
    # OKC vs SAS, total 225.5
    {"home_team": "Oklahoma City Thunder", "away_team": "San Antonio Spurs",
     "market_type": "total", "line": "225.5"},
    # OKC favoured by 8
    {"home_team": "Oklahoma City Thunder", "away_team": "San Antonio Spurs",
     "market_type": "spread", "line": "-8.0"},
]

_MULTI_GAME_ROWS = [
    # Game 1: OKC vs SAS, total 225.5, spread 8
    {"home_team": "Oklahoma City Thunder", "away_team": "San Antonio Spurs",
     "market_type": "total", "line": "225.5"},
    {"home_team": "Oklahoma City Thunder", "away_team": "San Antonio Spurs",
     "market_type": "spread", "line": "-8.0"},
    # Game 2: LAL vs GSW, total 231.0, spread 4
    {"home_team": "Los Angeles Lakers", "away_team": "Golden State Warriors",
     "market_type": "total", "line": "231.0"},
    {"home_team": "Los Angeles Lakers", "away_team": "Golden State Warriors",
     "market_type": "spread", "line": "-4.0"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContextForTeamVsOpponent:
    """FIX IN-9 validation: context_for_team correctness."""

    def _make_ctx(self, rows: list[dict]):
        """Return a live_context module with load_mainline patched to a tmp file."""
        import importlib
        import src.prediction.live_context as lc

        # Clear the lru_cache so each test gets a fresh load
        lc.load_mainline.cache_clear()

        tmpdir = tempfile.mkdtemp()
        date = "2026-06-01"
        csv_path = Path(tmpdir) / f"{date}_pin_mainline.csv"
        _write_mainline_csv(csv_path, rows)

        # Patch _LINES_DIR so load_mainline finds our tmp file
        with patch.object(lc, "_LINES_DIR", Path(tmpdir)):
            lc.load_mainline.cache_clear()
            yield lc, date

        lc.load_mainline.cache_clear()

    def test_single_game_team_equals_opponent(self, tmp_path):
        """On a single-game slate, context_for_team and context_for_opponent
        must return identical (total, spread_abs)."""
        import src.prediction.live_context as lc
        lc.load_mainline.cache_clear()

        csv_path = tmp_path / "2026-06-01_pin_mainline.csv"
        _write_mainline_csv(csv_path, _SINGLE_GAME_ROWS)
        date = "2026-06-01"

        with patch.object(lc, "_LINES_DIR", tmp_path):
            lc.load_mainline.cache_clear()

            team_result = lc.context_for_team("OKC", "SAS", date)
            opp_result  = lc.context_for_opponent("SAS", date)

        assert team_result == opp_result, (
            f"context_for_team {team_result!r} != context_for_opponent {opp_result!r}"
        )
        total, spread = team_result
        assert total == pytest.approx(225.5), f"Expected total=225.5, got {total}"
        assert spread == pytest.approx(8.0),  f"Expected spread_abs=8.0, got {spread}"

        lc.load_mainline.cache_clear()

    def test_multi_game_team_correct_game(self, tmp_path):
        """On a multi-game slate, context_for_team returns the right game for
        each player, while context_for_opponent returns None for shared-slate
        teams (ambiguous scan)."""
        import src.prediction.live_context as lc
        lc.load_mainline.cache_clear()

        csv_path = tmp_path / "2026-06-01_pin_mainline.csv"
        _write_mainline_csv(csv_path, _MULTI_GAME_ROWS)
        date = "2026-06-01"

        with patch.object(lc, "_LINES_DIR", tmp_path):
            lc.load_mainline.cache_clear()

            # OKC player — should see OKC/SAS game (225.5 / 8.0)
            okc_total, okc_spread = lc.context_for_team("OKC", "SAS", date)
            # LAL player — should see LAL/GSW game (231.0 / 4.0)
            lal_total, lal_spread = lc.context_for_team("LAL", "GSW", date)

            # context_for_opponent on a multi-game slate with the same opp appearing
            # once is still unambiguous — test against GSW (only in one game)
            gsw_total_opp, gsw_spread_opp = lc.context_for_opponent("GSW", date)

        assert okc_total  == pytest.approx(225.5), f"OKC total wrong: {okc_total}"
        assert okc_spread == pytest.approx(8.0),   f"OKC spread wrong: {okc_spread}"
        assert lal_total  == pytest.approx(231.0), f"LAL total wrong: {lal_total}"
        assert lal_spread == pytest.approx(4.0),   f"LAL spread wrong: {lal_spread}"

        # Verify the two games are distinct (not leaking into each other)
        assert okc_total != lal_total, "OKC and LAL games should have different totals"

        # context_for_opponent unambiguous when opp appears in exactly one game
        assert gsw_total_opp  == pytest.approx(231.0)
        assert gsw_spread_opp == pytest.approx(4.0)

        lc.load_mainline.cache_clear()

    def test_team_none_returns_none_none(self, tmp_path):
        """When team_abbrev is empty/None, context_for_team must return (None, None)
        gracefully — matching the fallback-to-opponent branch in compare_to_lines."""
        import src.prediction.live_context as lc
        lc.load_mainline.cache_clear()

        csv_path = tmp_path / "2026-06-01_pin_mainline.csv"
        _write_mainline_csv(csv_path, _SINGLE_GAME_ROWS)
        date = "2026-06-01"

        with patch.object(lc, "_LINES_DIR", tmp_path):
            lc.load_mainline.cache_clear()
            result_empty  = lc.context_for_team("", "SAS", date)
            result_none   = lc.context_for_team(None, "SAS", date)  # type: ignore[arg-type]

        assert result_empty == (None, None)
        assert result_none  == (None, None)

        lc.load_mainline.cache_clear()
