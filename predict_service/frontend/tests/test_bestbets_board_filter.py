"""Per-file tests for predict_service.frontend.bestbets_board_filter (QAFIX-2-1 / QAFIX-8).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_bestbets_board_filter.py -q

Acceptance criteria (QAFIX-2-1):
  - matchup containing 'Yes vs No' -> excluded
  - market_prob < 0.02             -> excluded
  - best_odds > 50.0               -> excluded
  - tipoff_utc in the past         -> excluded
  - valid soccer_intl entry (prob>=0.02, odds<=50, real matchup, future tipoff) -> kept
  - empty input                    -> [] not error
  - no $/roi key in output         -> verified recursively
  - never raises                   -> every path tested with garbage input

QAFIX-8 new acceptance criteria (iter 8 edge cases):
  - Yes/No card with tipoff 2025-07-02 (>1yr past) -> dropped
  - Card with no tipoff_utc but past commence_time  -> dropped
  - Card with market_prob=0.0005 / best_odds=2000   -> dropped (both independently)
  - Fresh future-tipoff sport card (NBA/MLB)        -> kept
  - Naive ISO-8601 tipoff string (no tz) treated as UTC -> past naive -> dropped
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from predict_service.frontend.bestbets_board_filter import (
    MAX_BEST_ODDS,
    MIN_MARKET_PROB,
    DEAD_MARKET_PROB,
    filter_cards,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
})

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = (_NOW + timedelta(hours=3)).isoformat()
_PAST = (_NOW - timedelta(hours=1)).isoformat()


def _has_forbidden_key(obj: Any) -> bool:
    """Recursively scan obj for any key matching FORBIDDEN_KEYS (case-insensitive)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                return True
            if _has_forbidden_key(v):
                return True
    elif isinstance(obj, (list, tuple)):
        return any(_has_forbidden_key(item) for item in obj)
    return False


def _valid_card(**overrides) -> Dict[str, Any]:
    """Build a minimal valid soccer_intl BestBetCard that passes all filters."""
    base: Dict[str, Any] = {
        "game_id": "sc_001",
        "matchup": "Brazil vs Argentina",
        "sport": "soccer_intl",
        "market_type": "moneyline",
        "prop_player": None,
        "prop_stat": None,
        "side": "home",
        "model_prob": 0.55,
        "market_prob": 0.48,
        "best_book": "draftkings",
        "best_odds": 2.1,
        "all_books": [],
        "edge_vs_market": 0.07,
        "units": 1.0,
        "tier": "A",
        "confidence": 0.55,
        "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "Calibrated decision-support only.",
        "tipoff_utc": _FUTURE,
    }
    base.update(overrides)
    return base


