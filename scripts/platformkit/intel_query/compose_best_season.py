"""Season-awareness helpers for compose_best.py -- split out to keep
compose_best.py under the <=300 LOC/file rail.

The GAP this closes: compose_best() picks its primary VERIFIED ranking claim
by gate verdict alone, with no notion of WHICH season the caller actually
asked about -- a "this season" / "2025-26" question silently got answered
with the 2024-25 gate-canonical leaderboard even when a VERIFIED claim for
the requested season existed elsewhere in the same corpus.

detect_requested_season() parses the question text for a season token.
resolve() decides, once compose_best has its gate-selected primary claim,
whether that claim's own window matches the request, and if not: (a)
substitutes a declared season-matched VERIFIED claim (its own ranking +
caveats carried verbatim, never re-derived), or (b) if none is declared/
available, leaves the original canonical claim in place with an honest
season-mismatch caveat instead of silently answering the wrong season.
build_primary_block() renders the "primary" envelope block for either case,
keeping the two authority levels (gate-canonical vs season-matched-but-not-
gate-canonical) from ever blurring together.

No requested season (the overwhelming majority of "best X" questions today)
-> resolve() is a no-op pass-through and build_primary_block() emits the
exact same keys as before this module existed -- byte-stable regression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ponytail: one constant for "this season" / "current season" -- bump by
# hand when the season rolls over; not a live calendar computation.
CURRENT_SEASON = "2025-26"

_SEASON_EXPLICIT_RE = re.compile(r"\b(20\d{2})[\s_-](\d{2})\b")
_SEASON_CURRENT_RE = re.compile(r"\b(this season|current season)\b", re.IGNORECASE)


def detect_requested_season(question: str) -> str | None:
    """Explicit 'YYYY-YY' / 'YYYY YY' / 'YYYY_YY' wins over the vaguer
    'this season'/'current season' phrasing (more specific token first).
    No token found -> None, meaning "no season awareness" to every caller
    (today's behavior, unchanged)."""
    text = question or ""
    m = _SEASON_EXPLICIT_RE.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    if _SEASON_CURRENT_RE.search(text):
        return CURRENT_SEASON
    return None


def normalize_season(value: Any) -> str:
    """'2024_25' / 'season_2024-25' / '2024-25' all normalize to '2024-25'
    -- both hyphen conventions seen across claim families must never cause
    a false season mismatch."""
    v = str(value or "").strip()
    if v.lower().startswith("season_"):
        v = v[len("season_"):]
    return v.replace("_", "-")


@dataclass(frozen=True)
class SeasonResolution:
    claim: dict[str, Any]
    claim_id: str
    using_fallback: bool
    caveat: str | None


def resolve(
    config: Any,
    verified: dict[str, dict[str, Any]],
    primary_claim: dict[str, Any],
    primary_claim_id: str,
    requested_season: str | None,
) -> SeasonResolution:
    """requested_season=None, or it matches the gate-selected primary
    claim's own window -> pass primary_claim through untouched. A mismatch
    first tries config.season_fallback (a VERIFIED claim for the SAME
    aspect with a matching window declared on the aspect config); if found,
    THAT claim becomes primary verbatim (own ranking, own caveats -- never
    re-derived). If no fallback is declared or the declared one isn't
    currently VERIFIED, the original canonical claim stays, annotated with
    an honest season-mismatch caveat instead of a silent wrong-season
    answer."""
    if requested_season is None:
        return SeasonResolution(primary_claim, primary_claim_id, False, None)
    primary_window = normalize_season(primary_claim.get("criteria", {}).get("window"))
    if primary_window == requested_season:
        return SeasonResolution(primary_claim, primary_claim_id, False, None)
    fallback_id = (getattr(config, "season_fallback", None) or {}).get(requested_season)
    fallback_claim = verified.get(fallback_id) if fallback_id else None
    if fallback_claim is not None:
        return SeasonResolution(fallback_claim, fallback_id, True, None)
    caveat = (
        f"season mismatch: requested {requested_season}, canonical ranking is "
        f"{primary_window} (gate-backed); no season-matching canonical exists"
    )
    return SeasonResolution(primary_claim, primary_claim_id, False, caveat)


def build_primary_block(
    primary_claim_id: str,
    conclusion_name: str,
    rank1: dict[str, Any],
    verdict_value: Any,
    verdict_file_display: str,
    requested_season: str | None,
    using_fallback: bool,
) -> dict[str, Any]:
    """Renders compose_best()'s "primary" envelope block. When no season was
    requested this emits the EXACT same keys compose_best built inline
    before this module existed (gate_verdict/gate_verdict_file, no season
    keys) -- the no-token regression test depends on this."""
    block: dict[str, Any] = {
        "claim_id": primary_claim_id,
        "rank1": conclusion_name,
        "score": rank1.get("value"),
    }
    if using_fallback:
        block["requested_season"] = requested_season
        block["authority"] = "season-matched VERIFIED ranking (not gate-canonical)"
    else:
        block["gate_verdict"] = verdict_value
        block["gate_verdict_file"] = verdict_file_display
        if requested_season is not None:
            block["requested_season"] = requested_season
            block["authority"] = "gate-canonical"
    return block
