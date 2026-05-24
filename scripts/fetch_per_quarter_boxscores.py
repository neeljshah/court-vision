"""fetch_per_quarter_boxscores.py — per-quarter boxscore fetch (cycle 91a, loop 5).

Cycle 89d REJECTED per-quarter pace decay because the local cache has only
FULL-GAME player gamelogs. Cycle 91a builds the fetch infra so cycles 91+
can probe Q1-pace-decay (T1-D) and live MIN extrapolation (T2-A) against
REAL per-quarter observations rather than the synthetic uniform-share
fallback used in 89d.

The script pulls ``boxscoretraditionalv3`` once per (game_id, period) for
each game in the season files, caching the raw response JSON under
``data/cache/quarter_box/<game_id>_q<p>.json``. Rate-limited at 25
req/min (same as cycle 90e position fetcher) and resume-safe — files
already on disk are skipped on the next run.

Default scope is the SMOKE subset (first 50 games × 4 periods = 200
calls ≈ 8 min). Pass ``--limit 0`` for the full ~1200-game pull
(~4800 calls ≈ 3+ hours), which should run as a background daemon
in a follow-up.

Usage
-----
    # SMOKE — first 50 games × 4 periods (default).
    python scripts/fetch_per_quarter_boxscores.py

    # Full background daemon — every game in 2024-25 + 2025-26.
    python scripts/fetch_per_quarter_boxscores.py --limit 0

    # Different seasons:
    python scripts/fetch_per_quarter_boxscores.py --seasons 2024-25
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_DEFAULT_SEASONS = ["2024-25", "2025-26"]
_PERIODS = (1, 2, 3, 4)


# ── game discovery ───────────────────────────────────────────────────────────

def collect_game_ids(seasons: List[str]) -> List[str]:
    """Discover game_ids from data/nba/season_games_<season>.json files.

    Returns sorted unique 10-char zero-padded game_id strings.
    """
    ids: List[str] = []
    for season in seasons:
        path = os.path.join(_NBA_DIR, f"season_games_{season}.json")
        if not os.path.exists(path):
            print(f"  [skip] no season_games file for {season}: {path}")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"  [warn] failed to read {path}: {e}")
            continue
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = g.get("game_id") or g.get("GAME_ID")
            if gid:
                ids.append(str(gid).zfill(10))
    return sorted(set(ids))


# ── single fetch ─────────────────────────────────────────────────────────────

# Period-range slicing uses the NBA endpoint's tick-based RangeType=1
# protocol: each regulation quarter is 720 seconds = 7200 ticks. Passing
# (start_period, end_period) alone is INSUFFICIENT — the v3 endpoint
# ignores those parameters and returns full-game totals, verified
# 2026-05-24. v2 with RangeType=1 + StartRange/EndRange in ticks DOES
# correctly slice; we use that here.
_QUARTER_TICKS = 7200  # 12 min * 60s * 10 ticks/s

_QUARTER_RANGE = {
    1: (0, 7200),
    2: (7200, 14400),
    3: (14400, 21600),
    4: (21600, 28800),
}


def fetch_quarter(game_id: str, period: int,
                  cache_dir: str = _CACHE_DIR) -> bool:
    """Fetch the boxscoretraditionalv2 slice for one (game_id, period).

    Uses RangeType=1 + tick-range to actually slice by quarter (the v3
    endpoint silently returns full-game totals when given period args,
    so this MUST use v2). Caches the full payload (player + team frames)
    so downstream aggregation can grow into any column. Returns True on
    a successful new write, False on skip (already cached) or error.
    Errors are logged but never raised — the caller keeps iterating.
    """
    out_path = os.path.join(cache_dir, f"{game_id}_q{period}.json")
    if os.path.exists(out_path):
        return False
    start_tick, end_tick = _QUARTER_RANGE.get(int(period), (0, _QUARTER_TICKS))
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        bs = boxscoretraditionalv2.BoxScoreTraditionalV2(
            game_id=game_id,
            start_period=str(period),
            end_period=str(period),
            start_range=str(start_tick),
            end_range=str(end_tick),
            range_type="1",
            timeout=30,
        )
        frames = bs.get_data_frames()
    except Exception as e:
        print(f"  [warn] {game_id} q{period}: {e}")
        return False

    payload = {
        "game_id": game_id,
        "period": period,
        "players": (
            [{k.lower(): _coerce(v) for k, v in row.items()}
             for row in frames[0].to_dict("records")]
            if len(frames) > 0 else []
        ),
        "teams": (
            [{k.lower(): _coerce(v) for k, v in row.items()}
             for row in frames[1].to_dict("records")]
            if len(frames) > 1 else []
        ),
    }
    os.makedirs(cache_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return True


def _coerce(v):
    """JSON-safe coercion (NaN → None)."""
    if v is None:
        return None
    if isinstance(v, (str, int, bool)):
        return v
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    try:
        f = float(v)
        if f != f:
            return None
        if f.is_integer():
            return int(f)
        return f
    except (TypeError, ValueError):
        return str(v)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    ap.add_argument("--limit", type=int, default=50,
                    help="Max NEW games to fetch this run (0 = unlimited). "
                         "Each game = 4 API calls (one per period).")
    ap.add_argument("--sleep", type=float, default=2.5,
                    help="Seconds between API calls (25/min ≈ 2.4s).")
    args = ap.parse_args()

    os.makedirs(_CACHE_DIR, exist_ok=True)

    ids = collect_game_ids(args.seasons)
    print(f"[quarter-box] {len(ids)} unique game_ids across {args.seasons}")

    # A game counts as "new" if ANY of its 4 quarter caches is missing.
    new_games = [
        gid for gid in ids
        if not all(
            os.path.exists(os.path.join(_CACHE_DIR, f"{gid}_q{p}.json"))
            for p in _PERIODS
        )
    ]
    print(f"[quarter-box] {len(new_games)} games not fully cached")
    if args.limit > 0:
        new_games = new_games[: args.limit]
        print(f"[quarter-box] limiting this run to {len(new_games)} games "
              f"(~{len(new_games) * 4} API calls)")

    written = skipped = errors = 0
    for i, gid in enumerate(new_games):
        for period in _PERIODS:
            out_path = os.path.join(_CACHE_DIR, f"{gid}_q{period}.json")
            if os.path.exists(out_path):
                skipped += 1
                continue
            time.sleep(args.sleep)
            ok = fetch_quarter(gid, period)
            if ok:
                written += 1
            else:
                errors += 1
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(new_games)}] written={written} "
                  f"skipped={skipped} errors={errors}", flush=True)
    print(f"[done] written={written} skipped={skipped} errors={errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
