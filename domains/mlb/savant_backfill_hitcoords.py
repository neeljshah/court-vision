"""domains.mlb.savant_backfill_hitcoords -- unblocks the pull-tendency x infield-
alignment prereg (domains/mlb/prereg_shift_framing.py H1, BLOCKED-on-premise: no
hc_x/hc_y/hit_location on savant_full__{2023,2024}.parquet -- see check_hit_coords).

SAME endpoint/pacing family as savant_backfill.py / acquire_statcast_fuller.py /
acquire_statcast_sample.py (no new source; the Savant CSV export already returns
these columns per-row, the prior lanes' client-side _KEEP just never selected
them). Widens savant_backfill._KEEP with hc_x, hc_y, hit_location (the exact
_HIT_COORD_COLS prereg_shift_framing.check_hit_coords looks for) plus
launch_speed_angle (bonus batted-ball-quality bucket, not hypothesis-mapped yet).

SEPARATE cache namespace (raw_days_hitcoords/) and SEPARATE output filename
(savant_hitcoords__<season>.parquet) -- per-day idempotency means a day already
cached under raw_days_savant/ WITHOUT these columns would silently never be
refetched if this lane wrote into that same namespace/file. Never touches
savant_full__2023.parquet or savant_full__2024.parquet (other lanes read them).

WRITES ONLY data/cache/statcast/. NEVER data/registry/, no sentinel, no flag, no
$/edge. ASCII-only; <=300 LOC. Per-file test in test_savant_backfill_hitcoords.py.
CLI: python -m domains.mlb.savant_backfill_hitcoords --season 2023 --max-seconds 900
     python -m domains.mlb.savant_backfill_hitcoords --season 2023 \
         --start 2023-05-01 --end 2023-05-07   # bounded validation slice
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from domains.mlb.acquire_statcast_sample import _HDR, _URL
from domains.mlb.savant_backfill import _KEEP as _SAVANT_KEEP, _season_days

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statcast"
_RAW_DIR = _CACHE / "raw_days_hitcoords"
_REPORT_FP = _REPO / "data" / "domains" / "mlb" / "savant_hitcoords_report.json"

_DELAY_S = 3.0  # same politeness as savant_backfill.py
_MAX_CONSECUTIVE_FAILURES = 3

# NEW columns this lane unlocks, mapped to the BLOCKED hypothesis each feeds.
_NEW_COLS: Dict[str, str] = {
    "hc_x": "pull-tendency x infield alignment (hit coordinate x)",
    "hc_y": "pull-tendency x infield alignment (hit coordinate y)",
    "hit_location": "pull-tendency x infield alignment (fielder position id)",
    "launch_speed_angle": "batted-ball quality bucket (bonus, not hypothesis-mapped this pass)",
}
# strict superset of savant_backfill's already-widened _KEEP (bb_type, on_1b/2b/3b,
# launch_angle, description, base + score cols) plus this lane's additions.
_KEEP = list(_SAVANT_KEEP) + list(_NEW_COLS.keys())


def _day_csv_hitcoords(day: str, timeout: int = 90) -> Optional[pd.DataFrame]:
    """One day, widened _KEEP. Returns None on ANY failure -- caller counts
    consecutive Nones toward the stop-rule (same contract as savant_backfill)."""
    params = {"all": "true", "type": "details", "game_date_gt": day,
              "game_date_lt": day, "min_pitches": "0", "min_results": "0",
              "group_by": "name", "sort_col": "pitches", "player_type": "pitcher",
              "min_pas": "0"}
    try:
        r = requests.get(_URL, params=params, headers=_HDR, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("day %s request exception: %s", day, exc)
        return None
    if r.status_code != 200 or len(r.content) < 200:
        log.warning("day %s HTTP %s bytes %s", day, r.status_code, len(r.content))
        return None
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    keep = [c for c in _KEEP if c in df.columns]
    return df[keep].copy()


def _fetch_new_days(days: List[str], raw_dir: Path, delay_s: float,
                    max_seconds: Optional[float]) -> Dict[str, object]:
    """FETCH step: walks `days` not already cached, stops on wall-clock budget OR
    _MAX_CONSECUTIVE_FAILURES in a row (politeness stop-rule) -- whichever first."""
    fetched: List[str] = []
    consecutive_failures = 0
    stopped_reason = None
    t0 = time.monotonic()
    for day in days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            continue
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            stopped_reason = "max_seconds"
            break
        df = _day_csv_hitcoords(day)
        if df is None:
            consecutive_failures += 1
            log.warning("consecutive_failures=%d after day %s", consecutive_failures, day)
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                stopped_reason = "consecutive_failures"
                break
            time.sleep(delay_s)
            continue
        consecutive_failures = 0
        if df.empty:
            time.sleep(delay_s)
            continue
        tmp = fp.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(fp)
        fetched.append(day)
        log.info("fetched %s rows=%d", day, len(df))
        time.sleep(delay_s)
    return {"fetched_days": fetched, "stopped_reason": stopped_reason,
            "consecutive_failures_at_stop": consecutive_failures}


def _materialize(days: List[str], raw_dir: Path) -> List[pd.DataFrame]:
    parts = []
    for day in days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            parts.append(pd.read_parquet(fp))
    return parts


def _coverage(df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    """Honest per-column coverage. hc_x/hc_y/hit_location are only populated on
    BATTED-BALL rows (bb_type notna / type=='X') -- report both the raw non-null
    rate and the in-play-only rate so a low raw rate isn't mistaken for a fetch bug."""
    rep: Dict[str, Dict[str, object]] = {}
    in_play = df[df["bb_type"].notna()] if "bb_type" in df.columns else df.iloc[0:0]
    for col, unlocks in _NEW_COLS.items():
        if col not in df.columns:
            rep[col] = {"obtained": False, "coverage_pct": 0.0,
                        "coverage_pct_in_play": 0.0, "unlocks": unlocks}
        else:
            nn = float(df[col].notna().mean()) if len(df) else 0.0
            nn_ip = float(in_play[col].notna().mean()) if len(in_play) else 0.0
            rep[col] = {"obtained": True, "coverage_pct": round(nn * 100.0, 2),
                        "coverage_pct_in_play": round(nn_ip * 100.0, 2), "unlocks": unlocks}
    return rep


