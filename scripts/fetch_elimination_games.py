#!/usr/bin/env python
"""
fetch_elimination_games.py

Build a DATA-DRIVEN historical prior for Game-7 / elimination-game dynamics.

Every number is computed from real NBA playoff game data pulled via nba_api
(leaguegamefinder team logs + boxscoretraditionalv2 for star deltas).
No fabricated constants.

Output: data/cache/intel_game7/elimination_game_prior.json

Method
------
1. Pull team-level playoff games for each season in WINDOW via leaguegamefinder
   (season_type='Playoffs'). Each playoff GAME_ID encodes round + game number:
       0042200405 = 004 (playoffs) | 22 (season yy) | 0 | 4 (round) | 0 | 5 (game#)
   round digit = GAME_ID[7], game# = GAME_ID[9].
2. Group games into series by (season, round, the two team abbreviations).
3. Identify:
     - Game 7s: game# == 7
     - Elimination games: any game where at least one team faces a loss-=-out
       (the trailing team is down 3-2, 3-3, 3-1->is anyone facing elimination?).
       Computed by reconstructing the series score game-by-game.
4. Compute, all from real PTS / MATCHUP / WL columns:
     A. Game-7 home win rate (all-window + recent-10y).
     B. Avg total in Game 7s and in elimination games vs that same series'
        average total over its earlier games  -> tests the "lean under" thesis.
     C. Home-team margin distribution in Game 7s.
     D. Star scoring delta: for each G7 series, the top-2 scorers per team,
        G7 points vs their mean points over games 1..6 of the SAME series
        (boxscore pull, apples-to-apples within-series baseline).
"""
import json
import time
import os
from collections import defaultdict
from statistics import mean, median, pstdev

import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder, boxscoretraditionalv2

ROOT = os.path.dirname(os.path.abspath(__file__))
# script lives in scripts/ ; repo root is parent
REPO = os.path.dirname(ROOT) if os.path.basename(ROOT) == "scripts" else ROOT
OUT_DIR = os.path.join(REPO, "data", "cache", "intel_game7")
OUT_PATH = os.path.join(OUT_DIR, "elimination_game_prior.json")

# Window: last 15 playoff seasons available (2010-11 .. 2024-25).
SEASONS = [f"{y}-{str(y+1)[-2:]}" for y in range(2010, 2025)]
RECENT_CUTOFF_SEASON = "2015-16"  # recent-era = 2015-16 onward (last ~10 yrs)

ROUND_NAME = {"1": "R1", "2": "ConfSemis", "3": "ConfFinals", "4": "Finals"}


def fetch_playoff_team_games(season, retries=3):
    for a in range(retries):
        try:
            df = leaguegamefinder.LeagueGameFinder(
                season_nullable=season,
                season_type_nullable="Playoffs",
                league_id_nullable="00",
                player_or_team_abbreviation="T",
                timeout=90,
            ).get_data_frames()[0]
            return df
        except Exception as e:
            print(f"  retry {season} ({a+1}): {e}")
            time.sleep(2 + a * 2)
    return pd.DataFrame()


def decode_game(gid):
    # gid like 0042200405
    rnd = gid[7]
    gnum = int(gid[9])
    return rnd, gnum


def build_series(all_rows):
    """all_rows: list of dicts (one per team-game). Group by series."""
    # key per game_id -> two team rows
    by_game = defaultdict(list)
    for r in all_rows:
        by_game[r["GAME_ID"]].append(r)
    # series key = (season, round, frozenset(teams))
    series = defaultdict(dict)  # key -> {gnum: gameinfo}
    for gid, rows in by_game.items():
        if len(rows) != 2:
            continue
        rnd, gnum = decode_game(gid)
        teams = frozenset(r["TEAM_ABBREVIATION"] for r in rows)
        season = rows[0]["SEASON"]
        skey = (season, rnd, teams)
        home = next((r for r in rows if "vs." in r["MATCHUP"]), None)
        away = next((r for r in rows if "@" in r["MATCHUP"]), None)
        if home is None or away is None:
            continue
        series[skey][gnum] = {
            "game_id": gid,
            "date": home["GAME_DATE"],
            "home": home["TEAM_ABBREVIATION"],
            "away": away["TEAM_ABBREVIATION"],
            "home_pts": int(home["PTS"]),
            "away_pts": int(away["PTS"]),
            "total": int(home["PTS"]) + int(away["PTS"]),
            "home_win": home["WL"] == "W",
            "margin_home": int(home["PTS"]) - int(away["PTS"]),
            "season": season,
            "round": rnd,
        }
    return series


