"""
build_archetype_drift.py — INT-38: Archetype Drift Detection

For each player with ≥4 CV games, project every individual game through
INT-1's saved KMeans + scaler and detect whether the player's per-game
archetype is stable, drifting, or transitioning across the season.

Outputs:
  data/intelligence/archetype_drift.parquet
  data/intelligence/archetype_drift_signals.json
  vault/Intelligence/Archetype_Drift_Atlas.md

Run:
    python scripts/build_archetype_drift.py
"""
from __future__ import annotations

import json
import os
import pickle
import sqlite3
import sys
from collections import Counter
from typing import Dict, List

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
INTEL_DIR = os.path.join(PROJECT_DIR, "data", "intelligence")
VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Intelligence")

os.makedirs(INTEL_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)

MIN_GAMES = 4  # minimum games for drift analysis

# ── Drift thresholds ───────────────────────────────────────────────────────
STABLE_THRESHOLD = 0.60       # >= 60% games in primary archetype → STABLE
DRIFTING_LOWER = 0.40         # < 40% → definitely DRIFTING; 40–60% also DRIFTING
TRANSITION_RECENCY_DIFF = 0.5 # recent half modal archetype differs from older half

# ── Archetype name lookup (from player_archetype_definitions.json) ─────────
ARCHETYPE_NAMES: Dict[int, str] = {}


def load_archetype_names() -> None:
    global ARCHETYPE_NAMES
    path = os.path.join(INTEL_DIR, "player_archetype_definitions.json")
    if os.path.exists(path):
        with open(path) as f:
            defs = json.load(f)
        ARCHETYPE_NAMES = {int(k): v["name"] for k, v in defs.items()}
    else:
        ARCHETYPE_NAMES = {0: "Archetype-0", 1: "Archetype-1",
                           2: "Archetype-2", 3: "Archetype-3"}
    print(f"  Loaded archetype names: {ARCHETYPE_NAMES}")


def load_int1_model() -> tuple:
    """
    Load INT-1's saved KMeans + scaler.  Do NOT refit.

    Bug 17 fix: loads player_atlas_kmeans.pkl + player_atlas_scaler.pkl
    (the 19-feature atlas model) instead of the legacy player_archetypes.pkl
    (9-feature B3 model).  This ensures per-game cluster IDs are aligned with
    the primary_archetype IDs in player_fingerprints.parquet.
    """
    intel_dir = os.path.join(PROJECT_DIR, "data", "intelligence")
    atlas_kmeans_path = os.path.join(MODELS_DIR, "player_atlas_kmeans.pkl")
    atlas_scaler_path = os.path.join(MODELS_DIR, "player_atlas_scaler.pkl")
    atlas_features_path = os.path.join(intel_dir, "player_atlas_feature_list.json")

    if (os.path.exists(atlas_kmeans_path) and os.path.exists(atlas_scaler_path)
            and os.path.exists(atlas_features_path)):
        # Bug 17 fix: use the aligned atlas model
        with open(atlas_kmeans_path, "rb") as f:
            kmeans = pickle.load(f)
        with open(atlas_scaler_path, "rb") as f:
            scaler = pickle.load(f)
        with open(atlas_features_path) as f:
            feat_data = json.load(f)
        features = feat_data["features"]  # raw feature names (no _mean suffix)
        print(f"  [Bug17-fix] Loaded atlas KMeans (K={kmeans.n_clusters}) from {atlas_kmeans_path}")
        print(f"  Features ({len(features)}): {features}")
    else:
        # Fallback: legacy 9-feature pkl (misaligned — do not use in production)
        print("  [WARN] Atlas pkl not found; falling back to legacy player_archetypes.pkl (BUG 17 NOT FIXED)")
        pkl_path = os.path.join(MODELS_DIR, "player_archetypes.pkl")
        with open(pkl_path, "rb") as f:
            state = pickle.load(f)
        scaler = state["scaler"]
        kmeans = state["kmeans"]
        features = state["features"]
        print(f"  Loaded KMeans (K={kmeans.n_clusters}) + scaler from {pkl_path}")
        print(f"  Features ({len(features)}): {features}")
    return scaler, kmeans, features


