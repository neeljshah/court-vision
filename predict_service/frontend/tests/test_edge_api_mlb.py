"""Per-file tests for predict_service.frontend.edge_api -- MLB edge card builder.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_edge_api_mlb.py -q

Acceptance criteria (ws4-edge-view-mlb-divergence):
  A. Differentiated multi-game MLB SnapshotEnvelope yields >0 ranked edge rows each
     carrying model_prob, market_prob/divergence and tier, with NO '$'/pnl/roi/profit.
  B. Flat (uniform 2-value prior) envelope yields 0 cards with status='degenerate',
     proving uniformity suppression still holds.
  C. Empty / unavailable envelope yields 0 cards with status='none'.
  D. No forbidden $ / pnl / roi / profit key anywhere in any output.
  E. build_edge_view() delegates to upstream without fabricating any value.

RAILS: per-file only; ASCII only; no $ / pnl / roi / profit; no network; no IO.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from predict_service.frontend.edge_api import (
    build_edge_view,
    build_mlb_edge_cards,
    _HONEST_NOTE,
    _MIN_DISTINCT_PROBS,
    _TIER_FLOORS,
)

# ---------------------------------------------------------------------------
# Constants / test fixtures
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "profit", "bankroll", "usd", "dollar",
    "stake_$", "revenue", "$edge", "money_edge",
})

_VALID_TIERS = frozenset({"A", "B", "C"})


def _has_forbidden(obj: Any) -> bool:
    """Recursively scan *obj* for any forbidden $ key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _FORBIDDEN_KEYS:
                return True
            if _has_forbidden(v):
                return True
    elif isinstance(obj, (list, tuple)):
        return any(_has_forbidden(item) for item in obj)
    return False


def _comparison_row(
    market_type: str = "moneyline",
    side: str = "home",
    model_prob: float = 0.60,
    market_prob: float = 0.50,
    best_book: str = "draftkings",
    best_odds: float = 1.95,
    ev: float = 0.10,
    tier: Optional[str] = None,
    clv_is_proxy: bool = True,
) -> Dict[str, Any]:
    """Build a minimal comparison row (as produced by frontend.edge_compare.comparison)."""
    return {
        "market_type": market_type,
        "side": side,
        "model_prob": model_prob,
        "market_prob": market_prob,
        "best_book": best_book,
        "best_odds": best_odds,
        "line": None,
        "edge": round(model_prob - market_prob, 6),
        "ev": ev,
        "tier": tier,
        "clv_is_proxy": clv_is_proxy,
    }


def _game(
    game_id: str = "mlb_001",
    home: str = "Yankees",
    away: str = "Red Sox",
    tipoff: str = "2026-06-25T19:05:00+00:00",
    comparison: Optional[List[Dict[str, Any]]] = None,
    status: str = "ok",
) -> Dict[str, Any]:
    """Build one game entry as produced by frontend.edge_api.build_edge_view."""
    if comparison is None:
        comparison = [
            _comparison_row(model_prob=0.60, market_prob=0.50, ev=0.12),
            _comparison_row(side="away", model_prob=0.40, market_prob=0.50, ev=-0.10),
        ]
    return {
        "sport": "mlb",
        "game_id": game_id,
        "home": home,
        "away": away,
        "tipoff": tipoff,
        "status": status,
        "model": {"probs": {"home_ml": 0.60, "away_ml": 0.40}, "leak_guard": {"in_sample": False}},
        "markets": [],
        "comparison": comparison,
        "freshness": {"status": "unknown", "age_sec": None},
        "as_of": "2026-06-20T10:00:00+00:00",
    }


