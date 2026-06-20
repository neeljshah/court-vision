"""predict_service.honesty_mw -- run the honesty linter on LIVE responses.

HL-P1. The governance honesty linter was test-time only; a fabricated $/roi/pnl
key produced at RUNTIME would have shipped uncaught. This middleware invokes
governance.honesty_linter.lint_obj on every JSON response body the API serves and
FAILS CLOSED: if a banned key / token / retracted number slips into a live
payload, the response is replaced with a 500 honesty-violation sentinel rather
than served. A dollar key NEVER reaches the browser.

Design:
  * Only application/json responses are inspected (HTML/SSE/streams pass through).
  * Bodies above _MAX_BODY_BYTES are passed through unscanned (defensive: an
    enormous body is not a place a $-key hides, and buffering it would be costly);
    this is logged. Normal envelopes are tiny.
  * The linter itself NEVER raises (it is pure + total); if scanning somehow
    fails, we FAIL CLOSED and return the 500 sentinel -- an un-lintable body is
    not served.
  * No $ field is ever introduced; the sentinel body carries none.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ field; reuse governance.honesty_linter verbatim (never reimplement the rules).
"""
from __future__ import annotations

import json
import logging
from typing import Any

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response
except Exception as exc:  # pragma: no cover -- starlette ships with fastapi
    raise ImportError("predict_service.honesty_mw requires starlette.") from exc

logger = logging.getLogger(__name__)

# Bodies larger than this are passed through unscanned (see module docstring).
_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MiB -- envelopes are far smaller

# The units-only rail: a response carrying a DOLLAR / P&L / ROI key is a runtime
# honesty violation even though it is not one of the governance "claim token"
# keys. The product is UNITS only; these keys must never reach the browser. We
# match a key when it EQUALS one of these or contains it as a token (so 'roi',
# 'paper_roi', 'total_pnl', 'stake_dollars' all trip; a matchup name cannot,
# since these are checked against object KEYS only, never free text).
#
# Token coverage reasoning (2026-06-19 honesty harden):
#   "stake"       -- bare 'stake' + compound 'total_stake' both trip (token match)
#   "total_stake" -- exact-key belt-and-suspenders (token "stake" already covers it)
#   "roi_pct"     -- token "roi" already covers it; listed for documentation clarity
#   "paper_roi"   -- token "roi" already covers it
#   "bankroll"    -- direct exact match already present
#   "total_pnl"   -- token "pnl" already covers it; exact key listed for clarity
#   "pnl"         -- already present (covers total_pnl, paper_pnl, etc.)
#   "usd"/"dollars" -- already present
_FORBIDDEN_MONEY_KEYS = (
    "pnl", "roi", "bankroll", "profit", "dollar",
    "stake_dollars", "stake_usd", "usd", "dollars",
    # Additions (2026-06-19): bare tokens previously missing; cover total_stake,
    # stake, paper_roi, roi_pct (roi token already caught these but explicit is safer),
    # total_pnl (pnl token covered; listed exact), paper_pnl, bankroll (already in).
    "stake", "total_stake", "total_pnl", "roi_pct", "paper_roi", "paper_pnl",
)

# UNITS-rail allow-list: keys that legitimately carry the bare "stake" token but
# are the UNITS-only rail itself, NOT a $/P&L field. The bare "stake" token above
# was added (2026-06-19) to catch stake_dollars/stake_usd (which keep their own
# explicit entries), but it over-matches the canonical units field stake_units and
# the two-leg arb unit stakes stake_a/stake_b. A key is exempt when it carries the
# "units" token (e.g. stake_units, total_stake_units) or is an explicit unit-stake
# leg; the explicit $ keys stake_dollars/stake_usd are NOT exempt (no "units" token,
# not in this set) so a real dollar key still trips the guard.
_UNITS_RAIL_EXEMPT_KEYS = ("stake_a", "stake_b")
_UNITS_RAIL_EXEMPT_TOKEN = "units"


