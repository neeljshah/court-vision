"""serve_prediction.py — sub-100ms lookup helper for the prediction cache.

R16_E3. Pairs with `scripts/build_prediction_cache.py`. The cache is a
parquet of RAW q10/q50/q90 per (player, stat); this module loads it once
into a dict keyed by (player_id, stat) and serves point lookups in
microseconds. Injury dampener is applied at serve time, never at build
time, so a single cache survives multiple injury-snapshot refreshes per
day.

Refresh policy (matches the spec):

    * Recompute when injury_status_*.json mtime is newer than cache.
    * Recompute when the parquet is for a different date (00:00 ET boundary).
    * TTL fallback: recompute when parquet is >24h old.

Public API:

    get_prediction(player_id, stat, *, apply_injury=True)
        -> {q10, q50, q90, sigma, availability_factor, ...} | None

    refresh()             # force a reload of the parquet
    cache_path()          # path of the currently-loaded parquet
    cache_stats()         # n_rows, n_players, computed_at, ...

The serve hot path is a single dict lookup + 4 float multiplies. The cold
path (first call / refresh) reads the parquet once.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date as _date, datetime
from typing import Dict, Optional, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
_TTL_SECONDS = 24 * 60 * 60

# Internal state — protected by _LOCK for thread-safety in case the ranker
# is multi-threaded. The hot path holds the lock only for the dict swap;
# DataFrame reads happen with the lock released.
_LOCK = threading.RLock()
_STATE: Dict[str, object] = {
    "index":                None,  # type: Optional[Dict[Tuple[int, str], dict]]
    "cache_path":           None,  # type: Optional[str]
    "cache_mtime":          0.0,
    "injury_path":          None,  # type: Optional[str]
    "injury_mtime":         0.0,
    "computed_at":          None,
    "n_rows":               0,
    "loaded_at":            0.0,
}


# ──────────────────────────────────────────────────────────────────────────
# Path discovery
# ──────────────────────────────────────────────────────────────────────────

def _today_cache_path() -> str:
    """Today's expected cache path — used for the date-boundary refresh."""
    return os.path.join(
        _CACHE_DIR, f"predictions_cache_{_date.today().isoformat()}.parquet"
    )


def _latest_cache_path() -> Optional[str]:
    """Fall back to the newest predictions_cache_*.parquet if today's absent."""
    today_path = _today_cache_path()
    if os.path.exists(today_path):
        return today_path
    if not os.path.isdir(_CACHE_DIR):
        return None
    best = None
    best_mtime = -1.0
    for fname in os.listdir(_CACHE_DIR):
        if not (fname.startswith("predictions_cache_") and fname.endswith(".parquet")):
            continue
        fpath = os.path.join(_CACHE_DIR, fname)
        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = fpath
    return best


def _latest_injury_path() -> Optional[str]:
    """Path of the newest injury_status_*.json — used to detect refresh need."""
    if not os.path.isdir(_CACHE_DIR):
        return None
    best = None
    best_mtime = -1.0
    for fname in os.listdir(_CACHE_DIR):
        if not (fname.startswith("injury_status_") and fname.endswith(".json")):
            continue
        fpath = os.path.join(_CACHE_DIR, fname)
        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = fpath
    return best


# ──────────────────────────────────────────────────────────────────────────
# Refresh detection
# ──────────────────────────────────────────────────────────────────────────

