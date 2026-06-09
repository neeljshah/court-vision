"""
audit_per_game_anomalies.py — Per-game CV artifact detector.

For each game in cv_features DB, computes per-player z-scores against that player's
other games (for paint_dwell_pct, avg_defender_distance, avg_spacing, shot_zone_paint_pct).
Flags games where >50% of tracked players have z-scores > 3 simultaneously —
indicating a game-level pipeline artifact rather than a player-level anomaly.

Output: vault/Intelligence/_per_game_anomalies_audit.txt

Usage:
    python scripts/audit_per_game_anomalies.py
    python scripts/audit_per_game_anomalies.py --threshold 0.5 --z 3.0
    python scripts/audit_per_game_anomalies.py --features paint_dwell_pct avg_spacing
    python scripts/audit_per_game_anomalies.py --min-players 3
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "nba_ai.db"
OUT_DIR = REPO_ROOT / "vault" / "Intelligence"
OUT_FILE = OUT_DIR / "_per_game_anomalies_audit.txt"

DEFAULT_FEATURES = [
    "paint_dwell_pct",
    "avg_defender_distance",
    "avg_spacing",
    "shot_zone_paint_pct",
]
DEFAULT_Z_THRESHOLD = 3.0
DEFAULT_GAME_FRACTION_THRESHOLD = 0.50   # >50% players anomalous → game artifact
DEFAULT_MIN_PLAYERS = 2                   # skip games with fewer tracked players


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def _load_cv_features(db_path: Path, features: list[str]) -> pd.DataFrame:
    """Return long-form cv_features for the requested feature names."""
    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" * len(features))
    df = pd.read_sql(
        f"""
        SELECT game_id, player_id, feature_name, feature_value
        FROM cv_features
        WHERE feature_name IN ({placeholders})
        """,
        conn,
        params=features,
    )
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------
def compute_per_player_zscores(
    df: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    """
    For each (player_id, feature_name) pair, compute a z-score for every game
    using the player's OTHER games as the baseline distribution.

    Returns a DataFrame with columns:
        game_id, player_id, feature_name, feature_value,
        baseline_mean, baseline_std, z_score, n_baseline_games
    """
    records = []
    for (pid, feat), grp in df.groupby(["player_id", "feature_name"]):
        grp = grp.reset_index(drop=True)
        vals = grp["feature_value"].values
        game_ids = grp["game_id"].values

        if len(grp) < 2:
            # Need at least one baseline game
            for i, row in grp.iterrows():
                records.append({
                    "game_id": game_ids[i],
                    "player_id": pid,
                    "feature_name": feat,
                    "feature_value": vals[i],
                    "baseline_mean": np.nan,
                    "baseline_std": np.nan,
                    "z_score": np.nan,
                    "n_baseline_games": 0,
                })
            continue

        for i in range(len(grp)):
            other_vals = np.delete(vals, i)
            bmean = float(np.mean(other_vals))
            bstd = float(np.std(other_vals, ddof=1)) if len(other_vals) > 1 else 0.0

            if bstd < 1e-9:
                # All other games identical — z is 0 if same, inf if different
                z = 0.0 if abs(vals[i] - bmean) < 1e-9 else np.inf
            else:
                z = float((vals[i] - bmean) / bstd)

            records.append({
                "game_id": game_ids[i],
                "player_id": pid,
                "feature_name": feat,
                "feature_value": float(vals[i]),
                "baseline_mean": bmean,
                "baseline_std": bstd,
                "z_score": z,
                "n_baseline_games": len(other_vals),
            })

    return pd.DataFrame(records)


def flag_game_artifacts(
    z_df: pd.DataFrame,
    z_threshold: float,
    game_fraction_threshold: float,
    min_players: int,
) -> pd.DataFrame:
    """
    Aggregate z-scores to the game level. Flag games where >game_fraction_threshold
    of tracked players have at least one |z| > z_threshold.

    Returns one row per game with columns:
        game_id, n_players, n_players_anomalous, pct_anomalous,
        anomalous_features_summary, is_game_artifact
    """
    # Drop rows with no baseline
    valid = z_df.dropna(subset=["z_score"])

    # Per-player-game: is this player anomalous (any feature z > threshold)?
    per_player_game = (
        valid[np.abs(valid["z_score"]) > z_threshold]
        .groupby(["game_id", "player_id"])["feature_name"]
        .apply(list)
        .reset_index()
        .rename(columns={"feature_name": "anomalous_features"})
    )

    # Count total tracked players per game
    total_per_game = (
        valid.groupby("game_id")["player_id"].nunique().reset_index()
        .rename(columns={"player_id": "n_players"})
    )

    # Count anomalous players per game
    anom_per_game = (
        per_player_game.groupby("game_id")["player_id"].nunique().reset_index()
        .rename(columns={"player_id": "n_players_anomalous"})
    )

    # Build feature summary per game: which features triggered how many players
    feat_summary = (
        per_player_game.assign(
            feat_str=lambda d: d["anomalous_features"].apply(
                lambda fl: ",".join(sorted(set(fl)))
            )
        )
        .groupby(["game_id", "feat_str"])
        .size()
        .reset_index(name="n_players_flagged_by_feat")
    )
    feat_summary_agg = (
        feat_summary.groupby("game_id")
        .apply(
            lambda g: "; ".join(
                f"{row.feat_str}(n={row.n_players_flagged_by_feat})"
                for _, row in g.iterrows()
            )
        )
        .reset_index(name="anomalous_features_summary")
    )

    result = (
        total_per_game
        .merge(anom_per_game, on="game_id", how="left")
        .merge(feat_summary_agg, on="game_id", how="left")
    )
    result["n_players_anomalous"] = result["n_players_anomalous"].fillna(0).astype(int)
    result["anomalous_features_summary"] = result["anomalous_features_summary"].fillna("")
    result["pct_anomalous"] = result["n_players_anomalous"] / result["n_players"]

    result["is_game_artifact"] = (
        (result["pct_anomalous"] > game_fraction_threshold)
        & (result["n_players"] >= min_players)
    )

    return result.sort_values("pct_anomalous", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def write_report(
    game_flags: pd.DataFrame,
    z_df: pd.DataFrame,
    features: list[str],
    z_threshold: float,
    game_fraction_threshold: float,
    min_players: int,
    out_path: Path,
) -> None:
    artifacts = game_flags[game_flags["is_game_artifact"]]
    lines = []
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Per-Game CV Anomaly Audit — {ts}")
    lines.append("")
    lines.append("## Parameters")
    lines.append(f"  features        : {features}")
    lines.append(f"  z_threshold     : {z_threshold}")
    lines.append(f"  game_fraction   : >{game_fraction_threshold:.0%} players anomalous")
    lines.append(f"  min_players     : {min_players}")
    lines.append(f"  total games     : {game_flags['game_id'].nunique()}")
    lines.append(f"  game artifacts  : {len(artifacts)}")
    lines.append("")

    lines.append("## GAME-LEVEL ARTIFACTS (>50% players with |z| > threshold)")
    lines.append("=" * 70)
    if len(artifacts) == 0:
        lines.append("  None detected.")
    else:
        for _, row in artifacts.iterrows():
            lines.append(
                f"  {row['game_id']}  {row['n_players_anomalous']}/{row['n_players']} players "
                f"({row['pct_anomalous']:.0%}) | {row['anomalous_features_summary']}"
            )
    lines.append("")

    lines.append("## TOP GAMES BY PCT ANOMALOUS PLAYERS (all games, sorted)")
    lines.append("-" * 70)
    for _, row in game_flags.head(30).iterrows():
        flag = " *** ARTIFACT" if row["is_game_artifact"] else ""
        lines.append(
            f"  {row['game_id']}  {row['n_players_anomalous']:2d}/{row['n_players']:2d} "
            f"({row['pct_anomalous']:.0%}){flag}"
        )
        if row["anomalous_features_summary"]:
            lines.append(f"    → {row['anomalous_features_summary']}")
    lines.append("")

    lines.append("## PER-PLAYER EXTREME ANOMALIES (|z| > 10)")
    lines.append("-" * 70)
    extreme = z_df[z_df["z_score"].abs() > 10].sort_values("z_score", key=abs, ascending=False)
    if len(extreme) == 0:
        lines.append("  None.")
    else:
        for _, row in extreme.head(30).iterrows():
            lines.append(
                f"  game={row['game_id']}  player={row['player_id']}  "
                f"{row['feature_name']}={row['feature_value']:.4f}  "
                f"z={row['z_score']:.1f}  baseline_mean={row['baseline_mean']:.4f}"
            )
    lines.append("")
    lines.append("## USAGE")
    lines.append("  python scripts/audit_per_game_anomalies.py")
    lines.append("  python scripts/audit_per_game_anomalies.py --z 4 --threshold 0.6")
    lines.append("  python scripts/audit_per_game_anomalies.py --features paint_dwell_pct avg_spacing")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit per-game CV anomalies.")
    parser.add_argument(
        "--features",
        nargs="+",
        default=DEFAULT_FEATURES,
        help="CV feature names to evaluate (default: paint_dwell_pct avg_defender_distance avg_spacing shot_zone_paint_pct)",
    )
    parser.add_argument(
        "--z",
        type=float,
        default=DEFAULT_Z_THRESHOLD,
        dest="z_threshold",
        help=f"Z-score threshold (default: {DEFAULT_Z_THRESHOLD})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_GAME_FRACTION_THRESHOLD,
        dest="game_fraction_threshold",
        help=f"Fraction of players anomalous to flag a game (default: {DEFAULT_GAME_FRACTION_THRESHOLD})",
    )
    parser.add_argument(
        "--min-players",
        type=int,
        default=DEFAULT_MIN_PLAYERS,
        dest="min_players",
        help=f"Minimum tracked players in a game (default: {DEFAULT_MIN_PLAYERS})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to nba_ai.db (default: {DB_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Loading cv_features from {args.db} ...")
    df = _load_cv_features(args.db, args.features)
    if df.empty:
        print("No data found. Check DB path and feature names.")
        return

    print(
        f"Loaded {len(df):,} rows  |  "
        f"{df['game_id'].nunique()} games  |  "
        f"{df['player_id'].nunique()} players  |  "
        f"{df['feature_name'].nunique()} features"
    )

    print("Computing per-player z-scores (leave-one-out) ...")
    z_df = compute_per_player_zscores(df, args.features)

    print("Flagging game-level artifacts ...")
    game_flags = flag_game_artifacts(
        z_df,
        z_threshold=args.z_threshold,
        game_fraction_threshold=args.game_fraction_threshold,
        min_players=args.min_players,
    )

    artifacts = game_flags[game_flags["is_game_artifact"]]
    print(f"\nFound {len(artifacts)} game-level artifacts (>{args.game_fraction_threshold:.0%} players with |z|>{args.z_threshold}):")
    for _, row in artifacts.iterrows():
        print(
            f"  {row['game_id']}  {row['n_players_anomalous']}/{row['n_players']} players  "
            f"{row['pct_anomalous']:.0%}  | {row['anomalous_features_summary']}"
        )

    write_report(
        game_flags,
        z_df,
        features=args.features,
        z_threshold=args.z_threshold,
        game_fraction_threshold=args.game_fraction_threshold,
        min_players=args.min_players,
        out_path=OUT_FILE,
    )


if __name__ == "__main__":
    main()
