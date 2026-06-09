"""
INT-39: CV-Quality-Aware Confidence
Builds per-(player_slot, game) CV tracking quality scores, aggregates per player,
and produces quality-adjusted Kelly multipliers by combining with INT-16 statistical confidence.

Outputs:
  data/intelligence/cv_quality_per_game.parquet
  data/intelligence/cv_quality_confidence_curves.json
  vault/Intelligence/CV_Quality_Confidence_Atlas.md
"""

import pandas as pd
import numpy as np
import glob
import os
import json
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = "C:/Users/neelj/nba-ai-system"
TRACKING_DIR = f"{ROOT}/data/tracking"
INTELLIGENCE_DIR = f"{ROOT}/data/intelligence"
VAULT_DIR = f"{ROOT}/vault/Intelligence"
INT16_PATH = f"{INTELLIGENCE_DIR}/per_player_confidence.parquet"
CV_PER_GAME_PATH = f"{ROOT}/data/player_cv_per_game.parquet"
OUT_PARQUET = f"{INTELLIGENCE_DIR}/cv_quality_per_game.parquet"
OUT_JSON = f"{INTELLIGENCE_DIR}/cv_quality_confidence_curves.json"
OUT_ATLAS = f"{VAULT_DIR}/CV_Quality_Confidence_Atlas.md"

# ── Quality score weights ─────────────────────────────────────────────────────
W_HOMOG = 0.4
W_JERSEY = 0.2
W_FRAMES = 0.2
W_PHANTOM = 0.2
FRAMES_THRESHOLD = 1000          # frames above this → full score
PHANTOM_STD_THRESHOLD = 50.0    # x_position std below this → phantom slot

# ── Quality buckets ───────────────────────────────────────────────────────────
HIGH_QUALITY = 0.7
LOW_QUALITY = 0.4


def load_tracking_games():
    """Return list of (game_id, path) for all tracking_data.csv files."""
    paths = glob.glob(f"{TRACKING_DIR}/*/tracking_data.csv")
    return [(os.path.basename(os.path.dirname(p)), p) for p in sorted(paths)]


