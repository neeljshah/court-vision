"""domains.mlb.starter_table_full_seasons -- extends starter_table__<season>.parquet
coverage from 2022-2023 (acquire_statcast_sample's bounded May-Jul sample windows,
the pitcher-tier prerequisite for the queued bat-tracking/OAA gates) to 2024-2026.

NO new network fetch: builds directly off the ALREADY-CACHED full-season pull
(savant_full__<season>.parquet, written by savant_backfill.py). Verified 2026-07-10
that savant_full's columns are a strict superset of what
acquire_statcast_sample.build_starter_table reads (game_pk, game_date, inning,
inning_topbot, at_bat_number, pitch_number, pitcher, home_team, away_team,
release_speed, release_spin_rate, pitch_type, events -- zero missing for 2023-2026).
So this is a pure transform, same "thin wrapper over an existing puller family"
pattern as savant_hitcoords_2025.py, just lighter since the fetch step is a no-op.

RESUMABLE/idempotent: a season whose starter_table__<season>.parquet already exists
is SKIPPED (use --force to rebuild) -- the per-season output file IS the resume
checkpoint. No state file needed: each season's transform is <20s (measured
2026-07-10: ~9s/400K rows), there is no network I/O to interrupt mid-season.

WRITES ONLY data/cache/statcast/starter_table__<season>.parquet. NEVER
data/registry/, no sentinel, no flag, no $/edge. ASCII-only; <=300 LOC. Per-file
test in domains/mlb/test_starter_table_full_seasons.py.
CLI: python -m domains.mlb.starter_table_full_seasons --seasons 2024,2025,2026
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.mlb.acquire_statcast_sample import _CACHE, build_starter_table

log = logging.getLogger(__name__)


def _source_fp(season: int, cache_dir: Path) -> Path:
    return cache_dir / f"savant_full__{season}.parquet"


def _out_fp(season: int, cache_dir: Path) -> Path:
    return cache_dir / f"starter_table__{season}.parquet"


def build_season(season: int, cache_dir: Optional[Path] = None,
                 force: bool = False) -> Dict[str, object]:
    """Build one season's starter_table from the already-cached savant_full pull.

    Idempotent: SKIPPED_EXISTS (no re-read/re-write) if the output already exists
    and force=False. MISSING_SOURCE (honest, no crash) if savant_full__<season>
    hasn't been pulled yet for that season.
    """
    cdir = Path(cache_dir) if cache_dir else _CACHE
    out_fp = _out_fp(season, cdir)
    if out_fp.exists() and not force:
        st = pd.read_parquet(out_fp)
        return {"season": season, "status": "SKIPPED_EXISTS",
                "starter_starts": int(len(st)),
                "unique_starters": int(st["pitcher"].nunique()) if not st.empty else 0,
                "parquet": str(out_fp)}
    src_fp = _source_fp(season, cdir)
    if not src_fp.exists():
        return {"season": season, "status": "MISSING_SOURCE", "starter_starts": 0,
                "source_expected": str(src_fp)}
    raw = pd.read_parquet(src_fp)
    starters = build_starter_table(raw, season)
    starters.to_parquet(out_fp, index=False)
    return {"season": season, "status": "OK", "raw_rows": int(len(raw)),
            "starter_starts": int(len(starters)),
            "unique_starters": int(starters["pitcher"].nunique()) if not starters.empty else 0,
            "parquet": str(out_fp)}


def build_seasons(seasons: List[int], cache_dir: Optional[Path] = None,
                  force: bool = False) -> Dict[str, object]:
    return {"seasons": {str(s): build_season(s, cache_dir=cache_dir, force=force)
                        for s in seasons}}


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(
        description="Extend starter_table coverage using already-cached savant_full pulls.")
    ap.add_argument("--seasons", default="2024,2025,2026")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    seasons = [int(s) for s in a.seasons.split(",") if s.strip()]
    res = build_seasons(seasons, force=a.force)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_season", "build_seasons", "_source_fp", "_out_fp"]
