"""scripts.platformkit.odds_provider.freshness -- staleness guard for line data.

A line is considered FRESH when its captured_at timestamp is within max_age_sec
of now. A None or unparseable timestamp degrades to "unknown" -- the caller
decides how to handle uncertainty; this module never raises.

Public API
----------
is_fresh(captured_at, *, now=None, max_age_sec=DEFAULT_MAX_AGE_SEC) -> bool
    True iff captured_at is parseable AND within max_age_sec of now.
    Unknown/unparseable timestamps return False (conservative: not trusted fresh).

freshness_status(captured_at, *, now=None, max_age_sec=DEFAULT_MAX_AGE_SEC)
    -> dict with keys:
        "status" : "fresh" | "stale" | "unknown"
        "age_sec" : float | None  (None when timestamp is unknown/unparseable)

Both functions are PURE (time injectable via now=) so they are trivially testable
and safe to call from daemons, boards, or scheduled checks without side effects.

Per-market override
-------------------
A per-market override map (dict[market_type -> max_age_sec]) can be passed to
both functions via the max_age_override kwarg.  When the market_type for a quote
is known, its override takes precedence over max_age_sec.  This lets callers be
tighter on moneyline (fast-moving at tip-off) and looser on props (slower lines).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Default max age: 15 minutes.  Lines older than this are marked stale.
# Chosen to be short enough to catch genuinely dead-data risk while giving
# enough runway for a polling cycle to complete before the next tip-off.
DEFAULT_MAX_AGE_SEC: float = 900.0  # 15 minutes

# Future-skew tolerance (seconds).  A captured_at slightly AHEAD of our clock is a
# legitimate, benign clock skew between the source/cache box and ours -- treat it as
# fresh (age ~0).  But a timestamp WILDLY in the future (corrupt feed, bad parse, a
# clock-skewed source stamping hours/days ahead) must NOT read green forever: its
# negative age would otherwise always satisfy age <= max_age.  Anything more than
# this tolerance into the future is UNTRUSTED -> classified "unknown" (fail-closed),
# so best_line_fresh excludes it, book_table marks it not-fresh, and the serving
# guard reads it not-green.  This is the future half of the stale-never-green rail.
FUTURE_SKEW_TOLERANCE_SEC: float = 120.0  # 2 minutes of tolerated clock skew

# Per-market-type defaults (seconds).  These are the built-in overrides; a
# caller may supply their own map to is_fresh / freshness_status.
MARKET_MAX_AGE: Dict[str, float] = {
    "moneyline": 900.0,   # 15 min -- moves fast near tip-off
    "spread":    900.0,   # 15 min
    "total":    1800.0,   # 30 min -- totals move more slowly
    "prop":     3600.0,   # 60 min -- prop lines rarely move inside game day
}


def _parse_utc(ts: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string into a UTC-aware datetime, or return None.

    Accepts the shapes produced by MarketQuote.captured_at and the aggregate()
    as_of field:
      "2026-06-18T20:00:00+00:00"  (isoformat with offset)
      "2026-06-18T20:00:00Z"       (Z-suffix -- Python 3.10 fromisoformat needs
                                    the Z swapped for +00:00 on 3.10; 3.11+ is fine)
    Returns None on any parse failure (no exception propagation).
    """
    if not ts:
        return None
    try:
        s = str(ts).strip()
        if not s:
            return None
        # Python 3.10 fromisoformat does NOT accept Z; replace with +00:00.
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        # Ensure timezone-aware; assume UTC if naive (should not happen).
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001 -- parse must never sink a row
        return None


def _resolve_max_age(
    market_type: Optional[str],
    max_age_sec: float,
    max_age_override: Optional[Dict[str, float]],
) -> float:
    """Pick the effective max_age: caller override > built-in MARKET_MAX_AGE > default."""
    if market_type:
        mt = str(market_type).lower()
        override_map = max_age_override if max_age_override is not None else {}
        if mt in override_map:
            return float(override_map[mt])
        if mt in MARKET_MAX_AGE:
            return MARKET_MAX_AGE[mt]
    return max_age_sec


