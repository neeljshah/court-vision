"""predict_service.freshness_sidecar -- the STALE-flag contract on the status surface.

W3 ROBUSTNESS (BACKEND lane). A feed can be REACHABLE-BUT-STALE: the producer last
wrote a snapshot, the file still parses, every field is present -- but the data is
hours old. Without an explicit staleness flag such a feed reads "green" on the
status surface even though it is dead. This module exposes the staleness verdict on
the status surface so a merely-reachable-but-stale feed reads STALE, not green. The
launcher -Health probe and the UI both consume `feed_status()` / `feed_rollup()`.

Two contracts:

  feed_status(sport) -> {sport, status, ok, fresh, stale, age_seconds, source_ts,
                         reason}
      Reuses the JUST-HARDENED odds_provider.freshness.sidecar_status (the
      stale-never-green source-timestamp guard): a MISSING sidecar -> "missing"
      (ok=False); a present-but-empty AUTHORITATIVE source key (frozen feed) ->
      "stale" (ok=False); an old source timestamp -> "stale" (ok=False). ok=True
      ONLY when status=="fresh". stale-never-green is inherited verbatim -- we add
      NO new path by which a stale feed can read green.

  feed_rollup(sports) -> {status, ok, feeds:[...], n_fresh, n_stale, ...}
      A MONOTONE-DOWN composite rollup over feed_status of each sport. Reuses
      status_composer._degrade (the single monotone-DOWN chokepoint): the parent
      starts at "ok" and is degraded by EVERY child -- ANY stale/missing/degraded
      child forces the parent off green. The rollup can only ever DEGRADE; a green
      child can never lift a stale parent back up.

NEVER raises: every failure degrades to an explicit stale/unavailable sentinel. No
$ field is emitted -- this is freshness observability only, calibration not edge.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ field; reuse odds_provider.freshness + status_composer._degrade verbatim.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Where the per-sport capture sidecars (_freshness.json) live. Mirrors the store
# dir env so a test monkeypatch flows through. Each sport is a SUBDIR holding its
# own _freshness.json (the shape odds_provider.freshness.sidecar_status expects).
_SIDECAR_ROOT_ENV = "PREDICT_SERVICE_FRESHNESS_DIR"
_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"

# Repo root is two levels up from this file (predict_service/freshness_sidecar.py).
# Repo-relative default candidates, tried in order (first existing dir wins).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPO_RELATIVE_DEFAULTS = (
    "data/cache/inplay_history",   # primary: where capture daemons write sidecars
    "data/frontend/predict_service",  # fallback: alternate store layout
)

# Map the freshness verdict ("fresh"/"stale"/"missing"/"unknown") onto the
# composer severity vocabulary so the monotone-DOWN _degrade can roll it up.
# Only "fresh" is OK; everything else is at least DEGRADED -- stale-never-green.
_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"

HONEST_NOTE = (
    "Feed freshness only. A reachable-but-stale feed reads STALE (ok=False), never "
    "green; the rollup only ever DEGRADES. No $ edge is claimed."
)


def _sidecar_root() -> str:
    """Resolve the sidecar root dir.

    Resolution order (first non-empty value wins):
      1. Env PREDICT_SERVICE_FRESHNESS_DIR -- explicit override (tests / deployment).
      2. Env PREDICT_SERVICE_STORE_DIR -- legacy store-dir env already on disk.
      3. First existing repo-relative default under _REPO_RELATIVE_DEFAULTS.
      4. First repo-relative candidate (whether it exists or not) -- a concrete
         wrong path that surfaces as 'missing', not a cwd-relative '.' that silently
         resolves to wherever the process was launched from.

    stale-never-green: a genuinely missing or stale sidecar at the resolved path
    still reads missing/stale (ok=False). This function never invents a green path.
    """
    explicit = os.environ.get(_SIDECAR_ROOT_ENV) or os.environ.get(_STORE_DIR_ENV)
    if explicit:
        return explicit
    # Walk repo-relative candidates; pick first that already exists on disk.
    for rel in _REPO_RELATIVE_DEFAULTS:
        candidate = _REPO_ROOT / rel
        if candidate.is_dir():
            return str(candidate)
    # No existing dir: return the primary candidate as a concrete (wrong) path.
    # This surfaces as 'missing' on the status surface, not a phantom cwd hit.
    return str(_REPO_ROOT / _REPO_RELATIVE_DEFAULTS[0])


def _verdict_severity(status: str) -> str:
    """Map a freshness verdict onto a composer severity. stale/missing -> DEGRADED."""
    if status == "fresh":
        return _OK
    if status == "missing":
        # A feed that never came up is a harder failure than a merely-old one.
        return _DOWN
    # "stale" / "unknown" / anything unexpected -> DEGRADED (never OK).
    return _DEGRADED


def feed_status(
    sport: str,
    *,
    now: Optional[datetime] = None,
    max_age_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """One sport's freshness verdict for the status surface. NEVER raises.

    Reuses odds_provider.freshness.sidecar_status (stale-never-green). Returns an
    explicit stale=True / fresh=False whenever the source timestamp is absent,
    empty (frozen feed), or older than max_age_sec -- so a reachable-but-stale feed
    can never read green on the status surface.
    """
    sport = str(sport).lower()
    root = _sidecar_root()
    sport_dir = os.path.join(root, sport)
    try:
        from scripts.platformkit.odds_provider.freshness import (  # noqa: PLC0415
            DEFAULT_MAX_AGE_SEC, sidecar_status,
        )
    except Exception as exc:  # noqa: BLE001 -- cannot import the guard -> STALE, not green
        logger.warning("freshness_sidecar: import sidecar_status failed: %s", exc)
        return {"sport": sport, "status": "stale", "ok": False, "fresh": False,
                "stale": True, "age_seconds": None, "source_ts": None,
                "reason": "freshness guard unavailable (%s)" % type(exc).__name__}
    age = max_age_sec if max_age_sec is not None else DEFAULT_MAX_AGE_SEC
    try:
        v = sidecar_status(sport_dir, now=now, max_age_sec=age)
    except Exception as exc:  # noqa: BLE001 -- the guard is total; belt + braces -> STALE
        logger.warning("freshness_sidecar: sidecar_status(%s) failed: %s",
                       sport, exc)
        return {"sport": sport, "status": "stale", "ok": False, "fresh": False,
                "stale": True, "age_seconds": None, "source_ts": None,
                "reason": "freshness read error (%s)" % type(exc).__name__}
    status = str(v.get("status", "unknown"))
    ok = bool(v.get("ok"))
    return {
        "sport": sport,
        "status": status,
        "ok": ok,
        "fresh": ok,                       # ok==True ONLY when status=="fresh"
        "stale": not ok,                   # explicit STALE flag for the UI / -Health
        "age_seconds": v.get("age_sec"),
        "source_ts": v.get("as_of"),
        "reason": None if ok else ("feed %s" % status),
    }


def feed_rollup(
    sports: List[str],
    *,
    now: Optional[datetime] = None,
    max_age_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """MONOTONE-DOWN composite freshness rollup over *sports*. NEVER raises.

    Parent starts at OK and is DEGRADED by every child via status_composer._degrade
    (the single monotone-DOWN chokepoint). ANY stale/missing child forces the parent
    off green; a green child can NEVER lift a stale parent back up. An empty sports
    list yields a DEGRADED 'no feeds' rollup (absence is never asserted green).
    """
    try:
        from scripts.platformkit.autonomy.status_composer import _degrade  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 -- no composer -> conservative local DOWN-only
        logger.warning("freshness_sidecar: import _degrade failed: %s", exc)
        _degrade = _degrade_fallback  # noqa: N806 -- documented conservative fallback

    feeds: List[Dict[str, Any]] = []
    overall = _OK
    for sport in (sports or []):
        f = feed_status(sport, now=now, max_age_sec=max_age_sec)
        feeds.append(f)
        overall = _degrade(overall, _verdict_severity(f["status"]))

    if not feeds:
        # No feeds at all: we cannot assert freshness -> DEGRADED, never green.
        overall = _degrade(overall, _DEGRADED)

    n_fresh = sum(1 for f in feeds if f["ok"])
    n_stale = sum(1 for f in feeds if not f["ok"])
    return {
        "status": overall,
        "ok": overall == _OK,
        "feeds": feeds,
        "n_feeds": len(feeds),
        "n_fresh": n_fresh,
        "n_stale": n_stale,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }


def _degrade_fallback(current: str, candidate: str) -> str:
    """Conservative monotone-DOWN fallback if status_composer cannot be imported.

    Mirrors status_composer._degrade semantics (WORSE of two; unknown -> DEGRADED)
    so the rollup is still monotone-DOWN even when the composer is unavailable.
    """
    rank = {_OK: 0, _DEGRADED: 1, _DOWN: 2}
    by_rank = {0: _OK, 1: _DEGRADED, 2: _DOWN}
    cur = rank.get(current, 1)
    cand = rank.get(candidate, 1)
    return by_rank[max(cur, cand)]


__all__ = ["feed_status", "feed_rollup", "HONEST_NOTE"]
