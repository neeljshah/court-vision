"""Explicit forward-versus-retrospective claim selection."""
from __future__ import annotations

from typing import Any

FORWARD = "FORWARD"
RETROSPECTIVE = "RETROSPECTIVE"


def _count(series: dict[str, Any]) -> int:
    for key in ("settled_n", "forward_n", "n_settled", "n"):
        value = series.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _claim_value(series: dict[str, Any] | None) -> Any:
    if not series:
        return None
    for key in ("claim", "value", "verdict"):
        if key in series:
            return series[key]
    return None


def _usable(forward: dict[str, Any] | None) -> bool:
    if not forward:
        return False
    min_n = forward.get("min_n", 1)
    if not isinstance(min_n, (int, float)):
        return False
    return _count(forward) > 0 and _count(forward) >= min_n


def primacy(forward: dict[str, Any] | None, retro: dict[str, Any] | None) -> dict[str, Any]:
    """Choose the claim source without silently presenting retro as forward."""
    forward_wins = _usable(forward)
    chosen = forward if forward_wins else retro
    forward_verdict = forward.get("verdict") if forward else None
    retro_verdict = retro.get("verdict") if retro else None
    conflict = bool(forward_wins and retro and forward_verdict != retro_verdict)
    provenance = FORWARD if forward_wins else RETROSPECTIVE
    note = "%s claim selected" % provenance
    if conflict:
        note = "FORWARD claim selected; forward verdict=%s, retrospective verdict=%s" % (
            forward_verdict, retro_verdict)
    elif not forward_wins:
        note = "RETROSPECTIVE claim selected; no usable settled forward series"
    return {
        "claim": _claim_value(chosen),
        "value": _claim_value(chosen),
        "provenance": provenance,
        "label": provenance,
        "conflict": conflict,
        "note": note,
        "retro": dict(retro) if retro else None,
    }


def label_row(row: dict[str, Any], retro: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a new scoreboard row with explicit claim provenance labels."""
    result = dict(row)
    verdict = row.get("verdict")
    is_unsettled = verdict in (None, "ABSENT", "UNKNOWN") or str(verdict).startswith(
        ("INSUFFICIENT", "PENDING"))
    forward = None if is_unsettled else {
        "value": verdict,
        "verdict": verdict,
        "settled_n": row.get("forward_n", 0),
        "min_n": 1,
    }
    chosen = primacy(forward, retro or {"value": verdict, "verdict": verdict})
    result["claim_provenance"] = chosen["provenance"]
    result["claim_label"] = chosen["label"]
    return result


__all__ = ["FORWARD", "RETROSPECTIVE", "primacy", "label_row"]
