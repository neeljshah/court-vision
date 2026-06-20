"""scripts.platformkit.odds_provider.venue_staleness_rollup -- per-venue staleness
matrix aggregated from the freshness arbiter output.

Takes any iterable of ArbitrateResult or raw {book: captured_at} venue-timestamp
maps and produces a venues{} matrix:
  {venue_name: {"status": "fresh"|"stale", "age_sec": float|None}}

plus a top-level rollup verdict:
  "overall":  "fresh"      -- at least one venue is fresh
            | "stale"      -- all venues present but none fresh (stale-never-green)
            | "UNAVAILABLE"-- empty input or every entry has no parseable timestamp

STALE-NEVER-GREEN: the overall verdict can NEVER be "ok"/"fresh" unless at least
one venue actually passes the SLA. An empty input is UNAVAILABLE, never green.
A venue with a missing/unparseable timestamp is marked "stale", not "unknown",
to satisfy the fail-closed rail.

Sidecar contract:
  sidecar_status(venues_matrix) returns the same shape as freshness.sidecar_status:
  {"ok": bool, "status": str, "venues": dict, "n_fresh": int, "n_stale": int}

  "ok" is True ONLY when overall == "fresh".

Public API
----------
rollup(
    venue_timestamps: dict[str, str|None],
    *,
    now                : Optional[datetime] = None,
    max_age_sec        : float = DEFAULT_MAX_AGE_SEC,
    market_type        : Optional[str] = None,
    max_age_override   : Optional[dict[str, float]] = None,
) -> VenueStalenessResult

rollup_from_arbitrate(result: ArbitrateResult, *, ...) -> VenueStalenessResult

sidecar_status(result: VenueStalenessResult) -> dict

build_on: line_freshness_arbiter.arbitrate + VenueAge, freshness.is_fresh SLA.
INVARIANTS: read-only over arbiter output; no network; no I/O; no $ field;
stale-never-green; <=300 LOC; ASCII only; stdlib only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_venue_staleness_rollup.py -q
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from scripts.platformkit.odds_provider.freshness import DEFAULT_MAX_AGE_SEC
from scripts.platformkit.odds_provider.line_freshness_arbiter import (
    UNAVAILABLE,
    ArbitrateResult,
    VenueAge,
    arbitrate,
)

# Rollup status constants (no "ok" to avoid confusion with the sidecar bool field).
STATUS_FRESH = "fresh"
STATUS_STALE = "stale"
# UNAVAILABLE sentinel reused from the arbiter -- empty or all-unparseable inputs.
STATUS_UNAVAILABLE = UNAVAILABLE  # "UNAVAILABLE"


@dataclass
class VenueRow:
    """Per-venue staleness verdict in the rollup matrix.

    status  : "fresh" | "stale"  -- never "unknown"; missing ts collapses to stale.
    age_sec : float | None       -- None only when ts was missing/unparseable.
    """

    status: str
    age_sec: Optional[float]


@dataclass
class VenueStalenessResult:
    """Output of rollup().

    venues  : {venue_name: VenueRow} -- every input venue is represented.
    overall : "fresh" | "stale" | "UNAVAILABLE"
              "fresh"       -- at least one venue is within SLA.
              "stale"       -- all venues present, none within SLA.
              "UNAVAILABLE" -- empty input or every ts unparseable.
    n_fresh : int  -- count of venues whose status == "fresh".
    n_stale : int  -- count of venues whose status == "stale".
    """

    venues: Dict[str, VenueRow] = field(default_factory=dict)
    overall: str = STATUS_UNAVAILABLE
    n_fresh: int = 0
    n_stale: int = 0


def _venue_row_from_venue_age(va: VenueAge) -> VenueRow:
    """Convert a VenueAge (from the arbiter candidates list) to a VenueRow.

    Missing/unparseable timestamps (age_sec=None, is_fresh=False) collapse to
    status="stale" per the stale-never-green rail -- never "unknown".
    """
    if va.is_fresh:
        return VenueRow(status=STATUS_FRESH, age_sec=va.age_sec)
    # Both genuinely-stale and unknown/missing timestamps are reported as stale.
    return VenueRow(status=STATUS_STALE, age_sec=va.age_sec)


def _overall_from_counts(n_venues: int, n_fresh: int) -> str:
    """Derive the overall rollup verdict from venue counts.

    Rules (stale-never-green):
      n_venues == 0         -> UNAVAILABLE (empty input)
      n_fresh > 0           -> fresh
      n_fresh == 0, venues  -> stale
    """
    if n_venues == 0:
        return STATUS_UNAVAILABLE
    if n_fresh > 0:
        return STATUS_FRESH
    return STATUS_STALE


def rollup_from_arbitrate(
    result: ArbitrateResult,
) -> VenueStalenessResult:
    """Build a VenueStalenessResult from an already-computed ArbitrateResult.

    This is the cheap path when the caller already has an ArbitrateResult: we
    re-use the candidates list that the arbiter already populated (no extra
    network or timestamp parsing).

    Parameters
    ----------
    result : ArbitrateResult from line_freshness_arbiter.arbitrate().

    Returns
    -------
    VenueStalenessResult with venues keyed by book name.  An empty
    candidates list -> overall=UNAVAILABLE.  Never raises.
    """
    try:
        return _rollup_from_candidates(result.candidates)
    except Exception:  # noqa: BLE001 -- must never sink callers
        return VenueStalenessResult()


def _rollup_from_candidates(candidates: List[VenueAge]) -> VenueStalenessResult:
    venues: Dict[str, VenueRow] = {}
    n_fresh = 0
    n_stale = 0
    for va in candidates:
        row = _venue_row_from_venue_age(va)
        venues[va.book] = row
        if row.status == STATUS_FRESH:
            n_fresh += 1
        else:
            n_stale += 1
    overall = _overall_from_counts(len(venues), n_fresh)
    return VenueStalenessResult(
        venues=venues,
        overall=overall,
        n_fresh=n_fresh,
        n_stale=n_stale,
    )


def rollup(
    venue_timestamps: Dict[str, Optional[str]],
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    market_type: Optional[str] = None,
    max_age_override: Optional[Dict[str, float]] = None,
) -> VenueStalenessResult:
    """Aggregate per-venue captured_at timestamps into a staleness matrix.

    Parameters
    ----------
    venue_timestamps  : {book: ISO-8601 captured_at | None}
        Per-venue line timestamps. A book with None or missing/unparseable ts
        is treated as stale (stale-never-green).
    now               : injectable UTC clock (default: datetime.now(utc)).
    max_age_sec       : maximum acceptable age in seconds (default 900 = 15 min).
    market_type       : "moneyline"|"spread"|"total"|"prop" -- per-market SLA.
    max_age_override  : caller-supplied {market_type: max_age_sec} map.

    Returns
    -------
    VenueStalenessResult with venues{} matrix + overall verdict.
    Never raises; empty input -> overall=UNAVAILABLE.
    """
    try:
        arb = arbitrate(
            venue_timestamps,
            now=now,
            max_age_sec=max_age_sec,
            market_type=market_type,
            max_age_override=max_age_override,
        )
        return _rollup_from_candidates(arb.candidates)
    except Exception:  # noqa: BLE001 -- must never sink callers
        return VenueStalenessResult()


def sidecar_status(result: VenueStalenessResult) -> Dict[str, Any]:
    """Serving-path verdict dict from a VenueStalenessResult.

    Returns a dict shaped like freshness.sidecar_status for consistency with the
    existing sidecar contract:
      {
        "ok"     : bool   -- True ONLY when overall == "fresh"
        "status" : str    -- "fresh" | "stale" | "UNAVAILABLE"
        "venues" : dict   -- {venue: {"status": str, "age_sec": float|None}}
        "n_fresh": int
        "n_stale": int
      }

    ok is False for both "stale" and "UNAVAILABLE" (stale-never-green).
    No $ field; calibration-only.  Never raises.
    """
    try:
        venues_dict: Dict[str, Any] = {
            name: {"status": row.status, "age_sec": row.age_sec}
            for name, row in result.venues.items()
        }
        ok = result.overall == STATUS_FRESH
        return {
            "ok": ok,
            "status": result.overall,
            "venues": venues_dict,
            "n_fresh": result.n_fresh,
            "n_stale": result.n_stale,
        }
    except Exception:  # noqa: BLE001 -- sidecar path must never sink callers
        return {
            "ok": False,
            "status": STATUS_UNAVAILABLE,
            "venues": {},
            "n_fresh": 0,
            "n_stale": 0,
        }


__all__ = [
    "VenueRow",
    "VenueStalenessResult",
    "STATUS_FRESH",
    "STATUS_STALE",
    "STATUS_UNAVAILABLE",
    "rollup",
    "rollup_from_arbitrate",
    "sidecar_status",
]
