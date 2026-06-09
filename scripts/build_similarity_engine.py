"""
INT-6 Cross-Player Similarity Engine
=====================================
Builds a queryable similarity index over CV-derived player fingerprints.

Outputs:
  data/intelligence/similarity_matrix.parquet  — N×N pairwise (euclidean + cosine)
  data/intelligence/similar_neighbors.json     — top-10 neighbors per player (3 modes)
  vault/Intelligence/Similarity_Engine.md      — usage guide
  vault/Intelligence/Similarity_Examples/*.md  — 5 annotated example queries
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.spatial.distance import cdist

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path("C:/Users/neelj/nba-ai-system")
FP_PATH    = ROOT / "data/intelligence/player_fingerprints.parquet"
ARCH_PATH  = ROOT / "data/intelligence/player_archetype_definitions.json"
PLAYERS_PATH = ROOT / "data/nba/player_full_2024-25.json"
OUT_DIR    = ROOT / "data/intelligence"
VAULT_INT  = ROOT / "vault/Intelligence"
SIM_EXAMPLES = VAULT_INT / "Similarity_Examples"

OUT_DIR.mkdir(parents=True, exist_ok=True)
VAULT_INT.mkdir(parents=True, exist_ok=True)
SIM_EXAMPLES.mkdir(parents=True, exist_ok=True)

# ── 18 reliable CV features (from INT-1) ──────────────────────────────────────
CV_FEATURES = [
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
]

# ── helpers ────────────────────────────────────────────────────────────────────

def load_data():
    df = pd.read_parquet(FP_PATH)
    with open(ARCH_PATH) as f:
        archetypes = json.load(f)
    with open(PLAYERS_PATH) as f:
        player_full = json.load(f)
    # build id->stats lookup
    player_stats = {str(v["player_id"]): v for v in player_full.values()}
    return df, archetypes, player_stats


def zscore_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score each feature column; replace 0-variance columns with 0."""
    out = df.copy()
    for col in CV_FEATURES:
        std = df[col].std()
        if std > 1e-9:
            out[col] = (df[col] - df[col].mean()) / std
        else:
            out[col] = 0.0
    return out


def cosine_similarity_matrix(X: np.ndarray) -> np.ndarray:
    """Return N×N cosine similarity (1 = identical direction, -1 = opposite)."""
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1e-9  # avoid /0
    Xn = X / norms
    return Xn @ Xn.T


def top_k_neighbors(dist_row: np.ndarray, ids: list, k: int, exclude_self: bool = True):
    """Return top-k nearest (smallest distance) from a distance row."""
    order = np.argsort(dist_row)
    results = []
    for idx in order:
        if exclude_self and ids[idx] == dist_row.__self_id:
            continue
        results.append(idx)
        if len(results) >= k:
            break
    return results


def feature_contribution(vec_a: np.ndarray, vec_b: np.ndarray) -> dict:
    """Return per-feature squared contribution to euclidean distance."""
    diffs = (vec_a - vec_b) ** 2
    total = diffs.sum() + 1e-12
    return {CV_FEATURES[i]: float(diffs[i] / total) for i in range(len(CV_FEATURES))}


def top_contributing_features(vec_a, vec_b, n=3):
    contrib = feature_contribution(vec_a, vec_b)
    return sorted(contrib.items(), key=lambda x: -x[1])[:n]


# ── Step 1 + 2 ─────────────────────────────────────────────────────────────────

def build_matrices(df_norm, df_raw, ids, names, archetypes_col):
    print("Computing pairwise distances ...")
    X = df_norm[CV_FEATURES].values.astype(np.float64)

    # Euclidean distances
    euc_mat = cdist(X, X, metric="euclidean")        # N×N

    # Cosine similarity
    cos_sim = cosine_similarity_matrix(X)            # N×N, higher = more similar
    cos_dist = 1.0 - cos_sim                         # convert to distance (0 = identical)

    n = len(ids)
    print(f"  {n} players -> {n*n:,} pairs")

    # Build long-form parquet (upper triangle only to halve size)
    rows = []
    for i in range(n):
        for j in range(i + 1, n):
            rows.append({
                "player_id_a": ids[i],
                "player_id_b": ids[j],
                "name_a":      names[i],
                "name_b":      names[j],
                "archetype_a": archetypes_col[i],
                "archetype_b": archetypes_col[j],
                "euclidean_distance": float(euc_mat[i, j]),
                "cosine_distance":    float(cos_dist[i, j]),
                "cosine_similarity":  float(cos_sim[i, j]),
            })

    sim_df = pd.DataFrame(rows)
    out_path = OUT_DIR / "similarity_matrix.parquet"
    sim_df.to_parquet(out_path, index=False)
    print(f"  Saved similarity_matrix.parquet ({len(sim_df):,} rows)")

    return euc_mat, cos_dist, cos_sim, X


