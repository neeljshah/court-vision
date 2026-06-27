"""Per-file test: frontend.serve now mounts the built-but-previously-unmounted
observability / autonomy / gateway / quant routers (the documented M1 stopgap
gap). Each newly surfaced path must RESOLVE -- 200 or an honest 503/empty
sentinel -- and must NEVER 500 (a fail-open crash) nor leak a $ field.

Run: python -m pytest tests/frontend/test_serve_extra_mounts.py -q
"""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from frontend.serve import app


# Paths the extra mounts are expected to surface on frontend.serve. Each is the
# canonical READ path; per-game/per-query variants resolve through the same
# router so the parent path is a sufficient resolve check.
_EXPECTED = (
    "/api/improve/status",   # status_routes
    "/api/parity",           # status_routes
    "/api/clv/over-time",    # status_routes
    "/api/improve/timeline",  # autonomy_routes
    "/api/ops/autonomy",     # autonomy_routes
    "/api/catalog",          # catalog_routes
    "/api/status.all_honest",  # catalog_routes
    "/api/quant/risk",       # quant_routes
    "/api/quant/clv",        # quant_routes
)

# $ / currency FIELD KEYS that must NEVER appear in any response body (honesty
# rail). We check JSON keys -- not raw text -- so an honest disclaimer that
# merely mentions the word "dollars" in prose ("units, never dollars") is fine;
# only an actual $ FIELD is a violation.
_BANNED_KEYS = ("usd", "dollars", "stake_usd", "pnl", "profit_usd",
                "bankroll_usd", "stake_dollars", "amount_usd")


def _iter_keys(obj):
    """Yield every dict key found recursively in a JSON-decoded structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower()
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_routes_are_registered():
    """Every expected path is actually mounted on the app (not a 404 router gap)."""
    registered = {getattr(r, "path", None) for r in app.routes}
    for path in _EXPECTED:
        assert path in registered, "%s not mounted on frontend.serve" % path


def test_health_still_ok(client: TestClient):
    """The base liveness probe is unaffected by the extra mounts."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.parametrize("path", _EXPECTED)
def test_route_resolves_never_500(client: TestClient, path: str):
    """Each path resolves to an honest status -- 200 or 503/empty, NEVER a 500."""
    r = client.get(path)
    # The whole point: a built route either serves real data (200) or an honest
    # unavailable sentinel (503) -- it must never crash (500) or 404 (unmounted).
    assert r.status_code in (200, 503), (
        "%s returned %s (expected 200 or honest 503)" % (path, r.status_code)
    )


@pytest.mark.parametrize("path", _EXPECTED)
def test_no_dollar_field_and_edge_not_claimed(client: TestClient, path: str):
    """No response leaks a $ FIELD; bodies that carry edge_claimed stamp it False."""
    r = client.get(path)
    try:
        body = r.json()
    except Exception:  # noqa: BLE001 -- some endpoints may stream / be empty
        return
    keys = set(_iter_keys(body))
    for banned in _BANNED_KEYS:
        assert banned not in keys, "%s leaked a $ field key %r" % (path, banned)
    # Where an edge_claimed flag is present it must be honest (False).
    if isinstance(body, dict) and "edge_claimed" in body:
        assert body["edge_claimed"] is False, "%s claims an edge" % path
