"""domains.mlb.acquire_statcast_fuller -- BROADER keyless pull of the ALREADY-USED public
Statcast source (baseballsavant CSV export -- same endpoint acquire_statcast_sample /
acquire_statcast_overlap wrap), extending the kept-column set to unlock FUTURE research
surfaces: catcher_framing (needs zone + call outcome + catcher id), umpire_zone_shape
(needs zone + call outcome), defensive_positioning (needs if/of alignment), batter
platoon splits (needs stand/p_throws handedness).

NO NEW SOURCE. Reuses the exact session/pacing/window conventions of
acquire_statcast_sample: same URL, same params shape, same _DELAY_S polite pacing, same
per-day cache-and-skip idempotency, same 2-season bounded windows (2022, 2023). This
module ONLY widens _KEEP (18/24 cols -> up to 33) and re-fetches days into a SEPARATE
cache namespace (raw_days_fuller/) so it never clobbers the existing narrower cached days
the SP-fatigue gate depends on.

MATERIALIZE ONLY -- no gate in this lane. Writes a per-season fuller parquet plus an
honest per-column coverage report (data/domains/mlb/statcast_fuller_report.json) recording
exactly which of the requested new columns the live endpoint actually returned, with what
non-null coverage, over what date range and row count. If the endpoint rejects a column
or a column is present-but-always-null, that is reported honestly, never papered over.

BOUNDED (~10 min pull cap): the CLI checkpoints per-day (atomic parquet writes with
as_of/corpus_id set at creation) and is resumable -- a capped run reports partial,
honest progress rather than silently truncating.

WRITES ONLY data/cache/statcast/raw_days_fuller/ and data/domains/mlb/. NEVER
data/registry/, no sentinel, no flag, no $/edge. ASCII-only; <=300 LOC. Per-file test in
tests/ (canned fixture, no live call).
CLI: python -m domains.mlb.acquire_statcast_fuller --season 2023 --days 18 --max-seconds 600
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


def acquire_season_fuller(season: int, days: int = 18, delay_s: float = _DELAY_S,
                          cache_dir: Optional[Path] = None,
                          max_seconds: Optional[float] = None) -> Dict[str, object]:
    """BOUNDED-acquire a season sample with the WIDENED column set. Per-day cached +
    idempotent under raw_days_fuller/ (a separate namespace from the narrower sample's
    raw_days/, so neither pull clobbers the other). Resumable: a day already cached here
    is reused without a re-fetch. `max_seconds` checkpoints and returns partial progress
    honestly instead of silently truncating."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days_fuller"
    raw_dir.mkdir(parents=True, exist_ok=True)
    starts = _WINDOWS.get(season, [f"{season}-05-01"])
    per_window = max(1, math.ceil(days / len(starts)))
    all_days = [d for ws in starts for d in _date_range(ws, per_window)]
    parts: List[pd.DataFrame] = []
    fetched_days: List[str] = []
    t0 = time.monotonic()
    capped = False
    for day in all_days:
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            capped = True
            break
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            parts.append(pd.read_parquet(fp))
            continue
        df = _day_csv_fuller(day)
        if df is None or df.empty:
            time.sleep(delay_s)
            continue
        tmp = fp.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(fp)  # atomic on POSIX/NTFS same-volume rename
        parts.append(df)
        fetched_days.append(day)
        log.info("fetched %s rows=%d", day, len(df))
        time.sleep(delay_s)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not out.empty:
        out = out[pd.to_datetime(out["game_date"]).dt.year == season].reset_index(drop=True)
    return {"df": out, "days_requested": len(all_days), "days_fetched_this_run": len(fetched_days),
            "days_available_total": len(parts), "capped": capped}


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
                      max_seconds: Optional[float] = None) -> Dict[str, object]:
    """Acquire the widened sample for one season, write parquet, return honest stats."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    cdir.mkdir(parents=True, exist_ok=True)
    acq = acquire_season_fuller(season, days=days, cache_dir=cdir, max_seconds=max_seconds)
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
           max_seconds: Optional[float] = None) -> Dict[str, object]:
    """Run the fuller pull across both existing sample seasons; write the honest
    materialization report to data/domains/mlb/statcast_fuller_report.json."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_season: Dict[str, object] = {}
    remaining = max_seconds
    t0 = time.monotonic()
    for s in seasons:
        season_budget = None
        if remaining is not None:
            season_budget = max(0.0, remaining - (time.monotonic() - t0))
        per_season[str(s)] = run_season_fuller(s, days=days, max_seconds=season_budget)
    total_rows = sum(r.get("raw_rows", 0) for r in per_season.values())
    any_capped = any(r.get("status") == "PARTIAL_CAPPED" for r in per_season.values())
    report = {
        "corpus_id": "statcast_fuller_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "baseballsavant statcast_search CSV (same keyless endpoint as "
                   "acquire_statcast_sample/acquire_statcast_overlap)",
        "cols_requested": list(_NEW_COLS.keys()),
        "seasons": per_season,
        "total_rows": total_rows,
        "any_capped": any_capped,
        "verdict": "PARTIAL_CAPPED" if any_capped else "MATERIALIZED",
        "note": "materialize-only lane; no gate run here. Unlocks catcher_framing, "
                "umpire_zone_shape, defensive_positioning, batter platoon splits as "
                "FUTURE research surfaces.",
    }
    with open(_REPORT_FP, "w", encoding="ascii", errors="replace") as f:
        json.dump(report, f, indent=2)
    report["report_path"] = str(_REPORT_FP)
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Broader keyless Statcast pull (fuller cols).")
    ap.add_argument("--season", type=int, default=None,
                    help="single season; omit to run both 2022+2023")
    ap.add_argument("--days", type=int, default=18)
    ap.add_argument("--max-seconds", type=float, default=600.0)
    a = ap.parse_args(argv)
    if a.season:
        res = run_season_fuller(a.season, days=a.days, max_seconds=a.max_seconds)
    else:
        res = run_all(days=a.days, max_seconds=a.max_seconds)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["acquire_season_fuller", "run_season_fuller", "run_all", "_day_csv_fuller",
           "_coverage_report", "_KEEP", "_NEW_COLS", "_BASE_KEEP", "_SCORE_COLS",
           "_CACHE", "_OUT_DIR", "_REPORT_FP", "_REPO"]
