"""governance.realmoney_gate -- the signed, default-DENY real-money AUTHORIZATION gate.

This is the ENFORCEMENT layer over the conservative, decision-only eligibility
arithmetic in ``scripts.platformkit.pm_trading.realmoney_gate`` (M4). It does NOT
replace that gate -- it WRAPS it and adds a hard default-DENY plus a signed
authorization token bound to the eligibility snapshot.

WHAT IT DOES (and pointedly does NOT do):
  * It NEVER authorizes a bet and NEVER moves money. ``authorize`` answers exactly
    one question: may a real-money MODE even be ENABLED? Placing any individual bet
    is a separate, human, downstream act -- this gate only governs the mode switch.
  * authorized=True requires ALL THREE, conjunctively:
        (1) the M4 decision-only gate says eligible=True (the paper CLV record
            clears the pre-registered bar), AND
        (2) a human has explicitly approved (human_approved=True), AND
        (3) a VALID signed authorization token is presented, bound to the exact
            eligibility snapshot (so a stale / forged / tampered token is rejected).
    Absent ANY of the three -> authorized=False (DEFAULT-DENY) with a clear reason.
  * The signing secret is NEVER in code: it is read from the environment
    (``GOVERNANCE_REALMONEY_SECRET``). With no secret set, no token can be verified,
    so the gate can only DENY -- the safe default.

INVARIANTS: build only under governance/; <=300 LOC; ASCII only; no secrets in
code; no I/O beyond reading the M4 ledger via its own loader; never flips a flag;
never places or authorizes a bet.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, List, Optional

from governance import policy as _policy
from scripts.platformkit.pm_trading import realmoney_gate as _rmg

#: Version of THIS authorization layer (distinct from the M4 eligibility version).
AUTHZ_VERSION = "governance.realmoney_gate.v1"

#: Environment variable holding the HMAC signing secret. NEVER hard-code a secret.
SECRET_ENV = "GOVERNANCE_REALMONEY_SECRET"

#: Token format: "<b64url(payload_json)>.<hex(hmac_sha256)>". ASCII only.
_TOKEN_SEP = "."


# --------------------------------------------------------------------------- #
# Eligibility snapshot -- the minimal, stable fingerprint a token is bound to.  #
# --------------------------------------------------------------------------- #
def _snapshot(eligibility: Dict[str, Any]) -> Dict[str, Any]:
    """The canonical, token-bound fingerprint of an eligibility result.

    A token authorizes ONLY the exact eligibility snapshot it was signed over. We
    bind the decision (eligible), the honest metrics, the gate version, and the
    pre-registered criteria. If any of these change, a previously issued token no
    longer verifies against the new snapshot -- stale authorizations cannot leak.
    """
    metrics = eligibility.get("metrics") or {}
    return {
        "eligible": bool(eligibility.get("eligible", False)),
        "gate_version": eligibility.get("gate_version", _rmg.GATE_VERSION),
        "authz_version": AUTHZ_VERSION,
        "metrics": {
            "n": metrics.get("n"),
            "clv_mean": metrics.get("clv_mean"),
            "clv_lb95": metrics.get("clv_lb95"),
            "pct_beat_close": metrics.get("pct_beat_close"),
            "true_close_frac": metrics.get("true_close_frac"),
        },
        "criteria": _policy.REALMONEY_THRESHOLDS,
    }


def _canonical(payload: Dict[str, Any]) -> bytes:
    """Deterministic, ASCII JSON encoding of *payload* for signing/verifying."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _b64url(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    import base64
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _read_secret(secret: Optional[str]) -> Optional[str]:
    """The signing secret: explicit arg wins, else the env var, else None.

    Returning None is the SAFE default: with no secret, no token can be verified,
    so the gate can only DENY. The secret is NEVER stored in code.
    """
    if secret:
        return secret
    env = os.environ.get(SECRET_ENV)
    return env if env else None


def sign_token(payload: Dict[str, Any], secret: str) -> str:
    """Sign *payload* into an HMAC-SHA256 authorization token.

    The token is ``<b64url(canonical_json)>.<hex(hmac)>``. The same canonical JSON
    encoding is used on verify, so the signature covers the exact payload bytes.
    Raises ValueError if no secret is provided -- you cannot sign without one.
    """
    if not secret:
        raise ValueError("sign_token requires a non-empty secret")
    body = _canonical(payload)
    mac = hmac.new(secret.encode("ascii"), body, hashlib.sha256).hexdigest()
    return _b64url(body) + _TOKEN_SEP + mac


