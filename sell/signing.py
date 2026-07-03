"""sell.signing -- HMAC-SHA256, tamper-evident signing of a TrackRecord dict.

sign(payload, secret) computes an HMAC-SHA256 over the CANONICAL JSON of the
record (sorted keys, no whitespace, ASCII) and returns a signed envelope that
wraps the original record plus a signature block. verify(record, secret) returns
True iff the embedded signature matches a freshly computed MAC over the record
body -- so a single mutated field FAILS verify (tamper-evident).

The secret is read ONLY from the environment (SELL_API_SECRET, shared with
sell.authz). With no secret available the record CANNOT be signed: sign() marks
it unsigned (signature=None, signed=False) and verify() returns False. No secret
ever lives in code.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets in code;
no I/O beyond os.environ; never raises on bad input (verify returns False).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

#: Shared with sell.authz -- the single HMAC signing secret, env-only.
SECRET_ENV = "SELL_API_SECRET"

#: Algorithm label stamped into the signature block.
SIG_ALGO = "HMAC-SHA256"

#: Key under which the signature block is attached to the signed envelope.
SIG_KEY = "signature"

#: Signature-block version stamp -- bump when the block shape changes.
SIG_VERSION = 1


def read_secret() -> Optional[str]:
    """Return the signing secret from env, or None (cannot-sign default)."""
    val = os.environ.get(SECRET_ENV, "")
    return val if val else None


def canonical_json(record: Dict[str, Any]) -> bytes:
    """Deterministic, ASCII JSON bytes of *record* for signing/verifying.

    Sorted keys + tight separators make the byte image stable regardless of
    dict insertion order, so the MAC is reproducible. Any embedded signature
    block is excluded by the caller before this is invoked.
    """
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        default=str,
    ).encode("ascii")


def _body_without_signature(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of *record* with the signature block removed."""
    return {k: v for k, v in (record or {}).items() if k != SIG_KEY}


def _mac(body: Dict[str, Any], secret: str) -> str:
    """HMAC-SHA256 hex digest over the canonical JSON of *body*."""
    return hmac.new(
        secret.encode("ascii"), canonical_json(body), hashlib.sha256
    ).hexdigest()


def sign(payload: Dict[str, Any], secret: Optional[str] = None) -> Dict[str, Any]:
    """Return a signed envelope wrapping *payload* (the TrackRecord dict).

    The signature is computed over the canonical JSON of *payload* (with any
    pre-existing signature block stripped first, so re-signing is idempotent).

    Args:
        payload: the record dict to sign (e.g. TrackRecord.to_dict()).
        secret:  override for tests; production reads SELL_API_SECRET from env.

    Returns:
        A new dict equal to *payload* plus a ``signature`` block::

            {"algo": "HMAC-SHA256", "value": <hex|None>,
             "signed": <bool>, "v": 1}

        When no secret is available the record is returned UNSIGNED
        (value=None, signed=False) -- it is never silently presented as signed.
    """
    body = _body_without_signature(payload if isinstance(payload, dict) else {})
    sec = secret if secret else read_secret()
    if not sec:
        block = {"algo": SIG_ALGO, "value": None, "signed": False,
                 "v": SIG_VERSION}
        out = dict(body)
        out[SIG_KEY] = block
        return out
    value = _mac(body, sec)
    out = dict(body)
    out[SIG_KEY] = {"algo": SIG_ALGO, "value": value, "signed": True,
                    "v": SIG_VERSION}
    return out


def verify(record: Dict[str, Any], secret: Optional[str] = None) -> bool:
    """Return True iff *record* carries a valid signature over its own body.

    Constant-time MAC comparison. A single mutated field changes the canonical
    body image and FAILS verification (tamper-evident). Any malformation, a
    missing / unsigned signature block, or an absent secret -> False (never
    raises).

    Args:
        record: a signed envelope produced by :func:`sign`.
        secret: override for tests; production reads SELL_API_SECRET from env.
    """
    if not isinstance(record, dict):
        return False
    block = record.get(SIG_KEY)
    if not isinstance(block, dict):
        return False
    if not block.get("signed") or not block.get("value"):
        return False
    sec = secret if secret else read_secret()
    if not sec:
        return False
    try:
        body = _body_without_signature(record)
        expected = _mac(body, sec)
        return hmac.compare_digest(expected, str(block.get("value")))
    except Exception:  # pragma: no cover - belt-and-suspenders, never raise
        return False


def is_signed(record: Dict[str, Any]) -> bool:
    """True iff *record* carries a signature block claiming signed=True."""
    if not isinstance(record, dict):
        return False
    block = record.get(SIG_KEY)
    return bool(isinstance(block, dict) and block.get("signed")
                and block.get("value"))


__all__ = [
    "SECRET_ENV",
    "SIG_ALGO",
    "SIG_KEY",
    "SIG_VERSION",
    "read_secret",
    "canonical_json",
    "sign",
    "verify",
    "is_signed",
]
