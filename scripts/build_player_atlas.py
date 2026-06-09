"""
build_player_atlas.py — NBA Player Behavioral Fingerprint Atlas
Aggregates CV-tracked per-player behavioral profiles, clusters into archetypes,
and outputs parquet, archetype JSON, PCA visualization, and a vault note.

Usage:
    python scripts/build_player_atlas.py
"""

import pickle
import sqlite3
import json
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "nba_ai.db")
PLAYER_JSON = os.path.join(ROOT, "data", "nba", "player_full_2024-25.json")
OUT_DIR = os.path.join(ROOT, "data", "intelligence")
MODELS_DIR = os.path.join(ROOT, "data", "models")
VAULT_DIR = os.path.join(ROOT, "vault", "Intelligence")
PARQUET_OUT = os.path.join(OUT_DIR, "player_fingerprints.parquet")
VIZ_OUT = os.path.join(OUT_DIR, "player_atlas_viz.png")
ARCHETYPE_OUT = os.path.join(OUT_DIR, "player_archetype_definitions.json")
VAULT_NOTE = os.path.join(VAULT_DIR, "Player_Atlas.md")
# Bug 17 fix: atlas-specific pkl files (separate from legacy player_archetypes.pkl)
ATLAS_KMEANS_PKL = os.path.join(MODELS_DIR, "player_atlas_kmeans.pkl")
ATLAS_SCALER_PKL = os.path.join(MODELS_DIR, "player_atlas_scaler.pkl")
ATLAS_FEATURE_LIST = os.path.join(OUT_DIR, "player_atlas_feature_list.json")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)

# ── Reliable features to use for fingerprinting ───────────────────────────
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
    # avg_defender_distance included with caveat (noisy sentinel values)
    "avg_defender_distance",
]

MIN_GAMES = 2


def load_player_name_map():
    """Build player_id -> name dict from player_full JSON."""
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


