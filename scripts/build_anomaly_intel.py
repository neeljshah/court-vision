"""
build_anomaly_intel.py — INT-4: CV Anomaly Detection Intelligence

For each (player, game) in cv_features (with >= 3 OTHER baseline games),
compute leave-one-out z-scores per feature, rank anomalies, and output:
  - data/intelligence/anomaly_log.parquet
  - vault/Intelligence/Anomaly_Atlas.md
  - vault/Intelligence/Anomalies/<player>__<game>.md  (top 10)

Usage:
    python scripts/build_anomaly_intel.py
"""

import sqlite3
import json
import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "nba_ai.db")
PLAYER_JSON = os.path.join(ROOT, "data", "nba", "player_full_2024-25.json")
FINGERPRINTS_PATH = os.path.join(ROOT, "data", "intelligence", "player_fingerprints.parquet")
OUT_DIR = os.path.join(ROOT, "data", "intelligence")
VAULT_INTEL_DIR = os.path.join(ROOT, "vault", "Intelligence")
ANOMALY_LOG_OUT = os.path.join(OUT_DIR, "anomaly_log.parquet")
ATLAS_OUT = os.path.join(VAULT_INTEL_DIR, "Anomaly_Atlas.md")
ANOMALY_NOTES_DIR = os.path.join(VAULT_INTEL_DIR, "Anomalies")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(VAULT_INTEL_DIR, exist_ok=True)
os.makedirs(ANOMALY_NOTES_DIR, exist_ok=True)

# ── Reliable features from INT-1 (same list as build_player_atlas.py) ─────
FINGERPRINT_FEATURES = [
    "paint_dwell_pct",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "avg_shot_distance",
    "touches_per_game",
    "shots_per_possession",
    "possession_duration_avg",
    "second_chance_rate",
    "potential_assists",
    "preshot_velocity_peak",
    "defender_approach_speed",
    "play_type_transition_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "catch_shoot_pct",
    "avg_dribble_count",
    "contested_shot_rate",
    "avg_defender_distance",  # noisy sentinel ISSUE-022; flagged in caveats
]

# Dead features — excluded (all-zero or near all-zero)
DEAD_FEATURES = {"play_type_drive_pct", "avg_closeout_speed"}

# Z-score threshold for "anomalous"
Z_THRESH = 2.0

# Minimum OTHER games needed to score a player-game
MIN_BASELINE_GAMES = 3


# ── Helpers ────────────────────────────────────────────────────────────────

def load_player_name_map() -> dict:
    """Build player_id (int) -> display name dict from player_full JSON."""
    name_map = {}
    if not os.path.exists(PLAYER_JSON):
        print("  [WARN] player_full JSON not found — names will be IDs")
        return name_map
    with open(PLAYER_JSON, "r") as f:
        data = json.load(f)
    for name, info in data.items():
        pid = info.get("player_id")
        if pid:
            name_map[int(pid)] = name.title()
    return name_map


