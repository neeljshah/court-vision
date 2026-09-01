"""domains.mlb.savant_backfill -- resumable keyless Savant pull that unblocks the 5
prereg-BLOCKED MLB hypotheses in domains/mlb/prereg/mlb_hypotheses.py (missing
on_1b/on_2b/on_3b, launch_angle, and any 2024+ season). SAME endpoint/pacing family
as acquire_statcast_sample/acquire_statcast_fuller (no new source) -- widens _KEEP
further and adds NEW seasons via a SEPARATE cache namespace (raw_days_savant/) so it
never clobbers statcast_fuller__2022/2023 or the SP-fatigue sample.

NEW columns vs statcast_fuller: on_1b/on_2b/on_3b (base-runner MLBAM ids or NaN),
launch_angle, description (per-PITCH result code, distinct from prose 'des'),
bb_type. PRIORITY (run_priority): 2024 full season; 2022/2023 refresh; 2025.
DAY LIST comes from the corpus's own schedule (probables.parquet) -- no off-days
in the list, so a fetch failure is unambiguous.

POLITENESS (binding): 1 day/request, _DELAY_S=3.0s, per-day checkpointed +
idempotent (raw_days_savant/day__<date>.parquet), STOPS after 3 consecutive
failures, reports FAILED_CONSECUTIVE honestly.

--called-pitches mode (FRAMING_DATA_ACQ_2026-09-01): separate <=100MB-budgeted,
date-sliced, resumable pull of taken-pitch rows into raw_days_called_pitches/.
Does NOT produce command_target_dev_x_ft/command_target_height_ft -- not in
Statcast, ever; see the memo for why this mode still ships.

WRITES ONLY data/cache/statcast/. NEVER data/registry/, no sentinel/flag/$-edge.
ASCII-only. Per-file test in test_savant_backfill.py.
CLI: python -m domains.mlb.savant_backfill --season 2024 --max-seconds 900
     python -m domains.mlb.savant_backfill --called-pitches --season 2024
"""
from __future__ import annotations

import argparse
import hashlib
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
                    max_seconds: Optional[float], fetch_fn=None,
                    max_bytes: Optional[float] = None) -> Dict[str, object]:
    """Walks `days` not cached; stops on wall-clock budget, byte budget (cache
    bytes on disk; used by --called-pitches), or _MAX_CONSECUTIVE_FAILURES --
    whichever first. `fetch_fn` defaults to `_day_csv_savant`."""
    fetch = fetch_fn or _day_csv_savant
    fetched: List[str] = []
    consecutive_failures = 0
    stopped_reason = None
    t0 = time.monotonic()
    total_bytes = sum(fp.stat().st_size for fp in raw_dir.glob("day__*.parquet"))
    for day in days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            continue
        if max_bytes is not None and total_bytes >= max_bytes:
            stopped_reason = "byte_budget"
            break
        if max_seconds is not None and (time.monotonic() - t0) > max_seconds:
            stopped_reason = "max_seconds"
            break
        df = fetch(day)
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
        total_bytes += fp.stat().st_size
        fetched.append(day)
        log.info("fetched %s rows=%d", day, len(df))
        time.sleep(delay_s)
    return {"fetched_days": fetched, "stopped_reason": stopped_reason,
            "consecutive_failures_at_stop": consecutive_failures,
            "total_bytes": total_bytes}


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


# --called-pitches mode: does NOT produce command_target_dev_x_ft /
# command_target_height_ft (not in Statcast, ever) -- see the memo.
_TAKEN_DESCRIPTIONS = {"ball", "called_strike", "blocked_ball"}
_CALLED_PITCH_BUDGET_BYTES = 100_000_000  # <=100MB cap


def _day_csv_called_pitches(day: str, timeout: int = 90) -> Optional[pd.DataFrame]:
    """`_day_csv_savant`, row-filtered to taken pitches (None stays None)."""
    df = _day_csv_savant(day, timeout=timeout)
    if df is None or df.empty or "description" not in df.columns:
        return df
    return df[df["description"].isin(_TAKEN_DESCRIPTIONS)].reset_index(drop=True)


def run_called_pitches(days: List[str], max_seconds: Optional[float] = None,
                       max_bytes: float = _CALLED_PITCH_BUDGET_BYTES,
                       cache_dir: Optional[Path] = None) -> Dict[str, object]:
    """Byte-budgeted (<=100MB default), date-sliced, idempotent taken-pitch pull.
    Writes called_pitches__<first>_<last>.parquet + a manifest (rows/bytes/date
    range/sha256) to data/cache/statcast/ (never data/registry/)."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days_called_pitches"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetch = _fetch_new_days(days, raw_dir, _DELAY_S, max_seconds,
                            fetch_fn=_day_csv_called_pitches, max_bytes=max_bytes)
    parts = _materialize(days, raw_dir)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    manifest: Dict[str, object] = {
        "corpus_id": "called_pitches_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(df)), "days_requested": len(days),
        "days_fetched_this_run": len(fetch["fetched_days"]),
        "stopped_reason": fetch["stopped_reason"],
        "byte_budget": max_bytes, "bytes_on_disk_cache": fetch["total_bytes"],
    }
    if not df.empty:
        out_fp = cdir / f"called_pitches__{days[0]}_{days[-1]}.parquet"
        df.to_parquet(out_fp, index=False)
        manifest["parquet"] = str(out_fp)
        manifest["bytes_output_file"] = out_fp.stat().st_size
        manifest["sha256"] = hashlib.sha256(out_fp.read_bytes()).hexdigest()
        manifest["date_range"] = [str(df["game_date"].min()), str(df["game_date"].max())]
    manifest_fp = cdir / "called_pitches_manifest.json"
    with open(manifest_fp, "w", encoding="ascii", errors="replace") as f:
        json.dump(manifest, f, indent=2, default=str)
    manifest["manifest_path"] = str(manifest_fp)
    return manifest


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
    ap.add_argument("--called-pitches", action="store_true",
                    help="byte-budgeted (<=100MB) taken-pitch-only acquisition mode")
    ap.add_argument("--max-bytes", type=float, default=_CALLED_PITCH_BUDGET_BYTES)
    a = ap.parse_args(argv)
    if a.called_pitches:
        season = a.season or int(a.priority.split(",")[0])
        res = run_called_pitches(_season_days(season), max_seconds=a.max_seconds,
                                 max_bytes=a.max_bytes)
    elif a.season:
        res = run_season(a.season, max_seconds=a.max_seconds)
    else:
        seasons = [int(s) for s in a.priority.split(",") if s.strip()]
        res = run_priority({s: a.max_seconds for s in seasons})
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["run_season", "run_priority", "run_called_pitches", "_day_csv_savant",
           "_day_csv_called_pitches", "_season_days", "_coverage", "_KEEP",
           "_NEW_COLS", "_TAKEN_DESCRIPTIONS", "_CALLED_PITCH_BUDGET_BYTES",
           "_CACHE", "_RAW_DIR", "_REPO", "_DELAY_S", "_MAX_CONSECUTIVE_FAILURES"]
