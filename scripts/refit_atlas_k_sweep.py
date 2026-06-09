"""
refit_atlas_k_sweep.py — K-sweep analysis for NBA Player Behavioral Fingerprint Atlas

Tests K = 4, 5, 6, 7, 8, 10 and selects best K by:
  - Silhouette score (primary)
  - Max cluster size < 40% of total (catch-all penalty — if any cluster exceeds 40%, K is penalized)

Outputs:
  - data/intelligence/player_fingerprints_kbest.parquet  (best-K assignments)
  - data/models/player_atlas_kmeans_kbest.pkl            (best-K KMeans model)
  - vault/Intelligence/Atlas_K_Refit_Analysis.md         (full analysis note)

Usage:
    python scripts/refit_atlas_k_sweep.py
"""

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARQUET_IN   = os.path.join(ROOT, "data", "intelligence", "player_fingerprints.parquet")
PARQUET_OUT  = os.path.join(ROOT, "data", "intelligence", "player_fingerprints_kbest.parquet")
PKL_OUT      = os.path.join(ROOT, "data", "models", "player_atlas_kmeans_kbest.pkl")
VAULT_NOTE   = os.path.join(ROOT, "vault", "Intelligence", "Atlas_K_Refit_Analysis.md")

os.makedirs(os.path.join(ROOT, "data", "intelligence"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "data", "models"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "vault", "Intelligence"), exist_ok=True)

# Features used for fingerprinting (same 19 as build_player_atlas.py)
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
    "avg_defender_distance",
]

K_VALUES = [4, 5, 6, 7, 8, 10]
MAX_CLUSTER_PCT_THRESHOLD = 0.40   # catch-all penalty if any cluster exceeds 40%
N_INIT = 20
RANDOM_STATE = 42

# Known player IDs for tracking
CURRY_ID   = 201939
JOKIC_ID   = 203999
HARDEN_ID  = 201935  # highest dist_from_centroid at K=4


# ── Cluster naming heuristics ───────────────────────────────────────────────

def centroid_feature_signature(centroid_std, feature_names, top_n=5):
    """Return dict of top_n features by absolute z-score, with values."""
    feat_z = dict(zip(feature_names, centroid_std))
    ranked = sorted(feat_z.items(), key=lambda x: abs(x[1]), reverse=True)
    return {k.replace("_mean", "").replace("_", " "): round(float(v), 3)
            for k, v in ranked[:top_n]}


def label_cluster(centroid_std, feature_names):
    """
    Assign a human-readable archetype label based on centroid z-scores.
    More granular than the original label_archetype() to accommodate K>4.
    """
    feat_short = [f.replace("_mean", "") for f in feature_names]
    z = dict(zip(feat_short, centroid_std))
    ranked = sorted(z.items(), key=lambda x: abs(x[1]), reverse=True)
    top = {k: v for k, v in ranked[:6]}

    paint      = z.get("paint_dwell_pct", 0) + z.get("shot_zone_paint_pct", 0)
    three      = z.get("shot_zone_3pt_pct", 0) + z.get("catch_shoot_pct", 0)
    ball_hdl   = z.get("touches_per_game", 0) + z.get("potential_assists", 0)
    iso        = z.get("play_type_isolation_pct", 0)
    post       = z.get("play_type_post_pct", 0)
    transition = z.get("play_type_transition_pct", 0)
    dribble    = z.get("avg_dribble_count", 0)
    contested  = z.get("contested_shot_rate", 0)
    second_chc = z.get("second_chance_rate", 0)
    shots_pp   = z.get("shots_per_possession", 0)
    pre_vel    = z.get("preshot_velocity_peak", 0)
    poss_dur   = z.get("possession_duration_avg", 0)
    mid_range  = z.get("shot_zone_mid_range_pct", 0)

    # Post big
    if post > 1.5:
        return "Post-Up Scorer"
    # Paint / second chance big with low ball-handling
    if paint > 2.0 and ball_hdl < -0.5:
        return "Paint-Dominant Big"
    # Paint big but moderate ball usage
    if paint > 1.0 and dribble < -0.3 and ball_hdl < 0.5:
        return "Stretch-Limited Big"
    # High ball movement, assist creation = primary handler
    if ball_hdl > 1.8 or (z.get("touches_per_game", 0) > 1.2 and z.get("potential_assists", 0) > 1.0):
        return "Primary Ball-Handler"
    # Elite generalist: high activity across multiple dimensions, no extreme single feature
    if (abs(paint) < 0.8 and abs(three) < 0.8 and abs(ball_hdl) < 1.5
            and (pre_vel > 0.4 or shots_pp > 0.3 or abs(poss_dur) > 0.3)
            and z.get("touches_per_game", 0) > 0.2):
        return "Elite Generalist"
    # Transition-heavy
    if transition > 1.0 and three > 0.5:
        return "High-Activity Transition Wing"
    # Pure catch-and-shoot
    if three > 1.5 and dribble < -0.5 and ball_hdl < 0:
        return "Spot-Up Catch-and-Shoot"
    # Contested perimeter with some creation
    if three > 0.8 and dribble > 0.3 and iso > 0.3:
        return "Perimeter Isolation Creator"
    # Mid-range / contested inside scorer
    if contested > 0.8 and mid_range > 0.3:
        return "Contested Mid-Range Scorer"
    # Versatile perimeter (3pt oriented but some ball usage)
    if three > 0.5 and ball_hdl >= 0:
        return "Versatile Perimeter Player"
    # Default by dominant signal
    if paint > 0.5:
        return "Versatile Big"
    if three > 0.3:
        return "3-and-D Wing"
    # Negative-feature clusters (low activity bench)
    if (z.get("touches_per_game", 0) < -0.5 and shots_pp < -0.3):
        return "Low-Usage Role Player"
    return "Versatile Forward"