def series_is_recent(season):
    return season >= RECENT_CUTOFF_SEASON


def analyze(series):
    g7_home_wins_all = []
    g7_home_wins_recent = []
    g7_margins = []  # home margin in game 7
    g7_total_vs_seravg = []  # (g7_total, series_prior_avg_total)
    elim_total_vs_seravg = []  # elimination games vs that series prior avg
    g7_records = []  # for star-delta pass (need game_ids per series)

    for skey, games in series.items():
        season, rnd, teams = skey
        gnums = sorted(games)
        # series prior average total = mean total over games before the last game
        # (for G7: games 1-6; for any elim game: games before it)
        # Reconstruct wins to find elimination games.
        # Map team -> wins as series progresses.
        team_list = list(teams)
        wins = {t: 0 for t in team_list}
        for gn in gnums:
            g = games[gn]
            # before this game: is either team facing elimination? (down 3-x, opp at 3)
            prior_totals = [games[x]["total"] for x in gnums if x < gn]
            # elimination = a team is at 3 wins and the other can be eliminated this game
            facing_elim = (max(wins.values()) == 3) if wins else False
            if facing_elim and prior_totals:
                elim_total_vs_seravg.append((g["total"], mean(prior_totals)))
            # tally this game's winner
            winner = g["home"] if g["home_win"] else g["away"]
            wins[winner] = wins.get(winner, 0) + 1

        # Game 7 handling
        if 7 in games:
            g7 = games[7]
            prior = [games[x]["total"] for x in gnums if x < 7]
            g7_home_wins_all.append(1 if g7["home_win"] else 0)
            if series_is_recent(season):
                g7_home_wins_recent.append(1 if g7["home_win"] else 0)
            g7_margins.append(g7["margin_home"])
            if prior:
                g7_total_vs_seravg.append((g7["total"], mean(prior)))
            g7_records.append({
                "season": season,
                "round": ROUND_NAME.get(rnd, rnd),
                "home": g7["home"],
                "away": g7["away"],
                "g7_total": g7["total"],
                "series_prior_avg_total": round(mean(prior), 1) if prior else None,
                "g7_margin_home": g7["margin_home"],
                "home_win": g7["home_win"],
                "game_ids": [games[x]["game_id"] for x in gnums],
                "g7_game_id": g7["game_id"],
            })

    return {
        "g7_home_wins_all": g7_home_wins_all,
        "g7_home_wins_recent": g7_home_wins_recent,
        "g7_margins": g7_margins,
        "g7_total_vs_seravg": g7_total_vs_seravg,
        "elim_total_vs_seravg": elim_total_vs_seravg,
        "g7_records": g7_records,
    }


