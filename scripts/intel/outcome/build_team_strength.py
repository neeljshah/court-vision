"""
build_team_strength.py
======================
Compute 2025-26 season team outcome-strength cards and save to
data/cache/intel_outcome/team_strength.json.

Deliverables per team
---------------------
1.  Record W-L, point differential per game, pts-for/against per game.
2.  Off/def/net rating from leaguegamelog (100-possession normalised via pace
    from team_advanced_stats where available; otherwise raw per-game average).
    Pace per team (avg possessions), game-total tendency vs league average.
3.  Home vs road splits: win%, avg margin.
4.  SRS-style opponent-adjusted rating via iterative margin convergence
    (10 iterations; normalised so league mean = 0).
5.  Logistic win-probability model: margin → P(win) for any neutral-floor
    matchup (fit on 2025-26 regular-season game margins).
6.  Leak-free as-of time series: for each team×game, the SRS-style rating
    computed using ONLY games strictly before that game date.

Output JSON schema
------------------
{
  "as_of_date": "YYYY-MM-DD",          # date script was run (= context date)
  "season": "2025-26",
  "sources": [...],                     # source files used
  "league": {
    "avg_game_total_pts": float,        # avg combined score per game
    "home_win_pct": float,              # season-wide home-team win %
    "home_court_margin_pts": float,     # avg margin advantage of home team
    "logistic_scale_pt_per_pct": float, # 1 rating pt ≈ X win-prob pp
    "logistic_k": float,               # fitted sigmoid k coefficient
    "n_games": int
  },
  "teams": {
    "<TRI>": {
      "team": str,                      # 3-letter tricode
      "full_name": str,                 # full team name
      "wins": int,
      "losses": int,
      "win_pct": float,
      "n_games": int,
      "pts_for_pg": float,              # avg points scored per game
      "pts_against_pg": float,          # avg points allowed per game
      "margin_pg": float,               # avg point differential per game (for - against)
      "off_rtg": float,                 # offensive rating (pts/100 poss), season avg
      "def_rtg": float,                 # defensive rating (pts allowed/100 poss), season avg
      "net_rtg": float,                 # off_rtg - def_rtg
      "pace": float,                    # avg possessions per 48 min, season avg
      "avg_game_total": float,          # avg combined pts in their games
      "game_total_vs_league": float,    # avg_game_total - league avg (+ = pace up games)
      "home_win_pct": float,
      "home_margin_pg": float,
      "road_win_pct": float,
      "road_margin_pg": float,
      "home_games": int,
      "road_games": int,
      "srs_rating": float,              # opponent-adjusted rating (neutral floor, vs avg opp)
      "srs_rank": int,                  # rank 1=best, 30=worst
      "market_implied_spread": float,   # avg closing spread (home_spread) when they play (signed: neg favours them)
      "as_of": [
        {
          "date": "YYYY-MM-DD",         # date of the game being played
          "game_id": str,
          "rating_to_date": float,      # SRS rating using only prior-game data (leak-free)
          "n_games_prior": int          # number of games used to compute rating
        },
        ...
      ]
    }
  }
}

Leak-safety argument
--------------------
The as_of series entry for date D uses only games with game_date < D.
The iterative SRS solve is re-run on that restricted game set, so no
outcome from game-on-date-D (or later) contaminates the rating.
"""

import json
import pathlib
import warnings
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit  # sigmoid

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path("C:/Users/neelj/nba-ai-system")
OUT_DIR = ROOT / "data/cache/intel_outcome"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "team_strength.json"

GAMELOG_PATH = ROOT / "data/cache/cv_fix/leaguegamelog_regular_season.parquet"
ADV_STATS_PATH = ROOT / "data/team_advanced_stats.parquet"
SPREADS_PATH = ROOT / "data/pregame_spreads.parquet"


# ── Helper: build game-level dataframe from player gamelog ───────────────────

