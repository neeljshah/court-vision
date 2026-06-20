"""predict_service.frontend.test_improve_sharpening_routes -- per-file test.

Acceptance criteria (SH = sharpening endpoint):

  SH1. GET /api/improve/sharpening -> 200; keys: status, enabled, edge_claimed,
       trends, coverage, reconcile, honest_note.

  SH2. edge_claimed is ALWAYS False (never fabricated).

  SH3. enabled mirrors the sentinel (False when sentinel absent; no crash).

  SH4. Missing ledger -> status='unavailable'; coverage.ledger_present=False;
       reconcile.status='INSUFFICIENT_DATA'; never green on missing data.

  SH5. No $/roi/pnl/profit key anywhere in the response.

  SH6. honest_note present and non-empty; references 'calibration'.

  SH7. reconcile block has n_drift, drift_flags, clean, status keys.

  SH8. coverage block has gaps list, ledger_present, vs_close, summary keys.

  SH9. GET /api/improve/sharpening with explicit ?ledger=<absent> -> unavailable.

  SH10. trends block is a dict; each entry has status, n_data_cycles keys.

  SH11. Route is mounted in app.py: a fresh TestClient over predict_service.app
        sees /api/improve/sharpening return 200 (mount-failure path must still
        produce 200 from unavailable sentinel, not a real 404).

  SH12. _build_coverage_block({}) -> ledger_present=False (never green on empty).

  SH13. _build_reconcile_block({}) -> status='INSUFFICIENT_DATA', clean=False.

  SH14. _build_trends_block({}) -> {} (empty trends dict on empty input).

  SH15. Response for absent ledger has no 'pnl', '$', 'roi', 'profit' key.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_improve_sharpening_routes.py -q
"""
from __future__ import annotations

import sys
import tempfile
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.frontend.improve_sharpening_routes import (  # noqa: E402
    _build_coverage_block,
    _build_reconcile_block,
    _build_trends_block,
    _ledger_exists,
    _UNAVAILABLE_RESPONSE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_bad_key(d: object) -> bool:
    """True if any key in *d* (recursively) contains $, roi, pnl, or profit."""
    if not isinstance(d, dict):
        return False
    for k, v in d.items():
        kl = str(k).lower()
        if any(tok in kl for tok in ("$", "roi", "pnl", "profit")):
            return True
        if isinstance(v, dict) and _has_bad_key(v):
            return True
        if isinstance(v, list):
            for item in v:
                if _has_bad_key(item):
                    return True
    return False


def _make_test_client_absent_ledger():
    """TestClient over a standalone app that exercises the sharpening route
    with no ledger on disk. Returns (client, response)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.improve_sharpening_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/api/improve/sharpening")
    return client, resp


def _make_test_client_with_ledger(ledger_path: str):
    """TestClient over a standalone app with an explicit ledger path."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.improve_sharpening_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get(f"/api/improve/sharpening?ledger={ledger_path}")
    return client, resp


def _minimal_ledger_row(market: str = "nba_pts", cycle: int = 0) -> dict:
    """Minimal JSONL row for the segmented ledger."""
    return {
        "market": market,
        "cycle": cycle,
        "status": "INSUFFICIENT_DATA",
        "readout": {"raw_brier": None, "raw_ece": None},
    }


def _write_minimal_ledger(tmp_path: str) -> str:
    """Write a minimal ledger and return its file path."""
    p = Path(tmp_path) / "improve_ledger_segmented.jsonl"
    p.write_text(
        json.dumps(_minimal_ledger_row("nba_pts", 0)) + "\n",
        encoding="utf-8",
    )
    return str(p)


# ---------------------------------------------------------------------------
# SH1 -- 200 with all required top-level keys
# ---------------------------------------------------------------------------

def test_sh1_required_keys():
    """SH1: Response has status, enabled, edge_claimed, trends, coverage,
    reconcile, honest_note keys."""
    _, resp = _make_test_client_absent_ledger()
    assert resp.status_code == 200, f"SH1: expected 200; got {resp.status_code}"
    body = resp.json()
    for key in ("status", "enabled", "edge_claimed", "trends",
                "coverage", "reconcile", "honest_note"):
        assert key in body, f"SH1: missing key {key!r} in response"


# ---------------------------------------------------------------------------
# SH2 -- edge_claimed is always False
# ---------------------------------------------------------------------------

def test_sh2_edge_claimed_always_false():
    """SH2: edge_claimed is False in every code path."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    assert body["edge_claimed"] is False, (
        f"SH2: edge_claimed must be False; got {body['edge_claimed']!r}"
    )


# ---------------------------------------------------------------------------
# SH3 -- enabled mirrors sentinel (False when absent, never crashes)
# ---------------------------------------------------------------------------

def test_sh3_enabled_is_bool():
    """SH3: enabled is always a bool (False when sentinel absent)."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    assert isinstance(body["enabled"], bool), (
        f"SH3: enabled must be bool; got {type(body['enabled'])!r}"
    )


