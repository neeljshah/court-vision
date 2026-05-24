"""fetch_player_tracking_v3.py — backfill boxscoreplayertrackv3 per-game.

Cycle 84a (loop 5): pulls boxscoreplayertrackv3 for every game_id in the
requested seasons. Writes data/nba/playertrackv3_<game_id>.json (per-player
rows: minutes, speed, distance, touches, passes, contestedFGA, reboundChances,
defendedAtRimFGA, ...). Skips game_ids already cached.

Mirrors fetch_advanced_boxscores.py but for the player-tracking v3 endpoint.

Run:
    python scripts/fetch_player_tracking_v3.py --seasons 2024-25 --sleep 0.65
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_DEFAULT_SEASONS = ["2024-25"]


def fetch_game(game_id: str) -> bool:
    """Fetch one game's player-tracking v3 box; return True on write."""
    out_path = os.path.join(_CACHE_DIR, f"playertrackv3_{game_id}.json")
    if os.path.exists(out_path):
        return False
    from nba_api.stats.endpoints import boxscoreplayertrackv3
    last_err = None
    for attempt in range(3):
        try:
            resp = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                game_id=game_id, timeout=60,
            )
            df = resp.get_data_frames()[0]
            rows = [{k: v for k, v in r.items()} for r in df.to_dict("records")]
            with open(out_path, "w") as f:
                json.dump(rows, f, default=str)
            return True
        except Exception as e:
            last_err = e
            time.sleep(2 + attempt)
    print(f"  [warn] {game_id} failed after retries: {last_err}", flush=True)
    return False


def collect_game_ids(seasons) -> list:
    ids: list = []
    for season in seasons:
        path = os.path.join(_CACHE_DIR, f"season_games_{season}.json")
        if not os.path.exists(path):
            print(f"  [skip] no season_games file for {season}")
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = g.get("game_id") or g.get("GAME_ID")
            if gid:
                ids.append(str(gid).zfill(10))
    return sorted(set(ids))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    ap.add_argument("--sleep", type=float, default=0.65)
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap on number of NEW games to fetch (0 = no cap).")
    args = ap.parse_args()

    ids = collect_game_ids(args.seasons)
    print(f"[playertrackv3] {len(ids)} unique game_ids across {args.seasons}",
          flush=True)
    written = skipped = errors = 0
    new_count = 0
    for i, gid in enumerate(ids):
        out_path = os.path.join(_CACHE_DIR, f"playertrackv3_{gid}.json")
        if os.path.exists(out_path):
            skipped += 1
            continue
        if args.limit and new_count >= args.limit:
            break
        time.sleep(args.sleep)
        ok = fetch_game(gid)
        new_count += 1
        if ok:
            written += 1
        else:
            errors += 1
        if (new_count) % 50 == 0:
            print(f"  [{new_count}] written={written} skipped(pre)={skipped} "
                  f"errors={errors}", flush=True)
    print(f"[done] written={written} skipped={skipped} errors={errors}",
          flush=True)


if __name__ == "__main__":
    main()