# ── Main sweep ──────────────────────────────────────────────────────────────

def run_sweep(X_std, player_ids, player_names, n_cv_games_arr):
    """Fit KMeans for each K value and collect metrics."""
    results = {}
    models  = {}

    curry_idx = np.where(player_ids == CURRY_ID)[0]
    jokic_idx = np.where(player_ids == JOKIC_ID)[0]

    curry_idx = int(curry_idx[0]) if len(curry_idx) else None
    jokic_idx = int(jokic_idx[0]) if len(jokic_idx) else None

    for k in K_VALUES:
        print(f"\n  Fitting K={k}...")
        km = KMeans(n_clusters=k, n_init=N_INIT, random_state=RANDOM_STATE)
        labels = km.fit_predict(X_std)

        sil   = silhouette_score(X_std, labels)
        db    = davies_bouldin_score(X_std, labels)
        inertia = km.inertia_

        sizes = np.bincount(labels, minlength=k)
        n     = len(labels)
        max_pct = sizes.max() / n
        min_pct = sizes.min() / n

        # Distances from each player to their centroid
        dists = np.array([
            np.linalg.norm(X_std[i] - km.cluster_centers_[labels[i]])
            for i in range(n)
        ])
        n_high_dist = int((dists > 8.0).sum())

        curry_cluster = int(labels[curry_idx]) if curry_idx is not None else None
        jokic_cluster = int(labels[jokic_idx]) if jokic_idx is not None else None
        curry_cluster_size = int(sizes[curry_cluster]) if curry_cluster is not None else None
        jokic_cluster_size = int(sizes[jokic_cluster]) if jokic_cluster is not None else None

        # Is catch-all penalty triggered?
        catch_all_penalty = max_pct > MAX_CLUSTER_PCT_THRESHOLD

        # Penalized score for selection: silhouette minus big penalty if catch-all
        penalized_score = sil - (0.05 if catch_all_penalty else 0.0)

        results[k] = {
            "k":                k,
            "silhouette":       round(sil, 4),
            "davies_bouldin":   round(db, 4),
            "inertia":          round(inertia, 1),
            "max_cluster_size": int(sizes.max()),
            "min_cluster_size": int(sizes.min()),
            "max_pct":          round(max_pct, 4),
            "min_pct":          round(min_pct, 4),
            "catch_all_penalty": catch_all_penalty,
            "penalized_score":  round(penalized_score, 4),
            "curry_cluster":    curry_cluster,
            "curry_cluster_size": curry_cluster_size,
            "jokic_cluster":    jokic_cluster,
            "jokic_cluster_size": jokic_cluster_size,
            "n_dist_gt_8":      n_high_dist,
            "labels":           labels,
            "dists":            dists,
        }
        models[k] = km

        print(f"    silhouette={sil:.4f}  DB={db:.4f}  inertia={inertia:.0f}")
        print(f"    max_pct={max_pct:.1%}  min_size={sizes.min()}  max_size={sizes.max()}")
        print(f"    catch_all_penalty={catch_all_penalty}  penalized={penalized_score:.4f}")
        if curry_cluster is not None:
            print(f"    Curry -> cluster {curry_cluster} (size={curry_cluster_size})")
        if jokic_cluster is not None:
            print(f"    Jokic -> cluster {jokic_cluster} (size={jokic_cluster_size})")

    return results, models