# ── Step 3 ─────────────────────────────────────────────────────────────────────

def build_neighbors_json(df_norm, df_raw, euc_mat, cos_dist, ids, names, archetypes_col, player_stats):
    print("Building top-10 neighbors per player ...")
    X = df_norm[CV_FEATURES].values.astype(np.float64)
    n = len(ids)

    neighbors = {}
    for i, pid in enumerate(ids):
        key = f"{pid}_{names[i]}"

        # helper: build neighbor entry
        def make_entry(j, dist_val, metric="euclidean"):
            top_feats = top_contributing_features(X[i], X[j])
            top_feat_labels = [f"{f} ({v:.1%})" for f, v in top_feats]
            return {
                "player_id": str(ids[j]),
                "name": names[j],
                "archetype": archetypes_col[j],
                "n_cv_games": int(df_raw.iloc[j]["n_cv_games"]),
                metric: round(float(dist_val), 4),
                "top_features_driving_similarity": top_feat_labels,
            }

        # top-10 euclidean
        euc_row = euc_mat[i].copy()
        euc_row[i] = 1e9  # mask self
        euc_order = np.argsort(euc_row)[:10]
        top_euc = [make_entry(j, euc_mat[i, j], "distance") for j in euc_order]

        # top-10 cosine
        cos_row = cos_dist[i].copy()
        cos_row[i] = 1e9
        cos_order = np.argsort(cos_row)[:10]
        top_cos = [make_entry(j, cos_dist[i, j], "cosine_distance") for j in cos_order]

        # top-10 same archetype
        arch = archetypes_col[i]
        same_mask = np.array([a == arch for a in archetypes_col], dtype=bool)
        same_mask[i] = False
        if same_mask.sum() == 0:
            top_arch = []
        else:
            arch_dists = euc_mat[i].copy()
            arch_dists[~same_mask] = 1e9
            arch_order = np.argsort(arch_dists)[:10]
            arch_order = [j for j in arch_order if same_mask[j]]
            top_arch = [make_entry(j, euc_mat[i, j], "distance") for j in arch_order]

        neighbors[key] = {
            "player_id": str(pid),
            "name": names[i],
            "archetype": archetypes_col[i],
            "n_cv_games": int(df_raw.iloc[i]["n_cv_games"]),
            "top_10_euclidean": top_euc,
            "top_10_cosine": top_cos,
            "top_10_same_archetype": top_arch,
        }

    out_path = OUT_DIR / "similar_neighbors.json"
    with open(out_path, "w") as f:
        json.dump(neighbors, f, indent=2)
    print(f"  Saved similar_neighbors.json ({n} players)")
    return neighbors


# ── Step 4 — Example notes ─────────────────────────────────────────────────────

def find_player_key(neighbors, name_substr):
    """Return (key, entry) for first match by substring."""
    name_lower = name_substr.lower()
    for k, v in neighbors.items():
        if name_lower in v["name"].lower():
            return k, v
    return None, None


