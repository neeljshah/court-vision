"""
effects_vacated_load.py
Measure teammate usage/scoring reroute when a high-usage star is OUT.

Method:
1. Load all gamelog JSONs for seasons 2022-23 through 2024-25 (per-game box stats).
2. Identify high-usage stars: top-20% FGA+0.44FTA+TOV per minute, >=20 games.
3. For each star, find games their team played but star DID NOT appear (injured/inactive
   per dnp_rows; not just coach decision).
4. Compare teammate per-min stats: star-IN vs star-OUT games.
5. Report usage multiplier, pts multiplier, and recommended sim parameter.

NOTE: gamelogs only contain games players PLAYED (no DNP rows).
Star-OUT = team game not in star's played_game_ids AND confirmed in injury DNP table.

Sources:
  data/nba/gamelog_full_{pid}_{season}.json
  data/dnp_rows.parquet
"""

import json
import glob
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

REPO = Path("C:/Users/neelj/nba-ai-system")
GAMELOG_DIR = REPO / "data" / "nba"
DNP_PATH = REPO / "data" / "dnp_rows.parquet"
SEASONS = ["2022-23", "2023-24", "2024-25"]

# ── 1. Load all gamelogs ────────────────────────────────────────────────────

print("Loading gamelogs ...", flush=True)
gl_rows = []
for season in SEASONS:
    pattern = str(GAMELOG_DIR / f"gamelog_full_*_{season}.json")
    for fpath in glob.glob(pattern):
        pid_str = os.path.basename(fpath).replace("gamelog_full_", "").replace(f"_{season}.json", "")
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        with open(fpath) as fh:
            games = json.load(fh)
        for g in games:
            min_str = g.get("min", 0)
            try:
                if isinstance(min_str, str) and ":" in min_str:
                    parts = min_str.split(":")
                    minutes = int(parts[0]) + int(parts[1]) / 60
                else:
                    minutes = float(min_str or 0)
            except Exception:
                minutes = 0.0
            matchup = g.get("matchup", "")
            team = matchup[:3].strip() if matchup else ""
            gl_rows.append({
                "season": season,
                "player_id": pid,
                "game_id": str(g.get("game_id", "")),
                "game_date": str(g.get("game_date", "")),
                "team": team,
                "min": minutes,
                "fga": int(g.get("fga") or 0),
                "fta": int(g.get("fta") or 0),
                "tov": int(g.get("tov") or 0),
                "pts": int(g.get("pts") or 0),
                "ast": int(g.get("ast") or 0),
            })

gl = pd.DataFrame(gl_rows)
gl["usage_raw"] = gl["fga"] + 0.44 * gl["fta"] + gl["tov"]
print(f"  {len(gl):,} player-game rows, {gl['player_id'].nunique()} players, "
      f"{gl['game_id'].nunique()} unique games", flush=True)

# ── 2. Identify high-usage stars ───────────────────────────────────────────

season_stats = (gl[gl["min"] > 5]
                .groupby(["season", "player_id", "team"])
                .agg(total_usage=("usage_raw", "sum"),
                     total_min=("min", "sum"),
                     total_pts=("pts", "sum"),
                     n_games=("game_id", "nunique"))
                .reset_index())
season_stats["use_per_min"] = season_stats["total_usage"] / season_stats["total_min"]
season_stats["pts_per_min"] = season_stats["total_pts"] / season_stats["total_min"]

thresh = season_stats.groupby("season")["use_per_min"].quantile(0.80).rename("thresh_80")
season_stats = season_stats.join(thresh, on="season")
season_stats["is_star"] = season_stats["use_per_min"] >= season_stats["thresh_80"]
stars = season_stats[season_stats["is_star"] & (season_stats["n_games"] >= 20)].copy()
print(f"  Stars (top-20% usage, >=20g): {len(stars)} player-seasons", flush=True)

# ── 3. Build star-IN and star-OUT game sets ───────────────────────────────

# All games per team-season
team_games = (gl.groupby(["season", "team"])["game_id"]
              .agg(set).reset_index()
              .rename(columns={"game_id": "all_team_games"}))