def build_games_df(gl: pd.DataFrame) -> pd.DataFrame:
    """Aggregate player gamelog → one row per game with home/away scores."""
    gl = gl[gl["SEASON_ID"] == "22025"].copy()

    team_game = (
        gl.groupby(["GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION"])
        .agg(
            team_pts=("PTS", "sum"),
            is_home=("MATCHUP", lambda x: int(any("vs." in m for m in x))),
            wl=("WL", "first"),
        )
        .reset_index()
    )

    home_tg = team_game[team_game["is_home"] == 1][
        ["GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "team_pts"]
    ].rename(columns={"TEAM_ABBREVIATION": "home_tri", "team_pts": "home_pts"})

    away_tg = team_game[team_game["is_home"] == 0][
        ["GAME_ID", "TEAM_ABBREVIATION", "team_pts"]
    ].rename(columns={"TEAM_ABBREVIATION": "away_tri", "team_pts": "away_pts"})

    games = home_tg.merge(away_tg, on="GAME_ID").copy()
    games["margin"] = games["home_pts"] - games["away_pts"]
    games["total_pts"] = games["home_pts"] + games["away_pts"]
    games["GAME_DATE"] = pd.to_datetime(games["GAME_DATE"])
    games = games.sort_values("GAME_DATE").reset_index(drop=True)
    return games


# ── Helper: SRS iterative solve ───────────────────────────────────────────────

def solve_srs(games: pd.DataFrame, teams: list, n_iter: int = 10) -> dict:
    """
    Simple Rating System (SRS) via iterative average-margin convergence.
    rating[team] ≈ avg_margin_pg + avg(opponent_ratings)
    Normalised so league mean = 0.

    Returns dict: team → srs_rating
    """
    team_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ratings = np.zeros(n)

    # Build margin lookup per team
    # For each team, track all games: (opponent, home_margin_for_this_team)
    team_records: dict = {t: [] for t in teams}
    for _, row in games.iterrows():
        h, a = row["home_tri"], row["away_tri"]
        m = row["margin"]  # positive = home won
        if h in team_records:
            team_records[h].append((a, m))   # home margin for home team
        if a in team_records:
            team_records[a].append((h, -m))  # away team margin = -home margin

    for _ in range(n_iter):
        new_ratings = np.zeros(n)
        for t in teams:
            records = team_records[t]
            if not records:
                continue
            opp_ratings = [ratings[team_idx[opp]] for opp, _ in records if opp in team_idx]
            margins = [m for _, m in records]
            if not opp_ratings:
                new_ratings[team_idx[t]] = np.mean(margins)
            else:
                new_ratings[team_idx[t]] = np.mean(margins) - np.mean(opp_ratings)
        # Normalise: centre around 0
        new_ratings -= new_ratings.mean()
        ratings = new_ratings

    return {t: float(ratings[team_idx[t]]) for t in teams}


# ── Helper: logistic fit spread → P(home wins) ───────────────────────────────

def fit_logistic(games: pd.DataFrame, sp: pd.DataFrame):
    """
    Fit sigmoid: P(home_win) = expit(k * (-home_spread))
    using pre-game spreads as the predictive signal against actual outcomes.

    This is the correct predictive formulation — using actual game margins
    produces perfect separation (margin == outcome) and an unbounded k.
    We use pregame spreads (imperfect predictors) so the fit is well-defined.

    Returns k (scale coefficient).
    Falls back to k = 0.115 (domain convention: 7-pt fav ≈ 69% win) if
    fewer than 50 matched games are found.
    """
    ESPN_TO_TRI = {
        "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS",
        "UTAH": "UTA", "WSH": "WAS",
    }
    sp2 = sp.copy()
    sp2["home_tri_sp"] = sp2["home_team"].replace(ESPN_TO_TRI)
    sp2["game_date_dt"] = pd.to_datetime(sp2["game_date"])
    games2 = games.copy()
    games2["home_win"] = (games2["margin"] > 0).astype(int)

    merged = games2.merge(
        sp2[["game_date_dt", "home_tri_sp", "home_spread"]],
        left_on=["GAME_DATE", "home_tri"],
        right_on=["game_date_dt", "home_tri_sp"],
        how="inner",
    )

    if len(merged) < 50:
        print(f"  [logistic] Only {len(merged)} matched spread-game rows; using domain default k=0.115")
        return 0.115

    y = merged["home_win"].values.astype(float)
    x = -merged["home_spread"].values  # negative spread → home favourite → positive x

    def neg_loglik(k):
        p = expit(k * x)
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))

    res = minimize_scalar(neg_loglik, bounds=(0.01, 1.0), method="bounded")
    k = float(res.x)
    print(f"  [logistic] Fitted k={k:.4f} on {len(merged)} matched games")
    return k


# ── Helper: as-of SRS series (leak-free) ─────────────────────────────────────

