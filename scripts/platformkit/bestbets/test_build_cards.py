"""Per-file test for scripts.platformkit.bestbets.build_cards.

Acceptance criteria
-------------------
A  build_cards(now=fixed) returns a list (not an exception, not None).
B  A stale Polymarket 'Yes vs No' card (matchup 'Yes vs No',
   market_prob 0.0005, tipoff a year past) is ABSENT from output.
C  A past-tipoff card is absent from output.
D  Every returned card has no $/pnl/roi field and carries
   edge_vs_market labelled as prob-diff (a float, NOT a $ string).
E  Empty upstream (all sports return []) -> [] not raise.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_build_cards.py -q
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

import scripts.platformkit.bestbets.build_cards as _bc_mod
from scripts.platformkit.bestbets.build_cards import build_cards

# Capture the REAL _call_build_prop_cards BEFORE the autouse fixture patches it,
# so the decoupling tests can exercise the genuine cache-read path.
_REAL_CALL_BUILD_PROP_CARDS = _bc_mod._call_build_prop_cards


@pytest.fixture(autouse=True)
def _no_live_prop_board():
    """Isolate the GAME-market assertions from the live prop board.

    build_cards now also appends player-prop cards via _call_build_prop_cards,
    which calls the real build_prop_board (loads parquets / providers -- slow and
    nondeterministic). These game-market tests must stay fast and deterministic, so
    we stub the prop append to []. The prop path has its OWN per-file test
    (test_prop_cards.py). One test below overrides this to assert the wiring.
    """
    with patch(
        "scripts.platformkit.bestbets.build_cards._call_build_prop_cards",
        return_value=[],
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers: minimal valid BestBetCard factory
# ---------------------------------------------------------------------------

_BANNED_KEYS = {"dollar", "pnl", "roi", "profit", "bankroll", "usd"}


def _make_card(
    matchup: str = "TeamA vs TeamB",
    sport: str = "nba",
    market_prob: float = 0.52,
    model_prob: float = 0.56,
    edge_vs_market: float = 0.04,
    tipoff_utc: Optional[str] = None,
    best_odds: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a minimal card dict that passes all sanitization checks by default."""
    return {
        "game_id": "g1",
        "matchup": matchup,
        "sport": sport,
        "market_type": "moneyline",
        "prop_player": None,
        "prop_stat": None,
        "side": "home",
        "model_prob": model_prob,
        "market_prob": market_prob,
        "best_book": "draftkings",
        "best_odds": best_odds,
        "all_books": [],
        "edge_vs_market": edge_vs_market,
        "units": 1.0,
        "tier": "B",
        "confidence": model_prob,
        "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True,
                "clv_pct": None, "beat_close": None},
        "clv_is_proxy": True,
        "status": "pregame",
        "honest_note": "test card",
        "tipoff_utc": tipoff_utc,
    }


def _future_tipoff(days_ahead: int = 1) -> str:
    """ISO-8601 UTC timestamp *days_ahead* in the future."""
    dt = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=days_ahead)
    return dt.isoformat()


def _past_tipoff(days_ago: int = 365) -> str:
    """ISO-8601 UTC timestamp *days_ago* in the past."""
    dt = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Acceptance test A: returns a list (no exception, no None)
# ---------------------------------------------------------------------------

class TestBuildCardsReturnsListNoRaise:
    """A: build_cards(now=fixed) always returns a list, never raises."""

    def test_returns_list_with_real_compute(self):
        now = time.time()
        result = build_cards(now=now)
        assert isinstance(result, list), (
            f"Expected list, got {type(result)!r}"
        )

    def test_returns_list_with_all_empty_upstream(self):
        """Empty upstream -> [] not raise."""
        empty_result = {"status": "ok", "cards": [], "sport": "nba"}
        now = time.time()
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            return_value=empty_result,
        ):
            result = build_cards(now=now, sports=("nba",))
        assert result == [], f"Expected [], got {result!r}"

    def test_no_exception_on_none_now(self):
        result = build_cards(now=None)
        assert isinstance(result, list)

    def test_no_exception_when_compute_raises(self):
        """If compute_best_bets raises, degrade to []."""
        def _exploding(sport):
            raise RuntimeError("upstream kaboom")
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_exploding,
        ):
            result = build_cards(now=time.time(), sports=("nba",))
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Acceptance test B: stale Polymarket 'Yes vs No' card absent
# ---------------------------------------------------------------------------