def load_per_game_cv_vectors(features: List[str]) -> pd.DataFrame:
    """
    Pivot cv_features DB into (player_id, game_id) × features.
    Only the 9 clustering features are needed.
    NaNs → 0 (same imputation as INT-1's build step).
    """
    conn = sqlite3.connect(DB_PATH)
    # Pull only the features we need + player names from fingerprints
    placeholders = ",".join(f"'{f}'" for f in features)
    df = pd.read_sql(
        f"SELECT player_id, game_id, feature_name, feature_value "
        f"FROM cv_features WHERE feature_name IN ({placeholders})",
        conn,
    )
    conn.close()

    pivot = df.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="mean",
    )

    # Ensure all clustering features present (fill missing with 0)
    for feat in features:
        if feat not in pivot.columns:
            pivot[feat] = 0.0
    pivot = pivot[features].fillna(0.0).reset_index()

    print(f"  Loaded {len(pivot)} (player, game) rows with {len(features)} features")
    return pivot


def load_game_order() -> Dict[str, int]:
    """
    Build game_id → chronological order mapping.
    Game IDs are lexicographically sortable (NBA convention: YYMM...).
    We use lexicographic sort as a proxy for date order.
    Optionally enrich with dates from season_games_*.json files.
    """
    import glob

    game_dates: Dict[str, str] = {}

    season_dir = os.path.join(PROJECT_DIR, "data", "nba")
    for fpath in sorted(glob.glob(os.path.join(season_dir, "season_games_*.json"))):
        with open(fpath) as f:
            data = json.load(f)
        rows = data.get("rows", [])
        for row in rows:
            gid = row.get("game_id", "")
            gdate = row.get("game_date", "")
            if gid and gdate:
                game_dates[gid] = gdate

    if game_dates:
        sorted_ids = sorted(game_dates.keys(), key=lambda g: game_dates.get(g, g))
    else:
        # Fallback: lexicographic sort of game IDs
        conn = sqlite3.connect(DB_PATH)
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT game_id FROM cv_features ORDER BY game_id"
        ).fetchall()]
        conn.close()
        sorted_ids = ids

    order_map = {gid: idx for idx, gid in enumerate(sorted_ids)}
    print(f"  Game order map: {len(order_map)} games resolved")
    return order_map


def load_player_names() -> Dict[int, str]:
    fp_path = os.path.join(INTEL_DIR, "player_fingerprints.parquet")
    fp = pd.read_parquet(fp_path, columns=["player_name", "archetype_id", "archetype_name"])
    name_map = fp["player_name"].to_dict()          # player_id → name
    archetype_map = fp["archetype_id"].to_dict()    # player_id → primary archetype_id
    arch_name_map = fp["archetype_name"].to_dict()  # player_id → primary archetype_name
    return name_map, archetype_map, arch_name_map


def per_game_archetype_assignment(
    pivot: pd.DataFrame,
    scaler,
    kmeans,
    features: List[str],
) -> pd.DataFrame:
    """
    Project each (player_id, game_id) row through scaler + kmeans.
    Returns pivot with added column 'per_game_archetype'.

    CAVEAT: Single-game CV vectors are noisier than full-history aggregates.
    A single game may land in a different cluster due to variance, not true
    role change.  This is why we need ≥4 games before drawing conclusions.
    """
    X = pivot[features].values.astype(float)
    X_scaled = scaler.transform(X)
    labels = kmeans.predict(X_scaled)
    pivot = pivot.copy()
    pivot["per_game_archetype"] = labels
    return pivot