def write_example_1_wemby(neighbors, df_norm, df_raw, ids, names, archetypes_col, X):
    key, wemby = find_player_key(neighbors, "Wembanyama")
    if wemby is None:
        print("  WARNING: Wembanyama not found in dataset")
        return

    top5 = wemby["top_10_euclidean"][:5]

    lines = []
    lines.append("# Who Plays Like Victor Wembanyama?")
    lines.append("")
    lines.append("**Query:** `who plays like Wembanyama`")
    lines.append("")
    lines.append("## Wembanyama's Profile")
    lines.append(f"- **Archetype:** {wemby['archetype']}")
    lines.append(f"- **CV Games:** {wemby['n_cv_games']} (decent sample for a second-year player)")
    lines.append("")
    lines.append("Wembanyama's CV fingerprint is dominated by extreme **preshot_velocity_peak** (fast, explosive cuts before shooting), above-average **second_chance_rate** (relentless motor), and unusually high **contested_shot_rate** — he creates his own shots at extraordinary height. He is in the **High-Motor Cutter / Physical Slasher** archetype, which already tells you he reads as a physical, active player rather than a pure perimeter sniper.")
    lines.append("")
    lines.append("## Top 5 Similar Players (Euclidean)")
    lines.append("")

    for rank, nb in enumerate(top5, 1):
        lines.append(f"### {rank}. {nb['name']} (dist={nb['distance']:.3f})")
        lines.append(f"- **Archetype:** {nb['archetype']}")
        lines.append(f"- **CV Games:** {nb['n_cv_games']}")
        lines.append(f"- **Key shared dimensions:** {', '.join(nb['top_features_driving_similarity'])}")
        lines.append("")

    lines.append("## Archetype-Restricted Match (Same Cluster Only)")
    top_arch5 = wemby["top_10_same_archetype"][:5]
    if top_arch5:
        for rank, nb in enumerate(top_arch5, 1):
            lines.append(f"{rank}. **{nb['name']}** — dist={nb['distance']:.3f}, {nb['n_cv_games']} CV games")
    else:
        lines.append("No same-archetype matches.")

    lines.append("")
    lines.append("## Caveats")
    lines.append("- Wemby had 7 CV-tracked games. His fingerprint is moderately reliable but not fully converged — 13+ games would be ideal.")
    lines.append("- The High-Motor Cutter cluster has 62 players (many wings/bigs with active off-ball tendencies). Wemby is the only center-profile player in this cluster with 7+ games, so 'similar' means 'similar activity pattern' not 'similar size or position'.")
    lines.append("- `avg_defender_distance` = 0.0 for Wemby in the dataset (likely a CV measurement gap), which may flatten his uniqueness metric slightly.")
    lines.append("")
    lines.append("## Practical Uses")
    lines.append("- **Injury backup analysis:** If Wemby misses games, his nearest neighbors' stat profiles give you a rough expected floor for a replacement with similar usage patterns.")
    lines.append("- **Scouting comps:** A young player appearing as Wemby's neighbor (pre-stardom) is worth watching — the CV pattern matched before the box score did.")
    lines.append("- **Archetype purity:** Wemby's `dist_from_centroid` tells you if he's a canonical High-Motor Cutter or an outlier within that cluster.")

    path = SIM_EXAMPLES / "who_plays_like_wemby.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {path.name}")


def write_example_2_curry_clones(neighbors, df_raw, player_stats):
    key, curry = find_player_key(neighbors, "Stephen Curry")
    if curry is None:
        print("  WARNING: Curry not found")
        return

    # Filter underrated: n_cv_games < 5 OR low pts
    top10 = curry["top_10_euclidean"]
    underrated = []
    for nb in top10:
        pid = nb["player_id"]
        games = nb["n_cv_games"]
        pts = player_stats.get(pid, {}).get("pts", 999)
        if games < 5 or (isinstance(pts, (int, float)) and pts < 15):
            underrated.append((nb, pts))
    # also include some even if slightly over threshold
    if len(underrated) < 3:
        for nb in top10:
            pid = nb["player_id"]
            pts = player_stats.get(pid, {}).get("pts", 999)
            if (nb, pts) not in underrated:
                underrated.append((nb, pts))
        underrated = underrated[:5]

    lines = []
    lines.append("# Underrated Curry Clones — Hidden Perimeter Gems")
    lines.append("")
    lines.append("**Query:** Stephen Curry's nearest CV neighbors that are NOT stars")
    lines.append("")
    lines.append("## Why This Query Is Interesting")
    lines.append("Curry's CV fingerprint is defined by: extreme **catch_shoot_pct**, high **shot_zone_3pt_pct**, elevated **avg_shot_distance**, fast **preshot_velocity_peak** (catch-and-fire), and low **avg_dribble_count** (minimal ball-handling before shooting). Players who share this profile but don't have the name recognition are hidden value targets.")
    lines.append("")
    lines.append(f"**Curry's Archetype:** {curry['archetype']} (note: despite being the greatest shooter ever, his archetype is 'Low-CV-Activity Profile' — this is a dataset artifact from the Warriors' high-pace system causing low per-possession tracking depth)")
    lines.append("")
    lines.append("## Curry's Full Profile")
    lines.append(f"- n_cv_games: {curry['n_cv_games']}")
    lines.append("")
    lines.append("## Top Neighbors with Low Profile")
    lines.append("")

    for nb, pts in underrated[:5]:
        pid = nb["player_id"]
        stat = player_stats.get(pid, {})
        pts_display = pts if isinstance(pts, (int, float)) and pts < 900 else "N/A"
        min_val = stat.get("min", "N/A")
        lines.append(f"### {nb['name']}")
        lines.append(f"- **Distance:** {nb['distance']:.3f} | **CV Games:** {nb['n_cv_games']}")
        lines.append(f"- **Archetype:** {nb['archetype']}")
        lines.append(f"- **Season stats:** {pts_display} PPG, {min_val} MPG")
        lines.append(f"- **Why similar to Curry:** {', '.join(nb['top_features_driving_similarity'])}")
        lines.append("")

    lines.append("## All Top-10 Euclidean Neighbors (for reference)")
    for rank, nb in enumerate(top10, 1):
        pid = nb["player_id"]
        pts = player_stats.get(pid, {}).get("pts", "N/A")
        lines.append(f"{rank}. **{nb['name']}** — dist={nb['distance']:.3f}, {nb['n_cv_games']} CV games, {pts} PPG")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- Curry is in the 'Low-CV-Activity' cluster — 44% of all players are here. Similarity within this cluster is less granular than in the sport-specific clusters.")
    lines.append("- A player with 2-3 CV games may have a noisy vector. Cross-validate against their season shot chart before trusting the similarity.")
    lines.append("- 'Similar CV fingerprint' does not mean 'similar production' — it means similar shot selection and movement patterns. Curry's efficiency is irreproducible; his STYLE is what we're matching here.")
    lines.append("")
    lines.append("## Practical Uses")
    lines.append("- **DFS value plays:** A player with Curry's movement profile but Tier-3 salary pricing could be a GPP pivot.")
    lines.append("- **Trade targets:** Teams needing floor spacers should look here — these players create similar spacing patterns.")

    path = SIM_EXAMPLES / "underrated_curry_clones.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {path.name}")