def _needs_refresh() -> Tuple[bool, str]:
    """Return (needs_refresh, reason). Inspects all three refresh triggers."""
    cache_path = _STATE.get("cache_path")
    if not cache_path or _STATE.get("index") is None:
        return True, "no-cache-loaded"
    if not os.path.exists(cache_path):
        return True, "cache-file-missing"

    # Trigger 1: parquet was rewritten since we loaded it.
    try:
        mtime = os.path.getmtime(cache_path)
    except OSError:
        return True, "cache-mtime-unreadable"
    if mtime > float(_STATE["cache_mtime"]):
        return True, "cache-file-rewritten"

    # Trigger 2: injury snapshot newer than the one we cached against.
    injury_path = _latest_injury_path()
    if injury_path and injury_path != _STATE.get("injury_path"):
        return True, "injury-snapshot-rotated"
    if injury_path:
        try:
            inj_mtime = os.path.getmtime(injury_path)
        except OSError:
            inj_mtime = 0.0
        if inj_mtime > float(_STATE["injury_mtime"]):
            return True, "injury-snapshot-updated"

    # Trigger 3: date boundary — today's expected path exists and differs.
    today_path = _today_cache_path()
    if os.path.exists(today_path) and today_path != cache_path:
        return True, "date-boundary"

    # Trigger 4: TTL fallback — >24h since the parquet was written.
    age = time.time() - mtime
    if age > _TTL_SECONDS:
        return True, "ttl-expired"

    return False, "fresh"


# ──────────────────────────────────────────────────────────────────────────
# Load
# ──────────────────────────────────────────────────────────────────────────

def _load_parquet_into_index(cache_path: str) -> Dict[Tuple[int, str], dict]:
    """Read the parquet once and pivot to a {(player_id, stat): row_dict} dict."""
    df = pd.read_parquet(cache_path)
    idx: Dict[Tuple[int, str], dict] = {}
    if df.empty:
        return idx
    # Vectorised: build records once, then key into the dict.
    for rec in df.to_dict(orient="records"):
        try:
            pid = int(rec["player_id"])
        except (TypeError, ValueError, KeyError):
            continue
        stat = str(rec.get("stat", "")).lower()
        if not stat:
            continue
        idx[(pid, stat)] = {
            "player_name": rec.get("player_name", ""),
            "team":        rec.get("team", ""),
            "q10":         float(rec.get("q10", float("nan"))),
            "q50":         float(rec.get("q50", float("nan"))),
            "q90":         float(rec.get("q90", float("nan"))),
            "sigma":       float(rec.get("sigma", float("nan"))),
            "computed_at": rec.get("computed_at", ""),
        }
    return idx


def refresh(*, force: bool = False) -> str:
    """Reload the index from the freshest cache file. Returns reason string.

    `force=True` bypasses the freshness check (used by tests to exercise
    the load path). Returns "fresh" when no refresh was needed.
    """
    with _LOCK:
        if not force:
            need, reason = _needs_refresh()
            if not need:
                return reason
        else:
            reason = "force"
        cache_path = _latest_cache_path()
        if cache_path is None:
            # No parquet exists at all — leave index empty.
            _STATE["index"]        = {}
            _STATE["cache_path"]   = None
            _STATE["cache_mtime"]  = 0.0
            _STATE["computed_at"]  = None
            _STATE["n_rows"]       = 0
            _STATE["loaded_at"]    = time.time()
            return "no-cache-available"
        index = _load_parquet_into_index(cache_path)
        try:
            cache_mtime = os.path.getmtime(cache_path)
        except OSError:
            cache_mtime = time.time()
        injury_path = _latest_injury_path()
        injury_mtime = 0.0
        if injury_path and os.path.exists(injury_path):
            try:
                injury_mtime = os.path.getmtime(injury_path)
            except OSError:
                injury_mtime = 0.0
        # First entry computed_at — they're all equal per-build.
        computed_at = None
        if index:
            computed_at = next(iter(index.values())).get("computed_at")
        _STATE["index"]         = index
        _STATE["cache_path"]    = cache_path
        _STATE["cache_mtime"]   = cache_mtime
        _STATE["injury_path"]   = injury_path
        _STATE["injury_mtime"]  = injury_mtime
        _STATE["computed_at"]   = computed_at
        _STATE["n_rows"]        = len(index)
        _STATE["loaded_at"]     = time.time()
        return reason


def _ensure_loaded() -> None:
    """Lazy-load on first call; cheap on subsequent calls."""
    if _STATE.get("index") is None:
        refresh(force=True)
        return
    need, _reason = _needs_refresh()
    if need:
        refresh()


