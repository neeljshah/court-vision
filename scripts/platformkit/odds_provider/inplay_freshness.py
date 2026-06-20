"""scripts.platformkit.odds_provider.inplay_freshness -- in-play staleness helpers.

The stale-never-green (LA-P0-a) primitives shared by the in-play capture daemon,
split out so inplay_snapshot_daemon stays loop-logic-only (and <=300 LOC). All are
PURE / injectable (time via *now*) and reuse freshness.is_fresh -- the SAME guard
the serving sidecar uses -- so a frozen feed reads stale on capture AND on serve.

  * source_fresh(source_ts, now)  -> is a body's TRUE fetch time recent enough to
    trust (within SOURCE_MAX_AGE_SEC)? A frozen/cached re-serve fails -> tick dropped.
  * freshest_source_ts(kept)      -> the most-recent source_ts among KEPT ticks, or
    None (a frozen feed drops every tick -> None -> sidecar reads stale/RED).
  * write_freshness(dir, now, n, last_source_ts) -> atomically write the per-sport
    sidecar {last_capture_ts, last_n_ticks, last_source_ts}; the serving guard
    prefers the source time, so a None there reads RED, never green off poll time.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; stdlib + repo-internal.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# A captured in-play tick whose BODY was fetched longer ago than this is FROZEN (the
# feed stopped updating) and is DROPPED -- never re-stamped fresh at poll time.
# Reuses freshness.is_fresh's moneyline cadence (live lines move in seconds).
SOURCE_MAX_AGE_SEC = 120.0


def _iso(dt: datetime) -> str:
    d = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_fresh(source_ts: Any, now: datetime) -> bool:
    """True iff *source_ts* (a body's TRUE fetch time) is within SOURCE_MAX_AGE_SEC
    of *now*. Reuses freshness.is_fresh, so a frozen feed's old source_ts reads NOT
    fresh and the caller drops the tick (never re-stamps it fresh)."""
    try:
        from .freshness import is_fresh
        return is_fresh(source_ts, now=now, max_age_sec=SOURCE_MAX_AGE_SEC)
    except Exception as exc:  # noqa: BLE001 -- guard must never sink the poll
        logger.debug("source freshness check failed: %s", exc)
        return False


def freshest_source_ts(kept: List[Dict[str, Any]]) -> Optional[str]:
    """The most-recent source_ts among KEPT ticks, or None (LA-P0-a). On a frozen
    feed every tick is dropped -> kept empty -> None -> sidecar reads stale/RED."""
    stamps = [str(t["source_ts"]) for t in kept if t.get("source_ts")]
    return max(stamps) if stamps else None


def write_freshness(sport_dir: Path, now: datetime, n_ticks: int,
                    last_source_ts: Optional[str] = None) -> None:
    """Atomically write the sidecar {last_capture_ts, last_n_ticks, last_source_ts}.

    last_source_ts is the TRUE freshest feed time among kept ticks (LA-P0-a): a poll
    that kept ZERO live ticks (frozen feed) writes None, so the serving guard reads
    stale/RED, never green off the poll wall-clock. The caller advances this ONLY on
    a successful poll (a failed poll leaves the sidecar untouched).
    """
    sport_dir.mkdir(parents=True, exist_ok=True)
    target = sport_dir / "_freshness.json"
    payload = {"last_capture_ts": _iso(now), "last_n_ticks": int(n_ticks),
               "last_source_ts": last_source_ts}
    tmp = target.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(str(tmp), str(target))


__all__ = ["SOURCE_MAX_AGE_SEC", "source_fresh", "freshest_source_ts",
           "write_freshness"]