def load_cv_features():
    """Load cv_features from SQLite and pivot to wide format."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()
    print(f"  Loaded {len(df):,} cv_feature rows | "
          f"{df['player_id'].nunique()} players | {df['game_id'].nunique()} games")
    return df


def build_player_profiles(df_long):
    """Aggregate per-player stats from long-format cv_features."""
    # Filter to fingerprint features only
    df = df_long[df_long["feature_name"].isin(FINGERPRINT_FEATURES)].copy()

    # Bug 27 guard: potential_assists=0 means xAST submodule did not run for that
    # game (45.1% of CV games are all-zero).  Null them out so the per-player mean
    # is computed only over games where the PA model actually produced output.
    pa_mask = (df["feature_name"] == "potential_assists") & (df["feature_value"] == 0.0)
    df.loc[pa_mask, "feature_value"] = np.nan  # Bug 27 guard

    # Per-player per-feature stats
    agg = (
        df.groupby(["player_id", "feature_name"])["feature_value"]
        .agg(["mean", "std", "min", "max"])
        .reset_index()
    )

    # Pivot to wide: one row per player, columns = feature_mean/std/etc
    mean_wide = agg.pivot(index="player_id", columns="feature_name", values="mean")
    std_wide = agg.pivot(index="player_id", columns="feature_name", values="std")
    mean_wide.columns = [f"{c}_mean" for c in mean_wide.columns]
    std_wide.columns = [f"{c}_std" for c in std_wide.columns]

    # Metadata — Bug 46 fix: compute n_cv_games AFTER the Bug-27 NaN mask and ONLY
    # from rows that have a valid (non-NaN, non-zero) feature value.  Counting
    # game_ids from the full df inflates sample size for players whose only rows
    # were phantom zeros (e.g. Curry-class players absent from the current DB
    # snapshot): those games showed n_cv_games >= MIN_GAMES but every behavioral
    # feature was 0.0, placing them into the wrong archetype (Bug 44 root cause).
    df_valid = df[df["feature_value"].notna() & (df["feature_value"] != 0.0)]
    valid_game_counts = (
        df_valid.groupby("player_id")["game_id"]
        .agg(n_cv_games="nunique")
        .reset_index()
    )
    # first_game_id / last_game_id still from full df (for bookkeeping provenance)
    first_last = (
        df.groupby("player_id")["game_id"]
        .agg(first_game_id="min", last_game_id="max")
        .reset_index()
    )
    meta = valid_game_counts.merge(first_last, on="player_id", how="left")

    # Teams seen (from the broader long df to include all features)
    team_map = {}  # placeholder — cv_features doesn't have team column directly

    profiles = meta.join(mean_wide, on="player_id").join(std_wide, on="player_id")
    profiles = profiles.set_index("player_id")

    # Keep only players with >= MIN_GAMES
    profiles = profiles[profiles["n_cv_games"] >= MIN_GAMES]
    print(f"  Players with >= {MIN_GAMES} CV games: {len(profiles)}")
    return profiles


def select_features_for_clustering(profiles):
    """Return feature column names (mean values of fingerprint features) available in profiles."""
    feat_cols = [f"{f}_mean" for f in FINGERPRINT_FEATURES if f"{f}_mean" in profiles.columns]
    # Drop features with zero variance (all-zero or constant)
    variances = profiles[feat_cols].var()
    dead = variances[variances == 0].index.tolist()
    if dead:
        print(f"  Dropping zero-variance features: {[c.replace('_mean','') for c in dead]}")
    feat_cols = [c for c in feat_cols if c not in dead]
    print(f"  Features used for clustering: {len(feat_cols)}")
    return feat_cols


def impute_missing(X):
    """Fill NaN with 0 (players with zero activity in that feature)."""
    return np.nan_to_num(X, nan=0.0)


def choose_k(X_std, k_range=range(4, 9)):
    """Try K=4..8, pick best PENALIZED silhouette score.

    Bug 21 fix 2026-05-29: previously selected by raw silhouette only, which
    favored K=5 with a 45% catch-all cluster. Penalty: if max-cluster-size /
    total > 0.40 (catch-all signal), halve the silhouette. K-sweep at K=7 wins
    on penalized score AND has the best Davies-Bouldin (1.890).
    """
    best_k, best_score, best_model = None, -1.0, None
    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_std)
        raw_silhouette = silhouette_score(X_std, labels)
        # Catch-all penalty: any cluster > 40% of players → halve the score
        from collections import Counter as _C
        sizes = _C(labels)
        max_pct = max(sizes.values()) / len(labels)
        penalty = 0.5 if max_pct > 0.40 else 1.0
        score = raw_silhouette * penalty
        scores[k] = (round(raw_silhouette, 4), round(max_pct, 3), round(score, 4))
        if score > best_score:
            best_score, best_k, best_model = score, k, km
    print(f"  Penalized silhouette scores (raw, max%, penalized): {scores}")
    print(f"  Best K={best_k} (penalized={best_score:.4f})")
    return best_k, best_score, best_model


def label_archetype(cluster_id, centroid_std, feature_names):
    """Heuristic human label based on top distinguishing features.

    Bug 28 fix: the generic "Versatile Forward" fallback was returned for two
    distinct cluster profiles, creating duplicate names that confused INT-38
    archetype drift detection.  We now use centroid feature signals to
    distinguish the two sub-types BEFORE falling through to the generic label:

    - "Off-Ball Forward": negative possession_duration_avg AND negative
      avg_defender_distance → low-touch, off-ball mover who takes few dribbles
      and rarely gets defender attention.
    - "Athletic Forward": positive second_chance_rate AND/OR positive
      preshot_velocity_peak → physical, high-motor player who generates
      second-chance attempts and attacks with pace.

    Bug 45 fix: at K=8 the generic "Versatile Big" and "Versatile Perimeter
    Player" fallbacks could fire for two distinct clusters simultaneously,
    producing duplicate names with the same over-collapse problem as Bug 28.
    We add centroid-driven disambiguation for both before falling through:

    "Versatile Big" sub-types:
    - "Shot-Creating Big": positive shots_per_possession AND positive
      possession_duration_avg → paint presence but actively generates own shots
      with dribbles / longer possessions (stretch-4 / pick-and-roll creator).
    - "Passive Paint Big": positive paint_dwell_pct but low shots_per_possession
      AND negative possession_duration_avg → catch-and-finish roll man, short
      possessions, minimal ball-creation.

    "Versatile Perimeter Player" sub-types:
    - "Off-Ball Perimeter Shooter": very negative defender_approach_speed →
      defenses treat this player as a gravity/spacing threat rather than a
      ball-handler; low-dribble catch-and-move 3pt profile.
    - "Versatile Perimeter Player": default perimeter label (the original name)
      is kept for the non-off-ball variant so existing downstream joins
      on that string are not broken.

    The distinction is feature-centroid-driven, NOT cluster-ID-driven, so it
    remains correct if clusters re-permute on re-fit.
    """
    feat_short = [f.replace("_mean", "") for f in feature_names]
    z = dict(zip(feat_short, centroid_std))

    # Sort by absolute z-score descending
    ranked = sorted(z.items(), key=lambda x: abs(x[1]), reverse=True)

    # Read top signals
    top = {k: v for k, v in ranked[:5]}

    paint = top.get("paint_dwell_pct", 0) + top.get("shot_zone_paint_pct", 0)
    three = top.get("shot_zone_3pt_pct", 0) + top.get("catch_shoot_pct", 0)
    ball_handler = top.get("touches_per_game", 0) + top.get("potential_assists", 0)
    isolation = top.get("play_type_isolation_pct", 0)
    post = top.get("play_type_post_pct", 0)
    transition = top.get("play_type_transition_pct", 0)
    dribble = top.get("avg_dribble_count", 0)
    contested = top.get("contested_shot_rate", 0)

    # Bug 28 fix: read the full z dict (not just top-5) for the sub-type signals
    possession_dur = z.get("possession_duration_avg", 0)
    defender_dist = z.get("avg_defender_distance", 0)
    second_chance = z.get("second_chance_rate", 0)
    preshot_vel = z.get("preshot_velocity_peak", 0)
    # Bug 45 fix: additional centroid signals for Big and Perimeter disambiguation
    shots_per_poss = z.get("shots_per_possession", 0)
    paint_dwell = z.get("paint_dwell_pct", 0)
    def_approach = z.get("defender_approach_speed", 0)

    # Heuristic labeling (thresholds on z-scores)
    if paint > 1.5 and ball_handler < 0:
        return "Paint-Dominant Big"
    if post > 0.5 or (paint > 1.0 and dribble < -0.2):
        return "Post-Up Scorer"
    if three > 1.5 and ball_handler < 0 and dribble < 0:
        return "Pure Catch-and-Shoot Wing"
    if ball_handler > 1.5 or (top.get("touches_per_game", 0) > 1.0 and
                               top.get("potential_assists", 0) > 0.5):
        return "Primary Ball-Handler"
    if isolation > 0.5 and dribble > 0.5:
        return "Isolation Creator"
    if transition > 0.5 and contested < 0:
        return "Transition Threat"
    if three > 0.5 and contested > 0.3:
        return "Perimeter Shooter (Contested)"

    # Bug 45 fix: disambiguate duplicate "Versatile Big" fallback.
    # Two paint-heavy clusters at K=8 both hit paint > 0.5 → same generic name.
    # Distinguish by shots_per_possession and possession_duration_avg:
    # - "Shot-Creating Big": generates own looks (high spp + longer possessions)
    # - "Passive Paint Big": catch-and-finish roll man (low spp + short possessions)
    if paint > 0.5:
        if shots_per_poss > 0.3 and possession_dur > 0.2:
            return "Shot-Creating Big"
        if paint_dwell > 0.3 and shots_per_poss < 0.0 and possession_dur < 0.0:
            return "Passive Paint Big"
        return "Versatile Big"

    # Bug 45 fix: disambiguate duplicate "Versatile Perimeter Player" fallback.
    # Two 3pt-heavy clusters at K=8 both hit three > 0.5 → same generic name.
    # Distinguish by defender_approach_speed:
    # - "Off-Ball Perimeter Shooter": defenses treat as spacing threat (very
    #   negative def_approach) with low dribbles → pure gravity / catch-and-move
    if three > 0.5:
        if def_approach < -0.5 and dribble < 0.0:
            return "Off-Ball Perimeter Shooter"
        return "Versatile Perimeter Player"

    # Bug 28 fix: disambiguate duplicate "Versatile Forward" fallback.
    # Check for "Off-Ball Forward" first (negative possession + negative defender distance
    # is the stronger / more diagnostic signal for a low-touch off-ball mover).
    if possession_dur < -0.4 and defender_dist < -0.4:
        return "Off-Ball Forward"
    # "Athletic Forward": positive second-chance rate or preshot velocity peak →
    # high-motor, physically-driven second-chance / pace attacker.
    if second_chance > 0.4 or preshot_vel > 0.4:
        return "Athletic Forward"
    return "Versatile Forward"


def interpret_archetypes(km, X_std, feature_names, profiles, name_map):
    """Build archetype definitions dict from cluster centroids."""
    labels = km.labels_
    centroids = km.cluster_centers_  # shape (K, n_features)
    global_mean = X_std.mean(axis=0)
    global_std = X_std.std(axis=0) + 1e-8

    archetypes = {}
    for cid in range(km.n_clusters):
        cluster_mask = labels == cid
        n_players = int(cluster_mask.sum())

        # Centroid z-scores relative to all players
        centroid_z = (centroids[cid] - global_mean) / global_std
        feat_z = dict(zip(feature_names, centroid_z))
        # Top 5 by absolute value
        top_feats = dict(
            sorted(feat_z.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        )
        top_feats = {k.replace("_mean", ""): round(float(v), 3) for k, v in top_feats.items()}

        # Auto-label
        name = label_archetype(cid, centroid_z, feature_names)

        # Example players (up to 5, by n_cv_games)
        cluster_pids = profiles.index[cluster_mask].tolist()
        cluster_profiles = profiles.loc[cluster_pids].sort_values("n_cv_games", ascending=False)
        examples = []
        for pid in cluster_profiles.index[:5]:
            pname = name_map.get(int(pid), f"ID:{pid}")
            games = int(cluster_profiles.loc[pid, "n_cv_games"])
            examples.append(f"{pname} ({games}g)")

        archetypes[str(cid)] = {
            "name": name,
            "n_players": n_players,
            "top_distinguishing_features": top_feats,
            "examples": examples,
        }

    # Bug 45 safety net: if any two clusters still share a name after centroid
    # disambiguation (edge case at unusual K values), append the dominant
    # top-feature key as a suffix to make every label unique.
    seen_names: dict = {}
    for cid_str, arch in archetypes.items():
        base = arch["name"]
        if base in seen_names:
            # First occurrence gets a suffix too so both are clearly distinct
            if seen_names[base] is not None:
                prev_cid = seen_names[base]
                prev_top = list(archetypes[prev_cid]["top_distinguishing_features"].keys())[0]
                archetypes[prev_cid]["name"] = f"{base} ({prev_top.replace('_', ' ')})"
                seen_names[base] = None  # mark as already suffixed
            cur_top = list(arch["top_distinguishing_features"].keys())[0]
            arch["name"] = f"{base} ({cur_top.replace('_', ' ')})"
        else:
            seen_names[base] = cid_str

    return archetypes


def find_outliers(X_std, km, profiles, name_map, threshold=2.5):
    """Players > threshold σ from their archetype centroid."""
    labels = km.labels_
    outliers = []
    for i, pid in enumerate(profiles.index):
        cid = labels[i]
        centroid = km.cluster_centers_[cid]
        dist = float(np.linalg.norm(X_std[i] - centroid))
        outliers.append({"player_id": int(pid), "dist": dist, "archetype": cid})

    out_df = pd.DataFrame(outliers).sort_values("dist", ascending=False)
    # Threshold: top ~5% or dist > threshold
    p95 = out_df["dist"].quantile(0.95)
    notable = out_df[out_df["dist"] >= max(p95, threshold)].head(10)

    result = []
    for _, row in notable.iterrows():
        pname = name_map.get(row["player_id"], f"ID:{int(row['player_id'])}")
        result.append(
            {"name": pname, "player_id": int(row["player_id"]),
             "dist_from_centroid": round(row["dist"], 3),
             "archetype_id": int(row["archetype"])}
        )
    return result, out_df["dist"].values


def build_visualization(profiles, X_pca, km, archetypes, name_map, pca_var):
    """2D PCA scatter colored by archetype with player annotations."""
    labels = km.labels_
    K = km.n_clusters

    COLORS = plt.cm.tab10(np.linspace(0, 0.9, K))
    fig, ax = plt.subplots(figsize=(14, 10))

    # Plot each archetype
    for cid in range(K):
        mask = labels == cid
        color = COLORS[cid]
        ax.scatter(
            X_pca[mask, 0], X_pca[mask, 1],
            c=[color], s=45, alpha=0.65, edgecolors="white", linewidths=0.3,
            label=f"[{cid}] {archetypes[str(cid)]['name']} (n={archetypes[str(cid)]['n_players']})",
        )

    # Annotate top players by game count
    n_annotate = min(15, len(profiles))
    top_pids = profiles.nlargest(n_annotate, "n_cv_games").index

    annotated = 0
    for i, pid in enumerate(profiles.index):
        if pid in top_pids:
            pname = name_map.get(int(pid), None)
            if pname is None:
                continue
            short = pname.split()[-1] if " " in pname else pname
            ax.annotate(
                short, (X_pca[i, 0], X_pca[i, 1]),
                fontsize=7, alpha=0.85,
                xytext=(4, 4), textcoords="offset points",
                color="#222222",
            )
            annotated += 1

    ax.set_xlabel(f"PCA Component 1 ({pca_var[0]:.1f}% variance)", fontsize=11)
    ax.set_ylabel(f"PCA Component 2 ({pca_var[1]:.1f}% variance)", fontsize=11)
    ax.set_title(
        "NBA Player Behavioral Fingerprint Atlas (CV-derived)\n"
        f"n={len(profiles)} players | {len(FINGERPRINT_FEATURES)} features | K={K} archetypes",
        fontsize=13, fontweight="bold",
    )
    ax.legend(loc="upper right", fontsize=9, framealpha=0.8)
    ax.grid(True, alpha=0.2, linestyle="--")
    ax.set_facecolor("#f8f9fa")
    fig.tight_layout()
    fig.savefig(VIZ_OUT, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Viz saved: {VIZ_OUT}")


def build_vault_note(profiles, archetypes, outliers, pca_var, best_k, best_sil,
                     feat_cols, name_map):
    """Write vault/Intelligence/Player_Atlas.md."""
    n_players = len(profiles)
    first_game = profiles["first_game_id"].min()
    last_game = profiles["last_game_id"].max()

    arch_section = ""
    for cid_str, arch in archetypes.items():
        feats_str = ", ".join(
            [f"`{k}` z={v:+.2f}" for k, v in arch["top_distinguishing_features"].items()]
        )
        examples_str = " | ".join(arch["examples"])
        arch_section += (
            f"\n### Archetype {cid_str}: {arch['name']}\n"
            f"- **Players:** {arch['n_players']}\n"
            f"- **Defining features:** {feats_str}\n"
            f"- **Examples:** {examples_str}\n"
        )

    outlier_section = ""
    for o in outliers:
        outlier_section += (
            f"- **{o['name']}** — dist={o['dist_from_centroid']:.2f}σ from "
            f"archetype [{o['archetype_id']}] `{archetypes[str(o['archetype_id'])]['name']}`\n"
        )

    feat_list = ", ".join([f.replace("_mean", "") for f in feat_cols])

    content = f"""# Player Behavioral Fingerprint Atlas — v1