# ──────────────────────────────────────────────────────────────────────────
# Public lookup
# ──────────────────────────────────────────────────────────────────────────

def get_prediction(
    player_id: int,
    stat: str,
    *,
    apply_injury: bool = True,
    player_name: Optional[str] = None,
) -> Optional[dict]:
    """Return cached q10/q50/q90 (optionally dampened by injury availability).

    Args:
        player_id:   NBA stats player_id.
        stat:        one of pts/reb/ast/fg3m/stl/blk/tov.
        apply_injury: when True, multiply q10/q50/q90 by the live
                     availability_factor from src.prediction.injury_availability.
        player_name: optional fallback for the availability lookup.

    Returns:
        dict with keys q10, q50, q90, sigma, availability_factor, player_name,
        team, computed_at. Returns None when (player_id, stat) is not in cache.

    Performance target: <100ms p99. The hot path is a single dict lookup +
    constant-time injury factor lookup + 4 float multiplies.
    """
    _ensure_loaded()
    idx = _STATE.get("index") or {}
    rec = idx.get((int(player_id), str(stat).lower()))
    if rec is None:
        return None
    q10, q50, q90, sigma = rec["q10"], rec["q50"], rec["q90"], rec["sigma"]
    factor = 1.0
    if apply_injury:
        try:
            from src.prediction.injury_availability import (  # noqa: PLC0415
                get_availability_factor,
            )
            factor = float(get_availability_factor(
                player_id=int(player_id),
                player_name=player_name or rec.get("player_name") or None,
            ))
        except Exception:
            factor = 1.0
    if factor != 1.0:
        q10 = q10 * factor
        q50 = q50 * factor
        q90 = q90 * factor
        sigma = sigma * factor
    return {
        "player_id":           int(player_id),
        "player_name":         rec.get("player_name", ""),
        "team":                rec.get("team", ""),
        "stat":                str(stat).lower(),
        "q10":                 q10,
        "q50":                 q50,
        "q90":                 q90,
        "sigma":               sigma,
        "availability_factor": factor,
        "computed_at":         rec.get("computed_at", ""),
    }


def cache_path() -> Optional[str]:
    """Return the path of the currently-loaded cache file."""
    _ensure_loaded()
    return _STATE.get("cache_path")  # type: ignore[return-value]


def cache_stats() -> dict:
    """Return a small status dict — useful for health checks / dashboards."""
    _ensure_loaded()
    return {
        "cache_path":   _STATE.get("cache_path"),
        "n_rows":       _STATE.get("n_rows", 0),
        "n_players":    len({
            pid for (pid, _) in (_STATE.get("index") or {}).keys()
        }),
        "computed_at":  _STATE.get("computed_at"),
        "loaded_at":    _STATE.get("loaded_at"),
        "injury_path":  _STATE.get("injury_path"),
    }


def reset_for_tests() -> None:
    """Drop in-process state. Tests use this to force the cold-load path."""
    with _LOCK:
        _STATE["index"]         = None
        _STATE["cache_path"]    = None
        _STATE["cache_mtime"]   = 0.0
        _STATE["injury_path"]   = None
        _STATE["injury_mtime"]  = 0.0
        _STATE["computed_at"]   = None
        _STATE["n_rows"]        = 0
        _STATE["loaded_at"]     = 0.0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Serve prediction cache lookups")
    ap.add_argument("--pid", type=int, required=False)
    ap.add_argument("--stat", default="pts")
    ap.add_argument("--stats", action="store_true",
                    help="Print cache_stats() and exit")
    ap.add_argument("--no-injury", action="store_true")
    args = ap.parse_args()
    if args.stats or args.pid is None:
        print(json.dumps(cache_stats(), indent=2, default=str))
    else:
        result = get_prediction(args.pid, args.stat,
                                apply_injury=not args.no_injury)
        print(json.dumps(result, indent=2, default=str))
