"""domains.mlb.savant_backfill -- resumable keyless Savant pull that unblocks the 5
prereg-BLOCKED MLB hypotheses in domains/mlb/prereg/mlb_hypotheses.py (missing
on_1b/on_2b/on_3b, launch_angle, and any 2024+ season). SAME endpoint/pacing family
as acquire_statcast_sample/acquire_statcast_fuller (no new source) -- widens _KEEP
further and adds NEW seasons via a SEPARATE cache namespace (raw_days_savant/) so it
never clobbers statcast_fuller__2022/2023 or the SP-fatigue sample.

NEW columns vs statcast_fuller: on_1b, on_2b, on_3b (base-runner state, MLBAM ids of
the runner or NaN), launch_angle, description (the per-PITCH result code: ball,
called_strike, swinging_strike, foul, hit_into_play, ... -- distinct from the
already-present 'des', which is prose), bb_type (ground_ball/line_drive/fly_ball/
popup, needed for "contact type").

PRIORITY (see run_priority): (a) 2024 full season -- independent-season replication
target for the 3 provisional MLB survivors: platoon x pitch-type, count-leverage x
mix, velo-band x TTO; (b) 2022/2023 column refresh (same widened _KEEP, separate
namespace); (c) 2025.

DAY LIST comes from the corpus's OWN schedule (data/domains/mlb/probables.parquet,
game_date filtered to the season) -- no guessed calendar bounds, no off-days in the
list, so a fetch failure is unambiguous (not a legitimate day-off).

POLITENESS (binding): 1 day/request, _DELAY_S=3.0s between requests, per-day
checkpointed + idempotent (raw_days_savant/day__<date>.parquet), STOPS after 3
consecutive request failures (does not hammer) and reports FAILED_CONSECUTIVE
honestly rather than proxy-shopping.

WRITES ONLY data/cache/statcast/. NEVER data/registry/, no sentinel, no flag, no
$/edge. ASCII-only; <=300 LOC. Per-file test in test_savant_backfill.py.
CLI: python -m domains.mlb.savant_backfill --season 2024 --max-seconds 900
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

from domains.mlb.acquire_statcast_fuller import _BASE_KEEP, _NEW_COLS as _FULLER_NEW_COLS
from domains.mlb.acquire_statcast_sample import _HDR, _URL

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statcast"
_RAW_DIR = _CACHE / "raw_days_savant"
_PROBABLES_FP = _REPO / "data" / "domains" / "mlb" / "probables.parquet"
_REPORT_FP = _REPO / "data" / "domains" / "mlb" / "savant_backfill_report.json"

_DELAY_S = 3.0  # politeness: 2-3s between per-day requests
_MAX_CONSECUTIVE_FAILURES = 3

# columns unlocked THIS lane, mapped to the BLOCKED hypothesis each feeds (see
# domains/mlb/prereg/mlb_hypotheses.py BLOCKED_REASONS).
_NEW_COLS: Dict[str, str] = {
    "on_1b": "base-out state x contact type (GB/FB)",
    "on_2b": "base-out state x contact type (GB/FB)",
    "on_3b": "base-out state x contact type (GB/FB)",
    "launch_angle": "launch-angle tightness x park factor",
    "release_extension": "SP in-game fatigue deltas (mlb_sp_ingame_fatigue_* templates)",
    "bb_type": "base-out state x contact type (GB/FB)",  # GB/FB label
    "description": "premise-only: real per-pitch S/B/X sub-code (not wired to a "
                    "hypothesis this pass)",
}
# superset: statcast_fuller's full kept set (base + score + its own _NEW_COLS) plus
# this lane's additions. Strict superset -- nothing previously relied upon is dropped.
_KEEP = (_BASE_KEEP + ["home_score", "away_score", "bat_score", "post_home_score",
                       "post_away_score", "launch_speed"] +
         list(_FULLER_NEW_COLS.keys()) + list(_NEW_COLS.keys()))


def _season_days(season: int) -> List[str]:
    """This season's actual game-days from the corpus's own schedule (probables.
    parquet). No off-days in the list -> a None fetch result is unambiguously a
    request failure, never a legitimate empty day. Falls back to a calendar guess
    only if the schedule parquet is missing entirely."""
    if _PROBABLES_FP.exists():
        pdf = pd.read_parquet(_PROBABLES_FP, columns=["game_date"])
        gd = pd.to_datetime(pdf["game_date"])
        days = sorted(gd[gd.dt.year == season].dt.strftime("%Y-%m-%d").unique().tolist())
        if days:
            return days
    log.warning("probables schedule has no rows for %s, falling back to calendar guess", season)
    d0, d1 = pd.Timestamp(f"{season}-03-20"), pd.Timestamp(f"{season}-10-05")
    return [(d0 + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)]


def _day_csv_savant(day: str, timeout: int = 90) -> Optional[pd.DataFrame]:
    """One day, widened _KEEP. Returns None on ANY failure (bad status, short body,
    network exception) -- the caller counts consecutive Nones toward the stop-rule."""
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
        df = _day_csv_savant(day)
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
    """Read back EVERY cached day in `days`, unconditionally (no wall-clock budget)."""
    parts = []
    for day in days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            parts.append(pd.read_parquet(fp))
    return parts


def _coverage(df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    rep: Dict[str, Dict[str, object]] = {}
    for col, unlocks in _NEW_COLS.items():
        if col not in df.columns:
            rep[col] = {"obtained": False, "coverage_pct": 0.0, "unlocks": unlocks}
        else:
            nn = float(df[col].notna().mean()) if len(df) else 0.0
            rep[col] = {"obtained": True, "coverage_pct": round(nn * 100.0, 2), "unlocks": unlocks}
    return rep


def run_season(season: int, max_seconds: Optional[float] = None,
              cache_dir: Optional[Path] = None) -> Dict[str, object]:
    """Fetch (bounded + failure-stopped) then materialize (unbounded) one season,
    write data/cache/statcast/savant_full__<season>.parquet, return honest stats."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days_savant"
    raw_dir.mkdir(parents=True, exist_ok=True)
    days = _season_days(season)
    fetch = _fetch_new_days(days, raw_dir, _DELAY_S, max_seconds)
    parts = _materialize(days, raw_dir)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not df.empty:
        df = df[pd.to_datetime(df["game_date"]).dt.year == season].reset_index(drop=True)
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
        out_fp = cdir / f"savant_full__{season}.parquet"
        df.to_parquet(out_fp, index=False)
        out["parquet"] = str(out_fp)
        out["date_range"] = [str(df["game_date"].min()), str(df["game_date"].max())]
        out["coverage"] = _coverage(df)
    return out