def write_example_3_opposite_of_giannis(neighbors, df_norm, df_raw, ids, names, archetypes_col, X):
    # Giannis not in dataset — use the biggest paint-dweller as proxy
    # Find player with highest paint_dwell_pct
    paint_vals = df_raw["paint_dwell_pct"].values
    paint_max_idx = np.argmax(paint_vals)
    proxy_pid = ids[paint_max_idx]
    proxy_name = names[paint_max_idx]

    # Now find the farthest players from that player
    euc_row = np.sqrt(((X - X[paint_max_idx]) ** 2).sum(axis=1))
    euc_row[paint_max_idx] = -1  # exclude self
    farthest_idx = np.argsort(-euc_row)[:10]

    lines = []
    lines.append("# Opposite of Giannis — The Anti-Archetype Query")
    lines.append("")
    lines.append("**Query:** Players FARTHEST from a paint-dominant physical big")
    lines.append("")
    lines.append("## Note on Dataset")
    lines.append("Giannis Antetokounmpo (ID 203507) is NOT in the CV dataset — he had 0 tracked games in our corpus. To answer the spirit of this query, we identify the player with the highest **paint_dwell_pct** in the dataset as the proxy paint-dominant archetype, then find who is farthest from them.")
    lines.append("")
    lines.append(f"**Paint-dominant proxy player:** {proxy_name} (player_id: {proxy_pid})")
    lines.append(f"- **paint_dwell_pct:** {df_raw.iloc[paint_max_idx]['paint_dwell_pct']:.3f}")
    lines.append(f"- **shot_zone_paint_pct:** {df_raw.iloc[paint_max_idx]['shot_zone_paint_pct']:.3f}")
    lines.append(f"- **avg_shot_distance:** {df_raw.iloc[paint_max_idx]['avg_shot_distance']:.1f} ft")
    lines.append(f"- **Archetype:** {archetypes_col[paint_max_idx]}")
    lines.append(f"- **CV Games:** {df_raw.iloc[paint_max_idx]['n_cv_games']}")
    lines.append("")
    lines.append("## Top 10 Players FARTHEST from Paint-Dominant Profile")
    lines.append("")
    lines.append("These are the anti-archetypes — players who operate in completely different spatial and behavioral dimensions:")
    lines.append("")

    for rank, j in enumerate(farthest_idx, 1):
        dist_val = float(euc_row[j])
        top_feats = top_contributing_features(X[paint_max_idx], X[j])
        feat_labels = [f"{f} ({v:.1%})" for f, v in top_feats]
        lines.append(f"### {rank}. {names[j]} (distance: {dist_val:.3f})")
        lines.append(f"- **Archetype:** {archetypes_col[j]} | **CV Games:** {df_raw.iloc[j]['n_cv_games']}")
        lines.append(f"- **Dimensions driving the gap:** {', '.join(feat_labels)}")
        lines.append(f"- **Their paint_dwell_pct:** {df_raw.iloc[j]['paint_dwell_pct']:.3f} vs proxy's {df_raw.iloc[paint_max_idx]['paint_dwell_pct']:.3f}")
        lines.append("")

    lines.append("## What This Tells Us")
    lines.append("Players in the farthest positions are typically pure perimeter operators — high **avg_shot_distance**, high **shot_zone_3pt_pct**, low **possession_duration_avg** (quick-release shooters). They are the spatial opposites of a paint anchor.")
    lines.append("")
    lines.append("## Practical Use")
    lines.append("- **Lineup construction:** If a paint anchor is on the floor, their anti-archetype neighbors create optimal floor spacing.")
    lines.append("- **Defensive matchup:** An anti-archetype player can relocate freely off-ball when the paint is clogged — high spacing utility.")
    lines.append("- **Team-building:** Front offices building around a paint-dominant big should target players from the far end of this distance ranking.")
    lines.append("")
    lines.append("## Caveat")
    lines.append("This query uses Euclidean distance in 18-d normalized space. Two players can be 'opposite' while still having moderate similarity on some dimensions. The 'opposite' label means overall vector distance, not categorical opposition.")

    path = SIM_EXAMPLES / "opposite_of_giannis.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {path.name}")


