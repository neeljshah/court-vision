"""Freshness X1 -- the structured-extraction STUB the LLM fills (instructor/Pydantic-shaped).

The LLM sits in EXACTLY one box: it reads unstructured injury/lineup text and returns typed
player-status records. It emits status / severity / body_part / a verbatim text span and an
EXTRACTION confidence ONLY -- it NEVER predicts a game, estimates a win probability, or outputs
any number that enters the prediction chain. The vacated-load model (deterministic, validated)
computes every redistribution downstream.

extract_doc() is a STUB that raises NotImplementedError so CI never makes a live API call and no
secret is required. The real call is a HUMAN-RUN step (instructor.from_anthropic, key from env,
max_retries for shape; this module's downstream_valid() re-validation catches the ~12% semantic
miss that retries do not). The shapes here mirror the eventual pydantic models so wiring the live
call is a drop-in.

Stdlib only (dataclasses stand in for the pydantic BaseModels until the live step is wired).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

try:  # package import (external callers, `python -m scripts.platformkit.freshness...`)
    from scripts.platformkit.freshness.schema import (  # type: ignore
        validate_delta, STATUSES, SEVERITIES)
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    from schema import validate_delta, STATUSES, SEVERITIES  # type: ignore

# The binding invariant, stated to the model verbatim. The schema has NO probability field;
# the only numeric output is `confidence` (confidence in the EXTRACTION, not any game outcome).
SYSTEM_PROMPT = (
    "You are a sports-data EXTRACTION tool. You read injury/lineup/news text and return "
    "structured player-status records. You do NOT predict games, estimate win probability, "
    "project minutes, or output ANY number except the schema's `confidence` field -- and that "
    "field is your confidence in the EXTRACTION, never in a game outcome. If a field is not "
    "stated in the text, leave it null/unknown -- never guess. Map vague phrasing "
    "conservatively: 'game-time decision' -> GTD (not AVAILABLE); LLMs are biased toward "
    "optimistic availability, so resist it. Quote the verbatim evidence span in `note`."
)


@dataclass
class InjuryExtraction:
    """One player-status the LLM pulled from ONE document (pre-resolution).

    Pydantic-shaped: when the live call is wired this becomes a BaseModel with field validators.
    No probability field exists by construction -- the invariant is enforced by the shape itself.
    """
    player_name: str
    status: str                      # one of STATUSES
    severity: str = "unknown"        # one of SEVERITIES
    team_raw: Optional[str] = None
    body_part: Optional[str] = None
    game_date: Optional[str] = None  # ISO date the status applies to
    note: str = ""                   # verbatim evidence span
    confidence: float = 0.0          # EXTRACTION confidence [0,1], NOT an outcome prob


@dataclass
class ExtractionBatch:
    """Top-level tool-call return: one document yields zero or more extractions."""
    extractions: List[InjuryExtraction] = field(default_factory=list)


def extract_doc(raw_text: str, model: str = "claude-haiku-4-5",
                max_retries: int = 3) -> ExtractionBatch:
    """STUB. The live LLM extraction is a HUMAN-RUN step (needs an API key from env).

    The real implementation uses instructor.from_anthropic with response_model=ExtractionBatch
    and max_retries to fix SHAPE failures; downstream_valid() below catches the ~12% SEMANTIC
    miss that retries do not. We raise here so CI is hermetic and no secret is referenced.
    """
    raise NotImplementedError(
        "live LLM call is a HUMAN-RUN step (set the Anthropic key in env and wire "
        "instructor.from_anthropic with response_model=ExtractionBatch); the STUB exists so "
        "CI stays hermetic and the LLM never emits a number that enters predictions."
    )


def _date_close(game_date: Optional[str], doc_date: Optional[str], max_days: int = 3) -> bool:
    """Reject hallucinated dates: game_date must be within +/- max_days of the doc date."""
    if not game_date or not doc_date:
        return True
    from datetime import date
    try:
        gd = date.fromisoformat(game_date[:10])
        dd = date.fromisoformat(doc_date[:10])
    except ValueError:
        return False
    return abs((gd - dd).days) <= max_days


def downstream_valid(ext: InjuryExtraction, doc_date: Optional[str] = None) -> bool:
    """The 12%-catch re-validation: enum membership, severity/status consistency, date sanity.

    Returns False for rows that must be quarantined (schema_ok=0), never silently trusted.
    This is the non-negotiable gate; instructor's retries fix shape, not truth.
    """
    if ext.status not in STATUSES:
        return False
    if ext.severity not in SEVERITIES:
        return False
    if not (0.0 <= float(ext.confidence) <= 1.0):
        return False
    if ext.severity == "season_ending" and ext.status in ("AVAILABLE", "PROBABLE"):
        return False
    if not _date_close(ext.game_date, doc_date):
        return False
    return True


def to_delta(ext: InjuryExtraction, team_id: str, source: str, extracted_at: str,
             player_id: str, is_fallback_proxy: bool = False) -> dict:
    """Resolve an extraction into a delta dict (player_id resolution is a deterministic lookup,
    done by the caller -- never the LLM). Validates the result before returning."""
    d = {
        "player_id": player_id, "team_id": team_id,
        "status": ext.status, "severity": ext.severity,
        "game_date": ext.game_date, "source": source,
        "extracted_at": extracted_at, "confidence": float(ext.confidence),
        "body_part": ext.body_part or "", "note": ext.note,
        "is_fallback_proxy": is_fallback_proxy,
    }
    validate_delta(d)
    return d
