"""Deterministic keyword-matching question classifier (no LLM call).

Classifies a natural-language question string into ONE of the 3 supported
v1 families, or None if it matches none of them. Pure string/regex logic --
this module never touches disk and never calls a model. The intent is that
an EXTERNAL LLM calls ask() as a tool; ask() (via this module) does the
routing deterministically so the answer surface stays auditable.

Families:
    TOP_N        -- "who are the top N <metric-ish words>" ranking questions
    ENTITY_LOOKUP -- "where does <player> rank on <metric>" / "what is
                     <player>'s <metric>"
    PROVENANCE   -- "how do you know" / "show the evidence" / "prove" for a
                     specific claim_id
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FAMILY_TOP_N = "top_n"
FAMILY_ENTITY_LOOKUP = "entity_lookup"
FAMILY_PROVENANCE = "provenance"

ALL_FAMILIES = (FAMILY_TOP_N, FAMILY_ENTITY_LOOKUP, FAMILY_PROVENANCE)

_TOP_N_RE = re.compile(
    r"\btop\s*[- ]?\s*(\d+)\b|\bbest\s+(\d+)\b", re.IGNORECASE
)
_PROVENANCE_WORDS = re.compile(
    r"\b(how do you know|show (?:me )?(?:the )?evidence|prove|provenance|"
    r"source(?:s)? for|where does that come from)\b",
    re.IGNORECASE,
)
_RANK_LOOKUP_RE = re.compile(
    r"\bwhere does\b.+\brank\b|\brank(?:ing)? of\b|\bwhat rank\b|\bwhat is\b.+\brank\b",
    re.IGNORECASE,
)
# claim_id token: producer ids are snake_case, may include digits/hyphens
# once quoted (e.g. season_2024-25 windows embedded in the id).
_CLAIM_ID_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9-]+){2,})\b", re.IGNORECASE)
_WINDOW_RE = re.compile(r"\bwindow\s*[=:]\s*([a-z0-9_-]+)\b", re.IGNORECASE)


@dataclass
class ParsedQuestion:
    family: str | None
    top_n: int | None = None
    claim_id: str | None = None
    entity_name: str | None = None
    raw: str = ""
    metric_hints: list[str] = field(default_factory=list)
    window_hint: str | None = None


_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "composite": ("composite", "shooter", "shooting", "best shooters"),
    "fg3_pct": ("3pt", "three point", "3-point", "fg3", "threes"),
    "ts_pct": ("true shooting", "ts%", "ts pct", "ts_pct"),
    "efg_pct": ("effective field goal", "efg%", "efg pct", "efg"),
}


def _extract_window_hint(text: str) -> str | None:
    """Explicit 'window=last_20' / 'window: season_2024-25' style hint."""
    m = _WINDOW_RE.search(text)
    return m.group(1) if m else None


def _extract_metric_hints(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for metric, aliases in _METRIC_ALIASES.items():
        if any(a in lower for a in aliases):
            hits.append(metric)
    return hits


def _extract_claim_id(text: str) -> str | None:
    """Pull the FIRST snake_case-looking token that resembles a claim_id.
    Provenance questions are expected to name the claim_id explicitly
    (e.g. 'show the evidence for nba_shooting_composite_last_20')."""
    for m in _CLAIM_ID_RE.finditer(text):
        token = m.group(1)
        if "_" in token:
            return token
    return None


def _extract_entity_name(text: str) -> str | None:
    """Best-effort entity name extraction for entity-lookup questions:
    text between 'does'/'for' and 'rank'/'on', or a capitalized run of
    words. Deterministic, no NLP model -- good enough for the CLI/tool
    surface where the caller usually names the player directly."""
    m = re.search(
        r"\bdoes\s+(.+?)\s+rank\b", text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"\bwhat is\s+(.+?)'s\b", text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"\bfor\s+([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+)+)\b", text
    )
    if m:
        return m.group(1).strip()
    return None


def classify(question: str) -> ParsedQuestion:
    """Deterministically classify a question into a supported family.

    Order matters: provenance (explicit claim_id + evidence words) is
    checked first since it can otherwise look like a top-N or lookup
    question if the claim_id itself contains digits/words like 'top'."""
    text = question or ""
    window_hint = _extract_window_hint(text)

    if _PROVENANCE_WORDS.search(text):
        claim_id = _extract_claim_id(text)
        return ParsedQuestion(
            family=FAMILY_PROVENANCE, claim_id=claim_id, raw=question,
            metric_hints=_extract_metric_hints(text), window_hint=window_hint,
        )

    top_n_match = _TOP_N_RE.search(text)
    if top_n_match:
        n_str = top_n_match.group(1) or top_n_match.group(2)
        return ParsedQuestion(
            family=FAMILY_TOP_N,
            top_n=int(n_str) if n_str else None,
            raw=question,
            metric_hints=_extract_metric_hints(text),
            window_hint=window_hint,
        )

    if _RANK_LOOKUP_RE.search(text):
        return ParsedQuestion(
            family=FAMILY_ENTITY_LOOKUP,
            entity_name=_extract_entity_name(text),
            raw=question,
            metric_hints=_extract_metric_hints(text),
            window_hint=window_hint,
        )

    return ParsedQuestion(
        family=None, raw=question, metric_hints=_extract_metric_hints(text), window_hint=window_hint,
    )


def describe_families() -> list[dict[str, Any]]:
    """Human-readable family descriptions -- used to populate
    nearest_supported_families in the honest-unanswerable response."""
    return [
        {"family": FAMILY_TOP_N, "example": "Who are the top 10 best shooters (composite) in window=last_20?"},
        {"family": FAMILY_ENTITY_LOOKUP, "example": "Where does Stephen Curry rank on fg3_pct in window=season_2024-25?"},
        {"family": FAMILY_PROVENANCE, "example": "How do you know? Show the evidence for nba_shooting_composite_last_20."},
    ]
