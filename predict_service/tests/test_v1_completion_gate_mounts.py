"""predict_service.tests.test_v1_completion_gate_mounts -- BE7-1-v1-postgame-gate.

Acceptance criteria:
  V1. A completed-game payload (live.state='post' / game_state='post') on
      /api/v1/edges/{sport}/{game_id} yields decision=no_bet, tier=None,
      stake_units absent/0, and freshness stale (suppressed=True).
  V2. A completed-game payload on /api/v1/edges/{sport} (sport-level) yields
      the same suppression on that game's entry; pregame entry untouched.
  V3. A completed-game payload on /api/v1/bestbets/{sport}/{game_id} yields
      decision=no_bet, tier=None, stake_units=0, best_bets=[].
  V4. A completed-game payload on /api/v1/bestbets/{sport} (sport-level) same;
      pregame entry retains its best_bets.
  V5. A pregame payload passes through UNCHANGED on /api/v1/edges/{sport}/{game_id}.
  V6. A pregame payload passes through UNCHANGED on /api/v1/bestbets/{sport}/{game_id}.
  V7. No $/pnl/roi/profit KEY (not value) appears anywhere in any response.
  V8. The gated routes are registered BEFORE the un-gated routers so first-match
      wins: gated handler fires (suppression present on completed game).

Run (per-file only):
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest predict_service/tests/test_v1_completion_gate_mounts.py -q
"""
from __future__ import annotations

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch, MagicMock

import pytest

# Ensure repo root on sys.path.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

from predict_service.v1_completion_gate_mounts import register


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

_SPORT = "nba"
_POST_GAME_ID = "401859967"   # Completed game (6 days past, Finals)
_PRE_GAME_ID = "401999001"    # Future pregame

_HONEST_NOTE_STUB = "Calibrated decision-support only."
_DECISION_NOTE_STUB = "Units only, no dollar field."