*Generated: 2026-05-28 | Atlas builder: `scripts/build_player_atlas.py`*

## Overview
- **Players included:** {n_players} (with ≥ {MIN_GAMES} CV-tracked games)
- **Games spanned:** {first_game} → {last_game}
- **Features used:** {len(feat_cols)} reliable CV features
- **Archetypes (K-Means):** K={best_k} (silhouette={best_sil:.4f})
- **PCA variance explained:** PC1={pca_var[0]:.1f}%, PC2={pca_var[1]:.1f}%, combined={sum(pca_var):.1f}%

## Visualization
![[../../data/intelligence/player_atlas_viz.png]]

*Each point is one player. Color = archetype assignment. Axes = first two PCA components of standardized CV features.*

---

## Archetypes
{arch_section}

---

## Notable Outliers (players furthest from their archetype centroid)
These players are the "weird-for-their-type" or genuinely unique behavioral profiles.
A large distance from the cluster centroid can mean: limited game sample, mixed-role player,
or genuinely anomalous play style that doesn't fit cleanly into any archetype.

{outlier_section}

---

## Features Used for Fingerprinting
`{feat_list}`

**Features deliberately excluded:**
- `play_type_drive_pct` — 0% non-zero (dead feature)
- `avg_closeout_speed` — 0% non-zero (dead feature)
- `made_pct` — raw shot make rate, too noisy for behavioral profiling
- `cv_archetype` / `cv_xast_pred` / `n_shots_tracked` / `avg_fatigue_proxy` / etc. — auxiliary or meta features