def run_priority(seasons_max_seconds: Dict[int, float]) -> Dict[str, object]:
    """Run several seasons in priority order (dict insertion order = priority: caller
    passes {2024: budget, 2022: budget, 2023: budget, 2025: budget}). Writes the
    honest per-season report to data/domains/mlb/savant_backfill_report.json."""
    per_season: Dict[str, object] = {}
    for season, budget in seasons_max_seconds.items():
        per_season[str(season)] = run_season(season, max_seconds=budget)
    report = {
        "corpus_id": "savant_full_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "baseballsavant statcast_search CSV (keyless, same endpoint as "
                   "acquire_statcast_sample/acquire_statcast_fuller)",
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
    ap = argparse.ArgumentParser(description="Resumable keyless Savant backfill (new cols/seasons).")
    ap.add_argument("--season", type=int, default=None, help="single season; omit to run --priority")
    ap.add_argument("--max-seconds", type=float, default=600.0)
    ap.add_argument("--priority", default="2024,2022,2023,2025",
                    help="comma-separated season order when --season is omitted")
    a = ap.parse_args(argv)
    if a.season:
        res = run_season(a.season, max_seconds=a.max_seconds)
    else:
        seasons = [int(s) for s in a.priority.split(",") if s.strip()]
        res = run_priority({s: a.max_seconds for s in seasons})
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["run_season", "run_priority", "_day_csv_savant", "_season_days",
           "_coverage", "_KEEP", "_NEW_COLS", "_CACHE", "_RAW_DIR", "_REPO",
           "_DELAY_S", "_MAX_CONSECUTIVE_FAILURES"]