def load_game_date_map() -> dict:
    """Build game_id -> game_date from all season_games JSON files."""
    date_map = {}
    nba_dir = os.path.join(ROOT, "data", "nba")
    for fname in os.listdir(nba_dir):
        if fname.startswith("season_games_") and fname.endswith(".json"):
            fpath = os.path.join(nba_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                rows = data.get("rows", [])
                for row in rows:
                    gid = row.get("game_id")
                    gdate = row.get("game_date")
                    if gid and gdate:
                        date_map[gid] = gdate
            except Exception as e:
                print(f"  [WARN] Could not read {fname}: {e}")
    return date_map


def load_cv_features_wide() -> pd.DataFrame:
    """Load cv_features from DB, pivot to wide format (player_id, game_id, feature...)."""
    conn = sqlite3.connect(DB_PATH)
    df_long = pd.read_sql(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()
    df_wide = df_long.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    df_wide.columns.name = None
    return df_wide


def get_active_features(df_wide: pd.DataFrame) -> list:
    """
    Return the intersection of FINGERPRINT_FEATURES and available columns,
    excluding dead columns and features with zero variance across the entire dataset.
    """
    available = set(df_wide.columns)
    active = []
    for feat in FINGERPRINT_FEATURES:
        if feat in DEAD_FEATURES:
            continue
        if feat not in available:
            print(f"  [WARN] Feature '{feat}' not in cv_features table — skipping")
            continue
        # Check variance: if std across ALL rows is 0, skip
        std = df_wide[feat].std(skipna=True)
        if std == 0 or pd.isna(std):
            print(f"  [SKIP] Feature '{feat}' has zero variance — dead column")
            continue
        active.append(feat)
    return active


def compute_dataset_stds(df_wide: pd.DataFrame, features: list) -> dict:
    """Compute dataset-wide std per feature (fallback for small baselines)."""
    return {feat: df_wide[feat].std(skipna=True) for feat in features}


def score_player_games(
    df_wide: pd.DataFrame,
    features: list,
    dataset_stds: dict,
    player_ids_to_score: set,
) -> list:
    """
    For each (player_id, game_id) where player has >= MIN_BASELINE_GAMES OTHER games,
    compute leave-one-out z-scores and aggregate anomaly statistics.
    Returns list of dicts (one per player-game).
    """
    records = []

    for pid in player_ids_to_score:
        player_df = df_wide[df_wide["player_id"] == pid].copy()
        n_total = len(player_df)
        if n_total < MIN_BASELINE_GAMES + 1:
            # Need at least MIN_BASELINE_GAMES OTHER games after leaving one out
            continue

        for _, row in player_df.iterrows():
            game_id = row["game_id"]
            # Leave-one-out: baseline = all OTHER games
            other_games = player_df[player_df["game_id"] != game_id]
            n_baseline = len(other_games)

            if n_baseline < MIN_BASELINE_GAMES:
                continue

            feature_zscores = []
            for feat in features:
                game_val = row[feat]
                baseline_vals = other_games[feat].dropna()

                if pd.isna(game_val):
                    continue

                # Quality gate: the player must have a meaningful baseline for this feature.
                # If 90%+ of their baseline values are zero, the feature is "inactive" for them
                # (likely not tracked), and any non-zero game value would produce a spurious
                # large z-score from near-zero std. Skip these.
                n_baseline_vals = len(baseline_vals)
                n_nonzero_baseline = (baseline_vals != 0).sum()
                if n_baseline_vals > 0 and (n_nonzero_baseline / n_baseline_vals) < 0.10:
                    # Less than 10% of baseline games are non-zero — feature is inactive for
                    # this player; skip to avoid astronomical z-scores from near-zero std.
                    continue

                baseline_mean = baseline_vals.mean() if n_baseline_vals > 0 else np.nan
                baseline_std = baseline_vals.std(skipna=True) if n_baseline_vals > 1 else np.nan

                if pd.isna(baseline_mean):
                    continue

                # Effective std: use dataset-wide std if baseline std is None or too small.
                # Also enforce a minimum std floor = max(baseline_std, 10% of dataset-wide std)
                # to prevent near-zero baseline variance producing astronomical z-scores from
                # small absolute differences.
                ds_std = dataset_stds.get(feat, np.nan)
                if pd.isna(baseline_std) or baseline_std < 1e-9:
                    eff_std = ds_std
                else:
                    # Floor at 10% of dataset std so tiny baseline clusters can't produce z>50
                    min_floor = (ds_std * 0.10) if (not pd.isna(ds_std) and ds_std > 0) else baseline_std
                    eff_std = max(baseline_std, min_floor)

                if pd.isna(eff_std) or eff_std < 1e-9:
                    continue

                z = (game_val - baseline_mean) / eff_std
                feature_zscores.append({
                    "feature": feat,
                    "z": z,
                    "game_val": game_val,
                    "baseline_mean": baseline_mean,
                    "baseline_std": eff_std,  # effective std used for z (may be floored)
                })

            if not feature_zscores:
                continue

            # Aggregate
            abs_zscores = [abs(fz["z"]) for fz in feature_zscores]
            n_anomalous = sum(1 for az in abs_zscores if az > Z_THRESH)
            max_abs_z = max(abs_zscores) if abs_zscores else 0.0

            # Top 3 by |z|
            top3 = sorted(feature_zscores, key=lambda x: abs(x["z"]), reverse=True)[:3]
            top3_serializable = [
                {
                    "feature": fz["feature"],
                    "z": round(fz["z"], 3),
                    "game_val": round(fz["game_val"], 4),
                    "baseline_mean": round(fz["baseline_mean"], 4),
                    "baseline_std": round(fz["baseline_std"], 4),
                }
                for fz in top3
            ]

            records.append({
                "player_id": pid,
                "game_id": game_id,
                "n_anomalous_features": n_anomalous,
                "max_abs_z": round(max_abs_z, 3),
                "top_3_features": json.dumps(top3_serializable),
                "baseline_n_games": n_baseline,
                "_top3_raw": top3,  # keep for vault writing
            })

    return records


def build_anomaly_dataframe(
    records: list,
    name_map: dict,
    date_map: dict,
    fingerprints: pd.DataFrame,
) -> pd.DataFrame:
    """Convert raw records to the anomaly_log DataFrame with names and dates."""
    rows = []
    for rec in records:
        pid = rec["player_id"]
        player_name = name_map.get(pid)
        if not player_name:
            # Try fingerprints
            if pid in fingerprints.index:
                player_name = fingerprints.loc[pid, "player_name"]
            else:
                player_name = f"ID:{pid}"

        game_date = date_map.get(rec["game_id"], "unknown")

        rows.append({
            "player_id": pid,
            "player_name": player_name,
            "game_id": rec["game_id"],
            "game_date": game_date,
            "n_anomalous_features": rec["n_anomalous_features"],
            "max_abs_z": rec["max_abs_z"],
            "top_3_features": rec["top_3_features"],
            "baseline_n_games": rec["baseline_n_games"],
        })

    return pd.DataFrame(rows)


def add_validation_stats(
    anomaly_df: pd.DataFrame,
    fingerprints: pd.DataFrame,
) -> pd.DataFrame:
    """
    Step 6: Add actual stat vs baseline for PTS/REB/AST where available.
    Uses player_full JSON season averages as baseline (not per-game — best available).
    For per-game actuals we'd need gamelog data which is not reliably available here.
    Marks columns as 'season_avg' to be honest about the comparison.
    """
    # Season-level stats from player_full (not per-game, but honest)
    stat_cols = ["pts", "reb", "ast"]
    if not os.path.exists(PLAYER_JSON):
        return anomaly_df

    with open(PLAYER_JSON) as f:
        player_full = json.load(f)

    # Build id -> season avg map
    id_to_stats = {}
    for name, info in player_full.items():
        pid = info.get("player_id")
        if pid:
            id_to_stats[int(pid)] = {
                "season_avg_pts": info.get("pts"),
                "season_avg_reb": info.get("reb"),
                "season_avg_ast": info.get("ast"),
            }

    # Merge
    stat_rows = []
    for _, row in anomaly_df.iterrows():
        pid = row["player_id"]
        stat_rows.append(id_to_stats.get(pid, {"season_avg_pts": None, "season_avg_reb": None, "season_avg_ast": None}))

    stat_df = pd.DataFrame(stat_rows)
    return pd.concat([anomaly_df.reset_index(drop=True), stat_df], axis=1)


def compute_player_volatility(anomaly_df: pd.DataFrame) -> pd.DataFrame:
    """Per-player anomaly summary: volatility score + most common anomaly feature."""
    results = []
    for pid, group in anomaly_df.groupby("player_id"):
        player_name = group["player_name"].iloc[0]
        n_games = len(group)
        n_anomalous_games = (group["n_anomalous_features"] > 0).sum()
        mean_max_z = group["max_abs_z"].mean()

        # Most common anomaly feature (across games where |z| > Z_THRESH)
        feature_counts = {}
        for _, row in group.iterrows():
            try:
                top3 = json.loads(row["top_3_features"])
            except Exception:
                continue
            for fz in top3:
                if abs(fz["z"]) > Z_THRESH:
                    feat = fz["feature"]
                    feature_counts[feat] = feature_counts.get(feat, 0) + 1

        most_common_feat = (
            max(feature_counts, key=feature_counts.get) if feature_counts else "none"
        )

        results.append({
            "player_id": pid,
            "player_name": player_name,
            "n_cv_games": n_games,
            "n_anomalous_games": n_anomalous_games,
            "pct_anomalous": round(100.0 * n_anomalous_games / n_games, 1) if n_games > 0 else 0.0,
            "mean_max_z": round(mean_max_z, 3),
            "most_common_anomaly_feature": most_common_feat,
        })

    return pd.DataFrame(results).sort_values("mean_max_z", ascending=False).reset_index(drop=True)


def interpret_anomaly(feature: str, z: float, game_val: float, baseline_mean: float) -> str:
    """Generate a human-readable interpretation of an anomalous feature."""
    direction = "above" if z > 0 else "below"
    mag = abs(z)

    interpretations = {
        "avg_defender_distance": (
            f"Defenders stayed {direction} normal distance (z={z:+.1f}σ). "
            + ("Tight coverage — less open looks." if z < 0 else "Unusually wide open — rare defensive attention.")
        ),
        "contested_shot_rate": (
            f"Shot contest rate {direction} baseline (z={z:+.1f}σ). "
            + ("Far more contested than usual — defensive gameplan adjusted." if z > 0 else "Fewer contests — got clean looks.")
        ),
        "preshot_velocity_peak": (
            f"Pre-shot velocity {direction} baseline (z={z:+.1f}σ). "
            + ("More explosive off-movement creation." if z > 0 else "Sluggish pre-shot movement — off rhythm or fatigued.")
        ),
        "touches_per_game": (
            f"Touch volume {direction} baseline (z={z:+.1f}σ). "
            + ("Unusually heavy usage/ball handling." if z > 0 else "Unusually quiet — reduced role or defensive attention.")
        ),
        "paint_dwell_pct": (
            f"Time in paint {direction} baseline (z={z:+.1f}σ). "
            + ("More interior presence — rim attack focus." if z > 0 else "Stayed perimeter — drove less.")
        ),
        "possession_duration_avg": (
            f"Possession length {direction} baseline (z={z:+.1f}σ). "
            + ("Longer possessions — more isolation/creation." if z > 0 else "Quick releases — in movement/transition system.")
        ),
        "play_type_transition_pct": (
            f"Transition play rate {direction} baseline (z={z:+.1f}σ). "
            + ("Team ran far more/less in transition than usual." )
        ),
        "defender_approach_speed": (
            f"Defender approach speed {direction} baseline (z={z:+.1f}σ). "
            + ("Defenders closed out harder/faster — more pressure." if z > 0 else "Soft closeouts — open looks available.")
        ),
        "potential_assists": (
            f"Potential assists {direction} baseline (z={z:+.1f}σ). "
            + ("High playmaking volume." if z > 0 else "Minimal playmaking — role compressed.")
        ),
        "avg_shot_distance": (
            f"Shot distance {direction} baseline (z={z:+.1f}σ). "
            + ("Shot from deeper than usual." if z > 0 else "Attacked the rim more than usual.")
        ),
    }

    default = f"Feature '{feature}' was {mag:.1f}σ {direction} this player's baseline."
    return interpretations.get(feature, default)


def write_per_anomaly_notes(top10: pd.DataFrame, date_map: dict) -> None:
    """Write individual vault notes for top 10 anomalies."""
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        player_name = row["player_name"]
        game_id = row["game_id"]
        game_date = row["game_date"]
        try:
            top3 = json.loads(row["top_3_features"])
        except Exception:
            top3 = []

        if not top3:
            continue

        # Primary anomaly
        primary = top3[0]
        primary_feat = primary["feature"]
        primary_z = primary["z"]
        primary_val = primary["game_val"]
        primary_mean = primary["baseline_mean"]
        primary_std = primary["baseline_std"]

        interp = interpret_anomaly(primary_feat, primary_z, primary_val, primary_mean)

        # Other deviations
        other_lines = []
        for fz in top3[1:]:
            z_str = f"+{fz['z']:.1f}σ" if fz["z"] > 0 else f"{fz['z']:.1f}σ"
            other_lines.append(f"- {fz['feature']}: {z_str}")

        safe_name = player_name.replace(" ", "_").replace("/", "_").replace(":", "_")
        note_filename = f"{safe_name}__{game_id}.md"
        note_path = os.path.join(ANOMALY_NOTES_DIR, note_filename)

        # Build stat comparison line
        stat_parts = []
        for stat in ["season_avg_pts", "season_avg_reb", "season_avg_ast"]:
            if stat in row and row[stat] is not None and not pd.isna(row[stat]):
                label = stat.replace("season_avg_", "").upper()
                stat_parts.append(f"{label}: {row[stat]:.1f}/g (season avg)")
        stat_line = " | ".join(stat_parts) if stat_parts else "No season stats available"

        note_content = f"""# {player_name} — Game {game_id} ({game_date})

**Anomaly Rank:** #{rank} of all player-games tracked

## Primary Deviation

**Feature:** `{primary_feat}`
**Z-score:** {primary_z:+.2f}σ
**Game value:** {primary_val:.4f}
**Baseline mean:** {primary_mean:.4f} (std: {primary_std:.4f})
**Baseline games used:** {int(row['baseline_n_games'])}

**Interpretation:** {interp}

## Other Notable Deviations This Game

{chr(10).join(other_lines) if other_lines else "- (No other |z| > 2.0 deviations)"}

## Total Anomalous Features

{int(row['n_anomalous_features'])} features with |z| > 2.0 this game.

## Season Context

{stat_line}

## Followup Question

Did {player_name}'s actual PTS/REB/AST this game beat or miss their season average?
(Validation hook — cross-reference game box score for {game_date}.)

## Caveats

- Baseline n={int(row['baseline_n_games'])} games ({"small — noisy std" if row['baseline_n_games'] < 5 else "adequate"})
- ISSUE-022: `avg_defender_distance` anomalies may reflect sentinel (200.0) measurement artifacts
- Cross-season role changes can make baseline_mean misleading

---
*Generated by scripts/build_anomaly_intel.py — INT-4*
"""

        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note_content)
        print(f"  [NOTE] Written: {note_filename}")


def write_anomaly_atlas(
    top50: pd.DataFrame,
    player_volatility: pd.DataFrame,
    total_scored: int,
    total_with_any_anomaly: int,
) -> None:
    """Write the main Anomaly_Atlas.md vault note."""
    # Build top 50 table
    top50_rows = []
    for rank, (_, row) in enumerate(top50.iterrows(), 1):
        try:
            top3 = json.loads(row["top_3_features"])
        except Exception:
            top3 = []
        primary = top3[0] if top3 else {}
        feat = primary.get("feature", "—")
        z = primary.get("z", 0)
        baseline = primary.get("baseline_mean", 0)
        actual = primary.get("game_val", 0)
        z_str = f"+{z:.2f}" if z > 0 else f"{z:.2f}"
        interp = interpret_anomaly(feat, z, actual, baseline)[:80]
        top50_rows.append(
            f"| {rank} | {row['player_name']} | {row['game_id']} ({row['game_date']}) "
            f"| {feat} | {z_str}σ | {baseline:.3f} | {actual:.3f} | {interp}... |"
        )

    top50_table = "\n".join(top50_rows)

    # Most volatile players (top 20)
    volatile_top20 = player_volatility.head(20)
    volatile_rows = []
    for _, row in volatile_top20.iterrows():
        volatile_rows.append(
            f"| {row['player_name']} | {int(row['n_cv_games'])} | "
            f"{row['mean_max_z']:.3f} | {row['most_common_anomaly_feature']} | "
            f"{int(row['n_anomalous_games'])}/{int(row['n_cv_games'])} ({row['pct_anomalous']:.0f}%) |"
        )
    volatile_table = "\n".join(volatile_rows)

    # Most consistent players (bottom 20 by mean_max_z, with >= 4 games)
    consistent = player_volatility[player_volatility["n_cv_games"] >= 4].tail(20)
    consistent_rows = []
    for _, row in consistent.sort_values("mean_max_z").iterrows():
        consistent_rows.append(
            f"| {row['player_name']} | {int(row['n_cv_games'])} | {row['mean_max_z']:.3f} |"
        )
    consistent_table = "\n".join(consistent_rows)

    pct_any = 100.0 * total_with_any_anomaly / total_scored if total_scored > 0 else 0
    top1pct_z = np.percentile(top50["max_abs_z"], 2) if len(top50) >= 50 else top50["max_abs_z"].min()

    atlas_content = f"""# CV Anomaly Atlas
*Generated by scripts/build_anomaly_intel.py — INT-4*
*Date: 2026-05-28*

## Coverage

- **Player-games scored:** {total_scored} (players with ≥{MIN_BASELINE_GAMES} baseline games)
- **Games with ANY |z|>2 deviation:** {total_with_any_anomaly} ({pct_any:.1f}%)
- **Features used:** {len(FINGERPRINT_FEATURES)} (from INT-1 reliable feature set)
- **Z-score threshold:** {Z_THRESH}σ

---

## Most Extreme Single-Game Anomalies (Top 50)

| # | Player | Game (Date) | Max-Z Feature | z | Baseline | Actual | Interpretation |
|---|--------|-------------|---------------|---|----------|--------|----------------|
{top50_table}

---

## Most Volatile Players (Top 20 by Mean Max-Z)

| Player | N Games | Mean Max-Z | Most Common Anomaly Feature | Anomalous Games |
|--------|---------|------------|----------------------------|-----------------|
{volatile_table}

---

## Most Consistent Players (Stable CV Profile, Bottom 20 by Mean Max-Z, ≥4 games)

| Player | N Games | Mean Max-Z |
|--------|---------|------------|
{consistent_table}

---

## How to Use This

- The **top-50 list** is the betting edge signal — players who PLAYED unusually in a specific game.
- If sportsbook lines hadn't updated for this volatility (lines move slow on CV behavioral shifts), there's potential value.
- Per-game anomaly score can be added to `prop_pergame` as a meta-feature (validate with walk-forward before shipping).
- `avg_defender_distance` anomalies: treat with caution due to ISSUE-022 sentinel values.

### Query patterns (pandas)
```python
import pandas as pd, json
df = pd.read_parquet('data/intelligence/anomaly_log.parquet')

# Extreme anomalies
df[df['max_abs_z'] > 2.5]

# Most volatile players
df.groupby('player_name')['max_abs_z'].mean().nlargest(20)

# All anomalous games for a player
df[(df['player_name'].str.contains('Wembanyama')) & (df['n_anomalous_features'] > 0)]

# Top anomaly feature breakdown
import json
top_feats = df['top_3_features'].apply(lambda x: json.loads(x)[0]['feature'] if x else None)
top_feats.value_counts()
```

### Claude API query example
> "Show me all games where Tatum was anomalous in avg_defender_distance"

---

## Caveats

1. **Players with only {MIN_BASELINE_GAMES} baseline games** → very noisy std → unreliable z-scores. Consider filtering to `baseline_n_games >= 5` for production use.
2. **ISSUE-022:** `avg_defender_distance` has a sentinel value of 200.0 when undetected. Anomalies on this feature may be measurement artifacts, not behavioral changes.
3. **Cross-season baselines:** if a player changed roles between seasons tracked, baseline_mean blends two regimes. Per-season baseline would be more accurate for multi-season players.
4. **Zero-heavy features** (`play_type_isolation_pct`, `play_type_post_pct`, `avg_dribble_count`): most players have zero as their baseline; a rare non-zero event produces large z-scores but may reflect low-significance plays.
5. **Leave-one-out is enforced** — the current game is always excluded from its own baseline.
"""

    with open(ATLAS_OUT, "w", encoding="utf-8") as f:
        f.write(atlas_content)
    print(f"[ATLAS] Written: {ATLAS_OUT}")


def main():
    print("=" * 60)
    print("INT-4: CV Anomaly Detection Intelligence")
    print("=" * 60)

    # ── Load data ──────────────────────────────────────────────
    print("\n[1] Loading data...")
    name_map = load_player_name_map()
    date_map = load_game_date_map()
    print(f"  Player name map: {len(name_map)} entries")
    print(f"  Game date map: {len(date_map)} entries")

    fingerprints = pd.read_parquet(FINGERPRINTS_PATH)
    print(f"  Fingerprints: {len(fingerprints)} players")

    df_wide = load_cv_features_wide()
    print(f"  CV features wide: {df_wide.shape[0]} player-games, {df_wide.shape[1]} columns")

    # ── Active features ────────────────────────────────────────
    print("\n[2] Selecting active features...")
    active_features = get_active_features(df_wide)
    print(f"  Active features ({len(active_features)}): {active_features}")

    # Dataset-wide std (fallback)
    dataset_stds = compute_dataset_stds(df_wide, active_features)

    # ── Player eligibility ─────────────────────────────────────
    print(f"\n[3] Identifying scoreable players (>= {MIN_BASELINE_GAMES} baseline games)...")
    games_per_player = df_wide.groupby("player_id")["game_id"].nunique()
    # Need N+1 total to have N baseline games after leave-one-out
    eligible_players = set(games_per_player[games_per_player >= MIN_BASELINE_GAMES + 1].index)
    print(f"  Eligible players: {len(eligible_players)}")
    total_eligible_pg = games_per_player[games_per_player >= MIN_BASELINE_GAMES + 1].sum()
    print(f"  Eligible player-games: {total_eligible_pg}")

    # ── Score ──────────────────────────────────────────────────
    print("\n[4] Computing leave-one-out anomaly scores...")
    records = score_player_games(df_wide, active_features, dataset_stds, eligible_players)
    print(f"  Scored: {len(records)} player-games")

    # ── Build DataFrame ────────────────────────────────────────
    print("\n[5] Building anomaly DataFrame...")
    anomaly_df = build_anomaly_dataframe(records, name_map, date_map, fingerprints)
    print(f"  Base shape: {anomaly_df.shape}")

    # Step 6: Add validation stats
    anomaly_df = add_validation_stats(anomaly_df, fingerprints)
    print(f"  With validation stats: {anomaly_df.shape}")

    # ── Save parquet ───────────────────────────────────────────
    print(f"\n[6] Saving parquet to {ANOMALY_LOG_OUT}...")
    anomaly_df_out = anomaly_df.drop(columns=[c for c in anomaly_df.columns if c.startswith("_")])
    anomaly_df_out.to_parquet(ANOMALY_LOG_OUT, index=False)
    print(f"  Saved {len(anomaly_df_out)} rows")

    # ── Rank anomalies ─────────────────────────────────────────
    print("\n[7] Ranking anomalies...")
    ranked = anomaly_df.sort_values(
        ["max_abs_z", "n_anomalous_features"], ascending=False
    ).reset_index(drop=True)

    top50 = ranked.head(50)
    top10 = ranked.head(10)

    total_scored = len(anomaly_df)
    total_with_any_anomaly = (anomaly_df["n_anomalous_features"] > 0).sum()
    pct_any = 100.0 * total_with_any_anomaly / total_scored if total_scored > 0 else 0
    print(f"  Total scored: {total_scored}")
    print(f"  With any |z|>2 deviation: {total_with_any_anomaly} ({pct_any:.1f}%)")
    if len(ranked) >= 50:
        p99_z = np.percentile(ranked["max_abs_z"], 99)
        n_top1pct = (ranked["max_abs_z"] >= p99_z).sum()
        print(f"  Top 1% (max_z >= {p99_z:.2f}): {n_top1pct} games")

    # ── Per-player volatility ──────────────────────────────────
    print("\n[8] Computing per-player volatility...")
    player_volatility = compute_player_volatility(anomaly_df)
    print(f"  Player volatility computed for {len(player_volatility)} players")

    # ── Top 10 anomaly summary ─────────────────────────────────
    print("\n  Top 10 most extreme anomalies:")
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        try:
            top3 = json.loads(row["top_3_features"])
        except Exception:
            top3 = []
        primary = top3[0] if top3 else {}
        feat = primary.get("feature", "?")
        z = primary.get("z", 0)
        z_str = f"+{z:.2f}" if z > 0 else f"{z:.2f}"
        print(
            f"    #{rank}: {row['player_name']} | {row['game_id']} ({row['game_date']}) "
            f"| {feat} z={z_str}s | {int(row['n_anomalous_features'])} features anomalous"
        )

    # ── Per-anomaly vault notes (top 10) ──────────────────────
    print("\n[9] Writing per-anomaly vault notes (top 10)...")
    write_per_anomaly_notes(top10, date_map)

    # ── Anomaly Atlas ──────────────────────────────────────────
    print("\n[10] Writing Anomaly Atlas...")
    write_anomaly_atlas(top50, player_volatility, total_scored, total_with_any_anomaly)

    # ── Final report ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("INT-4 Anomaly Detection Intelligence — Final Report")
    print("=" * 60)

    print(f"""
Coverage
--------
  Player-games scored:        {total_scored} (with >= {MIN_BASELINE_GAMES} baseline games)
  With ANY |z|>2 deviation:   {total_with_any_anomaly} ({pct_any:.1f}%)
  Active features:            {len(active_features)}""")

    if len(ranked) > 0:
        p99_z = np.percentile(ranked["max_abs_z"], 99)
        n_top1pct = (ranked["max_abs_z"] >= p99_z).sum()
        print(f"  Top 1% (max_z >= {p99_z:.2f}):   {n_top1pct} games")

    print("\nMost Extreme Single-Game Anomalies (Top 10)")
    print("-" * 60)
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        try:
            top3 = json.loads(row["top_3_features"])
        except Exception:
            top3 = []
        primary = top3[0] if top3 else {}
        feat = primary.get("feature", "?")
        z = primary.get("z", 0)
        z_str = f"+{z:.2f}" if z > 0 else f"{z:.2f}"
        print(
            f"  #{rank:2d}: {row['player_name']:<25} | {row['game_id']} ({row['game_date']}) "
            f"| {feat} z={z_str}s | {int(row['n_anomalous_features'])} anomalous"
        )

    print("\nMost Volatile Players (Top 10)")
    print("-" * 60)
    for _, row in player_volatility.head(10).iterrows():
        print(
            f"  {row['player_name']:<25} | volatility={row['mean_max_z']:.3f} "
            f"| n_games={int(row['n_cv_games'])} | top_feat={row['most_common_anomaly_feature']}"
        )

    print("\nMost Consistent Players (Bottom 10, >= 4 games)")
    print("-" * 60)
    consistent_players = player_volatility[player_volatility["n_cv_games"] >= 4].tail(10)
    for _, row in consistent_players.sort_values("mean_max_z").iterrows():
        print(
            f"  {row['player_name']:<25} | volatility={row['mean_max_z']:.3f} "
            f"| n_games={int(row['n_cv_games'])}"
        )

    print(f"""
Files Written
-------------
  {ANOMALY_LOG_OUT}
  {ATLAS_OUT}
  {ANOMALY_NOTES_DIR}/<player>__<game>.md  (top 10)

Query Patterns
--------------
  df[df['max_abs_z'] > 2.5]                                        # extreme anomalies
  df.groupby('player_name')['max_abs_z'].mean().nlargest(20)       # most volatile
  df[(df['player_name'].str.contains('Tatum')) & (df['n_anomalous_features'] > 0)]  # player filter

Honest Caveats
--------------
  1. Players with only {MIN_BASELINE_GAMES} baseline games have noisy std — filter to >= 5 for production
  2. ISSUE-022: avg_defender_distance sentinel (200.0) inflates z-scores — treat those anomalies skeptically
  3. Zero-heavy features (isolation/post/dribble) produce large z on any non-zero value
  4. Cross-season baseline: role changes make baseline_mean a blend of two regimes
""")


if __name__ == "__main__":
    main()
