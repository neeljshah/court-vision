"""test_execution_router_honesty.py -- Phase-7 honesty contract (TC).

CONTRACT UNDER TEST
-------------------
The product is a CALIBRATED predictor expressed in UNITS / probability.
NO dollar / roi / pnl / stake / bankroll field may reach the JSON of any
api/execution_router.py response. (.claude/rules/no-edge-claims.md)

DISCOVERY (2026-06-19, read-only)
---------------------------------
api/execution_router.py currently VIOLATES this contract:

  * /api/portfolio/summary -> the except-fallback returns a literal dict with
    top-level keys "bankroll", "total_pnl", "roi", "drawdown_pct"
    (api/execution_router.py:51-61). Because betting_portfolio.BettingPortfolio
    does NOT exist (only module-level functions), _load_portfolio() ALWAYS
    raises ImportError, so this fallback is the ONLY thing this endpoint ever
    returns -- every response carries $/roi/pnl keys.

  * /api/portfolio/close -> returns {"clv": ..., "pnl": req.result}
    (api/execution_router.py:123) -- leaks a pnl key.

  * /api/execution/quote and /api/portfolio/log echo a "stake" the caller sent.

api/ is HUMAN-GATED (.claude/rules/human-gated-paths.md): we do NOT edit it.
So the contract assertion that SHOULD pass is marked xfail(strict=False) with a
PROPOSED fix. A promotion check (test_xfail_promotion_guard) fails loudly the
day the source is fixed, so the xfail can never silently rot.

PROPOSED FIX (for the human to apply in api/execution_router.py)
----------------------------------------------------------------
1. Drop the $-bearing keys from the portfolio_summary fallback; return only
   unit/probability/count fields, e.g.:
       {"units_pnl": 0.0, "clv_avg": 0.0, "open_count": 0,
        "drawdown_pct": 0.0, "win_rate": 0.0, "sharpe": 0.0}
   (no "bankroll", no "total_pnl", no "roi").
2. portfolio_close: return {"clv": result} -- drop the "pnl" key.
3. Run every endpoint response through a shared _strip_money_keys() scrubber
   (the BANNED_KEYS set below) before returning.
"""
from __future__ import annotations

import pytest

# Money / edge keys that must never reach API JSON (units / probability only).
BANNED_KEYS = {
    "roi", "roi_pct", "pnl", "total_pnl", "stake", "total_stake",
    "bankroll", "profit", "profit_loss", "usd", "dollars", "daily_pnl",
    "total_wagered",
}


def _client():
    """Mount ONLY execution_router on a throwaway FastAPI app."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.execution_router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _banned_keys_in(obj, path="$"):
    """Recursively collect every banned key found anywhere in a JSON object."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in BANNED_KEYS:
                found.append(f"{path}.{k}")
            found.extend(_banned_keys_in(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_banned_keys_in(v, f"{path}[{i}]"))
    return found


# ---------------------------------------------------------------------------
# Desired honest contract (xfail until the human applies the PROPOSED fix).
# strict=False so it flips to XPASS (not an ERROR) the moment the fix lands.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="api/execution_router.py:51-61 fallback emits bankroll/total_pnl/roi; "
           "api/ is human-gated -- see module PROPOSED FIX. strict=False.",
    strict=False,
)
def test_portfolio_summary_has_no_money_keys():
    resp = _client().get("/api/portfolio/summary")
    assert resp.status_code == 200
    leaked = _banned_keys_in(resp.json())
    assert not leaked, f"portfolio/summary leaked money keys: {leaked}"


@pytest.mark.xfail(
    reason="api/execution_router.py:123 portfolio/close success-path returns a "
           "literal {'clv':..., 'pnl': req.result}; the 'pnl' key violates the "
           "units-only contract. api/ is human-gated -- see module PROPOSED FIX. "
           "strict=False.",
    strict=False,
)
def test_portfolio_close_source_has_no_pnl_key():
    """Assert the LATENT success-path leak directly in the source.

    NB: at runtime /api/portfolio/close currently 500s because
    betting_portfolio.BettingPortfolio does not exist (see DISCOVERY notes),
    so the leak is unreachable-but-latent. We pin it against the source text so
    the xfail tracks the real defect rather than the incidental 500.
    """
    import inspect
    from api import execution_router

    src = inspect.getsource(execution_router.portfolio_close)
    # The honest contract: the success return must NOT mint a 'pnl' key.
    assert '"pnl"' not in src and "'pnl'" not in src, (
        "portfolio_close still constructs a 'pnl' key in its return -- "
        "PROPOSED FIX: return {'clv': result} only."
    )


# ---------------------------------------------------------------------------
# PROMOTION GUARD -- proves the violation still exists. The day the source is
# fixed this test FAILS, signalling "remove the two xfails above". This is the
# add-promotion-check the task requires so a silent xfail can't pass unnoticed.
# ---------------------------------------------------------------------------

def test_xfail_promotion_guard():
    """While the source still leaks, the summary endpoint MUST carry a money key.

    When this assertion starts failing, the human has fixed execution_router.py
    and the two xfail tests above should be un-xfailed (they will XPASS).
    """
    resp = _client().get("/api/portfolio/summary")
    assert resp.status_code == 200
    leaked = _banned_keys_in(resp.json())
    assert leaked, (
        "execution_router portfolio/summary NO LONGER leaks money keys -- "
        "PROMOTE: remove @xfail from test_portfolio_summary_has_no_money_keys "
        "and test_portfolio_close_has_no_money_keys, then delete this guard."
    )


def test_banned_key_scrubber_self_check():
    """The scrubber itself must catch nested money keys (guards the guard)."""
    sample = {"ok": 1, "nested": {"roi": 0.1, "list": [{"pnl": 5.0}]}}
    leaked = _banned_keys_in(sample)
    assert "$.nested.roi" in leaked
    assert "$.nested.list[0].pnl" in leaked
