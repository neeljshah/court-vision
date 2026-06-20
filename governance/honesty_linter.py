"""governance.honesty_linter -- enforce the no-edge-claims invariants on output.

Scans any user-facing string or JSON-like object for honesty violations and
returns a structured verdict. This is the gate that catches a fabrication before
it ships: a RETRACTED measurement-artifact number presented as a live result, a
$-edge style claim, or a banned key (``$edge``, ``roi_edge``, ...). A poisoned
report MUST come back ``clean=False``.

Honesty rules enforced (all read from :mod:`governance.policy`, never redefined):
  * BANNED NUMBERS (the six retracted figures) are violations UNLESS they sit in
    an explicit retraction / citation context -- the honesty docs are allowed to
    name an artifact in order to retract it. Retraction context is evaluated per
    string, so naming the artifact inside "(retracted ...)" framing is fine but a
    bare live number is not.
  * BANNED TOKENS (claim strings like "guaranteed profit") are violations even in
    a retraction context -- a $-edge field is wrong no matter the framing.
  * BANNED KEYS: any mapping key that is, or contains, a $-edge style token. The
    product carries probability / EV only; there is no dollar-edge field by
    design (predict_service.contracts has none).

PURE + TOTAL: no I/O, no decisions about money, never authorizes a bet, never
flips a flag, and NEVER raises -- a linter that crashes is a linter that gets
disabled, so every path is defensive and returns a verdict.

INVARIANTS: build only under governance/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List

from governance import policy as _pol

LINTER_VERSION = "governance.honesty_linter.v1"

# How deep we recurse into a nested object before giving up (defensive; real
# envelopes are shallow, but a cyclic / pathological object must not hang us).
_MAX_DEPTH = 40


def _violation(kind: str, where: str, detail: str) -> Dict[str, str]:
    return {"kind": kind, "where": where, "detail": detail}


def _scan_string(s: str, where: str) -> List[Dict[str, str]]:
    """Lint one string. Banned numbers respect retraction; tokens never do."""
    out: List[Dict[str, str]] = []
    try:
        text = s if isinstance(s, str) else str(s)
    except Exception:  # pragma: no cover - str() on a hostile object
        return out
    # Banned NUMBERS -- whitelisted only inside explicit retraction framing.
    for tok in _pol.find_banned_numbers(text, respect_retraction=True):
        out.append(_violation(
            "banned_number", where,
            "retracted figure %s presented without retraction context" % tok))
    # Banned TOKENS -- never whitelisted; a $edge claim is always wrong.
    for tok in _pol.find_banned_tokens(text):
        out.append(_violation(
            "banned_token", where,
            "forbidden claim token %r present" % tok))
    return out


def _key_is_banned(key: str) -> List[str]:
    """Banned claim tokens contained in a mapping key (case-insensitive)."""
    return _pol.find_banned_tokens(key if isinstance(key, str) else str(key))


def _walk(obj: Any, where: str, depth: int,
          out: List[Dict[str, str]]) -> None:
    """Recursively lint *obj*. Defensive: bounded depth, never raises."""
    if depth > _MAX_DEPTH:
        return
    if isinstance(obj, str):
        out.extend(_scan_string(obj, where))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            kstr = k if isinstance(k, str) else str(k)
            child = "%s.%s" % (where, kstr) if where else kstr
            # A key that is itself a $-edge style token is a structural violation
            # (the product has no dollar-edge field by design).
            for bad in _key_is_banned(kstr):
                out.append(_violation(
                    "banned_key", child,
                    "forbidden field key contains %r" % bad))
            # Keys can also carry retracted numbers as text.
            out.extend(_scan_string(kstr, child + "(key)"))
            _walk(v, child, depth + 1, out)
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            child = "%s[%d]" % (where, i) if where else "[%d]" % i
            _walk(v, child, depth + 1, out)
        return
    # Numbers / bools / None: a raw float cannot carry sign/percent framing the
    # banned-number regex needs, and equality on floats is brittle, so we only
    # lint the STRING forms above. (Retracted figures reach output as text.)
    return


def lint_obj(obj: Any) -> Dict[str, Any]:
    """Lint an arbitrary JSON-like object. Returns a structured verdict.

    Returns::

        {
          "clean": bool,                 # True iff no violations
          "violations": [                # empty iff clean
            {"kind": str, "where": str, "detail": str}, ...
          ],
          "linter_version": LINTER_VERSION,
        }

    ``kind`` is one of ``banned_number`` | ``banned_token`` | ``banned_key``.
    Pure and total: never raises, never performs I/O, never decides about money.
    """
    out: List[Dict[str, str]] = []
    try:
        _walk(obj, "", 0, out)
    except Exception as exc:  # pragma: no cover - belt-and-suspenders
        # A linter must never crash the preflight. If something pathological gets
        # past the defensive walk, fail CLOSED: report it as a violation so the
        # governance run does not silently pass un-linted output.
        out.append(_violation(
            "linter_error", "", "linter raised %s: %s" % (type(exc).__name__, exc)))
    return {
        "clean": (len(out) == 0),
        "violations": out,
        "linter_version": LINTER_VERSION,
    }


def lint_text(s: str) -> Dict[str, Any]:
    """Lint a single string. Thin wrapper over :func:`lint_obj`."""
    return lint_obj(s)


def assert_clean(obj: Any) -> None:
    """Raise ``AssertionError`` if *obj* fails the lint. For tests / hard gates.

    The pure path is :func:`lint_obj`; this is the only function here that may
    raise, and only on a violation, so callers can use it as a hard guard.
    """
    res = lint_obj(obj)
    if not res["clean"]:
        raise AssertionError(
            "honesty lint failed: %s" % res["violations"])


__all__ = [
    "LINTER_VERSION",
    "lint_text",
    "lint_obj",
    "assert_clean",
]
