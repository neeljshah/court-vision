"""Freshness X1 -- typed injury/lineup delta contract (promotes the eval_gate shape).

Reuses the eval_gate/freshness_schema InjuryDelta SHAPE and extends it for the live
extraction pipeline. The LLM fills these rows; it emits status/severity/body_part/text
plus an extraction-confidence ONLY -- NEVER a probability or any number that enters a
prediction. The vacated-load model (deterministic, already validated) computes every
redistribution downstream.

validate_delta() is the downstream RE-VALIDATION that catches the ~12% semantic-fail
constrained-decoding miss (right shape, wrong fact): malformed rows, out-of-enum
status/severity, severity/status inconsistency, and out-of-[0,1] confidence.

Self-contained: stdlib only (no pydantic dep so it runs in CI without installs).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple

# Typed vocab (tuples so they double as the enum + the validation set).
STATUSES: Tuple[str, ...] = (
    "OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "AVAILABLE", "GTD",
)
SEVERITIES: Tuple[str, ...] = (
    "none", "minor", "moderate", "major", "season_ending", "unknown",
)

# Status values that are logically inconsistent with a season-ending severity.
_PLAYS_THROUGH = ("AVAILABLE", "PROBABLE")


@dataclass(frozen=True)
class InjuryDelta:
    """One player-status pulled from ONE document, stamped with the vintage key.

    Mirrors eval_gate/freshness_schema.InjuryDelta and adds body_part + a free-text
    note (the LLM's verbatim evidence span). confidence is EXTRACTION confidence only.
    """
    player_id: str
    team_id: str
    status: str            # one of STATUSES
    severity: str          # one of SEVERITIES
    game_date: str         # ISO date of the game the status applies to
    source: str            # provenance (url / feed name)
    extracted_at: str      # ISO datetime the row became known -- the vintage key
    confidence: float      # 0..1 EXTRACTION confidence (never an outcome prob)
    body_part: str = ""    # optional, free text
    note: str = ""         # optional, verbatim evidence span the LLM read
    is_fallback_proxy: bool = False  # True => reconstructed post-hoc (outcome-conditioned)

    def as_dict(self) -> dict:
        return {
            "player_id": self.player_id, "team_id": self.team_id,
            "status": self.status, "severity": self.severity,
            "game_date": self.game_date, "source": self.source,
            "extracted_at": self.extracted_at, "confidence": self.confidence,
            "body_part": self.body_part, "note": self.note,
            "is_fallback_proxy": self.is_fallback_proxy,
        }


def validate_delta(d: dict) -> None:
    """Raise AssertionError on a malformed / semantically inconsistent row.

    Runs DOWNSTREAM of any constrained decoding; constrained decoding still fails
    ~12% semantically on hard cases, so this is the non-negotiable re-validation gate.
    """
    req = ("player_id", "team_id", "status", "severity", "game_date",
           "source", "extracted_at", "confidence")
    for k in req:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["status"] in STATUSES, f"bad status {d['status']}"
    assert d["severity"] in SEVERITIES, f"bad severity {d['severity']}"
    try:
        conf = float(d["confidence"])
    except (TypeError, ValueError):
        raise AssertionError("confidence not numeric")
    assert 0.0 <= conf <= 1.0, "confidence out of [0,1]"
    # semantic consistency: a season-ending injury cannot read as playing-through.
    if d["severity"] == "season_ending":
        assert d["status"] not in _PLAYS_THROUGH, (
            f"inconsistent: season_ending severity with status {d['status']}"
        )
    datetime.fromisoformat(d["extracted_at"])      # raises ValueError if not ISO
    datetime.fromisoformat(d["game_date"])          # raises ValueError if not ISO date


def is_out(d: dict, statuses: Tuple[str, ...] = ("OUT",)) -> bool:
    """True if the row's status is in the OUT-equivalent set (default binary OUT)."""
    return d.get("status") in statuses
