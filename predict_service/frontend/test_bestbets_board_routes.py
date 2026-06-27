"""Per-file test: predict_service.frontend.bestbets_board_routes (unified board).

Covers the unified board route: ML + total + spread + prop cards all surface;
priced bets rank before model-only props; model-only props are capped per sport
with an honest 'N more' count; stale-never-green; and the compute fallback when the
daemon cache is unavailable. Uses FastAPI TestClient + synthetic cached_board_read
envelopes -- NOT the live daemon.

Run: python -m pytest predict_service/frontend/test_bestbets_board_routes.py -q
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import scripts.platformkit.bestbets.cached_board_read as cbr
from predict_service.frontend import bestbets_board_routes as bbr


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(bbr.router)
    return TestClient(app)


def _game_card(sport, mt, side, tier, conf, mp=0.5):
    return {
        "game_id": "g_%s_%s" % (mt, side), "matchup": "A vs B", "sport": sport,
        "market_type": mt, "side": side, "tier": tier, "confidence": conf,
        "model_prob": conf, "market_prob": mp, "best_book": "pinnacle",
        "best_odds": 1.9, "all_books": [{"book": "pinnacle", "odds": 1.9}],
        "edge_vs_market": round(conf - mp, 4), "units": 1.0, "status": "pregame",
    }


def _prop_card(sport, player, conf, model_only=True, reliable=True):
    return {
        "game_id": "", "matchup": "A vs B", "sport": sport, "market_type": "prop",
        "prop_player": player, "prop_stat": "pts", "line": 12.5, "side": "over",
        "model_prob": conf, "confidence": conf,
        "market_prob": (None if model_only else 0.45),
        "best_odds": None, "all_books": [], "tier": "MODEL_VIEW" if model_only else "C",
        "edge_vs_market": (None if model_only else round(conf - 0.45, 4)),
        "units": 1.0, "model_only": model_only, "reliable": reliable,
        "status": "pregame",
    }


def _patch_cache(monkeypatch, cards, status="fresh", generated_at=1.0, stale_note=""):
    env = {"status": status, "overall": "ok" if status == "fresh" else "stale",
           "cards": cards, "generated_at": generated_at, "card_count": len(cards),
           "stale_note": stale_note, "honest_note": "n"}
    monkeypatch.setattr(cbr, "read", lambda **kw: env)


def test_all_markets_surface(monkeypatch):
    cards = [
        _game_card("mlb", "moneyline", "home", "A", 0.62),
        _game_card("mlb", "total", "over", "B", 0.57),
        _game_card("mlb", "spread", "home", "C", 0.54),
        _prop_card("mlb", "Player X", 0.61, model_only=True),
    ]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board").json()
    mts = {c["market_type"] for c in body["cards"]}
    assert {"moneyline", "total", "spread", "prop"} <= mts
    assert body["source"] == "daemon_cache"
    assert body["edge_claimed"] is False
    assert body["status"] == "ok"


def test_priced_ranked_before_model_only(monkeypatch):
    # A high-confidence model-only prop must still rank AFTER priced game cards.
    cards = [
        _prop_card("mlb", "Hot Prop", 0.99, model_only=True),
        _game_card("mlb", "moneyline", "home", "A", 0.60),
    ]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board").json()
    assert body["cards"][0]["market_type"] == "moneyline"
    assert body["cards"][-1]["model_only"] is True


def test_model_only_cap_and_more_count(monkeypatch):
    monkeypatch.setattr(bbr, "MODEL_ONLY_CAP_PER_SPORT", 3)
    cards = [_prop_card("mlb", "P%d" % i, 0.5 + i * 0.001) for i in range(10)]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board").json()
    assert len(body["cards"]) == 3
    assert body["model_only_more"] == 7
    assert body["model_only_truncated"].get("mlb") == 7


def test_priced_props_not_capped(monkeypatch):
    monkeypatch.setattr(bbr, "MODEL_ONLY_CAP_PER_SPORT", 1)
    # priced props (market_prob present) are NOT model-only -> never capped.
    cards = [_prop_card("mlb", "P%d" % i, 0.6, model_only=False) for i in range(5)]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board").json()
    assert len(body["cards"]) == 5
    assert body["model_only_more"] == 0


def test_stale_never_green(monkeypatch):
    cards = [_game_card("mlb", "moneyline", "home", "A", 0.62)]
    _patch_cache(monkeypatch, cards, status="stale", stale_note="cache is old")
    body = _client().get("/api/bestbets/board").json()
    assert body["status"] == "stale"
    assert body["stale"] is True
    assert body["cache_status"] == "stale"
    assert body["status"] != "ok"


def test_fallback_to_compute_when_cache_unavailable(monkeypatch):
    monkeypatch.setattr(cbr, "read", lambda **kw: {"status": "unavailable"})

    def _fake_compute(sport, **kw):
        if sport != "mlb":
            return {"cards": []}
        return {"cards": [_game_card("mlb", "moneyline", "home", "A", 0.6)]}

    monkeypatch.setattr(bbr, "compute_best_bets", _fake_compute)
    monkeypatch.setattr(bbr, "_active_sports", lambda: ["mlb"])
    body = _client().get("/api/bestbets/board").json()
    assert body["source"] == "compute"
    assert body["count"] == 1
    assert body["cards"][0]["market_type"] == "moneyline"


def test_sport_and_tier_filters(monkeypatch):
    cards = [
        _game_card("mlb", "moneyline", "home", "A", 0.62),
        _game_card("nba", "moneyline", "home", "B", 0.58),
    ]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board?sport=mlb&tier=A").json()
    assert body["count"] == 1
    assert body["cards"][0]["sport"] == "mlb"
    assert body["cards"][0]["tier"] == "A"


def test_invalid_tier_400(monkeypatch):
    _patch_cache(monkeypatch, [])
    r = _client().get("/api/bestbets/board?tier=Z")
    assert r.status_code == 400
    assert r.json()["edge_claimed"] is False


def test_best_book_and_books_array_carried(monkeypatch):
    cards = [_game_card("mlb", "moneyline", "home", "A", 0.62)]
    _patch_cache(monkeypatch, cards)
    body = _client().get("/api/bestbets/board").json()
    c = body["cards"][0]
    assert c["best_book"] == "pinnacle"
    assert c["best_odds"] == 1.9
    assert c["all_books"] and c["all_books"][0]["book"] == "pinnacle"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
