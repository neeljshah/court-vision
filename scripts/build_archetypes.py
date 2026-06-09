"""
build_archetypes.py — B3 Channel: Player Archetype Clustering

Cluster NBA players based on reliable position/possession CV features
(excludes defender_distance and other corrupted features). Saves:
  - data/models/player_archetypes.pkl  → {'scaler': ..., 'kmeans': ...}
  - data/models/player_archetype_map.json → {player_id_str: archetype_id_int}

Then writes cv_archetype feature values to the cv_features DB table.

Run:
    python scripts/build_archetypes.py
"""
from __future__ import annotations

import json
import os
import pickle
import sqlite3
import sys
from typing import Dict, List

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Reliable clustering features (position + possession, no defender_distance) ──
# play_type_drive_pct / post_pct / isolation_pct are ALL-ZERO in the DB — excluded.
CLUSTER_FEATURES = [
    "paint_dwell_pct",
    "touches_per_game",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "shots_per_possession",
    "possession_duration_avg",
    "potential_assists",
    "play_type_transition_pct",
]

K_DEFAULT = 6  # number of archetypes

# Human-readable labels assigned AFTER centroid inspection (updated below)
ARCHETYPE_LABELS = {
    0: "label_assigned_below",
    1: "label_assigned_below",
    2: "label_assigned_below",
    3: "label_assigned_below",
    4: "label_assigned_below",
    5: "label_assigned_below",
}


def load_player_features() -> tuple[np.ndarray, List[int]]:
    """Aggregate per-player feature vectors from cv_features DB.

    For each player with ≥2 distinct game_ids, average the CLUSTER_FEATURES
    across all their games.

    Returns
    -------
    X : np.ndarray shape (n_players, len(CLUSTER_FEATURES))
    player_ids : list of int (same order as X rows)
    """
    conn = sqlite3.connect(DB_PATH)
    import pandas as pd

    df = pd.read_sql(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()

    # Pivot to (player_id x game_id, feature)
    pivot = df.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
    )

    # Add missing cluster features as 0
    for feat in CLUSTER_FEATURES:
        if feat not in pivot.columns:
            pivot[feat] = 0.0

    pivot = pivot[CLUSTER_FEATURES].reset_index()

    # Only keep players with >= 2 distinct games
    game_counts = pivot.groupby("player_id")["game_id"].nunique()
    eligible = game_counts[game_counts >= 2].index
    pivot = pivot[pivot["player_id"].isin(eligible)]

    print(f"  Total (player_id, game_id) rows: {len(df.groupby(['player_id', 'game_id']))}")
    print(f"  Players with >=2 games: {len(eligible)}")

    # Bug 27 guard: potential_assists=0 means xAST submodule did not run for that
    # game.  Null zeros so per-player mean uses only PA-active games.
    if "potential_assists" in pivot.columns:
        pivot.loc[pivot["potential_assists"] == 0.0, "potential_assists"] = np.nan  # Bug 27 guard

    # Average across games per player
    player_avg = pivot.groupby("player_id")[CLUSTER_FEATURES].mean()
    player_ids = list(player_avg.index)
    X = player_avg.values.astype(float)
    print(f"  Feature matrix shape: {X.shape}")
    return X, player_ids


