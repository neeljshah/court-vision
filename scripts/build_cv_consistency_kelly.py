"""build_cv_consistency_kelly.py — INT-55: CV Behavioral Consistency as Kelly Multiplier.

Measures within-player BEHAVIORAL stability of CV features. Orthogonal to:
  - INT-16 (per_player_confidence): outcome-level stat volatility
  - E1 (cv_coverage_gates): raw frame/game count coverage
  - INT-39 (cv_quality_per_game): tracking quality metrics (homography, jersey resolution)

This module asks: "Is this player behaving consistently frame-to-frame / game-to-game?"
High behavioral consistency -> higher CV in Kelly -> larger stake (up to 1.5×).
High behavioral INCONSISTENCY -> lower multiplier -> reduced stake (down to 0.5×).

Dimensions used (10 behavioral features):
  Role/Usage:   shots_per_possession, paint_dwell_pct, play_type_drive_pct,
                play_type_isolation_pct, play_type_post_pct, play_type_transition_pct,
                shot_zone_3pt_pct, shot_zone_mid_range_pct, shot_zone_paint_pct
  Behavioral:   avg_defender_distance, avg_spacing, contested_shot_rate,
                catch_shoot_pct, avg_dribble_count, possession_duration_avg,
                avg_shot_clock_at_shot

SKIPPED per recipe: avg_closeout_speed (Bug 35 sparse), n_shots_tracked,
  made_pct, second_chance_rate, potential_assists (target-leak risk)

Output schema (per player_id × asof_date):
  player_id (int), asof_date (str ISO), n_cv_games_in_window (int)
  cv_consistency_z (float), cv_consistency_mult (float)
  dim_<f>_cv, dim_<f>_z for each dimension f

Multiplier formula:
  cv_f = std/mean+ε   for unbounded features
  cv_f = MAD/median   for [0,1] pct features
  z-score cv_f across 30-day rolling population
  cv_consistency_raw = -mean(z_cv_f)  [negated: low CV = high consistency]
  winsorize 1/99%, z-score -> cv_consistency_z
  cv_consistency_mult = 1 + 0.5 * clip(cv_consistency_z, -1, +1)  -> [0.5, 1.5]

Outputs:
  data/intelligence/cv_consistency_kelly.parquet
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = ROOT / "data" / "nba_ai.db"
INT16_PATH = ROOT / "data" / "intelligence" / "per_player_confidence.parquet"
OUT_PATH = ROOT / "data" / "intelligence" / "cv_consistency_kelly.parquet"

# Dimensions to use per recipe
BOUNDED_DIMS = [
    "shots_per_possession",
    "paint_dwell_pct",
    "play_type_drive_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "play_type_transition_pct",
    "shot_zone_3pt_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_paint_pct",
    "contested_shot_rate",
    "catch_shoot_pct",
]

UNBOUNDED_DIMS = [
    "avg_defender_distance",
    "avg_spacing",
    "avg_dribble_count",
    "possession_duration_avg",
    "avg_shot_clock_at_shot",
]

ALL_DIMS = BOUNDED_DIMS + UNBOUNDED_DIMS
EPSILON = 1e-6

# Rolling window for within-player CV computation
N_WINDOW = 5    # primary
N_FALLBACK = 8  # fallback if <5 games available
MIN_GAMES = 3   # NULL if <3 games (variance unstable)

# Rolling population window for z-scoring
POP_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Helper: approximate game date from NBA game_id
# ---------------------------------------------------------------------------

def game_id_to_approx_date(game_id: str) -> Optional[date]:
    """Derive an approximate calendar date from an NBA standard game_id.

    Format: 002YYGGGGG where YY = last 2 digits of season start year,
    GGGGG = sequential game number within that season.

    Approximation uses linear interpolation over 175-day regular season.
    Accurate to ±7 days on average; sufficient for ordering and asof joins.
    """
    if not isinstance(game_id, str) or len(game_id) < 8:
        return None
    try:
        season_code = int(game_id[3:5])
        game_num = int(game_id[5:])
        if season_code == 24:
            season_start = date(2024, 10, 22)
        elif season_code == 25:
            season_start = date(2025, 10, 22)
        else:
            return None
        total_games = 1230
        days_offset = round(game_num / total_games * 175)
        return season_start + timedelta(days=days_offset)
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Load cv_features into wide format
# ---------------------------------------------------------------------------

def load_cv_features_wide() -> pd.DataFrame:
    """Load cv_features from nba_ai.db and pivot to wide format.

    Returns DataFrame: columns = [game_id, player_id, game_date, <dim_cols>]
    Only rows with at least 3 non-null dimensions are kept.
    """
    conn = sqlite3.connect(str(DB_PATH))
    raw = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()

    log.info("cv_features raw rows: %d", len(raw))

    # Pivot to wide
    wide = (
        raw[raw["feature_name"].isin(ALL_DIMS)]
        .pivot_table(
            index=["game_id", "player_id"],
            columns="feature_name",
            values="feature_value",
            aggfunc="mean",
        )
        .reset_index()
    )
    wide.columns.name = None

    # Ensure all dim columns present
    for col in ALL_DIMS:
        if col not in wide.columns:
            wide[col] = np.nan

    # Add approximate game date from game_id
    wide["game_date"] = wide["game_id"].map(game_id_to_approx_date)
    wide = wide.dropna(subset=["game_date"])
    wide["game_date"] = pd.to_datetime(wide["game_date"])

    # Drop rows with too few valid dims
    dim_valid = wide[ALL_DIMS].notna().sum(axis=1)
    wide = wide[dim_valid >= 3].copy()

    log.info(
        "cv_features wide: %d rows, %d players, %d games",
        len(wide),
        wide["player_id"].nunique(),
        wide["game_id"].nunique(),
    )
    return wide


# ---------------------------------------------------------------------------
# Per-player rolling CV computation
# ---------------------------------------------------------------------------

def _cv_for_dim(series: pd.Series, bounded: bool) -> float:
    """Compute coefficient of variation for a series of per-game values.

    bounded=True  -> MAD / (median + ε)
    bounded=False -> std  / (mean  + ε)
    """
    vals = series.dropna().values
    if len(vals) < 2:
        return np.nan
    if bounded:
        med = float(np.median(vals))
        mad = float(np.median(np.abs(vals - med)))
        return mad / (abs(med) + EPSILON)
    else:
        m = float(np.mean(vals))
        s = float(np.std(vals, ddof=1))
        return s / (abs(m) + EPSILON)


def build_per_player_cv_snapshots(wide: pd.DataFrame) -> pd.DataFrame:
    """For each (player_id, game) compute rolling CV over prior N games.

    Output: one row per (player_id, asof_date) with dim_<f>_cv columns.
    asof_date = date of the CURRENT game (the snapshot is from prior games).
    """
    rows: List[Dict] = []

    for player_id, grp in wide.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        n_total = len(grp)

        for i in range(n_total):
            current_game = grp.iloc[i]
            asof_date = current_game["game_date"]
            current_game_id = current_game["game_id"]

            # Use prior games only (strict shift(1))
            prior = grp.iloc[:i]  # all rows before index i

            if len(prior) == 0:
                continue

            # Determine window size
            n_avail = len(prior)
            if n_avail >= N_WINDOW:
                window = prior.tail(N_WINDOW)
            elif n_avail >= N_FALLBACK:
                window = prior.tail(N_FALLBACK)
            elif n_avail >= MIN_GAMES:
                window = prior
            else:
                # Not enough history
                continue

            # Leakage check: current game must not be in window
            assert current_game_id not in window["game_id"].values, (
                f"LEAKAGE: game {current_game_id} found in its own CV window "
                f"for player {player_id}"
            )

            row: Dict = {
                "player_id": int(player_id),
                "asof_date": asof_date.strftime("%Y-%m-%d"),
                "n_cv_games_in_window": len(window),
            }

            dim_cvs = []
            for dim in ALL_DIMS:
                if dim not in window.columns:
                    row[f"dim_{dim}_cv"] = np.nan
                    dim_cvs.append(np.nan)
                    continue
                bounded = dim in BOUNDED_DIMS
                cv_val = _cv_for_dim(window[dim], bounded=bounded)
                row[f"dim_{dim}_cv"] = cv_val
                dim_cvs.append(cv_val)

            rows.append(row)

    df = pd.DataFrame(rows)
    log.info("CV snapshots: %d rows, %d players", len(df), df["player_id"].nunique())
    return df


# ---------------------------------------------------------------------------
# Population z-scoring (rolling 30-day window)
# ---------------------------------------------------------------------------

def zscore_cv_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score each dim_<f>_cv across the rolling 30-day population.

    For each asof_date, we use all snapshots within [asof_date - 30d, asof_date].
    This avoids future look-ahead in the z-score normalization.
    """
    df = df.copy()
    df["asof_dt"] = pd.to_datetime(df["asof_date"])
    df = df.sort_values("asof_dt").reset_index(drop=True)

    dim_cv_cols = [f"dim_{d}_cv" for d in ALL_DIMS]
    dim_z_cols = [f"dim_{d}_z" for d in ALL_DIMS]

    # Pre-allocate z-score columns
    for col in dim_z_cols:
        df[col] = np.nan

    dates = df["asof_dt"].values
    asof_dts_ns = df["asof_dt"].astype(np.int64).values
    window_ns = POP_WINDOW_DAYS * 86400 * int(1e9)

    for idx in range(len(df)):
        current_ns = asof_dts_ns[idx]
        # Rolling population: all rows with asof_dt in [current - 30d, current]
        mask = (asof_dts_ns >= current_ns - window_ns) & (asof_dts_ns <= current_ns)
        pop = df.loc[mask]

        for cv_col, z_col in zip(dim_cv_cols, dim_z_cols):
            pop_vals = pop[cv_col].dropna().values
            if len(pop_vals) < 3:
                continue
            mu = np.mean(pop_vals)
            sigma = np.std(pop_vals, ddof=1)
            if sigma < EPSILON:
                df.at[idx, z_col] = 0.0
            else:
                df.at[idx, z_col] = (df.at[idx, cv_col] - mu) / sigma

    return df


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def build_composite(df: pd.DataFrame) -> pd.DataFrame:
    """Build cv_consistency_raw -> winsorize -> z-score -> multiplier."""
    df = df.copy()

    dim_z_cols = [f"dim_{d}_z" for d in ALL_DIMS]
    valid_z = df[dim_z_cols]

    # Mean of per-dim z-scores, negated: low CV (consistent) = high score
    df["cv_consistency_raw"] = -valid_z.mean(axis=1, skipna=True)

    # Winsorize 1/99%
    raw = df["cv_consistency_raw"].dropna()
    p1 = raw.quantile(0.01)
    p99 = raw.quantile(0.99)
    df["cv_consistency_raw_w"] = df["cv_consistency_raw"].clip(p1, p99)

    # Z-score across all rows
    mu = df["cv_consistency_raw_w"].mean()
    sigma = df["cv_consistency_raw_w"].std(ddof=1)
    if sigma < EPSILON:
        df["cv_consistency_z"] = 0.0
    else:
        df["cv_consistency_z"] = (df["cv_consistency_raw_w"] - mu) / sigma

    # Multiplier: 1 + 0.5 * clip(z, -1, +1) -> [0.5, 1.5]
    df["cv_consistency_mult"] = 1.0 + 0.5 * df["cv_consistency_z"].clip(-1.0, 1.0)

    # NaN multiplier -> 1.0 (neutral, no signal)
    df["cv_consistency_mult"] = df["cv_consistency_mult"].fillna(1.0)
    df["cv_consistency_z"] = df["cv_consistency_z"].fillna(np.nan)

    return df