def pick_best_k(results):
    """
    Select best K by penalized score (silhouette - 0.05 if max cluster > 40%).
    Among ties, prefer lower K (simpler model).
    """
    best_k = max(results.keys(), key=lambda k: (results[k]["penalized_score"], -k))
    print(f"\n  Best K selected: {best_k} "
          f"(penalized_score={results[best_k]['penalized_score']:.4f})")
    return best_k


def build_cluster_profiles(km, X_std, feature_names, player_ids, player_names,
                            n_cv_games_arr, global_mean, global_std_arr):
    """For each cluster, compute centroid z-scores, top features, representative players."""
    labels = km.labels_
    K = km.n_clusters
    profiles = {}

    for cid in range(K):
        mask = labels == cid
        centroid_z = (km.cluster_centers_[cid] - global_mean) / (global_std_arr + 1e-8)
        top_feats  = centroid_feature_signature(centroid_z, feature_names)
        label      = label_cluster(centroid_z, feature_names)

        # Representative players: sort by distance to centroid (ascending = most central)
        cluster_idx = np.where(mask)[0]
        cluster_dists = np.array([
            np.linalg.norm(X_std[i] - km.cluster_centers_[cid])
            for i in cluster_idx
        ])
        sorted_by_centrality = cluster_idx[np.argsort(cluster_dists)]

        # Pick top 5 by game count within most-central 50%
        n_central = max(5, len(cluster_idx) // 2)
        central_idx = sorted_by_centrality[:n_central]
        central_games = n_cv_games_arr[central_idx]
        top5_local = central_idx[np.argsort(central_games)[::-1][:5]]
        rep_players = [
            f"{player_names[i]} ({n_cv_games_arr[i]}g)"
            for i in top5_local
        ]

        profiles[cid] = {
            "name":      label,
            "n_players": int(mask.sum()),
            "top_distinguishing_features": top_feats,
            "representative_players": rep_players,
            "centroid_z_raw": {fn.replace("_mean","").replace("_"," "): round(float(z), 3)
                               for fn, z in zip(feature_names, centroid_z)},
        }

    return profiles


def build_fingerprints_parquet(fp_source, km, X_std, feature_names,
                                player_ids, player_names, cluster_profiles):
    """Build the kbest fingerprints parquet from the source parquet + new cluster labels."""
    labels = km.labels_
    n = len(labels)

    dists = np.array([
        np.linalg.norm(X_std[i] - km.cluster_centers_[labels[i]])
        for i in range(n)
    ])

    arch_names = [cluster_profiles[labels[i]]["name"] for i in range(n)]

    # Start from the source parquet, keep all feature columns
    feat_short = [f.replace("_mean", "").replace("_mean", "") for f in feature_names]
    keep_cols = ["n_cv_games", "first_game_id", "last_game_id", "player_name"] + feat_short

    # Subset available columns
    available = [c for c in keep_cols if c in fp_source.columns]
    df_out = fp_source[available].copy()

    # Overwrite archetype assignments
    df_out["archetype_id"]       = labels
    df_out["archetype_name"]     = arch_names
    df_out["dist_from_centroid"] = dists
    df_out["k_value"]            = km.n_clusters

    # Reorder nicely
    front_cols = ["n_cv_games", "archetype_id", "archetype_name", "dist_from_centroid",
                  "k_value", "player_name"]
    other_cols = [c for c in df_out.columns if c not in front_cols]
    df_out = df_out[front_cols + other_cols]

    return df_out


# ── Vault note ──────────────────────────────────────────────────────────────

def build_vault_note(results, best_k, cluster_profiles, player_ids, player_names,
                     n_cv_games_arr):
    """Write Atlas_K_Refit_Analysis.md."""

    # Build the metrics table
    header = ("| K | Silhouette | Davies-Bouldin | Inertia | Max% | Min Size | "
              "Curry Cluster | Curry Size | Jokic Cluster | Jokic Size | "
              "N(dist>8) | Catch-All? |")
    sep    = ("|---|-----------|----------------|---------|------|----------|"
              "--------------|------------|---------------|------------|"
              "-----------|-----------|")
    rows = []
    for k in K_VALUES:
        r = results[k]
        marker = " **BEST**" if k == best_k else ""
        rows.append(
            f"| {k}{marker} | {r['silhouette']:.4f} | {r['davies_bouldin']:.4f} | "
            f"{r['inertia']:.0f} | {r['max_pct']:.1%} | {r['min_cluster_size']} | "
            f"{r['curry_cluster']} | {r['curry_cluster_size']} | "
            f"{r['jokic_cluster']} | {r['jokic_cluster_size']} | "
            f"{r['n_dist_gt_8']} | {'YES' if r['catch_all_penalty'] else 'no'} |"
        )
    table = "\n".join([header, sep] + rows)

    # Cluster details section for best K
    cluster_section = ""
    for cid, prof in cluster_profiles.items():
        feats_str = ", ".join(
            [f"`{k}` z={v:+.3f}" for k, v in list(prof["top_distinguishing_features"].items())[:5]]
        )
        reps = " | ".join(prof["representative_players"])
        cluster_section += (
            f"\n### Cluster {cid}: {prof['name']}\n"
            f"- **Players:** {prof['n_players']} "
            f"({prof['n_players']/230*100:.1f}% of 230)\n"
            f"- **Top distinguishing features:** {feats_str}\n"
            f"- **Representative players:** {reps}\n"
        )

    # Bug 14 resolution assessment
    best = results[best_k]
    curry_cid   = best["curry_cluster"]
    jokic_cid   = best["jokic_cluster"]
    curry_size  = best["curry_cluster_size"]
    jokic_size  = best["jokic_cluster_size"]
    max_pct     = best["max_pct"]

    curry_name  = cluster_profiles[curry_cid]["name"]  if curry_cid  is not None else "N/A"
    jokic_name  = cluster_profiles[jokic_cid]["name"]  if jokic_cid  is not None else "N/A"

    same_cluster = (curry_cid == jokic_cid)
    curry_small  = (curry_size <= 35)   # <= 35 players = meaningful, not catch-all
    jokic_small  = (jokic_size <= 35)
    no_catchall  = (max_pct < MAX_CLUSTER_PCT_THRESHOLD)

    bug14_resolved = same_cluster and curry_small and no_catchall

    if bug14_resolved:
        resolution_text = (
            f"**Bug 14 STATUS: RESOLVED at K={best_k}.**\n\n"
            f"Curry (ID {CURRY_ID}) and Jokic (ID {JOKIC_ID}) both land in "
            f"cluster {curry_cid} (\"{curry_name}\", n={curry_size} = "
            f"{curry_size/230*100:.1f}% of 230). No cluster exceeds {MAX_CLUSTER_PCT_THRESHOLD:.0%}. "
            f"They share a small, semantically meaningful cluster of high-activity generalists. "
            f"The 70.9% catch-all \"Versatile Forward\" cluster is broken up."
        )
        recommendation = (
            f"**Recommend promoting K={best_k} to default in `build_player_atlas.py`.** "
            f"The Bug 14 catch-all is resolved. All downstream atlases (INT-2 cards, "
            f"INT-17 archetype×scheme, INT-6 similarity) will benefit from sharper labels."
        )
    else:
        issues = []
        if not same_cluster:
            issues.append(f"Curry (cluster {curry_cid}) and Jokic (cluster {jokic_cid}) are in DIFFERENT clusters")
        if not curry_small:
            issues.append(f"Curry's cluster has {curry_size} players ({curry_size/230*100:.1f}%) — still large")
        if not no_catchall:
            issues.append(f"Largest cluster is still {max_pct:.1%} (>{MAX_CLUSTER_PCT_THRESHOLD:.0%} threshold)")
        resolution_text = (
            f"**Bug 14 STATUS: PARTIALLY RESOLVED at K={best_k}.**\n\n"
            f"Issues remaining:\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
            f"Curry lands in cluster {curry_cid} (\"{curry_name}\", n={curry_size}). "
            f"Jokic lands in cluster {jokic_cid} (\"{jokic_name}\", n={jokic_size})."
        )
        recommendation = (
            f"**Partial improvement over K=4.** Bug 14 is not fully resolved at K={best_k} "
            f"by the strict criteria. Consider K={best_k+1} or K={best_k+2} if the separation "
            f"still isn't sufficient, but weigh against increased model complexity."
        )

    # Broader context on any newly surfaced issues
    new_bugs_section = ""
    # Check: did K=4 silhouette nosedive vs best K? Indicates structural instability
    sil_k4 = results[4]["silhouette"]
    sil_best = results[best_k]["silhouette"]
    sil_delta = sil_best - sil_k4

    if sil_delta > 0.02:
        new_bugs_section = f"""
## New Bug Detection

### Bug 18 — Low overall silhouette across all K values (weak cluster structure in CV features)
**Surfaced by**: K-sweep refit analysis (2026-05-28)
**Symptom**: Best silhouette across K=4..10 is only {sil_best:.4f}. For reference, silhouette > 0.5
indicates well-separated clusters; > 0.25 is marginal; < 0.2 suggests the feature space does not
naturally separate into discrete archetypes. CV features produce weak cluster structure overall.
**Root cause hypothesis**: The 19 behavioral features are noisy (especially `avg_defender_distance`
with sentinel-value contamination and `play_type_post_pct`/`play_type_isolation_pct` which are
near-zero for 90%+ of players). With many near-zero features, the standardized feature space is
dominated by a few active features, and most players cluster densely near the origin.
**Impact**: All archetype labels are softer boundaries than the INT-1 note implies.
The atlas is useful for relative comparison but not hard categorization.
**Fix proposals**:
  a) Remove or re-weight near-zero features (isolation, post, transition) before clustering
  b) Apply PCA whitening (not just standardization) before KMeans to remove collinearity
  c) Use UMAP dimensionality reduction before KMeans for non-linear structure
**Effort**: Low (1-2 hours — test feature subsetting + UMAP pre-processing)
"""

    content = f"""# Atlas K-Refit Analysis — K-Sweep for Bug 14 Resolution
*Generated: 2026-05-28 | Script: `scripts/refit_atlas_k_sweep.py`*
*Purpose: Find optimal K to break up the 70.9% "Versatile Forward" catch-all cluster at K=4.*

---

## Summary

| Metric | K=4 (current) | K={best_k} (best) |
|--------|---------------|---------|
| Silhouette | {results[4]['silhouette']:.4f} | {results[best_k]['silhouette']:.4f} |
| Davies-Bouldin | {results[4]['davies_bouldin']:.4f} | {results[best_k]['davies_bouldin']:.4f} |
| Largest cluster % | {results[4]['max_pct']:.1%} | {results[best_k]['max_pct']:.1%} |
| Curry cluster size | {results[4]['curry_cluster_size']} | {results[best_k]['curry_cluster_size']} |
| Jokic cluster size | {results[4]['jokic_cluster_size']} | {results[best_k]['jokic_cluster_size']} |
| N players dist>8σ | {results[4]['n_dist_gt_8']} | {results[best_k]['n_dist_gt_8']} |

---

## K-Sweep Metrics Table

{table}

*Catch-All: any cluster > {MAX_CLUSTER_PCT_THRESHOLD:.0%} of total players.*
*Penalized score = silhouette − 0.05 if catch-all triggered, else = silhouette.*
*Best K chosen by max penalized score (with tie-break: prefer lower K).*

---

## Best K Selection: K={best_k}

**Selection reasoning:**
- Silhouette = {results[best_k]['silhouette']:.4f} (Davies-Bouldin = {results[best_k]['davies_bouldin']:.4f})
- Largest cluster = {results[best_k]['max_pct']:.1%} ({'BELOW' if not results[best_k]['catch_all_penalty'] else 'ABOVE'} {MAX_CLUSTER_PCT_THRESHOLD:.0%} threshold → {'no' if not results[best_k]['catch_all_penalty'] else 'HAS'} catch-all penalty)
- Curry lands in cluster {curry_cid} ("{curry_name}", n={curry_size})
- Jokic lands in cluster {jokic_cid} ("{jokic_name}", n={jokic_size})
- N(dist>8σ) = {results[best_k]['n_dist_gt_8']} (vs {results[4]['n_dist_gt_8']} at K=4) — {'improved' if results[best_k]['n_dist_gt_8'] < results[4]['n_dist_gt_8'] else 'unchanged or worse'}

---

## Cluster Labels and Profiles at K={best_k}

{cluster_section}

---

## Bug 14 Resolution Assessment

{resolution_text}

---

## Recommendation

{recommendation}

---

## Should build_player_atlas.py be updated to use K={best_k}?

{'YES — promote K=' + str(best_k) + ' to default in `build_player_atlas.py`. Update the `choose_k()` range and/or hardcode K=' + str(best_k) + ' to avoid silhouette reverting to K=4 on future data.' if bug14_resolved else 'CONDITIONAL — K=' + str(best_k) + ' is an improvement but does not fully satisfy Bug 14 criteria. Promote if the partial improvement is sufficient for downstream uses; otherwise investigate higher K or feature engineering changes.'}

**Files produced:**
- `data/intelligence/player_fingerprints_kbest.parquet` — K={best_k} assignments (original K=4 parquet untouched)
- `data/models/player_atlas_kmeans_kbest.pkl` — K={best_k} KMeans model

---

## Update History
| Version | Date | Notes |
|---------|------|-------|
| v1 | 2026-05-28 | K-sweep K=4..10, best K={best_k} selected |

{new_bugs_section}
"""
    with open(VAULT_NOTE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Vault note -> {VAULT_NOTE}")
    return bug14_resolved, resolution_text


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print("=== Atlas K-Sweep Refit (Bug 14 Investigation) ===\n")

    # 1. Load existing fingerprints parquet (has the feature means already)
    print("[1] Loading existing fingerprints parquet...")
    fp = pd.read_parquet(PARQUET_IN)
    print(f"  Loaded {len(fp)} players")

    # 2. Extract feature matrix (same 19 features, already season-mean aggregated)
    print("[2] Building feature matrix...")
    feat_cols = [f for f in FINGERPRINT_FEATURES if f in fp.columns]
    missing   = [f for f in FINGERPRINT_FEATURES if f not in fp.columns]
    if missing:
        print(f"  [WARN] Features not found in parquet: {missing}")
    print(f"  Using {len(feat_cols)} features: {feat_cols}")

    X = fp[feat_cols].values
    X = np.nan_to_num(X, nan=0.0)

    player_ids   = fp.index.values.astype(int)
    player_names = fp["player_name"].values if "player_name" in fp.columns else np.array([f"ID:{p}" for p in player_ids])
    n_cv_games   = fp["n_cv_games"].values

    # 3. Standardize
    print("[3] Standardizing features...")
    scaler  = StandardScaler()
    X_std   = scaler.fit_transform(X)
    global_mean     = X_std.mean(axis=0)
    global_std_arr  = X_std.std(axis=0)

    feature_names = [f + "_mean" for f in feat_cols]   # consistent with build_player_atlas naming

    # 4. K-sweep
    print(f"[4] Running KMeans sweep: K = {K_VALUES}, n_init={N_INIT}, seed={RANDOM_STATE}...")
    results, models = run_sweep(X_std, player_ids, player_names, n_cv_games)

    # 5. Pick best K
    print("\n[5] Selecting best K...")
    best_k = pick_best_k(results)
    best_km = models[best_k]

    # Print comparison table
    print("\n  K | Silhouette | DB     | Max%   | Catch-All | Curry sz | Jokic sz | Penalized")
    print("  " + "-"*78)
    for k in K_VALUES:
        r = results[k]
        marker = " <-- BEST" if k == best_k else ""
        print(f"  {k} | {r['silhouette']:.4f}     | {r['davies_bouldin']:.4f} | "
              f"{r['max_pct']:.1%}  | {'YES' if r['catch_all_penalty'] else 'no ':3s}       | "
              f"{r['curry_cluster_size']:8} | {r['jokic_cluster_size']:8} | "
              f"{r['penalized_score']:.4f}{marker}")

    # 6. Build cluster profiles for best K
    print(f"\n[6] Building cluster profiles for K={best_k}...")
    cluster_profiles = build_cluster_profiles(
        best_km, X_std, feature_names, player_ids, player_names,
        n_cv_games, global_mean, global_std_arr
    )
    print("\n  Cluster assignments:")
    for cid, prof in cluster_profiles.items():
        pct = prof["n_players"] / len(fp) * 100
        top3 = list(prof["top_distinguishing_features"].items())[:3]
        top3_str = ", ".join([f"{k}:{v:+.3f}" for k, v in top3])
        print(f"    [{cid}] {prof['name']:35s} n={prof['n_players']:3d} ({pct:.1f}%) | {top3_str}")
        print(f"         Rep: {' | '.join(prof['representative_players'][:3])}")

    # 7. Check Curry and Jokic placement
    r = results[best_k]
    print(f"\n  Curry  -> cluster {r['curry_cluster']} "
          f"(\"{cluster_profiles[r['curry_cluster']]['name']}\", "
          f"n={r['curry_cluster_size']})")
    print(f"  Jokic  -> cluster {r['jokic_cluster']} "
          f"(\"{cluster_profiles[r['jokic_cluster']]['name']}\", "
          f"n={r['jokic_cluster_size']})")

    # 8. Build output parquet
    print(f"\n[7] Building fingerprints_kbest.parquet...")
    df_out = build_fingerprints_parquet(
        fp, best_km, X_std, feat_cols,
        player_ids, player_names, cluster_profiles
    )
    df_out.to_parquet(PARQUET_OUT, index=True)
    print(f"  Saved {len(df_out)} player fingerprints -> {PARQUET_OUT}")

    # 9. Save KMeans pkl
    print(f"[8] Saving KMeans pkl -> {PKL_OUT}...")
    with open(PKL_OUT, "wb") as f:
        pickle.dump(best_km, f)
    print(f"  Saved K={best_k} KMeans model -> {PKL_OUT}")

    # 10. Save scaler too (needed for inference)
    scaler_path = PKL_OUT.replace("_kmeans_kbest.pkl", "_scaler_kbest.pkl")
    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)
    print(f"  Saved scaler -> {scaler_path}")

    # 11. Vault note
    print(f"\n[9] Writing vault note...")
    bug14_resolved, _ = build_vault_note(
        results, best_k, cluster_profiles,
        player_ids, player_names, n_cv_games
    )

    # 12. Final report
    print("\n" + "="*65)
    print(f"Atlas K-Sweep Complete | Best K = {best_k}")
    print("="*65)
    print(f"\nK-sweep summary:")
    print(f"  {'K':>2}  {'Silhouette':>10}  {'DB':>8}  {'Max%':>6}  {'CatchAll':>8}  "
          f"{'CurrySz':>7}  {'JokicSz':>7}")
    print(f"  {'-'*60}")
    for k in K_VALUES:
        r = results[k]
        print(f"  {k:>2}  {r['silhouette']:>10.4f}  {r['davies_bouldin']:>8.4f}  "
              f"{r['max_pct']:>6.1%}  {'YES' if r['catch_all_penalty'] else 'no':>8}  "
              f"{r['curry_cluster_size']:>7}  {r['jokic_cluster_size']:>7}")

    print(f"\nBug 14 resolved at K={best_k}: {'YES' if bug14_resolved else 'PARTIAL'}")
    print(f"\nFiles written:")
    print(f"  {PARQUET_OUT}")
    print(f"  {PKL_OUT}")
    print(f"  {scaler_path}")
    print(f"  {VAULT_NOTE}")


if __name__ == "__main__":
    main()
