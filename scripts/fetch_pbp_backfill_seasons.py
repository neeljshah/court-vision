"""
fetch_pbp_backfill_seasons.py
==============================
Backfill per-period PBP cache (data/nba/pbp_{game_id}_p{period}.json)
for historical NBA seasons so build_pbp_possession_features.py can produce
train-side rows.

Reuses fetch_playbyplay() from src/data/nba_enricher.py (same function that
writes the per-period files for live tracking). Applies the headers patch so
NBA API calls succeed.

Usage:
    python scripts/fetch_pbp_backfill_seasons.py --seasons 2023-24
    python scripts/fetch_pbp_backfill_seasons.py --seasons 2023-24 2022-23
    python scripts/fetch_pbp_backfill_seasons.py --seasons 2023-24 --max 100

Behaviour:
  - Skips games that already have ALL regular periods cached (p1–p4).
  - Logs errors to data/nba/pbp_fetch_errors.log (never stops on failure).
  - Idempotent — safe to re-run; won't re-fetch completed games.
  - Progress line every 50 games + elapsed time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Apply NBA API headers patch BEFORE any nba_api import
from src.data.nba_api_headers_patch import apply_patch
apply_patch()

from src.data.nba_enricher import fetch_playbyplay, _NBA_CACHE  # noqa: E402

_ERROR_LOG = os.path.join(_NBA_CACHE, "pbp_fetch_errors.log")
_REGULAR_PERIODS = (1, 2, 3, 4)
# OT periods (5 and beyond) — we attempt up to 4 OT periods; stop if empty
_MAX_OT_PERIODS = 4


def _game_is_cached(game_id: str) -> bool:
    """Return True if all 4 regular-period PBP files exist and are non-empty."""
    for p in _REGULAR_PERIODS:
        path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                return False
        except Exception:
            return False
    return True


def _log_error(game_id: str, period: int, msg: str) -> None:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(_ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts}  game={game_id}  period={period}  error={msg}\n")


def _load_game_ids(season: str) -> list[str]:
    """Load game IDs from data/nba/season_games_{season}.json."""
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        print(f"[backfill] ERROR: season_games file not found: {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    rows = data.get("rows", data) if isinstance(data, dict) else data
    return [str(r["game_id"]) for r in rows if r.get("game_id")]


def fetch_game_pbp(game_id: str) -> tuple[int, int]:
    """
    Fetch all periods for one game.

    Returns (periods_fetched, periods_errored).
    """
    fetched = 0
    errored = 0

    # Regular periods
    for p in _REGULAR_PERIODS:
        path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        # Skip if already cached with a period-end event
        if os.path.exists(path):
            try:
                with open(path) as f:
                    cached = json.load(f)
                if isinstance(cached, list) and any(
                    r.get("event_type") == 13 for r in cached
                ):
                    # Already complete
                    continue
            except Exception:
                pass  # Re-fetch if corrupt

        try:
            rows = fetch_playbyplay(game_id, p)
            # fetch_playbyplay already writes the file
            if rows is not None and len(rows) > 0:
                fetched += 1
            # An empty period (period doesn't exist) — just skip, not an error
        except Exception as e:
            msg = str(e)[:200]
            _log_error(game_id, p, msg)
            errored += 1

    # OT periods — only fetch if this game has more than 4 periods
    # We detect OT by trying period 5; stop at first empty response
    for p in range(5, 5 + _MAX_OT_PERIODS):
        path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    cached = json.load(f)
                if isinstance(cached, list) and any(
                    r.get("event_type") == 13 for r in cached
                ):
                    continue
            except Exception:
                pass

        try:
            rows = fetch_playbyplay(game_id, p)
            if rows is None or len(rows) == 0:
                break  # No OT at this period
            fetched += 1
        except Exception as e:
            msg = str(e)[:200]
            _log_error(game_id, p, msg)
            errored += 1
            break  # Don't continue OT chain on error

    return fetched, errored


def backfill_season(
    season: str,
    max_games: int = 9999,
    t_deadline: float = float("inf"),
) -> dict:
    """
    Backfill PBP for all regular-season games in `season`.

    Args:
        season:     e.g. "2023-24"
        max_games:  cap on games to process (for testing)
        t_deadline: unix timestamp — stop before this time

    Returns dict with counts.
    """
    game_ids = _load_game_ids(season)
    if not game_ids:
        return {"season": season, "total": 0, "fetched": 0, "skipped": 0, "errored": 0}

    print(f"\n[backfill] Season {season}: {len(game_ids)} games in schedule")

    total_fetched = 0
    total_skipped = 0
    total_errored = 0
    processed = 0
    t_start = time.time()

    for gid in game_ids:
        if processed >= max_games:
            print(f"[backfill] Reached --max {max_games} games. Stopping.")
            break
        if time.time() > t_deadline:
            print(f"[backfill] Time budget reached. Stopping at {processed} games.")
            break

        if _game_is_cached(gid):
            total_skipped += 1
            processed += 1
            if processed % 100 == 0:
                elapsed = time.time() - t_start
                print(
                    f"  [{season}] {processed}/{len(game_ids)} processed "
                    f"({total_fetched} fetched, {total_skipped} skipped, "
                    f"{total_errored} errored) — {elapsed:.0f}s elapsed"
                )
            continue

        f, e = fetch_game_pbp(gid)
        total_fetched += (1 if f > 0 else 0)
        total_errored += (1 if e > 0 else 0)
        processed += 1

        if processed % 50 == 0:
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = len(game_ids) - processed
            eta_min = (remaining / rate / 60) if rate > 0 else 0
            print(
                f"  [{season}] {processed}/{len(game_ids)} processed "
                f"({total_fetched} new fetched, {total_skipped} skipped, "
                f"{total_errored} errored) — {elapsed:.0f}s elapsed, "
                f"ETA ~{eta_min:.0f} min"
            )

    elapsed = time.time() - t_start
    print(
        f"\n[backfill] {season} DONE: {total_fetched} new fetched, "
        f"{total_skipped} already cached, {total_errored} errored "
        f"— {elapsed:.0f}s ({elapsed/60:.1f} min)"
    )
    return {
        "season": season,
        "total": len(game_ids),
        "processed": processed,
        "fetched": total_fetched,
        "skipped": total_skipped,
        "errored": total_errored,
        "elapsed_sec": round(elapsed, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill PBP cache for historical seasons")
    ap.add_argument(
        "--seasons", nargs="+", default=["2023-24"],
        help="Seasons to backfill, e.g. 2023-24 2022-23",
    )
    ap.add_argument(
        "--max", type=int, default=9999,
        help="Max games per season (for testing; default: all)",
    )
    ap.add_argument(
        "--budget-minutes", type=float, default=85,
        help="Stop fetching after this many minutes total (default 85)",
    )
    args = ap.parse_args()

    t_deadline = time.time() + args.budget_minutes * 60
    print(f"[backfill] Seasons: {args.seasons} | Budget: {args.budget_minutes} min | Max/season: {args.max}")
    print(f"[backfill] Error log: {_ERROR_LOG}")

    results = []
    for season in args.seasons:
        if time.time() > t_deadline:
            print(f"[backfill] Time budget exhausted before starting {season}")
            break
        result = backfill_season(season, max_games=args.max, t_deadline=t_deadline)
        results.append(result)

    print("\n[backfill] Summary:")
    for r in results:
        print(
            f"  {r['season']}: {r.get('fetched', 0)} new fetched, "
            f"{r.get('skipped', 0)} already cached, "
            f"{r.get('errored', 0)} errored "
            f"({r.get('elapsed_sec', 0):.0f}s)"
        )


if __name__ == "__main__":
    main()