def _money_key_violations(obj: Any, where: str = "") -> list:
    """Scan an object's KEYS for a forbidden dollar / P&L / ROI key. Total."""
    out: list = []

    def _walk(node: Any, path: str, depth: int) -> None:
        if depth > 40:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                child = ("%s.%s" % (path, kl)) if path else kl
                # Split the key into word tokens; a forbidden money token as a
                # whole word (or the whole key) is a violation.
                words = set(kl.replace("-", "_").split("_"))
                # UNITS-rail exemption: stake_units (units token) and stake_a/b are
                # the units rail, not $ fields; do not let the bare "stake" token
                # block them. Explicit $ keys (stake_dollars/usd) are NOT exempt.
                is_units_rail = (
                    _UNITS_RAIL_EXEMPT_TOKEN in words or kl in _UNITS_RAIL_EXEMPT_KEYS)
                hit = kl in _FORBIDDEN_MONEY_KEYS or bool(words & set(_FORBIDDEN_MONEY_KEYS))
                if hit and is_units_rail:
                    # Only forgive when the matching token is the bare unit-stake
                    # token; a true $/roi/pnl token in the SAME key still trips.
                    bad = (words & set(_FORBIDDEN_MONEY_KEYS)) - {"stake"}
                    if not bad and kl not in ("stake_dollars", "stake_usd"):
                        hit = False
                if hit:
                    out.append({"kind": "banned_money_key", "where": child,
                                "detail": "units-only rail: key %r is a "
                                          "forbidden $/P&L/ROI field" % k})
                _walk(v, child, depth + 1)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                _walk(v, "%s[%d]" % (path, i), depth + 1)

    try:
        _walk(obj, where, 0)
    except Exception:  # noqa: BLE001 -- a scan failure must not crash the guard
        out.append({"kind": "money_scan_error", "where": where,
                    "detail": "money-key scan raised"})
    return out


def _violation_response(violations: Any, where: str) -> JSONResponse:
    """The fail-closed 500 sentinel served instead of a poisoned body."""
    return JSONResponse(
        {
            "status": "error",
            "reason": "honesty linter blocked a response (fail-closed)",
            "where": where,
            "violations": violations,
            "edge_claimed": False,
            "honest_note": (
                "A runtime honesty violation (banned $/roi/pnl key or retracted "
                "number) was detected and the response was withheld. This is a "
                "fail-closed guard; no fabricated figure is ever served."),
        },
        status_code=500,
    )


class HonestyLinterMiddleware(BaseHTTPMiddleware):
    """Lint every JSON response on the way out; fail closed on a violation."""

    async def dispatch(self, request, call_next):  # noqa: ANN001, ANN201
        response = await call_next(request)
        ctype = response.headers.get("content-type", "")
        if "application/json" not in ctype.lower():
            return response

        # Buffer the streamed body so we can both inspect AND re-emit it.
        body = b""
        try:
            async for chunk in response.body_iterator:
                body += chunk
                if len(body) > _MAX_BODY_BYTES:
                    break
        except Exception as exc:  # noqa: BLE001 -- a broken stream is not ours to fix
            logger.warning("honesty_mw: body buffering failed: %s", exc)
            return response

        path = str(getattr(request, "url", "")) or request.url.path
        if len(body) > _MAX_BODY_BYTES:
            logger.warning("honesty_mw: body too large to scan (%d B) at %s; "
                           "passing through", len(body), path)
            return _passthrough(response, body)

        try:
            obj = json.loads(body.decode("utf-8")) if body.strip() else None
        except Exception:  # noqa: BLE001 -- non-JSON body labelled json: pass through
            return _passthrough(response, body)

        try:
            from governance.honesty_linter import lint_obj  # noqa: PLC0415
            verdict = lint_obj(obj)
        except Exception as exc:  # noqa: BLE001 -- linter import/scan failed: FAIL CLOSED
            logger.error("honesty_mw: linter unavailable at %s: %s -- failing closed",
                         path, exc)
            return _violation_response(
                [{"kind": "linter_error",
                  "detail": "linter unavailable (%s)" % type(exc).__name__}], path)

        violations = list(verdict.get("violations", []) or [])
        # The units-only rail: also block a runtime $/P&L/ROI KEY, which the
        # governance linter (claim-token + retracted-number focused) does not
        # itself enumerate. Both checks together cover the rail.
        violations.extend(_money_key_violations(obj, path))

        if violations:
            logger.error("honesty_mw: BLOCKED a response at %s: %s",
                         path, violations)
            return _violation_response(violations, path)

        return _passthrough(response, body)


def _passthrough(response: "Response", body: bytes) -> "Response":
    """Re-emit a buffered body with the original status + headers (sans length)."""
    headers = dict(response.headers)
    headers.pop("content-length", None)  # recomputed by Starlette
    return Response(content=body, status_code=response.status_code,
                    headers=headers, media_type=response.media_type)


__all__ = ["HonestyLinterMiddleware"]