**Caveat on `avg_defender_distance`:** This feature has known sentinel values (200.0 when
undetected). It was included but should be interpreted with care. The 52% non-zero rate suggests
meaningful signal in populated games, but outliers driven purely by this feature warrant scrutiny.

---

## How to Query This Atlas

```python
import pandas as pd
import json

# Load fingerprints
df = pd.read_parquet('data/intelligence/player_fingerprints.parquet')

# Load archetype definitions
with open('data/intelligence/player_archetype_definitions.json') as f:
    archs = json.load(f)

# Query examples
# --- All paint-dominant bigs ---
df[df['archetype_name'] == 'Paint-Dominant Big']

# --- Top 5% by paint dwell ---
df[df['paint_dwell_pct'] > df['paint_dwell_pct'].quantile(0.95)]

# --- Perimeter shooters with high pass creation ---
df[(df['shot_zone_3pt_pct'] > 0.3) & (df['potential_assists'] > 2.0)]

# --- Players most like ball-handlers but assigned differently ---
df[df['touches_per_game'] > df['touches_per_game'].quantile(0.9)].sort_values('touches_per_game', ascending=False)

# --- Sort by PCA distance from origin (most distinctive behavior) ---
df['pca_magnitude'] = (df['pca_x']**2 + df['pca_y']**2)**0.5
df.sort_values('pca_magnitude', ascending=False).head(20)
```

