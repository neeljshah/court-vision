"""NYK/SAS Team System — Stage 1: ingest every game's play-by-play + boxscore.

Source = cdn.nba.com liveData static JSON (stats.nba.com is blocked from here).
  PBP : https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{gid}.json
  Box : https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json
Both verified working for early-season, mid-season, and playoff/Finals games.

Refreshes the NYK/SAS game inventory from the league schedule, then fetches PBP+box
for every final (or live) game and caches the raw JSON. Incremental: cached final
games are skipped unless --refresh. Run before pbp_parse.py.

  python scripts/team_system/fetch_team_pbp.py [--refresh]
"""
from __future__ import annotations

import json
import os
import sys
import time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
PBP_DIR = os.path.join(TS, "pbp")
BOX_DIR = os.path.join(TS, "box")
GAMES_JSON = os.path.join(TS, "nyk_sas_games.json")
TEAMS = ("NYK", "SAS")
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}
SCHED = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
PBP_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{}.json"
BOX_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
_KIND = {"001": "pre", "002": "reg", "004": "playoff", "005": "playin", "003": "allstar"}


def _get(url, timeout=12, retries=2):
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(0.6 * (i + 1))
    return None


def refresh_inventory() -> list:
    """Re-pull the league schedule and rewrite the NYK/SAS game inventory."""
    sch = _get(SCHED, timeout=20)
    if not sch:
        print("WARN: schedule fetch failed; using cached inventory")
        return json.load(open(GAMES_JSON)) if os.path.exists(GAMES_JSON) else []
    rows = []
    for d in sch["leagueSchedule"]["gameDates"]:
        for g in d["games"]:
            ht, at = g["homeTeam"], g["awayTeam"]
            if ht["teamTricode"] in TEAMS or at["teamTricode"] in TEAMS:
                rows.append({
                    "gid": g["gameId"], "date": g["gameDateEst"][:10],
                    "status": g["gameStatus"], "matchup": f'{at["teamTricode"]}@{ht["teamTricode"]}',
                    "home": ht["teamTricode"], "away": at["teamTricode"],
                    "home_id": ht["teamId"], "away_id": at["teamId"],
                    "label": g.get("gameLabel", ""), "hs": ht.get("score"), "as": at.get("score"),
                    "kind": _KIND.get(g["gameId"][:3], g["gameId"][:3]),
                })
    rows = [r for r in rows if r["kind"] in ("reg", "playoff", "playin")]
    rows.sort(key=lambda r: (r["date"], r["gid"]))
    os.makedirs(TS, exist_ok=True)
    json.dump(rows, open(GAMES_JSON, "w"), indent=0)
    return rows


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(PBP_DIR, exist_ok=True)
    os.makedirs(BOX_DIR, exist_ok=True)
    games = refresh_inventory()
    final = [g for g in games if g["status"] == 3]
    live = [g for g in games if g["status"] == 2]
    todo = [g for g in (final + live)]
    print(f"inventory: {len(games)} NYK/SAS games | {len(final)} final | {len(live)} live")

    fetched = skipped = failed = 0
    for g in todo:
        gid = g["gid"]
        pbp_fp = os.path.join(PBP_DIR, f"{gid}.json")
        box_fp = os.path.join(BOX_DIR, f"{gid}.json")
        cached = os.path.exists(pbp_fp) and os.path.exists(box_fp)
        # skip cached finals unless --refresh; always (re)fetch live games
        if cached and g["status"] == 3 and not refresh:
            skipped += 1
            continue
        pbp = _get(PBP_URL.format(gid))
        box = _get(BOX_URL.format(gid))
        if not pbp or not box:
            failed += 1
            print(f"  FAIL {gid} {g['matchup']} (pbp={'ok' if pbp else 'X'} box={'ok' if box else 'X'})")
            continue
        json.dump(pbp, open(pbp_fp, "w"))
        json.dump(box, open(box_fp, "w"))
        fetched += 1
        time.sleep(0.12)
        if fetched % 25 == 0:
            print(f"  ... {fetched} fetched")
    print(f"DONE: fetched={fetched} skipped(cached final)={skipped} failed={failed}")
    # report team ids seen for NYK/SAS (verify SAS=1610612759, NYK=1610612752)
    ids = {}
    for g in games:
        ids[g["home"]] = g["home_id"]
        ids[g["away"]] = g["away_id"]
    print(f"team ids: NYK={ids.get('NYK')} SAS={ids.get('SAS')}")


if __name__ == "__main__":
    main()