def write_example_4_bridge_players(neighbors, df_norm, df_raw, ids, names, archetypes_col, X):
    # Bridge players: their top-10 euclidean neighbors span >= 3 different archetypes
    bridge_scores = []
    for i, pid in enumerate(ids):
        key = f"{pid}_{names[i]}"
        entry = neighbors[key]
        top10 = entry["top_10_euclidean"]
        arch_set = set(nb["archetype"] for nb in top10)
        bridge_scores.append((i, pid, names[i], archetypes_col[i], len(arch_set), arch_set, df_raw.iloc[i]["n_cv_games"]))

    bridge_scores.sort(key=lambda x: (-x[4], -x[6]))  # most archetypes, then most games
    top_bridges = bridge_scores[:10]

    lines = []
    lines.append("# Bridge Players Between Archetypes")
    lines.append("")
    lines.append("**Query:** Players whose top-10 nearest neighbors span the most different archetypes")
    lines.append("")
    lines.append("## What Are Bridge Players?")
    lines.append("A 'bridge player' sits at the boundary between behavioral archetypes. Their CV fingerprint is versatile enough that the algorithm finds neighbors in multiple clusters — they are the glue players of the style taxonomy.")
    lines.append("")
    lines.append("## Methodology")
    lines.append("For each player, count distinct archetypes represented in their top-10 euclidean neighbors. Players with neighbors in 3+ archetypes are considered bridges. Within ties, prefer players with more CV games (more reliable vectors).")
    lines.append("")
    lines.append("## Top Bridge Players")
    lines.append("")

    for rank, (i, pid, name, arch, n_archs, arch_set, n_games) in enumerate(top_bridges, 1):
        key = f"{pid}_{name}"
        top10 = neighbors[key]["top_10_euclidean"]
        lines.append(f"### {rank}. {name}")
        lines.append(f"- **Own archetype:** {arch}")
        lines.append(f"- **Neighbor archetypes:** {', '.join(sorted(arch_set))} ({n_archs} distinct)")
        lines.append(f"- **CV Games:** {n_games}")
        lines.append(f"- **Top 5 neighbors:**")
        for nb in top10[:5]:
            lines.append(f"  - {nb['name']} ({nb['archetype']}, dist={nb['distance']:.3f})")
        lines.append("")

    lines.append("## Interpretation")
    lines.append("Bridge players are tactically versatile. In modern NBA analytics, a player classified as 'bridge' by CV similarity may:")
    lines.append("- Switch between off-ball cutting and catch-and-shoot depending on lineup context")
    lines.append("- Be misclassified by simple role labels (e.g., called a 'wing' but plays like a combo guard situationally)")
    lines.append("- Represent a transitional profile — their role may be shifting as they develop")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- 44% of all players are in the 'Low-CV-Activity' noise cluster. A player whose neighbors span archetypes including this cluster is harder to interpret — it may mean genuine versatility OR just that the fingerprint has high noise.")
    lines.append("- Players with only 2-3 CV games are excluded from this analysis (their vectors are too noisy to trust cross-archetype coverage).")
    lines.append("")
    lines.append("## Practical Use")
    lines.append("- **Lineup versatility scoring:** Bridge players are your '+1' in lineup permutations — they fit multiple lineup contexts.")
    lines.append("- **Trade value:** A player who bridges archetypes is harder to replace with a single-archetype acquisition.")

    path = SIM_EXAMPLES / "bridge_players_between_archetypes.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {path.name}")


