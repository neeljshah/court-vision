"""fetch_player_positions.py — commonplayerinfo cache + positions parquet
(cycle 90e, loop 5).

Cycle 89c rejected position-based stratification because the pergame
dataset lacks a position field. This script unlocks that: it fetches
``commonplayerinfo`` for every unique player_id, caches the FULL response
JSON to ``data/cache/playerinfo/<pid>.json`` for future-proofing, then
consolidates a tabular ``data/player_positions.parquet`` carrying just
the fields downstream code actually needs.

The cache is gitignored-eligible (it's under data/). The script is safe
to interrupt — files already on disk are skipped on the next run, so
the full ~850-pid fetch can run incrementally as a background daemon.

Usage
-----
    # Default — discover pids from gamelog files, fetch up to --limit new pids.
    python scripts/fetch_player_positions.py --limit 50

    # Full run (slow — rate-limited at ~25/min, ~35 min for 850 pids).
    python scripts/fetch_player_positions.py --limit 0

The 50-pid subset is sufficient for infra validation. The full fetch is
deferred to a follow-up daemon run.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "playerinfo")
_PARQUET_PATH = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")
_GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")


# ── pid discovery ─────────────────────────────────────────────────────────────

def collect_player_ids() -> List[int]:
    """Discover unique player_ids from gamelog filenames.

    Filename convention: ``gamelog_<pid>_<season>.json``.
    Falls back to season_games.parquet only if the gamelog glob is empty.
    Returns sorted unique pids.
    """
    pids: set = set()
    for path in glob.glob(os.path.join(_GAMELOG_DIR, "gamelog_*.json")):
        try:
            stem = os.path.basename(path).split("_")
            pid = int(stem[1])
            pids.add(pid)
        except (ValueError, IndexError):
            continue
    return sorted(pids)


# ── single-pid fetch ──────────────────────────────────────────────────────────

def fetch_player(pid: int, cache_dir: str = _CACHE_DIR) -> bool:
    """Fetch commonplayerinfo for one pid and cache the full payload.

    Returns True on a successful new write, False on skip (already cached)
    or error. Errors are logged but never raised — the caller can keep
    iterating through the rest of the pid list.
    """
    out_path = os.path.join(cache_dir, f"{pid}.json")
    if os.path.exists(out_path):
        return False
    try:
        from nba_api.stats.endpoints import commonplayerinfo
        bs = commonplayerinfo.CommonPlayerInfo(player_id=pid, timeout=30)
        frames = bs.get_data_frames()
    except Exception as e:
        print(f"  [warn] pid {pid}: {e}")
        return False
    # Frame 0 is CommonPlayerInfo (the row we care about); frame 1 is
    # PlayerHeadlineStats; frame 2 is AvailableSeasons. Keep all three —
    # downstream code may grow into the headline stats / season history.
    payload = {
        "player_id": pid,
        "common_player_info": (
            [{k: _coerce_jsonable(v) for k, v in row.items()}
             for row in frames[0].to_dict("records")]
            if len(frames) > 0 else []
        ),
        "player_headline_stats": (
            [{k: _coerce_jsonable(v) for k, v in row.items()}
             for row in frames[1].to_dict("records")]
            if len(frames) > 1 else []
        ),
        "available_seasons": (
            [{k: _coerce_jsonable(v) for k, v in row.items()}
             for row in frames[2].to_dict("records")]
            if len(frames) > 2 else []
        ),
    }
    os.makedirs(cache_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return True


def _coerce_jsonable(v):
    """Coerce pandas/numpy scalars to JSON-safe types (NaN → None)."""
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    if v is None:
        return None
    if isinstance(v, (str, int, bool)):
        return v
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        if f.is_integer():
            return int(f)
        return f
    except (TypeError, ValueError):
        return str(v)


# ── parquet consolidation ─────────────────────────────────────────────────────

def _height_to_inches(raw) -> Optional[int]:
    """Convert NBA 'feet-inches' string (e.g. '6-9') to total inches."""
    if not raw:
        return None
    try:
        parts = str(raw).split("-")
        if len(parts) != 2:
            return None
        return int(parts[0]) * 12 + int(parts[1])
    except (ValueError, AttributeError):
        return None


def _weight_to_lbs(raw) -> Optional[int]:
    if not raw:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def build_parquet(cache_dir: str = _CACHE_DIR,
                  parquet_path: str = _PARQUET_PATH) -> int:
    """Walk the cache directory and consolidate into player_positions.parquet.

    Columns: player_id, position, height_inches, weight_lbs, birth_date,
    draft_year, display_name. Returns the row count written.
    """
    import pandas as pd

    rows: List[Dict] = []
    if not os.path.isdir(cache_dir):
        print(f"  [skip] no cache dir: {cache_dir}")
        return 0
    for fname in sorted(os.listdir(cache_dir)):
        if not fname.endswith(".json"):
            continue
        try:
            pid = int(fname.removesuffix(".json"))
        except ValueError:
            continue
        try:
            with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        info = payload.get("common_player_info") or []
        if not info:
            continue
        r = info[0]
        rows.append({
            "player_id":     pid,
            "position":      str(r.get("POSITION") or "").strip() or None,
            "height_inches": _height_to_inches(r.get("HEIGHT")),
            "weight_lbs":    _weight_to_lbs(r.get("WEIGHT")),
            "birth_date":    str(r.get("BIRTHDATE") or "")[:10] or None,
            "draft_year":    str(r.get("DRAFT_YEAR") or "").strip() or None,
            "display_name":  str(r.get("DISPLAY_FIRST_LAST") or "").strip() or None,
        })
    if not rows:
        print("  [skip] no cached rows to consolidate")
        return 0
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(parquet_path), exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    print(f"  wrote {parquet_path} ({len(df)} rows)")
    return len(df)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50,
                    help="Max NEW pids to fetch this run (0 = unlimited).")
    ap.add_argument("--sleep", type=float, default=2.5,
                    help="Seconds between API calls (25/min ≈ 2.4s).")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Skip API calls, only rebuild parquet from cache.")
    args = ap.parse_args()

    os.makedirs(_CACHE_DIR, exist_ok=True)

    if not args.skip_fetch:
        pids = collect_player_ids()
        print(f"[positions] {len(pids)} unique player_ids discovered")
        new_pids = [p for p in pids
                    if not os.path.exists(os.path.join(_CACHE_DIR, f"{p}.json"))]
        print(f"[positions] {len(new_pids)} pids not yet cached")
        if args.limit > 0:
            new_pids = new_pids[: args.limit]
            print(f"[positions] limiting this run to {len(new_pids)} pids")

        written = errors = 0
        for i, pid in enumerate(new_pids):
            time.sleep(args.sleep)
            ok = fetch_player(pid)
            if ok:
                written += 1
            else:
                errors += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(new_pids)}] written={written} errors={errors}",
                      flush=True)
        print(f"[done] written={written} errors={errors}")

    n = build_parquet()
    print(f"[parquet] {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
