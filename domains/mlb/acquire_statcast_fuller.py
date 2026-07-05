"""domains.mlb.acquire_statcast_fuller -- BROADER keyless pull of the ALREADY-USED public
Statcast source (baseballsavant CSV export, same endpoint acquire_statcast_sample /
acquire_statcast_overlap wrap), widening kept-columns to unlock FUTURE research
surfaces: catcher_framing, umpire_zone_shape, defensive_positioning, batter platoon
splits. NO NEW SOURCE -- reuses acquire_statcast_sample's URL/params/pacing/per-day
idempotency into a SEPARATE cache namespace (raw_days_fuller/) so it never clobbers
the narrower cached days the SP-fatigue gate depends on.

MATERIALIZE ONLY -- no gate in this lane. Writes a per-season fuller parquet plus an
honest per-column coverage report (data/domains/mlb/statcast_fuller_report.json): which
new columns the endpoint actually returned, non-null coverage, date range, row count.
A rejected or always-null column is reported honestly, never papered over.

BOUNDED, checkpointed per-day (atomic writes, as_of/corpus_id at creation), resumable --
a capped run reports partial, honest progress rather than truncating.

FULL-SEASON EXTENSION (--full-season): widens the day-list from the ~18-36 day _WINDOWS
sample to the FULL real regular season (schedule from probables.parquet, fallback bounds
in _FULL_SEASON_BOUNDS) -- a capped run covers fewer of the ~180 game-days; the next
invocation resumes from the per-day cache.

WRITES ONLY data/cache/statcast/raw_days_fuller/ and data/domains/mlb/. NEVER
data/registry/, no sentinel, no flag, no $/edge. ASCII-only; <=300 LOC.
CLI: python -m domains.mlb.acquire_statcast_fuller --full-season --max-seconds 1200
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from domains.mlb.acquire_statcast_sample import _DELAY_S, _URL, _HDR, _WINDOWS, _date_range

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statcast"
_OUT_DIR = _REPO / "data" / "domains" / "mlb"
_REPORT_FP = _OUT_DIR / "statcast_fuller_report.json"
_PROBABLES_FP = _OUT_DIR / "probables.parquet"

# FULL regular-season boundaries, derived from data/domains/mlb/probables.parquet (real
# schedule, not guessed): 2022-04-07..10-05 (180 game-days), 2023-03-30..10-01 (183
# game-days) -- verified 2026-07-04 via probables['game_date'] min/max per season.
_FULL_SEASON_BOUNDS = {
    2022: ("2022-04-07", "2022-10-05"),
    2023: ("2023-03-30", "2023-10-01"),
}


def _full_season_days(season: int) -> List[str]:
    """Actual game-days for `season` from the on-disk schedule (probables.parquet) when
    available -- skips true off-days (All-Star break) vs a wasted fetch+delay. Falls
    back to a plain calendar range over _FULL_SEASON_BOUNDS if the parquet is missing."""
    lo, hi = _FULL_SEASON_BOUNDS.get(season, (f"{season}-04-01", f"{season}-10-01"))
    if _PROBABLES_FP.exists():
        try:
            pdf = pd.read_parquet(_PROBABLES_FP, columns=["game_date"])
            gd = pd.to_datetime(pdf["game_date"])
            days = sorted(gd[(gd >= lo) & (gd <= hi)].dt.strftime("%Y-%m-%d").unique().tolist())
            if days:
                return days
        except Exception:
            log.warning("probables schedule read failed, falling back to calendar range")
    d0, d1 = pd.Timestamp(lo), pd.Timestamp(hi)
    return [(d0 + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]

# the ORIGINAL 18-col _KEEP from acquire_statcast_sample, reused verbatim so a fuller
# pull is a strict superset (nothing already-relied-upon is dropped).
_BASE_KEEP = ["game_pk", "game_date", "inning", "inning_topbot", "at_bat_number",
              "pitch_number", "pitcher", "batter", "events", "release_speed",
              "release_spin_rate", "estimated_woba_using_speedangle", "pitch_type",
              "balls", "strikes", "outs_when_up", "home_team", "away_team"]
# score cols (as in acquire_statcast_overlap) so the fuller pull is overlap-capable too.
_SCORE_COLS = ["home_score", "away_score", "bat_score", "post_home_score",
               "post_away_score", "launch_speed"]
# NEW columns this lane unlocks, mapped to the research surface each feeds.
_NEW_COLS = {
    "zone": "umpire_zone_shape+catcher_framing",       # 1-14 strike-zone grid location
    "type": "umpire_zone_shape",                       # S/B/X pitch-result code
    "des": "umpire_zone_shape",                         # text desc (called_strike etc)
    "fielder_2": "catcher_framing",                     # catcher's MLBAM id
    "stand": "batter_platoon_splits",                   # batter handedness L/R
    "p_throws": "batter_platoon_splits",                # pitcher handedness L/R
    "if_fielding_alignment": "defensive_positioning",   # infield shift label
    "of_fielding_alignment": "defensive_positioning",   # outfield shift label
    "plate_x": "umpire_zone_shape+catcher_framing",     # horizontal pitch location (ft)
    "plate_z": "umpire_zone_shape+catcher_framing",     # vertical pitch location (ft)
    "sz_top": "umpire_zone_shape",                      # batter's strike zone top (ft)
    "sz_bot": "umpire_zone_shape",                      # batter's strike zone bottom (ft)
}
_KEEP = _BASE_KEEP + _SCORE_COLS + list(_NEW_COLS.keys())
_RAW_DIR = _CACHE / "raw_days_fuller"


def _replace_with_retry(tmp: Path, fp: Path, tries: int = 5, backoff_s: float = 0.5) -> None:
    """tmp.replace(fp) retried vs transient Windows rename races (AV/indexer touching
    the path mid-move: Permission/FileNotFound even if the move already landed)."""
    for i in range(tries):
        try:
            return tmp.replace(fp)
        except (PermissionError, FileNotFoundError):
            if fp.exists() and not tmp.exists():
                return  # rename actually succeeded despite the raised exception
            if i == tries - 1:
                raise
            time.sleep(backoff_s * (i + 1))


def _day_csv_fuller(day: str, timeout: int = 90) -> Optional[pd.DataFrame]:
    """Same endpoint/params as acquire_statcast_sample._day_csv, widened _KEEP."""
    params = {"all": "true", "type": "details", "game_date_gt": day,
              "game_date_lt": day, "min_pitches": "0", "min_results": "0",
              "group_by": "name", "sort_col": "pitches", "player_type": "pitcher",
              "min_pas": "0"}
    r = requests.get(_URL, params=params, headers=_HDR, timeout=timeout)
    if r.status_code != 200 or len(r.content) < 200:
        log.warning("day %s HTTP %s bytes %s", day, r.status_code, len(r.content))
        return None
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    keep = [c for c in _KEEP if c in df.columns]
    return df[keep].copy()


def _fetch_new_days(all_days: List[str], raw_dir: Path, delay_s: float,
                    max_seconds: Optional[float]) -> Dict[str, object]:
    """FETCH step only: walks `all_days` and fetches any NOT already cached in raw_dir,
    writing each atomically. The wall-clock budget (`max_seconds`) applies ONLY here --
    it bounds how much NEW network fetching this invocation does. It does NOT gate which
    cached days get read back later (that is MATERIALIZE's job, see
    _materialize_all_cached, and it always includes every cached day regardless of where
    a budget-cap left off on a previous run). Returns fetched_days + capped flag."""
    fetched_days: List[str] = []
    t0 = time.monotonic()
    capped = False
    for day in all_days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            continue
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            capped = True
            break
        df = _day_csv_fuller(day)
        if df is None or df.empty:
            time.sleep(delay_s)
            continue
        tmp = fp.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        _replace_with_retry(tmp, fp)  # atomic rename; retried vs transient Windows locks
        fetched_days.append(day)
        log.info("fetched %s rows=%d", day, len(df))
        time.sleep(delay_s)
    return {"fetched_days": fetched_days, "capped": capped}


def _materialize_all_cached(all_days: List[str], raw_dir: Path) -> List[pd.DataFrame]:
    """MATERIALIZE step only: reads back EVERY day in `all_days` that has a cache file on
    disk, unconditionally -- no wall-clock budget applies here. This is the fix for the
    stranded-checkpoint bug: a prior capped FETCH run may have left cached days AFTER the
    day it broke on (e.g. a later resumed run cached more days than an earlier session
    materialized), and those must still be included."""
    parts: List[pd.DataFrame] = []
    for day in all_days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            parts.append(pd.read_parquet(fp))
    return parts


def acquire_season_fuller(season: int, days: int = 18, delay_s: float = _DELAY_S,
                          cache_dir: Optional[Path] = None,
                          max_seconds: Optional[float] = None,
                          full_season: bool = False) -> Dict[str, object]:
    """Acquire a season sample with the WIDENED column set, split into two independent
    steps: FETCH (bounded by max_seconds, only touches days not yet cached) then
    MATERIALIZE (unbounded, reads back EVERY cached day in raw_days_fuller/ regardless of
    whether this run's fetch step reached it). This is the fix for the wave-39 stranded-
    checkpoint bug: previously a single loop fetched AND collected in the same pass, so
    hitting the wall-clock budget at the Nth day meant every ALREADY-cached day after N
    (from a prior run) was silently dropped from the output, even though it was sitting
    on disk the whole time. Per-day cached + idempotent under raw_days_fuller/ (a separate
    namespace from the narrower sample's raw_days/, so neither pull clobbers the other).

    full_season=True switches the day-list from the bounded _WINDOWS sample to the FULL
    real schedule (via _full_season_days), so a resumed job eventually covers the whole
    season rather than the original ~18-36 day window."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days_fuller"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if full_season:
        all_days = _full_season_days(season)
    else:
        starts = _WINDOWS.get(season, [f"{season}-05-01"])
        per_window = max(1, math.ceil(days / len(starts)))
        all_days = [d for ws in starts for d in _date_range(ws, per_window)]
    fetch = _fetch_new_days(all_days, raw_dir, delay_s, max_seconds)
    parts = _materialize_all_cached(all_days, raw_dir)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not out.empty:
        out = out[pd.to_datetime(out["game_date"]).dt.year == season].reset_index(drop=True)
    return {"df": out, "days_requested": len(all_days),
            "days_fetched_this_run": len(fetch["fetched_days"]),
            "days_available_total": len(parts), "capped": fetch["capped"]}


def _coverage_report(df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    """Honest per-column coverage: requested vs obtained vs non-null fraction."""
    rep: Dict[str, Dict[str, object]] = {}
    for col, surfaces in _NEW_COLS.items():
        if col not in df.columns:
            rep[col] = {"obtained": False, "coverage_pct": 0.0, "surfaces": surfaces}
        else:
            nn = float(df[col].notna().mean()) if len(df) else 0.0
            rep[col] = {"obtained": True, "coverage_pct": round(nn * 100.0, 2),
                        "surfaces": surfaces}
    return rep


def run_season_fuller(season: int, days: int = 18, cache_dir: Optional[Path] = None,
                      max_seconds: Optional[float] = None,
                      full_season: bool = False) -> Dict[str, object]:
    """Acquire the widened sample for one season, write parquet, return honest stats."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    cdir.mkdir(parents=True, exist_ok=True)
    acq = acquire_season_fuller(season, days=days, cache_dir=cdir, max_seconds=max_seconds,
                                full_season=full_season)
    df = acq["df"]
    if df.empty:
        return {"season": season, "status": "INSUFFICIENT_DATA", "raw_rows": 0,
                "capped": acq["capped"], "days_fetched_this_run": acq["days_fetched_this_run"]}
    out_fp = cdir / f"statcast_fuller__{season}.parquet"
    df.to_parquet(out_fp, index=False)
    date_range = [str(df["game_date"].min()), str(df["game_date"].max())]
    status = "PARTIAL_CAPPED" if acq["capped"] else "OK"
    return {"season": season, "status": status, "raw_rows": int(len(df)),
            "raw_parquet": str(out_fp), "date_range": date_range,
            "days_fetched_this_run": acq["days_fetched_this_run"],
            "days_available_total": acq["days_available_total"],
            "days_requested": acq["days_requested"],
            "cols_requested": list(_NEW_COLS.keys()),
            "cols_obtained": [c for c in _NEW_COLS if c in df.columns],
            "coverage": _coverage_report(df)}


def run_all(seasons: List[int] = (2022, 2023), days: int = 18,
           max_seconds: Optional[float] = None,
           full_season: bool = False) -> Dict[str, object]:
    """Run the fuller pull across both sample seasons; write the honest materialization
    report to data/domains/mlb/statcast_fuller_report.json. full_season=True +
    seasons=(2023, 2022): 2023 (fresher) is prioritized within the shared wall-clock
    budget, then 2022 gets whatever remains -- repeated invocations eventually cover
    both full seasons via the per-day cache checkpoint (resumable, no re-fetch)."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_season: Dict[str, object] = {}
    remaining = max_seconds
    t0 = time.monotonic()
    for s in seasons:
        season_budget = None
        if remaining is not None:
            season_budget = max(0.0, remaining - (time.monotonic() - t0))
        per_season[str(s)] = run_season_fuller(s, days=days, max_seconds=season_budget,
                                                full_season=full_season)
    total_rows = sum(r.get("raw_rows", 0) for r in per_season.values())
    any_capped = any(r.get("status") == "PARTIAL_CAPPED" for r in per_season.values())
    days_done = sum(r.get("days_available_total", 0) for r in per_season.values())
    days_total = sum(r.get("days_requested", 0) for r in per_season.values())
    report = {
        "corpus_id": "statcast_fuller_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "baseballsavant statcast_search CSV (same keyless endpoint as "
                   "acquire_statcast_sample/acquire_statcast_overlap)",
        "cols_requested": list(_NEW_COLS.keys()),
        "seasons": per_season,
        "total_rows": total_rows,
        "any_capped": any_capped,
        "full_season": full_season,
        "days_done": days_done,
        "days_total": days_total,
        "verdict": "PARTIAL_CAPPED" if any_capped else "MATERIALIZED",
        "note": ("full-season extension in progress -- resumable, next wave continues "
                  "via the per-day raw_days_fuller/ cache." if full_season and any_capped
                  else "materialize-only lane; no gate run here. Unlocks catcher_framing, "
                       "umpire_zone_shape, defensive_positioning, batter platoon splits as "
                       "FUTURE research surfaces."),
    }
    with open(_REPORT_FP, "w", encoding="ascii", errors="replace") as f:
        json.dump(report, f, indent=2)
    report["report_path"] = str(_REPORT_FP)
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Broader keyless Statcast pull (fuller cols).")
    ap.add_argument("--season", type=int, default=None,
                    help="single season; omit to run both (order set by --priority)")
    ap.add_argument("--days", type=int, default=18)
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--full-season", action="store_true",
                    help="pull the FULL real schedule (resumable), not _WINDOWS sample")
    ap.add_argument("--priority", default="2023,2022",
                    help="comma-separated season order for --full-season (2023 first)")
    a = ap.parse_args(argv)
    fs = a.full_season
    if a.season:
        res = run_season_fuller(a.season, days=a.days, max_seconds=a.max_seconds, full_season=fs)
    else:
        seasons = [int(s) for s in a.priority.split(",") if s.strip()]
        res = run_all(seasons=seasons, days=a.days, max_seconds=a.max_seconds, full_season=fs)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["acquire_season_fuller", "run_season_fuller", "run_all", "_day_csv_fuller",
           "_coverage_report", "_KEEP", "_NEW_COLS", "_BASE_KEEP", "_SCORE_COLS",
           "_CACHE", "_OUT_DIR", "_REPORT_FP", "_REPO", "_full_season_days",
           "_FULL_SEASON_BOUNDS", "_PROBABLES_FP"]