# Games each player actually played (min > 5 to avoid garbage-time slivers)
star_played = (gl[gl["min"] > 5]
               .groupby(["season", "player_id", "team"])["game_id"]
               .agg(set).reset_index()
               .rename(columns={"game_id": "played_games"}))

# Injury/inactive DNP table (not coach decisions)
dnp = pd.read_parquet(DNP_PATH)
dnp["game_id"] = dnp["game_id"].astype(str)
inj_dnp = dnp[dnp["dnp_reason"].isin(["injury", "inactive"])].copy()

# For each star, confirmed-missed games = team games - played games,
# intersected with injury DNP records
star_info = stars.merge(star_played, on=["season", "player_id", "team"], how="left")
star_info = star_info.merge(team_games, on=["season", "team"], how="left")

def confirmed_missed(row):
    played = row["played_games"] if isinstance(row["played_games"], set) else set()
    missed = row["all_team_games"] - played if isinstance(row["all_team_games"], set) else set()
    pid = row["player_id"]
    inj_games = set(inj_dnp[inj_dnp["player_id"] == pid]["game_id"])
    return missed & inj_games  # injury-confirmed misses only

star_info["out_games"] = star_info.apply(confirmed_missed, axis=1)
star_info["n_out"] = star_info["out_games"].apply(len)
star_info["n_in"] = star_info["played_games"].apply(lambda x: len(x) if isinstance(x, set) else 0)

print(f"  Stars with >=3 injury-confirmed out games: "
      f"{(star_info['n_out'] >= 3).sum()}", flush=True)

# ── 4. Compute teammate per-min stats for each star IN/OUT condition ────────

results = []
for _, row in star_info.iterrows():
    if row["n_out"] < 3 or row["n_in"] < 15:
        continue

    season = row["season"]
    team = row["team"]
    star_pid = row["player_id"]
    out_games = row["out_games"]
    in_games = row["played_games"]

    # Teammates = same season/team, different player, played (min > 0)
    team_gl = gl[(gl["season"] == season) &
                 (gl["team"] == team) &
                 (gl["player_id"] != star_pid) &
                 (gl["min"] > 0)]

    tmm_in = team_gl[team_gl["game_id"].isin(in_games)]
    tmm_out = team_gl[team_gl["game_id"].isin(out_games)]

    if len(tmm_in) < 20 or len(tmm_out) < 10:
        continue

    def per_min(df):
        total_min = df["min"].sum()
        if total_min == 0:
            return None
        return {
            "use_per_min": df["usage_raw"].sum() / total_min,
            "pts_per_min": df["pts"].sum() / total_min,
            "ast_per_min": df["ast"].sum() / total_min,
            "n_games": df["game_id"].nunique(),
        }

    s_in = per_min(tmm_in)
    s_out = per_min(tmm_out)
    if s_in is None or s_out is None:
        continue

    results.append({
        "season": season,
        "team": team,
        "star_pid": star_pid,
        "star_use_pm": row["use_per_min"],
        "n_in": s_in["n_games"],
        "n_out": row["n_out"],
        "use_in": s_in["use_per_min"],
        "use_out": s_out["use_per_min"],
        "pts_in": s_in["pts_per_min"],
        "pts_out": s_out["pts_per_min"],
        "ast_in": s_in["ast_per_min"],
        "ast_out": s_out["ast_per_min"],
    })

res = pd.DataFrame(results)
if len(res) == 0:
    print("ERROR: no pairs found")
    sys.exit(1)

res["use_mult"] = res["use_out"] / res["use_in"]
res["pts_mult"] = res["pts_out"] / res["pts_in"]
res["ast_mult"] = res["ast_out"] / res["ast_in"]

print(f"\n  Valid star-in/out comparison pairs: {len(res)}", flush=True)

# ── 5. Aggregate results ───────────────────────────────────────────────────

# Weight by n_out (smaller/noisier cell)
w = res["n_out"].values

def wmean(col, wts):
    return (col.values * wts).sum() / wts.sum()

avg_use_in  = wmean(res["use_in"],  w)
avg_use_out = wmean(res["use_out"], w)
avg_pts_in  = wmean(res["pts_in"],  w)
avg_pts_out = wmean(res["pts_out"], w)
avg_ast_in  = wmean(res["ast_in"],  w)
avg_ast_out = wmean(res["ast_out"], w)

