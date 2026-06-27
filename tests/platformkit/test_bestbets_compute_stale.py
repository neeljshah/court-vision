"""test_bestbets_compute_stale.py -- integration tests for stale suppression
wired into compute_best_bets (BE-A-stale-suppress-board).

Acceptance criteria:
  (1) Card with tipoff_utc 150 h past, no completion signal -> dropped (None).
  (2) Card with live.state='post' -> dropped/demoted (no longer Tier-A pregame).
  (3) Yes/No matchup card -> dropped.
  (4) Fresh pregame card (tipoff 2 h future) -> retained.
  (5) No $ field on any output card.
  (6) edge_claimed=False on the top-level result dict.

Strategy: monkey-patch _get_edge_view and _do_decide_game in bestbets_compute
so the tests run pure-Python with no network / no store dependency.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    tests/platformkit/test_bestbets_compute_stale.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _future_iso(hours: float = 2.0) -> str:
    return _iso(_NOW + timedelta(hours=hours))


def _past_iso(hours: float) -> str:
    return _iso(_NOW - timedelta(hours=hours))


def _make_game(
    game_id: str,
    home: str,
    away: str,
    tipoff: Optional[str] = None,
    live_state: str = "",
    tier: str = "A",
    market_prob: float = 0.55,
    model_prob: float = 0.62,
) -> Dict[str, Any]:
    """Return a minimal game dict suitable for _do_decide_game return."""
    return {
        "game_id": game_id,
        "home": home,
        "away": away,
        "tipoff": tipoff,
        "live": {"state": live_state} if live_state else {},
        "best_bets": [{
            "decision": "bet",
            "market_type": "moneyline",
            "side": home,
            "tier": tier,
            "flat_unit": 1.0,
            "model_prob": model_prob,
            "market_prob": market_prob,
        }],
        "candidates": [{
            "market_type": "moneyline",
            "side": home,
            "model_prob": model_prob,
            "market_prob": market_prob,
            "best_book": "draftkings",
            "best_odds": 1.85,
            "all_books": [],
            "flat_unit": 1.0,
        }],
    }


def _compute(games: List[Dict[str, Any]], now: datetime = _NOW) -> Dict[str, Any]:
    """Run compute_best_bets with patched dependencies; injects a fixed now."""
    # Reload to get a clean module state.
    mod_name = "predict_service.bestbets_compute"
    if mod_name in sys.modules:
        mod = sys.modules[mod_name]
    else:
        mod = importlib.import_module(mod_name)

    edge_view = {"status": "ok", "games": games}

    def _fake_edge_view(sport: str) -> Dict[str, Any]:  # noqa: ARG001
        return edge_view

    def _fake_decide(game: Dict[str, Any]) -> Dict[str, Any]:
        return game

    with (
        mock.patch.object(mod, "_get_edge_view", side_effect=_fake_edge_view),
        mock.patch.object(mod, "_do_decide_game", side_effect=_fake_decide),
        # Inject deterministic now into apply_suppression via stale_game_suppressor
        mock.patch(
            "scripts.platformkit.bestbets.stale_game_suppressor"
            ".apply_suppression",
            wraps=_wrap_supp(now),
        ),
    ):
        return mod.compute_best_bets("nba", include_props=False)


def _wrap_supp(now: datetime):
    """Return a wrapper for apply_suppression that pins 'now'."""
    from scripts.platformkit.bestbets.stale_game_suppressor import (
        apply_suppression as _real,
    )

    def _wrapped(cards, **kwargs):
        kwargs.setdefault("now", now)
        return _real(cards, **kwargs)

    return _wrapped


# ---------------------------------------------------------------------------
# (1) Stale tipoff 150 h past -> card dropped
# ---------------------------------------------------------------------------

class TestStaleTipoffDropped:
    def test_150h_past_card_absent(self):
        """(1) tipoff 150 h in the past with no completion signal -> excluded."""
        game = _make_game(
            "nyk_sas_old", "NYK", "SAS", tipoff=_past_iso(150),
        )
        result = _compute([game])
        ids = [c["game_id"] for c in result["cards"]]
        assert "nyk_sas_old" not in ids, (
            "150-h-old card must not appear on the board (got ids=%s)" % ids
        )

    def test_150h_past_no_pregame_status(self):
        """(1b) No stale card is served with status='pregame'."""
        game = _make_game("old2", "NYK", "SAS", tipoff=_past_iso(150))
        result = _compute([game])
        for c in result["cards"]:
            if c["game_id"] == "old2":
                assert c.get("status") != "pregame", (
                    "Stale card must not have status='pregame': %s" % c
                )


# ---------------------------------------------------------------------------
# (2) live.state='post' -> dropped / demoted (not a Tier-A pregame card)
# ---------------------------------------------------------------------------

class TestPostStateSuppressed:
    def test_post_state_not_actionable(self):
        """(2) game with live.state='post' must not appear as a Tier-A pregame bet."""
        game = _make_game(
            "post_game", "LAL", "BOS",
            tipoff=_future_iso(1),  # future tipoff but live says post
            live_state="post",
        )
        result = _compute([game])
        actionable = [
            c for c in result["cards"]
            if c["game_id"] == "post_game"
            and c.get("status") == "pregame"
            and c.get("tier") == "A"
        ]
        assert actionable == [], (
            "post-state game must not appear as Tier-A pregame: %s" % actionable
        )

    def test_post_state_card_dropped_or_demoted(self):
        """(2b) post-state card is either absent or has decision!='bet'."""
        game = _make_game(
            "post_game2", "MIL", "PHI",
            tipoff=_future_iso(2),
            live_state="post",
        )
        result = _compute([game])
        for c in result["cards"]:
            if c["game_id"] == "post_game2":
                assert c.get("decision") != "bet", (
                    "post-state card must not have decision='bet': %s" % c
                )


# ---------------------------------------------------------------------------
# (3) Yes/No matchup card -> dropped
# ---------------------------------------------------------------------------

class TestYesNoDropped:
    def test_yes_vs_no_matchup_absent(self):
        """(3) matchup='Yes vs No' (Polymarket binary) -> excluded from board."""
        # Inject a card whose matchup is Yes vs No by using home='Yes', away='No'
        game = _make_game(
            "pm_binary", "Yes", "No",
            tipoff=_future_iso(3),
            market_prob=0.0005,  # also dead-market; belt+suspenders
        )
        result = _compute([game])
        ids = [c["game_id"] for c in result["cards"]]
        assert "pm_binary" not in ids, (
            "Yes/No binary matchup must be excluded (got ids=%s)" % ids
        )

    def test_yes_vs_no_explicit_matchup(self):
        """(3b) Direct Yes vs No matchup string in card -> excluded."""
        from scripts.platformkit.bestbets.stale_game_suppressor import suppress_card
        card = {
            "game_id": "pm1", "matchup": "Yes vs No",
            "market_prob": 0.55, "tipoff_utc": _future_iso(5),
            "status": "pregame", "tier": "A",
        }
        out = suppress_card(card, now=_NOW)
        assert out is None, "Yes vs No card must be suppressed (got %s)" % out


# ---------------------------------------------------------------------------
# (4) Fresh pregame card (tipoff 2 h future) -> retained
# ---------------------------------------------------------------------------

class TestFreshPregameRetained:
    def test_fresh_card_present(self):
        """(4) Tipoff 2 h in future -> card retained on board."""
        game = _make_game(
            "fresh_game", "GSW", "DEN",
            tipoff=_future_iso(2),
            tier="A",
            model_prob=0.63,
            market_prob=0.55,
        )
        result = _compute([game])
        ids = [c["game_id"] for c in result["cards"]]
        assert "fresh_game" in ids, (
            "Fresh pregame card must be retained (got ids=%s)" % ids
        )

    def test_fresh_card_tier_intact(self):
        """(4b) Fresh card tier and status are not demoted by suppressor."""
        game = _make_game(
            "fresh_game2", "OKC", "PHX",
            tipoff=_future_iso(4),
            tier="A",
        )
        result = _compute([game])
        matches = [c for c in result["cards"] if c["game_id"] == "fresh_game2"]
        assert matches, "Fresh card must appear in board"
        c = matches[0]
        assert c.get("status") in ("pregame", "live"), (
            "Fresh card must have live/pregame status, got: %s" % c.get("status")
        )


# ---------------------------------------------------------------------------
# (5) No dollar-amount / P&L keys on any output card
# ---------------------------------------------------------------------------

# Keys whose presence would signal a prohibited dollar-amount field.
_DOLLAR_KEYS = frozenset({
    "pnl", "roi", "dollar_pnl", "profit", "dollar_edge",
    "roi_pct", "profit_usd", "expected_value_dollars",
})


class TestNoDollarField:
    def test_no_dollar_key_in_cards(self):
        """(5) No card in the board output carries a dollar-amount key."""
        games = [
            _make_game("fresh3", "MIA", "CLE", tipoff=_future_iso(3)),
            _make_game("stale3", "NYK", "SAS", tipoff=_past_iso(150)),
        ]
        result = _compute(games)
        for card in result["cards"]:
            bad = _DOLLAR_KEYS & set(card.keys())
            assert not bad, "Dollar-amount key(s) %s found in card: %s" % (bad, card)

    def test_no_dollar_key_in_result_envelope(self):
        """(5b) Top-level result envelope has no dollar-amount key."""
        game = _make_game("nodollar", "BKN", "TOR", tipoff=_future_iso(2))
        result = _compute([game])
        bad = _DOLLAR_KEYS & set(result.keys())
        assert not bad, "Dollar-amount key(s) %s in result envelope" % bad


# ---------------------------------------------------------------------------
# (6) edge_claimed=False on result dict
# ---------------------------------------------------------------------------

class TestEdgeClaimedFalse:
    def test_edge_claimed_false(self):
        """(6) compute_best_bets always returns edge_claimed=False."""
        game = _make_game("ec1", "SAC", "UTA", tipoff=_future_iso(5))
        result = _compute([game])
        assert result.get("edge_claimed") is False, (
            "edge_claimed must be False, got: %s" % result.get("edge_claimed")
        )

    def test_edge_claimed_false_empty_board(self):
        """(6b) edge_claimed=False even when board is empty."""
        result = _compute([])
        assert result.get("edge_claimed") is False
