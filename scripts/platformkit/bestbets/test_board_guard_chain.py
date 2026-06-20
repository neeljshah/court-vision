"""Per-file test for scripts.platformkit.bestbets.board_guard_chain (BE-R5-1).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/bestbets/test_board_guard_chain.py -q

Acceptance criteria:
  - Yes-vs-No card (Polymarket binary) -> dropped
  - past-tipoff card -> dropped
  - market_prob < 0.02 -> dropped
  - clean sports cards (NBA, soccer_intl, MLB) -> pass through unchanged (matchup/sport)
  - chain is pure: input list not mutated; input card dicts not mutated
  - never raises on garbage input
  - empty input -> empty output (stale-never-green)
  - no $ / roi / pnl key in output

RAILS: ASCII only; per-file only; no full pytest suite.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from scripts.platformkit.bestbets.board_guard_chain import (
    CHAIN_STEPS,
    apply_guard_chain,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = (_NOW + timedelta(hours=4)).isoformat()
_PAST = (_NOW - timedelta(hours=2)).isoformat()

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
})


def _no_forbidden(obj: Any) -> bool:
    """Return True when obj contains no forbidden $ keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                return False
            if not _no_forbidden(v):
                return False
    elif isinstance(obj, (list, tuple)):
        return all(_no_forbidden(item) for item in obj)
    return True


def _card(**overrides) -> Dict[str, Any]:
    """Build a minimal valid BestBetCard that passes all guards."""
    base: Dict[str, Any] = {
        "game_id": "nba_001",
        "matchup": "Celtics vs Lakers",
        "sport": "nba",
        "market_type": "moneyline",
        "prop_player": None,
        "prop_stat": None,
        "side": "home",
        "model_prob": 0.58,
        "market_prob": 0.50,
        "best_book": "draftkings",
        "best_odds": 1.95,
        "all_books": [],
        "edge_vs_market": 0.08,
        "units": 1.0,
        "tier": "A",
        "confidence": 0.58,
        "clv": {"clv_status": "INSUFFICIENT_DATA"},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "Calibrated decision-support only.",
        "tipoff_utc": _FUTURE,
    }
    base.update(overrides)
    return base