use_mult_wt = avg_use_out / avg_use_in
pts_mult_wt = avg_pts_out / avg_pts_in
ast_mult_wt = avg_ast_out / avg_ast_in

print()
print("=" * 64)
print("VACATED LOAD EFFECT -- teammate per-min when star IN vs OUT")
print("=" * 64)
print(f"  N star-seasons:       {len(res)}")
print(f"  Median n_out:         {res['n_out'].median():.0f}  | median n_in: {res['n_in'].median():.0f}")
print()
print(f"  Teammate USAGE/min  star IN:  {avg_use_in:.4f}")
print(f"  Teammate USAGE/min  star OUT: {avg_use_out:.4f}")
print(f"  Usage multiplier:             {use_mult_wt:.4f}  ({(use_mult_wt-1)*100:+.1f}%)")
print()
print(f"  Teammate PTS/min    star IN:  {avg_pts_in:.4f}")
print(f"  Teammate PTS/min    star OUT: {avg_pts_out:.4f}")
print(f"  PTS/min multiplier:           {pts_mult_wt:.4f}  ({(pts_mult_wt-1)*100:+.1f}%)")
print()
print(f"  Teammate AST/min    star IN:  {avg_ast_in:.4f}")
print(f"  Teammate AST/min    star OUT: {avg_ast_out:.4f}")
print(f"  AST/min multiplier:           {ast_mult_wt:.4f}  ({(ast_mult_wt-1)*100:+.1f}%)")

# Per-star-season distribution
print()
print("  Per-star use_mult distribution:")
print(f"    p10={res['use_mult'].quantile(.10):.3f}  "
      f"p25={res['use_mult'].quantile(.25):.3f}  "
      f"median={res['use_mult'].median():.3f}  "
      f"p75={res['use_mult'].quantile(.75):.3f}  "
      f"p90={res['use_mult'].quantile(.90):.3f}")

# Significance
t, pval = scipy_stats.ttest_1samp(res["use_mult"], popmean=1.0)
print(f"\n  t-test (use_mult vs 1.0): t={t:.2f}, p={pval:.4f}, n={len(res)}")

# ── 6. By star usage tier ──────────────────────────────────────────────────

res["tier"] = pd.qcut(res["star_use_pm"], 3, labels=["mid_star", "high_star", "elite_star"])
print()
print("  By star tier:")
for tier in ["mid_star", "high_star", "elite_star"]:
    grp = res[res["tier"] == tier]
    ww = grp["n_out"].values
    um = wmean(grp["use_out"], ww) / wmean(grp["use_in"], ww)
    pm = wmean(grp["pts_out"], ww) / wmean(grp["pts_in"], ww)
    print(f"    {tier:12s}: n={len(grp):3d}  use_mult={um:.3f}  pts_mult={pm:.3f}  "
          f"star_use_pm_avg={grp['star_use_pm'].mean():.3f}")

# ── 7. Per-player role absorption ─────────────────────────────────────────

# Use individual-level data: for each teammate of a star, compare their
# per-game usage-per-min star-IN vs. star-OUT
print()
print("  Per-player role absorption (teammate's own use_mult):")

player_stats = (gl[gl["min"] > 5]
                .groupby(["season", "player_id", "team"])
                .agg(use_pm=("usage_raw", lambda x: x.sum() / gl.loc[x.index, "min"].sum()),
                     n_g=("game_id", "nunique"))
                .reset_index())
player_stats["role"] = pd.qcut(
    player_stats["use_pm"], 4,
    labels=["bench", "role", "secondary", "co_star"],
    duplicates="drop")

role_records = {r: {"use_mult": [], "n": 0} for r in ["bench", "role", "secondary", "co_star"]}

# Precompute lookup: (season, pid, team) -> role
role_lu = {(r["season"], r["player_id"], r["team"]): r["role"]
           for _, r in player_stats.iterrows()}

