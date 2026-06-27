"""P5 API contract test -- Prediction API (:8099) + Execution API.

OFFLINE / seeded: a real predict_service.store rooted at tmp_path is written with
store.save(), so every endpoint exercises the genuine read path (no parallel
stub).  Live network is never required -- the in-game read is monkeypatched onto a
seeded live state, and the seeded edges drive deterministic tier/floor outcomes.

Contract asserted:
  PREDICTION API
    * GET /api/predict/{sport}            -> calibrated PREGAME numbers (envelope).
    * GET /api/report/{sport}/{game_id}   -> calibrated pregame AND an IN-GAME
      block carrying a live number (served via the frozen live read).
  EXECUTION API (/api/v1/bestbets)
    * Shin-devigged market_prob + EV present on every candidate.
    * An A-tier candidate (EV >= 0.08) appears in best_bets with decision='bet'.
    * A below-floor candidate (EV < 0.02) is decision='no_bet', NOT in best_bets.
    * Stake is in UNITS only -- flat_unit + kelly_units; NO $ / dollar key.
    * The CLV beat-scoreboard field is present.
  HONESTY
    * No response body key is a dollar amount / contains '$' (units only).

Run: python -m pytest tests/platformkit/test_p5_api_contract.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predict_service import app as app_module
from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

_SPORT = "nba"
# Forbidden money KEYS (exact, lowercased) -- a matchup name may legitimately
# contain a substring like 'ros', so we check object KEYS, not bare substrings.
_FORBIDDEN_KEYS = (
    "$", "dollar", "dollars", "roi", "profit", "pnl", "bankroll",
    "stake_dollars", "$edge", "dollar_edge",
)


def _seeded_envelope() -> SnapshotEnvelope:
    """One game with an A-tier ML home edge and a below-floor away edge.

    home: model_prob 0.62 @ best_odds 1.95 -> EV = 0.62*1.95 - 1 = +0.209 (A).
    away: model_prob 0.39 @ best_odds 2.10 -> EV = 0.39*2.10 - 1 = -0.181 (no bet).
    Both market sides carry a devigged_prob so edge_api builds a comparison row.
    """
    mkt_home = MarketRow(
        sport=_SPORT, game_id="g1", market_type="moneyline", side="home",
        odds=1.95, book="kalshi", devigged_prob=0.55,
        captured_at="2026-06-18T00:00:00+00:00", is_close=True, clv_is_proxy=False)
    mkt_away = MarketRow(
        sport=_SPORT, game_id="g1", market_type="moneyline", side="away",
        odds=2.10, book="dk", devigged_prob=0.45,
        captured_at="2026-06-18T00:00:00+00:00", is_close=True, clv_is_proxy=False)
    pred = PredictionRecord(
        sport=_SPORT, game_id="g1", home="NYK", away="SAS",
        tipoff="2026-06-18T23:00:00+00:00",
        pregame_probs={"home_ml": 0.62, "away_ml": 0.39},
        markets=[mkt_home, mkt_away])
    edge_home = EdgeRow(game_id="g1", market_type="moneyline", side="home",
                        model_prob=0.62, market_prob=0.55, ev=0.209,
                        tier=None, book="kalshi")
    edge_away = EdgeRow(game_id="g1", market_type="moneyline", side="away",
                        model_prob=0.39, market_prob=0.45, ev=-0.181,
                        tier=None, book="dk")
    return SnapshotEnvelope(
        sport=_SPORT, generated_at="2026-06-18T22:00:00+00:00", status="ok",
        predictions=[pred], markets=[mkt_home, mkt_away],
        edges=[edge_home, edge_away])


def _seeded_live(*_a, **_k):
    """A deterministic in-game block (no network) -- a live re-priced number."""
    return {"status": "ok", "state": "live", "home_score": 58, "away_score": 51,
            "clock": "4:12 Q3", "p_home_win": 0.71}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient over the real store rooted at tmp_path, with live read stubbed."""
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_store_out_dir", lambda: str(tmp_path))
    # Stub the in-game read everywhere it is imported (report + bestbets).
    import frontend.report as report_mod
    monkeypatch.setattr(report_mod, "_live", _seeded_live)
    store.save(_seeded_envelope(), out_dir=tmp_path)
    return TestClient(app_module.app), tmp_path