def compute_game_player_quality(df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """
    For each player slot in a game's tracking_data.csv, compute the 5 quality
    indicators and composite quality_score.
    Returns a DataFrame with one row per (game_id, player_slot).
    """
    records = []
    slots = df["player_id"].unique()

    # Game-level: total unique frames is our 'game duration'
    n_total_frames = df["frame"].nunique()

    for slot in sorted(slots):
        pdf = df[df["player_id"] == slot]

        # --- 1. homography_valid_rate ---
        homography_valid_rate = float(pdf["homography_valid"].mean()) if "homography_valid" in pdf.columns else 0.0

        # --- 2. jersey_resolution_rate ---
        # jersey_number not-null means jersey was resolved for that frame
        if "jersey_number" in pdf.columns:
            jersey_resolution_rate = float(pdf["jersey_number"].notna().mean())
        else:
            jersey_resolution_rate = 0.0

        # --- 3. frame_count ---
        frame_count = int(len(pdf))

        # --- 4. phantom_slot_flag ---
        if "x_position" in pdf.columns and len(pdf) > 1:
            x_std = float(pdf["x_position"].std())
            phantom_slot_flag = bool(x_std < PHANTOM_STD_THRESHOLD)
        else:
            phantom_slot_flag = True  # can't tell → treat as phantom

        # --- 5. tracking_density ---
        tracking_density = float(frame_count / n_total_frames) if n_total_frames > 0 else 0.0

        # --- Player name (best available) ---
        if "player_name" in pdf.columns:
            name_counts = pdf["player_name"].dropna().value_counts()
            if len(name_counts) > 0:
                player_name = name_counts.index[0]
            else:
                player_name = f"slot_{slot}"
        else:
            player_name = f"slot_{slot}"

        # --- Composite quality score ---
        frames_score = min(1.0, frame_count / FRAMES_THRESHOLD)
        phantom_score = 0.0 if phantom_slot_flag else 1.0

        quality_score = (
            W_HOMOG * homography_valid_rate
            + W_JERSEY * jersey_resolution_rate
            + W_FRAMES * frames_score
            + W_PHANTOM * phantom_score
        )
        quality_score = float(np.clip(quality_score, 0.0, 1.0))

        # Skip slots with NaN player_id (can happen in malformed data)
        try:
            slot_int = int(slot)
        except (ValueError, TypeError):
            continue

        records.append({
            "game_id": game_id,
            "player_slot": slot_int,
            "player_name": player_name,
            "homography_valid_rate": round(homography_valid_rate, 4),
            "jersey_resolution_rate": round(jersey_resolution_rate, 4),
            "frame_count": frame_count,
            "phantom_slot_flag": phantom_slot_flag,
            "tracking_density": round(tracking_density, 4),
            "quality_score": round(quality_score, 4),
        })

    return pd.DataFrame(records)


def attach_nba_player_ids(quality_df: pd.DataFrame, cv_per_game: pd.DataFrame) -> pd.DataFrame:
    """
    Merge nba_player_id from player_cv_per_game.parquet onto quality_df
    using (game_id, player_slot).
    """
    if cv_per_game is None or len(cv_per_game) == 0:
        quality_df["nba_player_id"] = pd.NA
        return quality_df

    # Normalise types
    cv_lookup = cv_per_game[["game_id", "player_id", "nba_player_id", "player_name"]].copy()
    cv_lookup.columns = ["game_id", "player_slot", "nba_player_id", "cv_player_name"]
    cv_lookup["game_id"] = cv_lookup["game_id"].astype(str)
    cv_lookup["player_slot"] = cv_lookup["player_slot"].astype(int)

    quality_df["game_id"] = quality_df["game_id"].astype(str)
    quality_df["player_slot"] = quality_df["player_slot"].astype(int)

    merged = quality_df.merge(cv_lookup, on=["game_id", "player_slot"], how="left")

    # Use cv_player_name to fill in when tracking_data has only color#?
    has_placeholder = merged["player_name"].str.contains("#", na=True)
    merged.loc[has_placeholder & merged["cv_player_name"].notna(), "player_name"] = \
        merged.loc[has_placeholder & merged["cv_player_name"].notna(), "cv_player_name"]

    merged.drop(columns=["cv_player_name"], inplace=True)
    return merged


def aggregate_per_player(quality_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each nba_player_id (where available), aggregate quality across games.
    Returns per-player summary DataFrame.
    """
    has_id = quality_df[quality_df["nba_player_id"].notna()].copy()
    has_id["nba_player_id"] = has_id["nba_player_id"].astype(int)

    if len(has_id) == 0:
        return pd.DataFrame()

    agg = has_id.groupby("nba_player_id").agg(
        player_name=("player_name", lambda x: x.mode()[0] if len(x) > 0 else "unknown"),
        n_games=("game_id", "nunique"),
        mean_quality=("quality_score", "mean"),
        min_quality=("quality_score", "min"),
        max_quality=("quality_score", "max"),
        std_quality=("quality_score", "std"),
        n_high_quality_games=("quality_score", lambda x: (x > HIGH_QUALITY).sum()),
        n_low_quality_games=("quality_score", lambda x: (x < LOW_QUALITY).sum()),
        mean_homography_rate=("homography_valid_rate", "mean"),
        mean_jersey_rate=("jersey_resolution_rate", "mean"),
        mean_frame_count=("frame_count", "mean"),
        phantom_flag_rate=("phantom_slot_flag", "mean"),
    ).reset_index()

    agg["mean_quality"] = agg["mean_quality"].round(4)
    agg["min_quality"] = agg["min_quality"].round(4)
    agg["max_quality"] = agg["max_quality"].round(4)
    agg["std_quality"] = agg["std_quality"].fillna(0.0).round(4)
    return agg.sort_values("mean_quality", ascending=False)


def compute_quality_adjusted_kelly(
    player_agg: pd.DataFrame, int16: pd.DataFrame
) -> pd.DataFrame:
    """
    For each player with both INT-16 and INT-39 data, compute:
      adjusted_<stat>_mult = INT-16_<stat>_mult × (0.5 + 0.5 × player_avg_quality)
    """
    if len(player_agg) == 0 or len(int16) == 0:
        return pd.DataFrame()

    joined = player_agg.merge(
        int16[["player_id", "player_name",
               "pts_confidence_mult", "reb_confidence_mult", "ast_confidence_mult",
               "fg3m_confidence_mult", "stl_confidence_mult", "blk_confidence_mult",
               "tov_confidence_mult", "overall_confidence_mult"]],
        left_on="nba_player_id",
        right_on="player_id",
        how="inner",
        suffixes=("_cv", "_int16"),
    )

    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        col = f"{stat}_confidence_mult"
        joined[f"adj_{stat}_mult"] = (
            joined[col] * (0.5 + 0.5 * joined["mean_quality"])
        ).round(4)

    joined["adj_overall_mult"] = (
        joined["overall_confidence_mult"] * (0.5 + 0.5 * joined["mean_quality"])
    ).round(4)

    return joined


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[INT-39] Starting CV-Quality-Aware Confidence build — {datetime.now():%Y-%m-%d %H:%M}")

    # ── Load helper tables ────────────────────────────────────────────────────
    int16 = pd.read_parquet(INT16_PATH)
    print(f"  INT-16 players loaded: {len(int16)}")

    try:
        cv_per_game = pd.read_parquet(CV_PER_GAME_PATH)
        cv_per_game["game_id"] = cv_per_game["game_id"].astype(str)
        print(f"  player_cv_per_game loaded: {len(cv_per_game)} rows, "
              f"{cv_per_game['game_id'].nunique()} games")
    except Exception as e:
        print(f"  WARNING: Could not load player_cv_per_game.parquet: {e}")
        cv_per_game = None

    # ── Step 1: Per-(player_slot, game) quality ───────────────────────────────
    tracking_games = load_tracking_games()
    print(f"\n[Step 1] Computing quality for {len(tracking_games)} games...")

    all_quality = []
    errors = 0
    for i, (game_id, path) in enumerate(tracking_games, 1):
        if i % 50 == 0:
            print(f"  ... {i}/{len(tracking_games)} games processed")
        try:
            df = pd.read_csv(path, low_memory=False,
                             usecols=["frame", "player_id", "player_name",
                                      "x_position", "homography_valid", "jersey_number"])
            if len(df) == 0:
                continue
            game_quality = compute_game_player_quality(df, game_id)
            all_quality.append(game_quality)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  WARNING: Skipped {game_id}: {e}")

    if errors > 5:
        print(f"  ... ({errors} total errors, showing first 5)")

    quality_df = pd.concat(all_quality, ignore_index=True)
    print(f"  Total (game, slot) records: {len(quality_df)}")

    # ── Step 2: Attach NBA player IDs ─────────────────────────────────────────
    print("\n[Step 2] Attaching NBA player IDs...")
    quality_df = attach_nba_player_ids(quality_df, cv_per_game)
    n_with_id = quality_df["nba_player_id"].notna().sum()
    print(f"  Records with nba_player_id: {n_with_id} / {len(quality_df)}")

    # player_id_out is stored as string to accommodate both NBA IDs and "slot_X" labels
    quality_df["player_id_out"] = quality_df.apply(
        lambda r: str(int(r["nba_player_id"])) if pd.notna(r["nba_player_id"]) else f"slot_{r['player_slot']}",
        axis=1
    )

    # ── Step 3: Per-player aggregation ───────────────────────────────────────
    print("\n[Step 3] Aggregating per player...")
    player_agg = aggregate_per_player(quality_df)
    print(f"  Players with NBA ID + quality data: {len(player_agg)}")

    # ── Quality distribution ──────────────────────────────────────────────────
    high_pct = (quality_df["quality_score"] > HIGH_QUALITY).mean() * 100
    med_pct = (
        (quality_df["quality_score"] >= LOW_QUALITY) &
        (quality_df["quality_score"] <= HIGH_QUALITY)
    ).mean() * 100
    low_pct = (quality_df["quality_score"] < LOW_QUALITY).mean() * 100
    mean_quality = quality_df["quality_score"].mean()
    print(f"  Quality distribution: {high_pct:.1f}% high, {med_pct:.1f}% medium, {low_pct:.1f}% low")
    print(f"  Mean quality: {mean_quality:.3f}")

    # ── Step 4: Quality-adjusted Kelly multipliers ────────────────────────────
    print("\n[Step 4] Computing quality-adjusted Kelly multipliers...")
    adj_df = compute_quality_adjusted_kelly(player_agg, int16)
    print(f"  Players with both INT-16 and INT-39 data: {len(adj_df)}")

    # ── Step 5a: Save parquet ─────────────────────────────────────────────────
    print(f"\n[Step 5] Saving outputs...")
    os.makedirs(INTELLIGENCE_DIR, exist_ok=True)

    parquet_out = quality_df[[
        "game_id", "player_slot", "player_name",
        "homography_valid_rate", "jersey_resolution_rate",
        "frame_count", "phantom_slot_flag", "tracking_density",
        "quality_score", "nba_player_id"
    ]].copy()
    # Cast nba_player_id safely
    parquet_out["nba_player_id"] = pd.to_numeric(parquet_out["nba_player_id"], errors="coerce")

    parquet_out.to_parquet(OUT_PARQUET, index=False)
    print(f"  Saved: {OUT_PARQUET} ({len(parquet_out)} rows)")

    # ── Step 5b: Save JSON ────────────────────────────────────────────────────
    output_json = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "intelligence_id": "INT-39",
            "description": "CV tracking quality per player-game + quality-adjusted Kelly multipliers",
            "n_player_game_records": int(len(quality_df)),
            "n_players_with_quality": int(len(player_agg)),
            "n_players_with_adjusted_kelly": int(len(adj_df)),
            "mean_quality": round(float(mean_quality), 4),
            "pct_high_quality": round(float(high_pct), 2),
            "pct_medium_quality": round(float(med_pct), 2),
            "pct_low_quality": round(float(low_pct), 2),
            "quality_weights": {
                "homography_valid_rate": W_HOMOG,
                "jersey_resolution_rate": W_JERSEY,
                "frame_count_score": W_FRAMES,
                "non_phantom_score": W_PHANTOM,
            },
            "thresholds": {
                "high_quality": HIGH_QUALITY,
                "low_quality": LOW_QUALITY,
                "frames_for_full_score": FRAMES_THRESHOLD,
                "phantom_x_std_threshold": PHANTOM_STD_THRESHOLD,
            },
        },
        "per_player_quality": {},
        "quality_adjusted_kelly": {},
    }

    # Per-player quality
    if len(player_agg) > 0:
        for _, row in player_agg.iterrows():
            pid = int(row["nba_player_id"])
            output_json["per_player_quality"][str(pid)] = {
                "player_name": row["player_name"],
                "n_games": int(row["n_games"]),
                "mean_quality": float(row["mean_quality"]),
                "min_quality": float(row["min_quality"]),
                "max_quality": float(row["max_quality"]),
                "std_quality": float(row["std_quality"]),
                "n_high_quality_games": int(row["n_high_quality_games"]),
                "n_low_quality_games": int(row["n_low_quality_games"]),
                "mean_homography_rate": round(float(row["mean_homography_rate"]), 4),
                "mean_jersey_rate": round(float(row["mean_jersey_rate"]), 4),
                "mean_frame_count": int(row["mean_frame_count"]),
                "phantom_flag_rate": round(float(row["phantom_flag_rate"]), 4),
                "quality_bucket": (
                    "high" if row["mean_quality"] > HIGH_QUALITY
                    else "low" if row["mean_quality"] < LOW_QUALITY
                    else "medium"
                ),
            }

    # Quality-adjusted Kelly
    if len(adj_df) > 0:
        for _, row in adj_df.iterrows():
            pid = int(row["player_id"])
            output_json["quality_adjusted_kelly"][str(pid)] = {
                "player_name": row.get("player_name_cv", row.get("player_name_int16", "unknown")),
                "mean_quality": float(row["mean_quality"]),
                "quality_mult_factor": round(float(0.5 + 0.5 * row["mean_quality"]), 4),
                "original_overall_mult": float(row["overall_confidence_mult"]),
                "adj_overall_mult": float(row["adj_overall_mult"]),
                "adj_pts_mult": float(row["adj_pts_mult"]),
                "adj_reb_mult": float(row["adj_reb_mult"]),
                "adj_ast_mult": float(row["adj_ast_mult"]),
                "adj_fg3m_mult": float(row["adj_fg3m_mult"]),
                "adj_stl_mult": float(row["adj_stl_mult"]),
                "adj_blk_mult": float(row["adj_blk_mult"]),
                "adj_tov_mult": float(row["adj_tov_mult"]),
            }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {OUT_JSON}")

    # ── Step 5c: Generate Atlas Markdown ─────────────────────────────────────
    print("\n[Step 6] Generating CV Quality Confidence Atlas...")
    os.makedirs(VAULT_DIR, exist_ok=True)
    _write_atlas(quality_df, player_agg, adj_df, output_json)
    print(f"  Saved: {OUT_ATLAS}")

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("## INT-39 CV-Quality-Aware Confidence — Final Report")
    print("=" * 60)
    print(f"\n### Coverage")
    print(f"  (player, game) slot records scored: {len(quality_df)}")
    print(f"  Unique games processed: {quality_df['game_id'].nunique()}")
    print(f"  Slots with NBA player ID resolved: {n_with_id} ({n_with_id/len(quality_df)*100:.1f}%)")
    print(f"  Named players with quality profile: {len(player_agg)}")

    print(f"\n### Distribution")
    print(f"  High quality (>0.7):   {high_pct:.1f}%")
    print(f"  Medium (0.4–0.7):      {med_pct:.1f}%")
    print(f"  Low quality (<0.4):    {low_pct:.1f}%")
    print(f"  Mean quality: {mean_quality:.3f}")

    if len(player_agg) > 0:
        top5 = player_agg.head(5)
        print("\n### Top 5 best-tracked players (intelligence most reliable)")
        print(f"  {'Player':<25} {'Mean Q':>8} {'Games':>7} {'High Q Games':>14}")
        for _, row in top5.iterrows():
            adj_row = adj_df[adj_df["player_id"] == row["nba_player_id"]]
            adj_str = f"{adj_row['adj_overall_mult'].values[0]:.3f}" if len(adj_row) > 0 else "no INT-16"
            print(f"  {row['player_name']:<25} {row['mean_quality']:>8.3f} "
                  f"{int(row['n_games']):>7} {int(row['n_high_quality_games']):>14}  adj_kelly={adj_str}")

        bottom5 = player_agg.tail(5)
        print("\n### Bottom 5 worst-tracked (interpret CV intelligence with caution)")
        print(f"  {'Player':<25} {'Mean Q':>8} {'Games':>7} {'Low Q Games':>13}")
        for _, row in bottom5.iterrows():
            adj_row = adj_df[adj_df["player_id"] == row["nba_player_id"]]
            adj_str = f"{adj_row['adj_overall_mult'].values[0]:.3f}" if len(adj_row) > 0 else "no INT-16"
            print(f"  {row['player_name']:<25} {row['mean_quality']:>8.3f} "
                  f"{int(row['n_games']):>7} {int(row['n_low_quality_games']):>13}  adj_kelly={adj_str}")

    if len(adj_df) > 0:
        print(f"\n### Quality-adjusted Kelly — sample (top 5 by adjusted mult)")
        top_adj = adj_df.sort_values("adj_overall_mult", ascending=False).head(5)
        print(f"  {'Player':<25} {'Qual':>6} {'INT-16 mult':>12} {'Adj mult':>10}")
        for _, row in top_adj.iterrows():
            pname = row.get("player_name_cv", row.get("player_name_int16", "unknown"))
            # Encode to ASCII safe for any terminal
            pname_safe = pname.encode("ascii", errors="replace").decode("ascii")
            print(f"  {pname_safe:<25} {row['mean_quality']:>6.3f} "
                  f"{row['overall_confidence_mult']:>12.4f} {row['adj_overall_mult']:>10.4f}")

    print(f"\n### Files")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")

    print("\n### Honest caveats")
    print("  - Quality weighting (0.4/0.2/0.2/0.2) is heuristic and tunable")
    print("  - NBA player ID resolved for only ~27% of (game, slot) records;")
    print("    remaining slots use local slot IDs 1-10 — not cross-game identities")
    print("  - Phantom-slot threshold (x_pos std < 50px) is borrowed from prior intel")
    print("  - Short game clips naturally score lower — not all low-quality = bad tracking")
    print("  - Quality varies game-to-game; per-player mean may mask variance")

    return quality_df, player_agg, adj_df


def _write_atlas(quality_df, player_agg, adj_df, meta_json):
    """Write the vault Markdown atlas."""
    n_records = len(quality_df)
    n_players = len(player_agg)
    mean_q = meta_json["metadata"]["mean_quality"]
    high_pct = meta_json["metadata"]["pct_high_quality"]
    med_pct = meta_json["metadata"]["pct_medium_quality"]
    low_pct = meta_json["metadata"]["pct_low_quality"]
    n_adj = meta_json["metadata"]["n_players_with_adjusted_kelly"]

    lines = [
        "# CV Quality-Aware Confidence Atlas",
        "",
        f"> Generated: {datetime.now():%Y-%m-%d %H:%M}  |  Intelligence ID: **INT-39**",
        "",
        "## Methodology",
        "",
        "Quality score per `(player_slot, game)` combining four indicators:",
        "",
        "| Component | Weight | Derivation |",
        "|-----------|--------|------------|",
        "| `homography_valid_rate` | 0.40 | % of player's frames with valid court homography |",
        "| `jersey_resolution_rate` | 0.20 | % of frames where jersey number was resolved (not null) |",
        "| `frame_count_score` | 0.20 | min(1, frame_count / 1000) — proxy for time-on-court coverage |",
        "| `non_phantom_score` | 0.20 | 1 if x_position std ≥ 50px (player moved), else 0 (phantom/stuck slot) |",
        "",
        "Per-player average quality aggregated across all games with CV data.  ",
        "**Quality-adjusted Kelly** = INT-16 statistical multiplier × (0.5 + 0.5 × mean_quality)",
        "",
        "## Coverage",
        "",
        f"- Player-game slots scored: **{n_records:,}**",
        f"- Players with quality profile (NBA ID resolved): **{n_players}**",
        f"- Players with quality-adjusted Kelly (INT-16 cross-referenced): **{n_adj}**",
        f"- Mean quality across all records: **{mean_q:.3f}**",
        f"- Distribution: {high_pct:.1f}% high (>0.7) / {med_pct:.1f}% medium / {low_pct:.1f}% low (<0.4)",
        "",
    ]

    # Top 25 best-tracked
    lines += [
        "## Top 25 Best-Tracked Players",
        "",
        "Players where CV-derived intelligence is most reliable.",
        "",
        "| Player | Mean Quality | N Games | High-Q Games | INT-16 Mult | Adj Kelly |",
        "|--------|-------------|---------|--------------|-------------|-----------|",
    ]
    top25 = player_agg.head(25)
    for _, row in top25.iterrows():
        adj_row = adj_df[adj_df["player_id"] == row["nba_player_id"]] if len(adj_df) > 0 else pd.DataFrame()
        if len(adj_row) > 0:
            int16_mult = f"{adj_row['overall_confidence_mult'].values[0]:.4f}"
            adj_mult = f"{adj_row['adj_overall_mult'].values[0]:.4f}"
        else:
            int16_mult = "—"
            adj_mult = "—"
        lines.append(
            f"| {row['player_name']} | {row['mean_quality']:.3f} | {int(row['n_games'])} | "
            f"{int(row['n_high_quality_games'])} | {int16_mult} | {adj_mult} |"
        )

    # Bottom 25 worst-tracked
    lines += [
        "",
        "## Bottom 25 Worst-Tracked Players",
        "",
        "Players where any CV-derived intelligence carries higher uncertainty.",
        "Bet sizing should be reduced via the quality-adjusted Kelly multiplier.",
        "",
        "| Player | Mean Quality | N Games | Low-Q Games | INT-16 Mult | Adj Kelly |",
        "|--------|-------------|---------|-------------|-------------|-----------|",
    ]
    bottom25 = player_agg.tail(25).iloc[::-1]
    for _, row in bottom25.iterrows():
        adj_row = adj_df[adj_df["player_id"] == row["nba_player_id"]] if len(adj_df) > 0 else pd.DataFrame()
        if len(adj_row) > 0:
            int16_mult = f"{adj_row['overall_confidence_mult'].values[0]:.4f}"
            adj_mult = f"{adj_row['adj_overall_mult'].values[0]:.4f}"
        else:
            int16_mult = "—"
            adj_mult = "—"
        lines.append(
            f"| {row['player_name']} | {row['mean_quality']:.3f} | {int(row['n_games'])} | "
            f"{int(row['n_low_quality_games'])} | {int16_mult} | {adj_mult} |"
        )

    # Quality-adjusted Kelly section
    lines += [
        "",
        "## Quality-Adjusted Kelly Multipliers",
        "",
        "Formula: `adj_kelly = INT-16_mult × (0.5 + 0.5 × mean_quality)`",
        "",
        "- A player with quality=1.0 → full INT-16 multiplier",
        "- A player with quality=0.0 → only 50% of INT-16 multiplier",
        "- A player with quality=0.5 → 75% of INT-16 multiplier",
        "",
        "| Player | Mean Quality | Quality Factor | INT-16 Overall | Adj Overall | Adj PTS | Adj REB | Adj AST |",
        "|--------|-------------|----------------|----------------|-------------|---------|---------|---------|",
    ]
    if len(adj_df) > 0:
        for _, row in adj_df.sort_values("adj_overall_mult", ascending=False).iterrows():
            pname = row.get("player_name_cv", row.get("player_name_int16", "unknown"))
            factor = 0.5 + 0.5 * row["mean_quality"]
            lines.append(
                f"| {pname} | {row['mean_quality']:.3f} | {factor:.3f} | "
                f"{row['overall_confidence_mult']:.4f} | {row['adj_overall_mult']:.4f} | "
                f"{row['adj_pts_mult']:.4f} | {row['adj_reb_mult']:.4f} | {row['adj_ast_mult']:.4f} |"
            )

    # How to use
    lines += [
        "",
        "## How to Use",
        "",
        "### Bet Sizing",
        "Replace INT-16 Kelly multiplier with INT-39 quality-adjusted version:",
        "```",
        "kelly_fraction = base_kelly × adj_overall_mult  # instead of × int16_mult",
        "```",
        "",
        "### AI Chat",
        "Surface quality caveats for low-quality players:",
        "```",
        "f\"This player's CV data has only {mean_homography_rate:.0%} homography validity",
        " — interpret CV-derived intelligence cautiously.\"",
        "```",
        "",
        "### Combine with INT-V5 Compound Signals",
        "Only fire compound bet signals when player has mean_quality > 0.4 (medium or better).",
        "For quality < 0.4, treat all CV-derived signals as low-confidence.",
        "",
        "## Honest Caveats",
        "",
        "- Quality weighting formula (0.4 / 0.2 / 0.2 / 0.2) is heuristic — weights are tunable",
        "- NBA player ID resolved for only ~27% of (game, slot) records; ",
        "  unresolved slots carry no cross-game identity, limiting per-player aggregation",
        "- Phantom-slot threshold (x_pos std < 50px) borrowed from prior intelligence work",
        "- Short game clips score lower than full-game recordings — some 'low quality' = short clip",
        "- Quality varies game-to-game; per-player mean may mask high-variance players",
        "- jersey_resolution_rate proxies OCR success but some games have jersey numbers",
        "  stored as `0.0` (valid number) vs true null — marginal inflation possible",
        "",
        "## Related Intelligence",
        "",
        "- [[INT-16 Statistical Confidence]] — per-player CV/confidence from stat distribution",
        "- [[INT-V5 Compound Signal Verdicts]] — only fire when CV quality is adequate",
        "- [[Tracker Improvements Log]] — CV tracking quality history",
    ]

    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
