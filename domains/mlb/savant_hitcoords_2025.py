"""domains.mlb.savant_hitcoords_2025 -- resumable 2025 STARTER for the savant
hitcoords backfill (unblocks the bat-tracking gate whose outcome attribute
contact_quality ends at 2024 -- docs/research/bat_tracking_asof_2026-07-11.md).

Thin wrapper over the EXISTING puller family (domains/mlb/savant_backfill_
hitcoords.py -- same endpoint, same _KEEP columns, same raw_days_hitcoords/
per-day cache namespace), so savant_hitcoords__2025.parquet lands with the
IDENTICAL schema as savant_hitcoords__{2023,2024}.parquet and profile builders
(domains/mlb/profiles/ingredients_batter.py) consume it unchanged.

What this adds vs calling savant_backfill_hitcoords directly:
- timeout 40s (census-verified 2026-07-09: this endpoint needs 30-40s; the
  parent module's 90s default exceeds the politeness rail's 30-40s band)
- 1 req/s pacing rail (1.0s sleep after each response; the response itself
  takes 10-40s so effective rate is far below 1/s)
- STATE FILE data/cache/statcast/hitcoords_2025_state.json with the last-
  completed date, days cached/total, stop reason -- resume by re-running the
  same CLI; already-cached days are skipped (per-day idempotency).

UTC/ET note: day keys come from the schedule's own game_date values
(data/domains/mlb/probables.parquet, ET calendar dates) and the Savant
game_date_gt/lt params use that same calendar; the day list is the complete
schedule, so both candidate dates around any UTC/ET boundary are in the list.

POLITENESS (binding): 1 day/request, stops after 3 consecutive failures and
records the stop honestly (never hammers, never evades).
WRITES ONLY data/cache/statcast/. NEVER data/registry/, no flag, no $/edge.
CLI: python -m domains.mlb.savant_hitcoords_2025 --max-seconds 1800
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from domains.mlb.acquire_statcast_fuller import _replace_with_retry
from domains.mlb.savant_backfill import _season_days
from domains.mlb.savant_backfill_hitcoords import _CACHE, _day_csv_hitcoords, run_days

log = logging.getLogger(__name__)

SEASON = 2025
_TIMEOUT_S = 40   # census-verified band (30-40s); parent's 90s default not used
_DELAY_S = 1.0    # politeness rail: max 1 req/s to baseballsavant
_MAX_CONSECUTIVE_FAILURES = 3
STATE_FP = _CACHE / "hitcoords_2025_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_state(state: Dict[str, object], state_fp: Path) -> None:
    state_fp.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_fp.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="ascii")
    # retried rename: a concurrent reader (AV/indexer/monitoring probe) holding
    # the path mid-move raises transient WinError 5 -- proven 2026-07-10 when a
    # probe crashed the first chunk's state write after 124 days landed.
    _replace_with_retry(tmp, state_fp)


def load_state(state_fp: Path = STATE_FP) -> Dict[str, object]:
    if state_fp.exists():
        return json.loads(state_fp.read_text(encoding="ascii"))
    return {}


def pull_chunk(max_seconds: float, season: int = SEASON,
               cache_dir: Optional[Path] = None,
               state_fp: Optional[Path] = None,
               fetch_fn: Optional[Callable] = None) -> Dict[str, object]:
    """One bounded, resumable chunk: fetch uncached schedule days (1 req/s,
    40s timeout, 3-consecutive-failure stop), update the state file after each
    landed day, then materialize EVERY cached day into
    savant_hitcoords__<season>.parquet via the parent module's run_days
    (max_seconds=0.0 -> its fetch step no-ops, materialize is unbounded)."""
    days: List[str] = _season_days(season)
    cdir = Path(cache_dir) if cache_dir else _CACHE
    sfp = Path(state_fp) if state_fp else STATE_FP
    raw_dir = cdir / "raw_days_hitcoords"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetch_fn or (lambda d: _day_csv_hitcoords(d, timeout=_TIMEOUT_S))

    fetched: List[str] = []
    failures = 0
    stopped = "complete"
    last_completed: Optional[str] = None
    t0 = time.monotonic()
    for day in days:
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            last_completed = day
            continue
        if (time.monotonic() - t0) > max_seconds:
            stopped = "max_seconds"
            break
        df = fetch(day)
        if df is None:
            failures += 1
            log.warning("day %s failed (consecutive=%d)", day, failures)
            if failures >= _MAX_CONSECUTIVE_FAILURES:
                stopped = "consecutive_failures"  # recorded honestly, no retry storm
                break
            time.sleep(_DELAY_S)
            continue
        failures = 0
        if not df.empty:
            tmp = fp.with_suffix(".tmp.parquet")
            df.to_parquet(tmp, index=False)
            _replace_with_retry(tmp, fp)
            fetched.append(day)
            log.info("fetched %s rows=%d", day, len(df))
        last_completed = day
        try:  # advisory only -- the per-day cache is the real resume state
            _write_state({"season": season, "last_completed_day": last_completed,
                          "days_total": len(days), "stopped_reason": "in_progress",
                          "updated_at": _now_iso()}, sfp)
        except OSError as exc:
            log.warning("state write skipped (%s); day %s already cached", exc, day)
        time.sleep(_DELAY_S)

    mat = run_days(days, season, max_seconds=0.0, cache_dir=cdir)
    cached = sum(1 for d in days if (raw_dir / f"day__{d}.parquet").exists())
    state: Dict[str, object] = {
        "season": season, "last_completed_day": last_completed,
        "days_total": len(days), "days_cached": cached,
        "fetched_this_run": len(fetched), "stopped_reason": stopped,
        "raw_rows": mat.get("raw_rows", 0),
        "parquet": mat.get("parquet"), "date_range": mat.get("date_range"),
        "updated_at": _now_iso(),
        "resume": "python -m domains.mlb.savant_hitcoords_2025 --max-seconds 1800",
    }
    _write_state(state, sfp)
    return state


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Resumable 2025 savant hitcoords starter.")
    ap.add_argument("--max-seconds", type=float, default=1800.0)
    a = ap.parse_args(argv)
    print(json.dumps(pull_chunk(a.max_seconds), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["pull_chunk", "load_state", "SEASON", "STATE_FP",
           "_TIMEOUT_S", "_DELAY_S", "_MAX_CONSECUTIVE_FAILURES"]
