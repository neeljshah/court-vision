"""predict_service.frontend.test_supervisor_status_route.

Per-file test for GET /api/ops/supervisor via FastAPI TestClient.

Acceptance criteria (all must pass):
  A. Present, fresh, all-ready file -> status=ok, live=True, no $ key.
  B. Stale updated_at -> status=unavailable, live=False.
  C. Missing file -> status=unavailable, live=False, no crash.
  D. any_degraded=True when any proc is not READY.
  E. any_degraded=True when a proc heartbeat is older than its fresh_sec.
  F. Stale heartbeat does NOT force live=True (stale-never-green even when
     all_ready is True in the file).
  G. No $ / pnl key ever appears in the response body.
  H. all_ready=True alone is insufficient when updated_at is stale.
  I. Route mounts via extra_mounts.register without sinking app boot.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import pytest

# -- FastAPI TestClient setup --------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.frontend.supervisor_status_route import (
    read_supervisor_status,
    router,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


CLIENT = TestClient(_make_app())


# -- helpers -------------------------------------------------------------------

_FORBIDDEN_KEYS = {"pnl", "roi", "profit", "edge_profit", "dollar", "usd"}


def _assert_no_dollar(body: Dict[str, Any]) -> None:
    """Assert no $ / profit / pnl key is present at ANY level."""
    for key in body:
        assert key not in _FORBIDDEN_KEYS, f"forbidden $ key in response: {key!r}"
    for proc in body.get("procs", []):
        for key in proc:
            assert key not in _FORBIDDEN_KEYS, f"forbidden $ key in proc: {key!r}"


def _fresh_doc(
    *,
    all_ready: bool = True,
    procs: list | None = None,
    age_offset: float = 0.0,
) -> Dict[str, Any]:
    """Build a minimal supervisor doc that is fresh by default."""
    now = time.time()
    return {
        "schema_version": "1.0.0",
        "profile": "default",
        "started_at": now - 3600.0,
        "updated_at": now - age_offset,
        "all_ready": all_ready,
        "procs": procs if procs is not None else [
            {
                "name": "m1_producer",
                "state": "READY",
                "pid": 1,
                "restarts": 0,
                "ready": True,
                "detail": {"kind": "none", "reason": "no probe; ready if alive"},
            }
        ],
    }


def _write_doc(path: Path, doc: Dict[str, Any]) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


# -- route-level tests (via TestClient) ----------------------------------------

def test_route_present_fresh_all_ready(tmp_path: Path) -> None:
    """A: Fresh file + all_ready=True + healthy procs -> 200, live=True."""
    p = tmp_path / "supervisor_status.json"
    _write_doc(p, _fresh_doc())

    from predict_service.frontend import supervisor_status_route as mod
    old = mod._DEFAULT_STATUS_PATH
    mod._DEFAULT_STATUS_PATH = p
    try:
        resp = CLIENT.get("/api/ops/supervisor")
    finally:
        mod._DEFAULT_STATUS_PATH = old

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["live"] is True
    assert body["overall"] == "ok"
    assert body["any_degraded"] is False
    assert body["edge_claimed"] is False
    assert len(body["procs"]) == 1
    _assert_no_dollar(body)


def test_route_missing_file() -> None:
    """C: Missing file -> status=unavailable, live=False, no crash."""
    from predict_service.frontend import supervisor_status_route as mod
    old = mod._DEFAULT_STATUS_PATH
    mod._DEFAULT_STATUS_PATH = Path("/nonexistent/path/supervisor_status.json")
    try:
        resp = CLIENT.get("/api/ops/supervisor")
    finally:
        mod._DEFAULT_STATUS_PATH = old

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["live"] is False
    _assert_no_dollar(body)


# -- unit tests over read_supervisor_status (tmp_path-based) ------------------

def test_fresh_all_ready_green(tmp_path: Path) -> None:
    """A: Fresh + all_ready + no degraded proc -> live=True."""
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc())
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["live"] is True
    assert body["status"] == "ok"
    assert body["any_degraded"] is False
    _assert_no_dollar(body)


def test_stale_updated_at_never_green(tmp_path: Path) -> None:
    """B + H: Stale updated_at -> unavailable even when all_ready=True."""
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(age_offset=200.0))  # 200s > 120s SLA
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["status"] == "unavailable"
    assert body["live"] is False
    assert resp.status_code == 503
    _assert_no_dollar(body)


def test_missing_file_unavailable(tmp_path: Path) -> None:
    """C: Missing file -> unavailable, no crash."""
    p = tmp_path / "nonexistent.json"
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["status"] == "unavailable"
    assert body["live"] is False
    _assert_no_dollar(body)


def test_any_degraded_not_ready_proc(tmp_path: Path) -> None:
    """D: A proc with ready=False -> any_degraded=True, live=False."""
    bad_proc = {
        "name": "m1_producer",
        "state": "DOWN",
        "pid": 1,
        "restarts": 2,
        "ready": False,
        "detail": {"kind": "none"},
    }
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=False, procs=[bad_proc]))
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["any_degraded"] is True
    assert body["live"] is False
    assert body["procs"][0]["degraded"] is True
    _assert_no_dollar(body)


def test_any_degraded_stale_heartbeat(tmp_path: Path) -> None:
    """E: Proc with age_sec > fresh_sec -> degraded=True, live=False."""
    stale_proc = {
        "name": "m5_heartbeat",
        "state": "READY",
        "pid": 99,
        "restarts": 0,
        "ready": True,
        "detail": {
            "kind": "heartbeat-file-fresh",
            "age_sec": 400.0,   # older than fresh_sec
            "fresh_sec": 300.0,
        },
    }
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=[stale_proc]))
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["any_degraded"] is True
    assert body["live"] is False
    assert body["procs"][0]["degraded"] is True
    _assert_no_dollar(body)


def test_stale_heartbeat_overrides_all_ready(tmp_path: Path) -> None:
    """F: Stale heartbeat in a proc means live=False even when all_ready=True."""
    stale_proc = {
        "name": "m_stale",
        "state": "READY",
        "pid": 5,
        "restarts": 0,
        "ready": True,
        "detail": {"kind": "heartbeat-file-fresh", "age_sec": 999.0, "fresh_sec": 300.0},
    }
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=[stale_proc]))
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["live"] is False
    _assert_no_dollar(body)


def test_no_dollar_keys_in_body(tmp_path: Path) -> None:
    """G: No $ / pnl / roi / profit / dollar key in any response."""
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc())
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    _assert_no_dollar(body)
    # Edge_claimed must be False
    assert body.get("edge_claimed") is False


def test_restarts_total_aggregated(tmp_path: Path) -> None:
    """restarts_total sums all proc restarts correctly."""
    procs = [
        {"name": "a", "state": "READY", "restarts": 3, "ready": True,
         "detail": {"kind": "none"}},
        {"name": "b", "state": "READY", "restarts": 2, "ready": True,
         "detail": {"kind": "none"}},
    ]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(procs=procs))
    resp = read_supervisor_status(p)
    body = json.loads(resp.body)
    assert body["restarts_total"] == 5


def test_extra_mounts_register_does_not_crash() -> None:
    """I: extra_mounts.register mounts supervisor route without sinking app boot."""
    app = FastAPI()
    from predict_service.extra_mounts import register
    try:
        register(app)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"extra_mounts.register raised unexpectedly: {exc}")

    # Verify /api/ops/supervisor path is now registered
    paths = [r.path for r in app.routes]
    assert "/api/ops/supervisor" in paths, (
        f"Expected /api/ops/supervisor in routes; got: {paths}"
    )


# ---------------------------------------------------------------------------
# New acceptance tests: kind-aware freshness scoring (ws4 workstream fix).
# ---------------------------------------------------------------------------

def _http_200_proc(name: str = "m1_api", *, probe_ok: bool = True) -> dict:
    """A proc whose readiness kind is http-200 (never writes a heartbeat file)."""
    return {
        "name": name,
        "state": "READY",
        "pid": 42,
        "restarts": 0,
        "ready": probe_ok,
        "detail": {
            "kind": "http",
            "url": "http://127.0.0.1:8099/health",
            "status": 200 if probe_ok else 503,
        },
    }


def _none_proc(name: str = "m1_simple", *, ready: bool = True) -> dict:
    """A proc whose readiness kind is 'none' (alive = ready, no heartbeat)."""
    return {
        "name": name,
        "state": "READY" if ready else "DOWN",
        "pid": 7,
        "restarts": 0,
        "ready": ready,
        "detail": {
            "kind": "none",
            "reason": "no probe; ready if alive",
        },
    }


def test_http_200_proc_with_null_heartbeat_scores_ok(tmp_path: Path) -> None:
    """http-200 service: heartbeat_age_sec=null + passing probe -> ok=True, fresh=ok."""
    procs = [_http_200_proc(probe_ok=True)]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    assert resp.status_code == 200, "Expected 200 for healthy http-200 proc"
    built = body["procs"][0]
    # heartbeat_age_sec must still be null (http services have no heartbeat file)
    assert built["heartbeat_age_sec"] is None, (
        "http-200 service must have heartbeat_age_sec=null; got %r"
        % built["heartbeat_age_sec"]
    )
    # But it must score ok, not degraded
    assert built.get("ok") is True, (
        "http-200 proc with passing probe must score ok=True; got %r" % built
    )
    assert built.get("fresh") == "ok", (
        "http-200 proc with passing probe must score fresh='ok'; got %r" % built.get("fresh")
    )
    assert built.get("degraded") is False, (
        "http-200 proc with passing probe must not be degraded; got %r" % built
    )
    assert body["all_ready"] is True, (
        "all_ready must be True when all probes pass; got %r" % body["all_ready"]
    )
    assert body["live"] is True, "live must be True when http probe passes"
    _assert_no_dollar(body)


def test_http_200_proc_failing_probe_scores_not_ok(tmp_path: Path) -> None:
    """http-200 service: failing probe (status!=200) -> ok=False, degraded=True."""
    procs = [_http_200_proc(probe_ok=False)]
    p = tmp_path / "s.json"
    # The supervisor wrote ready=False because the probe failed
    _write_doc(p, _fresh_doc(all_ready=False, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    built = body["procs"][0]
    assert built.get("ok") is False, (
        "http-200 proc with failing probe must score ok=False; got %r" % built
    )
    assert built.get("degraded") is True, (
        "http-200 proc with failing probe must be degraded=True; got %r" % built
    )
    assert body["all_ready"] is False, (
        "all_ready must be False when http probe fails; got %r" % body["all_ready"]
    )
    assert body["live"] is False, "live must be False when http probe fails"
    assert body["any_degraded"] is True


def test_none_kind_proc_with_null_heartbeat_scores_ok(tmp_path: Path) -> None:
    """kind='none' service: heartbeat_age_sec=null + ready=True -> ok=True."""
    procs = [_none_proc(ready=True)]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    assert resp.status_code == 200
    built = body["procs"][0]
    assert built["heartbeat_age_sec"] is None, "kind='none' has no heartbeat age"
    assert built.get("ok") is True, (
        "kind='none' ready proc must score ok=True; got %r" % built
    )
    assert built.get("degraded") is False
    assert body["all_ready"] is True
    assert body["live"] is True


def test_all_ready_true_iff_every_service_probe_healthy(tmp_path: Path) -> None:
    """all_ready=True iff every service is probe-healthy (mixed kinds)."""
    procs = [
        _http_200_proc("svc_http", probe_ok=True),
        _none_proc("svc_none", ready=True),
        {
            "name": "svc_heartbeat",
            "state": "READY",
            "pid": 10,
            "restarts": 0,
            "ready": True,
            "detail": {"kind": "heartbeat-file-fresh", "age_sec": 60.0, "fresh_sec": 300.0},
        },
    ]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    assert body["all_ready"] is True, (
        "all_ready must be True when every probe is healthy; got %r" % body["all_ready"]
    )
    assert body["live"] is True
    assert body["any_degraded"] is False
    for proc in body["procs"]:
        assert proc.get("ok") is True, "Every proc must score ok=True; got %r" % proc


def test_all_ready_false_when_one_http_probe_fails(tmp_path: Path) -> None:
    """all_ready=False as soon as one http probe fails, even if others are healthy."""
    procs = [
        _http_200_proc("svc_http_ok", probe_ok=True),
        _http_200_proc("svc_http_fail", probe_ok=False),
        _none_proc("svc_none", ready=True),
    ]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=False, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    assert body["all_ready"] is False, (
        "all_ready must be False when any probe fails; got %r" % body["all_ready"]
    )
    assert body["live"] is False
    assert body["any_degraded"] is True


def test_heartbeat_proc_null_age_still_degraded(tmp_path: Path) -> None:
    """Heartbeat service with age_sec=null remains degraded (file never written)."""
    procs = [
        {
            "name": "m5_heartbeat_missing",
            "state": "READY",
            "pid": 55,
            "restarts": 0,
            "ready": True,
            "detail": {"kind": "heartbeat-file-fresh", "fresh_sec": 300.0},
            # age_sec intentionally absent (heartbeat file never written)
        },
    ]
    p = tmp_path / "s.json"
    _write_doc(p, _fresh_doc(all_ready=True, procs=procs))

    resp = read_supervisor_status(p)
    body = json.loads(resp.body)

    built = body["procs"][0]
    assert built.get("ok") is False, (
        "heartbeat proc with null age_sec must score ok=False (file never written); "
        "got %r" % built
    )
    assert built.get("degraded") is True
    assert body["all_ready"] is False
    assert body["live"] is False
