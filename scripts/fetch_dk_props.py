"""fetch_dk_props.py — daily DraftKings (+ FanDuel) player props to canonical CSV.

Wraps src/data/props_scraper.get_current_props() and writes the results in
the schema compare_to_lines.py and backtest_vs_closing_lines.py expect:

    player,opp,venue,stat,line,over_odds,under_odds

Joins with tonight's NBA schedule (via scoreboardv2) to fill opp + venue
per player. Output path defaults to `data/lines/<date>.csv` so the daily
predict_slate ledger and the sportsbook lines accumulate in parallel —
once 30+ days of both exist, `backtest_vs_closing_lines.py` becomes the
honest closing-line backtest the cycle-52 synthetic version stands in for.

Run:
    python scripts/fetch_dk_props.py                                # DK only
    python scripts/fetch_dk_props.py --book draftkings --book fanduel
    python scripts/fetch_dk_props.py --out /tmp/tonight.csv
    python scripts/fetch_dk_props.py --no-schedule    # skip opp/venue join

Three-tier fetch (defined by src/data/props_scraper):
    1. Odds API (ODDS_API_KEY env var, free tier 500 req/mo) — most reliable
    2. DraftKings / FanDuel direct scrape — often blocked
    3. Manual seed file: data/props/props_{today}.json
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date as _date
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports — scoreboardv2 is used to
# join opp+venue per player.
import src.data.nba_api_headers_patch  # noqa: F401, E402

from src.data.props_scraper import get_current_props  # noqa: E402


# DK prop_type → compare_to_lines canonical stat. TOV is not exposed in DK's
# main NBA endpoint, so it's omitted (NaN); the model still predicts it but
# it can't be backtested vs DK closing lines.
_PROP_MAP = {
    "points":   "pts",
    "rebounds": "reb",
    "assists":  "ast",
    "threes":   "fg3m",
    "steals":   "stl",
    "blocks":   "blk",
}


def _today_iso() -> str:
    return _date.today().isoformat()


def _fetch_schedule(date_str: str) -> Dict[int, Dict[str, str]]:
    """Return {player_team_id: {opp_abbrev, venue}} for every team playing on date_str.

    Uses scriptraped predict_slate.fetch_games (which wraps scoreboardv2 via
    NBAStatsHTTP since the wrapper has a known bug). Each team plays once per
    night so the team_id → opp+venue map is unambiguous.
    """
    try:
        from scripts.predict_slate import fetch_games  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] schedule join unavailable: {e}")
        return {}
    games = fetch_games(date_str)
    out: Dict[int, Dict[str, str]] = {}
    for g in games:
        h_abbrev = g.get("home_abbrev") or f"T{g.get('home_id')}"
        a_abbrev = g.get("away_abbrev") or f"T{g.get('away_id')}"
        out[int(g["home_id"])] = {"opp": a_abbrev, "venue": "home"}
        out[int(g["away_id"])] = {"opp": h_abbrev, "venue": "away"}
    return out


def _resolve_player_team(player_name: str) -> int:
    """nba_api static index → team_id for a player. 0 if not found / inactive."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
        from nba_api.stats.endpoints import commonplayerinfo  # noqa: PLC0415
        import time  # noqa: PLC0415
    except Exception:
        return 0
    match = players.find_players_by_full_name(player_name)
    if not match:
        return 0
    pid = match[0]["id"]
    try:
        time.sleep(0.6)
        info = commonplayerinfo.CommonPlayerInfo(player_id=pid).get_data_frames()[0]
        return int(info.iloc[0]["TEAM_ID"])
    except Exception:
        return 0


def collect_props(books: List[str]) -> List[Dict]:
    """Pull props from each book; merge by (player, prop_type, line), de-dup."""
    seen: Dict[tuple, Dict] = {}
    for book in books:
        try:
            recs = get_current_props(book)
        except Exception as e:
            print(f"  [warn] {book} fetch failed: {e}")
            recs = []
        for r in recs:
            pt = r.get("prop_type", "")
            stat = _PROP_MAP.get(pt)
            if not stat:
                continue
            key = (str(r.get("player_name", "")).lower().strip(),
                   stat, float(r.get("line", 0.0)))
            if key in seen:
                continue       # first book wins; future cycle could merge odds
            seen[key] = {
                "player": r.get("player_name", ""),
                "stat":   stat,
                "line":   float(r.get("line", 0.0)),
                "over_odds":  int(r.get("over_odds", -110)),
                "under_odds": int(r.get("under_odds", -110)),
                "book":   r.get("book", book),
            }
    return list(seen.values())


def write_canonical(props: List[Dict],
                     team_lookup: Dict[int, Dict[str, str]],
                     resolve_team_fn,
                     out_path: str) -> int:
    """Write canonical-schema CSV. Returns rows written.

    resolve_team_fn(player_name) -> int (team_id) is injectable for testing.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    n = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["player", "opp", "venue", "stat", "line",
                    "over_odds", "under_odds"])
        for p in props:
            opp = ""; venue = "home"
            if team_lookup:
                team_id = resolve_team_fn(p["player"])
                vm = team_lookup.get(team_id)
                if vm:
                    opp = vm["opp"]; venue = vm["venue"]
            w.writerow([p["player"], opp, venue, p["stat"],
                        f"{p['line']:g}", p["over_odds"], p["under_odds"]])
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", action="append", default=None,
                    help="Repeatable. Default: draftkings. Examples: --book draftkings --book fanduel")
    ap.add_argument("--out", default=None,
                    help="Output CSV. Default: data/lines/<today>.csv")
    ap.add_argument("--no-schedule", action="store_true",
                    help="Skip the schedule join — opp/venue will be blank.")
    ap.add_argument("--date", default=None,
                    help="Schedule date YYYY-MM-DD (default: today).")
    args = ap.parse_args()

    books = args.book or ["draftkings"]
    date_str = args.date or _today_iso()
    out = args.out or os.path.join(PROJECT_DIR, "data", "lines",
                                     f"{date_str}.csv")

    print(f"[fetch_dk_props] books={books}  date={date_str}", flush=True)
    props = collect_props(books)
    if not props:
        print("[fetch_dk_props] no props returned (Odds API empty, scrape blocked, "
              "no seed file). See PREDICTIONS_QUICKSTART section 5 for ODDS_API_KEY.")
        return 1

    team_lookup: Dict[int, Dict[str, str]] = {}
    if not args.no_schedule:
        team_lookup = _fetch_schedule(date_str)
        if not team_lookup:
            print("  [warn] schedule join returned 0 games — opp/venue will be blank")

    n = write_canonical(props, team_lookup, _resolve_player_team, out)
    by_stat: Dict[str, int] = {}
    for p in props:
        by_stat[p["stat"]] = by_stat.get(p["stat"], 0) + 1
    print(f"  wrote {n} props -> {out}")
    print(f"  by stat: " + "  ".join(f"{s}={c}" for s, c in sorted(by_stat.items())))
    if team_lookup:
        print(f"  schedule join: {len(team_lookup)} teams on {date_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
