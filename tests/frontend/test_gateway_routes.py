"""Per-file test: the WAVE 4 gateway routes mounted on predict_service.app.

Covers:
  * GET /api/catalog              -> lists all four faces + the standing rails
  * GET /api/status.all_honest    -> ok=True now
  * GET /api/status.all_honest?inject=<$body>      -> flips ok=False
  * GET /api/status.all_honest?inject=<real-money> -> flips ok=False
  * GET /api/status.all_honest?inject=<stale-green>-> flips ok=False
  * GET /api/intel/{query}        -> number-free hit list, honest flags
  * NO $ / roi / pnl key in any response body

Run: python -m pytest tests/frontend/test_gateway_routes.py -q
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from predict_service import app as app_module

_client = TestClient(app_module.app)

_FORBIDDEN = ("roi", "pnl", "profit", "dollar", "bankroll", "stake_dollars", "usd")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower()
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_keys(it)


def _assert_no_money_keys(body):
    keys = set(_iter_keys(body))
    for k in keys:
        words = set(k.replace("-", "_").split("_"))
        assert not (words & set(_FORBIDDEN)), "forbidden money key: %s" % k


def test_catalog_lists_all_faces():
    r = _client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    faces = {f["face"] for f in body["faces"]}
    assert faces == {"prediction", "execution", "lines", "intelligence"}
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
    _assert_no_money_keys(body)


def test_all_honest_true_now():
    r = _client.get("/api/status.all_honest")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["violations"] == []


def test_all_honest_flips_false_on_injected_money_key():
    inject = json.dumps({"status": "ok", "total_pnl": 9.0})
    r = _client.get("/api/status.all_honest", params={"inject": inject})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_all_honest_flips_false_on_injected_real_money():
    inject = json.dumps({"status": "ok", "real_money_enabled": True})
    r = _client.get("/api/status.all_honest", params={"inject": inject})
    assert r.json()["ok"] is False


def test_all_honest_flips_false_on_injected_stale_green():
    inject = json.dumps({"status": "ok", "serveable": True,
                         "freshness": {"serveable": False, "status": "stale"}})
    r = _client.get("/api/status.all_honest", params={"inject": inject})
    assert r.json()["ok"] is False


def test_intel_is_number_free():
    r = _client.get("/api/intel/drop coverage rim runner")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["number_free"] is True
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
    # No bettable-number key leaks into any hit.
    forbidden_hit = {"probability", "odds", "edge", "kelly", "clv", "ev"}
    for k in set(_iter_keys(body)):
        assert k not in forbidden_hit, "intel leaked a number key: %s" % k
    _assert_no_money_keys(body)
