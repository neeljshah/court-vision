"""fetch_season_games_2025_26.py — refresh data/nba/season_games_2025-26.json.

Cycles 99a/100c/100d failed because q1_<stat>_l5 features had <20% holdout
coverage. The root cause: ``data/nba/season_games_2025-26.json`` either
didn't exist on disk OR only carried game_id+game_date (no home_team /
away_team), so most downstream consumers treated the season as missing.

This script writes a v8-compatible season_games snapshot covering every
2025-26 regular-season game discoverable via NBA API leaguegamelog. The
columns matter primarily for tooling that joins on (team, game_date) —
the per-quarter daemon only needs (game_id, season, game_date), but
rest-travel / advanced-features pipelines need home_team/away_team too.

PATH A (default): call NBA API leaguegamelog endpoint.
PATH B (fallback): reconstruct from cached gamelog_full_<player>_2025-26.json
files (same reconstruction logic used by build_rest_travel_parquet).

Existing rows are preserved when --merge is set: any rich columns
(off_rtg etc.) already populated by fetch_historical_seasons.py stay.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
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
_SCHEMA_VERSION = 8  # matches fetch_historical_seasons.py default

_GAMELOG_DATE_FORMATS = ("%b %d, %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _parse_date(s: str) -> Optional[str]:
    if not s:
        return None
    for fmt in _GAMELOG_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    return None


# ── PATH A: leaguegamelog ────────────────────────────────────────────────────

def fetch_from_leaguegamelog(season: str = _DEFAULT_SEASON) -> List[Dict[str, Any]]:
    """Call NBA API leaguegamelog and pair home/away rows into single games.

    Returns a list of {game_id, season, game_date, home_team, away_team}
    dicts. Returns [] on any API error so the caller can fall back to
    gamelogs.
    """
    try:
        from nba_api.stats.endpoints import leaguegamelog  # type: ignore
    except Exception as e:
        print(f"  [warn] nba_api import failed: {e}")
        return []
    try:
        time.sleep(0.6)
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
            timeout=45,
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] leaguegamelog({season}) failed: {e}")
        return []
    print(f"  [api] {len(gl)} team-game rows for {season}", flush=True)

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
        })
        if is_home:
            rec["home_team"] = team
        else:
            rec["away_team"] = team

    # Drop games we couldn't pair (one side missing); preserve the rest.
    complete = [g for g in games.values()
                if g["home_team"] and g["away_team"]]
    print(f"  [api] paired {len(complete)}/{len(games)} games", flush=True)
    return complete


# ── PATH B: reconstruct from cached gamelogs ─────────────────────────────────

def reconstruct_from_gamelogs(season: str = _DEFAULT_SEASON) -> List[Dict[str, Any]]:
    """Walk cached per-player gamelog files and recover (gid,date,home,away).

    Each gamelog row has a 'matchup' like 'OKC @ BOS' (away) or
    'OKC vs. BOS' (home). Combining many players' perspectives lets us
    recover almost every team game.
    """
    paths = sorted(glob.glob(os.path.join(
        _NBA_CACHE, f"gamelog_full_*_{season}.json")))
    games: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        for r in rows:
            gid = str(r.get("game_id", "")).zfill(10)
            if not gid or gid == "0000000000":
                continue
            if gid in games:
                continue
            matchup = str(r.get("matchup", ""))
            m = re.match(r"^([A-Z]{3})\s+(@|vs\.?)\s+([A-Z]{3})$", matchup)
            if not m:
                continue
            t1, sep, t2 = m.group(1), m.group(2), m.group(3)
            if sep == "@":
                away_team, home_team = t1, t2
            else:
                home_team, away_team = t1, t2
            gdate = _parse_date(str(r.get("game_date", "")))
            if not gdate:
                continue
            games[gid] = {
                "game_id": gid,
                "season": season,
                "game_date": gdate,
                "home_team": home_team,
                "away_team": away_team,
            }
    print(f"  [recon] reconstructed {len(games)} games from "
          f"{len(paths)} gamelog files", flush=True)
    return list(games.values())


# ── merge with existing file ─────────────────────────────────────────────────

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
            # Fill missing fields only — don't clobber rich data.
            for k, v in r.items():
                if by_gid[gid].get(k) in (None, "", 0) and v not in (None, ""):
                    by_gid[gid][k] = v
        else:
            by_gid[gid] = r
    # Sort by date for readability.
    return sorted(by_gid.values(),
                  key=lambda x: (x.get("game_date", ""), x.get("game_id", "")))


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=_DEFAULT_SEASON)
    ap.add_argument("--no-api", action="store_true",
                    help="Skip PATH A (NBA API) and use only cached gamelogs.")
    ap.add_argument("--no-merge", action="store_true",
                    help="Overwrite existing file (default merges).")
    args = ap.parse_args()

    os.makedirs(_NBA_CACHE, exist_ok=True)
    out_path = os.path.join(_NBA_CACHE, f"season_games_{args.season}.json")

    fresh: List[Dict[str, Any]] = []
    if not args.no_api:
        fresh = fetch_from_leaguegamelog(args.season)
    if not fresh:
        print("  [path] falling back to PATH B (gamelog reconstruction)")
        fresh = reconstruct_from_gamelogs(args.season)

    if not fresh:
        print(f"[error] no games discovered for {args.season} via either path.")
        return 1

    existing = {} if args.no_merge else _load_existing(out_path)
    if existing:
        print(f"  [merge] {len(existing)} existing rows -> upserting")

    merged = merge(existing, fresh)
    payload = {"v": _SCHEMA_VERSION, "rows": merged}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    enriched = sum(1 for r in merged if r.get("home_team") and r.get("away_team"))
    print(f"[done] wrote {len(merged)} games -> {out_path}")
    print(f"        with home_team/away_team: {enriched}/{len(merged)}")
    if merged:
        print(f"        date range: {merged[0]['game_date']} "
              f"-> {merged[-1]['game_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