# -- honesty helper -----------------------------------------------------------

def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


def _assert_no_dollar(body) -> None:
    for k in _iter_keys(body):
        ks = str(k).lower()
        assert "$" not in ks, "dollar key %r in response" % k
        assert ks not in _FORBIDDEN_KEYS, "money key %r in response" % k


# -- PREDICTION API -----------------------------------------------------------

def test_prediction_pregame(client):
    cl, _ = client
    r = cl.get("/api/predict/%s" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    pred = body["predictions"][0]
    # Calibrated PREGAME numbers present.
    assert pred["pregame_probs"]["home_ml"] == pytest.approx(0.62)
    _assert_no_dollar(body)


def test_prediction_ingame(client):
    cl, _ = client
    r = cl.get("/api/report/%s/g1" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # Calibrated pregame ...
    assert body["pregame"]["model_probs"]["home_ml"] == pytest.approx(0.62)
    # ... AND an in-game number for the seeded slate.
    live = body["live"]
    assert live["status"] == "ok"
    assert live["p_home_win"] == pytest.approx(0.71)
    _assert_no_dollar(body)


# -- EXECUTION API ------------------------------------------------------------

def test_execution_tier_floors_and_no_bet(client):
    cl, _ = client
    r = cl.get("/api/v1/bestbets/%s" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    game = body["games"][0]
    cand = {c["side"]: c for c in game["candidates"]}

    # Shin-devigged market_prob + EV are present on every candidate.
    for c in game["candidates"]:
        assert c["market_prob"] is not None
        assert c["ev"] is not None

    # A-tier candidate (EV >= 0.08) -> decision='bet', tier 'A', in best_bets.
    home = cand["home"]
    assert home["ev"] == pytest.approx(0.62 * 1.95 - 1.0, abs=1e-6)
    assert home["tier"] == "A"
    assert home["decision"] == "bet"
    assert home["flat_unit"] == 1.0
    assert home["kelly_units"] >= 0.0
    assert any(b["side"] == "home" for b in game["best_bets"])

    # Below-floor candidate (EV < 0.02) -> no_bet, NOT in best_bets, 0 units.
    away = cand["away"]
    assert away["tier"] is None
    assert away["decision"] == "no_bet"
    assert away["stake_units"] == 0.0
    assert not any(b["side"] == "away" for b in game["best_bets"])

    _assert_no_dollar(body)


def test_execution_units_only_no_dollar(client):
    cl, _ = client
    r = cl.get("/api/v1/bestbets/%s" % _SPORT)
    body = r.json()
    home = next(c for g in body["games"] for c in g["candidates"]
                if c["side"] == "home")
    # Stake fields are UNIT counts, never money.
    assert set(["flat_unit", "kelly_units", "stake_units"]).issubset(home.keys())
    assert "stake" not in home or "units" in str(home).lower()
    _assert_no_dollar(body)


def test_execution_clv_scoreboard_present(client):
    cl, _ = client
    r = cl.get("/api/v1/bestbets/%s" % _SPORT)
    body = r.json()
    assert "clv" in body, "CLV beat-scoreboard missing from execution response"
    clv = body["clv"]
    assert "n_bets" in clv
    assert "mean_clv_pct" in clv
    _assert_no_dollar(body)


def test_execution_below_floor_proxy_bump(client):
    """A proxy close raises every floor +0.01 -- exercised at the unit level."""
    from frontend.exec_decision import assign_tier
    # EV 0.025: clears C (0.02) on a true close, but NOT the proxy floor (0.03).
    assert assign_tier(0.025, clv_is_proxy=False) == "C"
    assert assign_tier(0.025, clv_is_proxy=True) is None
    # EV 0.085 clears A (0.08) on a true close; proxy A floor is 0.09 -> B.
    assert assign_tier(0.085, clv_is_proxy=False) == "A"
    assert assign_tier(0.085, clv_is_proxy=True) == "B"


def test_execution_per_game_endpoint(client):
    cl, _ = client
    r = cl.get("/api/v1/bestbets/%s/g1" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["game_id"] == "g1"
    assert any(b["side"] == "home" for b in body["best_bets"])
    assert body["live"]["status"] == "ok"
    assert "clv" in body
    _assert_no_dollar(body)
