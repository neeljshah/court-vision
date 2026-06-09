"""
INT-52: Opponent Defensive Intensity Atlas (C3 step 4)
Rolling per-team-per-date defensive intensity with 6 dimensions, z-scored
via expanding-window league pool (walk-forward safe, strict date < game_date).

Inputs:
  - data/nba_ai.db           cv_features table (long-form)
  - data/nba/season_games_*.json  game_id -> date + home/away team mapping
  - data/nba/player_full_*.json   player_id -> team mapping
  - data/team_advanced_stats.parquet  for def_rtg correlation sanity check

Outputs:
  - data/intelligence/opp_defensive_intensity.parquet

Usage:
    python scripts/build_opp_defensive_intensity.py
    python scripts/build_opp_defensive_intensity.py --window 10
    python scripts/build_opp_defensive_intensity.py --window 5 --window-second 10
"""
from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths — script-relative ROOT; no hardcoded Windows paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
NBA_CACHE_DIR = DATA_DIR / "nba"
DB_PATH = DATA_DIR / "nba_ai.db"
OUT_PARQUET = DATA_DIR / "intelligence" / "opp_defensive_intensity.parquet"
TEAM_ADV_STATS = DATA_DIR / "team_advanced_stats.parquet"

# ---------------------------------------------------------------------------
# Bug 35 tolerance: closeout dim is NULL when < this fraction of opposing
# player-games in the window have non-zero avg_closeout_speed values.
# All current values are 0.0 (known-broken), so this will always fire.
# ---------------------------------------------------------------------------
_CLOSEOUT_MIN_COVERAGE = 0.40  # 40% must be non-None AND non-zero

# Bug 22 sentinel guard: defender_distance >= 50 is a 200.0 sentinel artifact
_DEFENDER_DIST_MAX = 50.0

# Dimension weights for composite (contested_shot_rate + defender_distance = 2x)
_DIM_WEIGHTS = {
    "opp_contested_shot_rate_imposed_z": 2.0,
    "opp_avg_defender_distance_imposed_z": 2.0,
    "opp_paint_attempts_allowed_pct_z": 1.0,
    "opp_pace_imposed_z": 1.0,
    "opp_catch_shoot_allowed_pct_z": 1.0,
    "opp_closeout_speed_imposed_z": 1.0,  # dropped from composite when NULL
}

# Quality residualization (Bug-13 pattern from build_defensive_schemes.py)
_QUALITY_WEIGHT = 0.08


# ---------------------------------------------------------------------------
# Step 1: Load player_id -> team_abbrev from player_full JSON files
# ---------------------------------------------------------------------------

def _load_player_team_map() -> Dict[int, str]:
    """
    Build {player_id: team_abbrev} from player_full_*.json files.
    Most-recent season wins; season-level assignment only.
    """
    pid_to_team: Dict[int, str] = {}
    season_files = ["player_full_2025-26.json", "player_full_2024-25.json",
                    "player_full_2023-24.json"]
    for fname in season_files:
        fpath = NBA_CACHE_DIR / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
            continue
        if isinstance(data, dict):
            for _name, info in data.items():
                if isinstance(info, dict):
                    pid = info.get("player_id") or info.get("PLAYER_ID")
                    team = info.get("team") or info.get("TEAM_ABBREVIATION")
                    if pid and team:
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    pid = row.get("player_id") or row.get("PLAYER_ID")
                    team = row.get("team") or row.get("TEAM_ABBREVIATION")
                    if pid and team:
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
    return pid_to_team


# ---------------------------------------------------------------------------
# Step 2: Load game_id -> {date, home_team, away_team} from season_games JSON
# ---------------------------------------------------------------------------