def compute_as_of_series(games: pd.DataFrame, teams: list) -> dict:
    """
    For each game (ordered by date), compute the SRS rating for every team
    using ONLY games strictly before that game's date.

    Returns: {team: [{"date": ..., "game_id": ..., "rating_to_date": ..., "n_games_prior": ...}, ...]}
    """
    as_of: dict = {t: [] for t in teams}
    games_sorted = games.sort_values("GAME_DATE").reset_index(drop=True)

    # Group games by date for efficiency: for each date, we compute SRS on
    # all games BEFORE that date. Teams that play on date D get the same prior.
    dates = sorted(games_sorted["GAME_DATE"].unique())

    # Precompute: at each date boundary, what is the prior SRS?
    prior_srs_cache: dict = {}  # date_str → {team: rating}

    for i, d in enumerate(dates):
        d_str = str(d.date())
        prior_games = games_sorted[games_sorted["GAME_DATE"] < d]
        n_prior = len(prior_games)
        if n_prior < 2:
            prior_srs = {t: 0.0 for t in teams}
        else:
            prior_srs = solve_srs(prior_games, teams, n_iter=10)
        prior_srs_cache[d_str] = (prior_srs, n_prior)

    # Now assign to each game row
    for _, row in games_sorted.iterrows():
        d_str = str(row["GAME_DATE"].date())
        prior_srs, n_prior = prior_srs_cache[d_str]
        gid = row["GAME_ID"]
        game_date_str = d_str
        for tri in [row["home_tri"], row["away_tri"]]:
            if tri in as_of:
                as_of[tri].append({
                    "date": game_date_str,
                    "game_id": gid,
                    "rating_to_date": round(prior_srs.get(tri, 0.0), 4),
                    "n_games_prior": n_prior,
                })

    return as_of


# ── Helper: per-team net rating from advanced stats (if available) ───────────

def get_adv_ratings(adv: pd.DataFrame) -> pd.DataFrame:
    """
    Compute season-average off/def/net rtg and pace per team from
    team_advanced_stats.parquet.
    Only uses 2025-26 data (game_date >= 2025-10-01).
    """
    adv25 = adv[adv["game_date"] >= "2025-10-01"].copy()
    if adv25.empty:
        return pd.DataFrame()
    avg = (
        adv25.groupby("team_tricode")
        .agg(
            off_rtg=("off_rtg", "mean"),
            def_rtg=("def_rtg", "mean"),
            pace=("pace", "mean"),
        )
        .reset_index()
        .rename(columns={"team_tricode": "tri"})
    )
    avg["net_rtg"] = avg["off_rtg"] - avg["def_rtg"]
    return avg


# ── Helper: compute off/def rating from raw game box scores ──────────────────

def compute_raw_rtg(games: pd.DataFrame) -> pd.DataFrame:
    """
    Approximate per-100-possession ratings from game scores.
    Without possession counts we use a fixed average (≈ 100 poss/game)
    so this is effectively per-game pts scaled to /100-equiv.
    We will refine with pace from adv stats if available.
    """
    rows = []
    for tri in pd.unique(pd.concat([games["home_tri"], games["away_tri"]])):
        h = games[games["home_tri"] == tri]
        a = games[games["away_tri"] == tri]
        pts_for = list(h["home_pts"]) + list(a["away_pts"])
        pts_against = list(h["away_pts"]) + list(a["home_pts"])
        if pts_for:
            rows.append({
                "tri": tri,
                "off_rtg_raw": float(np.mean(pts_for)),
                "def_rtg_raw": float(np.mean(pts_against)),
                "net_rtg_raw": float(np.mean(pts_for)) - float(np.mean(pts_against)),
            })
    return pd.DataFrame(rows)


# ── Helper: market-implied spread ────────────────────────────────────────────