def _utc_now(now: Optional[datetime]) -> datetime:
    if now is not None:
        dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def freshness_status(
    captured_at: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    market_type: Optional[str] = None,
    max_age_override: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Return a freshness status dict for *captured_at*.

    Returns {"status": "fresh"|"stale"|"unknown", "age_sec": float|None}.

    A None or unparseable timestamp returns status="unknown", age_sec=None --
    the caller must decide how to handle uncertain data (never raises).
    A parseable timestamp is classified fresh/stale against the effective max age
    (see _resolve_max_age for override precedence).

    Parameters
    ----------
    captured_at     : ISO-8601 string (or None / any) -- the line's timestamp.
    now             : injectable UTC datetime (default: datetime.now(utc)).
    max_age_sec     : default max age in seconds when no per-market override applies.
    market_type     : optional market type string ("moneyline"|"spread"|"total"|"prop")
                      used to look up a per-market max-age from MARKET_MAX_AGE or
                      max_age_override.
    max_age_override: optional caller-supplied {market_type: max_age_sec} map;
                      takes precedence over the built-in MARKET_MAX_AGE table.
    """
    dt = _parse_utc(captured_at)
    if dt is None:
        return {"status": "unknown", "age_sec": None}
    reference = _utc_now(now)
    age_sec = (reference - dt).total_seconds()
    # Future-skew guard (the future half of stale-never-green): a timestamp more
    # than FUTURE_SKEW_TOLERANCE_SEC AHEAD of our clock is not a real recent capture
    # -- it is a corrupt/clock-skewed feed whose negative age would otherwise read
    # fresh forever.  Treat it as UNTRUSTED -> "unknown" (fail-closed), never green.
    # Mild skew (within tolerance) stays fresh so a benign source/box clock offset
    # does not flap a legitimately-current line to stale.
    if age_sec < -FUTURE_SKEW_TOLERANCE_SEC:
        return {"status": "unknown", "age_sec": age_sec}
    effective = _resolve_max_age(market_type, max_age_sec, max_age_override)
    status = "fresh" if age_sec <= effective else "stale"
    return {"status": status, "age_sec": age_sec}


def is_fresh(
    captured_at: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    market_type: Optional[str] = None,
    max_age_override: Optional[Dict[str, float]] = None,
) -> bool:
    """True iff *captured_at* is parseable AND within the effective max age of now.

    An unknown/unparseable timestamp returns False (conservative: not trusted
    fresh; the daemon should not silently trust stale-or-unknown data).
    Pure: no network, no I/O, safe to call freely.

    Parameters
    ----------
    captured_at     : ISO-8601 string (or None / any) -- the line's timestamp.
    now             : injectable UTC datetime (default: datetime.now(utc)).
    max_age_sec     : default max age when no per-market override applies.
    market_type     : optional market type for per-market max-age lookup.
    max_age_override: optional caller-supplied {market_type: max_age_sec} map.
    """
    result = freshness_status(
        captured_at,
        now=now,
        max_age_sec=max_age_sec,
        market_type=market_type,
        max_age_override=max_age_override,
    )
    return result["status"] == "fresh"


# --------------------------------------------------------------------------- #
# SERVING-PATH GUARD (LA-P0-b): turn a dead/cached feed RED on the dashboard.
#
# The capture daemons write a per-sport `_freshness.json` sidecar carrying the
# slate's TRUE source timestamp (pregame: source_as_of; in-play: last_capture_ts).
# The serving layer (board / API) calls sidecar_status(sport) and MUST surface a
# not-"ok" result as a stale/red indicator. A MISSING, unparseable, or stale sidecar
# is conservatively NOT fresh -> "stale"/"missing" (a dead feed can never read green).
# --------------------------------------------------------------------------- #

# Sidecar timestamp keys, in priority order: the source/data time first (true
# freshness of the underlying feed), then the poll/capture wall-clock as a fallback.
_SIDECAR_TS_KEYS = ("source_as_of", "last_capture_ts", "poll_at")

# AUTHORITATIVE source-time keys (LA-P0-a). When a sidecar carries one of these, it
# is the TRUE feed time and OVERRIDES the poll wall-clock entirely -- even when its
# value is None/empty. An in-play poll off a FROZEN feed (every tick dropped stale)
# writes last_source_ts=None on purpose: the sidecar must then read stale/RED, NOT
# fall through to the poll wall-clock and read green. So a PRESENT-but-empty
# authoritative key short-circuits to "stale", never green.
_SIDECAR_SOURCE_KEYS = ("source_as_of", "last_source_ts")


def _read_sidecar(path: Path) -> Optional[Dict[str, Any]]:
    """Load a `_freshness.json` sidecar dict, or None if absent/unreadable."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001 -- a bad sidecar reads as 'missing', never green
        return None


def sidecar_status(
    sport_dir: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
) -> Dict[str, Any]:
    """Serving-path freshness verdict for a sport's capture sidecar directory.

    Reads *sport_dir*/_freshness.json (the per-sport sidecar a capture daemon
    writes) and applies the staleness guard to its TRUE source timestamp. Returns
    {"ok": bool, "status": "fresh"|"stale"|"missing"|"unknown", "age_sec": ...,
     "as_of": str|None}.

    ok is True ONLY when status == "fresh". A MISSING sidecar (daemon never ran /
    feed never came up) -> ok=False, status="missing". A sidecar whose source
    timestamp is older than max_age_sec -> ok=False, status="stale". This is the
    stale-never-green rail: the serving layer renders any ok=False as RED.
    """
    path = Path(sport_dir) / "_freshness.json"
    side = _read_sidecar(path)
    if side is None:
        return {"ok": False, "status": "missing", "age_sec": None, "as_of": None}
    # An AUTHORITATIVE source-time key present in the sidecar OVERRIDES the poll
    # wall-clock -- even if its value is None/empty (a frozen-feed poll). A present-
    # but-empty authoritative key reads stale/RED, never falling through to a fresh
    # poll wall-clock (the stale-never-green rail, LA-P0-a).
    for key in _SIDECAR_SOURCE_KEYS:
        if key in side:
            val = side.get(key)
            if not val:
                return {"ok": False, "status": "stale", "age_sec": None,
                        "as_of": None}
            fs = freshness_status(val, now=now, max_age_sec=max_age_sec)
            return {"ok": fs["status"] == "fresh", "status": fs["status"],
                    "age_sec": fs["age_sec"], "as_of": val}
    ts = None
    for key in _SIDECAR_TS_KEYS:
        if side.get(key):
            ts = side.get(key)
            break
    fs = freshness_status(ts, now=now, max_age_sec=max_age_sec)
    return {
        "ok": fs["status"] == "fresh",
        "status": fs["status"],
        "age_sec": fs["age_sec"],
        "as_of": ts,
    }


def serve_ok(
    sport_dir: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
) -> bool:
    """True iff the sport's feed is FRESH enough to serve as green. Convenience
    boolean over sidecar_status; a missing/stale/unknown sidecar is False (red)."""
    return sidecar_status(sport_dir, now=now, max_age_sec=max_age_sec)["ok"]


__all__ = [
    "DEFAULT_MAX_AGE_SEC",
    "FUTURE_SKEW_TOLERANCE_SEC",
    "MARKET_MAX_AGE",
    "freshness_status",
    "is_fresh",
    "sidecar_status",
    "serve_ok",
]