def _load_game_info_map() -> Dict[str, dict]:
    """Return {game_id: {date, home_team, away_team}} from all season_games_*.json."""
    gmap: Dict[str, dict] = {}
    for fpath in glob.glob(str(NBA_CACHE_DIR / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row:
                    gid = str(row["game_id"])
                    gmap[gid] = {
                        "date": row.get("game_date", ""),
                        "home_team": row.get("home_team", ""),
                        "away_team": row.get("away_team", ""),
                    }
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
    return gmap


# ---------------------------------------------------------------------------
# Step 3: Load cv_features from DB, pivot wide, map players to offensive teams
# ---------------------------------------------------------------------------

def _load_cv_wide(db_path: Path) -> pd.DataFrame:
    """
    Load cv_features and pivot to wide form.
    Returns DataFrame with columns: game_id, player_id, + one col per feature_name.
    """
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
        " WHERE player_id != 0"
    ).fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["player_id", "game_id", "feature_name", "feature_value"])
    # Pivot: one row per (game_id, player_id), feature_name columns
    wide = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide


# ---------------------------------------------------------------------------
# Step 4: Map each player-game to their OFFENSIVE team (the team being defended)
# and the DEFENSIVE team (the opponent imposing defensive pressure).
# ---------------------------------------------------------------------------