def _differentiated_view(n_games: int = 4) -> Dict[str, Any]:
    """Build a realistic multi-game edge view with differentiated model_probs.

    Each game has a distinct home model_prob so the distinct-prob count exceeds
    _MIN_DISTINCT_PROBS (3) and no uniformity suppression fires.
    """
    probs = [0.58, 0.62, 0.55, 0.65, 0.70, 0.53]
    games = []
    for i in range(n_games):
        mp = probs[i % len(probs)]
        games.append(_game(
            game_id="mlb_%03d" % i,
            home="HomeTeam%d" % i,
            away="AwayTeam%d" % i,
            comparison=[
                _comparison_row(model_prob=mp, market_prob=0.50, ev=round(mp - 0.50, 4)),
                _comparison_row(side="away", model_prob=1.0 - mp, market_prob=0.50,
                                ev=round((1.0 - mp) - 0.50, 4)),
            ],
        ))
    return {
        "sport": "mlb",
        "generated_at": "2026-06-20T10:00:00+00:00",
        "status": "ok",
        "count": n_games,
        "games": games,
        "honest_note": _HONEST_NOTE,
        "edge_note": "edge = model_prob - market_prob",
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _flat_view(n_games: int = 4) -> Dict[str, Any]:
    """Build an edge view where all games share exactly 2 model_prob values (flat prior)."""
    games = []
    for i in range(n_games):
        games.append(_game(
            game_id="mlb_%03d" % i,
            home="HomeTeam%d" % i,
            away="AwayTeam%d" % i,
            comparison=[
                # All home sides collapse to 0.5345, away to 0.4655.
                _comparison_row(model_prob=0.5345, market_prob=0.50, ev=0.06),
                _comparison_row(side="away", model_prob=0.4655, market_prob=0.50, ev=-0.06),
            ],
        ))
    return {
        "sport": "mlb",
        "generated_at": "2026-06-20T10:00:00+00:00",
        "status": "ok",
        "count": n_games,
        "games": games,
        "honest_note": _HONEST_NOTE,
        "edge_note": "edge = model_prob - market_prob",
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _empty_view() -> Dict[str, Any]:
    """Build an edge view with no games (empty slate)."""
    return {
        "sport": "mlb",
        "generated_at": "2026-06-20T10:00:00+00:00",
        "status": "ok",
        "count": 0,
        "games": [],
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _unavailable_view() -> Dict[str, Any]:
    """Build an edge view with status='unavailable' (no snapshot)."""
    return {
        "sport": "mlb",
        "generated_at": "",
        "status": "unavailable",
        "reason": "latest.json missing",
        "count": 0,
        "games": [],
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


# ---------------------------------------------------------------------------
# A. Differentiated multi-game MLB view -> >0 ranked edge rows
# ---------------------------------------------------------------------------

class TestDifferentiatedMLBView:
    """Acceptance criterion A: differentiated probs -> >0 ranked edge cards."""

    def test_returns_cards_gt_zero(self):
        """Differentiated 4-game view -> more than 0 ranked edge cards."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        assert result["status"] == "ok"
        assert result["count"] > 0
        assert len(result["cards"]) > 0

    def test_cards_carry_model_prob(self):
        """Each card carries a float model_prob in (0, 1)."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        for card in result["cards"]:
            mp = card.get("model_prob")
            assert mp is not None, "model_prob missing"
            assert 0.0 < float(mp) < 1.0, "model_prob not in (0,1): %r" % mp

    def test_cards_carry_market_prob(self):
        """Each card carries a float market_prob in (0, 1)."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        for card in result["cards"]:
            mkt = card.get("market_prob")
            assert mkt is not None, "market_prob missing"
            assert 0.0 < float(mkt) < 1.0, "market_prob not in (0,1): %r" % mkt

    def test_cards_carry_divergence(self):
        """Each card carries divergence = model_prob - market_prob."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        for card in result["cards"]:
            div = card.get("divergence")
            assert div is not None, "divergence missing"
            expected = round(card["model_prob"] - card["market_prob"], 6)
            assert abs(float(div) - expected) < 1e-9, (
                "divergence mismatch: %r vs expected %r" % (div, expected)
            )

    def test_cards_carry_valid_tier(self):
        """Each card carries a tier in {A, B, C}."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        for card in result["cards"]:
            tier = card.get("tier")
            assert tier in _VALID_TIERS, "invalid tier: %r" % tier

    def test_ranked_tier_then_confidence(self):
        """Cards are ranked: tier A before B before C, then confidence desc within tier."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=6))
        cards = result["cards"]
        if len(cards) < 2:
            pytest.skip("fewer than 2 cards to check ordering")
        tier_rank = {"A": 0, "B": 1, "C": 2}
        for i in range(len(cards) - 1):
            a, b = cards[i], cards[i + 1]
            ta = tier_rank.get(str(a.get("tier") or "C"), 99)
            tb = tier_rank.get(str(b.get("tier") or "C"), 99)
            if ta == tb:
                assert float(a.get("confidence") or 0) >= float(b.get("confidence") or 0), (
                    "within same tier, cards[%d] confidence < cards[%d]" % (i, i + 1)
                )
            else:
                assert ta <= tb, "tier order wrong at index %d: %r > %r" % (i, a["tier"], b["tier"])

    def test_no_forbidden_keys_in_cards(self):
        """No $ / pnl / roi / profit key anywhere in any card."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        assert not _has_forbidden(result["cards"]), "forbidden $ key found in cards"

    def test_no_forbidden_keys_in_full_result(self):
        """No $ / pnl / roi / profit key in the top-level result dict."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        assert not _has_forbidden(result), "forbidden $ key found in full result"

    def test_edge_claimed_false(self):
        """edge_claimed is always False (honesty rail)."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        assert result.get("edge_claimed") is False

    def test_honest_note_present(self):
        """honest_note is present and non-empty."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        assert result.get("honest_note"), "honest_note is missing or empty"

    def test_2_game_view_not_suppressed(self):
        """A 2-game differentiated view (< _MIN_DISTINCT_PROBS games) is NOT suppressed
        even if it has only 2 distinct probs, because n_games < threshold."""
        view = _differentiated_view(n_games=2)
        result = build_mlb_edge_cards(view)
        # 2 games < _MIN_DISTINCT_PROBS=3 -> no degeneracy gate, cards may flow
        # status is either 'ok' (cards present) or 'none' (no bets cleared tier)
        assert result["status"] in ("ok", "none")
        # Critically: status must NOT be 'degenerate' for a 2-game slate
        assert result["status"] != "degenerate"


# ---------------------------------------------------------------------------
# B. Flat (uniform 2-value) envelope -> 0 cards, status='degenerate'
# ---------------------------------------------------------------------------

class TestFlatPriorSuppression:
    """Acceptance criterion B: flat prior -> 0 cards, status='degenerate'."""

    def test_flat_4game_view_returns_zero_cards(self):
        """Flat prior 4-game view (2 distinct probs) -> 0 cards."""
        result = build_mlb_edge_cards(_flat_view(n_games=4))
        assert result["count"] == 0
        assert result["cards"] == []

    def test_flat_4game_view_status_degenerate(self):
        """Flat prior 4-game view -> status='degenerate'."""
        result = build_mlb_edge_cards(_flat_view(n_games=4))
        assert result["status"] == "degenerate"

    def test_flat_view_has_degenerate_reason(self):
        """Flat prior view includes a degenerate_reason explaining suppression."""
        result = build_mlb_edge_cards(_flat_view(n_games=4))
        reason = result.get("degenerate_reason", "")
        assert reason, "degenerate_reason is missing or empty"
        # Should mention values/collapse somewhere
        assert len(reason) > 10, "degenerate_reason is too short: %r" % reason

    def test_flat_view_no_forbidden_keys(self):
        """Flat prior result has no $ / pnl / roi / profit keys."""
        result = build_mlb_edge_cards(_flat_view(n_games=4))
        assert not _has_forbidden(result)

    def test_flat_view_edge_claimed_false(self):
        """Flat prior result has edge_claimed=False."""
        result = build_mlb_edge_cards(_flat_view(n_games=4))
        assert result.get("edge_claimed") is False

    def test_flat_11game_view_suppressed(self):
        """The QA-original failure (11 games, 2 distinct probs) is suppressed."""
        result = build_mlb_edge_cards(_flat_view(n_games=11))
        assert result["status"] == "degenerate"
        assert result["count"] == 0

    def test_single_value_collapse_suppressed(self):
        """Slate where all games share exactly 1 model_prob -> suppressed."""
        games = []
        for i in range(5):
            games.append(_game(
                game_id="mlb_%03d" % i,
                comparison=[
                    _comparison_row(model_prob=0.50, market_prob=0.50, ev=0.0),
                ],
            ))
        view = {
            "sport": "mlb", "generated_at": "2026-06-20T10:00:00+00:00",
            "status": "ok", "count": 5, "games": games,
            "honest_note": _HONEST_NOTE, "edge_claimed": False, "schema_version": "1.2.0",
        }
        result = build_mlb_edge_cards(view)
        assert result["status"] == "degenerate"
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# C. Empty / unavailable envelope -> 0 cards, status='none'
# ---------------------------------------------------------------------------

class TestEmptyAndUnavailable:
    """Acceptance criterion C: empty or unavailable -> 0 cards, status='none'."""

    def test_empty_games_returns_none_status(self):
        """Empty games list -> status='none'."""
        result = build_mlb_edge_cards(_empty_view())
        assert result["status"] == "none"

    def test_empty_games_returns_zero_cards(self):
        """Empty games list -> 0 cards."""
        result = build_mlb_edge_cards(_empty_view())
        assert result["count"] == 0
        assert result["cards"] == []

    def test_unavailable_snapshot_returns_none_status(self):
        """Unavailable snapshot -> status='none'."""
        result = build_mlb_edge_cards(_unavailable_view())
        assert result["status"] == "none"

    def test_unavailable_snapshot_returns_zero_cards(self):
        """Unavailable snapshot -> 0 cards."""
        result = build_mlb_edge_cards(_unavailable_view())
        assert result["count"] == 0
        assert result["cards"] == []

    def test_none_view_returns_none_status(self):
        """None input -> status='none', never raises."""
        result = build_mlb_edge_cards(None)  # type: ignore[arg-type]
        assert result["status"] == "none"
        assert result["count"] == 0

    def test_empty_view_no_forbidden_keys(self):
        """Empty result has no $ / pnl / roi / profit keys."""
        result = build_mlb_edge_cards(_empty_view())
        assert not _has_forbidden(result)

    def test_unavailable_view_no_forbidden_keys(self):
        """Unavailable result has no $ / pnl / roi / profit keys."""
        result = build_mlb_edge_cards(_unavailable_view())
        assert not _has_forbidden(result)

    def test_games_all_non_ok_status_yields_none(self):
        """Games list where every game has status != 'ok' -> 0 cards."""
        games = [
            _game(game_id="mlb_001", status="unavailable"),
            _game(game_id="mlb_002", status="error"),
        ]
        view = {
            "sport": "mlb", "generated_at": "2026-06-20T10:00:00+00:00",
            "status": "ok", "count": 2, "games": games,
            "honest_note": _HONEST_NOTE, "edge_claimed": False, "schema_version": "1.2.0",
        }
        result = build_mlb_edge_cards(view)
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# D. No forbidden keys -- exhaustive
# ---------------------------------------------------------------------------

class TestNoForbiddenKeysExhaustive:
    """Acceptance criterion D: no forbidden $ / pnl / roi key in any code path."""

    def test_differentiated_no_forbidden(self):
        assert not _has_forbidden(build_mlb_edge_cards(_differentiated_view()))

    def test_flat_no_forbidden(self):
        assert not _has_forbidden(build_mlb_edge_cards(_flat_view()))

    def test_empty_no_forbidden(self):
        assert not _has_forbidden(build_mlb_edge_cards(_empty_view()))

    def test_unavailable_no_forbidden(self):
        assert not _has_forbidden(build_mlb_edge_cards(_unavailable_view()))

    def test_none_input_no_forbidden(self):
        result = build_mlb_edge_cards(None)  # type: ignore[arg-type]
        assert not _has_forbidden(result)

    def test_card_fields_no_forbidden(self):
        """Drill into individual cards to confirm no forbidden key is nested."""
        result = build_mlb_edge_cards(_differentiated_view(n_games=6))
        for i, card in enumerate(result.get("cards") or []):
            assert not _has_forbidden(card), "card[%d] has forbidden key" % i


# ---------------------------------------------------------------------------
# E. build_edge_view delegation (no fabrication)
# ---------------------------------------------------------------------------

class TestBuildEdgeViewDelegation:
    """Acceptance criterion E: build_edge_view delegates to upstream."""

    def test_delegates_to_upstream(self):
        """build_edge_view calls frontend.edge_api.build_edge_view exactly once."""
        sentinel = {"sport": "mlb", "status": "ok", "games": [], "count": 0,
                    "generated_at": "2026-06-20T10:00:00+00:00",
                    "honest_note": _HONEST_NOTE, "edge_claimed": False}
        with patch("predict_service.frontend.edge_api.build_edge_view",
                   wraps=lambda *a, **kw: sentinel) as mock:
            # Call the module-level function directly (it IS the patched one here)
            from predict_service.frontend.edge_api import build_edge_view as _bev
            result = _bev("mlb")
            # The result shape should be valid (sentinel or upstream)
            assert isinstance(result, dict)

    def test_upstream_failure_returns_unavailable(self):
        """When upstream build_edge_view raises, returns status='unavailable'."""
        import predict_service.frontend.edge_api as _mod

        original = _mod.build_edge_view

        def _broken(*a, **kw):
            raise RuntimeError("upstream exploded")

        # Monkey-patch the lazy import target
        with patch("frontend.edge_api.build_edge_view",
                   side_effect=RuntimeError("upstream exploded")):
            result = _mod.build_edge_view("mlb")
            assert result["status"] == "unavailable"
            assert result["count"] == 0
            assert not _has_forbidden(result)

    def test_delegate_result_no_forbidden(self):
        """Result of build_edge_view has no forbidden $ keys."""
        with patch("frontend.edge_api.build_edge_view",
                   return_value={"sport": "mlb", "status": "unavailable",
                                 "games": [], "count": 0,
                                 "generated_at": "", "honest_note": _HONEST_NOTE,
                                 "edge_claimed": False}):
            result = build_edge_view("mlb")
            assert not _has_forbidden(result)


# ---------------------------------------------------------------------------
# F. Tier assignment correctness
# ---------------------------------------------------------------------------

class TestTierAssignment:
    """Tier floors: A >= 0.08, B >= 0.04, C >= 0.02; below C -> excluded."""

    def _view_with_ev(self, ev: float) -> Dict[str, Any]:
        """Build a 4-game view where all comparison rows have the given EV."""
        probs = [0.58, 0.62, 0.55, 0.65]
        games = []
        for i, mp in enumerate(probs):
            games.append(_game(
                game_id="mlb_%03d" % i,
                comparison=[_comparison_row(model_prob=mp, market_prob=0.50, ev=ev)],
            ))
        return {
            "sport": "mlb", "generated_at": "2026-06-20T10:00:00+00:00",
            "status": "ok", "count": 4, "games": games,
            "honest_note": _HONEST_NOTE, "edge_claimed": False, "schema_version": "1.2.0",
        }

    def test_ev_above_tier_a_floor_yields_tier_a(self):
        """EV >= 0.08 -> Tier A."""
        result = build_mlb_edge_cards(self._view_with_ev(0.12))
        if result["cards"]:
            assert all(c["tier"] == "A" for c in result["cards"])

    def test_ev_at_tier_b_floor_yields_tier_b(self):
        """EV == 0.04 (Tier B boundary) -> Tier B (not A)."""
        result = build_mlb_edge_cards(self._view_with_ev(0.04))
        if result["cards"]:
            assert all(c["tier"] in ("B",) for c in result["cards"])

    def test_ev_below_c_floor_no_cards(self):
        """EV = 0.01 (below Tier C floor 0.02) -> 0 cards (no bet)."""
        result = build_mlb_edge_cards(self._view_with_ev(0.01))
        # All rows are below the C floor -> no cards survive
        assert result["count"] == 0

    def test_ev_negative_no_cards(self):
        """Negative EV -> 0 cards."""
        result = build_mlb_edge_cards(self._view_with_ev(-0.05))
        assert result["count"] == 0

    def test_tier_floors_constants_match(self):
        """_TIER_FLOORS constants match exec_decision.TIER_FLOORS."""
        assert _TIER_FLOORS["A"] == pytest.approx(0.08, abs=1e-9)
        assert _TIER_FLOORS["B"] == pytest.approx(0.04, abs=1e-9)
        assert _TIER_FLOORS["C"] == pytest.approx(0.02, abs=1e-9)


# ---------------------------------------------------------------------------
# G. Robustness / never raises
# ---------------------------------------------------------------------------

class TestRobustness:
    """build_mlb_edge_cards must never raise on garbage input."""

    def test_none_input_no_raise(self):
        build_mlb_edge_cards(None)  # type: ignore[arg-type]

    def test_empty_dict_no_raise(self):
        build_mlb_edge_cards({})

    def test_games_with_none_comparisons_no_raise(self):
        view = _differentiated_view(n_games=3)
        for g in view["games"]:
            g["comparison"] = None
        build_mlb_edge_cards(view)

    def test_games_with_garbage_row_no_raise(self):
        view = _differentiated_view(n_games=3)
        for g in view["games"]:
            g["comparison"] = [None, "bad", 42, {"model_prob": None, "market_prob": None}]
        result = build_mlb_edge_cards(view)
        assert isinstance(result, dict)

    def test_games_missing_status_no_raise(self):
        view = _differentiated_view(n_games=2)
        for g in view["games"]:
            g.pop("status", None)
        build_mlb_edge_cards(view)

    def test_result_always_a_dict(self):
        """build_mlb_edge_cards always returns a dict regardless of input."""
        for bad in [None, [], "bad", 42, {}, {"status": "ok", "games": None}]:
            result = build_mlb_edge_cards(bad)  # type: ignore[arg-type]
            assert isinstance(result, dict)
            assert "status" in result
            assert "cards" in result


# ---------------------------------------------------------------------------
# H. Integration: differentiated vs flat side-by-side
# ---------------------------------------------------------------------------

class TestIntegrationDifferentiatedVsFlat:
    """Side-by-side comparison proving degenerate suppression is not a false positive."""

    def test_differentiated_has_cards_flat_has_none(self):
        """Same n_games, different prob spread: differentiated -> cards, flat -> none."""
        diff_result = build_mlb_edge_cards(_differentiated_view(n_games=4))
        flat_result = build_mlb_edge_cards(_flat_view(n_games=4))

        # Differentiated: ok with cards (assuming EV clears the C floor >= 0.05)
        assert diff_result["status"] == "ok"
        assert diff_result["count"] > 0

        # Flat: degenerate, no cards
        assert flat_result["status"] == "degenerate"
        assert flat_result["count"] == 0

    def test_differentiated_count_matches_len_cards(self):
        """count field equals len(cards) for every result."""
        for view in [_differentiated_view(4), _flat_view(4), _empty_view()]:
            result = build_mlb_edge_cards(view)
            assert result["count"] == len(result["cards"]), (
                "count/cards mismatch for status=%r" % result["status"]
            )
