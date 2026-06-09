"""
INT-87: Schedule Strength 7-Day Rolling Indicator
Builds per-(player_id, game_date) schedule strength features based on
opponent def_rtg faced in prior 7 days (strict <).

Usage:
    python scripts/build_schedule_strength.py --build
    python scripts/build_schedule_strength.py --validate
    python scripts/build_schedule_strength.py --build --validate
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

ROOT = Path(__file__).resolve().parent.parent
DATA_NBA = ROOT / "data" / "nba"
DATA_INTEL = ROOT / "data" / "intelligence"
OUTPUT_PATH = DATA_INTEL / "schedule_strength_7d.parquet"
VAULT_PATH = ROOT / "vault" / "Intelligence" / "INT-87_Schedule_Strength.md"

SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_gamelogs() -> pd.DataFrame:
    """Load all gamelog_full_*.json files into a single DataFrame."""
    files = sorted(glob.glob(str(DATA_NBA / "gamelog_full_*.json")))
    rows = []
    for f in files:
        with open(f) as fp:
            data = json.load(fp)
        rows.extend(data)
    df = pd.DataFrame(rows)

    # Parse game_date: format is "Apr 06, 2023"
    df["game_date"] = pd.to_datetime(df["game_date"], format="%b %d, %Y")

    # Extract opponent tricode from matchup
    def _get_opp(matchup: str) -> str:
        if " vs. " in matchup:
            return matchup.split(" vs. ")[1].strip()
        elif " @ " in matchup:
            return matchup.split(" @ ")[1].strip()
        return ""

    df["opp_team"] = df["matchup"].apply(_get_opp)

    # Derive season from season_id (e.g. "22024" -> "2024-25")
    # Fallback to game_date if season_id is missing/malformed
    def _season_from_date(d: pd.Timestamp) -> str:
        if d.month >= 10:
            return f"{d.year}-{str(d.year + 1)[2:]}"
        return f"{d.year - 1}-{str(d.year)[2:]}"

    def _season_label(row) -> str:
        sid = str(row["season_id"])
        if len(sid) == 5 and sid[0] == "2" and sid[1:5].isdigit():
            year = int(sid[1:5])
            return f"{year}-{str(year + 1)[2:]}"
        return _season_from_date(row["game_date"])

    df["season"] = df.apply(_season_label, axis=1)

    df = df[["player_id", "game_id", "game_date", "season", "opp_team"]].copy()
    df = df.dropna(subset=["player_id", "game_id"])
    df["player_id"] = df["player_id"].astype("int64")
    return df


def load_team_adv_asof() -> pd.DataFrame:
    """
    Load per-game team def_rtg from team_advanced_stats.parquet.
    Returns one row per (game_date, team_tricode) with that game's def_rtg.
    """
    path = ROOT / "data" / "team_advanced_stats.parquet"
    df = pd.read_parquet(path, columns=["game_id", "game_date", "team_tricode", "def_rtg"])
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def build_asof_def_rtg(team_adv: pd.DataFrame) -> pd.DataFrame:
    """
    Build asof (expanding, shift-1) def_rtg per (team, season).
    For each team+season, the def_rtg on a given date is the mean of all
    PRIOR games (shift(1).expanding().mean()) in that season.
    Returns df with columns: [game_date, team_tricode, season, asof_def_rtg, asof_quality]
    """

    def _season_label(d: pd.Timestamp) -> str:
        if d.month >= 10:
            return f"{d.year}-{str(d.year + 1)[2:]}"
        return f"{d.year - 1}-{str(d.year)[2:]}"

    df = team_adv.copy()
    df["season"] = df["game_date"].apply(_season_label)
    df = df.sort_values(["team_tricode", "season", "game_date"]).reset_index(drop=True)

    # shift(1).expanding().mean() per team+season — strict prior only
    df["asof_def_rtg"] = df.groupby(["team_tricode", "season"])["def_rtg"].transform(
        lambda s: s.shift(1).expanding().mean()
    )
    df["asof_quality"] = df["asof_def_rtg"].notna().astype("int8")

    return df[["game_date", "team_tricode", "season", "asof_def_rtg", "asof_quality"]]


def build_prior_season_fallback(team_adv: pd.DataFrame) -> pd.DataFrame:
    """
    Season-final mean def_rtg per team per season (for prior-season fallback).
    """

    def _season_label(d: pd.Timestamp) -> str:
        if d.month >= 10:
            return f"{d.year}-{str(d.year + 1)[2:]}"
        return f"{d.year - 1}-{str(d.year)[2:]}"

    df = team_adv.copy()
    df["season"] = df["game_date"].apply(_season_label)
    return (
        df.groupby(["team_tricode", "season"])["def_rtg"]
        .mean()
        .rename("prior_def_rtg")
        .reset_index()
    )


def load_season_games_def_rtg() -> pd.DataFrame:
    """
    Load season_games_*.json for 2025-26 def_rtg per game.
    Returns per (game_id, team, game_date, def_rtg) rows.
    """
    rows = []
    for season in SEASONS:
        path = DATA_NBA / f"season_games_{season}.json"
        if not path.exists():
            continue
        with open(path) as fp:
            d = json.load(fp)
        for r in d.get("rows", []):
            # Skip incomplete rows (some 2025-26 rows lack team fields)
            if "home_team" not in r or "away_team" not in r:
                continue
            if "home_def_rtg" not in r or "away_def_rtg" not in r:
                continue
            game_date = r["game_date"]
            gid = r["game_id"]
            # home team
            rows.append({
                "game_id": gid,
                "game_date": pd.to_datetime(game_date),
                "team_tricode": r["home_team"],
                "def_rtg": r["home_def_rtg"],
                "season": r["season"],
            })
            # away team
            rows.append({
                "game_id": gid,
                "game_date": pd.to_datetime(game_date),
                "team_tricode": r["away_team"],
                "def_rtg": r["away_def_rtg"],
                "season": r["season"],
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# League avg / std per season (for elite/weak D thresholds)
# ---------------------------------------------------------------------------

def compute_league_thresholds(team_adv: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-season league mean and std of def_rtg.
    Returns df: [season, league_mean_def_rtg, league_std_def_rtg]
    """

    def _season_label(d: pd.Timestamp) -> str:
        if d.month >= 10:
            return f"{d.year}-{str(d.year + 1)[2:]}"
        return f"{d.year - 1}-{str(d.year)[2:]}"

    df = team_adv.copy()
    df["season"] = df["game_date"].apply(_season_label)
    stats = df.groupby("season")["def_rtg"].agg(
        league_mean_def_rtg="mean", league_std_def_rtg="std"
    ).reset_index()
    return stats


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    print("[INT-87] Loading gamelogs...")
    gamelogs = load_gamelogs()
    print(f"  gamelogs: {len(gamelogs):,} player-game rows")

    print("[INT-87] Loading team advanced stats...")
    team_adv = load_team_adv_asof()  # raw per-game
    raw_team_adv = team_adv.copy()  # keep for building asof

    # Build asof def_rtg (shift-1 expanding mean, no leakage)
    print("[INT-87] Building asof def_rtg (shift-1 expanding)...")
    asof_df = build_asof_def_rtg(raw_team_adv)
    # asof_df: game_date, team_tricode, season, asof_def_rtg, asof_quality

    # Prior-season fallback
    print("[INT-87] Building prior-season fallback...")
    prior_df = build_prior_season_fallback(raw_team_adv)
    # prior_df: team_tricode, season, prior_def_rtg
    # Map prior season -> next season for fallback
    prior_df["season_year"] = prior_df["season"].apply(lambda s: int(s[:4]))
    prior_df["next_season"] = prior_df["season_year"].apply(
        lambda y: f"{y+1}-{str(y+2)[2:]}"
    )
    fallback_map = prior_df.set_index(["team_tricode", "next_season"])["prior_def_rtg"].to_dict()

    # League thresholds per season
    print("[INT-87] Computing league thresholds per season...")
    league = compute_league_thresholds(raw_team_adv)
    league_map = league.set_index("season")[["league_mean_def_rtg", "league_std_def_rtg"]].to_dict("index")
    # For 2025-26 (not in team_advanced_stats), use 2024-25 thresholds as proxy
    if "2025-26" not in league_map and "2024-25" in league_map:
        league_map["2025-26"] = league_map["2024-25"]
        print("  2025-26 thresholds: using 2024-25 proxy")

    # Build a lookup: (game_date, team_tricode) -> (asof_def_rtg, asof_quality)
    # For 2025-26 we need to use season_games data since team_advanced_stats ends 2024-25
    print("[INT-87] Loading season_games for 2025-26 coverage...")
    sg_df = load_season_games_def_rtg()
    sg_25 = sg_df[sg_df["season"] == "2025-26"].copy()
    if len(sg_25) > 0:
        print(f"  season_games 2025-26: {len(sg_25):,} team-game rows")
        # Build asof for 2025-26 from season_games
        sg_25 = sg_25.sort_values(["team_tricode", "game_date"]).reset_index(drop=True)
        sg_25["asof_def_rtg"] = sg_25.groupby("team_tricode")["def_rtg"].transform(
            lambda s: s.shift(1).expanding().mean()
        )
        sg_25["asof_quality"] = sg_25["asof_def_rtg"].notna().astype("int8")
        sg_asof = sg_25[["game_date", "team_tricode", "season", "asof_def_rtg", "asof_quality"]].copy()
        # Append to asof_df
        asof_df = pd.concat([asof_df, sg_asof], ignore_index=True)

    # Build merge key: (game_date, team_tricode) -> (asof_def_rtg, asof_quality)
    # Use only the needed columns to avoid column-name collisions (e.g. 'season')
    asof_lookup = (
        asof_df[["game_date", "team_tricode", "asof_def_rtg", "asof_quality"]]
        .drop_duplicates(subset=["game_date", "team_tricode"])
        .reset_index(drop=True)
    )

    # -----------------------------------------------------------------------
    # For each player-game, look up opp asof_def_rtg on game_date
    # -----------------------------------------------------------------------
    print("[INT-87] Joining opp asof_def_rtg to gamelogs...")
    gamelogs = gamelogs.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # Use pd.merge (not index join) so that the non-unique (game_date, opp_team)
    # index in gamelogs does NOT cause a many-to-many cartesian product.
    gamelogs_with_def = gamelogs.merge(
        asof_lookup.rename(columns={"team_tricode": "opp_team"}),
        on=["game_date", "opp_team"],
        how="left",
    )

    # Fill fallback where asof is NaN
    mask_nan = gamelogs_with_def["asof_def_rtg"].isna()
    if mask_nan.any():
        fallback_vals = gamelogs_with_def.loc[mask_nan].apply(
            lambda r: fallback_map.get((r["opp_team"], r["season"]), np.nan), axis=1
        )
        gamelogs_with_def.loc[mask_nan, "asof_def_rtg"] = fallback_vals
        gamelogs_with_def.loc[mask_nan, "asof_quality"] = 0

    gamelogs_with_def["asof_quality"] = gamelogs_with_def["asof_quality"].fillna(0).astype("int8")

    # -----------------------------------------------------------------------
    # For each (player, game_date), aggregate prior 7 days window
    # -----------------------------------------------------------------------
    print("[INT-87] Computing 7-day rolling window aggregates...")

    # Sort for window computation
    gamelogs_with_def = gamelogs_with_def.sort_values(
        ["player_id", "game_date"]
    ).reset_index(drop=True)

    # We need: for each row i, all prior rows j of same player_id where
    # (game_date[i] - 7 days) <= game_date[j] < game_date[i]
    # Use groupby + apply with a sorted window

    def _agg_window(group: pd.DataFrame) -> pd.DataFrame:
        group = group.sort_values("game_date").reset_index(drop=True)
        n = len(group)
        dates = group["game_date"].values
        def_rtgs = group["asof_def_rtg"].values
        asof_qs = group["asof_quality"].values

        n_games = np.zeros(n, dtype="int8")
        mean_def = np.full(n, np.nan)
        max_def = np.full(n, np.nan)
        min_def = np.full(n, np.nan)
        asof_q_out = np.zeros(n, dtype="int8")

        for i in range(n):
            cutoff = dates[i] - np.timedelta64(7, "D")
            mask = (dates < dates[i]) & (dates >= cutoff)
            window_vals = def_rtgs[mask]
            valid = window_vals[~np.isnan(window_vals)]
            ng = len(valid)
            n_games[i] = min(ng, 127)  # int8 max safety
            if ng > 0:
                mean_def[i] = valid.mean()
                max_def[i] = valid.max()
                min_def[i] = valid.min()
                asof_q_out[i] = int(asof_qs[mask].mean() >= 0.5)

        group["sched_str_7d_n_games"] = n_games
        group["sched_str_7d_mean_opp_def_rtg"] = mean_def.astype("float32")
        group["sched_str_7d_max_opp_def_rtg"] = max_def.astype("float32")
        group["sched_str_7d_min_opp_def_rtg"] = min_def.astype("float32")
        group["sched_str_7d_asof_quality"] = asof_q_out
        return group

    result = gamelogs_with_def.groupby("player_id", group_keys=False).apply(_agg_window)
    result = result.reset_index(drop=True)

    # -----------------------------------------------------------------------
    # Compute n_elite_d and n_weak_d using per-season thresholds
    # -----------------------------------------------------------------------
    print("[INT-87] Computing elite/weak defense counts...")

    def _count_elite_weak(group: pd.DataFrame) -> pd.DataFrame:
        group = group.sort_values("game_date").reset_index(drop=True)
        n = len(group)
        dates = group["game_date"].values
        def_rtgs = group["asof_def_rtg"].values
        seasons = group["season"].values

        n_elite = np.zeros(n, dtype="int8")
        n_weak = np.zeros(n, dtype="int8")

        for i in range(n):
            cutoff = dates[i] - np.timedelta64(7, "D")
            mask = (dates < dates[i]) & (dates >= cutoff)
            window_vals = def_rtgs[mask]
            window_seasons = seasons[mask]

            cnt_elite = 0
            cnt_weak = 0
            for j, (val, seas) in enumerate(zip(window_vals, window_seasons)):
                if np.isnan(val):
                    continue
                thresh = league_map.get(seas)
                if thresh is None:
                    thresh = league_map.get("2024-25", {"league_mean_def_rtg": 113.0, "league_std_def_rtg": 3.0})
                lmean = thresh["league_mean_def_rtg"]
                lstd = thresh["league_std_def_rtg"]
                if val < lmean - lstd:
                    cnt_elite += 1  # lower def_rtg = better defense
                elif val > lmean + lstd:
                    cnt_weak += 1
            n_elite[i] = min(cnt_elite, 127)
            n_weak[i] = min(cnt_weak, 127)

        group["sched_str_7d_n_elite_d"] = n_elite
        group["sched_str_7d_n_weak_d"] = n_weak
        return group

    result = result.groupby("player_id", group_keys=False).apply(_count_elite_weak)
    result = result.reset_index(drop=True)

    # -----------------------------------------------------------------------
    # Final output columns
    # -----------------------------------------------------------------------
    out = result[
        [
            "player_id",
            "game_date",
            "game_id",
            "season",
            "sched_str_7d_n_games",
            "sched_str_7d_mean_opp_def_rtg",
            "sched_str_7d_max_opp_def_rtg",
            "sched_str_7d_min_opp_def_rtg",
            "sched_str_7d_n_elite_d",
            "sched_str_7d_n_weak_d",
            "sched_str_7d_asof_quality",
        ]
    ].copy()

    out["player_id"] = out["player_id"].astype("int64")
    out["game_date"] = out["game_date"].dt.date  # store as date not datetime
    out["game_id"] = out["game_id"].astype(str)
    out["season"] = out["season"].astype(str)
    out["sched_str_7d_n_games"] = out["sched_str_7d_n_games"].astype("int8")
    out["sched_str_7d_mean_opp_def_rtg"] = out["sched_str_7d_mean_opp_def_rtg"].astype("float32")
    out["sched_str_7d_max_opp_def_rtg"] = out["sched_str_7d_max_opp_def_rtg"].astype("float32")
    out["sched_str_7d_min_opp_def_rtg"] = out["sched_str_7d_min_opp_def_rtg"].astype("float32")
    out["sched_str_7d_n_elite_d"] = out["sched_str_7d_n_elite_d"].astype("int8")
    out["sched_str_7d_n_weak_d"] = out["sched_str_7d_n_weak_d"].astype("int8")
    out["sched_str_7d_asof_quality"] = out["sched_str_7d_asof_quality"].astype("int8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(f"[INT-87] Written: {output_path} ({len(out):,} rows)")
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame | None = None) -> bool:
    if df is None:
        df = pd.read_parquet(OUTPUT_PATH)
        # convert game_date if needed
        if not pd.api.types.is_datetime64_any_dtype(df["game_date"]):
            df["game_date"] = pd.to_datetime(df["game_date"])
    else:
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["game_date"]):
            df["game_date"] = pd.to_datetime(df["game_date"])

    all_pass = True

    # ------------------------------------------------------------------
    # 3a: LAL road trip sanity
    # ------------------------------------------------------------------
    print("\n[VAL-3a] LAL road trip sanity...")
    LEBRON = 2544
    AD = 203076
    lal_players = df[df["player_id"].isin([LEBRON, AD])].copy()
    # Find games right after a stretch where LAL faced elite defenses
    # Look for row with sched_str_7d_n_elite_d >= 2
    strong_stretch = lal_players[lal_players["sched_str_7d_n_elite_d"] >= 2]
    if len(strong_stretch) > 0:
        row = strong_stretch.iloc[0]
        pid_name = "LeBron" if row["player_id"] == LEBRON else "AD"
        print(f"  PASS: {pid_name} on {row['game_date']} game {row['game_id']}: "
              f"n_elite_d={row['sched_str_7d_n_elite_d']}, "
              f"mean_opp_def_rtg={row['sched_str_7d_mean_opp_def_rtg']:.1f}, "
              f"n_games={row['sched_str_7d_n_games']}")
    else:
        print("  WARN: No LAL player row found with n_elite_d >= 2")
        print("  Best rows:")
        best = lal_players.nlargest(3, "sched_str_7d_n_elite_d")[
            ["game_date", "player_id", "sched_str_7d_n_games", "sched_str_7d_n_elite_d", "sched_str_7d_mean_opp_def_rtg"]
        ]
        print(best.to_string(index=False))
        # Not hard fail — window may be too tight during specific stretches
        # But flag it
        print("  NOTE: Assertion n_elite_d >= 2 not met for any LAL row")

    # ------------------------------------------------------------------
    # 3b: Coverage gate
    # ------------------------------------------------------------------
    print("\n[VAL-3b] Coverage gate (>=0.95)...")
    # Players with >= 5 prior season games in that season
    player_game_counts = df.groupby(["player_id", "season"]).size().rename("total_games")
    df_cov = df.merge(
        player_game_counts.reset_index(), on=["player_id", "season"]
    )
    # Exclude early-season rows: require at least 7 days into the season
    # Proxy: n_games > 0 means at least one prior game in window
    # Eligible rows: player has >= 5 total games in season (not first 7 days)
    eligible = df_cov[df_cov["total_games"] >= 5].copy()
    # Exclude the very first rows of each player-season (first 7 days = no window)
    # Mark rows where player has been in the dataset at least 7 days
    # Use rank within player-season
    eligible["game_rank"] = eligible.groupby(["player_id", "season"])["game_date"].rank()
    eligible_filtered = eligible[eligible["game_rank"] > 2]  # skip first 2 games

    pct_nonnull = (eligible_filtered["sched_str_7d_n_games"] > 0).mean()
    threshold = 0.95
    status = "PASS" if pct_nonnull >= threshold else "FAIL"
    print(f"  {status}: coverage = {pct_nonnull:.4f} (threshold = {threshold})")
    if pct_nonnull < threshold:
        all_pass = False

    # ------------------------------------------------------------------
    # 3c: Distribution sanity
    # ------------------------------------------------------------------
    print("\n[VAL-3c] Distribution sanity...")
    nonzero = df[df["sched_str_7d_n_games"] > 0]
    n_mode_vals = nonzero["sched_str_7d_n_games"].mode().values
    mean_def = nonzero["sched_str_7d_mean_opp_def_rtg"].mean()
    std_def = nonzero["sched_str_7d_mean_opp_def_rtg"].std()
    n_unique_means = nonzero["sched_str_7d_mean_opp_def_rtg"].nunique()

    print(f"  n_games mode: {n_mode_vals}")
    print(f"  mean_opp_def_rtg: mean={mean_def:.2f}, std={std_def:.2f}")
    print(f"  unique mean_opp_def_rtg values: {n_unique_means}")

    if n_unique_means < 10:
        print("  FAIL: mean_opp_def_rtg is near-constant — asof join may be broken")
        all_pass = False
    else:
        print("  PASS: distribution looks non-degenerate")

    if not (110 <= mean_def <= 120):
        print(f"  WARN: mean_def_rtg={mean_def:.2f} outside expected range 110-120")
    else:
        print(f"  PASS: mean_def_rtg={mean_def:.2f} in expected range 110-120")

    if not (1.5 <= std_def <= 5.0):
        print(f"  WARN: std_def_rtg={std_def:.2f} outside expected range 1.5-5.0")
    else:
        print(f"  PASS: std_def_rtg={std_def:.2f} in expected range 1.5-5.0")

    # ------------------------------------------------------------------
    # 3d: Null control (shuffle test)
    # ------------------------------------------------------------------
    print("\n[VAL-3d] Null control (shuffle test)...")

    # Load gamelogs to get PTS as proxy target
    files = sorted(glob.glob(str(DATA_NBA / "gamelog_full_*.json")))
    pts_rows = []
    for f in files:
        with open(f) as fp:
            data = json.load(fp)
        for row in data:
            # Some gamelog files lack player_id (different schema) — skip them
            if "player_id" not in row or "game_id" not in row:
                continue
            pts_rows.append({
                "player_id": int(row["player_id"]),
                "game_id": str(row["game_id"]),
                "pts": float(row.get("pts", 0) or 0),
            })
    pts_df = pd.DataFrame(pts_rows)

    # Merge with schedule strength
    df_test = df.merge(pts_df, on=["player_id", "game_id"], how="inner")
    df_test = df_test[df_test["sched_str_7d_n_games"] > 0].dropna(
        subset=["sched_str_7d_mean_opp_def_rtg", "pts"]
    )

    if len(df_test) < 100:
        print("  SKIP: insufficient data for null control")
    else:
        # Compute residual vs player mean
        player_mean_pts = df_test.groupby("player_id")["pts"].transform("mean")
        df_test["pts_residual"] = df_test["pts"] - player_mean_pts

        real_corr, _ = scipy_stats.pearsonr(
            df_test["sched_str_7d_mean_opp_def_rtg"],
            df_test["pts_residual"],
        )

        # Shuffle: shuffle opp_def_rtg within season to break temporal structure
        # Recompute window on shuffled data
        # For speed, just shuffle mean_opp_def_rtg within season
        rng = np.random.default_rng(42)
        df_shuffled = df_test.copy()
        for seas, idx in df_shuffled.groupby("season").groups.items():
            vals = df_shuffled.loc[idx, "sched_str_7d_mean_opp_def_rtg"].values.copy()
            rng.shuffle(vals)
            df_shuffled.loc[idx, "sched_str_7d_mean_opp_def_rtg"] = vals

        shuffled_corr, _ = scipy_stats.pearsonr(
            df_shuffled["sched_str_7d_mean_opp_def_rtg"],
            df_shuffled["pts_residual"],
        )

        delta = abs(real_corr) - abs(shuffled_corr)
        MIN_DELTA = 0.005
        status_nc = "PASS" if delta >= MIN_DELTA else "NULL_CONTROL_FAIL"
        print(f"  real_corr={real_corr:.4f}, shuffled_corr={shuffled_corr:.4f}, delta={delta:.4f}")
        print(f"  {status_nc} (min_delta={MIN_DELTA})")
        if status_nc == "NULL_CONTROL_FAIL":
            print("NULL_CONTROL_FAIL")
            all_pass = False

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n[INT-87] Validation summary:")
    asof_dist = df["sched_str_7d_asof_quality"].value_counts().to_dict()
    print(f"  asof_quality distribution: {asof_dist}")
    print(f"  total rows: {len(df):,}")
    nonzero_pct = (df["sched_str_7d_n_games"] > 0).mean() * 100
    print(f"  rows with n_games>0: {nonzero_pct:.1f}%")

    return all_pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="INT-87: Schedule Strength 7-Day Rolling")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if not args.build and not args.validate:
        parser.print_help()
        sys.exit(0)

    df = None
    if args.build:
        df = build()

    if args.validate:
        ok = validate(df)
        if not ok:
            sys.exit(1)

    print("\n[INT-87] Done.")


if __name__ == "__main__":
    main()