class TestYesVsNoBinaryCardDropped:
    """B: a Polymarket 'Yes vs No' binary card is absent from output."""

    def _run_with_cards(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = time.time()
        def _fake_compute(sport):
            return {"status": "ok", "sport": sport, "cards": cards}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_fake_compute,
        ):
            return build_cards(now=now, sports=("soccer_intl",))

    def test_yes_vs_no_stale_polymarket_card_dropped(self):
        """The exemplar bad card: matchup='Yes vs No', market_prob=0.0005, 1yr past."""
        bad_card = _make_card(
            matchup="Yes vs No",
            sport="soccer_intl",
            market_prob=0.0005,
            model_prob=0.999,
            edge_vs_market=0.998,
            tipoff_utc=_past_tipoff(365),
        )
        result = self._run_with_cards([bad_card])
        matchups = [c.get("matchup", "") for c in result]
        assert "Yes vs No" not in matchups, (
            f"'Yes vs No' card survived sanitization. Output matchups: {matchups!r}"
        )

    def test_yes_vs_no_case_insensitive(self):
        """Any casing of 'Yes vs No' is dropped."""
        bad_card = _make_card(
            matchup="yes vs no",
            sport="soccer_intl",
            market_prob=0.50,
            model_prob=0.55,
            edge_vs_market=0.05,
            tipoff_utc=_future_tipoff(1),
        )
        result = self._run_with_cards([bad_card])
        assert all("yes vs no" not in c.get("matchup", "").lower() for c in result)

    def test_good_soccer_card_survives(self):
        """A genuine soccer card with a future tipoff is not dropped."""
        good_card = _make_card(
            matchup="France vs Brazil",
            sport="soccer_intl",
            market_prob=0.55,
            model_prob=0.60,
            edge_vs_market=0.05,
            tipoff_utc=_future_tipoff(1),
        )
        result = self._run_with_cards([good_card])
        matchups = [c.get("matchup", "") for c in result]
        assert "France vs Brazil" in matchups, (
            f"Good card was incorrectly dropped. Output matchups: {matchups!r}"
        )


# ---------------------------------------------------------------------------
# Acceptance test C: past-tipoff card absent
# ---------------------------------------------------------------------------

class TestPastTipoffCardDropped:
    """C: a card whose tipoff is in the past is absent from output."""

    def _run_with_cards(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = time.time()
        def _fake_compute(sport):
            return {"status": "ok", "sport": sport, "cards": cards}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_fake_compute,
        ):
            return build_cards(now=now, sports=("nba",))

    def test_past_tipoff_dropped(self):
        """Card with tipoff 1 day in the past is dropped."""
        stale = _make_card(
            matchup="BOS vs LAL",
            sport="nba",
            market_prob=0.52,
            model_prob=0.56,
            edge_vs_market=0.04,
            tipoff_utc=_past_tipoff(1),
        )
        result = self._run_with_cards([stale])
        matchups = [c.get("matchup", "") for c in result]
        assert "BOS vs LAL" not in matchups, (
            f"Past-tipoff card survived sanitization. Output matchups: {matchups!r}"
        )

    def test_future_tipoff_survives(self):
        """Card with tipoff 2 days in the future is not dropped for staleness."""
        fresh = _make_card(
            matchup="BOS vs MIA",
            sport="nba",
            market_prob=0.52,
            model_prob=0.56,
            edge_vs_market=0.04,
            tipoff_utc=_future_tipoff(2),
        )
        result = self._run_with_cards([fresh])
        matchups = [c.get("matchup", "") for c in result]
        assert "BOS vs MIA" in matchups, (
            f"Future-tipoff card was incorrectly dropped. Output matchups: {matchups!r}"
        )

    def test_no_tipoff_field_not_dropped_on_that_criterion(self):
        """A card with NO tipoff field is not dropped for the tipoff criterion."""
        no_tipoff = _make_card(
            matchup="NYK vs SAS",
            sport="nba",
            market_prob=0.52,
            model_prob=0.56,
            edge_vs_market=0.04,
            tipoff_utc=None,
        )
        result = self._run_with_cards([no_tipoff])
        matchups = [c.get("matchup", "") for c in result]
        # Should survive (tipoff criterion: missing time -> not a drop)
        assert "NYK vs SAS" in matchups, (
            f"Card with no tipoff was incorrectly dropped. Output matchups: {matchups!r}"
        )


# ---------------------------------------------------------------------------
# Acceptance test D: no banned keys, edge_vs_market is a float
# ---------------------------------------------------------------------------