def analyze_drift(
    player_games: pd.DataFrame,
    primary_archetype: int,
    game_order: Dict[str, int],
) -> Dict:
    """
    For a single player's game rows, compute drift metrics.

    Parameters
    ----------
    player_games : rows for this player (sorted by game order)
    primary_archetype : INT-1 atlas assignment
    game_order : game_id → chronological index

    Returns
    -------
    dict with drift metrics
    """
    # Sort chronologically
    player_games = player_games.copy()
    player_games["game_order"] = player_games["game_id"].map(
        lambda g: game_order.get(g, 0)
    )
    player_games = player_games.sort_values("game_order")

    archetypes = player_games["per_game_archetype"].tolist()
    n_games = len(archetypes)

    # Consistency score: fraction matching primary
    n_primary = sum(1 for a in archetypes if a == primary_archetype)
    consistency = n_primary / n_games

    # Archetype distribution
    dist = Counter(archetypes)

    # Top alternate (most common non-primary)
    alt_counts = {k: v for k, v in dist.items() if k != primary_archetype}
    top_alternate = max(alt_counts, key=alt_counts.get) if alt_counts else primary_archetype

    # Recent vs older half
    mid = n_games // 2
    older_half = archetypes[:mid]
    recent_half = archetypes[mid:]

    older_modal = Counter(older_half).most_common(1)[0][0] if older_half else primary_archetype
    recent_modal = Counter(recent_half).most_common(1)[0][0] if recent_half else primary_archetype

    # Recent archetype: last 3 games modal
    last_3 = archetypes[-3:]
    recent_3_modal = Counter(last_3).most_common(1)[0][0]

    # Drift tag
    if consistency >= STABLE_THRESHOLD:
        drift_tag = "STABLE"
    elif recent_modal != older_modal and n_games >= 4:
        # Bug 28 safety net: if older_modal and recent_modal map to the SAME archetype
        # name (e.g. two clusters both called "Versatile Forward" before the rename fix),
        # treat as STABLE — same behavior under a different numeric ID is not a real
        # transition.  This handles any future duplicate-name regressions gracefully.
        older_modal_name = ARCHETYPE_NAMES.get(older_modal, str(older_modal))
        recent_modal_name = ARCHETYPE_NAMES.get(recent_modal, str(recent_modal))
        if older_modal_name == recent_modal_name:
            drift_tag = "STABLE"
        else:
            # Recent behavior differs from older behavior → TRANSITIONING
            # Additional check: recent half should be fairly consistent in the new archetype
            recent_consistency_in_modal = sum(
                1 for a in recent_half if a == recent_modal
            ) / len(recent_half) if recent_half else 0
            if recent_consistency_in_modal >= 0.5:
                drift_tag = "TRANSITIONING"
            else:
                drift_tag = "DRIFTING"
    else:
        drift_tag = "DRIFTING"

    # All archetypes seen (for scatter description)
    scatter = list(dist.keys())

    # Bug 28 fix: expose the half-split modals that DROVE the drift_tag decision
    # (not recent_3_modal which can differ from the half-split modal used above).
    # This ensures older_archetype_name / recent_archetype_name in the parquet
    # are aligned with the TRANSITIONING/DRIFTING tag — no display mismatches.
    return {
        "n_games": n_games,
        "consistency_score": round(consistency, 4),
        "archetype_sequence": archetypes,
        "archetype_distribution": {
            ARCHETYPE_NAMES.get(k, str(k)): v for k, v in dist.items()
        },
        "top_alternate_archetype": top_alternate,
        "drift_tag": drift_tag,
        "recent_archetype": recent_modal,      # half-split recent modal (aligns with tag)
        "recent_archetype_3game": recent_3_modal,  # last-3-game modal (informational)
        "older_archetype": older_modal,
        "scatter_archetypes": scatter,
    }