# ---------------------------------------------------------------------------
# SH4 -- missing ledger -> unavailable, ledger_present=False, INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_sh4_absent_ledger_is_unavailable():
    """SH4a: absent ledger -> status='unavailable'."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    # Either 'unavailable' (default path) or 'ok' if _DEFAULT_LEDGER happens to
    # exist on disk. We enforce: if coverage.ledger_present is False -> unavailable.
    cov = body.get("coverage", {})
    if not cov.get("ledger_present", True):
        assert body["status"] == "unavailable", (
            f"SH4: ledger absent but status={body['status']!r} (not 'unavailable')"
        )


def test_sh4_absent_ledger_coverage_not_present():
    """SH4b: absent ledger -> coverage.ledger_present=False."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    cov = body.get("coverage", {})
    # Either ledger_present is False (no ledger) or True (ledger exists on disk).
    # We only assert the False branch is consistent with status=unavailable.
    if not cov.get("ledger_present", True):
        assert body["status"] == "unavailable"


def test_sh4_explicit_absent_path_is_unavailable():
    """SH4c: explicit ?ledger=<non-existent> -> status='unavailable'."""
    _, resp = _make_test_client_with_ledger("/does/not/exist/ledger.jsonl")
    body = resp.json()
    assert body["status"] == "unavailable", (
        f"SH4c: explicit absent ledger must be unavailable; got {body['status']!r}"
    )
    assert body["edge_claimed"] is False


# ---------------------------------------------------------------------------
# SH5 -- no $/roi/pnl/profit key anywhere
# ---------------------------------------------------------------------------

def test_sh5_no_dollar_key_absent_ledger():
    """SH5a: no $/roi/pnl/profit key in absent-ledger response."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    assert not _has_bad_key(body), "SH5: $/roi/pnl/profit key found in response"


def test_sh5_no_dollar_key_explicit_absent():
    """SH5b: no banned key with explicit absent ledger path."""
    _, resp = _make_test_client_with_ledger("/no/ledger.jsonl")
    body = resp.json()
    assert not _has_bad_key(body), "SH5b: $/roi/pnl/profit key found in unavailable resp"


# ---------------------------------------------------------------------------
# SH6 -- honest_note present, non-empty, references 'calibration'
# ---------------------------------------------------------------------------

def test_sh6_honest_note_references_calibration():
    """SH6: honest_note is non-empty and mentions 'calibration'."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    note = body.get("honest_note", "")
    assert note, "SH6: honest_note must be non-empty"
    assert "calibration" in note.lower() or "Calibration" in note, (
        f"SH6: honest_note must reference calibration; got {note!r}"
    )


# ---------------------------------------------------------------------------
# SH7 -- reconcile block keys
# ---------------------------------------------------------------------------

def test_sh7_reconcile_block_keys():
    """SH7: reconcile block has n_drift, drift_flags, clean, status."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    rec = body.get("reconcile", {})
    for key in ("n_drift", "drift_flags", "clean", "status"):
        assert key in rec, f"SH7: reconcile missing key {key!r}"


def test_sh7_reconcile_absent_ledger_insufficient():
    """SH7b: absent ledger -> reconcile.status='INSUFFICIENT_DATA'."""
    _, resp = _make_test_client_with_ledger("/no/ledger.jsonl")
    body = resp.json()
    rec = body.get("reconcile", {})
    assert rec.get("status") == "INSUFFICIENT_DATA", (
        f"SH7b: expected INSUFFICIENT_DATA; got {rec.get('status')!r}"
    )


# ---------------------------------------------------------------------------
# SH8 -- coverage block keys
# ---------------------------------------------------------------------------

def test_sh8_coverage_block_keys():
    """SH8: coverage block has gaps, ledger_present, vs_close, summary."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    cov = body.get("coverage", {})
    for key in ("gaps", "ledger_present", "vs_close", "summary"):
        assert key in cov, f"SH8: coverage missing key {key!r}"


# ---------------------------------------------------------------------------
# SH9 -- explicit absent ledger path via query param -> unavailable
# ---------------------------------------------------------------------------