class TestNoBannedKeysProbDiff:
    """D: every returned card has no $/pnl/roi field; edge_vs_market is a float."""

    def _run_with_cards(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = time.time()
        def _fake_compute(sport):
            return {"status": "ok", "sport": sport, "cards": cards}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_fake_compute,
        ):
            return build_cards(now=now, sports=("nba",))

    def test_no_dollar_pnl_roi_keys(self):
        """No banned money-key on any card."""
        card = _make_card(tipoff_utc=_future_tipoff(1))
        result = self._run_with_cards([card])
        for c in result:
            for banned in _BANNED_KEYS:
                assert banned not in c, (
                    f"Banned key '{banned}' found in card: {list(c.keys())!r}"
                )

    def test_edge_vs_market_is_float(self):
        """edge_vs_market is a finite float (prob diff), not a string or None."""
        import math
        card = _make_card(
            market_prob=0.52, model_prob=0.56, edge_vs_market=0.04,
            tipoff_utc=_future_tipoff(1),
        )
        result = self._run_with_cards([card])
        for c in result:
            evm = c.get("edge_vs_market")
            assert isinstance(evm, (int, float)), (
                f"edge_vs_market is not numeric: {evm!r}"
            )
            assert math.isfinite(float(evm)), (
                f"edge_vs_market is not finite: {evm!r}"
            )

    def test_units_is_flat_unit(self):
        """units field is present and numeric (flat-unit, not $)."""
        card = _make_card(tipoff_utc=_future_tipoff(1))
        result = self._run_with_cards([card])
        for c in result:
            units = c.get("units")
            assert units is not None, "units field missing from card"
            assert isinstance(units, (int, float)), (
                f"units is not numeric: {units!r}"
            )


# ---------------------------------------------------------------------------
# Acceptance test E: empty upstream -> [] not raise
# ---------------------------------------------------------------------------

class TestEmptyUpstreamReturnsEmptyList:
    """E: when all sports return empty cards, build_cards returns [] not raise."""

    def test_all_sports_empty(self):
        def _empty(sport):
            return {"status": "ok", "sport": sport, "cards": []}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_empty,
        ):
            result = build_cards(now=time.time())
        assert result == [], f"Expected [], got {result!r}"

    def test_compute_returns_no_cards_key(self):
        """If upstream omits 'cards' key entirely, degrade to []."""
        def _no_cards(sport):
            return {"status": "ok", "sport": sport}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_no_cards,
        ):
            result = build_cards(now=time.time())
        assert isinstance(result, list)

    def test_compute_returns_none_for_cards(self):
        """If upstream sets cards=None, degrade to []."""
        def _none_cards(sport):
            return {"status": "ok", "sport": sport, "cards": None}
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=_none_cards,
        ):
            result = build_cards(now=time.time())
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Prop wiring: player-prop cards are appended to the unified board
# ---------------------------------------------------------------------------

class TestPropCardsWiredIn:
    """build_cards appends market_type='prop' cards from the prop path."""

    def _prop_card(self):
        return {
            "game_id": "", "matchup": "A vs B", "sport": "soccer_intl",
            "market_type": "prop", "prop_player": "P", "prop_stat": "Shots",
            "line": 1.5, "side": "over", "model_prob": 0.62, "proj": 2.1,
            "market_prob": None, "best_book": "underdog", "best_odds": None,
            "all_books": [], "edge_vs_market": None, "units": 1.0,
            "tier": "MODEL_VIEW", "confidence": 0.62, "model_only": True,
            "edge_claimed": False, "status": "pregame", "as_of": "2026-06-21",
            "honest_note": "model-only", "clv_is_proxy": True,
        }

    def test_prop_card_appended_even_with_no_game_cards(self):
        """No game cards but live props -> board still has the prop cards."""
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=lambda s: {"status": "ok", "sport": s, "cards": []},
        ), patch(
            "scripts.platformkit.bestbets.build_cards._call_build_prop_cards",
            return_value=[self._prop_card()],
        ):
            result = build_cards(now=time.time())
        props = [c for c in result if c.get("market_type") == "prop"]
        assert len(props) == 1
        assert props[0]["model_only"] is True
        assert props[0]["edge_vs_market"] is None  # model-only: no edge claimed

    def test_model_only_prop_not_dropped_by_market_prob_guard(self):
        """A null-market_prob model-only prop survives (appended AFTER sanitize)."""
        with patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=lambda s: {"status": "ok", "sport": s,
                                   "cards": [_make_card()]},
        ), patch(
            "scripts.platformkit.bestbets.build_cards._call_build_prop_cards",
            return_value=[self._prop_card()],
        ):
            result = build_cards(now=time.time())
        assert any(c.get("market_type") == "prop" for c in result)
        assert any(c.get("market_type") == "moneyline" for c in result)