# ---------------------------------------------------------------------------
# Colinearity check with INT-16
# ---------------------------------------------------------------------------

def run_colinearity_check(df: pd.DataFrame) -> Dict[str, float]:
    """Compute correlations with INT-16 overall_confidence_mult and n_cv_games.

    Returns dict: {corr_int16: float, corr_n_games: float}
    """
    results: Dict[str, float] = {}

    # Correlation with n_cv_games_in_window
    mask = df["cv_consistency_z"].notna() & df["n_cv_games_in_window"].notna()
    if mask.sum() > 10:
        r_ngames, _ = scipy_stats.pearsonr(
            df.loc[mask, "cv_consistency_z"].values,
            df.loc[mask, "n_cv_games_in_window"].values,
        )
        results["corr_n_games"] = float(r_ngames)
    else:
        results["corr_n_games"] = np.nan

    # Correlation with INT-16 overall_confidence_mult
    # Merge on player_id (INT-16 is player-level, not per-game)
    if INT16_PATH.exists():
        int16 = pd.read_parquet(INT16_PATH)[["player_id", "overall_confidence_mult"]]
        merged = df[["player_id", "cv_consistency_z"]].dropna().merge(int16, on="player_id", how="inner")
        if len(merged) > 10:
            r_int16, _ = scipy_stats.pearsonr(
                merged["cv_consistency_z"].values,
                merged["overall_confidence_mult"].values,
            )
            results["corr_int16"] = float(r_int16)
        else:
            results["corr_int16"] = np.nan
            log.warning("Too few INT-16 overlapping players for correlation check")
    else:
        results["corr_int16"] = np.nan
        log.warning("INT-16 parquet not found; skipping INT-16 correlation")

    return results


