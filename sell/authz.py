"""sell.authz -- HMAC-signed API key issuance and verification.

Provides issue_key(tenant, plan) and verify_key(key) -> (tenant, plan) or
None. Keys are signed with HMAC-SHA256; the secret is read ONLY from the
environment (SELL_API_SECRET). No secret in code.

Key format (ASCII, URL-safe):
    <b64url(payload_json)>.<hex(hmac_sha256)>

payload_json is a canonical, deterministic JSON envelope::

    {"tenant": <str>, "plan": <str>, "issued_at": <int-epoch>, "v": 1}

INVARIANTS: <=300 LOC; ASCII only; no secrets in code; no $-edge field;
no I/O beyond os.environ; never raises on bad input (verify_key returns None).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Tuple

#: Environment variable that holds the HMAC signing secret.
#: NEVER hard-code a secret; with no env var set the gate can only DENY.
SECRET_ENV = "SELL_API_SECRET"

#: Payload version stamp -- bump when the payload shape changes.
_PAYLOAD_VERSION = 1

#: Separator between the b64url-encoded payload and the HMAC hex digest.
_SEP = "."

#: The product makes no dollar-edge claims. Carried on every key metadata dict.
EDGE_CLAIMED: bool = False


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #

def _read_secret() -> Optional[str]:
    """Return the signing secret from env, or None (DENY-safe default)."""
    val = os.environ.get(SECRET_ENV, "")
    return val if val else None


def _canonical(payload: dict) -> bytes:
    """Deterministic, ASCII JSON bytes of *payload* for signing/verifying."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: dict, secret: str) -> str:
    """Return the signed token string for *payload* using *secret*."""
    body = _canonical(payload)
    mac = hmac.new(secret.encode("ascii"), body, hashlib.sha256).hexdigest()
    return _b64url_encode(body) + _SEP + mac


def _verify(token: str, secret: str) -> Optional[dict]:
    """Return the decoded payload if *token* is valid, else None.

    Constant-time MAC comparison. Any malformation -> None (never raises).
    """
    try:
        head, mac = token.split(_SEP, 1)
        body = _b64url_decode(head)
        expected = hmac.new(secret.encode("ascii"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            return None
        payload = json.loads(body.decode("ascii"))
        return payload if isinstance(payload, dict) else None
    except (ValueError, TypeError, json.JSONDecodeError, Exception):
        return None


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def issue_key(tenant: str, plan: str, *, _secret: Optional[str] = None) -> str:
    """Issue a signed API key for *tenant* on *plan*.

    The secret is read from SELL_API_SECRET (env) unless *_secret* is provided
    (tests only). Raises ValueError if no secret is available.

    Args:
        tenant: opaque tenant identifier (no PII required; must be ASCII).
        plan:   plan label (e.g. "free", "pro", "enterprise").
        _secret: override for tests -- never used in production paths.

    Returns:
        Signed key string (ASCII, URL-safe).

    Raises:
        ValueError: when no signing secret is configured.
    """
    if not tenant or not isinstance(tenant, str):
        raise ValueError("tenant must be a non-empty string")
    if not plan or not isinstance(plan, str):
        raise ValueError("plan must be a non-empty string")
    secret = _secret or _read_secret()
    if not secret:
        raise ValueError(
            "No signing secret available. Set %s in the environment." % SECRET_ENV
        )
    payload = {
        "tenant": str(tenant),
        "plan": str(plan),
        "issued_at": int(time.time()),
        "v": _PAYLOAD_VERSION,
        "edge_claimed": EDGE_CLAIMED,  # always False -- no dollar-edge claim
    }
    return _sign(payload, secret)


def verify_key(
    key: str, *, _secret: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    """Verify *key*; return (tenant, plan) if valid, else None.

    Invalid, forged, or tampered keys return None (never raises). With no
    signing secret configured (SELL_API_SECRET unset), all keys are denied.

    Args:
        key:     The API key string to verify.
        _secret: Override for tests -- never used in production paths.

    Returns:
        (tenant, plan) tuple on success, None on any failure.
    """
    if not key or not isinstance(key, str):
        return None
    secret = _secret or _read_secret()
    if not secret:
        return None
    payload = _verify(key, secret)
    if payload is None:
        return None
    tenant = payload.get("tenant")
    plan = payload.get("plan")
    if not tenant or not plan:
        return None
    return (str(tenant), str(plan))


def key_metadata(
    key: str, *, _secret: Optional[str] = None
) -> Optional[dict]:
    """Return the full decoded payload for *key*, or None on any failure.

    Useful for auditing issued_at, version, and the edge_claimed flag.
    """
    if not key or not isinstance(key, str):
        return None
    secret = _secret or _read_secret()
    if not secret:
        return None
    return _verify(key, secret)


__all__ = [
    "SECRET_ENV",
    "EDGE_CLAIMED",
    "issue_key",
    "verify_key",
    "key_metadata",
]