def _assign_teams(
    wide: pd.DataFrame,
    pid_to_team: Dict[int, str],
    game_info: Dict[str, dict],
) -> pd.DataFrame:
    """
    Add columns: offensive_team, defensive_team, game_date.
    offensive_team = team the player belongs to (team being defended).
    defensive_team = the opposing team (team imposing defense on this player).
    """
    # Map player -> offensive team
    wide["offensive_team"] = wide["player_id"].map(lambda p: pid_to_team.get(int(p)))

    # Map game -> date + teams
    wide["game_date"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("date", ""))
    wide["home_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("home_team", ""))
    wide["away_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("away_team", ""))

    # Defensive team = opposite team in the game
    def _get_def_team(row):
        ot = row["offensive_team"]
        if not ot:
            return None
        ht = row["home_team"]
        at = row["away_team"]
        if ot == ht:
            return at
        elif ot == at:
            return ht
        else:
            # Player team not in this game's home/away (trade artifact) — skip
            return None

    wide["defensive_team"] = wide.apply(_get_def_team, axis=1)

    # Drop rows with missing team/date
    before = len(wide)
    wide = wide.dropna(subset=["offensive_team", "defensive_team", "game_date"])
    wide = wide[wide["game_date"] != ""]
    after = len(wide)
    print(f"  Player-game rows after team assignment: {after} (dropped {before - after} unmapped)")
    return wide


# ---------------------------------------------------------------------------
# Step 5: For each (defensive_team, game_date) rolling window, compute
# raw feature means from the cv rows of players they defended.
# ---------------------------------------------------------------------------

_INTENSITY_FEATURES = {
    "contested_shot_rate": "opp_contested_shot_rate_imposed_z",
    "avg_defender_distance": "opp_avg_defender_distance_imposed_z",
    "shot_zone_paint_pct": "opp_paint_attempts_allowed_pct_z",
    "possession_duration_avg": "opp_pace_imposed_z",      # will be inverted: 1/duration = pace
    "catch_shoot_pct": "opp_catch_shoot_allowed_pct_z",
    "avg_closeout_speed": "opp_closeout_speed_imposed_z",
}


def _compute_raw_game_level(wide: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate cv feature columns from (game_id, player) to (game_id, defensive_team) level.
    Returns one row per (game_id, defensive_team, game_date) with mean feature values.
    """
    feat_cols = list(_INTENSITY_FEATURES.keys())
    # Ensure columns exist; fill missing with NaN
    for col in feat_cols:
        if col not in wide.columns:
            wide[col] = np.nan

    # Filter defender_distance sentinels (Bug 22)
    wide = wide.copy()
    if "avg_defender_distance" in wide.columns:
        wide.loc[wide["avg_defender_distance"] >= _DEFENDER_DIST_MAX, "avg_defender_distance"] = np.nan

    # Aggregate to game level by defensive_team
    agg_dict = {col: "mean" for col in feat_cols}
    agg_dict["player_id"] = "count"  # n_player_games in this game

    # Also track closeout non-null rate for Bug 35
    wide["_closeout_valid"] = (
        wide["avg_closeout_speed"].notna() &
        (wide["avg_closeout_speed"] != 0.0)
    ).astype(float)

    agg_dict["_closeout_valid"] = "mean"  # fraction with valid closeout

    game_level = (
        wide.groupby(["game_id", "defensive_team", "game_date"])
        .agg(agg_dict)
        .reset_index()
        .rename(columns={"player_id": "n_player_games_in_game"})
    )
    game_level["game_date"] = pd.to_datetime(game_level["game_date"])
    game_level = game_level.sort_values("game_date").reset_index(drop=True)
    return game_level


# ---------------------------------------------------------------------------
# Step 6: Walk-forward rolling window + expanding z-score pool
# ---------------------------------------------------------------------------

def _expand_zscore(
    all_means: pd.Series,
    all_dates: pd.Series,
    current_date: pd.Timestamp,
) -> float:
    """
    Compute league-expanding z-score pool up to (strictly less than) current_date.
    Returns (mean_val - league_mean) / league_std using all league obs before current_date.
    Returns 0.0 (league prior) if pool has <2 valid values.
    """
    mask = all_dates < current_date
    pool = all_means[mask].dropna()
    if len(pool) < 2:
        return np.nan  # signal: use league prior
    mu = pool.mean()
    sigma = pool.std(ddof=1)
    if sigma < 1e-9:
        return 0.0
    # Current value not in pool; caller passes current_val separately
    # But here we need current_val — handled in the outer loop
    return mu, sigma


def _compute_rolling_intensity(
    game_level: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """
    For each (defensive_team, game_date), compute rolling-window mean of each
    intensity dimension over the last `window` games, then z-score it
    via expanding league pool with strict date < game_date cutoff.

    Returns rows: team_id, season, game_date, n_games_window, 6 dims z-scores,
                  composite_z, data_density.
    """
    teams = sorted(game_level["defensive_team"].unique())
    print(f"  Computing rolling intensity for {len(teams)} defensive teams, window={window} ...")

    feat_cols = list(_INTENSITY_FEATURES.keys())

    # Pre-sort
    game_level = game_level.sort_values(["game_date", "defensive_team"]).reset_index(drop=True)

    # Pre-build league-wide series for expanding z-score: for each feature,
    # collect all (date, team_window_mean) pairs.
    # We compute team window means first, then z-score them.

    # Step 6a: for each team, compute rolling means over prior `window` games
    team_windows: List[dict] = []

    for team in teams:
        tdf = game_level[game_level["defensive_team"] == team].sort_values("game_date")

        for i, (_, row) in enumerate(tdf.iterrows()):
            gdate = row["game_date"]
            # Rolling window: up to window games BEFORE current (strict <)
            past = tdf[tdf["game_date"] < gdate].tail(window)
            n = len(past)

            if n == 0:
                continue  # no prior data

            rec: dict = {
                "team_id": team,
                "game_date": gdate,
                "n_games_window": n,
            }

            # Raw means over the window
            for feat in feat_cols:
                if feat == "avg_closeout_speed":
                    # Check Bug 35 coverage
                    valid_frac = past["_closeout_valid"].mean()
                    rec["_closeout_coverage"] = float(valid_frac)
                    if valid_frac >= _CLOSEOUT_MIN_COVERAGE:
                        rec["_raw_closeout"] = float(past[feat].mean()) if past[feat].notna().any() else np.nan
                    else:
                        rec["_raw_closeout"] = np.nan  # will become NULL in output
                elif feat == "avg_defender_distance":
                    vals = past[feat].dropna()
                    rec["_raw_avg_defender_distance"] = float(vals.mean()) if len(vals) else np.nan
                elif feat == "possession_duration_avg":
                    vals = past[feat].replace(0, np.nan).dropna()
                    # Convert to pace: 1/duration (higher pace = lower duration)
                    rec["_raw_pace"] = float((1.0 / vals).mean()) if len(vals) else np.nan
                else:
                    vals = past[feat].dropna()
                    rec[f"_raw_{feat}"] = float(vals.mean()) if len(vals) else np.nan

            team_windows.append(rec)

    if not team_windows:
        print("  WARNING: No team windows computed. Insufficient data.")
        return pd.DataFrame()

    tw_df = pd.DataFrame(team_windows).sort_values("game_date").reset_index(drop=True)
    print(f"  Team-game windows computed: {len(tw_df)} rows")

    # Step 6b: for each row, z-score using expanding pool of all teams' raw means
    # up to strictly < game_date
    raw_feature_map = {
        "opp_contested_shot_rate_imposed_z": "_raw_contested_shot_rate",
        "opp_avg_defender_distance_imposed_z": "_raw_avg_defender_distance",
        "opp_paint_attempts_allowed_pct_z": "_raw_shot_zone_paint_pct",
        "opp_pace_imposed_z": "_raw_pace",
        "opp_catch_shoot_allowed_pct_z": "_raw_catch_shoot_pct",
        "opp_closeout_speed_imposed_z": "_raw_closeout",
    }
    # Sign inversion: higher defender_distance = farther away = LOOSER defense.
    # We want imposed_z to be POSITIVE for tighter defense (lower distance = tighter).
    # So: invert sign for avg_defender_distance.
    _SIGN_INVERT = {"opp_avg_defender_distance_imposed_z"}

    # Build league quality_z for Bug-13 correction
    quality_z_map: Dict[str, float] = {}
    if TEAM_ADV_STATS.exists():
        try:
            tas = pd.read_parquet(TEAM_ADV_STATS)
            tas["season_year"] = pd.to_datetime(tas["game_date"]).dt.year
            recent = tas[tas["season_year"] >= 2024]
            team_defrtg = recent.groupby("team_tricode")["def_rtg"].mean()
            league_mean = float(team_defrtg.mean())
            league_std = float(team_defrtg.std())
            for t, drtg in team_defrtg.items():
                quality_z_map[str(t)] = (drtg - league_mean) / league_std
            print(f"  [Bug-13] Loaded def_rtg quality_z for {len(quality_z_map)} teams")
        except Exception as e:
            print(f"  [Bug-13] WARNING: could not load team_advanced_stats: {e}")

    results = []
    all_dates = tw_df["game_date"]

    for dim_col, raw_col in raw_feature_map.items():
        if raw_col not in tw_df.columns:
            tw_df[dim_col] = np.nan
            continue

        raw_series = tw_df[raw_col]
        z_vals = np.full(len(tw_df), np.nan)

        for idx, (_, row) in enumerate(tw_df.iterrows()):
            curr_val = row[raw_col]
            if pd.isna(curr_val):
                z_vals[idx] = np.nan
                continue

            curr_date = row["game_date"]
            mask = all_dates < curr_date
            pool = raw_series[mask].dropna()

            if len(pool) < 2:
                # League prior: z=0
                z_vals[idx] = np.nan  # marks as league_prior candidate
            else:
                mu = pool.mean()
                sigma = pool.std(ddof=1)
                if sigma < 1e-9:
                    z_vals[idx] = 0.0
                else:
                    z = (curr_val - mu) / sigma
                    # Sign inversion for defender_distance (lower = tighter D)
                    if dim_col in _SIGN_INVERT:
                        z = -z
                    z_vals[idx] = float(z)

        tw_df[dim_col] = z_vals

    # Apply Bug-13 quality residualization to each z-score dimension
    for dim_col in _DIM_WEIGHTS:
        if dim_col not in tw_df.columns:
            continue
        tw_df[f"_quality_corr"] = tw_df["team_id"].map(
            lambda t: quality_z_map.get(t, 0.0) * _QUALITY_WEIGHT
        )
        tw_df[dim_col] = tw_df[dim_col] - tw_df["_quality_corr"]

    # Step 6c: Composite z-score (NaN-safe weighted mean; drop closeout if NULL)
    def _composite(row):
        vals = []
        wts = []
        for dim, wt in _DIM_WEIGHTS.items():
            if dim == "opp_closeout_speed_imposed_z":
                # Only include if NOT null (Bug 35 tolerance — do NOT zero-fill)
                v = row.get(dim, np.nan)
                if pd.isna(v):
                    continue
                vals.append(v)
                wts.append(wt)
            else:
                v = row.get(dim, np.nan)
                if pd.isna(v):
                    continue
                vals.append(v)
                wts.append(wt)
        if not vals:
            return np.nan
        return float(np.average(vals, weights=wts))

    tw_df["opp_defensive_intensity_z"] = tw_df.apply(_composite, axis=1)

    # Step 6d: Shrinkage for small-N windows
    # n >= 5: use raw mean directly (already done via rolling window)
    # n 2-4: shrink toward 0 (league prior) at weight n/5
    # n < 2: set to 0 (league prior)
    def _apply_shrinkage(row, col):
        n = row["n_games_window"]
        v = row[col]
        if pd.isna(v):
            return v
        if n < 2:
            return 0.0
        elif n < 5:
            return v * (n / 5.0)
        return v

    dim_cols = list(_DIM_WEIGHTS.keys()) + ["opp_defensive_intensity_z"]
    for col in dim_cols:
        if col in tw_df.columns:
            tw_df[col] = tw_df.apply(lambda r: _apply_shrinkage(r, col), axis=1)

    # Step 6e: Data density label
    def _density(n):
        if n >= 10:
            return "high"
        elif n >= 5:
            return "med"
        elif n >= 2:
            return "low"
        else:
            return "league_prior"

    tw_df["data_density"] = tw_df["n_games_window"].map(_density)

    # Step 6f: Add season from game_id prefix (use game_date year as proxy)
    tw_df["season"] = tw_df["game_date"].dt.year.map(
        lambda y: f"{y-1}-{str(y)[-2:]}" if tw_df["game_date"].dt.month.iloc[0] < 7 else f"{y}-{str(y+1)[-2:]}"
    )
    # More accurate: derive from game_date month
    def _season(d):
        y, m = d.year, d.month
        if m >= 10:  # October start
            return f"{y}-{str(y+1)[-2:]}"
        else:
            return f"{y-1}-{str(y)[-2:]}"

    tw_df["season"] = tw_df["game_date"].map(_season)
    tw_df["game_date"] = tw_df["game_date"].dt.strftime("%Y-%m-%d")

    # Select output columns
    keep_cols = [
        "team_id", "season", "game_date", "n_games_window",
        "opp_contested_shot_rate_imposed_z",
        "opp_avg_defender_distance_imposed_z",
        "opp_paint_attempts_allowed_pct_z",
        "opp_pace_imposed_z",
        "opp_catch_shoot_allowed_pct_z",
        "opp_closeout_speed_imposed_z",
        "opp_defensive_intensity_z",
        "data_density",
    ]
    for col in keep_cols:
        if col not in tw_df.columns:
            tw_df[col] = np.nan

    return tw_df[keep_cols].sort_values(["team_id", "game_date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 7: Sanity checks and correlation with def_rtg
# ---------------------------------------------------------------------------

def _sanity_check(result: pd.DataFrame) -> dict:
    """
    Compute sanity metrics:
    - Top/bottom-10 composite z-scores
    - Correlation with NBA-API def_rtg
    Returns dict with findings.
    """
    findings = {}

    # Team-level aggregate composite_z (mean over all game-dates)
    team_agg = (
        result.groupby("team_id")["opp_defensive_intensity_z"]
        .agg(["mean", "std", "count"])
        .rename(columns={"mean": "composite_z_mean", "std": "composite_z_std", "count": "n_rows"})
        .sort_values("composite_z_mean", ascending=False)
    )
    findings["top_10"] = team_agg.head(10).reset_index().to_dict("records")
    findings["bottom_10"] = team_agg.tail(10).reset_index().to_dict("records")

    print("\n  Top-10 most intense defenses (composite_z):")
    for i, row in enumerate(findings["top_10"][:10]):
        print(f"    {i+1:2d}. {row['team_id']:4s}  mean_z={row['composite_z_mean']:+.3f}  n={row['n_rows']}")

    print("\n  Bottom-10 least intense defenses (composite_z):")
    for i, row in enumerate(findings["bottom_10"][:10]):
        print(f"    {i+1:2d}. {row['team_id']:4s}  mean_z={row['composite_z_mean']:+.3f}  n={row['n_rows']}")

    # Correlation with def_rtg from team_advanced_stats
    corr_val = np.nan
    if TEAM_ADV_STATS.exists():
        try:
            tas = pd.read_parquet(TEAM_ADV_STATS)
            tas["season_year"] = pd.to_datetime(tas["game_date"]).dt.year
            recent = tas[tas["season_year"] >= 2024]
            defrtg_agg = recent.groupby("team_tricode")["def_rtg"].mean().reset_index()
            defrtg_agg.columns = ["team_id", "def_rtg_mean"]

            merged = team_agg.reset_index().merge(defrtg_agg, on="team_id")
            if len(merged) >= 5:
                corr_val = merged["composite_z_mean"].corr(merged["def_rtg_mean"])
                print(f"\n  Correlation composite_z vs def_rtg: r = {corr_val:.3f}")
                if abs(corr_val) > 0.8:
                    print("  WARNING: |r| > 0.8 — atlas may just proxy def_rtg, REJECT signal.")
                    findings["verdict"] = f"REJECT: |r| = {corr_val:.3f} > 0.8 (proxies def_rtg)"
                elif abs(corr_val) < 0.3:
                    print("  NOTE: |r| < 0.3 — weak correlation; atlas captures independent signal.")
                    findings["verdict"] = f"INDEPENDENT: |r| = {corr_val:.3f} < 0.3"
                else:
                    print(f"  OK: |r| = {abs(corr_val):.3f} in target range [0.3, 0.8].")
                    findings["verdict"] = f"OK: |r| = {corr_val:.3f} in [-0.7, -0.3] target range"
            findings["corr_composite_vs_defrtg"] = float(corr_val) if not np.isnan(corr_val) else None
            findings["corr_n_teams"] = len(merged)
        except Exception as e:
            print(f"  [warn] could not compute def_rtg correlation: {e}")
            findings["corr_composite_vs_defrtg"] = None
    else:
        print("  [warn] team_advanced_stats.parquet not found; def_rtg correlation skipped")
        findings["corr_composite_vs_defrtg"] = None

    # Data density distribution
    dens_dist = result["data_density"].value_counts(normalize=True).to_dict()
    findings["density_distribution"] = {k: round(v * 100, 1) for k, v in dens_dist.items()}
    print("\n  Data density distribution:")
    for bucket, pct in sorted(dens_dist.items(), key=lambda x: -x[1]):
        print(f"    {bucket}: {pct*100:.1f}%")

    # Bug 35 closeout NULL rate
    closeout_null_rate = result["opp_closeout_speed_imposed_z"].isna().mean()
    findings["closeout_null_pct"] = round(closeout_null_rate * 100, 1)
    print(f"\n  Bug 35 — opp_closeout_speed_imposed_z NULL rate: {closeout_null_rate*100:.1f}%")

    # Expected teams in top quartile for 2024-25
    expected_top = {"BOS", "MIN", "OKC", "MIA"}
    top_teams = {r["team_id"] for r in findings["top_10"]}
    hits = expected_top & top_teams
    findings["expected_top_present"] = list(hits)
    print(f"\n  Expected elite defenses in top-10: {hits} / {expected_top}")

    return findings


# ---------------------------------------------------------------------------
# Public reader API: walk-forward safe
# ---------------------------------------------------------------------------

def get_opp_intensity(
    opp_team: str,
    game_date: str,
    parquet_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Fetch the most recent intensity row for opp_team with game_date STRICTLY
    less than the given game_date. Walk-forward safe.

    Args:
        opp_team: team tricode (e.g. "BOS")
        game_date: ISO date string "YYYY-MM-DD"
        parquet_path: path to opp_defensive_intensity.parquet (default: OUT_PARQUET)

    Returns:
        dict with all intensity columns, or None if no prior data exists.
    """
    if parquet_path is None:
        parquet_path = OUT_PARQUET
    if not Path(parquet_path).exists():
        return None

    df = pd.read_parquet(parquet_path)
    # Strict date < game_date (walk-forward safe)
    subset = df[(df["team_id"] == opp_team.upper()) & (df["game_date"] < game_date)]
    if subset.empty:
        return None
    return subset.sort_values("game_date").iloc[-1].to_dict()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="INT-52: Build opponent defensive intensity atlas (rolling z-scored)."
    )
    ap.add_argument("--window", type=int, default=5, help="Primary rolling window (default: 5 games)")
    ap.add_argument("--window-second", type=int, default=None,
                    help="Optional second window; adds _w<N>_ prefixed columns to same parquet")
    ap.add_argument("--report-only", action="store_true", help="Skip write; print stats only")
    args = ap.parse_args()

    print("\n=== INT-52 Opponent Defensive Intensity Atlas ===")

    # Load data
    print("\n--- Loading data sources ---")
    pid_to_team = _load_player_team_map()
    print(f"  player_id->team: {len(pid_to_team)} players")

    game_info = _load_game_info_map()
    print(f"  game_info map: {len(game_info)} games")

    wide = _load_cv_wide(DB_PATH)
    print(f"  cv_features wide: {len(wide)} player-game rows")

    wide = _assign_teams(wide, pid_to_team, game_info)
    game_level = _compute_raw_game_level(wide)
    print(f"  Game-level (defensive_team x game): {len(game_level)} rows, "
          f"{game_level['defensive_team'].nunique()} teams")

    # Primary window
    print(f"\n--- Rolling intensity (window={args.window}) ---")
    result = _compute_rolling_intensity(game_level, window=args.window)
    print(f"  Output rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")

    # Optional second window
    if args.window_second is not None and args.window_second != args.window:
        print(f"\n--- Rolling intensity (window={args.window_second}) ---")
        result2 = _compute_rolling_intensity(game_level, window=args.window_second)
        # Merge: add _w<N>_ prefixed columns to result
        dim_cols = [
            "opp_contested_shot_rate_imposed_z", "opp_avg_defender_distance_imposed_z",
            "opp_paint_attempts_allowed_pct_z", "opp_pace_imposed_z",
            "opp_catch_shoot_allowed_pct_z", "opp_closeout_speed_imposed_z",
            "opp_defensive_intensity_z",
        ]
        rename_map = {c: f"w{args.window_second}_{c}" for c in dim_cols}
        rename_map["n_games_window"] = f"n_games_window_w{args.window_second}"
        rename_map["data_density"] = f"data_density_w{args.window_second}"
        result2 = result2.rename(columns=rename_map)
        result = result.merge(
            result2[["team_id", "game_date"] + list(rename_map.values())],
            on=["team_id", "game_date"],
            how="left",
        )
        print(f"  Merged second window columns (w{args.window_second}_*)")

    # Sanity checks
    print("\n--- Sanity checks ---")
    findings = _sanity_check(result)

    # Write
    if not args.report_only:
        OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(OUT_PARQUET, index=False)
        print(f"\n  Saved: {OUT_PARQUET} ({len(result)} rows)")

    # Summary
    print("\n=== INT-52 COMPLETE ===")
    print(f"  Rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")
    print(f"  Closeout NULL rate: {findings['closeout_null_pct']}%")
    corr = findings.get('corr_composite_vs_defrtg')
    if corr is not None:
        print(f"  Correlation composite_z vs def_rtg: r = {corr:.3f}")
    print(f"  Verdict: {findings.get('verdict', 'N/A')}")

    return result, findings


if __name__ == "__main__":
    main()