def sweep_k(X_scaled: np.ndarray, k_range=range(4, 9)) -> int:
    """Sweep K=4..8, pick best by silhouette score. Return chosen K."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    print("\n  K-sweep (inertia + silhouette):")
    best_k, best_sil = K_DEFAULT, -1.0
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=20, random_state=42)
        labels = km.fit_predict(X_scaled)
        inertia = km.inertia_
        sil = silhouette_score(X_scaled, labels) if k > 1 else 0.0
        marker = ""
        if sil > best_sil:
            best_sil = sil
            best_k = k
            marker = "  <-- best silhouette"
        print(f"    K={k}: inertia={inertia:.1f}  silhouette={sil:.4f}{marker}")

    print(f"  -> Chosen K={best_k} (silhouette={best_sil:.4f})")
    return best_k


def interpret_archetypes(km, scaler, feature_names) -> Dict[int, str]:
    """Print centroid z-scores and assign human-readable labels."""
    centroids_scaled = km.cluster_centers_  # already in standardized space
    # z-scores in standardized space = the centroid values themselves
    # (mean=0, std=1 after StandardScaler)

    # Map cluster_id → label based on centroid inspection
    label_rules = []
    labels_out = {}

    print("\n  Archetype centroids (z-scores, standardized space):")
    print(f"  {'ID':>3}  {'N':>4}  {'Top features (|z|)':}")
    print("  " + "-" * 70)

    unique, counts = np.unique(km.labels_, return_counts=True)
    count_map = dict(zip(unique.tolist(), counts.tolist()))

    for cid in range(km.n_clusters):
        centroid = centroids_scaled[cid]
        n = count_map.get(cid, 0)

        # Sort features by absolute z-score
        order = np.argsort(np.abs(centroid))[::-1]
        top_feats = []
        for i in order[:5]:
            top_feats.append(f"{feature_names[i]}={centroid[i]:+.2f}")

        # Heuristic label assignment based on top distinguishing features
        feat_z = {feature_names[i]: centroid[i] for i in range(len(feature_names))}
        label = _assign_label(feat_z, cid)
        labels_out[cid] = label

        print(f"  {cid:>3}  {n:>4}  {label}")
        for i, fz in enumerate(top_feats):
            print(f"         {'':>5}  {fz}")
        print()

    return labels_out


def _assign_label(feat_z: Dict[str, float], cid: int) -> str:
    """Heuristic label from centroid z-scores."""
    paint = feat_z.get("paint_dwell_pct", 0)
    three = feat_z.get("shot_zone_3pt_pct", 0)
    mid = feat_z.get("shot_zone_mid_range_pct", 0)
    touches = feat_z.get("touches_per_game", 0)
    assists = feat_z.get("potential_assists", 0)
    duration = feat_z.get("possession_duration_avg", 0)
    transition = feat_z.get("play_type_transition_pct", 0)
    shots_pp = feat_z.get("shots_per_possession", 0)
    paint_shot = feat_z.get("shot_zone_paint_pct", 0)

    # Score each archetype type
    scores = {
        "paint_big":           paint * 1.5 + paint_shot * 1.5 - three * 0.5,
        "perimeter_shooter":   three * 1.5 + shots_pp * 0.5 - paint * 0.5,
        "ball_handler":        touches * 1.5 + assists * 1.0 + duration * 0.5,
        "playmaker":           assists * 2.0 + touches * 0.5,
        "low_usage_role":      -touches - assists - shots_pp,
        "transition_runner":   transition * 2.0,
        "mid_range_scorer":    mid * 1.5 - three * 0.3,
    }
    # Pick the archetype with the highest heuristic score
    best = max(scores, key=scores.__getitem__)
    return best


def build_and_save(X: np.ndarray, player_ids: List[int]) -> tuple:
    """Standardize, sweep K, fit final KMeans, save artifacts."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    best_k = sweep_k(X_scaled)

    # Fit final model with chosen K
    km = KMeans(n_clusters=best_k, n_init=50, random_state=42)
    km.fit(X_scaled)

    sil = silhouette_score(X_scaled, km.labels_)
    print(f"\n  Final model: K={best_k}, inertia={km.inertia_:.1f}, silhouette={sil:.4f}")

    # Save artifacts
    artifact = {"scaler": scaler, "kmeans": km, "features": CLUSTER_FEATURES}
    pkl_path = os.path.join(MODEL_DIR, "player_archetypes.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump(artifact, f)
    print(f"  Saved: {pkl_path}")

    # Save player → archetype map
    archetype_map = {str(pid): int(lbl) for pid, lbl in zip(player_ids, km.labels_)}
    json_path = os.path.join(MODEL_DIR, "player_archetype_map.json")
    with open(json_path, "w") as f:
        json.dump(archetype_map, f, indent=2)
    print(f"  Saved: {json_path}")

    return scaler, km, archetype_map, best_k, sil


def write_to_db(archetype_map: Dict[str, int]) -> int:
    """Write feature_name='cv_archetype' to cv_features for all clustered players."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all (player_id, game_id) pairs for clustered players
    pids = [int(k) for k in archetype_map]
    placeholders = ",".join("?" * len(pids))
    c.execute(
        f"SELECT DISTINCT player_id, game_id FROM cv_features WHERE player_id IN ({placeholders})",
        pids,
    )
    rows = c.fetchall()

    written = 0
    for player_id, game_id in rows:
        arch_id = archetype_map.get(str(player_id))
        if arch_id is None:
            continue
        c.execute(
            """INSERT OR REPLACE INTO cv_features (game_id, player_id, feature_name, feature_value)
               VALUES (?, ?, 'cv_archetype', ?)""",
            (game_id, player_id, float(arch_id)),
        )
        written += 1

    conn.commit()
    conn.close()
    print(f"  DB writes: {written} cv_archetype rows written")
    return written


def main():
    print("=" * 60)
    print("B3 Player Archetype Clustering")
    print("=" * 60)

    print("\n[Step 1] Aggregating per-player feature vectors...")
    X, player_ids = load_player_features()

    n_players = len(player_ids)
    print(f"  Using {len(CLUSTER_FEATURES)} features: {CLUSTER_FEATURES}")

    print("\n[Step 2] Standardizing + clustering...")
    scaler, km, archetype_map, K, sil = build_and_save(X, player_ids)

    print("\n[Step 3] Interpreting archetypes...")
    # Refit scaler on X to get labels
    from sklearn.preprocessing import StandardScaler
    X_scaled = scaler.transform(X)
    labels = km.predict(X_scaled)
    km.labels_ = labels  # store for interpretation
    interpret_archetypes(km, scaler, CLUSTER_FEATURES)

    print("\n[Step 4] Writing cv_archetype to DB...")
    n_written = write_to_db(archetype_map)

    # Summary
    n_total_players_in_db = len(set(archetype_map.keys()))
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Players clustered (>=2 games): {n_players}")
    print(f"  K chosen: {K}")
    print(f"  Silhouette score: {sil:.4f}")
    print(f"  DB rows written: {n_written}")
    print(f"  Players unclustered: 316 - {n_players} = {316 - n_players} (insufficient games)")
    print("\nArtifacts:")
    print(f"  data/models/player_archetypes.pkl")
    print(f"  data/models/player_archetype_map.json")


if __name__ == "__main__":
    main()