def star_deltas(g7_records, max_series=None, sleep=0.6):
    """For each G7 series, pull boxscores for all games. Select stars by their
    SERIES-PRIOR scoring (top-2 per team over games 1..6, no peeking at the G7),
    then measure their G7 pts vs that pre-G7 series average.

    NOTE: stars are chosen on the pre-G7 baseline -- NOT on G7 points -- to avoid
    the selection bias where a role player who erupts in the G7 gets picked
    precisely because of that eruption. This keeps the delta an honest estimate
    of how established stars perform in Game 7 relative to their series form.
    A >=15 pt prior-series average floor restricts to genuine scoring options.
    """
    deltas = []  # dict per star
    recs = g7_records if max_series is None else g7_records[:max_series]
    for i, rec in enumerate(recs):
        try:
            # pull boxscore per game in the series
            player_pts = defaultdict(dict)  # (pid,name,team)-> {game_id: pts}
            for gid in rec["game_ids"]:
                bx = boxscoretraditionalv2.BoxScoreTraditionalV2(
                    game_id=gid, timeout=90
                ).get_data_frames()[0]
                time.sleep(sleep)
                for _, row in bx.iterrows():
                    if pd.isna(row["PTS"]):
                        continue
                    key = (int(row["PLAYER_ID"]), row["PLAYER_NAME"], row["TEAM_ABBREVIATION"])
                    player_pts[key][gid] = float(row["PTS"])
            g7_gid = rec["g7_game_id"]
            # per team, rank players by PRE-G7 series average (selection w/o peeking)
            by_team = defaultdict(list)
            for key, gp in player_pts.items():
                prior = [v for g, v in gp.items() if g != g7_gid]
                if g7_gid in gp and len(prior) >= 3:
                    by_team[key[2]].append((key, mean(prior), gp[g7_gid], len(prior)))
            for team, plist in by_team.items():
                # rank by pre-G7 series scoring, take top-2 (the series' stars)
                plist.sort(key=lambda x: -x[1])
                for key, base, g7p, npg in plist[:2]:
                    if base >= 15.0:  # genuine scoring option floor
                        deltas.append({
                            "season": rec["season"],
                            "round": rec["round"],
                            "player": key[1],
                            "team": team,
                            "g7_pts": g7p,
                            "series_prior_avg_pts": round(base, 2),
                            "delta": round(g7p - base, 2),
                            "n_prior_games": npg,
                        })
            print(f"  star pass series {i+1}/{len(recs)} done ({rec['season']} {rec['round']})", flush=True)
        except Exception as e:
            print(f"  star pass series {i+1} FAILED: {e}", flush=True)
            time.sleep(3)
    return deltas


