"""Per-file test: contract validation for the execution-dashboard API shapes.

Validates the exact JSON shapes the ExecutionGrid / EdgeCard / PlaceBetButton
/ OpenBetsPanel components consume:

  * GET /api/v1/edges/{sport}     -- EdgeView envelope shape + deep game objects.
  * GET /api/v1/edges/{sport}/{game_id} -- single-game deep edge object.
  * POST /api/paper/place         -- place request/response shape.
  * GET /api/paper/open           -- open bets list.

Honesty invariants (all checked recursively on every response body):
  - NO key containing $, dollar, roi, pnl, profit, bankroll.
  - edge_claimed is always False (where present).
  - executed is always False on every bet row.
  - No fabricated comparison row for a market with no devigged_prob.

Setup strategy: two bare FastAPI mini-apps (isolating edge_routes and
exec_routes), with store either stubbed via ?store_dir= query param (edge routes)
or monkeypatched (exec routes).  This mirrors the patterns already used in
test_edge_routes.py and test_exec_routes.py.

Run: python -m pytest tests/frontend/test_exec_ui_contract.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GID = "0042500401"
_GID2 = "0042500402"
_BOOK = "espn:DK"
_DEC = 1.80          # taken_decimal -- must match what we put in the envelope
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "bankroll")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_forbidden(obj: Any, path: str = "") -> None:
    """Recursively assert no forbidden money-field KEY appears in any JSON object."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, (
                    "forbidden key %r (matches %r) found at path %r" % (k, bad, path)
                )
            _no_forbidden(v, path + "." + str(k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _no_forbidden(item, path + "[%d]" % i)


def _walk_bets(obj: Any) -> list:
    """Collect every dict node that carries an 'executed' key (bet rows)."""
    out = []
    if isinstance(obj, dict):
        if "executed" in obj:
            out.append(obj)
        for v in obj.values():
            out.extend(_walk_bets(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_walk_bets(item))
    return out


# ---------------------------------------------------------------------------
# Test envelope factory
# ---------------------------------------------------------------------------

def _make_envelope(game_ids: list) -> SnapshotEnvelope:
    predictions, markets, edges = [], [], []
    for gid in game_ids:
        mkt_home = MarketRow(
            sport=_SPORT, game_id=gid, market_type="moneyline",
            side="home", line=None, odds=_DEC, book=_BOOK,
            devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
            is_close=False, clv_is_proxy=True,
        )
        mkt_away = MarketRow(
            sport=_SPORT, game_id=gid, market_type="moneyline",
            side="away", line=None, odds=2.10, book=_BOOK,
            devigged_prob=0.43, captured_at="2026-06-18T22:00:00+00:00",
            is_close=False, clv_is_proxy=True,
        )
        rec = PredictionRecord(
            sport=_SPORT, game_id=gid,
            home="Boston Celtics", away="New York Knicks",
            tipoff="2026-06-18T23:30:00+00:00",
            pregame_probs={"home_ml": 0.60, "away_ml": 0.40},
            markets=[mkt_home, mkt_away],
            leak_guard={"in_sample": False},
        )
        edge = EdgeRow(
            game_id=gid, market_type="moneyline", side="home",
            model_prob=0.60, market_prob=0.57, ev=0.08, tier="B",
            book=_BOOK, line=None, clv_is_proxy=True,
        )
        predictions.append(rec)
        markets.extend([mkt_home, mkt_away])
        edges.append(edge)
    from datetime import datetime, timezone
    return SnapshotEnvelope(
        sport=_SPORT,
        # Fresh generated_at so the exec_routes freshness gate (P0-6) passes; the
        # gate rejects a stale snapshot, which is exercised in test_exec_routes.
        generated_at=datetime.now(timezone.utc).isoformat(),
        status="ok",
        predictions=predictions,
        markets=markets,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Fixtures -- edge_routes (bare mini-app + ?store_dir= param)
# ---------------------------------------------------------------------------

@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """Write the test envelope to tmp_path; stub freshness to deterministic."""
    import frontend.edge_api as _edge_api  # noqa: PLC0415
    env = _make_envelope([_GID, _GID2])
    store.save(env, out_dir=tmp_path, append=False)
    monkeypatch.setattr(
        _edge_api, "_freshness",
        lambda *a, **k: {"status": "fresh", "age_sec": 60.0},
    )
    return tmp_path


@pytest.fixture()
def edge_client(store_dir):
    """Bare FastAPI app with only edge_routes mounted; store via ?store_dir=."""
    import frontend.edge_routes as _er  # noqa: PLC0415
    app = FastAPI()
    app.include_router(_er.router)
    return TestClient(app)


def _sd(store_dir: Path) -> str:
    """Query param value for store_dir."""
    return str(store_dir)


# ---------------------------------------------------------------------------
# Fixtures -- exec_routes (bare mini-app + monkeypatched store)
# ---------------------------------------------------------------------------

def _exec_envelope() -> SnapshotEnvelope:
    return _make_envelope([_GID])


@pytest.fixture()
def exec_client(monkeypatch):
    """Bare FastAPI app with only exec_routes mounted; store is monkeypatched."""
    import frontend.exec_routes as _xr  # noqa: PLC0415
    monkeypatch.setattr(
        _xr.store, "read_latest",
        lambda sport, *a, **k: (
            _exec_envelope() if str(sport).lower() == _SPORT
            else SnapshotEnvelope.unavailable(sport)
        ),
    )
    app = FastAPI()
    app.include_router(_xr.router)
    return TestClient(app)


@pytest.fixture()
def ledger_path(tmp_path):
    return str(tmp_path / "ledger_test.jsonl")


# ===========================================================================
# GET /api/v1/edges/{sport} -- EdgeView envelope
# ===========================================================================

class TestEdgeViewEnvelope:
    """EdgeView must conform to the shape ExecutionGrid reads."""

    def test_status_200(self, edge_client, store_dir):
        r = edge_client.get("/api/v1/edges/%s" % _SPORT,
                            params={"store_dir": _sd(store_dir)})
        assert r.status_code == 200

    def test_top_level_keys(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        for key in ("sport", "generated_at", "status", "count", "games",
                    "honest_note", "edge_note", "edge_claimed", "schema_version"):
            assert key in body, "missing top-level key %r" % key

    def test_status_ok(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["status"] == "ok"

    def test_edge_claimed_false(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["edge_claimed"] is False

    def test_count_matches_games(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["count"] == len(body["games"])
        assert body["count"] == 2

    def test_honest_note_non_empty(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["honest_note"]
        assert body["edge_note"]

    def test_no_forbidden_keys(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        _no_forbidden(body)

    def test_games_is_list_of_objects(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert isinstance(body["games"], list)
        for g in body["games"]:
            assert isinstance(g, dict)

    def test_unavailable_sport_sentinel(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/tennis",
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["status"] == "unavailable"
        assert body.get("games", []) == []
        assert body["edge_claimed"] is False
        _no_forbidden(body)


# ===========================================================================
# DEEP GAME OBJECT shape (inside games[])
# ===========================================================================

class TestDeepGameObjectShape:
    """Per-game object shape: what EdgeCard reads."""

    def _game(self, edge_client, store_dir) -> dict:
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        return body["games"][0]

    def test_required_top_level_keys(self, edge_client, store_dir):
        g = self._game(edge_client, store_dir)
        for key in ("sport", "game_id", "home", "away", "tipoff", "status",
                    "model", "markets", "comparison", "freshness", "as_of"):
            assert key in g, "missing game key %r" % key

    def test_status_ok(self, edge_client, store_dir):
        assert self._game(edge_client, store_dir)["status"] == "ok"

    def test_model_shape(self, edge_client, store_dir):
        m = self._game(edge_client, store_dir)["model"]
        assert "probs" in m and "leak_guard" in m
        assert isinstance(m["probs"], dict)
        assert "in_sample" in m["leak_guard"]
        assert m["leak_guard"]["in_sample"] is False

    def test_model_probs_not_empty(self, edge_client, store_dir):
        probs = self._game(edge_client, store_dir)["model"]["probs"]
        assert len(probs) >= 1

    def test_markets_is_list(self, edge_client, store_dir):
        assert isinstance(self._game(edge_client, store_dir)["markets"], list)

    def test_every_market_has_required_keys(self, edge_client, store_dir):
        for m in self._game(edge_client, store_dir)["markets"]:
            for key in ("market_type", "side", "book", "odds",
                        "devigged_prob", "is_close", "clv_is_proxy"):
                assert key in m, "missing market key %r" % key

    def test_comparison_is_list(self, edge_client, store_dir):
        assert isinstance(self._game(edge_client, store_dir)["comparison"], list)

    def test_comparison_row_shape(self, edge_client, store_dir):
        for row in self._game(edge_client, store_dir)["comparison"]:
            for key in ("market_type", "side", "model_prob", "market_prob",
                        "best_book", "best_odds", "line", "edge", "ev", "tier",
                        "clv_is_proxy"):
                assert key in row, "missing comparison key %r" % key

    def test_comparison_no_fabricated_market_prob(self, edge_client, store_dir):
        """market_prob must come from a real devigged_prob; no fabrication."""
        for row in self._game(edge_client, store_dir)["comparison"]:
            assert row["market_prob"] is not None, (
                "market_prob must not be None; a row with no devigged quote "
                "must be absent"
            )

    def test_edge_is_model_minus_market_or_null(self, edge_client, store_dir):
        """edge = model_prob - market_prob (or null when model_prob absent)."""
        for row in self._game(edge_client, store_dir)["comparison"]:
            if row["model_prob"] is not None:
                expected = round(
                    float(row["model_prob"]) - float(row["market_prob"]), 9
                )
                actual = round(float(row["edge"]), 9)
                assert abs(expected - actual) < 1e-6, (
                    "edge mismatch: expected ~%s got %s" % (expected, actual)
                )
            else:
                assert row["edge"] is None

    def test_no_dollar_edge_key_in_comparison(self, edge_client, store_dir):
        for row in self._game(edge_client, store_dir)["comparison"]:
            for key in row:
                assert "$" not in key.lower() and "dollar" not in key.lower()

    def test_freshness_shape(self, edge_client, store_dir):
        f = self._game(edge_client, store_dir)["freshness"]
        assert "status" in f
        assert f["status"] in ("fresh", "stale", "unknown")

    def test_no_forbidden_in_game(self, edge_client, store_dir):
        _no_forbidden(self._game(edge_client, store_dir))


# ===========================================================================
# GET /api/v1/edges/{sport}/{game_id} -- single-game deep edge
# ===========================================================================

class TestSingleGameEdge:
    """build_game_edge: same shape + hoisted top-level fields."""

    def test_status_200(self, edge_client, store_dir):
        r = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                            params={"store_dir": _sd(store_dir)})
        assert r.status_code == 200

    def test_ok_status(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["status"] == "ok"

    def test_top_level_hoisted_fields(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        for key in ("generated_at", "honest_note", "edge_note",
                    "edge_claimed", "schema_version"):
            assert key in body, "missing hoisted key %r" % key

    def test_edge_claimed_false(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["edge_claimed"] is False

    def test_game_id_matches(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["game_id"] == _GID

    def test_unknown_game_id_sentinel(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/DOES_NOT_EXIST" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body["status"] == "unavailable"
        assert body["edge_claimed"] is False
        _no_forbidden(body)

    def test_no_forbidden_keys(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        _no_forbidden(body)


# ===========================================================================
# POST /api/paper/place -- place request/response shape
# ===========================================================================

class TestPaperPlaceContract:
    """POST /api/paper/place: validation rules + response shape."""

    def _place(self, exec_client, ledger_path, **overrides):
        payload = dict(
            sport=_SPORT, game_id=_GID,
            market_type="moneyline", side="home",
            book=_BOOK, taken_decimal=_DEC,
        )
        payload.update(overrides)
        return exec_client.post(
            "/api/paper/place",
            json=payload,
            params={"ledger": ledger_path},
        )

    # -- 422 field validation -------------------------------------------------

    def test_missing_sport_422(self, exec_client, ledger_path):
        r = exec_client.post(
            "/api/paper/place",
            json={"game_id": _GID, "market_type": "moneyline",
                  "side": "home", "book": _BOOK, "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        )
        assert r.status_code == 422

    def test_taken_decimal_le1_422(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path, taken_decimal=0.95)
        assert r.status_code == 422

    def test_taken_decimal_eq1_422(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path, taken_decimal=1.0)
        assert r.status_code == 422

    def test_missing_book_422(self, exec_client, ledger_path):
        r = exec_client.post(
            "/api/paper/place",
            json={"sport": _SPORT, "game_id": _GID,
                  "market_type": "moneyline", "side": "home",
                  "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        )
        assert r.status_code == 422

    # -- 400 line validation --------------------------------------------------

    def test_wrong_price_rejected_400(self, exec_client, ledger_path):
        """A stale/fabricated price not in the store must be rejected 400."""
        r = self._place(exec_client, ledger_path, taken_decimal=2.99)
        assert r.status_code == 400
        assert r.json()["status"] == "rejected"

    def test_unknown_sport_rejected_400(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path, sport="tennis")
        assert r.status_code == 400
        assert r.json()["status"] == "rejected"

    def test_unknown_game_id_rejected_400(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path, game_id="DOES_NOT_EXIST")
        assert r.status_code == 400
        assert r.json()["status"] == "rejected"

    def test_wrong_book_rejected_400(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path, book="fabricated:book")
        assert r.status_code == 400
        assert r.json()["status"] == "rejected"

    # -- 200 happy path -------------------------------------------------------

    def test_valid_place_200(self, exec_client, ledger_path):
        r = self._place(exec_client, ledger_path)
        assert r.status_code == 200

    def test_valid_response_shape(self, exec_client, ledger_path):
        body = self._place(exec_client, ledger_path).json()
        assert body["status"] == "ok"
        assert "idempotent" in body
        assert "bet" in body
        assert "honest_note" in body

    def test_bet_row_shape(self, exec_client, ledger_path):
        bet = self._place(exec_client, ledger_path).json()["bet"]
        for key in ("sport", "game_id", "matchup", "market_type", "side",
                    "taken_book", "taken_decimal", "model_prob", "model_ev",
                    "tier", "stake_units", "channel", "idem_key",
                    "status", "executed", "ts"):
            assert key in bet, "missing bet row key %r" % key

    def test_executed_always_false(self, exec_client, ledger_path):
        bet = self._place(exec_client, ledger_path).json()["bet"]
        assert bet["executed"] is False

    def test_channel_is_paper_manual(self, exec_client, ledger_path):
        bet = self._place(exec_client, ledger_path).json()["bet"]
        assert bet["channel"] == "paper_manual"

    def test_no_forbidden_keys_in_response(self, exec_client, ledger_path):
        body = self._place(exec_client, ledger_path).json()
        _no_forbidden(body)

    def test_model_ev_is_probability_space(self, exec_client, ledger_path):
        """model_ev = model_prob * taken_decimal - 1 (never a dollar amount)."""
        body = self._place(exec_client, ledger_path).json()
        bet = body["bet"]
        if bet["model_prob"] is not None and bet["taken_decimal"] is not None:
            expected = round(
                float(bet["model_prob"]) * float(bet["taken_decimal"]) - 1.0, 4
            )
            actual = round(float(bet["model_ev"]), 4)
            assert abs(expected - actual) < 0.01, (
                "model_ev mismatch: expected ~%s got %s" % (expected, actual)
            )

    def test_stake_units_is_numeric_not_dollar(self, exec_client, ledger_path):
        """stake_units is a unit sizing (not a dollar amount)."""
        bet = self._place(exec_client, ledger_path).json()["bet"]
        assert isinstance(bet["stake_units"], (int, float))
        # flat_unit=1.0 + optional quarter-kelly; always >= 1.0
        assert float(bet["stake_units"]) >= 1.0

    # -- idempotency ----------------------------------------------------------

    def test_second_place_same_day_idempotent(self, exec_client, ledger_path):
        self._place(exec_client, ledger_path)
        r2 = self._place(exec_client, ledger_path)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["idempotent"] is True
        assert body2["bet"]["executed"] is False
        _no_forbidden(body2)

    def test_first_place_not_idempotent(self, exec_client, ledger_path):
        body = self._place(exec_client, ledger_path).json()
        assert body["idempotent"] is False


# ===========================================================================
# GET /api/paper/open -- open bets list
# ===========================================================================

class TestPaperOpenContract:
    """GET /api/paper/open: shape what OpenBetsPanel reads."""

    def test_status_200(self, exec_client):
        r = exec_client.get("/api/paper/open",
                            params={"ledger": "/nonexistent.jsonl"})
        assert r.status_code == 200

    def test_empty_ledger_shape(self, exec_client):
        body = exec_client.get("/api/paper/open",
                               params={"ledger": "/nonexistent.jsonl"}).json()
        assert body["status"] == "ok"
        assert body["count"] == 0
        assert body["open"] == []
        assert "honest_note" in body

    def test_after_place_open_contains_bet(self, exec_client, ledger_path):
        exec_client.post(
            "/api/paper/place",
            json={"sport": _SPORT, "game_id": _GID,
                  "market_type": "moneyline", "side": "home",
                  "book": _BOOK, "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        )
        body = exec_client.get("/api/paper/open",
                               params={"ledger": ledger_path}).json()
        assert body["status"] == "ok"
        assert body["count"] >= 1
        for row in body["open"]:
            assert str(row.get("status", "open")).lower() == "open"

    def test_open_bets_all_executed_false(self, exec_client, ledger_path):
        exec_client.post(
            "/api/paper/place",
            json={"sport": _SPORT, "game_id": _GID,
                  "market_type": "moneyline", "side": "home",
                  "book": _BOOK, "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        )
        body = exec_client.get("/api/paper/open",
                               params={"ledger": ledger_path}).json()
        for row in _walk_bets(body):
            assert row.get("executed") is False

    def test_no_forbidden_keys_in_open(self, exec_client, ledger_path):
        body = exec_client.get("/api/paper/open",
                               params={"ledger": ledger_path}).json()
        _no_forbidden(body)

    def test_sport_filter_works(self, exec_client, ledger_path):
        """Sport filter must return only rows for the requested sport."""
        body = exec_client.get("/api/paper/open",
                               params={"ledger": ledger_path,
                                       "sport": "tennis"}).json()
        for row in body["open"]:
            assert row.get("sport", "").lower() == "tennis"


# ===========================================================================
# Cross-endpoint: executed=False invariant across all bet-carrying responses
# ===========================================================================

class TestExecutedFalseInvariant:
    """executed MUST be False on every bet row in every endpoint."""

    def _do_place(self, exec_client, ledger_path):
        return exec_client.post(
            "/api/paper/place",
            json={"sport": _SPORT, "game_id": _GID,
                  "market_type": "moneyline", "side": "home",
                  "book": _BOOK, "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        )

    def test_place_response_executed_false(self, exec_client, ledger_path):
        body = self._do_place(exec_client, ledger_path).json()
        for bet in _walk_bets(body):
            assert bet["executed"] is False

    def test_open_response_executed_false(self, exec_client, ledger_path):
        self._do_place(exec_client, ledger_path)
        body = exec_client.get("/api/paper/open",
                               params={"ledger": ledger_path}).json()
        for bet in _walk_bets(body):
            assert bet["executed"] is False


# ===========================================================================
# Honesty: no $ / money-fabrication anywhere in edge responses
# ===========================================================================

class TestEdgeViewHonestyInvariants:
    """End-to-end honesty scan: no forbidden keys, edge_claimed=False everywhere."""

    def test_sport_edge_view_no_forbidden(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        _no_forbidden(body)

    def test_game_edge_no_forbidden(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        _no_forbidden(body)

    def test_edge_claimed_false_sport_view(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s" % _SPORT,
                               params={"store_dir": _sd(store_dir)}).json()
        assert body.get("edge_claimed") is False

    def test_edge_claimed_false_game_view(self, edge_client, store_dir):
        body = edge_client.get("/api/v1/edges/%s/%s" % (_SPORT, _GID),
                               params={"store_dir": _sd(store_dir)}).json()
        assert body.get("edge_claimed") is False

    def test_no_raw_edge_key_in_bet_rows(self, exec_client, ledger_path):
        """Bet rows must never carry a raw 'edge' key (only model_prob/model_ev/tier)."""
        body = exec_client.post(
            "/api/paper/place",
            json={"sport": _SPORT, "game_id": _GID,
                  "market_type": "moneyline", "side": "home",
                  "book": _BOOK, "taken_decimal": _DEC},
            params={"ledger": ledger_path},
        ).json()
        bet = body.get("bet", {})
        assert "edge" not in bet, "bet row must not have a bare 'edge' key"