def build_records(
    pivot: pd.DataFrame,
    game_order: Dict[str, int],
    name_map: Dict[int, str],
    archetype_map: Dict[int, int],
    arch_name_map: Dict[int, str],
) -> List[Dict]:
    """Main analysis loop: per player, compute drift metrics."""
    records = []
    players_with_enough = (
        pivot.groupby("player_id")["game_id"].nunique() >= MIN_GAMES
    )
    eligible_players = players_with_enough[players_with_enough].index.tolist()

    print(f"\n  Players with >={MIN_GAMES} CV games: {len(eligible_players)}")

    for pid in sorted(eligible_players):
        player_rows = pivot[pivot["player_id"] == pid]
        player_name = name_map.get(pid, f"ID:{pid}")
        primary_id = archetype_map.get(pid)

        if primary_id is None:
            # Player has CV games but wasn't in INT-1 (edge case: only 2 games in INT-1 min)
            # Use most common per-game archetype as primary
            all_archetypes = player_rows["per_game_archetype"].tolist()
            primary_id = Counter(all_archetypes).most_common(1)[0][0]

        drift = analyze_drift(player_rows, primary_id, game_order)

        records.append({
            "player_id": pid,
            "player_name": player_name,
            "primary_archetype": primary_id,
            "primary_archetype_name": ARCHETYPE_NAMES.get(primary_id, str(primary_id)),
            "n_games": drift["n_games"],
            "consistency_score": drift["consistency_score"],
            "top_alternate_archetype": drift["top_alternate_archetype"],
            "top_alternate_archetype_name": ARCHETYPE_NAMES.get(
                drift["top_alternate_archetype"], str(drift["top_alternate_archetype"])
            ),
            "drift_tag": drift["drift_tag"],
            # recent_archetype = half-split modal (same signal that drives the tag)
            "recent_archetype": drift["recent_archetype"],
            "recent_archetype_name": ARCHETYPE_NAMES.get(
                drift["recent_archetype"], str(drift["recent_archetype"])
            ),
            # recent_archetype_3game = last 3 games modal (granular recency signal)
            "recent_archetype_3game": drift["recent_archetype_3game"],
            "recent_archetype_3game_name": ARCHETYPE_NAMES.get(
                drift["recent_archetype_3game"], str(drift["recent_archetype_3game"])
            ),
            "older_archetype": drift["older_archetype"],
            "older_archetype_name": ARCHETYPE_NAMES.get(
                drift["older_archetype"], str(drift["older_archetype"])
            ),
            "archetype_distribution": json.dumps(drift["archetype_distribution"]),
            "archetype_sequence": json.dumps(drift["archetype_sequence"]),
            "scatter_archetypes": json.dumps(
                [ARCHETYPE_NAMES.get(a, str(a)) for a in drift["scatter_archetypes"]]
            ),
        })

    return records


