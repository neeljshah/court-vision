"""scripts.platformkit.ingame.quote_freshness -- reusable QUOTE-FRESHNESS mask over an
in-game tick stream (queue item 2, LANE 2).

WHY (binding context)
----------------------------------------------------------------------------
wave-6 found only 10-40% of soccer in-play ticks carry a genuinely NEW venue quote --
the rest repeat the previous tick's market_prob verbatim (a stale run up to 62
consecutive ticks). Every model-vs-venue Brier comparison in this repo scores against
these possibly-stale venue quotes, which can inflate (or deflate) the model-vs-venue
gap in EITHER direction: a stale quote is easier to beat late in its run (state has
moved on, the quote has not) and easier to match/undercut early in a fresh tick's own
run. This module supplies the FRESH-tick mask so downstream verdict code can score a
fresh-only arm alongside the existing raw arm, additively -- see
ingame_outcome_verdict_freshness.py for the consumer.

DEFINITION (binding)
----------------------------------------------------------------------------
A tick's venue quote is FRESH if its market_prob differs from the PREVIOUS tick's
market_prob for the SAME game (rows already sorted by ts, e.g. via
live_grade._load_pairs), OR it is the first tick of that game's sequence (nothing to
compare against -- first observation of a quote is definitionally new information, not
a repeat). Every other tick (market_prob == previous tick's market_prob, bit-for-bit)
is STALE. Floating point values are compared with a small epsilon (venue feeds
round-trip through JSON as floats; treat sub-epsilon "differences" as no real update).

This is intentionally a SYNTACTIC definition (did the printed number move), not a
semantic one (did the market's true belief move) -- we cannot observe the latter, and
the syntactic definition is exactly what the wave-6 measurement used.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network;
never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_quote_freshness.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

_EPS = 1e-9

# Pre-registered 2026-09-01: venue-clock state-age ceilings for paper suppression.
STATE_AGE_CEILING_SEC = {"mlb": 5.0}
SLOW_STATE_AGE_CEILING_SEC = 120.0


def _as_prob(value: Any) -> Optional[float]:
    """Coerce to float; None if non-numeric (never fabricated)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def state_age_sec(order_time: Any, rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Age of the freshest source clock behind an order; None is an honest absence."""
    order_dt = _parse_ts(order_time) if isinstance(order_time, str) else order_time
    if not isinstance(order_dt, datetime):
        return None
    if order_dt.tzinfo is None:
        order_dt = order_dt.replace(tzinfo=timezone.utc)
    sources = [_parse_ts(r.get("src_ts")) for r in rows if isinstance(r, dict)]
    freshest = max((s for s in sources if s is not None), default=None)
    return None if freshest is None else round((order_dt - freshest).total_seconds(), 3)


def state_age_ceiling_sec(sport: str) -> float:
    """The registered source-clock ceiling for a sport (not a quote-price heuristic)."""
    return STATE_AGE_CEILING_SEC.get(str(sport).lower(), SLOW_STATE_AGE_CEILING_SEC)


def freshness_mask(rows: Sequence[Dict[str, Any]], *,
                   prob_field: str = "market_prob",
                   eps: float = _EPS) -> List[bool]:
    """Per-row FRESH/STALE mask over a SINGLE game's tick sequence.

    rows MUST already be in tick order (e.g. live_grade._load_pairs sorts by ts).
    Row i is FRESH iff i == 0 (first tick: nothing to compare, treated as new
    information) OR rows[i][prob_field] differs from rows[i-1][prob_field] by more
    than eps. A row whose prob_field is missing/non-numeric is conservatively STALE
    (never counted as a fresh observation -- we cannot confirm it moved). Never raises;
    an empty input returns an empty mask.
    """
    n = len(rows)
    if n == 0:
        return []
    mask: List[bool] = [False] * n
    prev: Optional[float] = None
    for i, r in enumerate(rows):
        cur = _as_prob(r.get(prob_field))
        if i == 0:
            mask[i] = cur is not None
        else:
            mask[i] = cur is not None and prev is not None and abs(cur - prev) > eps
        prev = cur
    return mask


def filter_fresh(rows: Sequence[Dict[str, Any]], *,
                 prob_field: str = "market_prob",
                 eps: float = _EPS) -> List[Dict[str, Any]]:
    """Convenience: rows restricted to the FRESH subset (order preserved)."""
    mask = freshness_mask(rows, prob_field=prob_field, eps=eps)
    return [r for r, fresh in zip(rows, mask) if fresh]


def freshness_share(rows: Sequence[Dict[str, Any]], *,
                    prob_field: str = "market_prob",
                    eps: float = _EPS) -> Dict[str, Any]:
    """{'n_ticks', 'n_fresh_ticks', 'fresh_share'} for one game's sequence.

    fresh_share is None (not 0.0) when n_ticks == 0, so a caller never mistakes 'no
    data' for 'measured 0% fresh'. Never raises."""
    mask = freshness_mask(rows, prob_field=prob_field, eps=eps)
    n = len(mask)
    n_fresh = sum(1 for m in mask if m)
    return {
        "n_ticks": n,
        "n_fresh_ticks": n_fresh,
        "fresh_share": (n_fresh / n) if n > 0 else None,
    }


def longest_stale_run(rows: Sequence[Dict[str, Any]], *,
                      prob_field: str = "market_prob",
                      eps: float = _EPS) -> int:
    """Longest consecutive run of STALE ticks (0 if rows is empty or all-fresh).
    Diagnostic only -- mirrors the wave-6 'max stale run' measurement."""
    mask = freshness_mask(rows, prob_field=prob_field, eps=eps)
    longest = run = 0
    for fresh in mask:
        if fresh:
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    return longest


__all__ = [
    "freshness_mask", "filter_fresh", "freshness_share", "longest_stale_run",
    "state_age_sec", "state_age_ceiling_sec", "STATE_AGE_CEILING_SEC",
    "SLOW_STATE_AGE_CEILING_SEC",
]
