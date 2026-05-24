"""fetch_advanced_boxscores.py — per-game advanced boxscore fetch (loop 5 track A3).

Pulls boxscoreadvancedv2 for every regular-season game in the requested seasons.
Writes data/nba/boxscore_adv_<game_id>.json (player rows: USG_PCT, TS_PCT,
OFF_RATING, DEF_RATING, NET_RATING, AST_PCT, DREB_PCT, OREB_PCT, REB_PCT,
TM_TOV_PCT, EFG_PCT, USG, PIE).

Skips games whose JSON already exists. ~5000 calls × 0.6s sleep = ~50 min for
full 2-season pull. Run in background.
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
_DEFAULT_SEASONS = ["2023-24", "2024-25", "2025-26"]


def fetch_game(game_id: str) -> bool:
    # boxscoreadvancedv2 returns empty {} from stats.nba.com (verified
    # 2026-05-23: status 200 with no resultSet key). v3 endpoint works and
    # carries the same per-player advanced columns.
    from nba_api.stats.endpoints import boxscoreadvancedv3
    out_path = os.path.join(_CACHE_DIR, f"boxscore_adv_{game_id}.json")
    if os.path.exists(out_path):
        return False
    try:
        bs = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id, timeout=30)
        frames = bs.get_data_frames()
    except Exception as e:
        print(f"  [warn] adv boxscore {game_id}: {e}")
        return False
    payload = {
        "game_id": game_id,
        "players": [
            {k.lower(): v for k, v in row.items()}
            for row in frames[0].to_dict("records")
        ],
        "teams": [
            {k.lower(): v for k, v in row.items()}
            for row in frames[1].to_dict("records")
        ] if len(frames) > 1 else [],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f)
    return True


def collect_game_ids(seasons) -> list:
    ids: list = []
    for season in seasons:
        path = os.path.join(_CACHE_DIR, f"season_games_{season}.json")
        if not os.path.exists(path):
            print(f"  [skip] no season_games file for {season}")
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        # season_games files are {v: int, rows: [{game_id, ...}, ...]}
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = g.get("game_id") or g.get("GAME_ID")
            if gid:
                ids.append(str(gid).zfill(10))
    return sorted(set(ids))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    ap.add_argument("--sleep", type=float, default=0.55)
    args = ap.parse_args()

    ids = collect_game_ids(args.seasons)
    print(f"[adv boxscores] {len(ids)} unique game_ids across {args.seasons}")
    written = skipped = errors = 0
    for i, gid in enumerate(ids):
        out_path = os.path.join(_CACHE_DIR, f"boxscore_adv_{gid}.json")
        if os.path.exists(out_path):
            skipped += 1
            continue
        time.sleep(args.sleep)
        ok = fetch_game(gid)
        if ok:
            written += 1
        else:
            errors += 1
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(ids)}] written={written} skipped={skipped} errors={errors}", flush=True)
    print(f"[done] written={written} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    main()