def _filter(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Call filter_cards with the fixed reference time."""
    return filter_cards(cards, now=_NOW)


# ---------------------------------------------------------------------------
# 1. Non-sports binary matchup: 'Yes vs No'
# ---------------------------------------------------------------------------

class TestNonSportsBinary:

    def test_yes_vs_no_exact_case_excluded(self):
        """Matchup 'Yes vs No' -> excluded."""
        card = _valid_card(matchup="Yes vs No")
        assert _filter([card]) == []

    def test_yes_vs_no_lowercase_excluded(self):
        """Matchup 'yes vs no' (all lowercase) -> excluded."""
        card = _valid_card(matchup="yes vs no")
        assert _filter([card]) == []

    def test_yes_vs_no_uppercase_excluded(self):
        """Matchup 'YES VS NO' (all caps) -> excluded."""
        card = _valid_card(matchup="YES VS NO")
        assert _filter([card]) == []

    def test_yes_vs_no_embedded_excluded(self):
        """Matchup with 'yes vs no' embedded in a longer string -> excluded."""
        card = _valid_card(matchup="Will X happen: Yes vs No")
        assert _filter([card]) == []

    def test_real_soccer_matchup_kept(self):
        """Real soccer matchup 'Brazil vs Argentina' -> kept."""
        card = _valid_card(matchup="Brazil vs Argentina")
        result = _filter([card])
        assert len(result) == 1
        assert result[0]["matchup"] == "Brazil vs Argentina"

    def test_nba_real_matchup_not_dropped(self):
        """NBA matchup 'Celtics vs Lakers' -> not dropped by binary check."""
        card = _valid_card(matchup="Celtics vs Lakers", sport="nba")
        result = _filter([card])
        assert len(result) == 1

    def test_mixed_batch_excludes_only_binary(self):
        """Mixed list: only the 'Yes vs No' card is removed."""
        cards = [
            _valid_card(matchup="Yes vs No"),
            _valid_card(matchup="France vs Spain"),
            _valid_card(matchup="Germany vs Italy"),
        ]
        result = _filter(cards)
        assert len(result) == 2
        for c in result:
            assert "yes vs no" not in c["matchup"].lower()


# ---------------------------------------------------------------------------
# 2. market_prob < 0.02 (degenerate market)
# ---------------------------------------------------------------------------

class TestMarketProbFilter:

    def test_zero_market_prob_excluded(self):
        """market_prob=0.0 -> excluded."""
        assert _filter([_valid_card(market_prob=0.0)]) == []

    def test_below_min_excluded(self):
        """market_prob=0.019 (just below 0.02) -> excluded."""
        assert _filter([_valid_card(market_prob=0.019)]) == []

    def test_exactly_at_min_kept(self):
        """market_prob=0.02 (boundary, inclusive) -> kept."""
        result = _filter([_valid_card(market_prob=0.02)])
        assert len(result) == 1

    def test_above_min_kept(self):
        """market_prob=0.5 -> kept."""
        result = _filter([_valid_card(market_prob=0.5)])
        assert len(result) == 1

    def test_none_market_prob_excluded(self):
        """market_prob=None (unparseable) -> excluded."""
        assert _filter([_valid_card(market_prob=None)]) == []

    def test_string_market_prob_excluded(self):
        """market_prob='bad_value' -> excluded (unparseable)."""
        assert _filter([_valid_card(market_prob="bad_value")]) == []

    def test_nan_market_prob_excluded(self):
        """market_prob=nan -> excluded."""
        assert _filter([_valid_card(market_prob=float("nan"))]) == []

    def test_inf_market_prob_excluded(self):
        """market_prob=inf -> excluded."""
        assert _filter([_valid_card(market_prob=float("inf"))]) == []


# ---------------------------------------------------------------------------
# 3. best_odds > 50.0 (extreme longshot)
# ---------------------------------------------------------------------------

class TestBestOddsFilter:

    def test_absurd_odds_666_excluded(self):
        """best_odds=666.67 (Polymarket artifact) -> excluded."""
        assert _filter([_valid_card(best_odds=666.67)]) == []

    def test_absurd_odds_2000_excluded(self):
        """best_odds=2000 -> excluded."""
        assert _filter([_valid_card(best_odds=2000.0)]) == []

    def test_just_above_ceiling_excluded(self):
        """best_odds=50.01 -> excluded."""
        assert _filter([_valid_card(best_odds=50.01)]) == []

    def test_exactly_at_ceiling_kept(self):
        """best_odds=50.0 (boundary) -> kept."""
        result = _filter([_valid_card(best_odds=50.0)])
        assert len(result) == 1

    def test_normal_odds_kept(self):
        """best_odds=2.1 -> kept."""
        result = _filter([_valid_card(best_odds=2.1)])
        assert len(result) == 1

    def test_none_best_odds_not_dropped_alone(self):
        """best_odds=None -> not dropped on this criterion alone (odds absent is ok)."""
        card = _valid_card(best_odds=None)
        result = _filter([card])
        assert len(result) == 1

    def test_inf_odds_excluded(self):
        """best_odds=inf -> excluded."""
        assert _filter([_valid_card(best_odds=float("inf"))]) == []


# ---------------------------------------------------------------------------
# 4. tipoff_utc in the past -> excluded (stale-never-green)
# ---------------------------------------------------------------------------

class TestTipoffInPast:

    def test_past_tipoff_excluded(self):
        """tipoff_utc 1 hour ago -> excluded."""
        assert _filter([_valid_card(tipoff_utc=_PAST)]) == []

    def test_future_tipoff_kept(self):
        """tipoff_utc 3 hours from now -> kept."""
        result = _filter([_valid_card(tipoff_utc=_FUTURE)])
        assert len(result) == 1

    def test_no_tipoff_field_not_dropped(self):
        """No tipoff_utc key present -> not dropped on this criterion alone."""
        card = _valid_card()
        del card["tipoff_utc"]
        result = _filter([card])
        assert len(result) == 1

    def test_none_tipoff_not_dropped(self):
        """tipoff_utc=None -> not dropped on this criterion alone."""
        result = _filter([_valid_card(tipoff_utc=None)])
        assert len(result) == 1

    def test_tipoff_exactly_at_now_excluded(self):
        """tipoff_utc == now (not strictly future) -> excluded."""
        at_now = _NOW.isoformat()
        assert _filter([_valid_card(tipoff_utc=at_now)]) == []

    def test_tipoff_z_suffix_parsed(self):
        """ISO-8601 with Z suffix is parsed correctly (past -> excluded)."""
        past_z = (_NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _filter([_valid_card(tipoff_utc=past_z)]) == []

    def test_tipoff_z_suffix_future_kept(self):
        """ISO-8601 with Z suffix, future -> kept."""
        future_z = (_NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _filter([_valid_card(tipoff_utc=future_z)])
        assert len(result) == 1

    def test_unparseable_tipoff_not_dropped(self):
        """Unparseable tipoff_utc string -> not dropped (safe default)."""
        result = _filter([_valid_card(tipoff_utc="not_a_date")])
        assert len(result) == 1

    def test_datetime_object_past_excluded(self):
        """tipoff_utc as datetime object in the past -> excluded."""
        past_dt = _NOW - timedelta(minutes=30)
        assert _filter([_valid_card(tipoff_utc=past_dt)]) == []

    def test_datetime_object_future_kept(self):
        """tipoff_utc as datetime object in the future -> kept."""
        future_dt = _NOW + timedelta(hours=2)
        result = _filter([_valid_card(tipoff_utc=future_dt)])
        assert len(result) == 1

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime is assumed UTC; past naive datetime -> excluded."""
        naive_past = (_NOW - timedelta(hours=1)).replace(tzinfo=None)
        assert _filter([_valid_card(tipoff_utc=naive_past)]) == []


# ---------------------------------------------------------------------------
# 5. Valid soccer_intl entry kept end-to-end
# ---------------------------------------------------------------------------

class TestValidSoccerIntlKept:

    def test_valid_card_kept(self):
        """Valid soccer_intl card with all criteria satisfied -> kept."""
        card = _valid_card()
        result = _filter([card])
        assert len(result) == 1
        assert result[0]["sport"] == "soccer_intl"
        assert result[0]["tier"] == "A"

    def test_valid_card_not_mutated(self):
        """filter_cards must not mutate the input card."""
        card = _valid_card()
        original = copy.deepcopy(card)
        _filter([card])
        assert card == original

    def test_valid_card_not_mutated_input_list(self):
        """filter_cards must not mutate the input list."""
        cards = [_valid_card(), _valid_card(matchup="France vs Spain")]
        original_len = len(cards)
        _filter(cards)
        assert len(cards) == original_len

    def test_multiple_valid_cards_all_kept(self):
        """Multiple valid soccer_intl cards -> all kept."""
        cards = [
            _valid_card(game_id="sc_001", matchup="Brazil vs Argentina"),
            _valid_card(game_id="sc_002", matchup="France vs Spain"),
            _valid_card(game_id="sc_003", matchup="Germany vs Italy"),
        ]
        result = _filter(cards)
        assert len(result) == 3

    def test_no_forbidden_keys_in_output(self):
        """Output cards contain no $/roi/pnl/profit keys."""
        cards = [_valid_card()]
        result = _filter(cards)
        assert not _has_forbidden_key(result)


# ---------------------------------------------------------------------------
# 6. Empty input -> [] not error
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_list_returns_empty(self):
        """Empty input list -> [] (not an error)."""
        result = _filter([])
        assert result == []
        assert isinstance(result, list)

    def test_empty_list_no_exception(self):
        """filter_cards([]) must not raise."""
        filter_cards([], now=_NOW)

    def test_none_input_returns_empty(self):
        """None input -> [] (not an error, never raises)."""
        result = filter_cards(None, now=_NOW)  # type: ignore[arg-type]
        assert result == []

    def test_non_list_input_returns_empty(self):
        """Garbage non-list input -> [] (never raises)."""
        result = filter_cards("not_a_list", now=_NOW)  # type: ignore[arg-type]
        assert result == []


# ---------------------------------------------------------------------------
# 7. No $/roi key in any output
# ---------------------------------------------------------------------------

class TestNoForbiddenKeys:

    def test_no_forbidden_keys_single_valid(self):
        """Single valid card output: no forbidden $ keys."""
        result = _filter([_valid_card()])
        assert not _has_forbidden_key(result)

    def test_no_forbidden_keys_mixed_batch(self):
        """Mixed batch (some dropped, some kept): no forbidden $ keys in output."""
        cards = [
            _valid_card(matchup="Yes vs No"),         # dropped
            _valid_card(matchup="Brazil vs Argentina"), # kept
            _valid_card(market_prob=0.001),            # dropped
        ]
        result = _filter(cards)
        assert not _has_forbidden_key(result)

    def test_no_forbidden_keys_empty_output(self):
        """All-dropped batch: empty output has no forbidden keys."""
        cards = [
            _valid_card(matchup="Yes vs No"),
            _valid_card(best_odds=999.0),
        ]
        result = _filter(cards)
        assert result == []
        assert not _has_forbidden_key(result)


# ---------------------------------------------------------------------------
# 8. Never raises -- robustness
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_none_input_no_raise(self):
        """None as cards must not raise."""
        filter_cards(None, now=_NOW)  # type: ignore[arg-type]

    def test_dict_input_no_raise(self):
        """Dict instead of list must not raise."""
        filter_cards({"bad": "input"}, now=_NOW)  # type: ignore[arg-type]

    def test_list_with_none_entries_no_raise(self):
        """List containing None entries must not raise."""
        result = filter_cards([None, None], now=_NOW)
        assert isinstance(result, list)

    def test_list_with_non_dict_entries_no_raise(self):
        """List containing non-dict entries (strings, ints) must not raise."""
        result = filter_cards([42, "bad", True], now=_NOW)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_card_with_all_none_values_no_raise(self):
        """Card where all values are None must not raise."""
        card = {k: None for k in ["matchup", "market_prob", "best_odds",
                                   "edge_vs_market", "tipoff_utc"]}
        filter_cards([card], now=_NOW)

    def test_card_missing_all_keys_no_raise(self):
        """Completely empty card dict must not raise."""
        filter_cards([{}], now=_NOW)

    def test_card_with_garbage_types_no_raise(self):
        """Card with garbage non-string matchup type must not raise."""
        card = {
            "matchup": [1, 2, 3],     # not a string
            "market_prob": object(),   # not numeric
            "best_odds": {"nested": "dict"},
            "tipoff_utc": 12345,       # not a string/datetime
        }
        filter_cards([card], now=_NOW)

    def test_large_list_no_raise(self):
        """Large list of mixed valid/invalid cards must not raise."""
        cards = (
            [_valid_card(game_id=f"sc_{i}") for i in range(50)]
            + [_valid_card(matchup="Yes vs No") for _ in range(20)]
            + [_valid_card(market_prob=0.001) for _ in range(10)]
        )
        result = filter_cards(cards, now=_NOW)
        assert len(result) == 50


# ---------------------------------------------------------------------------
# 9. Boundary / integration
# ---------------------------------------------------------------------------

class TestBoundaryAndIntegration:

    def test_constants_exposed(self):
        """Module-level constants are accessible and match sanitizer values."""
        assert MIN_MARKET_PROB == pytest.approx(0.02, abs=1e-9)
        assert MAX_BEST_ODDS == pytest.approx(50.0, abs=1e-9)

    def test_multiple_drop_reasons_on_one_card(self):
        """Card failing multiple criteria is still excluded exactly once."""
        bad_card = _valid_card(
            matchup="Yes vs No",
            market_prob=0.001,
            best_odds=2000.0,
            tipoff_utc=_PAST,
        )
        result = _filter([bad_card])
        assert result == []

    def test_retained_order_matches_input_order(self):
        """Surviving cards appear in the same order as the input."""
        cards = [
            _valid_card(game_id="a", matchup="France vs Spain"),
            _valid_card(game_id="b", matchup="Yes vs No"),   # dropped
            _valid_card(game_id="c", matchup="Brazil vs Argentina"),
            _valid_card(game_id="d", market_prob=0.001),     # dropped
            _valid_card(game_id="e", matchup="Germany vs Italy"),
        ]
        result = _filter(cards)
        assert [c["game_id"] for c in result] == ["a", "c", "e"]

    def test_now_injectable_controls_tipoff_verdict(self):
        """Injecting a different 'now' changes which tipoff is past vs future."""
        tipoff_str = "2026-06-20T14:00:00+00:00"
        card = _valid_card(tipoff_utc=tipoff_str)

        # Before tipoff -> kept
        before = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert len(filter_cards([card], now=before)) == 1

        # After tipoff -> dropped
        after = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
        assert filter_cards([card], now=after) == []

    def test_dead_market_prob_constant_exposed(self):
        """DEAD_MARKET_PROB constant is accessible and below MIN_MARKET_PROB."""
        assert DEAD_MARKET_PROB == pytest.approx(0.001, abs=1e-9)
        assert DEAD_MARKET_PROB < MIN_MARKET_PROB


# ---------------------------------------------------------------------------
# 10. QAFIX-8 -- iter 8 edge cases that slipped through
# ---------------------------------------------------------------------------

class TestQAFIX8EdgeCases:
    """QAFIX-8: Hardening tests for edge cases identified in QA iter 8.

    Acceptance:
      - Yes/No card with tipoff 2025-07-02 (>1yr past) -> dropped
      - Card with no tipoff_utc but past commence_time  -> dropped
      - Card with market_prob=0.0005 / best_odds=2000   -> dropped (independently)
      - Fresh future-tipoff NBA/MLB card                -> kept
    """

    def test_yes_no_card_tipoff_one_year_past_dropped(self):
        """QA finding: Yes/No binary with tipoff 2025-07-02 must be dropped.

        The card represents a settled Polymarket binary contract that is over a year
        old. Both the matchup and the stale tipoff should trigger a drop.
        """
        card = _valid_card(
            matchup="Yes vs No",
            tipoff_utc="2025-07-02T00:00:00+00:00",
            market_prob=0.0005,
            best_odds=2000.0,
            edge_vs_market=0.34,
        )
        assert _filter([card]) == []

    def test_yes_no_card_tipoff_2025_dropped_by_matchup_alone(self):
        """Yes/No matchup alone is sufficient to drop even without checking tipoff."""
        card = _valid_card(
            matchup="Yes vs No",
            tipoff_utc="2025-07-02T00:00:00+00:00",
        )
        assert _filter([card]) == []

    def test_no_tipoff_utc_but_past_commence_time_dropped(self):
        """QA finding: card with no tipoff_utc but a past commence_time must be dropped.

        The original filter only checked tipoff_utc; a card with commence_time (used
        by Polymarket/OddsAPI events) slipped through as pregame.
        """
        card = _valid_card(
            matchup="Oklahoma City Thunder vs San Antonio Spurs",
            sport="nba",
            tipoff_utc=None,
        )
        del card["tipoff_utc"]
        # Inject a past commence_time (NBA Finals game completed hours ago)
        card["commence_time"] = (_NOW - timedelta(hours=6)).isoformat()
        assert _filter([card]) == []

    def test_no_tipoff_utc_future_commence_time_kept(self):
        """Card with no tipoff_utc but a future commence_time must be kept."""
        card = _valid_card(sport="nba", matchup="Lakers vs Warriors")
        del card["tipoff_utc"]
        card["commence_time"] = (_NOW + timedelta(hours=4)).isoformat()
        result = _filter([card])
        assert len(result) == 1

    def test_past_game_datetime_without_tipoff_utc_dropped(self):
        """Card with game_datetime in the past (and no tipoff_utc) must be dropped."""
        card = _valid_card(sport="mlb", matchup="Yankees vs Red Sox")
        del card["tipoff_utc"]
        card["game_datetime"] = (_NOW - timedelta(hours=3)).isoformat()
        assert _filter([card]) == []

    def test_market_prob_0005_dropped(self):
        """QA finding: market_prob=0.0005 (resolved Polymarket 'No' contract) -> dropped.

        DEAD_MARKET_PROB=0.001 catches this as a secondary dead-market signal even
        when the matchup is not 'yes vs no' (e.g. after a contract rename).
        """
        card = _valid_card(
            matchup="Brazil vs Argentina",
            market_prob=0.0005,
        )
        assert _filter([card]) == []

    def test_market_prob_0005_with_yes_no_still_dropped(self):
        """Polymarket binary with market_prob=0.0005 dropped by BOTH criteria."""
        card = _valid_card(matchup="Yes vs No", market_prob=0.0005)
        assert _filter([card]) == []

    def test_best_odds_2000_dropped(self):
        """QA finding: best_odds=2000 (Polymarket artifact) -> dropped by odds filter."""
        card = _valid_card(
            matchup="Brazil vs Argentina",
            best_odds=2000.0,
        )
        assert _filter([card]) == []

    def test_best_odds_200_dropped(self):
        """best_odds=200 (secondary staleness threshold) -> dropped."""
        card = _valid_card(matchup="France vs Spain", best_odds=200.0)
        assert _filter([card]) == []

    def test_fresh_nba_card_kept(self):
        """QA acceptance: fresh future-tipoff NBA card -> kept (not a false positive)."""
        card = _valid_card(
            sport="nba",
            matchup="Oklahoma City Thunder vs Indiana Pacers",
            market_prob=0.52,
            best_odds=1.95,
            tipoff_utc=(_NOW + timedelta(hours=2)).isoformat(),
        )
        result = _filter([card])
        assert len(result) == 1
        assert result[0]["sport"] == "nba"

    def test_fresh_mlb_card_kept(self):
        """QA acceptance: fresh future-tipoff MLB card -> kept (not a false positive)."""
        card = _valid_card(
            sport="mlb",
            matchup="Yankees vs Red Sox",
            market_prob=0.55,
            best_odds=1.85,
            tipoff_utc=(_NOW + timedelta(hours=5)).isoformat(),
        )
        result = _filter([card])
        assert len(result) == 1
        assert result[0]["sport"] == "mlb"

    def test_naive_iso_string_past_treated_as_utc_dropped(self):
        """Naive ISO-8601 tipoff_utc (no tz suffix) treated as UTC; past -> dropped."""
        # Naive string: no '+00:00' or 'Z' -- must be assumed UTC.
        naive_past = (_NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        card = _valid_card(
            sport="nba",
            matchup="Celtics vs Knicks",
            tipoff_utc=naive_past,
        )
        assert _filter([card]) == []

    def test_naive_iso_string_future_treated_as_utc_kept(self):
        """Naive ISO-8601 tipoff_utc in the future treated as UTC -> kept."""
        naive_future = (_NOW + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        card = _valid_card(
            sport="nba",
            matchup="Celtics vs Knicks",
            tipoff_utc=naive_future,
        )
        result = _filter([card])
        assert len(result) == 1

    def test_naive_commence_time_past_dropped(self):
        """Naive commence_time (no tz) that is past -> dropped via UTC assumption."""
        naive_past = (_NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        card = _valid_card(sport="mlb", matchup="Cubs vs Cardinals")
        del card["tipoff_utc"]
        card["commence_time"] = naive_past
        assert _filter([card]) == []