def run_days(days: List[str], season: int, max_seconds: Optional[float] = None,
            cache_dir: Optional[Path] = None,
            out_name: Optional[str] = None) -> Dict[str, object]:
    """Fetch (bounded + failure-stopped) then materialize (unbounded) an explicit
    day list, write data/cache/statcast/<out_name>.parquet, return honest stats.
    `days` restricted to `season` is the caller's job (see run_season / --start/--end)."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days_hitcoords"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetch = _fetch_new_days(days, raw_dir, _DELAY_S, max_seconds)
    parts = _materialize(days, raw_dir)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not df.empty and "game_date" in df.columns:
        df = df[df["game_date"].astype(str).isin(days)].reset_index(drop=True)
    days_done = len(parts)
    status = "OK"
    if fetch["stopped_reason"] == "consecutive_failures":
        status = "FAILED_CONSECUTIVE"
    elif fetch["stopped_reason"] == "max_seconds" and days_done < len(days):
        status = "PARTIAL_CAPPED"
    elif df.empty:
        status = "INSUFFICIENT_DATA"
    out: Dict[str, object] = {
        "season": season, "status": status, "raw_rows": int(len(df)),
        "days_requested": len(days), "days_fetched_this_run": len(fetch["fetched_days"]),
        "days_available_total": days_done, "stopped_reason": fetch["stopped_reason"],
    }
    if not df.empty:
        name = out_name or f"savant_hitcoords__{season}.parquet"
        out_fp = cdir / name
        df.to_parquet(out_fp, index=False)
        out["parquet"] = str(out_fp)
        out["date_range"] = [str(df["game_date"].min()), str(df["game_date"].max())]
        out["coverage"] = _coverage(df)
    return out


def run_season(season: int, max_seconds: Optional[float] = None,
              cache_dir: Optional[Path] = None) -> Dict[str, object]:
    """Full-season resumable run (this season's real game-days, from savant_backfill's
    own probables-derived _season_days -- no guessed calendar bounds)."""
    return run_days(_season_days(season), season, max_seconds=max_seconds, cache_dir=cache_dir)


def run_priority(seasons_max_seconds: Dict[int, float]) -> Dict[str, object]:
    per_season: Dict[str, object] = {}
    for season, budget in seasons_max_seconds.items():
        per_season[str(season)] = run_season(season, max_seconds=budget)
    report = {
        "corpus_id": "savant_hitcoords_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "baseballsavant statcast_search CSV (keyless, same endpoint as "
                   "savant_backfill/acquire_statcast_fuller/acquire_statcast_sample)",
        "cols_added": list(_NEW_COLS.keys()),
        "seasons": per_season,
    }
    _REPORT_FP.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FP, "w", encoding="ascii", errors="replace") as f:
        json.dump(report, f, indent=2, default=str)
    report["report_path"] = str(_REPORT_FP)
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Resumable keyless Savant hit-coordinate backfill.")
    ap.add_argument("--season", type=int, default=None, help="single season; omit to run --priority")
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--priority", default="2023,2024",
                    help="comma-separated season order when --season is omitted")
    ap.add_argument("--start", default=None, help="bounded validation slice: first game_date (YYYY-MM-DD)")
    ap.add_argument("--end", default=None, help="bounded validation slice: last game_date (YYYY-MM-DD, inclusive)")
    a = ap.parse_args(argv)
    if a.start and a.end:
        if not a.season:
            raise SystemExit("--start/--end requires --season")
        days = [d for d in _season_days(a.season) if a.start <= d <= a.end]
        res = run_days(days, a.season, max_seconds=a.max_seconds)
    elif a.season:
        res = run_season(a.season, max_seconds=a.max_seconds)
    else:
        seasons = [int(s) for s in a.priority.split(",") if s.strip()]
        res = run_priority({s: a.max_seconds for s in seasons})
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["run_days", "run_season", "run_priority", "_day_csv_hitcoords",
           "_coverage", "_KEEP", "_NEW_COLS", "_CACHE", "_RAW_DIR", "_REPO",
           "_DELAY_S", "_MAX_CONSECUTIVE_FAILURES"]
