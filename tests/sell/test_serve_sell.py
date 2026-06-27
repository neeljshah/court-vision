"""tests.sell.test_serve_sell -- per-file tests for sell.serve_sell (FastAPI).

Tests:
  * /sell/health -- always 200 without auth; edge_claimed=false.
  * Unauthenticated requests to gated endpoints -> 401.
  * Invalid / forged key -> 401.
  * Valid free key -> 200 on /sell/track_record.
  * Valid free key -> 403 on /sell/evidence (enterprise-only).
  * Valid pro key -> 403 on /sell/evidence (enterprise-only).
  * Valid enterprise key -> 200 on /sell/evidence.
  * Every payload carries edge_claimed=false and no $ key (honesty linter).
  * track_record response passes honesty linter.
  * evidence response passes honesty linter.
  * Usage meter increments on authenticated calls.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/sell/test_serve_sell.py -q
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from governance.honesty_linter import lint_obj
from sell.authz import issue_key

# --------------------------------------------------------------------------- #
# Shared test secret (never used in production)                               #
# --------------------------------------------------------------------------- #
_SECRET = "test-sell-api-secret-not-for-production"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch):
    """Inject the test secret so authz can sign/verify keys."""
    monkeypatch.setenv("SELL_API_SECRET", _SECRET)


@pytest.fixture(scope="module")
def client():
    """A TestClient scoped to the module (app import happens once)."""
    # Import here so the autouse monkeypatch above fires BEFORE the client
    # resolves env vars.  Module scope is fine because the app is stateless.
    from sell.serve_sell import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --------------------------------------------------------------------------- #
# Key helpers                                                                  #
# --------------------------------------------------------------------------- #

def _key(plan: str) -> str:
    return issue_key("test-tenant-%s" % plan, plan, _secret=_SECRET)


def _auth(plan: str) -> Dict[str, str]:
    return {"Authorization": "Bearer %s" % _key(plan)}


def _enterprise_key() -> str:
    return _key("enterprise")


def _free_key() -> str:
    return _key("free")


def _pro_key() -> str:
    return _key("pro")


# --------------------------------------------------------------------------- #
# /sell/health                                                                 #
# --------------------------------------------------------------------------- #

class TestHealth:
    def test_health_no_auth_200(self, client):
        r = client.get("/sell/health")
        assert r.status_code == 200

    def test_health_edge_claimed_false(self, client):
        body = r.json() if (r := client.get("/sell/health")) else {}
        r = client.get("/sell/health")
        body = r.json()
        assert body.get("edge_claimed") is False

    def test_health_has_honest_note(self, client):
        body = client.get("/sell/health").json()
        assert "honest_note" in body
        assert body["honest_note"]  # non-empty string

    def test_health_no_dollar_keys(self, client):
        body = client.get("/sell/health").json()
        verdict = lint_obj(body)
        assert verdict["clean"], "health endpoint failed honesty lint: %s" % verdict["violations"]

    def test_health_status_ok(self, client):
        body = client.get("/sell/health").json()
        assert body.get("status") == "ok"


# --------------------------------------------------------------------------- #
# Authentication enforcement                                                   #
# --------------------------------------------------------------------------- #

class TestAuth:
    def test_track_record_no_key_401(self, client):
        r = client.get("/sell/track_record")
        assert r.status_code == 401

    def test_evidence_no_key_401(self, client):
        r = client.get("/sell/evidence")
        assert r.status_code == 401

    def test_track_record_invalid_key_401(self, client):
        r = client.get("/sell/track_record",
                       headers={"Authorization": "Bearer not.a.real.key"})
        assert r.status_code == 401

    def test_evidence_invalid_key_401(self, client):
        r = client.get("/sell/evidence",
                       headers={"Authorization": "Bearer forged.key.value"})
        assert r.status_code == 401

    def test_forged_key_401(self, client):
        """Tamper the HMAC hex digit to break the key."""
        key = _free_key()
        parts = key.rsplit(".", 1)
        mac = parts[1]
        bad = "0" if mac[-1] != "0" else "1"
        forged = parts[0] + "." + mac[:-1] + bad
        r = client.get("/sell/track_record",
                       headers={"Authorization": "Bearer %s" % forged})
        assert r.status_code == 401

    def test_query_param_auth_works(self, client):
        """api_key query param is an accepted alternative to the header."""
        r = client.get("/sell/track_record",
                       params={"api_key": _free_key()})
        assert r.status_code == 200

    def test_401_body_edge_claimed_false(self, client):
        """Even error responses must carry edge_claimed=false."""
        r = client.get("/sell/track_record")
        body = r.json()
        # FastAPI wraps the detail as {"detail": {...}}
        detail = body.get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("edge_claimed") is False


# --------------------------------------------------------------------------- #
# /sell/track_record                                                           #
# --------------------------------------------------------------------------- #

class TestTrackRecord:
    def test_free_key_200(self, client):
        r = client.get("/sell/track_record", headers=_auth("free"))
        assert r.status_code == 200

    def test_pro_key_200(self, client):
        r = client.get("/sell/track_record", headers=_auth("pro"))
        assert r.status_code == 200

    def test_enterprise_key_200(self, client):
        r = client.get("/sell/track_record", headers=_auth("enterprise"))
        assert r.status_code == 200

    def test_edge_claimed_false(self, client):
        body = client.get("/sell/track_record", headers=_auth("free")).json()
        assert body.get("edge_claimed") is False

    def test_has_honest_note(self, client):
        body = client.get("/sell/track_record", headers=_auth("free")).json()
        assert "honest_note" in body

    def test_no_dollar_keys(self, client):
        """No $ / roi / profit keys -- honesty linter must be clean."""
        body = client.get("/sell/track_record", headers=_auth("free")).json()
        verdict = lint_obj(body)
        assert verdict["clean"], (
            "track_record endpoint failed honesty lint: %s" % verdict["violations"]
        )

    def test_schema_version_present(self, client):
        body = client.get("/sell/track_record", headers=_auth("free")).json()
        assert "schema_version" in body

    def test_no_roi_field(self, client):
        body = client.get("/sell/track_record", headers=_auth("free")).json()
        keys_lower = {k.lower() for k in body}
        assert "roi" not in keys_lower
        assert "$edge" not in keys_lower
        assert "profit" not in keys_lower

    def test_x_edge_claimed_header(self, client):
        r = client.get("/sell/track_record", headers=_auth("free"))
        assert r.headers.get("x-edge-claimed", "").lower() == "false"


# --------------------------------------------------------------------------- #
# /sell/evidence -- plan gating                                               #
# --------------------------------------------------------------------------- #

class TestEvidence:
    def test_free_key_403(self, client):
        """Free plan cannot access enterprise-only evidence endpoint."""
        r = client.get("/sell/evidence", headers=_auth("free"))
        assert r.status_code == 403

    def test_pro_key_403(self, client):
        """Pro plan cannot access enterprise-only evidence endpoint."""
        r = client.get("/sell/evidence", headers=_auth("pro"))
        assert r.status_code == 403

    def test_enterprise_key_200(self, client):
        """Enterprise plan CAN access the evidence endpoint."""
        r = client.get("/sell/evidence", headers=_auth("enterprise"))
        assert r.status_code == 200

    def test_403_body_edge_claimed_false(self, client):
        """Plan-denial responses must carry edge_claimed=false."""
        r = client.get("/sell/evidence", headers=_auth("free"))
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("edge_claimed") is False

    def test_evidence_edge_claimed_false(self, client):
        body = client.get("/sell/evidence",
                          headers=_auth("enterprise")).json()
        assert body.get("edge_claimed") is False

    def test_evidence_has_honest_note(self, client):
        body = client.get("/sell/evidence",
                          headers=_auth("enterprise")).json()
        assert "honest_note" in body

    def test_evidence_no_dollar_keys(self, client):
        """Evidence pack must also pass the honesty linter."""
        body = client.get("/sell/evidence",
                          headers=_auth("enterprise")).json()
        verdict = lint_obj(body)
        assert verdict["clean"], (
            "evidence endpoint failed honesty lint: %s" % verdict["violations"]
        )

    def test_evidence_has_artifacts(self, client):
        body = client.get("/sell/evidence",
                          headers=_auth("enterprise")).json()
        assert "artifacts" in body
        assert isinstance(body["artifacts"], list)
        assert len(body["artifacts"]) > 0

    def test_evidence_no_roi_field(self, client):
        body = client.get("/sell/evidence",
                          headers=_auth("enterprise")).json()
        keys_lower = {k.lower() for k in body}
        assert "roi" not in keys_lower
        assert "$edge" not in keys_lower


# --------------------------------------------------------------------------- #
# Usage meter                                                                  #
# --------------------------------------------------------------------------- #

class TestUsageMeter:
    def test_track_record_increments_meter(self, tmp_path, monkeypatch):
        """A successful /sell/track_record call records usage for that tenant."""
        import sell.tenancy as _tenancy
        import sell.usage_meter as _meter

        monkeypatch.setattr(_tenancy, "TENANTS_ROOT", tmp_path)

        from sell.serve_sell import app as _app
        with TestClient(_app) as c:
            tenant_id = "meter-test-free"
            key = issue_key(tenant_id, "free", _secret=_SECRET)
            c.get("/sell/track_record",
                  headers={"Authorization": "Bearer %s" % key})

        ns = _tenancy.namespace_for(tenant_id, root=tmp_path)
        total = _meter.total_calls(tenant_id, _ns=ns)
        assert total >= 1, "usage meter did not increment for tenant %s" % tenant_id

    def test_evidence_increments_meter(self, tmp_path, monkeypatch):
        """A successful /sell/evidence call records usage for that tenant."""
        import sell.tenancy as _tenancy
        import sell.usage_meter as _meter

        monkeypatch.setattr(_tenancy, "TENANTS_ROOT", tmp_path)

        from sell.serve_sell import app as _app
        with TestClient(_app) as c:
            tenant_id = "meter-test-enterprise"
            key = issue_key(tenant_id, "enterprise", _secret=_SECRET)
            c.get("/sell/evidence",
                  headers={"Authorization": "Bearer %s" % key})

        ns = _tenancy.namespace_for(tenant_id, root=tmp_path)
        total = _meter.total_calls(tenant_id, _ns=ns)
        assert total >= 1, "usage meter did not increment for evidence tenant"