# ---------------------------------------------------------------------------
# Residualization (if colinearity with INT-16 exceeds 0.4)
# ---------------------------------------------------------------------------

def residualize_against_int16(df: pd.DataFrame, corr_int16: float) -> pd.DataFrame:
    """If |corr_int16| >= 0.4, regress out INT-16 component from cv_consistency_z."""
    if abs(corr_int16) < 0.4 or not INT16_PATH.exists():
        return df

    log.warning(
        "Colinearity with INT-16 |rho|=%.3f >= 0.4; shipping E2 as residual",
        abs(corr_int16),
    )
    int16 = pd.read_parquet(INT16_PATH)[["player_id", "overall_confidence_mult"]]
    df = df.merge(int16, on="player_id", how="left")

    valid = df["cv_consistency_z"].notna() & df["overall_confidence_mult"].notna()
    if valid.sum() > 10:
        x = df.loc[valid, "overall_confidence_mult"].values.reshape(-1, 1)
        y = df.loc[valid, "cv_consistency_z"].values
        from numpy.linalg import lstsq
        beta, _, _, _ = lstsq(
            np.hstack([x, np.ones((len(x), 1))]), y, rcond=None
        )
        # Store residual back
        df.loc[valid, "cv_consistency_z"] = y - (x[:, 0] * beta[0] + beta[1])
        df["cv_consistency_z_residual"] = True
        # Recompute multiplier from residual z
        df["cv_consistency_mult"] = 1.0 + 0.5 * df["cv_consistency_z"].clip(-1.0, 1.0)
        df["cv_consistency_mult"] = df["cv_consistency_mult"].fillna(1.0)
        log.info("Residualized cv_consistency_z; beta_int16=%.4f", beta[0])
    else:
        log.warning("Not enough valid rows to residualize; shipping raw z")

    if "overall_confidence_mult" in df.columns:
        df = df.drop(columns=["overall_confidence_mult"])
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== INT-55: Build CV Consistency Kelly Multiplier ===")

    # 1. Load wide cv_features
    wide = load_cv_features_wide()
    if wide.empty:
        log.error("No cv_features data found. Aborting.")
        sys.exit(1)

    # 2. Per-player rolling CV snapshots
    snap = build_per_player_cv_snapshots(wide)
    if snap.empty:
        log.error("No CV snapshots generated (insufficient data). Aborting.")
        sys.exit(1)

    # 3. Z-score per dimension across population
    log.info("Z-scoring per-dim CV values across rolling population...")
    snap = zscore_cv_snapshots(snap)

    # 4. Build composite score + multiplier
    snap = build_composite(snap)

    # 5. Colinearity check
    log.info("Running colinearity checks...")
    corr = run_colinearity_check(snap)
    log.info(
        "Colinearity: corr_int16=%.3f  corr_n_games=%.3f",
        corr.get("corr_int16", float("nan")),
        corr.get("corr_n_games", float("nan")),
    )

    # 6. Residualize if needed
    corr_int16 = corr.get("corr_int16", 0.0) or 0.0
    snap = residualize_against_int16(snap, corr_int16)

    # 7. Final column selection
    keep_cols = (
        ["player_id", "asof_date", "n_cv_games_in_window",
         "cv_consistency_z", "cv_consistency_mult"]
        + [f"dim_{d}_cv" for d in ALL_DIMS]
        + [f"dim_{d}_z" for d in ALL_DIMS]
    )
    if "cv_consistency_z_residual" in snap.columns:
        keep_cols.append("cv_consistency_z_residual")
    if "asof_dt" in snap.columns:
        snap = snap.drop(columns=["asof_dt"])

    final = snap[[c for c in keep_cols if c in snap.columns]].copy()

    # 8. Stats
    n_rows = len(final)
    n_players = final["player_id"].nunique()
    z_valid = final["cv_consistency_z"].notna().sum()
    mult_stats = final["cv_consistency_mult"].describe()

    log.info("Output: %d rows, %d players, %d with non-null z", n_rows, n_players, z_valid)
    log.info(
        "Multiplier range [%.3f, %.3f], mean=%.3f",
        mult_stats["min"],
        mult_stats["max"],
        mult_stats["mean"],
    )
    log.info(
        "Colinearity summary: corr_int16=%.3f, corr_n_games=%.3f",
        corr.get("corr_int16", float("nan")),
        corr.get("corr_n_games", float("nan")),
    )

    # 9. Write output
    out_dir = OUT_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    final.to_parquet(str(OUT_PATH), index=False)
    log.info("Wrote %s", OUT_PATH)

    # Summary for eval
    print("\n=== BUILD SUMMARY ===")
    print(f"Rows:       {n_rows}")
    print(f"Players:    {n_players}")
    print(f"Valid z:    {z_valid} ({z_valid/max(n_rows,1)*100:.1f}%)")
    print(f"Mult range: [{mult_stats['min']:.3f}, {mult_stats['max']:.3f}]")
    print(f"Mult mean:  {mult_stats['mean']:.3f}")
    print(f"corr_int16:  {corr.get('corr_int16', 'N/A')}")
    print(f"corr_n_games:{corr.get('corr_n_games', 'N/A')}")


if __name__ == "__main__":
    main()
