"""Per-file unit tests for scripts.platformkit.prop_line_matrix (LS-09).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_line_matrix.py -q

NETWORK-FREE: all tests inject raw_rows; no real HTTP calls.

Acceptance matrix (LS-09):
- Two PropLine same (player, stat, side, line) diff price -> best_over_book is
  the higher-priced book.
- Exactly 1 MatrixRow per (player, stat, line) key.
- Empty input -> [] no exception.
- No $/roi/profit key in output.
- Lower-priced UNDER from one book and higher OVER from another -> both tracked.
- DFS pick'em rows (over_price=None) produce context row with payout_type
  "dfs_pickem"; a sportsbook row for the same key promotes to "sportsbook".
"""
from __future__ import annotations

import json
from typing import List

import pytest

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.prop_line_matrix import build_prop_matrix, MatrixRow

# ---------------------------------------------------------------------------
# Helpers -- canned PropLine factories (no network)
# ---------------------------------------------------------------------------

def _pl(
    player: str,
    stat: str,
    line: float,
    over_price: float | None = None,
    under_price: float | None = None,
    source: str = "book_a",
    payout_type: str = "sportsbook",
    sport: str = "nba",
    event_id: str = "evt-001",
    match: str | None = "Team A vs Team B",
    as_of: str | None = "2026-06-19T20:00:00+00:00",
) -> PropLine:
    """Convenience factory for test PropLine rows."""
    return PropLine(
        sport=sport,
        event_id=event_id,
        match=match,
        player=player,
        team="Team A",
        stat=stat,
        line=line,
        over_price=over_price,
        under_price=under_price,
        payout_type=payout_type,
        source=source,
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Tests: best-book selection
# ---------------------------------------------------------------------------

def test_higher_over_price_wins():
    """Two rows same key, different OVER price -> best_over_book is higher-priced."""
    rows = [
        _pl("LeBron James", "Points", 25.5, over_price=1.90, source="book_a"),
        _pl("LeBron James", "Points", 25.5, over_price=1.95, source="book_b"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1, "exactly one row per key"
    row = matrix[0]
    assert row.best_over_book == "book_b"
    assert row.best_over_price == pytest.approx(1.95)


def test_higher_under_price_wins():
    """Two rows same key, different UNDER price -> best_under_book is higher."""
    rows = [
        _pl("Stephen Curry", "Assists", 6.5, under_price=1.85, source="book_a"),
        _pl("Stephen Curry", "Assists", 6.5, under_price=1.92, source="book_b"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    row = matrix[0]
    assert row.best_under_book == "book_b"
    assert row.best_under_price == pytest.approx(1.92)


def test_best_price_split_across_books():
    """Best OVER and best UNDER can come from different books."""
    rows = [
        _pl("Nikola Jokic", "Rebounds", 12.5,
            over_price=1.95, under_price=1.82, source="book_a"),
        _pl("Nikola Jokic", "Rebounds", 12.5,
            over_price=1.88, under_price=1.91, source="book_b"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    row = matrix[0]
    assert row.best_over_book == "book_a"
    assert row.best_over_price == pytest.approx(1.95)
    assert row.best_under_book == "book_b"
    assert row.best_under_price == pytest.approx(1.91)


def test_invalid_price_not_one_point_zero_not_promoted():
    """Price <= 1.0 (e.g. 0.85 or 1.0) is never promoted as best."""
    rows = [
        _pl("Kevin Durant", "Points", 27.5, over_price=0.85, source="bad_book"),
        _pl("Kevin Durant", "Points", 27.5, over_price=1.90, source="good_book"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    row = matrix[0]
    assert row.best_over_book == "good_book"
    assert row.best_over_price == pytest.approx(1.90)


# ---------------------------------------------------------------------------
# Tests: exactly one row per key
# ---------------------------------------------------------------------------

def test_exactly_one_row_per_key():
    """Three rows all same (player, stat, line) -> exactly one MatrixRow."""
    rows = [
        _pl("Luka Doncic", "Points", 30.5, over_price=1.90, source="dk"),
        _pl("Luka Doncic", "Points", 30.5, over_price=1.92, source="fd"),
        _pl("Luka Doncic", "Points", 30.5, over_price=1.88, source="caesars"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1


def test_different_stats_produce_separate_rows():
    """Same player, different stat -> separate rows."""
    rows = [
        _pl("Giannis Antetokounmpo", "Points", 29.5, over_price=1.91),
        _pl("Giannis Antetokounmpo", "Rebounds", 11.5, over_price=1.91),
        _pl("Giannis Antetokounmpo", "Assists", 5.5, over_price=1.91),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 3
    stats = {r.stat for r in matrix}
    assert stats == {"Points", "Rebounds", "Assists"}


def test_different_lines_produce_separate_rows():
    """Same player+stat, different line -> separate rows."""
    rows = [
        _pl("Joel Embiid", "Points", 27.5, over_price=1.91),
        _pl("Joel Embiid", "Points", 28.5, over_price=1.91),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 2
    lines = sorted(r.line for r in matrix)
    assert lines == [27.5, 28.5]


def test_multiple_players_all_represented():
    """Each distinct player+stat+line gets exactly one row."""
    rows = [
        _pl("Player A", "Points", 20.5, over_price=1.90, source="dk"),
        _pl("Player A", "Points", 20.5, over_price=1.92, source="fd"),
        _pl("Player B", "Assists", 5.5, over_price=1.88, source="dk"),
        _pl("Player B", "Assists", 5.5, over_price=1.86, source="fd"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 2
    players = {r.player for r in matrix}
    assert players == {"Player A", "Player B"}


def test_row_key_case_insensitive():
    """Player/stat keys are normalized so case variants merge to one row."""
    rows = [
        _pl("lebron james", "points", 25.5, over_price=1.90, source="dk"),
        _pl("LeBron James", "Points", 25.5, over_price=1.95, source="fd"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1, "case variants must merge to one row"
    assert matrix[0].best_over_price == pytest.approx(1.95)


# ---------------------------------------------------------------------------
# Tests: empty input
# ---------------------------------------------------------------------------

def test_empty_raw_rows_returns_empty_list():
    """Empty raw_rows -> [] with no exception."""
    matrix = build_prop_matrix([], "nba", raw_rows=[])
    assert matrix == []


def test_empty_providers_no_raw_rows_returns_empty_list():
    """No providers and no raw_rows -> [] with no exception."""
    matrix = build_prop_matrix([], "nba")
    assert matrix == []


def test_none_raw_rows_and_unavailable_providers():
    """Provider returning unavailable sentinel -> [] no crash."""

    class _UnavailableProvider:
        name = "unavailable"

        def fetch_props(self, sport):
            return {"status": "UNAVAILABLE", "reason": "offseason"}

    matrix = build_prop_matrix([_UnavailableProvider()], "nba")
    assert matrix == []


def test_provider_that_raises_does_not_crash():
    """A provider that raises should be silently skipped; result is []."""

    class _ErrorProvider:
        name = "error_provider"

        def fetch_props(self, sport):
            raise RuntimeError("network timeout")

    matrix = build_prop_matrix([_ErrorProvider()], "nba")
    assert matrix == []


# ---------------------------------------------------------------------------
# Tests: no $ / roi / profit key
# ---------------------------------------------------------------------------

def test_no_dollar_or_roi_key_in_output():
    """MatrixRow.to_dict() must not contain $, roi, profit, payout dollar fields."""
    rows = [
        _pl("Anthony Davis", "Points", 24.5,
            over_price=1.92, under_price=1.88, source="dk"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    serialized = json.dumps(matrix[0].to_dict()).lower()
    for banned in ("roi", "profit", "dollar"):
        assert banned not in serialized, (
            "banned key/value '%s' found in MatrixRow output" % banned)


# ---------------------------------------------------------------------------
# Tests: payout_type logic
# ---------------------------------------------------------------------------

def test_dfs_pickem_row_has_payout_type_dfs():
    """Row with no real price (over_price=None) -> payout_type='dfs_pickem'."""
    rows = [
        _pl("Trae Young", "Points", 26.5,
            over_price=None, under_price=None, payout_type="dfs_pickem"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    assert matrix[0].payout_type == "dfs_pickem"
    assert matrix[0].best_over_price is None
    assert matrix[0].best_under_price is None


def test_sportsbook_promotes_payout_type():
    """DFS row + sportsbook row same key -> payout_type='sportsbook'."""
    rows = [
        _pl("Damian Lillard", "Points", 23.5,
            over_price=None, under_price=None, payout_type="dfs_pickem",
            source="prizepicks"),
        _pl("Damian Lillard", "Points", 23.5,
            over_price=1.91, under_price=1.91, payout_type="sportsbook",
            source="draftkings"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    assert matrix[0].payout_type == "sportsbook"
    assert matrix[0].best_over_price == pytest.approx(1.91)


# ---------------------------------------------------------------------------
# Tests: output is sorted
# ---------------------------------------------------------------------------

def test_output_sorted_by_player_stat_line():
    """Output rows are sorted by (player, stat, line) ascending."""
    rows = [
        _pl("Zion Williamson", "Points", 25.5, over_price=1.90),
        _pl("Ant Edwards", "Points", 22.5, over_price=1.90),
        _pl("Ant Edwards", "Assists", 4.5, over_price=1.90),
        _pl("Ant Edwards", "Points", 20.5, over_price=1.90),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 4
    players = [r.player for r in matrix]
    # "Ant Edwards" (lowercase 'a') sorts before "Zion Williamson"
    assert players[0] == "Ant Edwards"
    assert players[-1] == "Zion Williamson"
    # Ant Edwards rows: Assists < Points (alphabetically)
    ant_rows = [r for r in matrix if r.player == "Ant Edwards"]
    assert ant_rows[0].stat == "Assists"
    # Points rows are sorted by line ascending: 20.5, 22.5
    assert ant_rows[1].line == 20.5
    assert ant_rows[2].line == 22.5


# ---------------------------------------------------------------------------
# Tests: as_of tracks most-recent timestamp
# ---------------------------------------------------------------------------

def test_as_of_takes_most_recent():
    """as_of in MatrixRow reflects the most-recent contributing row."""
    rows = [
        _pl("Chris Paul", "Assists", 7.5, over_price=1.90,
            source="dk", as_of="2026-06-19T18:00:00+00:00"),
        _pl("Chris Paul", "Assists", 7.5, over_price=1.88,
            source="fd", as_of="2026-06-19T20:30:00+00:00"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    assert matrix[0].as_of == "2026-06-19T20:30:00+00:00"


# ---------------------------------------------------------------------------
# Tests: MatrixRow.to_dict() is JSON-serializable
# ---------------------------------------------------------------------------

def test_to_dict_is_json_serializable():
    """MatrixRow.to_dict() must be JSON-serializable with no custom objects."""
    rows = [
        _pl("Kawhi Leonard", "Points", 22.5,
            over_price=1.91, under_price=1.89, source="draftkings"),
    ]
    matrix = build_prop_matrix([], "nba", raw_rows=rows)
    assert len(matrix) == 1
    d = matrix[0].to_dict()
    serialized = json.dumps(d)  # must not raise
    parsed = json.loads(serialized)
    assert parsed["player"] == "Kawhi Leonard"
    assert parsed["stat"] == "Points"
    assert parsed["best_over_book"] == "draftkings"
    assert "best_over_price" in parsed
    assert "best_under_price" in parsed