def _post_game_edge_view() -> Dict[str, Any]:
    """build_game_edge-shaped dict for a COMPLETED game (game_state='post')."""
    return {
        "sport": _SPORT,
        "game_id": _POST_GAME_ID,
        "home": "NYK",
        "away": "SAS",
        "tipoff": "2026-06-12T23:30:00+00:00",
        "game_state": "post",
        "status": "ok",
        "decision": "bet",
        "stake_units": 1.5,
        "tier": "A",
        "ev": 0.12,
        "model_prob": 0.62,
        "market_prob": 0.50,
        "freshness": {
            "status": "fresh", "ok": True, "fresh": True, "stale": False,
        },
        "comparison": [
            {
                "market_type": "moneyline", "side": "home",
                "model_prob": 0.62, "market_prob": 0.50,
                "best_book": "DraftKings", "best_odds": 1.95,
                "tier": "A", "ev": 0.12, "decision": "bet",
                "stake_units": 1.5, "flat_unit": 1.0, "kelly_units": 0.5,
                "clv_is_proxy": False,
            }
        ],
        "generated_at": "2026-06-18T04:00:00+00:00",
        "honest_note": _HONEST_NOTE_STUB,
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _pre_game_edge_view() -> Dict[str, Any]:
    """build_game_edge-shaped dict for a FUTURE pregame."""
    return {
        "sport": _SPORT,
        "game_id": _PRE_GAME_ID,
        "home": "NYK",
        "away": "BOS",
        "tipoff": "2026-10-01T23:30:00+00:00",
        "game_state": "pre",
        "status": "ok",
        "decision": "bet",
        "stake_units": 1.25,
        "tier": "B",
        "ev": 0.07,
        "model_prob": 0.60,
        "market_prob": 0.52,
        "freshness": {
            "status": "fresh", "ok": True, "fresh": True, "stale": False,
        },
        "comparison": [
            {
                "market_type": "moneyline", "side": "home",
                "model_prob": 0.60, "market_prob": 0.52,
                "best_book": "FanDuel", "best_odds": 1.88,
                "tier": "B", "ev": 0.07, "decision": "bet",
                "stake_units": 1.25, "flat_unit": 1.0, "kelly_units": 0.25,
                "clv_is_proxy": False,
            }
        ],
        "generated_at": "2026-06-18T04:00:00+00:00",
        "honest_note": _HONEST_NOTE_STUB,
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _sport_edge_view() -> Dict[str, Any]:
    """build_edge_view response containing one post game and one pre game."""
    return {
        "sport": _SPORT,
        "generated_at": "2026-06-18T04:00:00+00:00",
        "status": "ok",
        "count": 2,
        "games": [_post_game_edge_view(), _pre_game_edge_view()],
        "honest_note": _HONEST_NOTE_STUB,
        "edge_claimed": False,
        "schema_version": "1.2.0",
    }


def _post_decided() -> Dict[str, Any]:
    """decide_game output for the post game."""
    return {
        "game_id": _POST_GAME_ID,
        "home": "NYK",
        "away": "SAS",
        "tipoff": "2026-06-12T23:30:00+00:00",
        "game_state": "post",
        "status": "ok",
        "candidates": [
            {
                "market_type": "moneyline", "side": "home",
                "tier": "A", "ev": 0.12, "decision": "bet",
                "stake_units": 1.5, "flat_unit": 1.0, "kelly_units": 0.5,
            }
        ],
        "best_bets": [
            {
                "market_type": "moneyline", "side": "home",
                "tier": "A", "ev": 0.12, "decision": "bet",
                "stake_units": 1.5, "flat_unit": 1.0, "kelly_units": 0.5,
            }
        ],
    }


def _pre_decided() -> Dict[str, Any]:
    """decide_game output for the pre game."""
    return {
        "game_id": _PRE_GAME_ID,
        "home": "NYK",
        "away": "BOS",
        "tipoff": "2026-10-01T23:30:00+00:00",
        "game_state": "pre",
        "status": "ok",
        "candidates": [
            {
                "market_type": "moneyline", "side": "home",
                "tier": "B", "ev": 0.07, "decision": "bet",
                "stake_units": 1.25, "flat_unit": 1.0, "kelly_units": 0.25,
            }
        ],
        "best_bets": [
            {
                "market_type": "moneyline", "side": "home",
                "tier": "B", "ev": 0.07, "decision": "bet",
                "stake_units": 1.25, "flat_unit": 1.0, "kelly_units": 0.25,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Patch context: active for the duration of the TestClient call
# ---------------------------------------------------------------------------

class _GatedAppCtx:
    """Context manager: builds a gated FastAPI app and keeps stubs active.

    Usage::
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get("/api/v1/edges/nba/401859967")
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self.client: TestClient

    def __enter__(self) -> "_GatedAppCtx":
        post = _post_game_edge_view()
        pre = _pre_game_edge_view()
        sport = _sport_edge_view()
        post_dec = _post_decided()
        pre_dec = _pre_decided()

        _dec_map = {_POST_GAME_ID: post_dec, _PRE_GAME_ID: pre_dec}

        def _fake_build_game_edge(sp, gid, store_out_dir=None):
            if gid == _POST_GAME_ID:
                return post
            if gid == _PRE_GAME_ID:
                return pre
            return {"status": "unavailable", "game_id": gid, "reason": "unknown"}

        def _fake_build_edge_view(sp, store_out_dir=None):
            return sport

        def _fake_decide_game(game):
            gid = (game or {}).get("game_id")
            return _dec_map.get(gid, game)

        # Activate patches and keep them alive in the ExitStack.
        self._stack.enter_context(
            patch("frontend.edge_api.build_game_edge",
                  side_effect=_fake_build_game_edge))
        self._stack.enter_context(
            patch("frontend.edge_api.build_edge_view",
                  side_effect=_fake_build_edge_view))
        self._stack.enter_context(
            patch("frontend.exec_decision.decide_game",
                  side_effect=_fake_decide_game))
        self._stack.enter_context(
            patch("frontend.exec_decision.decision_note",
                  return_value=_DECISION_NOTE_STUB))
        self._stack.enter_context(
            patch("predict_service.contracts.HONEST_NOTE",
                  _HONEST_NOTE_STUB))

        app = FastAPI()
        register(app)
        self.client = TestClient(app, raise_server_exceptions=True)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stack.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_money_key(obj: Any) -> bool:
    """Scan any nested dict/list for $ / pnl / profit / roi / bankroll KEYS only.

    Only inspects dict keys -- string values (like 'no $ edge claimed' in
    honest_note) are intentional narrative text and NOT violations.
    """
    _BANNED = {"$", "pnl", "profit", "roi", "bankroll", "dollar", "dollars"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(b == str(k).lower().strip() for b in _BANNED):
                return True
            if _has_money_key(v):
                return True
    if isinstance(obj, list):
        return any(_has_money_key(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# V1 -- completed game on /api/v1/edges/{sport}/{game_id}
# ---------------------------------------------------------------------------

class TestEdgesGameCompleted:
    def test_v1_edges_completed_decision_no_bet(self):
        """V1: completed game on /api/v1/edges/{sport}/{game_id} -> decision=no_bet."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("decision") == "no_bet", (
            "V1: completed game decision must be no_bet; got %r" % body.get("decision")
        )

    def test_v1_edges_completed_tier_none(self):
        """V1: completed game -> tier=None."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert body.get("tier") is None, (
            "V1: completed game tier must be None; got %r" % body.get("tier")
        )

    def test_v1_edges_completed_stake_units_absent(self):
        """V1: completed game -> stake_units removed."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert "stake_units" not in body, (
            "V1: stake_units must be absent on completed game edge"
        )

    def test_v1_edges_completed_freshness_stale(self):
        """V1: completed game -> freshness.status=stale."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        freshness = body.get("freshness") or {}
        assert freshness.get("status") == "stale", (
            "V1: freshness.status must be stale; got %r" % freshness.get("status")
        )

    def test_v1_edges_completed_suppressed(self):
        """V1: completed game -> suppressed=True."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert body.get("suppressed") is True, "V1: suppressed must be True"


# ---------------------------------------------------------------------------
# V2 -- completed game within /api/v1/edges/{sport} (sport-level)
# ---------------------------------------------------------------------------

class TestEdgesSportCompleted:
    def test_v2_sport_completed_game_suppressed(self):
        """V2: /api/v1/edges/{sport} -- completed game entry is suppressed."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}")
        assert resp.status_code == 200
        body = resp.json()
        games: List[Dict[str, Any]] = body.get("games") or []
        post = next((g for g in games if g.get("game_id") == _POST_GAME_ID), None)
        assert post is not None, "V2: completed game must be present in games list"
        assert post.get("decision") == "no_bet", (
            "V2: completed game decision must be no_bet; got %r" % post.get("decision")
        )
        assert post.get("suppressed") is True, "V2: suppressed must be True"
        assert post.get("tier") is None, "V2: tier must be None"

    def test_v2_sport_pre_game_unchanged(self):
        """V2: /api/v1/edges/{sport} -- pregame entry is NOT suppressed."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}")
        body = resp.json()
        games = body.get("games") or []
        pre = next((g for g in games if g.get("game_id") == _PRE_GAME_ID), None)
        assert pre is not None, "V2: pregame must be present in games list"
        assert not pre.get("suppressed"), (
            "V2: pregame must NOT be suppressed; suppressed=%r" % pre.get("suppressed")
        )


# ---------------------------------------------------------------------------
# V3 -- completed game on /api/v1/bestbets/{sport}/{game_id}
# ---------------------------------------------------------------------------

class TestBestbetsGameCompleted:
    def test_v3_bestbets_completed_decision_no_bet(self):
        """V3: /api/v1/bestbets/{sport}/{game_id} completed -> decision=no_bet."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("decision") == "no_bet", (
            "V3: completed game decision must be no_bet; got %r" % body.get("decision")
        )

    def test_v3_bestbets_completed_tier_none(self):
        """V3: completed bestbet -> tier=None."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert body.get("tier") is None, (
            "V3: tier must be None on completed game; got %r" % body.get("tier")
        )

    def test_v3_bestbets_completed_stake_units_zero(self):
        """V3: completed bestbet -> stake_units=0."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert body.get("stake_units") == 0, (
            "V3: stake_units must be 0 on completed game; got %r"
            % body.get("stake_units")
        )

    def test_v3_bestbets_completed_best_bets_empty(self):
        """V3: completed bestbet -> best_bets=[]."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        assert body.get("best_bets") == [], (
            "V3: best_bets must be [] on completed game; got %r"
            % body.get("best_bets")
        )

    def test_v3_bestbets_completed_freshness_stale(self):
        """V3: completed bestbet -> freshness.status=stale."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}")
        body = resp.json()
        freshness = body.get("freshness") or {}
        assert freshness.get("status") == "stale", (
            "V3: freshness.status must be stale; got %r" % freshness.get("status")
        )


# ---------------------------------------------------------------------------
# V4 -- completed game within /api/v1/bestbets/{sport}
# ---------------------------------------------------------------------------

class TestBestbetsSportCompleted:
    def test_v4_sport_completed_game_suppressed(self):
        """V4: /api/v1/bestbets/{sport} -- completed game zeroed out."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}")
        assert resp.status_code == 200
        body = resp.json()
        games = body.get("games") or []
        post = next((g for g in games if g.get("game_id") == _POST_GAME_ID), None)
        assert post is not None, "V4: completed game must be in games list"
        assert post.get("decision") == "no_bet", "V4: decision must be no_bet"
        assert post.get("tier") is None, "V4: tier must be None"
        assert post.get("stake_units") == 0, "V4: stake_units must be 0"
        assert post.get("best_bets") == [], "V4: best_bets must be []"

    def test_v4_sport_pre_game_has_bets(self):
        """V4: /api/v1/bestbets/{sport} -- pregame entry keeps its best_bets."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}")
        body = resp.json()
        games = body.get("games") or []
        pre = next((g for g in games if g.get("game_id") == _PRE_GAME_ID), None)
        assert pre is not None, "V4: pregame must be in games list"
        assert not pre.get("suppressed"), "V4: pregame must NOT be suppressed"
        assert len(pre.get("best_bets") or []) > 0, (
            "V4: pregame best_bets should be non-empty"
        )


# ---------------------------------------------------------------------------
# V5/V6 -- pregame passes through unchanged
# ---------------------------------------------------------------------------

class TestPregamePassthrough:
    def test_v5_edges_pregame_not_suppressed(self):
        """V5: pregame on /api/v1/edges/{sport}/{game_id} not suppressed."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/edges/{_SPORT}/{_PRE_GAME_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert not body.get("suppressed"), (
            "V5: pregame must NOT be suppressed; suppressed=%r"
            % body.get("suppressed")
        )
        assert body.get("decision") != "no_bet", (
            "V5: pregame decision must not be forced no_bet; got %r"
            % body.get("decision")
        )

    def test_v6_bestbets_pregame_has_bets(self):
        """V6: pregame on /api/v1/bestbets/{sport}/{game_id} has best_bets."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(f"/api/v1/bestbets/{_SPORT}/{_PRE_GAME_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert not body.get("suppressed"), "V6: pregame must NOT be suppressed"
        assert body.get("best_bets") != [], (
            "V6: pregame best_bets should not be empty"
        )


# ---------------------------------------------------------------------------
# V7 -- no $ / pnl / roi / profit KEY in any response
# ---------------------------------------------------------------------------

class TestNoDollarKey:
    @pytest.mark.parametrize("path", [
        f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}",
        f"/api/v1/edges/{_SPORT}/{_PRE_GAME_ID}",
        f"/api/v1/edges/{_SPORT}",
        f"/api/v1/bestbets/{_SPORT}/{_POST_GAME_ID}",
        f"/api/v1/bestbets/{_SPORT}/{_PRE_GAME_ID}",
        f"/api/v1/bestbets/{_SPORT}",
    ])
    def test_v7_no_dollar_key(self, path: str):
        """V7: no $ / pnl / roi / profit KEY in any v1 gated response (keys only)."""
        with _GatedAppCtx() as ctx:
            resp = ctx.client.get(path)
        body = resp.json()
        assert not _has_money_key(body), (
            "V7: money KEY (pnl/roi/profit/bankroll) found in response to %r" % path
        )


# ---------------------------------------------------------------------------
# V8 -- first-match ordering: gated handler fires before the un-gated router
# ---------------------------------------------------------------------------

class TestFirstMatchOrdering:
    def test_v8_gated_handler_fires_for_completed_game(self):
        """V8: register() before include_router -> gated handler fires on completed game."""
        # Build app: register gated THEN add a trivial un-gated route at same path.
        # The gated handler must win (first-match).
        app = FastAPI()

        post = _post_game_edge_view()
        pre = _pre_game_edge_view()

        def _fake_build_game_edge(sp, gid, store_out_dir=None):
            return post if gid == _POST_GAME_ID else pre

        def _fake_build_edge_view(sp, store_out_dir=None):
            return _sport_edge_view()

        def _fake_decide_game(game):
            gid = (game or {}).get("game_id")
            return _post_decided() if gid == _POST_GAME_ID else _pre_decided()

        stack = ExitStack()
        stack.enter_context(
            patch("frontend.edge_api.build_game_edge",
                  side_effect=_fake_build_game_edge))
        stack.enter_context(
            patch("frontend.edge_api.build_edge_view",
                  side_effect=_fake_build_edge_view))
        stack.enter_context(
            patch("frontend.exec_decision.decide_game",
                  side_effect=_fake_decide_game))
        stack.enter_context(
            patch("frontend.exec_decision.decision_note",
                  return_value=_DECISION_NOTE_STUB))
        stack.enter_context(
            patch("predict_service.contracts.HONEST_NOTE",
                  _HONEST_NOTE_STUB))

        register(app)  # gated routes FIRST

        # Now add a conflicting no-gate route at the same path (simulating the
        # un-gated router being include_router'd after register()).
        @app.get("/api/v1/edges/{sport}/{game_id}")  # noqa: F811
        def _ungated(sport: str, game_id: str) -> dict:
            return {"decision": "bet", "tier": "A", "gated": False}

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(f"/api/v1/edges/{_SPORT}/{_POST_GAME_ID}")
        stack.close()

        body = resp.json()
        # The GATED handler should have run -> suppression present or no_bet.
        assert body.get("suppressed") is True or body.get("decision") == "no_bet", (
            "V8: gated handler must win first-match; got decision=%r suppressed=%r"
            % (body.get("decision"), body.get("suppressed"))
        )
        # The un-gated stub's 'gated=False' marker must NOT be present.
        assert body.get("gated") is not False, (
            "V8: un-gated stub handler must not have won"
        )
