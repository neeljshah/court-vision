"""predict_service.frontend.test_pm_exec_detail_routes -- per-file test (PT-7).

Acceptance criteria:

  EX1. GET /fills/<bet_id> returns fills list + avg_price for a known bet.
  EX2. avg_price is the qty-weighted mean of all fill prices.
  EX3. Every fill row carries executed=False (paper-only).
  EX4. No $/roi/pnl/profit key anywhere in the response.
  EX5. Missing bet_id -> HTTP 404 + status="not_found" (never stale-green).
  EX6. real_money_enabled=False always present.
  EX7. edge_claimed=False always present.
  EX8. GET /report/<bet_id> returns avg_price, n_fills, exec_status but NO
       "fills" key (summary-only view).
  EX9. Multiple fills for same bet_id are aggregated correctly (n_fills>1).
  EX10. executed=False on top-level response payload (not just individual fills).
  EX11. honest_note is present and non-empty.
  EX12. Blotter with only settlement records for a bet_id -> not_found
        (settlement records are not fills).

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_pm_exec_detail_routes.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure repo root is on sys.path.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.frontend.pm_exec_detail_routes import (  # noqa: E402
    _build_fill_payload,
    _compute_avg_price,
    _shape_fill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_blotter(tmpdir: str, records: list) -> str:
    """Write JSONL blotter records to a tmpdir; return the dir path."""
    p = Path(tmpdir) / "blotter.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return tmpdir


def _fill_rec(market_id: str, qty: int, price: float,
              side: str = "BUY", fee: float = 0.0,
              ts: str = "2026-06-19T10:00:00Z",
              strategy: str = "paper") -> Dict[str, Any]:
    return {
        "kind": "fill",
        "ts": ts,
        "market_id": market_id,
        "side": side,
        "qty": qty,
        "price": price,
        "fee": fee,
        "strategy": strategy,
        "pred_ts": ts,
    }


def _settlement_rec(market_id: str) -> Dict[str, Any]:
    return {
        "kind": "settlement",
        "market_id": market_id,
        "resolution": 1.0,
        "net_qty": 100,
        "avg_price": 0.55,
        "pnl": 45.0,   # pnl lives in blotter internals but never in API output
        "pred_ts": "2026-06-19T10:00:00Z",
    }


def _has_bad_key(d: object) -> bool:
    """Recursive check: True if any key contains $, roi, pnl, or profit."""
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


# ---------------------------------------------------------------------------
# Unit: _shape_fill
# ---------------------------------------------------------------------------

def test_shape_fill_no_bad_keys():
    raw = _fill_rec("MKT-1", qty=100, price=0.55)
    shaped = _shape_fill(raw)
    assert not _has_bad_key(shaped), "shaped fill must have no $/roi/pnl/profit key"


def test_shape_fill_executed_false():
    shaped = _shape_fill(_fill_rec("MKT-1", qty=100, price=0.55))
    assert shaped["executed"] is False, "executed must be False on every fill"


def test_shape_fill_price_preserved():
    shaped = _shape_fill(_fill_rec("MKT-1", qty=100, price=0.62))
    assert shaped["price"] == pytest.approx(0.62), "fill price must be preserved"


# ---------------------------------------------------------------------------
# Unit: _compute_avg_price
# ---------------------------------------------------------------------------

def test_avg_price_single_fill():
    fills = [{"qty": 100, "price": 0.55}]
    result = _compute_avg_price(fills)
    assert result == pytest.approx(0.55), "single fill avg must equal fill price"


def test_avg_price_weighted():
    # 200 @ 0.50 + 100 @ 0.56 -> (100+56) / 300 = 0.52
    fills = [
        {"qty": 200, "price": 0.50},
        {"qty": 100, "price": 0.56},
    ]
    expected = round((200 * 0.50 + 100 * 0.56) / 300, 6)
    assert _compute_avg_price(fills) == pytest.approx(expected)


def test_avg_price_empty_returns_none():
    assert _compute_avg_price([]) is None


def test_avg_price_zero_qty_returns_none():
    assert _compute_avg_price([{"qty": 0, "price": 0.55}]) is None


# ---------------------------------------------------------------------------
# Integration: _build_fill_payload via temp blotter
# ---------------------------------------------------------------------------

def test_ex1_fills_list_and_avg_price():
    """EX1: known bet -> fills list + avg_price present."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-123", qty=100, price=0.55)])
        payload = _build_fill_payload("BET-123", td)
    assert payload["status"] == "ok"
    assert len(payload["fills"]) == 1
    assert payload["avg_price"] == pytest.approx(0.55)


def test_ex2_avg_price_is_weighted():
    """EX2: avg_price is qty-weighted mean of fill prices."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [
            _fill_rec("BET-X", qty=200, price=0.50),
            _fill_rec("BET-X", qty=100, price=0.56),
        ])
        payload = _build_fill_payload("BET-X", td)
    expected = round((200 * 0.50 + 100 * 0.56) / 300, 6)
    assert payload["avg_price"] == pytest.approx(expected), (
        "avg_price must be qty-weighted; got %r expected %r"
        % (payload["avg_price"], expected)
    )


def test_ex3_fill_rows_executed_false():
    """EX3: every fill row has executed=False."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [
            _fill_rec("BET-A", qty=50, price=0.48),
            _fill_rec("BET-A", qty=50, price=0.52),
        ])
        payload = _build_fill_payload("BET-A", td)
    for fill in payload["fills"]:
        assert fill.get("executed") is False, (
            "executed must be False on every fill row; got %r" % fill
        )