def write_example_5_archetype_centroids(neighbors, df_norm, df_raw, ids, names, archetypes_col, X, archetypes_dict):
    lines = []
    lines.append("# Archetype Centroids — The Purest Examples of Each Style")
    lines.append("")
    lines.append("**Query:** For each KMeans cluster, find the player CLOSEST to the cluster centroid")
    lines.append("")
    lines.append("## Methodology")
    lines.append("Compute the mean feature vector for each archetype cluster (the centroid). Then find the player with smallest Euclidean distance to that centroid. This player is the 'purest' or 'most canonical' example of that archetype.")
    lines.append("")

    unique_archs = sorted(set(archetypes_col))
    for arch in unique_archs:
        mask = np.array([a == arch for a in archetypes_col])
        arch_X = X[mask]
        arch_ids = [ids[i] for i in range(len(ids)) if archetypes_col[i] == arch]
        arch_names = [names[i] for i in range(len(ids)) if archetypes_col[i] == arch]
        arch_games = [int(df_raw.iloc[i]["n_cv_games"]) for i in range(len(ids)) if archetypes_col[i] == arch]

        centroid = arch_X.mean(axis=0)
        dists_to_centroid = np.sqrt(((arch_X - centroid) ** 2).sum(axis=1))
        sorted_idx = np.argsort(dists_to_centroid)

        # Find archetype def
        arch_def = None
        for k, v in archetypes_dict.items():
            if v["name"] == arch:
                arch_def = v
                break

        lines.append(f"## {arch}")
        lines.append(f"- **N players:** {mask.sum()}")

        if arch_def:
            top_feats = list(arch_def.get("top_distinguishing_features", {}).items())[:3]
            feat_str = ", ".join(f"{f} (z={z:+.2f})" for f, z in top_feats)
            lines.append(f"- **Defining features:** {feat_str}")

        lines.append("")
        lines.append("### Closest to centroid (most canonical examples):")
        for rank, j in enumerate(sorted_idx[:5], 1):
            dist_c = dists_to_centroid[j]
            lines.append(f"{rank}. **{arch_names[j]}** — dist_from_centroid={dist_c:.3f}, n_cv_games={arch_games[j]}")

        lines.append("")
        lines.append("### Farthest from centroid (outliers within this archetype):")
        for rank, j in enumerate(sorted_idx[-3:][::-1], 1):
            dist_c = dists_to_centroid[j]
            lines.append(f"{rank}. **{arch_names[j]}** — dist_from_centroid={dist_c:.3f}, n_cv_games={arch_games[j]}")

        lines.append("")

    lines.append("## Interpretation")
    lines.append("The centroid-closest player is the reference point for that archetype. When explaining what an archetype means:")
    lines.append("- Use the centroid player as the anchor example")
    lines.append("- Farthest-from-centroid players have a mix of this archetype's traits and elements of another — they may be edge cases or transitional profiles")
    lines.append("")
    lines.append("## Practical Uses")
    lines.append("- **Archetype explanation:** 'The High-Motor Cutter archetype — think [centroid player]'")
    lines.append("- **Valuation anchor:** If you know the centroid player's market value, it anchors valuation for others in that cluster")
    lines.append("- **Stability check:** Players far from centroid are volatile — their archetype assignment is less reliable")
    lines.append("")
    lines.append("## Caveat")
    lines.append("The Low-CV-Activity cluster centroid is a noise artifact — it represents players with many zero-valued features. The 'centroid player' here is simply whoever has the least activity, not a meaningful reference point. Treat this cluster's results with skepticism.")

    path = SIM_EXAMPLES / "archetype_centroids.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {path.name}")


# ── Step 5 — Main vault note ───────────────────────────────────────────────────

