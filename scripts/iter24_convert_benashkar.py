"""iter-24: convert benashkar 2025-26 in-season player prop CSVs to canonical CSV.

Source: data/external/historical_lines/benashkar_nba_gambling/data__output__player_props_*.csv
Schema in source: player_name, team, opponent, game_id, game_date, game_time,
                  prop_type (points/rebounds/assists/threes), line, over_odds,
                  under_odds, is_alt_line, sportsbook, scraped_at

Strategy:
1. Keep only is_alt_line == False (the main consensus line per book per player-game).
2. For each (game_date, player, prop_type) take the LATEST scraped_at sample
   (closest to closing line). Prefer fanduel > draftkings > betmgm tiebreak.
3. Look up actuals from local gamelog cache data/nba/gamelog_{player_id}_{season}.json.
4. Resolve player_name to player_id via nba_api static list (cached).
5. Resolve opp team to canonical TLA and infer venue from team/opponent (if team
   present) else mark venue UNK and drop downstream if needed.

Output: data/external/historical_lines/benashkar_2026_canonical.csv
"""
import glob
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime

import pandas as pd

SRC_DIR = "data/external/historical_lines/benashkar_nba_gambling"
GAMELOG_DIR = "data/nba"
OUT_PATH = "data/external/historical_lines/benashkar_2026_canonical.csv"
SEASON = "2025-26"

PROP_STAT_MAP = {
    "points": "pts",
    "rebounds": "reb",
    "assists": "ast",
    "threes": "fg3m",
}

# Boxscore key per stat (gamelog uses uppercase abbreviations)
ACTUAL_KEY = {
    "pts": "PTS",
    "reb": "REB",
    "ast": "AST",
    "fg3m": "FG3M",
    "stl": "STL",
    "blk": "BLK",
    "tov": "TOV",
}

BOOK_PREF = {"fanduel": 0, "draftkings": 1, "betmgm": 2}


def norm_name(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def build_player_id_map():
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception as e:
        print(f"  nba_api unavailable: {e}")
        return {}
    out = {}
    for p in players.get_players():
        out[norm_name(p["full_name"])] = p["id"]
    return out


def load_gamelog(player_id, season):
    fp = os.path.join(GAMELOG_DIR, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(fp):
        return None
    with open(fp) as f:
        return json.load(f)


def parse_gamelog_date(d):
    # gamelog GAME_DATE is "MMM DD, YYYY" -> 'YYYY-MM-DD'
    try:
        return datetime.strptime(d, "%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def main():
    # 1. Load all prop CSVs
    files = sorted(glob.glob(os.path.join(SRC_DIR, "data__output__player_props_*.csv")))
    print(f"benashkar prop files: {len(files)}")
    dfs = []
    for fp in files:
        try:
            d = pd.read_csv(fp)
            dfs.append(d)
        except Exception as e:
            print(f"  skip {os.path.basename(fp)}: {e}")
    raw = pd.concat(dfs, ignore_index=True)
    print(f"raw rows: {len(raw)}")

    # 2. Filter
    raw = raw[raw["is_alt_line"] == False].copy()  # noqa: E712
    raw = raw[raw["prop_type"].isin(PROP_STAT_MAP.keys())].copy()
    raw["stat"] = raw["prop_type"].map(PROP_STAT_MAP)
    raw["scraped_at_dt"] = pd.to_datetime(raw["scraped_at"], errors="coerce")
    raw["book_rank"] = raw["sportsbook"].map(BOOK_PREF).fillna(99).astype(int)
    print(f"after non-alt + 4 props: {len(raw)}")

    # 3. Pick closing line per (date, player, stat): latest scraped, tiebreak by book pref
    raw = raw.sort_values(["scraped_at_dt", "book_rank"], ascending=[False, True])
    closing = raw.drop_duplicates(subset=["game_date", "player_name", "stat"], keep="first")
    print(f"closing-line rows: {len(closing)}")
    print(f"  date range: {closing['game_date'].min()} -> {closing['game_date'].max()}")
    print(f"  stats: {closing['stat'].value_counts().to_dict()}")

    # 4. Resolve player_id once
    id_map = build_player_id_map()
    print(f"nba_api player map size: {len(id_map)}")

    # Group by player to load each gamelog once
    rows_out = []
    n_drop_id, n_drop_log, n_drop_game = 0, 0, 0
    closing["norm_name"] = closing["player_name"].map(norm_name)

    gamelog_cache = {}

    for player_name, grp in closing.groupby("norm_name"):
        pid = id_map.get(player_name)
        if not pid:
            n_drop_id += len(grp)
            continue
        if pid not in gamelog_cache:
            gamelog_cache[pid] = load_gamelog(pid, SEASON)
        gl = gamelog_cache[pid]
        if gl is None:
            n_drop_log += len(grp)
            continue
        # Build per-date lookup
        by_date = {}
        for game in gl:
            d = parse_gamelog_date(game.get("GAME_DATE", ""))
            if d:
                by_date[d] = game
        for _, r in grp.iterrows():
            date = str(r["game_date"])
            game = by_date.get(date)
            if not game:
                # Try date-1 (props sometimes posted EST for previous-night UTC game)
                # and date+1 for the inverse case.
                try:
                    d_obj = datetime.strptime(date, "%Y-%m-%d")
                    for delta in (1, -1):
                        cand = (d_obj.replace(day=d_obj.day) ).strftime("%Y-%m-%d")
                        # Use timedelta properly
                        from datetime import timedelta as _td
                        cand = (d_obj + _td(days=delta)).strftime("%Y-%m-%d")
                        if cand in by_date:
                            game = by_date[cand]
                            date = cand
                            break
                except Exception:
                    pass
            if not game:
                n_drop_game += 1
                continue
            stat = r["stat"]
            actual = game.get(ACTUAL_KEY[stat])
            if actual is None:
                continue
            # Venue: MATCHUP "PHX vs. DEN" = home, "PHX @ DEN" = away
            matchup = game.get("MATCHUP", "")
            venue = "home" if " vs. " in matchup else ("away" if " @ " in matchup else "")
            # Opponent abbrev: last token of matchup
            opp = matchup.split()[-1] if matchup else str(r.get("opponent") or "")
            rows_out.append(
                {
                    "date": date,
                    "player": r["player_name"],
                    "opp": opp,
                    "venue": venue,
                    "stat": stat,
                    "closing_line": float(r["line"]),
                    "over_odds": int(r["over_odds"]) if pd.notna(r["over_odds"]) else -110,
                    "under_odds": int(r["under_odds"]) if pd.notna(r["under_odds"]) else -110,
                    "actual_value": float(actual),
                }
            )

    out = pd.DataFrame(rows_out)
    print(f"final rows: {len(out)}")
    print(f"drop reasons: no_player_id={n_drop_id}, no_gamelog={n_drop_log}, no_game_on_date={n_drop_game}")
    if len(out):
        print(f"date range: {out['date'].min()} -> {out['date'].max()}")
        print(f"stat counts: {out['stat'].value_counts().to_dict()}")
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        out.to_csv(OUT_PATH, index=False)
        print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