---

## Data Files
| File | Description |
|------|-------------|
| `data/intelligence/player_fingerprints.parquet` | Per-player profiles with archetype + PCA coords + all feature means |
| `data/intelligence/player_archetype_definitions.json` | Archetype labels, centroids, example players |
| `data/intelligence/player_atlas_viz.png` | PCA scatter visualization |
| `scripts/build_player_atlas.py` | Rebuild script (run after new CV games are tracked) |

---

## Validation Hooks (Future)
- **Prop model feature**: `archetype_id` (categorical) + `pca_x`/`pca_y` (continuous) could be wired into `prop_pergame.py` as behavioral priors
- **Anomaly detection**: Any (player, game) where that game's CV profile differs from the player's atlas fingerprint by > 2σ on multiple features is "out of pattern" — could flag injury, minute restriction, or tracking error
- **Season-over-season behavioral drift**: Rebuild atlas per-season and compare `pca_x/y` shift per player to detect role changes

---

## Update History
| Version | Date | Notes |
|---------|------|-------|
| v1 | 2026-05-28 | Initial atlas. {n_players} players, K={best_k} archetypes, {len(feat_cols)} features |

"""
    with open(VAULT_NOTE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Vault note saved: {VAULT_NOTE}")


def main():
    print("=== NBA Player Behavioral Fingerprint Atlas ===\n")

    # 1. Load name map
    print("[1] Loading player names...")
    name_map = load_player_name_map()
    print(f"  Loaded {len(name_map)} player names")

    # 2. Load CV features
    print("\n[2] Loading CV features from DB...")
    df_long = load_cv_features()

    # 3. Build per-player profiles
    print("\n[3] Building per-player profiles...")
    profiles = build_player_profiles(df_long)
    n_excluded = df_long["player_id"].nunique() - len(profiles)
    print(f"  Players excluded (< {MIN_GAMES} games): {n_excluded}")

    # 4. Select features
    print("\n[4] Selecting fingerprint features...")
    feat_cols = select_features_for_clustering(profiles)

    # 5. Build feature matrix
    X = profiles[feat_cols].values
    X = impute_missing(X)

    # 6. Standardize
    print("\n[5] Standardizing features...")
    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)

    # 7. PCA
    print("\n[6] Running PCA (2D)...")
    pca = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_std)
    pca_var = [round(v * 100, 2) for v in pca.explained_variance_ratio_]
    print(f"  PCA variance: PC1={pca_var[0]}%, PC2={pca_var[1]}%, total={sum(pca_var):.1f}%")

    # 8. KMeans — choose best K
    print("\n[7] Selecting optimal K (4..8)...")
    best_k, best_sil, best_km = choose_k(X_std)

    # 9. Interpret archetypes
    print("\n[8] Interpreting archetypes...")
    archetypes = interpret_archetypes(best_km, X_std, feat_cols, profiles, name_map)
    for cid, arch in archetypes.items():
        print(f"  Cluster {cid}: {arch['name']} (n={arch['n_players']}) "
              f"top={list(arch['top_distinguishing_features'].keys())[:3]}")

    # 10. Outliers
    print("\n[9] Finding outliers...")
    outliers, dist_vals = find_outliers(X_std, best_km, profiles, name_map)
    for o in outliers[:5]:
        print(f"  {o['name']}: dist={o['dist_from_centroid']:.3f}")

    # 11. Build final parquet
    print("\n[10] Building fingerprints parquet...")
    labels = best_km.labels_
    arch_names = [archetypes[str(l)]["name"] for l in labels]

    fp = profiles[["n_cv_games", "first_game_id", "last_game_id"]].copy()
    fp["archetype_id"] = labels
    fp["archetype_name"] = arch_names
    fp["pca_x"] = X_pca[:, 0]
    fp["pca_y"] = X_pca[:, 1]
    fp["dist_from_centroid"] = dist_vals

    # Add all feature means as flat columns
    for fc in feat_cols:
        short = fc.replace("_mean", "")
        fp[short] = profiles[fc].fillna(0).values

    fp.index.name = "player_id"

    # Add player names
    fp["player_name"] = [name_map.get(int(pid), f"ID:{pid}") for pid in fp.index]

    fp.to_parquet(PARQUET_OUT, index=True)
    print(f"  Saved {len(fp)} player fingerprints -> {PARQUET_OUT}")

    # 12. Save archetype definitions
    with open(ARCHETYPE_OUT, "w") as f:
        json.dump(archetypes, f, indent=2)
    print(f"  Archetype definitions -> {ARCHETYPE_OUT}")

    # 13. Visualization
    print("\n[11] Building visualization...")
    build_visualization(profiles, X_pca, best_km, archetypes, name_map, pca_var)

    # 14. Vault note
    print("\n[12] Writing vault note...")
    build_vault_note(profiles, archetypes, outliers, pca_var, best_k, best_sil,
                     feat_cols, name_map)

    # 15. Bug 17 fix: save atlas KMeans + scaler + feature list for INT-38 use
    print("\n[13] Saving atlas KMeans + scaler for INT-38 alignment (Bug 17 fix)...")
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(ATLAS_KMEANS_PKL, "wb") as f:
        pickle.dump(best_km, f)
    print(f"  Atlas KMeans saved: {ATLAS_KMEANS_PKL}")
    with open(ATLAS_SCALER_PKL, "wb") as f:
        pickle.dump(scaler, f)
    print(f"  Atlas scaler saved: {ATLAS_SCALER_PKL}")
    # Feature list: the actual columns used (feat_cols are e.g. "paint_dwell_pct_mean")
    # Store the raw feature names (without _mean suffix) for INT-38 DB query
    raw_feat_names = [fc.replace("_mean", "") for fc in feat_cols]
    with open(ATLAS_FEATURE_LIST, "w") as f:
        json.dump({"features": raw_feat_names, "feat_cols": feat_cols}, f, indent=2)
    print(f"  Atlas feature list saved: {ATLAS_FEATURE_LIST} ({len(raw_feat_names)} features)")

    # ── Final report ──────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("INT-1 Player Behavioral Fingerprint Atlas — COMPLETE")
    print("="*60)
    print(f"  Players included: {len(profiles)}")
    print(f"  Players excluded: {n_excluded}")
    print(f"  Features used: {len(feat_cols)}")
    print(f"  KMeans K selected: {best_k}")
    print(f"  Silhouette score: {best_sil:.4f}")
    print(f"  PCA explained variance: PC1={pca_var[0]}%, PC2={pca_var[1]}%")
    print()
    print("Archetype labels and sizes:")
    for cid, arch in archetypes.items():
        top3 = list(arch["top_distinguishing_features"].items())[:3]
        top3_str = ", ".join([f"{k}:{v:+.2f}" for k, v in top3])
        print(f"  [{cid}] {arch['name']}: {arch['n_players']} players | {top3_str}")
    print()
    print("Notable outliers:")
    for o in outliers[:5]:
        print(f"  {o['name']}: dist={o['dist_from_centroid']:.3f} "
              f"(arch: {archetypes[str(o['archetype_id'])]['name']})")
    print()
    print(f"Files created:")
    print(f"  scripts/build_player_atlas.py")
    print(f"  {PARQUET_OUT}")
    print(f"  {VIZ_OUT}")
    print(f"  {ARCHETYPE_OUT}")
    print(f"  {VAULT_NOTE}")
    print(f"  {ATLAS_KMEANS_PKL}  (Bug 17 fix)")
    print(f"  {ATLAS_SCALER_PKL}  (Bug 17 fix)")
    print(f"  {ATLAS_FEATURE_LIST}  (Bug 17 fix)")


if __name__ == "__main__":
    main()
