"""Per-file test for predict_service.extra_mounts._prioritize_props_routes.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_extra_mounts_route_priority.py -q

Regression guard for the 2026-07-02 bug: Starlette matches routes in
REGISTRATION order. predict_service.app registers the generic
'/api/predict/{sport}/{game_id}' route BEFORE extra_mounts.register() mounts
'/api/predict/props/{sport}'. Both are 2-segment path patterns, so a request
for '/api/predict/props/mlb' structurally matched the generic route FIRST
(sport='props', game_id='mlb') -- silently returning a bogus "no snapshot for
sport 'props'" instead of real prop predictions, even though the underlying
prop data pipeline was fully populated. _prioritize_props_routes fixes this by
moving the props routes to the front of app.router.routes after mounting.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.extra_mounts import _prioritize_props_routes


def _build_colliding_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/predict/{sport}/{game_id}")
    def generic(sport: str, game_id: str):
        return {"handler": "generic", "sport": sport, "game_id": game_id}

    @app.get("/api/predict/props/{sport}")
    def props(sport: str):
        return {"handler": "props", "sport": sport}

    return app


def test_generic_route_wins_without_the_fix():
    app = _build_colliding_app()
    client = TestClient(app)
    body = client.get("/api/predict/props/mlb").json()
    assert body["handler"] == "generic"
    assert body["sport"] == "props"
    assert body["game_id"] == "mlb"


def test_props_route_wins_after_prioritizing():
    app = _build_colliding_app()
    _prioritize_props_routes(app)
    client = TestClient(app)
    body = client.get("/api/predict/props/mlb").json()
    assert body["handler"] == "props"
    assert body["sport"] == "mlb"


def test_prioritizing_does_not_drop_or_duplicate_routes():
    app = _build_colliding_app()
    before = len(app.router.routes)
    _prioritize_props_routes(app)
    assert len(app.router.routes) == before


def test_generic_two_segment_route_still_works_after_fix():
    app = _build_colliding_app()
    _prioritize_props_routes(app)
    client = TestClient(app)
    body = client.get("/api/predict/nba/game123").json()
    assert body["handler"] == "generic"
    assert body["sport"] == "nba"
    assert body["game_id"] == "game123"