# ---------------------------------------------------------------------------
# Decoupled cache: m10 reads the prop cache; it NEVER runs the slow build inline
# ---------------------------------------------------------------------------

class TestPropCacheDecoupling:
    """The fast m10 board reads prop_cards_cache; it must not build inline."""

    def _prop_card(self):
        return {
            "game_id": "", "matchup": "A vs B", "sport": "soccer_intl",
            "market_type": "prop", "prop_player": "P", "prop_stat": "Shots",
            "line": 1.5, "side": "over", "model_prob": 0.62, "proj": 2.1,
            "market_prob": None, "best_book": "underdog", "best_odds": None,
            "all_books": [], "edge_vs_market": None, "units": 1.0,
            "tier": "MODEL_VIEW", "confidence": 0.62, "model_only": True,
            "edge_claimed": False, "status": "pregame", "as_of": "2099-01-01",
            "honest_note": "model-only", "clv_is_proxy": True,
        }

    def test_reads_cache_not_slow_build(self, tmp_path):
        """build_cards reads the prop cache and NEVER calls build_prop_cards.

        build_prop_cards is the >240s full-board build. If build_cards ever calls
        it, the board tick hangs -- so we assert it is NOT invoked.
        """
        import scripts.platformkit.bestbets.prop_cards_cache as cache
        import scripts.platformkit.bestbets.prop_cards as pc

        p = tmp_path / "prop_cards_cache.json"
        now = 1000.0
        cache.write([self._prop_card()], now, n_more_model_only={"mlb": 3},
                    path=p)

        called = {"slow": False}

        def _boom_slow(*a, **k):
            called["slow"] = True
            raise AssertionError("slow build_prop_cards must NOT run inline")

        with patch.object(pc, "build_prop_cards", _boom_slow), patch.object(
            cache, "_DEFAULT_PATH", p
        ), patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=lambda s: {"status": "ok", "sport": s, "cards": []},
        ):
            # Undo the autouse stub so the REAL _call_build_prop_cards runs.
            with patch.object(
                _bc_mod, "_call_build_prop_cards", _REAL_CALL_BUILD_PROP_CARDS,
            ):
                result = build_cards(now=now)
        assert called["slow"] is False
        props = [c for c in result if c.get("market_type") == "prop"]
        assert len(props) == 1

    def test_missing_cache_degrades_honestly(self, tmp_path):
        """Missing cache -> game cards still emit, props omitted, no hang/raise."""
        import scripts.platformkit.bestbets.prop_cards_cache as cache
        import scripts.platformkit.bestbets.build_cards as bc

        missing = tmp_path / "nope.json"
        with patch.object(cache, "_DEFAULT_PATH", missing), patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=lambda s: {"status": "ok", "sport": s,
                                   "cards": [_make_card(
                                       tipoff_utc=_future_tipoff(1))]},
        ):
            # Real prop path (reads the missing cache) -- override the autouse stub.
            with patch.object(
                bc, "_call_build_prop_cards", _REAL_CALL_BUILD_PROP_CARDS,
            ):
                result = build_cards(now=time.time(), sports=("nba",))
        # Game cards present; NO prop cards (cache missing -> honest omit).
        assert any(c.get("market_type") == "moneyline" for c in result)
        assert not any(c.get("market_type") == "prop" for c in result)

    def test_stale_cache_omits_props(self, tmp_path):
        """A cache older than the SLA -> props omitted (stale-never-green)."""
        import scripts.platformkit.bestbets.prop_cards_cache as cache
        import scripts.platformkit.bestbets.build_cards as bc

        p = tmp_path / "prop_cards_cache.json"
        cache.write([self._prop_card()], 1000.0, path=p)
        now = 1000.0 + cache.DEFAULT_SLA_SEC + 9999.0
        with patch.object(cache, "_DEFAULT_PATH", p), patch(
            "scripts.platformkit.bestbets.build_cards._call_compute_best_bets",
            side_effect=lambda s: {"status": "ok", "sport": s, "cards": []},
        ):
            with patch.object(
                bc, "_call_build_prop_cards", _REAL_CALL_BUILD_PROP_CARDS,
            ):
                result = build_cards(now=now)
        assert not any(c.get("market_type") == "prop" for c in result)
