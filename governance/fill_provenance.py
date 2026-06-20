"""governance.fill_provenance -- a FILLED value must never masquerade as observed.

The hard-won lesson (percentile-fill-defeats-signals): when a 'live' / per-quarter
feature is FILLED -- percentile-filled, last-observed-carried-forward, imputed,
or otherwise synthesized rather than truly observed -- it silently destroys the
signal it pretends to carry. Such a value is HONEST only if it is flagged as
FILLED provenance; presented as a real observation it is a fabrication.

This module detects fill provenance from common markers and requires it be
flagged. It reads vocabulary from :mod:`governance.policy` (Provenance) and reuses
:mod:`governance.number_provenance` for the FILLED-presented-as-real check, adding
the heuristics that recognise a fill even when provenance was not explicitly set.

A cell is considered FILLED when ANY of these hold:
  * its provenance is explicitly :data:`Provenance.FILLED`;
  * it carries a truthy fill marker key (``filled`` / ``is_filled`` /
    ``percentile_fill`` / ``imputed`` / ``last_observed`` / ``carried_forward`` /
    ``proxy`` / ``backfilled``);
  * its ``fill_method`` / ``source`` names a known fill method
    (``percentile`` / ``percentile_fill`` / ``last_observed`` / ``ffill`` /
    ``carry_forward`` / ``impute`` / ``mean_fill`` / ``proxy``).

A FILLED cell that is NOT flagged as FILLED provenance is a violation.

DECISION-ONLY, pure, total: no I/O, never authorizes a bet, never flips a flag,
never raises. INVARIANTS: governance/ only; <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List

from governance.policy import Provenance, provenance_must_be_flagged

FILL_CHECK_VERSION = "governance.fill_provenance.v1"

_MAX_DEPTH = 40

# Boolean marker keys that, when truthy, mean the value was filled.
_FILL_FLAG_KEYS = (
    "filled", "is_filled", "percentile_fill", "imputed",
    "last_observed", "carried_forward", "carry_forward", "proxy",
    "backfilled", "is_proxy",
)

# String-valued keys whose value may name a known fill method.
_METHOD_KEYS = ("fill_method", "source", "source_kind", "method", "origin")

# Known fill-method names (substring match, case-insensitive).
_FILL_METHODS = (
    "percentile", "percentile_fill", "last_observed", "ffill", "bfill",
    "carry_forward", "carryforward", "impute", "imputed", "mean_fill",
    "median_fill", "proxy", "placeholder",
)

_PROVENANCE_KEYS = ("provenance", "prov", "source_kind")
_FLAG_KEYS = ("flagged", "is_flagged", "flag")


def _truthy_fill_marker(cell: Dict[str, Any]) -> bool:
    return any(bool(cell.get(k)) for k in _FILL_FLAG_KEYS)


def _named_fill_method(cell: Dict[str, Any]) -> bool:
    for k in _METHOD_KEYS:
        v = cell.get(k)
        if isinstance(v, str):
            low = v.lower()
            if any(m in low for m in _FILL_METHODS):
                return True
    return False


def _provenance_is_filled(cell: Dict[str, Any]) -> bool:
    for k in _PROVENANCE_KEYS:
        raw = cell.get(k)
        if raw is None:
            continue
        try:
            if Provenance(str(raw)) == Provenance.FILLED:
                return True
        except (ValueError, KeyError):
            continue
    return False


def is_filled_cell(cell: Any) -> bool:
    """True iff *cell* is a mapping that was FILLED (by any recognised marker)."""
    if not isinstance(cell, dict):
        return False
    return (_provenance_is_filled(cell)
            or _truthy_fill_marker(cell)
            or _named_fill_method(cell))


def _is_flagged_as_filled(cell: Dict[str, Any]) -> bool:
    """A filled cell is honest iff its provenance is the FILLED enum.

    A generic ``flagged=True`` is necessary but NOT sufficient -- the lesson is
    that a fill must be labelled as a fill (FILLED provenance), so a downstream
    consumer can drop it rather than mistake it for a real per-quarter signal.
    """
    return _provenance_is_filled(cell)


def _walk(obj: Any, where: str, depth: int,
          out: List[Dict[str, str]]) -> None:
    if depth > _MAX_DEPTH:
        return
    if isinstance(obj, dict):
        if is_filled_cell(obj) and not _is_flagged_as_filled(obj):
            out.append({
                "kind": "fill_not_flagged",
                "where": where or "<root>",
                "detail": ("value was FILLED (imputed / percentile / proxy) but "
                           "provenance is not %s; it must be flagged FILLED, "
                           "never presented as observed" % Provenance.FILLED.value),
            })
        for k, v in obj.items():
            kstr = k if isinstance(k, str) else str(k)
            child = "%s.%s" % (where, kstr) if where else kstr
            _walk(v, child, depth + 1, out)
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            child = "%s[%d]" % (where, i) if where else "[%d]" % i
            _walk(v, child, depth + 1, out)
        return
    return


def assert_fills_flagged(obj: Any) -> Dict[str, Any]:
    """Walk *obj* and flag any FILLED value not labelled with FILLED provenance.

    Returns::

        {
          "ok": bool,                    # True iff no unflagged fills
          "violations": [
            {"kind": "fill_not_flagged", "where": str, "detail": str}, ...
          ],
          "version": FILL_CHECK_VERSION,
        }

    Pure and total: never raises, never performs I/O, never decides about money.
    """
    out: List[Dict[str, str]] = []
    try:
        _walk(obj, "", 0, out)
    except Exception as exc:  # pragma: no cover - fail closed
        out.append({
            "kind": "fill_check_error", "where": "",
            "detail": "walk raised %s: %s" % (type(exc).__name__, exc)})
    return {
        "ok": (len(out) == 0),
        "violations": out,
        "version": FILL_CHECK_VERSION,
    }


def flag_fill(value: Any, *, method: str = "percentile_fill") -> Dict[str, Any]:
    """Build an honestly-flagged FILLED cell for *value*.

    The returned cell carries FILLED provenance and records the fill method, so a
    consumer can drop it rather than mistake it for an observed signal.
    """
    assert provenance_must_be_flagged(Provenance.FILLED)  # invariant guard
    return {
        "value": value,
        "provenance": Provenance.FILLED.value,
        "flagged": True,
        "filled": True,
        "fill_method": str(method),
        "presentable": False,
    }


__all__ = [
    "FILL_CHECK_VERSION",
    "is_filled_cell",
    "assert_fills_flagged",
    "flag_fill",
]
