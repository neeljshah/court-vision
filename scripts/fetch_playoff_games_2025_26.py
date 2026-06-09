"""fetch_playoff_games_2025_26.py — backfill 2026 playoff games.

The regular-season fetcher (fetch_season_games_2025_26.py) only pulls
season_type_all_star="Regular Season", so playoff games are missing
from data/nba/season_games_2025-26.json.

This script pulls the Playoffs leaguegamelog feed and merges into the
existing file WITHOUT clobbering any rich regular-season columns.
Existing playoff rows (if re-run) are updated for missing fields only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from src.data import nba_api_headers_patch  # noqa: F401
except Exception:
    pass

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_DEFAULT_SEASON = "2025-26"
_SCHEMA_VERSION = 8

_GAMELOG_DATE_FORMATS = ("%Y-%m-%d", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S")


def _parse_date(s: str) -> Optional[str]:
    if not s:
        return None
    for fmt in _GAMELOG_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    return None


def fetch_playoffs(season: str = _DEFAULT_SEASON,
                   retries: int = 3) -> List[Dict[str, Any]]:
    """Pull Playoffs leaguegamelog and pair home/away rows."""
    try:
        from nba_api.stats.endpoints import leaguegamelog  # type: ignore
    except Exception as e:
        print(f"  [warn] nba_api import failed: {e}")
        return []

    gl = None
    last_err = None
    for attempt in range(retries):
        try:
            sleep_s = 0.6 + attempt * 1.4
            time.sleep(sleep_s)
            gl = leaguegamelog.LeagueGameLog(
                season=season,
                season_type_all_star="Playoffs",
                player_or_team_abbreviation="T",
                timeout=60,
            ).get_data_frames()[0]
            break
        except Exception as e:
            last_err = e
            print(f"  [warn] leaguegamelog Playoffs attempt {attempt+1} failed: {e}")
    if gl is None:
        print(f"  [error] all attempts failed: {last_err}")
        return []

    print(f"  [api] {len(gl)} playoff team-game rows for {season}", flush=True)

    games: Dict[str, Dict[str, Any]] = {}
    for _, row in gl.iterrows():
        gid = str(row.get("GAME_ID", "")).zfill(10)
        if not gid or gid == "0000000000":
            continue
        matchup = str(row.get("MATCHUP", ""))
        team = str(row.get("TEAM_ABBREVIATION", "")).strip()
        gdate = _parse_date(str(row.get("GAME_DATE", "")))
        if not gdate or not team or not matchup:
            continue
        is_home = " vs. " in matchup or " vs " in matchup
        rec = games.setdefault(gid, {
            "game_id": gid,
            "season": season,
            "game_date": gdate,
            "home_team": None,
            "away_team": None,
            "playoff": True,
        })
        if is_home:
            rec["home_team"] = team
        else:
            rec["away_team"] = team

    complete = [g for g in games.values()
                if g["home_team"] and g["away_team"]]
    print(f"  [api] paired {len(complete)}/{len(games)} playoff games",
          flush=True)
    return complete


def _load_existing(path: str) -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    rows = payload["rows"] if isinstance(payload, dict) else payload
    return {str(r.get("game_id", "")).zfill(10): dict(r) for r in rows
            if r.get("game_id")}


def merge(existing: Dict[str, Dict[str, Any]],
          fresh: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Upsert: fresh rows fill gaps in existing; existing rich fields win."""
    by_gid = dict(existing)
    for r in fresh:
        gid = r["game_id"]
        if gid in by_gid:
            for k, v in r.items():
                if by_gid[gid].get(k) in (None, "", 0) and v not in (None, ""):
                    by_gid[gid][k] = v
        else:
            by_gid[gid] = r
    return sorted(by_gid.values(),
                  key=lambda x: (x.get("game_date", ""), x.get("game_id", "")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=_DEFAULT_SEASON)
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write; just print what would change.")
    args = ap.parse_args()

    os.makedirs(_NBA_CACHE, exist_ok=True)
    out_path = os.path.join(_NBA_CACHE, f"season_games_{args.season}.json")

    fresh = fetch_playoffs(args.season)
    if not fresh:
        print(f"[error] no playoff games discovered for {args.season}.")
        return 1

    existing = _load_existing(out_path)
    n_before = len(existing)
    new_gids = [r["game_id"] for r in fresh if r["game_id"] not in existing]
    print(f"  [merge] {n_before} existing rows; {len(new_gids)} new playoff "
          f"game_ids to add", flush=True)

    merged = merge(existing, fresh)

    if args.dry_run:
        print(f"[dry-run] would write {len(merged)} rows "
              f"(net +{len(merged) - n_before})")
        if new_gids:
            sample = [next(r for r in fresh if r["game_id"] == g)
                      for g in new_gids[:5]]
            print(f"  [dry-run] sample new rows: {sample}")
        return 0

    payload = {"v": _SCHEMA_VERSION, "rows": merged}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[done] wrote {len(merged)} games -> {out_path}")
    if merged:
        playoff_rows = [r for r in merged if r.get("game_date", "") >= "2026-04-15"]
        if playoff_rows:
            dates = sorted({r["game_date"] for r in playoff_rows})
            print(f"        playoff date range: {dates[0]} -> {dates[-1]}")
            print(f"        playoff game count: {len(playoff_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