def get_market_spreads(sp: pd.DataFrame) -> dict:
    """
    For each team tricode, compute their average home_spread (when home)
    and average away_spread (when away = -home_spread of opponent).
    Returns {tri: avg_market_spread_as_home} — negative means team is favourite.

    Note: spreads use ESPN abbreviations which differ slightly.
    We match on known mapping.
    """
    ESPN_TO_TRI = {
        "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS",
        "UTAH": "UTA", "WSH": "WAS",
    }
    sp = sp.copy()
    sp["home_tri"] = sp["home_team"].replace(ESPN_TO_TRI)
    sp["away_tri"] = sp["away_team"].replace(ESPN_TO_TRI)

    result = {}
    all_tris = pd.unique(pd.concat([sp["home_tri"], sp["away_tri"]]))
    for tri in all_tris:
        home_rows = sp[sp["home_tri"] == tri]["home_spread"]
        away_rows = sp[sp["away_tri"] == tri]["home_spread"].apply(lambda x: -x)
        all_spreads = pd.concat([home_rows, away_rows])
        if len(all_spreads) > 0:
            result[tri] = float(all_spreads.mean())
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Load sources
    gl = pd.read_parquet(GAMELOG_PATH)
    adv = pd.read_parquet(ADV_STATS_PATH)
    sp = pd.read_parquet(SPREADS_PATH)

    # Full-name map from gamelog
    full_names = (
        gl[gl["SEASON_ID"] == "22025"]
        .groupby("TEAM_ABBREVIATION")["TEAM_NAME"]
        .first()
        .to_dict()
    )

    # Build game-level frame
    games = build_games_df(gl)
    n_games = len(games)
    teams = sorted(pd.unique(pd.concat([games["home_tri"], games["away_tri"]])).tolist())
    print(f"Games: {n_games}, Teams: {len(teams)}")

    # ── 1. Basic team records ──────────────────────────────────────────────────
    team_stats: dict = {}
    for tri in teams:
        home_g = games[games["home_tri"] == tri]
        away_g = games[games["away_tri"] == tri]

        home_wins = int((home_g["margin"] > 0).sum())
        away_wins = int((-away_g["margin"] > 0).sum())  # away margin flipped
        home_losses = len(home_g) - home_wins
        away_losses = len(away_g) - away_wins

        wins = home_wins + away_wins
        losses = home_losses + away_losses
        n = wins + losses

        pts_for_all = list(home_g["home_pts"]) + list(away_g["away_pts"])
        pts_ag_all = list(home_g["away_pts"]) + list(away_g["home_pts"])

        # Home splits
        home_pts_for = list(home_g["home_pts"])
        home_pts_ag = list(home_g["away_pts"])
        home_margin = list(home_g["margin"])

        # Road splits
        road_pts_for = list(away_g["away_pts"])
        road_pts_ag = list(away_g["home_pts"])
        road_margin = list(-away_g["margin"])  # from away team's perspective

        # Game totals
        game_totals = list(home_g["total_pts"]) + list(away_g["total_pts"])

        team_stats[tri] = {
            "team": tri,
            "full_name": full_names.get(tri, tri),
            "wins": wins,
            "losses": losses,
            "win_pct": round(wins / n, 4) if n > 0 else 0.0,
            "n_games": n,
            "pts_for_pg": round(float(np.mean(pts_for_all)), 2) if pts_for_all else 0.0,
            "pts_against_pg": round(float(np.mean(pts_ag_all)), 2) if pts_ag_all else 0.0,
            "margin_pg": round(float(np.mean(pts_for_all)) - float(np.mean(pts_ag_all)), 2) if pts_for_all else 0.0,
            "home_games": len(home_g),
            "road_games": len(away_g),
            "home_win_pct": round(home_wins / len(home_g), 4) if len(home_g) > 0 else 0.0,
            "home_margin_pg": round(float(np.mean(home_margin)), 2) if home_margin else 0.0,
            "road_win_pct": round(away_wins / len(away_g), 4) if len(away_g) > 0 else 0.0,
            "road_margin_pg": round(float(np.mean(road_margin)), 2) if road_margin else 0.0,
            "avg_game_total": round(float(np.mean(game_totals)), 2) if game_totals else 0.0,
        }

    # ── 2. Off/Def/Net rating and Pace ────────────────────────────────────────
    adv_rtg = get_adv_ratings(adv)
    raw_rtg = compute_raw_rtg(games)

    # adv_rtg is empty for 2025-26 (confirmed in recon), use raw
    if adv_rtg.empty:
        print("Advanced stats: no 2025-26 data — using raw game-score ratings.")
        rtg_df = raw_rtg.rename(columns={
            "off_rtg_raw": "off_rtg",
            "def_rtg_raw": "def_rtg",
            "net_rtg_raw": "net_rtg",
        })
        rtg_df["pace"] = None
    else:
        rtg_df = adv_rtg.rename(columns={"tri": "tri"})

    rtg_map = rtg_df.set_index("tri").to_dict("index")

    league_avg_total = float(games["total_pts"].mean())

    for tri in teams:
        r = rtg_map.get(tri, {})
        team_stats[tri]["off_rtg"] = round(float(r.get("off_rtg", team_stats[tri]["pts_for_pg"])), 2)
        team_stats[tri]["def_rtg"] = round(float(r.get("def_rtg", team_stats[tri]["pts_against_pg"])), 2)
        team_stats[tri]["net_rtg"] = round(float(r.get("net_rtg", team_stats[tri]["margin_pg"])), 2)
        pace_val = r.get("pace")
        team_stats[tri]["pace"] = round(float(pace_val), 2) if pace_val is not None else None
        team_stats[tri]["game_total_vs_league"] = round(team_stats[tri]["avg_game_total"] - league_avg_total, 2)

    # ── 3. Market-implied spreads ─────────────────────────────────────────────
    market_spreads = get_market_spreads(sp)
    for tri in teams:
        team_stats[tri]["market_implied_spread"] = round(market_spreads.get(tri, 0.0), 2)

    # ── 4. Full-season SRS ────────────────────────────────────────────────────
    srs = solve_srs(games, teams, n_iter=10)
    srs_ranked = sorted(teams, key=lambda t: srs[t], reverse=True)
    for rank, tri in enumerate(srs_ranked, 1):
        team_stats[tri]["srs_rating"] = round(srs[tri], 4)
        team_stats[tri]["srs_rank"] = rank

    # ── 5. Logistic fit ───────────────────────────────────────────────────────
    k = fit_logistic(games, sp)
    # 1 rating point ≈ how much win-probability change near margin=0?
    # dP/dx at x=0 = k/4  (sigmoid derivative at 0)
    pt_per_pct = round(1.0 / (k / 4) / 100, 4)  # pts per 1 pp
    print(f"Logistic k={k:.4f}  => 1 pt SRS ≈ {k/4*100:.2f} pp win-prob near neutral")

    # ── 6. Leak-free as-of series ─────────────────────────────────────────────
    print("Computing leak-free as-of series...")
    as_of_all = compute_as_of_series(games, teams)
    for tri in teams:
        team_stats[tri]["as_of"] = as_of_all.get(tri, [])

    # ── League constants ──────────────────────────────────────────────────────
    home_win_pct = float((games["margin"] > 0).mean())
    home_court_margin = float(games["margin"].mean())

    league_block = {
        "avg_game_total_pts": round(league_avg_total, 2),
        "home_win_pct": round(home_win_pct, 4),
        "home_court_margin_pts": round(home_court_margin, 2),
        "logistic_k": round(k, 6),
        "logistic_scale_pt_per_pct": pt_per_pct,
        "n_games": n_games,
    }

    # ── Assemble final JSON ────────────────────────────────────────────────────
    output = {
        "as_of_date": str(date.today()),
        "season": "2025-26",
        "sources": [
            str(GAMELOG_PATH.relative_to(ROOT)),
            str(ADV_STATS_PATH.relative_to(ROOT)),
            str(SPREADS_PATH.relative_to(ROOT)),
        ],
        "league": league_block,
        "teams": team_stats,
    }

    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nSaved → {OUT_PATH}")

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"LEAGUE CONSTANTS")
    print(f"  avg game total     : {league_avg_total:.1f} pts")
    print(f"  home win pct       : {home_win_pct:.3f}")
    print(f"  home court margin  : {home_court_margin:+.2f} pts")
    print(f"  logistic k         : {k:.4f}")
    print(f"  1 SRS pt ≈         : {k/4*100:.2f} pp win-prob")

    print(f"\nTOP 5 by SRS (best teams):")
    for tri in srs_ranked[:5]:
        ts = team_stats[tri]
        print(f"  #{ts['srs_rank']:2d}  {tri:5s}  SRS={ts['srs_rating']:+6.2f}  W-L={ts['wins']}-{ts['losses']}  margin_pg={ts['margin_pg']:+5.2f}")

    print(f"\nBOTTOM 5 by SRS (weakest teams):")
    for tri in srs_ranked[-5:]:
        ts = team_stats[tri]
        print(f"  #{ts['srs_rank']:2d}  {tri:5s}  SRS={ts['srs_rating']:+6.2f}  W-L={ts['wins']}-{ts['losses']}  margin_pg={ts['margin_pg']:+5.2f}")

    # Verify as-of leak-free property
    print(f"\nLEAK-FREE VERIFICATION (first 3 entries for OKC):")
    okc_series = team_stats.get("OKC", {}).get("as_of", [])
    for entry in okc_series[:3]:
        print(f"  date={entry['date']}  n_prior={entry['n_games_prior']}  rating={entry['rating_to_date']:+.4f}")


if __name__ == "__main__":
    main()
