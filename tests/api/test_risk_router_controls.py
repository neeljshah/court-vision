"""The kill switch must be authenticated and must fail CLOSED.

Execution readiness audit 2026-09-17, defect #3. Before the accompanying change
to api/_risk_router.py and src/prediction/risk_controls.py:
  * LIVE_V2_AUTH_TOKEN unset -> _required_token() returned None -> auth_dep
    returned immediately, so POST /api/risk/kill-switch {"engage": false} was
    UNAUTHENTICATED BY DEFAULT: anyone who could reach the port could DISENGAGE
    the interlock.
  * read_kill_switch() caught every exception and returned (False, None), so a
    corrupt or unreadable kill_switch.json silently reported NOT ENGAGED.
  * The /api/risk/status 500 body asserted "kill_switch_engaged": false while
    the true state was unknown.
This file breaches each control. It writes nothing under data/.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/api/test_risk_router_controls.py -q
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import _risk_router as R
from src.prediction import risk_controls as RC

_TOKEN = "s3cret-token"


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _no_real_writes(monkeypatch, tmp_path):
    """Never touch data/cache/kill_switch.json from a test."""
    monkeypatch.setattr(RC, "_KILL_SWITCH_PATH", tmp_path / "kill_switch.json")
    monkeypatch.setattr(RC, "write_kill_switch",
                        lambda engaged, reason=None: None)


# -- auth on the MUTATING routes -------------------------------------------

def test_kill_switch_is_disabled_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.delenv("LIVE_V2_AUTH_TOKEN", raising=False)
    r = client.post("/api/risk/kill-switch", json={"engage": False})
    assert r.status_code == 503          # NOT 200 -- there is no open default
    assert "LIVE_V2_AUTH_TOKEN" in r.json()["detail"]


def test_bankroll_set_is_disabled_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.delenv("LIVE_V2_AUTH_TOKEN", raising=False)
    assert client.post("/api/bankroll/set", json={"bankroll": 10.0}).status_code == 503


def test_disengage_without_a_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", _TOKEN)
    assert client.post("/api/risk/kill-switch", json={"engage": False}).status_code == 401


def test_disengage_with_a_wrong_token_is_rejected(client, monkeypatch):
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", _TOKEN)
    r = client.post("/api/risk/kill-switch?token=wrong", json={"engage": False})
    assert r.status_code == 401


def test_engage_with_the_right_token_is_accepted(client, monkeypatch):
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", _TOKEN)
    client.cookies.set("cv_session", _TOKEN)
    r = client.post("/api/risk/kill-switch", json={"engage": True, "reason": "test"})
    assert r.status_code == 200 and r.json()["engaged"] is True


# -- fail-closed reads ------------------------------------------------------

def test_absent_state_file_is_the_initial_not_engaged_state(tmp_path, monkeypatch):
    monkeypatch.setattr(RC, "_KILL_SWITCH_PATH", tmp_path / "absent.json")
    assert RC.read_kill_switch() == (False, None)


def test_corrupt_state_file_reads_as_ENGAGED(tmp_path, monkeypatch):
    path = tmp_path / "kill_switch.json"
    path.write_text("{truncated", encoding="utf-8")
    monkeypatch.setattr(RC, "_KILL_SWITCH_PATH", path)
    engaged, reason = RC.read_kill_switch()
    assert engaged is True and reason           # unreadable != clear
    assert "unreadable" in reason


def test_valid_state_file_still_reads_through(tmp_path, monkeypatch):
    path = tmp_path / "kill_switch.json"
    monkeypatch.setattr(RC, "_KILL_SWITCH_PATH", path)
    path.write_text('{"engaged": true, "reason": "manual"}', encoding="utf-8")
    assert RC.read_kill_switch() == (True, "manual")
    path.write_text('{"engaged": false, "reason": ""}', encoding="utf-8")
    assert RC.read_kill_switch() == (False, None)


def test_status_outage_never_claims_the_switch_is_clear(client, monkeypatch):
    monkeypatch.delenv("LIVE_V2_AUTH_TOKEN", raising=False)

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(R, "_get_db", _boom)
    r = client.get("/api/risk/status")
    assert r.status_code == 500
    body = r.json()
    assert body["kill_switch_engaged"] is True
    assert body["kill_switch_state"] == "unknown"