def verify_token(token: Optional[str], secret: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verify *token* against *secret*; return the decoded payload or None.

    Returns the payload dict iff the token is well-formed AND its HMAC matches
    (constant-time compare). Any tampering with the body or the signature, a
    malformed token, or a missing secret -> None (DENY). NEVER raises.
    """
    if not token or not secret:
        return None
    try:
        body_b64, mac = token.split(_TOKEN_SEP, 1)
        body = _b64url_decode(body_b64)
        expected = hmac.new(secret.encode("ascii"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            return None
        payload = json.loads(body.decode("ascii"))
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _token_authorizes(token: Optional[str], snapshot: Dict[str, Any],
                      secret: Optional[str]) -> bool:
    """True iff *token* is valid AND bound to exactly *snapshot* (no drift)."""
    payload = verify_token(token, secret)
    if payload is None:
        return False
    # A valid token must carry the SAME snapshot we just computed; a token signed
    # over a stale / different eligibility cannot authorize the current state.
    return _canonical(payload) == _canonical(snapshot)


def authorize(
    *,
    summary: Optional[Dict[str, Any]] = None,
    rows: Optional[Any] = None,
    human_approved: bool = False,
    token: Optional[str] = None,
    secret: Optional[str] = None,
    eligibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Default-DENY real-money mode authorization. NEVER authorizes a bet.

    Returns::

        {
          "authorized": bool,        # DEFAULT False; True iff ALL of: eligible AND
                                     #   human_approved AND a valid bound token.
          "eligibility": {...},      # from pm_trading.realmoney_gate.evaluate (M4)
          "snapshot": {...},         # the token-bound eligibility fingerprint
          "token_valid": bool,       # was a valid, snapshot-bound token presented?
          "human_approved": bool,    # echoed human flip
          "reasons": [str, ...],     # why DENIED (empty iff authorized)
          "authz_version": AUTHZ_VERSION,
          "authorizes_bet": False,   # ALWAYS False -- governs mode switch only
        }

    *eligibility* may be passed directly (tests / callers holding it); otherwise it
    is computed by the M4 decision-only gate from *rows* / *summary*. The signing
    secret comes from *secret* or the ``GOVERNANCE_REALMONEY_SECRET`` env var; with
    no secret, no token verifies, so the gate can only DENY.
    """
    if eligibility is None:
        eligibility = _rmg.evaluate(summary=summary, rows=rows)
    snapshot = _snapshot(eligibility)
    secret_val = _read_secret(secret)

    reasons: List[str] = []

    eligible = bool(eligibility.get("eligible", False))
    if not eligible:
        # Surface the M4 reasons so the denial is explainable, not opaque.
        m4_reasons = eligibility.get("reasons") or ["paper CLV record not eligible"]
        reasons.append("M4 eligibility gate says ineligible: " + "; ".join(m4_reasons))

    if not human_approved:
        reasons.append("no human approval: a human flip is required (human_approved=False)")

    if secret_val is None:
        reasons.append(
            "no signing secret: set %s in the environment; without it no "
            "authorization token can be verified (default-DENY)" % SECRET_ENV)
        token_valid = False
    else:
        token_valid = _token_authorizes(token, snapshot, secret_val)
        if not token_valid:
            reasons.append(
                "no valid authorization token bound to the current eligibility "
                "snapshot (absent / forged / tampered / stale)")

    # DEFAULT-DENY: authorized only when every guard passes.
    authorized = eligible and bool(human_approved) and token_valid

    return {
        "authorized": bool(authorized),
        "eligibility": eligibility,
        "snapshot": snapshot,
        "token_valid": bool(token_valid),
        "human_approved": bool(human_approved),
        "reasons": reasons,
        "authz_version": AUTHZ_VERSION,
        # Keystone invariant: this gate governs whether a real-money MODE may be
        # enabled. It NEVER authorizes or places an individual bet, and a human
        # flip plus a valid signed token are ALWAYS required.
        "authorizes_bet": False,
        "honest_note": ("Default-DENY real-money authorization. authorized=True "
                        "only when the M4 paper-CLV gate is eligible AND a human "
                        "approved AND a valid signed token bound to that exact "
                        "eligibility is presented. It never places or authorizes a "
                        "bet; it governs the mode switch only."),
    }


__all__ = [
    "authorize",
    "sign_token",
    "verify_token",
    "AUTHZ_VERSION",
    "SECRET_ENV",
]