def _chain(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Invoke apply_guard_chain with the fixed reference time."""
    return apply_guard_chain(cards, now=_NOW)


# ---------------------------------------------------------------------------
# 1. Polymarket 'Yes vs No' binary card -> dropped
# ---------------------------------------------------------------------------

class TestYesVsNoDropped:

    def test_yes_vs_no_exact_case_dropped(self):
        """matchup='Yes vs No' -> dropped by Step 1 (board_sanitizer)."""
        card = _card(matchup="Yes vs No", sport="soccer_intl")
        assert _chain([card]) == []

    def test_yes_vs_no_lowercase_dropped(self):
        """matchup='yes vs no' (all lower) -> dropped."""
        card = _card(matchup="yes vs no", sport="soccer_intl")
        assert _chain([card]) == []

    def test_yes_vs_no_embedded_dropped(self):
        """matchup with 'yes vs no' embedded -> dropped."""
        card = _card(matchup="Market event: Yes vs No", sport="soccer_intl")
        assert _chain([card]) == []

    def test_yes_vs_no_uppercase_dropped(self):
        """matchup='YES VS NO' -> dropped."""
        card = _card(matchup="YES VS NO", sport="soccer_intl")
        assert _chain([card]) == []

    def test_real_matchup_not_dropped(self):
        """Real soccer matchup 'France vs Spain' -> NOT dropped."""
        card = _card(matchup="France vs Spain", sport="soccer_intl")
        result = _chain([card])
        assert len(result) == 1
        assert result[0]["matchup"] == "France vs Spain"

    def test_mixed_batch_only_binary_dropped(self):
        """Mixed batch: only the 'Yes vs No' card is removed."""
        cards = [
            _card(game_id="a", matchup="Yes vs No", sport="soccer_intl"),
            _card(game_id="b", matchup="France vs Spain", sport="soccer_intl"),
            _card(game_id="c", matchup="Celtics vs Lakers", sport="nba"),
        ]
        result = _chain(cards)
        assert len(result) == 2
        ids = {c["game_id"] for c in result}
        assert ids == {"b", "c"}


# ---------------------------------------------------------------------------
# 2. Past-tipoff card -> dropped (stale-never-green)
# ---------------------------------------------------------------------------

class TestPastTipoffDropped:

    def test_past_tipoff_utc_dropped(self):
        """tipoff_utc 2 hours ago -> dropped."""
        card = _card(tipoff_utc=_PAST)
        assert _chain([card]) == []

    def test_future_tipoff_utc_kept(self):
        """tipoff_utc 4 hours from now -> kept."""
        card = _card(tipoff_utc=_FUTURE)
        result = _chain([card])
        assert len(result) == 1

    def test_no_tipoff_field_not_dropped(self):
        """Missing tipoff_utc key -> NOT dropped on this criterion alone."""
        card = _card()
        del card["tipoff_utc"]
        result = _chain([card])
        assert len(result) == 1

    def test_none_tipoff_not_dropped(self):
        """tipoff_utc=None -> NOT dropped on this criterion alone."""
        card = _card(tipoff_utc=None)
        result = _chain([card])
        assert len(result) == 1

    def test_tipoff_exactly_at_now_dropped(self):
        """tipoff_utc == now (not strictly future) -> dropped."""
        at_now = _NOW.isoformat()
        assert _chain([_card(tipoff_utc=at_now)]) == []

    def test_tipoff_z_suffix_past_dropped(self):
        """ISO-8601 Z suffix, past -> dropped."""
        past_z = (_NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _chain([_card(tipoff_utc=past_z)]) == []

    def test_tipoff_datetime_object_past_dropped(self):
        """datetime object in the past -> dropped."""
        past_dt = _NOW - timedelta(minutes=30)
        assert _chain([_card(tipoff_utc=past_dt)]) == []

    def test_tipoff_datetime_object_future_kept(self):
        """datetime object in the future -> kept."""
        future_dt = _NOW + timedelta(hours=3)
        result = _chain([_card(tipoff_utc=future_dt)])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 3. market_prob < 0.02 -> dropped
# ---------------------------------------------------------------------------

class TestMarketProbDropped:

    def test_zero_market_prob_dropped(self):
        """market_prob=0.0 -> dropped."""
        assert _chain([_card(market_prob=0.0)]) == []

    def test_below_min_dropped(self):
        """market_prob=0.019 (just below floor) -> dropped."""
        assert _chain([_card(market_prob=0.019)]) == []

    def test_none_market_prob_dropped(self):
        """market_prob=None -> dropped (unparseable = degenerate)."""
        assert _chain([_card(market_prob=None)]) == []

    def test_exactly_at_floor_kept(self):
        """market_prob=0.02 (boundary, inclusive) -> kept."""
        result = _chain([_card(market_prob=0.02)])
        assert len(result) == 1

    def test_normal_market_prob_kept(self):
        """market_prob=0.50 -> kept."""
        result = _chain([_card(market_prob=0.50)])
        assert len(result) == 1

    def test_dead_market_prob_dropped(self):
        """market_prob=0.0005 (resolved binary / dead market) -> dropped."""
        assert _chain([_card(market_prob=0.0005)]) == []


# ---------------------------------------------------------------------------
# 4. Clean sports cards pass through unchanged
# ---------------------------------------------------------------------------

class TestCleanCardsPassThrough:

    def test_nba_card_passes(self):
        """Valid NBA card -> passes through; sport and matchup preserved."""
        card = _card(sport="nba", matchup="Celtics vs Lakers", model_prob=0.60)
        result = _chain([card])
        assert len(result) == 1
        assert result[0]["sport"] == "nba"
        assert result[0]["matchup"] == "Celtics vs Lakers"

    def test_soccer_card_passes(self):
        """Valid soccer_intl card -> passes through."""
        card = _card(sport="soccer_intl", matchup="Brazil vs Argentina", model_prob=0.55)
        result = _chain([card])
        assert len(result) == 1
        assert result[0]["sport"] == "soccer_intl"

    def test_mlb_card_passes(self):
        """Valid MLB card -> passes through."""
        card = _card(sport="mlb", matchup="Yankees vs Red Sox", model_prob=0.54)
        result = _chain([card])
        assert len(result) == 1
        assert result[0]["sport"] == "mlb"

    def test_multi_sport_all_pass(self):
        """Three valid cards from three different sports all pass."""
        cards = [
            _card(game_id="n1", sport="nba", matchup="Heat vs Bucks"),
            _card(game_id="s1", sport="soccer_intl", matchup="France vs Spain"),
            _card(game_id="m1", sport="mlb", matchup="Cubs vs Cardinals"),
        ]
        result = _chain(cards)
        assert len(result) == 3
        sports = {c["sport"] for c in result}
        assert sports == {"nba", "soccer_intl", "mlb"}


# ---------------------------------------------------------------------------
# 5. Chain is pure: no mutation of input list or card dicts
# ---------------------------------------------------------------------------

class TestChainIsPure:

    def test_input_list_not_mutated(self):
        """apply_guard_chain must not mutate the input list."""
        cards = [
            _card(game_id="a"),
            _card(game_id="b", matchup="Yes vs No"),
        ]
        original_len = len(cards)
        _chain(cards)
        assert len(cards) == original_len

    def test_input_card_dicts_not_mutated(self):
        """apply_guard_chain must not mutate any input card dict."""
        card = _card(game_id="x", model_prob=0.55)
        original = copy.deepcopy(card)
        _chain([card])
        assert card == original

    def test_returned_list_is_new(self):
        """Returned list is a new object, not the same as input."""
        cards = [_card()]
        result = _chain(cards)
        assert result is not cards

    def test_returned_card_dicts_are_copies(self):
        """Returned card dicts are new copies (not the same objects as input)."""
        card = _card()
        result = _chain([card])
        assert len(result) == 1
        assert result[0] is not card

    def test_degenerate_guard_does_not_mutate_input(self):
        """Degenerate-guard demotion must not mutate input card dict."""
        # 4 cards with same sport and identical model_prob -> triggers demotion.
        cards = [
            _card(game_id=f"g{i}", sport="mlb", model_prob=0.5345, matchup=f"Team{i} vs Opp{i}")
            for i in range(4)
        ]
        originals = [copy.deepcopy(c) for c in cards]
        _chain(cards)
        for orig, card in zip(originals, cards):
            assert card == orig, "Input card was mutated by degenerate guard"


# ---------------------------------------------------------------------------
# 6. Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_empty_input_no_raise(self):
        """Empty list -> no raise."""
        result = apply_guard_chain([], now=_NOW)
        assert result == []

    def test_none_input_no_raise(self):
        """None as cards -> no raise."""
        result = apply_guard_chain(None, now=_NOW)  # type: ignore[arg-type]
        assert result == []

    def test_non_list_input_no_raise(self):
        """String input -> no raise."""
        result = apply_guard_chain("not a list", now=_NOW)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_list_with_none_entries_no_raise(self):
        """List containing None entries -> no raise; non-dict entries silently dropped."""
        result = apply_guard_chain([None, None, _card()], now=_NOW)
        assert isinstance(result, list)

    def test_list_with_garbage_entries_no_raise(self):
        """List with mixed garbage -> no raise."""
        result = apply_guard_chain([42, "bad", True, _card()], now=_NOW)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_card_with_all_none_values_no_raise(self):
        """Card where all values are None -> no raise."""
        card: Dict[str, Any] = {
            k: None for k in ["matchup", "market_prob", "best_odds", "edge_vs_market", "tipoff_utc"]
        }
        apply_guard_chain([card], now=_NOW)

    def test_card_missing_all_keys_no_raise(self):
        """Completely empty card dict -> no raise."""
        apply_guard_chain([{}], now=_NOW)

    def test_large_mixed_batch_no_raise(self):
        """Large mixed batch with garbage -> no raise."""
        cards = (
            [_card(game_id=f"ok{i}") for i in range(30)]
            + [_card(matchup="Yes vs No") for _ in range(10)]
            + [_card(tipoff_utc=_PAST) for _ in range(10)]
            + [None, "garbage", 42]  # type: ignore[list-item]
        )
        result = apply_guard_chain(cards, now=_NOW)
        assert len(result) == 30


# ---------------------------------------------------------------------------
# 7. Empty input -> empty output (stale-never-green)
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_list_returns_empty(self):
        """Empty input -> [] (stale-never-green: no fabricated cards)."""
        result = _chain([])
        assert result == []
        assert isinstance(result, list)

    def test_all_dropped_returns_empty(self):
        """All cards dropped -> [] not error."""
        cards = [
            _card(matchup="Yes vs No"),
            _card(market_prob=0.001),
            _card(tipoff_utc=_PAST),
        ]
        assert _chain(cards) == []


# ---------------------------------------------------------------------------
# 8. No $ / roi / pnl key in output
# ---------------------------------------------------------------------------

class TestNoForbiddenKeys:

    def test_single_valid_card_no_forbidden_keys(self):
        """Single valid card output: no forbidden $ keys."""
        result = _chain([_card()])
        assert _no_forbidden(result)

    def test_mixed_batch_no_forbidden_keys(self):
        """Mixed batch output: no forbidden $ keys."""
        cards = [
            _card(matchup="Yes vs No"),             # dropped
            _card(matchup="Brazil vs Argentina"),    # kept
            _card(market_prob=0.001),               # dropped
            _card(matchup="Celtics vs Lakers"),      # kept
        ]
        result = _chain(cards)
        assert _no_forbidden(result)

    def test_empty_output_no_forbidden_keys(self):
        """All-dropped batch: empty output, still no forbidden keys."""
        result = _chain([_card(matchup="Yes vs No")])
        assert result == []
        assert _no_forbidden(result)


# ---------------------------------------------------------------------------
# 9. CHAIN_STEPS metadata
# ---------------------------------------------------------------------------

class TestChainMetadata:

    def test_chain_steps_is_tuple(self):
        """CHAIN_STEPS is a tuple."""
        assert isinstance(CHAIN_STEPS, tuple)

    def test_chain_steps_length(self):
        """CHAIN_STEPS has exactly 3 entries (one per guard step)."""
        assert len(CHAIN_STEPS) == 3

    def test_chain_steps_include_sanitizer(self):
        """CHAIN_STEPS references board_sanitizer.sanitize."""
        assert any("board_sanitizer" in s for s in CHAIN_STEPS)

    def test_chain_steps_include_degenerate_guard(self):
        """CHAIN_STEPS references degenerate_guard."""
        assert any("degenerate_guard" in s for s in CHAIN_STEPS)

    def test_chain_steps_include_uniformity(self):
        """CHAIN_STEPS references uniformity_enforce."""
        assert any("uniformity_enforce" in s for s in CHAIN_STEPS)


# ---------------------------------------------------------------------------
# 10. Integration: full-board scenario
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_polymarket_board_scenario(self):
        """Realistic board with a Polymarket Yes/No leak + stale event + clean cards.

        Verifies the full P1 QA fix end-to-end:
          * Polymarket 'Yes vs No' -> dropped
          * Stale past-tipoff soccer_intl card -> dropped
          * Two clean NBA/soccer cards -> pass through
        """
        cards = [
            # Polymarket Yes/No binary -- THE P1 QA BUG
            _card(
                game_id="pm_binary",
                matchup="Yes vs No",
                sport="soccer_intl",
                market_prob=0.0005,   # dead market
                best_odds=2000.0,
                tipoff_utc=_PAST,
            ),
            # Stale event (tipoff already happened)
            _card(
                game_id="stale_soccer",
                matchup="France vs Spain",
                sport="soccer_intl",
                market_prob=0.48,
                best_odds=2.1,
                tipoff_utc=_PAST,
            ),
            # Clean NBA card -> should survive
            _card(
                game_id="clean_nba",
                matchup="Celtics vs Lakers",
                sport="nba",
                model_prob=0.60,
                market_prob=0.50,
            ),
            # Clean soccer card -> should survive
            _card(
                game_id="clean_soccer",
                matchup="Brazil vs Argentina",
                sport="soccer_intl",
                model_prob=0.55,
                market_prob=0.48,
            ),
        ]
        result = _chain(cards)
        surviving_ids = {c["game_id"] for c in result}
        assert "pm_binary" not in surviving_ids, "Polymarket Yes/No must be dropped"
        assert "stale_soccer" not in surviving_ids, "Past-tipoff card must be dropped"
        assert "clean_nba" in surviving_ids, "Clean NBA card must survive"
        assert "clean_soccer" in surviving_ids, "Clean soccer card must survive"
        assert len(result) == 2

    def test_order_preserved(self):
        """Surviving cards appear in original input order."""
        cards = [
            _card(game_id="a", matchup="Celtics vs Lakers"),
            _card(game_id="b", matchup="Yes vs No"),   # dropped
            _card(game_id="c", matchup="France vs Spain", sport="soccer_intl"),
            _card(game_id="d", tipoff_utc=_PAST),      # dropped
            _card(game_id="e", matchup="Cubs vs Cardinals", sport="mlb"),
        ]
        result = _chain(cards)
        ids = [c["game_id"] for c in result]
        assert ids == ["a", "c", "e"]

    def test_now_injectable_controls_tipoff(self):
        """Injecting different 'now' changes the tipoff verdict."""
        tipoff_str = "2026-06-20T14:00:00+00:00"
        card = _card(tipoff_utc=tipoff_str)

        # Before tipoff -> card survives
        before = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
        result_before = apply_guard_chain([card], now=before)
        assert len(result_before) == 1

        # After tipoff -> card dropped
        after = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
        result_after = apply_guard_chain([card], now=after)
        assert result_after == []
