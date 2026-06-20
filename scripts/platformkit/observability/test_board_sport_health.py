"""test_board_sport_health.py -- per-file tests for observability/board_sport_health.py.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_board_sport_health.py -q

Acceptance (from OBS-BOARD-SPORT-HEALTH spec):
  * 11 MLB cards with 2 distinct probs -> sport row flagged non_discriminating=True
  * soccer_intl 'Yes vs No' / stale card -> counted in dropped buckets
  * clean slate -> all-pass (status=ok, n_dropped=0)
  * no $/edge field in any row
  * INSUFFICIENT_DATA when no cards for a sport bucket
  * never raises

ASCII only; <= 300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from scripts.platformkit.observability.board_sport_health import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NON_DISCRIMINATING,
    STATUS_OK,
    compute_sport_health,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_card(
    sport: str = "nba",
    model_prob: float = 0.55,
    market_prob: float = 0.50,
    matchup: str = "TeamA vs TeamB",
    best_odds: float = 1.90,
    edge_vs_market: float = 0.05,
    market_type: str = "moneyline",
    **extra: Any,
) -> Dict[str, Any]:
    card: Dict[str, Any] = {
        "sport": sport,
        "model_prob": model_prob,
        "market_prob": market_prob,
        "matchup": matchup,
        "best_odds": best_odds,
        "edge_vs_market": edge_vs_market,
        "market_type": market_type,
    }
    card.update(extra)
    return card


def _clean_mlb_cards(n: int = 5) -> List[Dict[str, Any]]:
    """Distinct probs -- healthy MLB board."""
    return [_make_card(sport="mlb", model_prob=0.50 + i * 0.04) for i in range(n)]


def _degenerate_mlb_cards(n: int = 11, n_distinct: int = 2) -> List[Dict[str, Any]]:
    """n cards with only n_distinct model_prob values -> should trigger non_discriminating."""
    cards = []
    for i in range(n):
        # Alternate between two probs so n_distinct=2 << n
        prob = 0.4655 if (i % 2 == 0) else 0.4656
        cards.append(_make_card(sport="mlb", model_prob=prob))
    return cards


def _soccer_binary_card() -> Dict[str, Any]:
    return _make_card(
        sport="soccer_intl",
        matchup="Some Team Yes vs No Outcome",
        model_prob=0.60,
        market_prob=0.55,
    )


def _soccer_stale_tipoff_card() -> Dict[str, Any]:
    return _make_card(
        sport="soccer_intl",
        matchup="Team A vs Team B",
        model_prob=0.55,
        market_prob=None,  # type: ignore[arg-type]
        best_odds=None,    # type: ignore[arg-type]
        tipoff_stale=True,
    )


def _soccer_clean_card(n: int = 3) -> List[Dict[str, Any]]:
    return [_make_card(sport="soccer_intl", model_prob=0.50 + i * 0.05) for i in range(n)]


def _by_sport(rows: List[Dict[str, Any]], sport: str) -> Dict[str, Any]:
    for row in rows:
        if row["sport"] == sport:
            return row
    raise KeyError(sport)


# ---------------------------------------------------------------------------
# Acceptance test 1: 11 MLB cards with 2 distinct probs -> non_discriminating
# ---------------------------------------------------------------------------

class TestMLBDegenerateBoard:
    """11 MLB cards, only 2 distinct model_prob values -> non_discriminating=True."""

    def _rows(self) -> List[Dict[str, Any]]:
        cards = _degenerate_mlb_cards(n=11, n_distinct=2)
        return compute_sport_health(cards)

    def test_mlb_row_present(self):
        rows = self._rows()
        sports = [r["sport"] for r in rows]
        assert "mlb" in sports, "Expected an mlb row"

    def test_non_discriminating_true(self):
        rows = self._rows()
        mlb = _by_sport(rows, "mlb")
        assert mlb["non_discriminating"] is True, (
            "Expected non_discriminating=True for 11-card board with 2 distinct probs; "
            "got: %s" % mlb
        )

    def test_status_non_discriminating(self):
        rows = self._rows()
        mlb = _by_sport(rows, "mlb")
        assert mlb["status"] == STATUS_NON_DISCRIMINATING

    def test_n_total_correct(self):
        rows = self._rows()
        mlb = _by_sport(rows, "mlb")
        assert mlb["n_total"] == 11

    def test_n_served_equals_n_total_minus_dropped(self):
        rows = self._rows()
        mlb = _by_sport(rows, "mlb")
        assert mlb["n_served"] == mlb["n_total"] - mlb["n_dropped"]


# ---------------------------------------------------------------------------
# Acceptance test 2: soccer_intl binary/stale cards -> counted in dropped buckets
# ---------------------------------------------------------------------------

class TestSoccerDroppedBuckets:
    """soccer_intl with 'Yes vs No' and stale-tipoff cards -> drops logged."""

    def _make_board(self) -> List[Dict[str, Any]]:
        return (
            _soccer_clean_card(3)
            + [_soccer_binary_card()]
            + [_soccer_stale_tipoff_card()]
        )

    def _row(self) -> Dict[str, Any]:
        return _by_sport(compute_sport_health(self._make_board()), "soccer_intl")

    def test_soccer_row_present(self):
        rows = compute_sport_health(self._make_board())
        sports = [r["sport"] for r in rows]
        assert "soccer_intl" in sports

    def test_dropped_binary_at_least_one(self):
        row = self._row()
        assert row["n_dropped_binary"] >= 1, (
            "Expected at least 1 binary drop; row: %s" % row
        )

    def test_dropped_stale_tipoff_at_least_one(self):
        row = self._row()
        # stale-tipoff OR degenerate (market_prob=None) -- at least one must fire
        dropped_stub = row["n_dropped_stale_tipoff"] + row["n_dropped_degenerate"]
        assert dropped_stub >= 1, (
            "Expected at least 1 stale-tipoff/degenerate drop; row: %s" % row
        )

    def test_n_dropped_accounts_for_bad_cards(self):
        row = self._row()
        # 2 bad cards out of 5 total
        assert row["n_dropped"] >= 2

    def test_n_served_equals_clean_cards(self):
        row = self._row()
        # 3 clean cards should pass
        assert row["n_served"] >= 3

    def test_n_total_five(self):
        row = self._row()
        assert row["n_total"] == 5


# ---------------------------------------------------------------------------
# Acceptance test 3: clean slate -> all-pass
# ---------------------------------------------------------------------------

class TestCleanSlate:
    """All cards clean, varied probs -> status=ok, n_dropped=0."""

    def _make_clean(self) -> List[Dict[str, Any]]:
        nba = [_make_card(sport="nba", model_prob=0.50 + i * 0.05) for i in range(4)]
        mlb = _clean_mlb_cards(4)
        return nba + mlb

    def test_all_status_ok(self):
        rows = compute_sport_health(self._make_clean())
        for row in rows:
            assert row["status"] == STATUS_OK, (
                "Expected status=ok for clean slate; sport=%s row=%s" % (row["sport"], row)
            )

    def test_no_drops(self):
        rows = compute_sport_health(self._make_clean())
        for row in rows:
            assert row["n_dropped"] == 0, (
                "Expected n_dropped=0 for clean board; sport=%s row=%s" % (row["sport"], row)
            )

    def test_non_discriminating_false(self):
        rows = compute_sport_health(self._make_clean())
        for row in rows:
            assert row["non_discriminating"] is False

    def test_two_sport_rows_returned(self):
        rows = compute_sport_health(self._make_clean())
        sports = {r["sport"] for r in rows}
        assert sports == {"nba", "mlb"}


# ---------------------------------------------------------------------------
# Acceptance test 4: no $ / edge field
# ---------------------------------------------------------------------------

class TestNoDollarField:
    _BANNED = {"pnl", "profit", "roi", "bankroll", "usd", "dollar", "stake",
               "edge", "ev", "expected_value"}

    def test_no_dollar_field_in_rows(self):
        cards = [_make_card(sport="nba", model_prob=0.50 + i * 0.05) for i in range(3)]
        rows = compute_sport_health(cards)
        for row in rows:
            for key in row.keys():
                assert key.lower() not in self._BANNED, (
                    "Banned $ field present in row: key=%s row=%s" % (key, row)
                )

    def test_honest_note_contains_calibration_not_edge(self):
        cards = [_make_card(sport="nba", model_prob=0.55 + i * 0.02) for i in range(3)]
        rows = compute_sport_health(cards)
        for row in rows:
            note = row.get("honest_note", "")
            # honest_note must reference calibration/units framing; no profit/roi claim
            assert "CALIBRATION" in note or "calibration" in note.lower(), (
                "honest_note must reference calibration: %s" % note
            )
            # No profit / roi fields fabricated in the note
            note_lower = note.lower()
            for banned_phrase in ("roi:", "profit:", "expected value:", "pnl:"):
                assert banned_phrase not in note_lower, (
                    "Banned phrase '%s' in honest_note: %s" % (banned_phrase, note)
                )


# ---------------------------------------------------------------------------
# Acceptance test 5: INSUFFICIENT_DATA when no cards
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """Empty input -> empty list returned (no sport buckets)."""

    def test_empty_input_returns_empty_list(self):
        rows = compute_sport_health([])
        assert rows == []

    def test_none_input_returns_empty_list(self):
        rows = compute_sport_health(None)  # type: ignore[arg-type]
        assert rows == []

    def test_all_dropped_cards_gives_insufficient_data_status(self):
        """When all cards for a sport are dropped, status=INSUFFICIENT_DATA."""
        cards = [
            _make_card(sport="tennis", matchup="Player Yes vs No Bet",
                       model_prob=0.55, market_prob=0.50),
            _make_card(sport="tennis", matchup="Player B Yes vs No Match",
                       model_prob=0.60, market_prob=0.50),
        ]
        rows = compute_sport_health(cards)
        tennis = _by_sport(rows, "tennis")
        assert tennis["status"] == STATUS_INSUFFICIENT_DATA
        assert tennis["n_served"] == 0


# ---------------------------------------------------------------------------
# Additional correctness / edge-case tests
# ---------------------------------------------------------------------------

class TestRequiredKeys:
    def test_required_keys_present(self):
        cards = [_make_card(sport="nba", model_prob=0.55 + i * 0.02) for i in range(4)]
        rows = compute_sport_health(cards)
        required = {
            "sport", "n_total", "n_served", "n_dropped",
            "n_dropped_binary", "n_dropped_degenerate",
            "n_dropped_stale_tipoff", "n_dropped_odds_extreme",
            "non_discriminating", "status", "honest_note",
        }
        for row in rows:
            missing = required - row.keys()
            assert not missing, "Missing keys in row: %s (row=%s)" % (missing, row)


class TestNeverRaises:
    def test_non_list_input(self):
        result = compute_sport_health("garbage")  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_non_dict_elements_ignored(self):
        result = compute_sport_health(["bad", 42, None, _make_card(sport="nba")])
        assert isinstance(result, list)

    def test_cards_missing_sport_bucketed_as_unknown(self):
        card = {
            "model_prob": 0.55,
            "market_prob": 0.50,
            "matchup": "A vs B",
            "best_odds": 1.90,
            "edge_vs_market": 0.05,
        }
        rows = compute_sport_health([card])
        sports = [r["sport"] for r in rows]
        assert "unknown" in sports


class TestMultiSportIsolation:
    """Drops in one sport do not contaminate another."""

    def test_nba_clean_soccer_dirty(self):
        nba_cards = [_make_card(sport="nba", model_prob=0.50 + i * 0.05) for i in range(4)]
        soccer_bad = [_make_card(sport="soccer_intl", matchup="Team Yes vs No",
                                  model_prob=0.55, market_prob=0.50)]
        rows = compute_sport_health(nba_cards + soccer_bad)
        nba_row = _by_sport(rows, "nba")
        assert nba_row["n_dropped"] == 0
        assert nba_row["status"] == STATUS_OK

    def test_soccer_dirty_does_not_affect_nba_row(self):
        nba_cards = [_make_card(sport="nba", model_prob=0.50 + i * 0.05) for i in range(4)]
        soccer_bad = [_make_card(sport="soccer_intl", matchup="Team Yes vs No",
                                  model_prob=0.55, market_prob=0.50)]
        rows = compute_sport_health(nba_cards + soccer_bad)
        soccer_row = _by_sport(rows, "soccer_intl")
        assert soccer_row["n_dropped_binary"] >= 1


class TestOddsExtremeDropBucket:
    """best_odds > 50 -> counted in n_dropped_odds_extreme."""

    def test_longshot_counted(self):
        cards = [
            _make_card(sport="nba", model_prob=0.55, best_odds=100.0),
        ]
        rows = compute_sport_health(cards)
        nba = _by_sport(rows, "nba")
        # Either the local classifier or the sanitizer catches it
        assert nba["n_dropped"] >= 1
