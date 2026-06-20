"""Per-file tests for scripts.platformkit.prop_edge_bestline (NETWORK-FREE).

Acceptance criteria (LS-03):
  1. Two providers quote same (player, stat, side) at different prices -> higher
     payout wins; exactly ONE row per key in the output.
  2. Single provider -> passthrough (no mutation, correct count).
  3. Empty / all-UNAVAILABLE providers -> is_available=False, honest reason,
     no $ P&L field anywhere.
  4. select_best_line locates the merged row by (player, stat, line) key.
  5. best_line_summary: no $ field; is_pm=False.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/test_prop_edge_bestline.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.odds_provider.base import unavailable
from scripts.platformkit.prop_edge_bestline import (
    BestLineResult,
    gather_best_lines,
    select_best_line,
    best_line_summary,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _line(
    player: str,
    stat: str,
    line: float,
    over_price: float | None,
    under_price: float | None,
    *,
    source: str = "provA",
    event_id: str = "ev1",
    payout_type: str = "sportsbook",
) -> PropLine:
    return PropLine(
        sport="soccer_intl",
        event_id=event_id,
        match="COL v FRA",
        player=player,
        team="COL",
        stat=stat,
        line=line,
        over_price=over_price,
        under_price=under_price,
        payout_type=payout_type,
        source=source,
        as_of="2026-06-19T00:00:00+00:00",
    )


class _CannedProvider:
    def __init__(self, name: str, rows: list) -> None:
        self.name = name
        self._rows = rows

    def fetch_props(self, sport: str) -> list:
        return list(self._rows)


class _DownProvider:
    name = "down_src"

    def fetch_props(self, sport: str) -> dict:
        return unavailable("provider is offline")


# ---------------------------------------------------------------------------
# Tests: two providers, same key, different price -> higher wins
# ---------------------------------------------------------------------------

def test_two_providers_same_key_over_price_higher_wins():
    """Higher over_price from provider B replaces the lower from provider A."""
    row_a = _line("Mbappe", "Shots", 2.5, over_price=1.80, under_price=2.10, source="A")
    row_b = _line("Mbappe", "Shots", 2.5, over_price=1.95, under_price=2.00, source="B")

    prov_a = _CannedProvider("A", [row_a])
    prov_b = _CannedProvider("B", [row_b])

    result = gather_best_lines([prov_a, prov_b], "soccer_intl")

    assert result.is_available
    assert len(result.rows) == 1, "must be exactly one row per key"
    merged = result.rows[0]
    # over_price: B's 1.95 beats A's 1.80
    assert merged.over_price == 1.95, "higher over_price should win"
    # under_price: A's 2.10 beats B's 2.00
    assert merged.under_price == 2.10, "higher under_price should win"


def test_two_providers_same_key_exactly_one_row():
    """Duplicate key from two providers collapses to exactly 1 row."""
    rows_a = [_line("Diaz", "Goals", 0.5, over_price=2.00, under_price=1.85, source="A")]
    rows_b = [_line("Diaz", "Goals", 0.5, over_price=1.90, under_price=1.95, source="B")]

    result = gather_best_lines(
        [_CannedProvider("A", rows_a), _CannedProvider("B", rows_b)], "soccer_intl"
    )

    assert result.is_available
    assert len(result.rows) == 1
    merged = result.rows[0]
    assert merged.player == "Diaz"
    assert merged.stat == "Goals"
    assert merged.over_price == 2.00
    assert merged.under_price == 1.95


def test_different_players_different_stats_no_collapsing():
    """Different keys must NOT be collapsed -- each survives as its own row."""
    rows_a = [
        _line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A"),
        _line("Diaz", "Goals", 0.5, 2.10, 1.75, source="A"),
    ]
    rows_b = [
        _line("Mbappe", "Shots On Target", 1.5, 1.80, 2.00, source="B"),
    ]

    result = gather_best_lines(
        [_CannedProvider("A", rows_a), _CannedProvider("B", rows_b)], "soccer_intl"
    )

    assert result.is_available
    # 3 distinct (player, stat, line) keys -> 3 rows
    assert len(result.rows) == 3


def test_same_key_case_insensitive_merge():
    """Provider label-casing differences on the same player/stat still merge."""
    row_a = _line("kylian mbappe", "shots", 2.5, 1.85, 1.85, source="A")
    row_b = _line("Kylian Mbappe", "Shots", 2.5, 1.95, 1.75, source="B")

    result = gather_best_lines(
        [_CannedProvider("A", [row_a]), _CannedProvider("B", [row_b])], "soccer_intl"
    )

    assert result.is_available
    assert len(result.rows) == 1
    merged = result.rows[0]
    assert merged.over_price == 1.95   # B wins on over
    assert merged.under_price == 1.85  # A wins on under


# ---------------------------------------------------------------------------
# Tests: single provider -> passthrough
# ---------------------------------------------------------------------------

def test_single_provider_passthrough():
    """A single provider's rows pass through unchanged; count == original."""
    rows = [
        _line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A"),
        _line("Diaz",   "Goals", 0.5, 2.00, 1.80, source="A"),
    ]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    assert result.is_available
    assert len(result.rows) == 2

    # Values unchanged
    shots_row = next(r for r in result.rows if r.stat == "Shots")
    assert shots_row.over_price == 1.90
    assert shots_row.under_price == 1.90


