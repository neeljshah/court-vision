"""Per-file test: predict_service.honest_route -- the shared honest-envelope decorator.

Covers the W3 ROBUSTNESS rail (BACKEND lane):
  * a handler that RAISES -> honest {status:'unavailable'} 503, NEVER a 500 stack
  * the served reason carries the exception TYPE NAME only -- NEVER the message,
    args, or a traceback (no internal/secret leak)
  * a degradation body carries edge_claimed=False and NO $/edge key (units rail)
  * the happy path is passed through UNCHANGED (zero behavior change)
  * async handlers are wrapped too
  * NEGATIVE CONTROL: a raised exception must NOT read as a 200/green -- proving the
    guard has teeth (a green-on-raise would FAIL this test)

Run: python -m pytest tests/predict_service/test_honest_route.py -q
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from predict_service.honest_route import honest_route, honest_envelope

_FORBIDDEN = ("roi", "pnl", "profit", "dollar", "bankroll", "stake", "usd")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_keys(it)


def _assert_no_money(body) -> None:
    keys = {str(k).lower() for k in _iter_keys(body)}
    for tok in _FORBIDDEN:
        assert tok not in keys, "forbidden money key %r in degradation body" % tok


def _client() -> TestClient:
    app = FastAPI()

    SECRET = "supersecret-token-1234"  # noqa: S105 -- a fake secret to prove no-leak

    @app.get("/raises")
    @honest_route(extra={"rows": [], "count": 0})
    def raises():  # noqa: ANN202
        raise ValueError("internal detail %s must NOT leak" % SECRET)

    @app.get("/ok")
    @honest_route
    def ok():  # noqa: ANN202
        return JSONResponse({"status": "ok", "value": 42})

    @app.get("/araises")
    @honest_route
    async def araises():  # noqa: ANN202
        raise RuntimeError("async boom %s" % SECRET)

    return TestClient(app, raise_server_exceptions=False)


def test_raise_becomes_honest_503_not_stack():
    c = _client()
    r = c.get("/raises")
    # NEGATIVE CONTROL: a raise must NEVER read as 200/green.
    assert r.status_code != 200
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["edge_claimed"] is False
    # type name present, message/secret absent.
    assert "ValueError" in body["reason"]
    assert "supersecret" not in json.dumps(body)
    assert "Traceback" not in json.dumps(body)
    # shape-stable empties seeded by extra.
    assert body["rows"] == [] and body["count"] == 0
    _assert_no_money(body)


def test_happy_path_passthrough_unchanged():
    c = _client()
    r = c.get("/ok")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "value": 42}


def test_async_handler_raise_is_honest():
    c = _client()
    r = c.get("/araises")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert "RuntimeError" in body["reason"]
    assert "supersecret" not in json.dumps(body)


def test_honest_envelope_drops_money_key():
    # The degradation body must never smuggle a $/edge key past the rail.
    env = honest_envelope("x raised", extra={"roi": 9.9, "rows": []})
    assert "roi" not in env
    assert env["rows"] == []
    assert env["status"] == "unavailable" and env["edge_claimed"] is False
