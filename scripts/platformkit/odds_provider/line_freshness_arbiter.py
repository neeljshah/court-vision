"""scripts.platformkit.odds_provider.line_freshness_arbiter -- multi-source
line-staleness arbiter for the bestbets board.

Given per-venue captured_at timestamps for a market, returns the FRESHEST
non-stale venue (book name) or the sentinel UNAVAILABLE when every source is
past SLA. This lets the board prefer a still-fresh venue over dropping the whole
card, while still degrading to UNAVAILABLE honestly when nothing is fresh.

Public API
----------
arbitrate(
    venue_timestamps   : {book: captured_at_iso | None},
    *,
    now                : Optional[datetime] = None,
    max_age_sec        : float = DEFAULT_MAX_AGE_SEC,
    market_type        : Optional[str] = None,
    max_age_override   : Optional[Dict[str, float]] = None,
) -> ArbitrateResult

ArbitrateResult fields:
    winner       : str | None    -- freshest venue name, or None (UNAVAILABLE)
    status       : "fresh" | "UNAVAILABLE"
    winner_age_sec: float | None -- age of the winning venue (None if UNAVAILABLE)
    candidates   : list[VenueAge] -- all venues sorted freshest-first

VenueAge fields:
    book         : str
    age_sec      : float | None   -- None when timestamp missing / unparseable
    is_fresh     : bool

Rules
-----
1. A venue with missing, None, or unparseable captured_at is treated as STALE
   (stale-never-green: unknown timestamps are never trusted fresh).
2. The venue with the smallest age_sec that is within max_age_sec wins.
3. When multiple venues are equally fresh (same smallest age), earliest entry
   in the iteration order wins (deterministic on sorted input).
4. When every venue is past SLA (or no venues given): status=UNAVAILABLE,
   winner=None.  NEVER returns a stale price as winner.
5. Injectable now-clock for reproducibility; no network, no I/O.
6. No $ field anywhere; calibration-only; stale-never-green.

build_on: freshness.is_fresh / freshness_status / DEFAULT_MAX_AGE_SEC (read-only)
          MarketQuote.book + captured_at fields (read-only)

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from scripts.platformkit.odds_provider.freshness import (
    DEFAULT_MAX_AGE_SEC,
    MARKET_MAX_AGE,
    freshness_status,
)

# The sentinel string returned in ArbitrateResult.status when no fresh venue exists.
UNAVAILABLE = "UNAVAILABLE"
STATUS_FRESH = "fresh"


@dataclass
class VenueAge:
    """Per-venue freshness verdict.

    book         : venue/book name
    age_sec      : how old the captured_at is relative to *now* (None if
                   the timestamp is missing or unparseable)
    is_fresh     : True iff age_sec is within the effective SLA
    """

    book: str
    age_sec: Optional[float]
    is_fresh: bool


@dataclass
class ArbitrateResult:
    """Output of arbitrate().

    winner        : name of the freshest in-SLA venue, or None (UNAVAILABLE)
    status        : "fresh" | "UNAVAILABLE"
    winner_age_sec: age of the winning venue in seconds, or None (UNAVAILABLE)
    candidates    : all input venues as VenueAge, sorted freshest-first
                    (unknown age sinks to the bottom of the sort)
    """

    winner: Optional[str]
    status: str
    winner_age_sec: Optional[float]
    candidates: List[VenueAge]


def _sort_key(va: VenueAge) -> float:
    """Ascending age sort key.  None (unparseable) sinks to infinity so it never
    wins over a parseable stale entry -- missing timestamps are the least trusted."""
    if va.age_sec is None:
        return float("inf")
    return va.age_sec


def arbitrate(
    venue_timestamps: Dict[str, Optional[str]],
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    market_type: Optional[str] = None,
    max_age_override: Optional[Dict[str, float]] = None,
) -> ArbitrateResult:
    """Pick the freshest venue from *venue_timestamps*, or UNAVAILABLE.

    Parameters
    ----------
    venue_timestamps  : {book: ISO-8601 captured_at | None}
        Per-venue line timestamps. A book with a missing key, None value, or
        unparseable string is treated as STALE (stale-never-green).
    now               : injectable UTC clock (default: datetime.now(utc)).
        Pass a fixed value in tests so freshness calculations are deterministic.
    max_age_sec       : maximum acceptable age in seconds (default 900 = 15 min).
        Per-market defaults from freshness.MARKET_MAX_AGE apply when market_type
        is given and no override is present.
    market_type       : "moneyline" | "spread" | "total" | "prop" -- used to
        select a per-market SLA via freshness.MARKET_MAX_AGE or max_age_override.
    max_age_override  : caller-supplied {market_type: max_age_sec} map; takes
        precedence over the built-in MARKET_MAX_AGE table.

    Returns
    -------
    ArbitrateResult with winner=None / status=UNAVAILABLE when no fresh venue
    exists. The winning venue is the one with the SMALLEST age_sec that is
    within the effective SLA. Ties broken by insertion order of venue_timestamps.
    Never raises; never returns a stale price as winner.
    """
    try:
        return _arbitrate_inner(
            venue_timestamps,
            now=now,
            max_age_sec=max_age_sec,
            market_type=market_type,
            max_age_override=max_age_override,
        )
    except Exception:  # noqa: BLE001 -- must never sink callers
        return ArbitrateResult(
            winner=None,
            status=UNAVAILABLE,
            winner_age_sec=None,
            candidates=[],
        )


def _arbitrate_inner(
    venue_timestamps: Dict[str, Optional[str]],
    *,
    now: Optional[datetime],
    max_age_sec: float,
    market_type: Optional[str],
    max_age_override: Optional[Dict[str, float]],
) -> ArbitrateResult:
    """Inner implementation (exceptions allowed here; arbitrate() is the guard)."""
    candidates: List[VenueAge] = []

    for book, ts in venue_timestamps.items():
        book_str = str(book)
        # A missing or falsy timestamp is never trusted as fresh.
        if not ts:
            candidates.append(VenueAge(book=book_str, age_sec=None, is_fresh=False))
            continue
        fs = freshness_status(
            ts,
            now=now,
            max_age_sec=max_age_sec,
            market_type=market_type,
            max_age_override=max_age_override,
        )
        # "unknown" (unparseable) -> treated as stale (fail-closed)
        age_sec: Optional[float] = fs["age_sec"]
        fresh = fs["status"] == STATUS_FRESH
        candidates.append(VenueAge(book=book_str, age_sec=age_sec, is_fresh=fresh))

    # Sort freshest-first (smallest age).  Unknown age sinks to infinity.
    sorted_candidates = sorted(candidates, key=_sort_key)

    # The winner is the first (freshest) in-SLA candidate.
    winner_va: Optional[VenueAge] = None
    for va in sorted_candidates:
        if va.is_fresh:
            winner_va = va
            break

    if winner_va is None:
        return ArbitrateResult(
            winner=None,
            status=UNAVAILABLE,
            winner_age_sec=None,
            candidates=sorted_candidates,
        )

    return ArbitrateResult(
        winner=winner_va.book,
        status=STATUS_FRESH,
        winner_age_sec=winner_va.age_sec,
        candidates=sorted_candidates,
    )


__all__ = [
    "arbitrate",
    "ArbitrateResult",
    "VenueAge",
    "UNAVAILABLE",
    "STATUS_FRESH",
    "DEFAULT_MAX_AGE_SEC",
]