def save_parquet(records: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    out_path = os.path.join(INTEL_DIR, "archetype_drift.parquet")
    df.to_parquet(out_path, index=False)
    print(f"  Saved parquet: {out_path} ({len(df)} rows)")
    return df


def save_json(df: pd.DataFrame) -> None:
    """Build categorised signal JSON."""
    out: Dict[str, List] = {"TRANSITIONING": [], "DRIFTING": [], "STABLE": []}

    for _, row in df.iterrows():
        tag = row["drift_tag"]
        player_name = row["player_name"]
        if tag == "TRANSITIONING":
            out["TRANSITIONING"].append({
                "player": player_name,
                "from": ARCHETYPE_NAMES.get(row["older_archetype"], str(row["older_archetype"])),
                "to": ARCHETYPE_NAMES.get(row["recent_archetype"], str(row["recent_archetype"])),
                "transition_recent_games": 3,
                "n_games": int(row["n_games"]),
                "consistency_score": float(row["consistency_score"]),
            })
        elif tag == "DRIFTING":
            scatter = json.loads(row["scatter_archetypes"])
            out["DRIFTING"].append({
                "player": player_name,
                "scatter_across": scatter,
                "primary": row["primary_archetype_name"],
                "consistency": float(row["consistency_score"]),
                "n_games": int(row["n_games"]),
            })
        else:  # STABLE
            out["STABLE"].append({
                "player": player_name,
                "primary": row["primary_archetype_name"],
                "consistency": float(row["consistency_score"]),
                "n_games": int(row["n_games"]),
            })

    # Sort each category
    out["TRANSITIONING"].sort(key=lambda x: x["n_games"], reverse=True)
    out["DRIFTING"].sort(key=lambda x: x["consistency"])
    out["STABLE"].sort(key=lambda x: -x["consistency"])

    json_path = os.path.join(INTEL_DIR, "archetype_drift_signals.json")
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Saved JSON: {json_path}")


def save_atlas(df: pd.DataFrame) -> None:
    stable = df[df["drift_tag"] == "STABLE"]
    drifting = df[df["drift_tag"] == "DRIFTING"]
    transitioning = df[df["drift_tag"] == "TRANSITIONING"]

    # Top 10 transitioning
    top_trans = transitioning.sort_values("n_games", ascending=False).head(10)
    # Top 10 drifting (most chaotic = lowest consistency)
    top_drift = drifting.sort_values("consistency_score").head(10)
    # Most stable (>= 0.9 consistency)
    top_stable = stable[stable["consistency_score"] >= 0.9].sort_values(
        "consistency_score", ascending=False
    ).head(20)

    def _arch(name_val):
        return str(name_val)

    lines = []
    lines.append("# Archetype Drift Atlas")
    lines.append("")
    lines.append("## Methodology")
    lines.append(
        "Per-game archetype assignment using INT-1's atlas KMeans + StandardScaler (Bug 17 fix). "
        "Each individual game's CV feature vector is projected through the SAME scaler and "
        "KMeans used to build the player atlas (player_atlas_kmeans.pkl / player_atlas_scaler.pkl) — "
        "no refitting. This ensures per-game cluster IDs are aligned with primary_archetype IDs "
        "from player_fingerprints.parquet. "
        "**Caveat:** single-game CV vectors are noisier than full-history aggregates."
    )
    lines.append("")
    lines.append("## Drift category breakdown")
    lines.append(f"- STABLE: {len(stable)} players (consistency ≥ {STABLE_THRESHOLD})")
    lines.append(f"- DRIFTING: {len(drifting)} players (consistency < {STABLE_THRESHOLD}, scattered)")
    lines.append(f"- TRANSITIONING: {len(transitioning)} players (recent assignment ≠ older assignment)")
    lines.append(f"- Total analyzed: {len(df)} players (≥{MIN_GAMES} CV games)")
    lines.append("")

    lines.append("## Top TRANSITIONING players")
    if len(top_trans) == 0:
        lines.append("_(none detected)_")
    else:
        lines.append("| player | from_archetype | to_archetype | n_games | consistency |")
        lines.append("|--------|----------------|-------------|---------|-------------|")
        for _, r in top_trans.iterrows():
            from_arch = _arch(r["older_archetype_name"])
            to_arch = _arch(r["recent_archetype_name"])
            lines.append(
                f"| {r['player_name']} | {from_arch} | {to_arch} "
                f"| {r['n_games']} | {r['consistency_score']:.2f} |"
            )
    lines.append("")

    lines.append("## Top DRIFTING players (most scattered)")
    if len(top_drift) == 0:
        lines.append("_(none detected)_")
    else:
        lines.append("| player | primary | scattered_across | consistency | n_games |")
        lines.append("|--------|---------|-----------------|-------------|---------|")
        for _, r in top_drift.iterrows():
            scatter = ", ".join(json.loads(r["scatter_archetypes"]))
            lines.append(
                f"| {r['player_name']} | {r['primary_archetype_name']} | {scatter} "
                f"| {r['consistency_score']:.2f} | {r['n_games']} |"
            )
    lines.append("")

    lines.append("## Most STABLE players (consistency ≥ 0.9)")
    if len(top_stable) == 0:
        lines.append("_(none at ≥0.90 threshold)_")
    else:
        lines.append("| player | primary | consistency | n_games |")
        lines.append("|--------|---------|-------------|---------|")
        for _, r in top_stable.iterrows():
            lines.append(
                f"| {r['player_name']} | {r['primary_archetype_name']} "
                f"| {r['consistency_score']:.2f} | {r['n_games']} |"
            )
    lines.append("")

    lines.append("## Betting implications")
    lines.append(
        "- **TRANSITIONING players:** market lines may lag the role change. "
        "CV-derived recent_archetype is more current than the season fingerprint. "
        "Check recent_archetype vs primary_archetype to identify stat-line divergence."
    )
    lines.append(
        "- **DRIFTING players:** their CV signal is multi-modal — single-archetype overlays "
        "(e.g., INT-17/INT-20) apply with reduced confidence. Use lower conviction sizing."
    )
    lines.append(
        "- **STABLE players:** archetype-based overlays (INT-17, INT-20, scheme interactions) "
        "are most reliable. High-confidence INT-1 archetypes."
    )
    lines.append("")
    lines.append("## Caveats")
    lines.append(f"- ≥{MIN_GAMES} games minimum for drift analysis; players with fewer games excluded")
    lines.append(
        "- Single-game CV vectors are noisier than full-history aggregates — "
        "a single divergent cluster assignment may reflect game-to-game variance, not true role change"
    )
    lines.append(
        "- K=4 clusters have coarse resolution; finer drift (e.g., more vs less transition "
        "usage within Perimeter Shooter) is not captured at this K"
    )
    lines.append(
        "- TRANSITIONING detection requires recent half modal ≠ older half modal AND "
        "≥50% consistency in recent modal — this filters noise but may miss gradual transitions"
    )

    atlas_path = os.path.join(VAULT_DIR, "Archetype_Drift_Atlas.md")
    with open(atlas_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved atlas: {atlas_path}")


def print_final_report(df: pd.DataFrame) -> None:
    stable = df[df["drift_tag"] == "STABLE"]
    drifting = df[df["drift_tag"] == "DRIFTING"]
    transitioning = df[df["drift_tag"] == "TRANSITIONING"]

    print("\n" + "=" * 65)
    print("INT-38 Archetype Drift — Final Report")
    print("=" * 65)
    print(f"\nCoverage")
    print(f"  Players analyzed (>={MIN_GAMES} games): {len(df)}")
    print(f"  STABLE:        {len(stable):>4}  ({100*len(stable)/len(df):.0f}%)")
    print(f"  DRIFTING:      {len(drifting):>4}  ({100*len(drifting)/len(df):.0f}%)")
    print(f"  TRANSITIONING: {len(transitioning):>4}  ({100*len(transitioning)/len(df):.0f}%)")

    if len(transitioning) > 0:
        print(f"\nTop {min(5, len(transitioning))} TRANSITIONING players")
        top5 = transitioning.sort_values("n_games", ascending=False).head(5)
        for _, r in top5.iterrows():
            print(
                f"  {r['player_name']:<30} "
                f"{r['older_archetype_name']} -> {r['recent_archetype_name']}  "
                f"({r['n_games']}g, cons={r['consistency_score']:.2f})"
            )

    if len(drifting) > 0:
        print(f"\nTop {min(5, len(drifting))} DRIFTING players (lowest consistency)")
        top5d = drifting.sort_values("consistency_score").head(5)
        for _, r in top5d.iterrows():
            scatter = ", ".join(json.loads(r["scatter_archetypes"]))
            print(
                f"  {r['player_name']:<30} cons={r['consistency_score']:.2f}  "
                f"scatter=[{scatter}]"
            )

    if len(stable) > 0:
        print(f"\nMost STABLE (top 5 by consistency)")
        top5s = stable.sort_values("consistency_score", ascending=False).head(5)
        for _, r in top5s.iterrows():
            print(
                f"  {r['player_name']:<30} {r['primary_archetype_name']:<45} "
                f"cons={r['consistency_score']:.2f}  {r['n_games']}g"
            )

    print("\nFiles")
    print("  scripts/build_archetype_drift.py")
    print("  vault/Intelligence/Archetype_Drift_Atlas.md")
    print("  data/intelligence/archetype_drift.parquet")
    print("  data/intelligence/archetype_drift_signals.json")

    print("\nHow to use")
    print(
        "  TRANSITIONING players -> use recent_archetype_name not primary in "
        "INT-17/INT-20 lookups"
    )
    print(
        "  DRIFTING players -> reduce conviction on archetype-based overlays "
        "(scatter_archetypes column shows all observed types)"
    )
    print("  STABLE -> full archetype-based intelligence applies")

    print("\nHonest caveats")
    print(
        f"  - >={MIN_GAMES} games minimum; players with fewer games excluded from analysis"
    )
    print(
        "  - Single-game CV vectors are noisier than full-history aggregates"
    )
    print(
        "  - Same KMeans (K=4) limitation -- bigger K might reveal more nuanced drift"
    )
    print("=" * 65)


def main() -> None:
    print("=" * 65)
    print("INT-38: Archetype Drift Detection")
    print("=" * 65)

    print("\n[Step 1] Loading archetype names + INT-1 model...")
    load_archetype_names()
    scaler, kmeans, features = load_int1_model()

    print("\n[Step 2] Loading player names + primary archetypes...")
    name_map, archetype_map, arch_name_map = load_player_names()
    print(f"  {len(name_map)} players in fingerprints")

    print("\n[Step 3] Loading per-game CV vectors...")
    pivot = load_per_game_cv_vectors(features)

    print("\n[Step 4] Per-game archetype assignment (no refit)...")
    pivot = per_game_archetype_assignment(pivot, scaler, kmeans, features)

    print("\n[Step 5] Loading game chronological order...")
    game_order = load_game_order()

    print("\n[Step 6] Drift analysis per player...")
    records = build_records(pivot, game_order, name_map, archetype_map, arch_name_map)

    print("\n[Step 7] Saving outputs...")
    df = save_parquet(records)
    save_json(df)
    save_atlas(df)

    print_final_report(df)


if __name__ == "__main__":
    main()