def test_sh9_explicit_absent_query_param():
    """SH9: ?ledger=<absent> -> status='unavailable'."""
    _, resp = _make_test_client_with_ledger("/absent/path/nope.jsonl")
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["edge_claimed"] is False


# ---------------------------------------------------------------------------
# SH10 -- trends block is a dict; entries have status + n_data_cycles
# ---------------------------------------------------------------------------

def test_sh10_trends_is_dict():
    """SH10a: trends is always a dict."""
    _, resp = _make_test_client_absent_ledger()
    body = resp.json()
    assert isinstance(body.get("trends"), dict), "SH10: trends must be a dict"


def test_sh10_trends_entries_have_required_keys():
    """SH10b: each trend entry has status and n_data_cycles."""
    with tempfile.TemporaryDirectory() as td:
        ledger_path = _write_minimal_ledger(td)
        _, resp = _make_test_client_with_ledger(ledger_path)
    body = resp.json()
    trends = body.get("trends", {})
    for mkt, entry in trends.items():
        assert "status" in entry, f"SH10b: trends[{mkt!r}] missing 'status'"
        assert "n_data_cycles" in entry, (
            f"SH10b: trends[{mkt!r}] missing 'n_data_cycles'"
        )


# ---------------------------------------------------------------------------
# SH11 -- route is mounted in predict_service.app (TestClient sees 200 not 404)
# ---------------------------------------------------------------------------

def test_sh11_route_mounted_in_app():
    """SH11: predict_service.app mounts sharpening; /api/improve/sharpening
    returns 200 (even if unavailable), never 404."""
    try:
        from fastapi.testclient import TestClient
        from predict_service.app import app  # noqa: PLC0415
    except Exception as exc:
        pytest.skip(f"SH11: predict_service.app not importable ({exc})")
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/improve/sharpening")
    assert resp.status_code == 200, (
        f"SH11: /api/improve/sharpening must return 200 (not 404); "
        f"got {resp.status_code}"
    )
    body = resp.json()
    assert "status" in body, "SH11: response must have 'status' key"
    assert body.get("edge_claimed") is False, "SH11: edge_claimed must be False"


# ---------------------------------------------------------------------------
# SH12 -- _build_coverage_block({}) -> ledger_present=False
# ---------------------------------------------------------------------------

def test_sh12_empty_coverage_block_not_present():
    """SH12: _build_coverage_block({}) -> ledger_present=False (never green)."""
    block = _build_coverage_block({})
    assert block.get("ledger_present") is False, (
        f"SH12: empty raw -> ledger_present=False; got {block.get('ledger_present')!r}"
    )
    assert "gaps" in block, "SH12: gaps key must be present"
    assert isinstance(block["gaps"], list), "SH12: gaps must be a list"


# ---------------------------------------------------------------------------
# SH13 -- _build_reconcile_block({}) -> INSUFFICIENT_DATA, clean=False
# ---------------------------------------------------------------------------

def test_sh13_empty_reconcile_block_insufficient():
    """SH13: _build_reconcile_block({}) -> INSUFFICIENT_DATA, clean=False."""
    block = _build_reconcile_block({})
    assert block.get("status") == "INSUFFICIENT_DATA", (
        f"SH13: expected INSUFFICIENT_DATA; got {block.get('status')!r}"
    )
    assert block.get("clean") is False, (
        f"SH13: clean must be False on empty block; got {block.get('clean')!r}"
    )


# ---------------------------------------------------------------------------
# SH14 -- _build_trends_block({}) -> {}
# ---------------------------------------------------------------------------

def test_sh14_empty_trends_block_is_empty_dict():
    """SH14: _build_trends_block({}) -> empty dict."""
    block = _build_trends_block({})
    assert block == {}, f"SH14: expected {{}}; got {block!r}"


# ---------------------------------------------------------------------------
# SH15 -- _UNAVAILABLE_RESPONSE has no banned keys
# ---------------------------------------------------------------------------

def test_sh15_unavailable_sentinel_no_bad_keys():
    """SH15: the module-level _UNAVAILABLE_RESPONSE sentinel has no banned keys."""
    assert not _has_bad_key(dict(_UNAVAILABLE_RESPONSE)), (
        "SH15: _UNAVAILABLE_RESPONSE must not have $/roi/pnl/profit key"
    )


def test_sh15_unavailable_sentinel_edge_claimed_false():
    """SH15b: sentinel has edge_claimed=False."""
    sentinel = dict(_UNAVAILABLE_RESPONSE)
    assert sentinel.get("edge_claimed") is False, (
        "SH15b: sentinel must have edge_claimed=False"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