for _, row in star_info[star_info["n_out"] >= 3].iterrows():
    if row["n_in"] < 15:
        continue
    season = row["season"]
    team = row["team"]
    star_pid = row["player_id"]
    out_games = row["out_games"]
    in_games = row["played_games"] if isinstance(row["played_games"], set) else set()

    team_gl = gl[(gl["season"] == season) &
                 (gl["team"] == team) &
                 (gl["player_id"] != star_pid) &
                 (gl["min"] > 0)]

    for pid2, pg in team_gl.groupby("player_id"):
        role = role_lu.get((season, pid2, team), None)
        if role is None:
            continue
        pg_in = pg[pg["game_id"].isin(in_games)]
        pg_out = pg[pg["game_id"].isin(out_games)]
        if len(pg_in) < 5 or len(pg_out) < 2:
            continue
        min_in = pg_in["min"].sum()
        min_out = pg_out["min"].sum()
        if min_in == 0 or min_out == 0:
            continue
        u_in = pg_in["usage_raw"].sum() / min_in
        u_out = pg_out["usage_raw"].sum() / min_out
        if u_in > 0:
            role_records[role]["use_mult"].append(u_out / u_in)
            role_records[role]["n"] += 1

for role_label in ["bench", "role", "secondary", "co_star"]:
    arr = role_records[role_label]["use_mult"]
    if arr:
        print(f"    {role_label:12s}: n_player-stars={len(arr):4d}  "
              f"median_use_mult={np.median(arr):.3f}  "
              f"mean_use_mult={np.mean(arr):.3f}")
    else:
        print(f"    {role_label:12s}: no data")

# ── 8. Minutes absorption check ───────────────────────────────────────────
# Do teammates get MORE minutes when star is out?
min_results = []
for _, row in star_info[star_info["n_out"] >= 3].iterrows():
    if row["n_in"] < 15:
        continue
    season = row["season"]
    team = row["team"]
    star_pid = row["player_id"]
    out_games = row["out_games"]
    in_games = row["played_games"] if isinstance(row["played_games"], set) else set()

    team_gl = gl[(gl["season"] == season) &
                 (gl["team"] == team) &
                 (gl["player_id"] != star_pid) &
                 (gl["min"] > 0)]

    # Average team minutes per game (teammates only)
    tmm_in_g = team_gl[team_gl["game_id"].isin(in_games)]
    tmm_out_g = team_gl[team_gl["game_id"].isin(out_games)]
    if len(tmm_in_g) < 10 or len(tmm_out_g) < 5:
        continue
    avg_min_in = tmm_in_g.groupby("game_id")["min"].sum().mean()
    avg_min_out = tmm_out_g.groupby("game_id")["min"].sum().mean()
    star_mpg = row["total_min"] / max(row["n_games"], 1)
    min_results.append({
        "avg_min_in": avg_min_in,
        "avg_min_out": avg_min_out,
        "star_mpg": star_mpg,
        "min_delta": avg_min_out - avg_min_in,
    })

mr = pd.DataFrame(min_results)
print()
print(f"  Star avg MPG (vacated): {mr['star_mpg'].mean():.1f}")
print(f"  Team min (excl star) IN:  {mr['avg_min_in'].mean():.1f}")
print(f"  Team min (excl star) OUT: {mr['avg_min_out'].mean():.1f}")
print(f"  Delta minutes absorbed:   {mr['min_delta'].mean():+.1f}  "
      f"(of star avg {mr['star_mpg'].mean():.1f} MPG)")

print()
print("=" * 64)
print("RECOMMENDED SIM PARAMETER")
print("=" * 64)
print(f"  Parameter: usage_reroute_mult")
print(f"  Value:     {use_mult_wt:.3f}")
print(f"  Formula:   when star is DNP, multiply each active teammate's")
print(f"             usage_per_possession by {use_mult_wt:.3f}")
print(f"  Points follow similarly (pts_mult={pts_mult_wt:.3f})")
print(f"  Baseline:  teammate usage/min = {avg_use_in:.4f} (star IN)")
print(f"  Condition: teammate usage/min = {avg_use_out:.4f} (star OUT)")
print(f"  N obs:     {res['n_out'].sum():.0f} star-out game-slots across {len(res)} star-seasons")
print("=" * 64)
