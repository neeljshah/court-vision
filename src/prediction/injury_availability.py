"""injury_availability.py — inference-time multiplicative `availability_factor`.

R15_W1 wiring of the R14_H4 ESPN injury feed into prop_pergame predictions.
R22_O8 extends this with an authoritative-source lookup: when a
`data/cache/nba_injuries_<today>.parquet` exists (written by
`scripts/nba_injury_report_scraper.py` / its daemon), that columnar
artifact is consulted FIRST — it is fresher and source-of-truth (NBA
PDF preferred, ESPN fallback, rotowire last-resort).

This is INFERENCE-ONLY logic — the underlying model is not retrained. At
predict-time we look up the most-recent injury status for a player and
multiply the model's q50/q10/q90 outputs by an availability_factor in
[0.0, 1.0]:

    OUT, NOT WITH TEAM  → 0.00
    DOUBTFUL            → 0.30
    QUESTIONABLE        → 0.60
    PROBABLE            → 0.90
    AVAILABLE           → 1.00

Lookup order (R22_O8):
    1. data/cache/nba_injuries_<today>.parquet     (authoritative, fresh)
    2. data/cache/injury_status_<latest>.json      (legacy ESPN snapshot)
    3. Trigger fresh scrape if both stale → re-check.

When the injury cache is older than _STALE_HOURS we trigger a fresh
scrape via `scripts/probe_R14_H4_injury_feed.py` so the prediction is
always backed by recent ESPN data. Because this only runs at inference,
it can NOT leak into the trained model — historical training rows have
no `availability_factor` column.

Public API
----------
    get_availability_factor(player_id)        -> float in [0, 1]
    apply_availability(player_id, q50,
                       q10=None, q90=None)    -> (q50, q10, q90)
    load_latest_snapshot()                    -> dict (raw payload)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date as _date_cls
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# R31_X2: worktree-aware cache-dir resolver. Honours NBA_DATA_DIR /
# explicit NBA_INJURY_CACHE_DIR env override. The canary is the parquet
# pattern WITHOUT a date (matching the daemon's recent output) — when
# missing we accept any populated `data/cache/` (including just legacy
# JSON snapshots). The canary is `None` because daily parquet filenames
# embed the date and a fresh worktree may have only the legacy JSON.
# Behaviour preserved: with no env vars and a local data/cache/ that's
# at least a directory, the local dir wins (unchanged from today).
from src.prediction._paths import resolve_data_dir  # noqa: E402
_CACHE_DIR = resolve_data_dir(
    "cache",
    env_var="NBA_INJURY_CACHE_DIR",
    project_dir=PROJECT_DIR,
)

# Match R14_H4 probe taxonomy exactly so a snapshot built by the probe
# round-trips here byte-for-byte without re-normalisation.
AVAILABILITY_FACTOR: Dict[str, float] = {
    "OUT":           0.0,
    "NOT WITH TEAM": 0.0,
    "DOUBTFUL":      0.3,
    "QUESTIONABLE":  0.6,
    "PROBABLE":      0.9,
    "AVAILABLE":     1.0,
}

_DEFAULT_FACTOR = 1.0          # player not in feed → assume healthy
_STALE_HOURS    = 6.0          # re-scrape after this many hours
_DISABLE_ENV    = "NBA_INJURY_WIRE_DISABLE"   # set to "1" to bypass entirely

# In-process cache so a single prediction batch hits disk once.
_CACHED: Dict[str, object] = {
    "by_player_id": None,     # type: Optional[Dict[int, float]]
    "by_name":      None,     # type: Optional[Dict[str, float]]
    "loaded_at":    0.0,
    "snapshot_mtime": 0.0,
}


def _disabled() -> bool:
    """Belt-and-braces escape hatch for tests / batch backtests."""
    return os.environ.get(_DISABLE_ENV, "0") == "1"


def _latest_snapshot_path() -> Optional[str]:
    """Return the path of the newest injury_status_<isodate>.json or None."""
    if not os.path.isdir(_CACHE_DIR):
        return None
    best: Optional[str] = None
    best_mtime = -1.0
    for fname in os.listdir(_CACHE_DIR):
        if not fname.startswith("injury_status_") or not fname.endswith(".json"):
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


def _trigger_fresh_scrape() -> bool:
    """Invoke scripts/probe_R14_H4_injury_feed.py for today.

    Returns True on a clean run (rc 0), False otherwise. Failure is
    non-fatal — the caller falls back to the stale snapshot.
    """
    script = os.path.join(PROJECT_DIR, "scripts",
                          "probe_R14_H4_injury_feed.py")
    if not os.path.exists(script):
        return False
    try:
        cp = subprocess.run(
            [sys.executable, script, "--date", _date_cls.today().isoformat()],
            cwd=PROJECT_DIR,
            check=False,
            capture_output=True,
            timeout=90,
        )
        return cp.returncode == 0
    except Exception as exc:
        print(f"[injury_availability] fresh scrape failed: {exc}")
        return False


def _is_stale(snap_path: Optional[str]) -> bool:
    """A missing or >_STALE_HOURS-old snapshot is stale."""
    if snap_path is None or not os.path.exists(snap_path):
        return True
    age_hours = (time.time() - os.path.getmtime(snap_path)) / 3600.0
    return age_hours > _STALE_HOURS


def load_latest_snapshot() -> Optional[dict]:
    """Read the most-recent snapshot JSON. Triggers a fresh scrape if stale."""
    snap_path = _latest_snapshot_path()
    if _is_stale(snap_path):
        _trigger_fresh_scrape()
        snap_path = _latest_snapshot_path()
    if snap_path is None or not os.path.exists(snap_path):
        return None
    try:
        with open(snap_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"[injury_availability] snapshot read failed: {exc}")
        return None


def _name_key(name: str) -> str:
    """Same normalisation rule the probe uses for player-name lookup."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name or "")) \
        .encode("ascii", "ignore").decode().lower().strip()
    for suf in (" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return " ".join(s.split())


def _latest_parquet_path() -> Optional[str]:
    """R22_O8 — return nba_injuries_<isodate>.parquet for today or None.

    The daemon writes today's parquet atomically; we never read
    yesterday's file when today's is missing (would be inference-stale).
    """
    today = _date_cls.today().isoformat()
    candidate = os.path.join(_CACHE_DIR, f"nba_injuries_{today}.parquet")
    return candidate if os.path.exists(candidate) else None


def _load_parquet_indices() -> Optional[Tuple[Dict[int, float], Dict[str, float], float]]:
    """R22_O8 — load (by_pid, by_name, mtime) from today's parquet.

    Returns None when:
      * pandas can't import (shouldn't happen — prop pipeline imports it).
      * The file is empty / missing the required columns.
      * Read errors (corrupt mid-write — caller falls back to legacy JSON).
    """
    pq_path = _latest_parquet_path()
    if pq_path is None:
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(pq_path)
    except Exception as exc:
        print(f"[injury_availability] parquet read failed: {exc}")
        return None
    if df.empty or "status" not in df.columns:
        return None
    by_pid: Dict[int, float] = {}
    by_name: Dict[str, float] = {}
    for _, rec in df.iterrows():
        status = str(rec.get("status") or "").upper().strip()
        factor = AVAILABILITY_FACTOR.get(status)
        if factor is None:
            continue
        pid_raw = rec.get("player_id")
        if pid_raw is not None and pd.notna(pid_raw):
            try:
                by_pid[int(pid_raw)] = float(factor)
            except (TypeError, ValueError):
                pass
        nm = _name_key(rec.get("player_name", ""))
        if nm:
            by_name[nm] = float(factor)
    try:
        mtime = os.path.getmtime(pq_path)
    except OSError:
        mtime = 0.0
    return by_pid, by_name, mtime


def _rebuild_indices() -> None:
    """Reload {player_id: factor} and {name_key: factor} from the freshest source.

    R22_O8 lookup order:
      1. Today's nba_injuries_<date>.parquet (authoritative, daemon-written).
      2. Legacy injury_status_<date>.json snapshot (ESPN-only fallback).
    """
    by_pid: Dict[int, float] = {}
    by_name: Dict[str, float] = {}
    mtime: float = 0.0

    parquet_load = _load_parquet_indices()
    if parquet_load is not None:
        by_pid, by_name, mtime = parquet_load
    else:
        payload = load_latest_snapshot() or {}
        for rec in payload.get("players") or []:
            status = str(rec.get("status") or "").upper().strip()
            factor = AVAILABILITY_FACTOR.get(status)
            if factor is None:
                continue
            pid_raw = rec.get("player_id")
            if pid_raw is not None:
                try:
                    by_pid[int(pid_raw)] = float(factor)
                except (TypeError, ValueError):
                    pass
            nm = _name_key(rec.get("player_name", ""))
            if nm:
                by_name[nm] = float(factor)
        snap_path = _latest_snapshot_path()
        mtime = (
            os.path.getmtime(snap_path) if snap_path
            and os.path.exists(snap_path) else 0.0
        )

    _CACHED["by_player_id"]   = by_pid
    _CACHED["by_name"]        = by_name
    _CACHED["loaded_at"]      = time.time()
    _CACHED["snapshot_mtime"] = mtime


def _ensure_loaded(force: bool = False) -> None:
    """Lazy-load (or refresh) the in-process index.

    R22_O8 — invalidate when either today's parquet or the legacy JSON
    snapshot has a newer mtime than what's cached, so daemon-driven
    parquet refreshes are picked up on the next prediction call.
    """
    if force or _CACHED["by_player_id"] is None:
        _rebuild_indices()
        return
    # Pick whichever source the rebuilt cache *would* use right now.
    parquet_path = _latest_parquet_path()
    snap_path = _latest_snapshot_path()
    active_path = parquet_path or snap_path
    if active_path is None:
        return
    try:
        current_mtime = os.path.getmtime(active_path)
    except OSError:
        return
    if current_mtime > float(_CACHED["snapshot_mtime"]):
        _rebuild_indices()


def get_availability_factor(player_id: Optional[int] = None,
                            player_name: Optional[str] = None) -> float:
    """Return the multiplicative availability factor for a player.

    Args:
        player_id:   NBA player_id (preferred — exact match).
        player_name: Player name fallback (canonicalised). Used when
                     player_id is missing OR not in the feed.

    Returns:
        Float in [0.0, 1.0]. Defaults to 1.0 when the player isn't in
        the feed (assume healthy) or the feed is unavailable.
    """
    if _disabled():
        return _DEFAULT_FACTOR
    _ensure_loaded()
    by_pid = _CACHED["by_player_id"] or {}
    by_name = _CACHED["by_name"] or {}
    if player_id is not None:
        try:
            f = by_pid.get(int(player_id))
        except (TypeError, ValueError):
            f = None
        if f is not None:
            return float(f)
    if player_name:
        f = by_name.get(_name_key(player_name))
        if f is not None:
            return float(f)
    return _DEFAULT_FACTOR


def apply_availability(
    player_id: Optional[int],
    q50: float,
    *,
    q10: Optional[float] = None,
    q90: Optional[float] = None,
    player_name: Optional[str] = None,
) -> Tuple[float, Optional[float], Optional[float]]:
    """Multiply q50 (and q10/q90 if supplied) by the availability factor.

    Edge case: when the factor is 0.0 (OUT / NOT WITH TEAM) the band
    collapses to (0, 0, 0) — that's intentional. The player will not
    play and any prop O/U on him is OUT-resolved at 0.

    Args:
        player_id:   NBA player_id (None falls back to name lookup).
        q50:         Median point estimate (raw-count units).
        q10:         Optional 10th-percentile (raw-count units).
        q90:         Optional 90th-percentile (raw-count units).
        player_name: Optional name for fallback lookup.

    Returns:
        (q50, q10, q90) tuple. q10 / q90 are None when not supplied.
    """
    factor = get_availability_factor(player_id=player_id,
                                     player_name=player_name)
    q50_adj = float(q50) * factor
    q10_adj = (float(q10) * factor) if q10 is not None else None
    q90_adj = (float(q90) * factor) if q90 is not None else None
    return q50_adj, q10_adj, q90_adj


def reset_cache() -> None:
    """Drop the in-process index. Used by tests to exercise the load path."""
    _CACHED["by_player_id"]   = None
    _CACHED["by_name"]        = None
    _CACHED["loaded_at"]      = 0.0
    _CACHED["snapshot_mtime"] = 0.0