def test_single_provider_one_row_passthrough():
    """Single provider, single row: is_available True, exactly 1 row."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.80, 2.10, source="A")]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    assert result.is_available
    assert len(result.rows) == 1
    assert result.rows[0].over_price == 1.80


# ---------------------------------------------------------------------------
# Tests: empty / UNAVAILABLE providers -> honest UNAVAILABLE
# ---------------------------------------------------------------------------

def test_all_providers_down_returns_unavailable():
    """When all providers return UNAVAILABLE, is_available is False."""
    result = gather_best_lines([_DownProvider()], "soccer_intl")

    assert not result.is_available
    assert result.unavailable_reason is not None
    assert len(result.rows) == 0


def test_empty_provider_list_returns_unavailable():
    """No providers configured -> is_available False, honest reason."""
    result = gather_best_lines([], "soccer_intl")

    assert not result.is_available
    assert result.unavailable_reason == "no providers configured"
    assert len(result.rows) == 0


def test_all_providers_return_empty_list_returns_unavailable():
    """Providers that return [] -> is_available False."""
    result = gather_best_lines([_CannedProvider("A", [])], "soccer_intl")

    assert not result.is_available
    assert len(result.rows) == 0


def test_mixed_one_down_one_ok_still_available():
    """One down + one ok provider: the ok provider's rows survive."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A")]
    result = gather_best_lines(
        [_DownProvider(), _CannedProvider("A", rows)], "soccer_intl"
    )

    assert result.is_available
    assert len(result.rows) == 1
    # Source health reflects the down provider
    assert "down_src" in result.sources
    assert "unavailable" in result.sources["down_src"]


def test_to_unavailable_dict_shape():
    """to_unavailable_dict returns the sentinel shape callers expect."""
    result = gather_best_lines([_DownProvider()], "soccer_intl")

    d = result.to_unavailable_dict()
    assert d["status"] == "unavailable"
    assert "reason" in d
    assert "sources" in d
    # NO dollar / P&L field
    assert "pnl" not in d
    assert "profit" not in d
    assert "roi" not in d


# ---------------------------------------------------------------------------
# Tests: no $ field anywhere
# ---------------------------------------------------------------------------

def test_no_dollar_pnl_field_in_rows():
    """PropLine rows returned by gather_best_lines must never carry $ P&L."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A")]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    for row in result.rows:
        d = row.to_dict()
        for key in d:
            assert "pnl" not in key.lower()
            assert "profit" not in key.lower()
            assert "roi" not in key.lower()
            assert key != "dollars"


def test_best_line_summary_no_dollar_field():
    """best_line_summary dict must not carry any $ P&L key."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A")]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")
    s = best_line_summary(result)

    assert "is_pm" in s and s["is_pm"] is False
    for key in s:
        assert "pnl" not in key.lower()
        assert "profit" not in key.lower()
        assert "roi" not in key.lower()


# ---------------------------------------------------------------------------
# Tests: select_best_line lookup
# ---------------------------------------------------------------------------

def test_select_best_line_found():
    """select_best_line finds the right merged row by (player, stat, line)."""
    rows = [
        _line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A"),
        _line("Diaz",   "Goals", 0.5, 2.00, 1.80, source="A"),
    ]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    found = select_best_line(result.rows, "Mbappe", "Shots", 2.5)
    assert found is not None
    assert found.over_price == 1.90


def test_select_best_line_case_insensitive():
    """Lookup is case/whitespace insensitive."""
    rows = [_line("Kylian Mbappe", "Shots On Target", 1.5, 1.85, 2.00, source="A")]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    found = select_best_line(result.rows, "kylian mbappe", "shots on target", 1.5)
    assert found is not None
    assert found.under_price == 2.00


def test_select_best_line_not_found_returns_none():
    """select_best_line returns None for a player/stat not in the rows."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A")]
    result = gather_best_lines([_CannedProvider("A", rows)], "soccer_intl")

    assert select_best_line(result.rows, "Unknown Player", "Shots", 2.5) is None
    assert select_best_line(result.rows, "Mbappe", "Goals", 2.5) is None
    assert select_best_line(result.rows, "Mbappe", "Shots", 3.5) is None


# ---------------------------------------------------------------------------
# Tests: sportsbook row beats pick'em row for same key
# ---------------------------------------------------------------------------

def test_sportsbook_beats_pickem_for_same_key():
    """When one provider has real prices and another has pick'em, real price wins."""
    pickem = _line("Mbappe", "Shots", 2.5, over_price=None, under_price=None,
                   source="pickem_src", payout_type="dfs_pickem")
    priced = _line("Mbappe", "Shots", 2.5, over_price=1.90, under_price=1.90,
                   source="book_src", payout_type="sportsbook")

    result = gather_best_lines(
        [_CannedProvider("pickem_src", [pickem]),
         _CannedProvider("book_src", [priced])],
        "soccer_intl",
    )

    assert result.is_available
    assert len(result.rows) == 1
    merged = result.rows[0]
    assert merged.over_price == 1.90
    assert merged.under_price == 1.90
    assert merged.payout_type == "sportsbook"


def test_pickem_survives_when_no_sportsbook():
    """When only a pick'em provider exists, its row surfaces with over_price=None."""
    pickem = _line("Mbappe", "Shots", 2.5, over_price=None, under_price=None,
                   source="pickem_src", payout_type="dfs_pickem")

    result = gather_best_lines([_CannedProvider("pickem_src", [pickem])], "soccer_intl")

    assert result.is_available
    assert len(result.rows) == 1
    merged = result.rows[0]
    assert merged.over_price is None
    assert merged.under_price is None


# ---------------------------------------------------------------------------
# Tests: source health reporting
# ---------------------------------------------------------------------------

def test_sources_dict_populated():
    """result.sources contains an entry per provider."""
    rows = [_line("Mbappe", "Shots", 2.5, 1.90, 1.90, source="A")]
    result = gather_best_lines(
        [_CannedProvider("A", rows), _DownProvider()], "soccer_intl"
    )

    assert "A" in result.sources
    assert "down_src" in result.sources
    assert "ok" in result.sources["A"]
    assert "unavailable" in result.sources["down_src"]
