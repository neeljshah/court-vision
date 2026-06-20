"""domains.mlb.acquire_statcast_overlap -- BOUNDED keyless Statcast acquisition on the
ESPN in-game base's OWN game-dates, so the richer per-pitch Statcast fields can JOIN
onto the proven in-game win-prob base (closes the prior TIER3_BLOCKED = ZERO calendar
overlap + the slimmer sample omitting score cols).

The ESPN base (data/cache/ingame/mlb_pitch_states__<season>.parquet) carries the
win-prob state (state_diff, frac_elapsed) + the win/loss OUTCOME label, and only ~16
opening-window dates per season. This module acquires Statcast for EXACTLY those dates,
1 day/request, polite delay, per-day cached + idempotent (re-fetching any cached day that
predates the wider score-bearing _KEEP), and writes a season overlap parquet that
INCLUDES home_score/away_score/bat_score/post_*_score + release_spin_rate +
estimated_woba_using_speedangle + release_speed + launch_speed.

If the ESPN base is not on disk -> TIER3_BLOCKED honestly (never fabricated). It NEVER
0-fills a join; the join itself is performed downstream in the gate probe.

WRITES ONLY data/cache/statcast/ (the data store). NEVER data/registry/, no sentinel,
no flag, no $/edge. ASCII-only; <=300 LOC. Per-file test in tests/.
CLI: python -m domains.mlb.acquire_statcast_overlap --season 2023 [--max-dates 16]
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd

from domains.mlb.acquire_statcast_sample import _CACHE, _DELAY_S, _KEEP, _REPO, _day_csv

log = logging.getLogger(__name__)
_SCORE_COLS = ("home_score", "away_score", "bat_score", "post_home_score",
               "post_away_score")


def espn_base_dates(season: int) -> List[str]:
    """The ESPN in-game pitch-states base's own game-dates for `season` (the JOIN target).
    Returns [] honestly if the base parquet is not on disk -- never fabricated."""
    base = _REPO / "data" / "cache" / "ingame" / f"mlb_pitch_states__{season}.parquet"
    if not base.exists():
        return []
    e = pd.read_parquet(base, columns=["date"])
    return sorted(pd.to_datetime(e["date"]).dt.strftime("%Y-%m-%d").unique().tolist())


def acquire_dates(dates: List[str], season: int, delay_s: float = _DELAY_S,
                  cache_dir: Optional[Path] = None) -> pd.DataFrame:
    """BOUNDED-acquire an EXPLICIT list of game-dates (1 day/request, per-day cache,
    idempotent). A cached per-day parquet from a prior SLIMMER pull (no score cols) is
    RE-FETCHED here so the wider score-bearing _KEEP lands; days already wide are reused.
    Never pulls a whole season."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    raw_dir = cdir / "raw_days"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parts: List[pd.DataFrame] = []
    for day in sorted(set(dates)):
        fp = raw_dir / f"day__{day}.parquet"
        if fp.exists():
            cached = pd.read_parquet(fp)
            if "home_score" in cached.columns:  # already score-bearing -> reuse
                parts.append(cached)
                continue
        df = _day_csv(day)  # (re)fetch with the wider _KEEP
        if df is None or df.empty:
            time.sleep(delay_s)
            continue
        df.to_parquet(fp, index=False)
        parts.append(df)
        log.info("fetched %s rows=%d", day, len(df))
        time.sleep(delay_s)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out = out[pd.to_datetime(out["game_date"]).dt.year == season].reset_index(drop=True)
    return out


def run_overlap(season: int, max_dates: int = 0, cache_dir: Optional[Path] = None) -> dict:
    """OVERLAP mode: acquire Statcast for the ESPN base's OWN dates (score cols included)
    so the richer per-pitch fields can JOIN onto the in-game win-prob base. Writes the
    season's overlap raw parquet. `max_dates` (0 = all base dates, ~16 opening-window
    dates) keeps the pull bounded + polite."""
    cdir = Path(cache_dir) if cache_dir else _CACHE
    cdir.mkdir(parents=True, exist_ok=True)
    dates = espn_base_dates(season)
    if not dates:
        return {"season": season, "status": "TIER3_BLOCKED",
                "reason": "NO_ESPN_BASE_ON_DISK", "overlap_dates": 0}
    if max_dates and max_dates > 0:
        dates = dates[:max_dates]
    raw = acquire_dates(dates, season, cache_dir=cdir)
    if raw.empty:
        return {"season": season, "status": "INSUFFICIENT_DATA", "raw_rows": 0,
                "overlap_dates": len(dates)}
    raw_fp = cdir / f"statcast__{season}_overlap.parquet"
    raw.to_parquet(raw_fp, index=False)
    have_score = [c for c in _SCORE_COLS if c in raw.columns]
    return {"season": season, "status": "OK", "raw_rows": int(len(raw)),
            "overlap_dates": len(dates), "raw_parquet": str(raw_fp),
            "statcast_games": int(raw["game_pk"].nunique()),
            "score_cols": have_score}


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Bounded keyless Statcast ESPN-overlap pull.")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--max-dates", type=int, default=0)
    a = ap.parse_args(argv)
    print(run_overlap(a.season, max_dates=a.max_dates))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["espn_base_dates", "acquire_dates", "run_overlap", "_SCORE_COLS"]