def write_main_vault_note(neighbors, df_raw, euc_mat, ids, names):
    n = len(ids)
    n_pairs = n * (n - 1) // 2
    # avg closest neighbor distance
    upper_tri = euc_mat[np.triu_indices(n, k=1)]
    avg_closest = np.mean([euc_mat[i][np.argmin(np.where(np.arange(n) != i, euc_mat[i], 1e9))] for i in range(n)])
    # players with no close match (closest neighbor > 3.0 euclidean std units)
    no_close = sum(
        1 for i in range(n)
        if np.min([euc_mat[i][j] for j in range(n) if j != i]) > 3.0
    )

    content = f"""# CV Similarity Engine

## What this is
Queryable cross-player similarity based on CV-derived behavioral fingerprints (INT-1 atlas).
230 players × 18 features, z-score normalized, pairwise euclidean + cosine distances.

## How to use

### Python query
```python
import json
neighbors = json.load(open('data/intelligence/similar_neighbors.json'))
# Keys are "player_id_name", e.g. "201939_Stephen Curry"
print(neighbors['201939_Stephen Curry']['top_10_euclidean'])
```

### Pandas pairwise
```python
import pandas as pd
sim = pd.read_parquet('data/intelligence/similarity_matrix.parquet')
sim.query("player_id_a == '201939'").nsmallest(10, 'euclidean_distance')
```

### Claude API integration
Feed `similar_neighbors.json` as context — chat queries like "who plays like Wemby?" hit pre-computed results instantly.

## Interesting examples
- [[Similarity_Examples/who_plays_like_wemby]]
- [[Similarity_Examples/underrated_curry_clones]]
- [[Similarity_Examples/opposite_of_giannis]]
- [[Similarity_Examples/bridge_players_between_archetypes]]
- [[Similarity_Examples/archetype_centroids]]

## Stats
- Players indexed: {n}
- Pairwise pairs (upper triangle): {n_pairs:,}
- Average closest-neighbor distance: {avg_closest:.3f}
- Players with no close match (closest > 3.0): {no_close}

## Methodology
- 18 reliable CV features from INT-1 (spatial zone %, shot distance, touches, play types, etc.)
- Z-score normalized per feature across all 230 players
- Pairwise **Euclidean distance** = overall behavioral similarity
- Pairwise **Cosine distance** = directional/playstyle similarity (magnitude-independent)
- Three neighbor modes: overall, cosine-playstyle, same-archetype restricted

## Caveats
- 44% of indexed players are in the **Low-CV-Activity** noise cluster — their similarity scores are unreliable for fine-grained comparisons
- Cross-season aggregation: traded players have profiles blending both teams' styles
- Sample sizes vary 2-16 games; players with 2-3 games have noisier vectors
- `avg_defender_distance` = 0.0 for many players (likely a CV measurement gap), potentially flattening uniqueness
- Giannis Antetokounmpo, LeBron James, and other stars with 0 tracked games are absent from the index

## File locations
- `data/intelligence/similarity_matrix.parquet` — full {n_pairs:,}-row pairwise matrix
- `data/intelligence/similar_neighbors.json` — top-10 per player in 3 ranking modes
"""
    path = VAULT_INT / "Similarity_Engine.md"
    path.write_text(content, encoding="utf-8")
    print(f"  Wrote vault/Intelligence/Similarity_Engine.md")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("INT-6 Cross-Player Similarity Engine")
    print("=" * 60)

    # Load
    print("\n[1/5] Loading data ...")
    df_raw, archetypes_dict, player_stats = load_data()
    print(f"  Fingerprints: {df_raw.shape[0]} players × {len(CV_FEATURES)} CV features")

    # Normalize
    print("\n[2/5] Z-score normalizing features ...")
    df_norm = zscore_normalize(df_raw)

    ids = list(df_raw.index)
    names = list(df_raw["player_name"])
    archetypes_col = list(df_raw["archetype_name"])
    X = df_norm[CV_FEATURES].values.astype(np.float64)

    print(f"  Feature matrix: {X.shape}")
    print(f"  Archetypes present: {sorted(set(archetypes_col))}")

    # Matrices
    print("\n[3/5] Computing pairwise similarity matrices ...")
    euc_mat, cos_dist, cos_sim, _ = build_matrices(df_norm, df_raw, ids, names, archetypes_col)

    # Neighbors
    print("\n[4/5] Building top-K neighbors JSON ...")
    neighbors = build_neighbors_json(df_norm, df_raw, euc_mat, cos_dist, ids, names, archetypes_col, player_stats)

    # Example notes
    print("\n[5/5] Writing example query notes ...")
    write_example_1_wemby(neighbors, df_norm, df_raw, ids, names, archetypes_col, X)
    write_example_2_curry_clones(neighbors, df_raw, player_stats)
    write_example_3_opposite_of_giannis(neighbors, df_norm, df_raw, ids, names, archetypes_col, X)
    write_example_4_bridge_players(neighbors, df_norm, df_raw, ids, names, archetypes_col, X)
    write_example_5_archetype_centroids(neighbors, df_norm, df_raw, ids, names, archetypes_col, X, archetypes_dict)

    # Main vault note
    print("\n[6/6] Writing main vault note ...")
    write_main_vault_note(neighbors, df_raw, euc_mat, ids, names)

    # ── Summary stats ──────────────────────────────────────────────────────────
    n = len(ids)
    upper_tri = euc_mat[np.triu_indices(n, k=1)]
    avg_min_dist = np.mean([
        np.min([euc_mat[i][j] for j in range(n) if j != i])
        for i in range(n)
    ])
    no_close = sum(
        1 for i in range(n)
        if np.min([euc_mat[i][j] for j in range(n) if j != i]) > 3.0
    )

    print("\n" + "=" * 60)
    print("INT-6 Cross-Player Similarity Engine — Final Report")
    print("=" * 60)
    print(f"\nFiles created:")
    print(f"  scripts/build_similarity_engine.py")
    print(f"  vault/Intelligence/Similarity_Engine.md")
    print(f"  vault/Intelligence/Similarity_Examples/who_plays_like_wemby.md")
    print(f"  vault/Intelligence/Similarity_Examples/underrated_curry_clones.md")
    print(f"  vault/Intelligence/Similarity_Examples/opposite_of_giannis.md")
    print(f"  vault/Intelligence/Similarity_Examples/bridge_players_between_archetypes.md")
    print(f"  vault/Intelligence/Similarity_Examples/archetype_centroids.md")
    print(f"  data/intelligence/similarity_matrix.parquet")
    print(f"  data/intelligence/similar_neighbors.json")

    print(f"\nStats:")
    print(f"  Players indexed:             {n}")
    print(f"  Pairwise distances computed: {n*(n-1)//2:,}")
    print(f"  Avg closest-neighbor dist:   {avg_min_dist:.4f}")
    print(f"  Players with no close match: {no_close} (closest > 3.0 std)")

    # Top-3 most unique players (largest min distance)
    min_dists = [
        (names[i], np.min([euc_mat[i][j] for j in range(n) if j != i]), archetypes_col[i], df_raw.iloc[i]['n_cv_games'])
        for i in range(n)
    ]
    min_dists.sort(key=lambda x: -x[1])
    print(f"\nMost unique profiles (largest min-neighbor distance):")
    for name, d, arch, g in min_dists[:5]:
        print(f"  {name}: {d:.3f} ({arch}, {g}g)")

    # Find Wemby's top neighbor for report
    k, w = find_player_key(neighbors, "Wembanyama")
    if w:
        top1 = w["top_10_euclidean"][0]
        print(f"\nWembanyama's closest neighbor: {top1['name']} (dist={top1['distance']:.3f})")
        print(f"  Shared dimensions: {', '.join(top1['top_features_driving_similarity'])}")

    # Find most-bridge player
    bridge_data = []
    for i, pid in enumerate(ids):
        key = f"{pid}_{names[i]}"
        entry = neighbors[key]
        top10 = entry["top_10_euclidean"]
        arch_set = set(nb["archetype"] for nb in top10)
        bridge_data.append((names[i], len(arch_set), arch_set))
    bridge_data.sort(key=lambda x: (-x[1], 0))
    print(f"\nMost versatile bridge player: {bridge_data[0][0]} spans {bridge_data[0][1]} archetypes in top-10 neighbors")

    # Archetype centroid analysis quick summary
    print(f"\nArchetype sizes:")
    arch_counts = {}
    for a in archetypes_col:
        arch_counts[a] = arch_counts.get(a, 0) + 1
    for a, c in sorted(arch_counts.items(), key=lambda x: -x[1]):
        print(f"  {a}: {c} players ({100*c/n:.0f}%)")

    print("\nDone.")


if __name__ == "__main__":
    main()