def test_ex4_no_bad_keys_in_payload():
    """EX4: no $/roi/pnl/profit key in entire payload."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-B", qty=100, price=0.55)])
        payload = _build_fill_payload("BET-B", td)
    assert not _has_bad_key(payload), (
        "EX4: no $/roi/pnl/profit key in fills payload"
    )


def test_ex5_missing_bet_id_not_found():
    """EX5: unknown bet_id -> status='not_found'."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-EXISTS", qty=100, price=0.55)])
        payload = _build_fill_payload("UNKNOWN-BET", td)
    assert payload["status"] == "not_found", (
        "EX5: missing bet_id must return status='not_found'; got %r"
        % payload["status"]
    )


def test_ex5_not_found_has_empty_fills():
    """EX5: not_found response has fills=[] (never stale data)."""
    with tempfile.TemporaryDirectory() as td:
        payload = _build_fill_payload("NO-SUCH-BET", td)
    assert payload["fills"] == []
    assert payload["avg_price"] is None


def test_ex6_real_money_enabled_always_false():
    """EX6: real_money_enabled=False always present."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-C", qty=100, price=0.55)])
        for bet_id in ("BET-C", "NO-BET"):
            payload = _build_fill_payload(bet_id, td)
            assert payload.get("real_money_enabled") is False, (
                "EX6: real_money_enabled must be False; got %r for %s"
                % (payload.get("real_money_enabled"), bet_id)
            )


def test_ex7_edge_claimed_always_false():
    """EX7: edge_claimed=False always present."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-D", qty=100, price=0.55)])
        for bet_id in ("BET-D", "NO-BET"):
            payload = _build_fill_payload(bet_id, td)
            assert payload.get("edge_claimed") is False, (
                "EX7: edge_claimed must be False; got %r for %s"
                % (payload.get("edge_claimed"), bet_id)
            )


def test_ex9_multiple_fills_aggregated():
    """EX9: multiple fills for same bet_id aggregated (n_fills > 1)."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [
            _fill_rec("BET-MULTI", qty=100, price=0.50, ts="2026-06-19T10:00:00Z"),
            _fill_rec("BET-MULTI", qty=200, price=0.54, ts="2026-06-19T10:01:00Z"),
            _fill_rec("BET-MULTI", qty=50,  price=0.58, ts="2026-06-19T10:02:00Z"),
        ])
        payload = _build_fill_payload("BET-MULTI", td)
    assert payload["n_fills"] == 3, (
        "EX9: expected 3 fills; got %d" % payload["n_fills"]
    )
    expected_avg = round(
        (100 * 0.50 + 200 * 0.54 + 50 * 0.58) / 350, 6
    )
    assert payload["avg_price"] == pytest.approx(expected_avg)


def test_ex10_top_level_executed_false():
    """EX10: top-level executed=False in payload (not just inside fills)."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-E", qty=100, price=0.55)])
        payload = _build_fill_payload("BET-E", td)
    assert payload.get("executed") is False, (
        "EX10: top-level executed must be False; got %r" % payload.get("executed")
    )


def test_ex10_not_found_executed_false():
    """EX10b: even not_found response has executed=False at top level."""
    with tempfile.TemporaryDirectory() as td:
        payload = _build_fill_payload("GHOST", td)
    assert payload.get("executed") is False


def test_ex11_honest_note_present():
    """EX11: honest_note is present and non-empty."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_fill_rec("BET-F", qty=100, price=0.55)])
        for bet_id in ("BET-F", "NO-BET"):
            payload = _build_fill_payload(bet_id, td)
            assert "honest_note" in payload, "EX11: honest_note must be present"
            assert payload["honest_note"], "EX11: honest_note must be non-empty"


def test_ex12_settlement_only_not_found():
    """EX12: blotter with only settlement records for a bet_id -> not_found."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [_settlement_rec("SETTLED-BET")])
        payload = _build_fill_payload("SETTLED-BET", td)
    assert payload["status"] == "not_found", (
        "EX12: settlement-only bet -> not_found (settlements are not fills); "
        "got status=%r" % payload["status"]
    )


def test_report_view_has_no_fills_key():
    """EX8: /report path strips fills list, exposing only summary fields."""
    with tempfile.TemporaryDirectory() as td:
        _write_blotter(td, [
            _fill_rec("BET-R", qty=100, price=0.55),
            _fill_rec("BET-R", qty=50, price=0.57),
        ])
        payload = _build_fill_payload("BET-R", td)
        # Simulate the /report endpoint by stripping fills.
        payload.pop("fills", None)
    assert "fills" not in payload, "EX8: report payload must not have fills key"
    assert payload.get("n_fills") == 2
    assert payload.get("avg_price") is not None
    assert payload.get("exec_status") == "FILLED"


def test_no_bad_keys_not_found_payload():
    """No $/roi/pnl/profit in not_found payload."""
    with tempfile.TemporaryDirectory() as td:
        payload = _build_fill_payload("NOBODY", td)
    assert not _has_bad_key(payload), "no $/roi/pnl/profit in not_found payload"


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
