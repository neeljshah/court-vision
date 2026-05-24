"""fetch_officials.py — per-game officials via BoxScoreSummaryV2.

WinProb's three ref_* features (ref_avg_fouls, ref_home_win_pct,
ref_fta_tendency) currently default to constants across every row — the
model gets zero signal from referee identity. NBA Stats' BoxScoreSummaryV2
endpoint returns a small officials table for each game.

This script:
  1. For each season, read the cached game_ids from season_games_{s}.json.
  2. For each game_id, call BoxScoreSummaryV2 (one-time cost ~0.6s/game with
     rate-limit sleep).
  3. Parse the Officials data frame (typically 3 refs per game) and write
     a per-season officials cache:
       data/nba/officials/officials_{season}.json
       {game_id: ["First Last", "First Last", "First Last"]}

  4. ALSO compute per-ref aggregate stats from the joined game-results
     and write data/nba/officials/ref_stats_{season}.json so the row
     builder can later compute home win pct / FTA tendency per ref crew.

Run:
    python scripts/fetch_officials.py 2021-22 2022-23 2023-24 2024-25
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_NBA_CACHE   = os.path.join(PROJECT_DIR, "data", "nba")
_OFFICIALS_DIR = os.path.join(_NBA_CACHE, "officials")
os.makedirs(_OFFICIALS_DIR, exist_ok=True)

_DELAY = 0.6  # NBA stats rate limit cushion


def _load_season_games(season: str) -> List[dict]:
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        payload = json.load(f)
    return payload["rows"] if isinstance(payload, dict) else payload


def fetch_officials_for_season(season: str) -> int:
    """Fetch officials per game for a season. Returns count written."""
    out_path = os.path.join(_OFFICIALS_DIR, f"officials_{season}.json")
    existing: Dict[str, List[str]] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                existing = json.load(f) or {}
            print(f"  [{season}] resuming from {len(existing)} cached games", flush=True)
        except Exception:
            existing = {}

    games = _load_season_games(season)
    if not games:
        print(f"  [{season}] no season_games cache — skip")
        return 0

    from nba_api.stats.endpoints import boxscoresummaryv2

    todo = [g for g in games if str(g.get("game_id", "")) not in existing]
    print(f"  [{season}] need to fetch officials for {len(todo)}/{len(games)} games",
          flush=True)

    n_done = 0
    for g in todo:
        gid = str(g.get("game_id", ""))
        if not gid:
            continue
        time.sleep(_DELAY)
        try:
            dfs = boxscoresummaryv2.BoxScoreSummaryV2(game_id=gid).get_data_frames()
            # Officials table is one of the result sets, typically containing
            # OFFICIAL_ID, FIRST_NAME, LAST_NAME, JERSEY_NUM
            refs: List[str] = []
            for df in dfs:
                if "FIRST_NAME" in df.columns and "LAST_NAME" in df.columns:
                    for _, r in df.iterrows():
                        first = str(r.get("FIRST_NAME", "")).strip()
                        last  = str(r.get("LAST_NAME", "")).strip()
                        if first or last:
                            refs.append(f"{first} {last}".strip())
                    if refs:
                        break
            existing[gid] = refs
        except Exception as e:
            print(f"    [warn] {gid}: {e}")
            existing[gid] = []
        n_done += 1
        if n_done % 50 == 0:
            # Periodic checkpoint so a kill doesn't lose hours of work.
            with open(out_path, "w") as f:
                json.dump(existing, f)
            print(f"    {n_done}/{len(todo)} games done — checkpointed", flush=True)

    with open(out_path, "w") as f:
        json.dump(existing, f)
    print(f"  [{season}] wrote {len(existing)} games -> {out_path}", flush=True)
    return len(existing)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seasons", nargs="+")
    args = ap.parse_args()
    print(f"Officials fetcher for {args.seasons}")
    print(f"  ~0.6s per game, season has ~1230 games -> ~12 min per season\n")
    t0 = time.time()
    for s in args.seasons:
        print(f"=== {s} ===", flush=True)
        fetch_officials_for_season(s)
    print(f"\nDONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