def summ(xs):
    if not xs:
        return None
    return {
        "n": len(xs),
        "mean": round(mean(xs), 3),
        "median": round(median(xs), 3),
        "std": round(pstdev(xs), 3) if len(xs) > 1 else None,
        "min": round(min(xs), 3),
        "max": round(max(xs), 3),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_rows = []
    for s in SEASONS:
        print(f"fetch {s} ...", flush=True)
        df = fetch_playoff_team_games(s)
        if df.empty:
            print(f"  WARNING: empty for {s}")
            continue
        df = df.copy()
        df["SEASON"] = s
        all_rows.extend(df.to_dict("records"))
        time.sleep(0.7)

    print(f"total team-game rows: {len(all_rows)}")
    series = build_series(all_rows)
    print(f"series reconstructed: {len(series)}")
    a = analyze(series)

    # totals deltas
    g7_totals = [t for t, _ in a["g7_total_vs_seravg"]]
    g7_base = [b for _, b in a["g7_total_vs_seravg"]]
    g7_diff = [t - b for t, b in a["g7_total_vs_seravg"]]
    elim_diff = [t - b for t, b in a["elim_total_vs_seravg"]]
    elim_totals = [t for t, _ in a["elim_total_vs_seravg"]]
    elim_base = [b for _, b in a["elim_total_vs_seravg"]]

    out = {
        "_meta": {
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "nba_api leaguegamefinder (Playoffs) + boxscoretraditionalv2",
            "window_seasons": [SEASONS[0], SEASONS[-1]],
            "recent_era_cutoff": RECENT_CUTOFF_SEASON,
            "n_team_game_rows": len(all_rows),
            "n_series": len(series),
            "note": "Every number computed from real game data. Game7/elim flags "
                    "decoded from playoff GAME_ID + reconstructed series score.",
        },
        "game7_home_win_rate": {
            "all_window": {
                "n": len(a["g7_home_wins_all"]),
                "rate": round(mean(a["g7_home_wins_all"]), 4) if a["g7_home_wins_all"] else None,
                "home_wins": sum(a["g7_home_wins_all"]),
            },
            "recent_era": {
                "cutoff": RECENT_CUTOFF_SEASON,
                "n": len(a["g7_home_wins_recent"]),
                "rate": round(mean(a["g7_home_wins_recent"]), 4) if a["g7_home_wins_recent"] else None,
                "home_wins": sum(a["g7_home_wins_recent"]),
            },
        },
        "elimination_under_thesis": {
            "game7_total_vs_series_prior_avg": {
                "n": len(g7_diff),
                "mean_g7_total": summ(g7_totals)["mean"] if g7_totals else None,
                "mean_series_prior_avg_total": summ(g7_base)["mean"] if g7_base else None,
                "mean_diff_g7_minus_prior": round(mean(g7_diff), 3) if g7_diff else None,
                "median_diff": round(median(g7_diff), 3) if g7_diff else None,
                "pct_g7_under_series_avg": round(mean([1 if d < 0 else 0 for d in g7_diff]), 4) if g7_diff else None,
            },
            "elimination_game_total_vs_series_prior_avg": {
                "n": len(elim_diff),
                "mean_elim_total": summ(elim_totals)["mean"] if elim_totals else None,
                "mean_series_prior_avg_total": summ(elim_base)["mean"] if elim_base else None,
                "mean_diff_elim_minus_prior": round(mean(elim_diff), 3) if elim_diff else None,
                "median_diff": round(median(elim_diff), 3) if elim_diff else None,
                "pct_elim_under_series_avg": round(mean([1 if d < 0 else 0 for d in elim_diff]), 4) if elim_diff else None,
            },
        },
        "game7_home_margin_distribution": summ(a["g7_margins"]),
        "game7_home_margin_buckets": None,
        "game7_list": a["g7_records"],
    }

    # margin buckets
    m = a["g7_margins"]
    if m:
        out["game7_home_margin_buckets"] = {
            "home_win": sum(1 for x in m if x > 0),
            "away_win": sum(1 for x in m if x < 0),
            "home_by_10plus": sum(1 for x in m if x >= 10),
            "home_by_1to9": sum(1 for x in m if 1 <= x <= 9),
            "away_by_1to9": sum(1 for x in m if -9 <= x <= -1),
            "away_by_10plus": sum(1 for x in m if x <= -10),
            "within_6_pts": sum(1 for x in m if abs(x) <= 6),
        }

    # star deltas (boxscore-heavy; do all G7 series in window)
    print("star delta pass (boxscore pulls per G7 series)...")
    sd = star_deltas(a["g7_records"])
    star_deltavals = [d["delta"] for d in sd]
    out["star_scoring_in_game7"] = {
        "method": "top-2 scorers per team per G7 series; G7 pts minus their mean "
                  "pts over games 1..6 of the SAME series (>=3 prior games req'd)",
        "n_star_games": len(sd),
        "mean_delta_g7_minus_series_avg": round(mean(star_deltavals), 3) if star_deltavals else None,
        "median_delta": round(median(star_deltavals), 3) if star_deltavals else None,
        "std_delta": round(pstdev(star_deltavals), 3) if len(star_deltavals) > 1 else None,
        "pct_stars_under_series_avg": round(mean([1 if d < 0 else 0 for d in star_deltavals]), 4) if star_deltavals else None,
        "detail": sorted(sd, key=lambda x: x["delta"]),
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"WROTE {OUT_PATH}")
    # console summary
    print(json.dumps({k: v for k, v in out.items() if k not in ("game7_list", "star_scoring_in_game7")}, indent=2))
    print("star summary:", out["star_scoring_in_game7"]["mean_delta_g7_minus_series_avg"],
          "n=", out["star_scoring_in_game7"]["n_star_games"])


if __name__ == "__main__":
    main()
