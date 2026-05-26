"""injury_availability.py — inference-time multiplicative `availability_factor`.

R15_W1 wiring of the R14_H4 ESPN injury feed into prop_pergame predictions.

This is INFERENCE-ONLY logic — the underlying model is not retrained. At
predict-time we look up the most-recent injury status for a player and
multiply the model's q50/q10/q90 outputs by an availability_factor in
[0.0, 1.0]:

    OUT, NOT WITH TEAM  → 0.00
    DOUBTFUL            → 0.30
    QUESTIONABLE        → 0.60
    PROBABLE            → 0.90
    AVAILABLE           → 1.00

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
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")

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


def _rebuild_indices() -> None:
    """Reload {player_id: factor} and {name_key: factor} from the latest snap."""
    payload = load_latest_snapshot() or {}
    by_pid: Dict[int, float] = {}
    by_name: Dict[str, float] = {}
    for rec in payload.get("players") or []:
        status = str(rec.get("status") or "").upper().strip()
        factor = AVAILABILITY_FACTOR.get(status)
        if factor is None:
            continue          # unknown bucket → skip, default 1.0 downstream
        pid_raw = rec.get("player_id")
        if pid_raw is not None:
            try:
                by_pid[int(pid_raw)] = float(factor)
            except (TypeError, ValueError):
                pass
        nm = _name_key(rec.get("player_name", ""))
        if nm:
            by_name[nm] = float(factor)
    _CACHED["by_player_id"]   = by_pid
    _CACHED["by_name"]        = by_name
    _CACHED["loaded_at"]      = time.time()
    snap_path = _latest_snapshot_path()
    _CACHED["snapshot_mtime"] = (
        os.path.getmtime(snap_path) if snap_path
        and os.path.exists(snap_path) else 0.0
    )


def _ensure_loaded(force: bool = False) -> None:
    """Lazy-load (or refresh) the in-process index."""
    if force or _CACHED["by_player_id"] is None:
        _rebuild_indices()
        return
    snap_path = _latest_snapshot_path()
    if snap_path is None:
        return
    try:
        current_mtime = os.path.getmtime(snap_path)
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
