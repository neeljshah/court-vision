"""convert_nickflower_to_canonical.py - iter-12 OOS frame builder.

Reads:
  data/external/historical_lines/nickflower_2025_26/reports_*.json (line snapshots)
  data/external/historical_lines/nickflower_2025_26/reports_graded_all.csv (actuals)

Joins on (date, player, market, side, line) -> emits canonical schema matching
playoffs_2024_canonical.csv:
  date,player,opp,venue,stat,closing_line,over_odds,under_odds,actual_value

Caveats:
  - nickflower markets pts/ast/reb/threes ONLY. NO STL/BLK.
  - 'threes' maps to canonical 'fg3m'.
  - Over/Under: nickflower picks one side. We emit canonical row with closing_line
    set to the picked line; over_odds/under_odds default to -110 (nickflower
    odds are sportsbook ML for the side, not both sides).
  - NO_GAME rows are skipped (player didn't play that date).
"""
from __future__ import annotations
import csv, json, os, glob, sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "nickflower_2025_26")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "season_2025_26_canonical.csv")

MARKET_TO_STAT = {
    "points": "pts",
    "assists": "ast",
    "rebounds": "reb",
    "threes": "fg3m",
    "steals": "stl",
    "blocks": "blk",
    "turnovers": "tov",
}

TEAM_ABBR = {
    'Atlanta Hawks':'ATL','Boston Celtics':'BOS','Brooklyn Nets':'BKN','Charlotte Hornets':'CHA',
    'Chicago Bulls':'CHI','Cleveland Cavaliers':'CLE','Dallas Mavericks':'DAL','Denver Nuggets':'DEN',
    'Detroit Pistons':'DET','Golden State Warriors':'GSW','Houston Rockets':'HOU','Indiana Pacers':'IND',
    'LA Clippers':'LAC','Los Angeles Clippers':'LAC','Los Angeles Lakers':'LAL','Memphis Grizzlies':'MEM',
    'Miami Heat':'MIA','Milwaukee Bucks':'MIL','Minnesota Timberwolves':'MIN','New Orleans Pelicans':'NOP',
    'New York Knicks':'NYK','Oklahoma City Thunder':'OKC','Orlando Magic':'ORL','Philadelphia 76ers':'PHI',
    'Phoenix Suns':'PHX','Portland Trail Blazers':'POR','Sacramento Kings':'SAC','San Antonio Spurs':'SAS',
    'Toronto Raptors':'TOR','Utah Jazz':'UTA','Washington Wizards':'WAS',
}


def _parse_event(event_name: str, opp_team: str):
    """Return (player_team, opp_team, venue) given 'Away @ Home' and opp abbr.

    Player's team = the side that is NOT opp_team. venue=home iff player's team
    is the home (right-of @) abbreviation.
    """
    if " @ " not in event_name:
        return None, None, None
    away_full, home_full = event_name.split(" @ ")
    away = TEAM_ABBR.get(away_full.strip())
    home = TEAM_ABBR.get(home_full.strip())
    if not away or not home:
        return None, None, None
    if opp_team == home:
        return away, home, "away"
    if opp_team == away:
        return home, away, "home"
    return None, None, None


def main():
    files = sorted(glob.glob(os.path.join(SRC_DIR, "reports_*.json")))
    print(f"  Found {len(files)} JSON line-snapshot files")

    # Build a (date, player, market, side, line) -> (event_name, opp_team) index.
    snap_idx = {}
    for fpath in files:
        bn = os.path.basename(fpath)
        # reports_YYYY-MM-DD_top_props.json
        try:
            date_str = bn.split("_")[1]
            datetime.fromisoformat(date_str)
        except Exception:
            continue
        data = json.load(open(fpath, encoding="utf-8"))
        for e in data:
            k = (date_str, e["player"], e["market"], e["side"], float(e["line"]))
            snap_idx[k] = {
                "event_name": e["event_name"], "opp_team": e["opp_team"],
                "odds": int(e["odds"]),
            }
    print(f"  Indexed {len(snap_idx)} JSON entries")

    graded_path = os.path.join(SRC_DIR, "reports_graded_all.csv")
    out_rows = []
    drops = {"no_game": 0, "no_event_match": 0, "no_stat_map": 0,
             "bad_venue": 0, "bad_actual": 0}
    stat_count = {}
    with open(graded_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            grade = r["grade"]
            if grade == "NO_GAME":
                drops["no_game"] += 1
                continue
            stat = MARKET_TO_STAT.get(r["market"])
            if stat is None:
                drops["no_stat_map"] += 1
                continue
            try:
                actual = float(r["actual"])
            except (TypeError, ValueError):
                drops["bad_actual"] += 1
                continue
            key = (r["date"], r["player"], r["market"], r["side"], float(r["line"]))
            snap = snap_idx.get(key)
            if snap is None:
                drops["no_event_match"] += 1
                continue
            player_team, opp_team, venue = _parse_event(snap["event_name"], snap["opp_team"])
            if venue is None:
                drops["bad_venue"] += 1
                continue
            # Best-effort odds: nickflower picked a side. Apply to that side; default
            # the other to -110.
            odds = snap["odds"]
            if r["side"] == "Over":
                over_odds = odds; under_odds = -110
            else:
                over_odds = -110; under_odds = odds
            out_rows.append({
                "date": r["date"], "player": r["player"],
                "opp": opp_team, "venue": venue, "stat": stat,
                "closing_line": float(r["line"]),
                "over_odds": over_odds, "under_odds": under_odds,
                "actual_value": actual,
                # extra fields preserved for downstream filtering
                "side": r["side"],
                "est_prob": r["est_prob"],
            })
            stat_count[stat] = stat_count.get(stat, 0) + 1

    fieldnames = ["date","player","opp","venue","stat","closing_line",
                  "over_odds","under_odds","actual_value","side","est_prob"]
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Wrote {len(out_rows)} rows -> {OUT_PATH}")
    print(f"  Drops: {drops}")
    print(f"  Per-stat counts: {stat_count}")
    print(f"  Date range: {min(r['date'] for r in out_rows)} .. {max(r['date'] for r in out_rows)}")


if __name__ == "__main__":
    main()
