"""governance.number_provenance -- every user-facing number must carry honest provenance.

A calibrated predictor may only PRESENT a number it can stand behind. A number
that was FILLED (imputed / percentile-filled / last-observed proxy) or whose
provenance is UNKNOWN must be FLAGGED, never shown as if it were a REAL_MODEL or
CAPTURED_MARKET output. This module tags numbers with provenance and walks an
envelope / report to verify every surfaced number carries an ALLOWED provenance.

Conventions for a tagged number (a "cell"): a mapping that carries a numeric
``value`` (or ``val`` / ``number``) alongside a ``provenance`` field. Provenance
may be a :class:`Provenance` enum, its string name, or be supplied separately via
:func:`tag`. A cell with FILLED / UNKNOWN provenance that is NOT explicitly
flagged (``flagged=True`` / ``is_flagged=True``) is a violation.

DECISION-ONLY, pure, total: no I/O, never authorizes a bet, never flips a flag,
never raises. INVARIANTS: governance/ only; <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from governance import policy as _pol
from governance.policy import Provenance

PROVENANCE_CHECK_VERSION = "governance.number_provenance.v1"

_MAX_DEPTH = 40

# Keys that, when present in a mapping, mark it as a tagged numeric "cell".
_VALUE_KEYS = ("value", "val", "number", "num")
_PROVENANCE_KEYS = ("provenance", "prov", "source_kind")
_FLAG_KEYS = ("flagged", "is_flagged", "flag", "unavailable")


def tag(value: Any, provenance: Provenance) -> Dict[str, Any]:
    """Tag *value* with *provenance*, returning a canonical cell mapping.

    The returned cell auto-sets ``flagged=True`` when the provenance must be
    flagged (FILLED / UNKNOWN), so a correctly tagged value is honest by default.
    """
    p = Provenance(provenance)
    must_flag = _pol.provenance_must_be_flagged(p)
    return {
        "value": value,
        "provenance": p.value,
        "flagged": bool(must_flag),
        "presentable": (p in _pol.PRESENTABLE_PROVENANCE),
    }


def _coerce_provenance(raw: Any) -> Optional[Provenance]:
    """Best-effort coerce *raw* into a Provenance. None if not coercible."""
    if raw is None:
        return None
    if isinstance(raw, Provenance):
        return raw
    try:
        return Provenance(str(raw))
    except (ValueError, KeyError):
        return None


def _is_flagged(cell: Dict[str, Any]) -> bool:
    for k in _FLAG_KEYS:
        if bool(cell.get(k)):
            return True
    return False


def _cell_value(cell: Dict[str, Any]) -> Any:
    for k in _VALUE_KEYS:
        if k in cell:
            return cell[k]
    return None


def _cell_provenance_raw(cell: Dict[str, Any]) -> Any:
    for k in _PROVENANCE_KEYS:
        if k in cell:
            return cell[k]
    return None


def _looks_like_cell(obj: Any) -> bool:
    """A cell is a mapping carrying both a numeric value key and a provenance key."""
    if not isinstance(obj, dict):
        return False
    has_val = any(k in obj for k in _VALUE_KEYS)
    has_prov = any(k in obj for k in _PROVENANCE_KEYS)
    return has_val and has_prov


def _check_cell(cell: Dict[str, Any], where: str) -> List[Dict[str, str]]:
    """A surfaced cell must carry an allowed provenance or be explicitly flagged."""
    out: List[Dict[str, str]] = []
    raw = _cell_provenance_raw(cell)
    prov = _coerce_provenance(raw)
    if prov is None:
        # Unrecognized provenance string -> treat as UNKNOWN (unsafe).
        if not _is_flagged(cell):
            out.append({
                "kind": "unknown_provenance", "where": where,
                "detail": "provenance %r unrecognized and not flagged" % (raw,)})
        return out
    if _pol.provenance_must_be_flagged(prov) and not _is_flagged(cell):
        out.append({
            "kind": "filled_presented_as_real", "where": where,
            "detail": ("number with %s provenance presented as real "
                       "(not flagged)" % prov.value)})
    return out


def _walk(obj: Any, where: str, depth: int,
          out: List[Dict[str, str]]) -> None:
    if depth > _MAX_DEPTH:
        return
    if _looks_like_cell(obj):
        out.extend(_check_cell(obj, where or "<root>"))
        # Still recurse into the value in case it nests further cells.
        _walk(_cell_value(obj), (where + ".value") if where else "value",
              depth + 1, out)
        return
    if isinstance(obj, dict):
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


def assert_provenance(obj: Any) -> Dict[str, Any]:
    """Walk *obj* and flag any user-facing number presented with bad provenance.

    Returns::

        {
          "ok": bool,                    # True iff no provenance violations
          "violations": [
            {"kind": str, "where": str, "detail": str}, ...
          ],
          "version": PROVENANCE_CHECK_VERSION,
        }

    ``kind`` is ``filled_presented_as_real`` (FILLED / UNKNOWN shown as real) or
    ``unknown_provenance`` (unrecognized provenance, treated as unsafe). Pure and
    total: never raises, never performs I/O, never decides about money.
    """
    out: List[Dict[str, str]] = []
    try:
        _walk(obj, "", 0, out)
    except Exception as exc:  # pragma: no cover - fail closed
        out.append({
            "kind": "provenance_error", "where": "",
            "detail": "walk raised %s: %s" % (type(exc).__name__, exc)})
    return {
        "ok": (len(out) == 0),
        "violations": out,
        "version": PROVENANCE_CHECK_VERSION,
    }


def is_presentable(provenance: Provenance) -> bool:
    """True iff *provenance* may be shown to a user as a genuine number."""
    return Provenance(provenance) in _pol.PRESENTABLE_PROVENANCE


__all__ = [
    "PROVENANCE_CHECK_VERSION",
    "tag",
    "assert_provenance",
    "is_presentable",
]
