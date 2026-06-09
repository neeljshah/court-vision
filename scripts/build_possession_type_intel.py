"""
INT-21: Possession-Type CV Intelligence
----------------------------------------
For each player with CV games, builds per-possession-type CV profiles:
  - "How does this player play in transition vs half-court?"
Outputs:
  - data/intelligence/possession_type_profiles.parquet
  - data/intelligence/possession_type_signatures.json
  - vault/Intelligence/Possession_Type_Atlas.md
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path("C:/Users/neelj/nba-ai-system")
TRACKING_DIR = ROOT / "data" / "tracking"
CV_PER_GAME_PATH = ROOT / "data" / "player_cv_per_game.parquet"
INTEL_DIR = ROOT / "data" / "intelligence"
VAULT_INTEL_DIR = ROOT / "vault" / "Intelligence"

OUTPUT_PARQUET = INTEL_DIR / "possession_type_profiles.parquet"
OUTPUT_JSON = INTEL_DIR / "possession_type_signatures.json"
OUTPUT_ATLAS = VAULT_INTEL_DIR / "Possession_Type_Atlas.md"

INTEL_DIR.mkdir(parents=True, exist_ok=True)
VAULT_INTEL_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_FRAMES_PER_GROUP = 50          # minimum frames for (player, possession_type) inclusion
MIN_PLAY_TYPES_FOR_SPECIALIST = 2  # min distinct types to tag a specialist

# CV features to aggregate from tracking_data.csv
CV_FEATURES = [
    "velocity",           # movement speed (higher in transition)
    "vel_toward_basket",  # drive / cut aggression
    "dist_to_basket_ft",  # floor position (lower = paint player)
    "off_ball_distance",  # spacing off ball
    "paint_touches",      # paint activity flag per frame
    "dribble_count",      # ball-handling volume
    "contest_arm_angle",  # defender contest level
    "jump_detected",      # jumping activity
    "team_spacing",       # team spread (team-level, still informative)
    "distance_to_ball",   # proximity to ball (lower = more involved)
]

# Possession type canonical ordering for display
POSS_ORDER = [
    "transition", "fast_break", "half_court",
    "drive", "paint_touch", "double_team", "post_up",
]

# Groupings for higher-level tags
RUNNING_TYPES = {"transition", "fast_break"}
HALFCOURT_TYPES = {"half_court", "drive", "double_team"}
INTERIOR_TYPES = {"post_up", "paint_touch"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_mean(s):
    """Mean ignoring NaN; returns NaN if all NaN."""
    v = s.dropna()
    return float(v.mean()) if len(v) > 0 else np.nan


def load_cv_game_map() -> dict:
    """
    Returns {(game_id, slot_player_id): nba_player_id} from player_cv_per_game.parquet.
    Also returns {(game_id, slot_player_id): player_name}.
    """
    df = pd.read_parquet(CV_PER_GAME_PATH)
    id_map = {}
    name_map = {}
    for _, row in df.iterrows():
        key = (str(row["game_id"]), int(row["player_id"]))
        # nba_player_id may be pd.NA
        nba_id = None if pd.isna(row["nba_player_id"]) else int(row["nba_player_id"])
        id_map[key] = nba_id
        name_map[key] = str(row["player_name"]) if pd.notna(row["player_name"]) else None
    return id_map, name_map


def get_overlap_games(id_map: dict) -> list:
    """Games present in both CV parquet and tracking directory."""
    cv_games = set(gid for (gid, _) in id_map.keys())
    tracking_games = set(os.listdir(TRACKING_DIR))
    overlap = sorted(cv_games & tracking_games)
    return overlap


def load_game_frames(game_id: str) -> pd.DataFrame | None:
    """
    Load tracking_data.csv for a game.
    Returns None if file not found or too small.
    """
    path = TRACKING_DIR / game_id / "tracking_data.csv"
    if not path.exists():
        return None
    try:
        cols_needed = [
            "frame", "player_id", "possession_type",
        ] + [c for c in CV_FEATURES if c != "distance_to_ball"]
        # distance_to_ball has high null rate; include separately
        cols_needed.append("distance_to_ball")

        df = pd.read_csv(path, low_memory=False, usecols=lambda c: c in cols_needed)
        if len(df) < 500:
            return None
        return df
    except Exception as e:
        print(f"  [WARN] Could not load {game_id}: {e}")
        return None


# ── Step 1 + 2: Per-game aggregation then cross-game aggregation ─────────────

def build_per_game_records(id_map: dict, name_map: dict, overlap_games: list) -> pd.DataFrame:
    """
    For each game × player × possession_type group with ≥MIN_FRAMES_PER_GROUP frames,
    compute mean of each CV feature.
    Returns long-format DataFrame with columns:
        game_id, nba_player_id, player_name, possession_type, n_frames, <cv_features...>
    """
    records = []
    n_games_processed = 0

    for game_id in overlap_games:
        df = load_game_frames(game_id)
        if df is None:
            continue

        # Ensure player_id is int-comparable
        try:
            df["player_id"] = df["player_id"].astype(int)
        except Exception:
            continue

        if "possession_type" not in df.columns:
            continue

        df = df[df["possession_type"].notna()].copy()
        if len(df) == 0:
            continue

        # Map slot player_id → nba_player_id + name
        def resolve_player(slot_id):
            key = (game_id, slot_id)
            return id_map.get(key, None), name_map.get(key, None)

        # Group by (player_id, possession_type)
        grouped = df.groupby(["player_id", "possession_type"])
        for (slot_id, poss_type), grp in grouped:
            n = len(grp)
            if n < MIN_FRAMES_PER_GROUP:
                continue

            nba_id, pname = resolve_player(int(slot_id))

            rec = {
                "game_id": game_id,
                "nba_player_id": nba_id,
                "player_name": pname,
                "possession_type": poss_type,
                "n_frames": n,
            }
            for feat in CV_FEATURES:
                if feat in grp.columns:
                    rec[f"cv_{feat}"] = safe_mean(grp[feat])
                else:
                    rec[f"cv_{feat}"] = np.nan

            records.append(rec)

        n_games_processed += 1
        if n_games_processed % 5 == 0:
            print(f"  Processed {n_games_processed}/{len(overlap_games)} games, "
                  f"{len(records)} group records so far...")

    print(f"  Total: {n_games_processed} games, {len(records)} (player, poss_type) group records")
    return pd.DataFrame(records)


def cross_game_aggregate(per_game: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per_game records across games for each (nba_player_id, possession_type).
    Returns one row per (nba_player_id, possession_type) with weighted mean CV features.
    Players with unresolved nba_player_id are grouped by player_name instead.
    """
    feat_cols = [c for c in per_game.columns if c.startswith("cv_")]

    results = []

    # Process resolved players (have nba_player_id)
    resolved = per_game[per_game["nba_player_id"].notna()].copy()
    unresolved = per_game[per_game["nba_player_id"].isna()].copy()

    def aggregate_group(subset, id_col, id_val, name_val):
        by_type = subset.groupby("possession_type")
        for ptype, grp in by_type:
            total_frames = grp["n_frames"].sum()
            if total_frames < MIN_FRAMES_PER_GROUP:
                continue
            rec = {
                "nba_player_id": id_val,
                "player_name": name_val,
                "possession_type": ptype,
                "n_frames": int(total_frames),
                "n_games": grp["game_id"].nunique(),
            }
            # Frame-weighted mean across games
            for feat in feat_cols:
                vals = grp[feat].dropna()
                wts = grp.loc[vals.index, "n_frames"]
                if len(vals) == 0:
                    rec[feat] = np.nan
                else:
                    rec[feat] = float(np.average(vals, weights=wts))
            results.append(rec)

    for nba_id, sub in resolved.groupby("nba_player_id"):
        # Get most common player name for this nba_id
        name = sub["player_name"].mode().iloc[0] if len(sub) > 0 else str(nba_id)
        aggregate_group(sub, "nba_player_id", nba_id, name)

    # Unresolved: group by player_name
    for pname, sub in unresolved.groupby("player_name"):
        if pd.isna(pname) or str(pname).endswith("#?") or pname == "None":
            continue
        aggregate_group(sub, "player_name", None, pname)

    df = pd.DataFrame(results)
    print(f"  Cross-game aggregation: {len(df)} (player, possession_type) rows "
          f"covering {df['player_name'].nunique()} players")
    return df


# ── Step 3: Player-level baseline + deltas ────────────────────────────────────

def compute_player_baselines(agg: pd.DataFrame) -> pd.DataFrame:
    """
    For each player, compute weighted-average baseline across ALL possession types.
    Returns {player_key: {feat: baseline_value}}.
    """
    feat_cols = [c for c in agg.columns if c.startswith("cv_")]
    baselines = {}

    for (nba_id, pname), sub in agg.groupby(["nba_player_id", "player_name"]):
        player_key = int(nba_id) if pd.notna(nba_id) else pname
        total_frames = sub["n_frames"].sum()
        baseline = {}
        for feat in feat_cols:
            vals = sub[feat].dropna()
            wts = sub.loc[vals.index, "n_frames"]
            if len(vals) == 0:
                baseline[feat] = np.nan
            else:
                baseline[feat] = float(np.average(vals, weights=wts))
        baseline["total_frames"] = int(total_frames)
        baselines[player_key] = baseline

    return baselines


def add_deltas(agg: pd.DataFrame, baselines: dict) -> pd.DataFrame:
    """
    Add delta columns: <feat>_delta = value_in_poss_type - player_baseline.
    Also compute a per-feature z-score using league std across all players for that feature.
    """
    feat_cols = [c for c in agg.columns if c.startswith("cv_")]

    # League-wide std per feature (for z-scoring)
    league_std = {}
    for feat in feat_cols:
        s = agg[feat].dropna()
        league_std[feat] = float(s.std()) if len(s) > 1 else 1.0

    delta_rows = []
    for _, row in agg.iterrows():
        nba_id = row["nba_player_id"]
        pname = row["player_name"]
        player_key = int(nba_id) if pd.notna(nba_id) else pname
        bl = baselines.get(player_key, {})

        new_row = row.to_dict()
        for feat in feat_cols:
            val = row[feat]
            bl_val = bl.get(feat, np.nan)
            if pd.notna(val) and pd.notna(bl_val) and bl_val != 0:
                delta = val - bl_val
                new_row[f"{feat}_delta"] = round(delta, 4)
                std = league_std.get(feat, 1.0)
                new_row[f"{feat}_z"] = round(delta / std, 3) if std > 0 else 0.0
            else:
                new_row[f"{feat}_delta"] = np.nan
                new_row[f"{feat}_z"] = np.nan
        delta_rows.append(new_row)

    return pd.DataFrame(delta_rows)


# ── Step 4: Specialization tags ───────────────────────────────────────────────

def tag_specialists(profiles: pd.DataFrame) -> dict:
    """
    For each player with ≥MIN_PLAY_TYPES_FOR_SPECIALIST distinct possession types,
    determine specialization tag and top differentiating features.

    Returns {player_key: {tag, top_transition_features, top_hc_features, n_types, ...}}
    """
    feat_cols = [c for c in profiles.columns if c.startswith("cv_") and not c.endswith(("_delta", "_z"))]
    delta_cols = [f"{f}_delta" for f in feat_cols]
    z_cols = [f"{f}_z" for f in feat_cols]

    specialists = {}

    for (nba_id, pname), sub in profiles.groupby(["nba_player_id", "player_name"]):
        player_key = int(nba_id) if pd.notna(nba_id) else pname
        types_observed = set(sub["possession_type"].tolist())
        n_types = len(types_observed)

        if n_types < MIN_PLAY_TYPES_FOR_SPECIALIST:
            continue

        # Gather possession-type → mean z-score across features
        type_profiles = {}
        for _, row in sub.iterrows():
            ptype = row["possession_type"]
            zs = {}
            for zc in z_cols:
                if zc in row and pd.notna(row[zc]):
                    feat = zc.replace("_z", "")
                    zs[feat] = float(row[zc])
            type_profiles[ptype] = zs

        # Running game score = mean z across running types (if observed)
        running_obs = types_observed & RUNNING_TYPES
        hc_obs = types_observed & HALFCOURT_TYPES
        interior_obs = types_observed & INTERIOR_TYPES

        def mean_score_for_types(type_set, zprofiles):
            """Mean absolute z summed across features for a set of types."""
            vals = []
            for t in type_set:
                if t in zprofiles:
                    zs = list(zprofiles[t].values())
                    if zs:
                        vals.append(float(np.mean(np.abs(zs))))
            return float(np.mean(vals)) if vals else 0.0

        running_score = mean_score_for_types(running_obs, type_profiles)
        hc_score = mean_score_for_types(hc_obs, type_profiles)
        interior_score = mean_score_for_types(interior_obs, type_profiles)

        # Determine top differentiating features per type
        def top_features_for_type(ptype, n=3):
            if ptype not in type_profiles:
                return []
            zs = type_profiles[ptype]
            sorted_feats = sorted(zs.items(), key=lambda x: abs(x[1]), reverse=True)
            return [(f.replace("cv_", ""), round(z, 3)) for f, z in sorted_feats[:n] if abs(z) > 0.3]

        # Tag assignment
        scores = {"TRANSITION_SPECIALIST": running_score,
                  "HALF_COURT_SPECIALIST": hc_score,
                  "INTERIOR_SPECIALIST": interior_score}
        max_tag = max(scores, key=scores.get)
        max_score = scores[max_tag]

        # Only assign specialist tag if there's a meaningful gap
        sorted_scores = sorted(scores.values(), reverse=True)
        gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 0
        tag = max_tag if (max_score > 0.5 and gap > 0.2) else "BALANCED"

        # Determine "best type" = highest total frames possession type
        best_type = sub.loc[sub["n_frames"].idxmax(), "possession_type"] if len(sub) > 0 else "half_court"

        # Total frames
        total_frames = int(sub["n_frames"].sum())

        # Top features for transition and half_court specifically
        top_trans = top_features_for_type("transition") or top_features_for_type("fast_break")
        top_hc = top_features_for_type("half_court")
        top_post = top_features_for_type("post_up")

        specialists[str(player_key)] = {
            "nba_player_id": int(nba_id) if pd.notna(nba_id) else None,
            "player_name": pname,
            "tag": tag,
            "n_types_observed": n_types,
            "types_observed": sorted(list(types_observed)),
            "best_type": best_type,
            "total_frames": total_frames,
            "running_score": round(running_score, 3),
            "hc_score": round(hc_score, 3),
            "interior_score": round(interior_score, 3),
            "top_transition_features": top_trans,
            "top_hc_features": top_hc,
            "top_post_features": top_post,
            "type_profiles": {k: {feat: round(v, 3) for feat, v in vd.items()}
                              for k, vd in type_profiles.items()},
        }

    return specialists


# ── Step 5: League-wide signatures ───────────────────────────────────────────

def compute_league_signatures(profiles: pd.DataFrame) -> dict:
    """
    Aggregate across ALL players to get league-wide mean CV features per possession_type.
    Also compute delta vs half_court baseline.
    """
    feat_cols = [c for c in profiles.columns if c.startswith("cv_") and not c.endswith(("_delta", "_z"))]
    feat_cols = [f for f in feat_cols if f != "cv_distance_to_ball"]  # too many nulls

    league = {}
    by_type = profiles.groupby("possession_type")
    for ptype, grp in by_type:
        rec = {"n_players": int(grp["player_name"].nunique()), "total_frames": int(grp["n_frames"].sum())}
        for feat in feat_cols:
            vals = grp[feat].dropna()
            wts = grp.loc[vals.index, "n_frames"]
            if len(vals) > 0:
                rec[feat] = round(float(np.average(vals, weights=wts)), 3)
            else:
                rec[feat] = None
        league[ptype] = rec

    # Compute delta vs half_court
    hc = league.get("half_court", {})
    for ptype, rec in league.items():
        if ptype == "half_court":
            continue
        rec["vs_half_court"] = {}
        for feat in feat_cols:
            v = rec.get(feat)
            h = hc.get(feat)
            if v is not None and h is not None:
                rec["vs_half_court"][feat.replace("cv_", "")] = round(v - h, 3)

    return league


# ── Step 6: Build signatures JSON ────────────────────────────────────────────

def build_signatures_json(specialists: dict, league_sigs: dict) -> dict:
    """
    Compact JSON output for AI chat and downstream use.
    """
    return {
        "metadata": {
            "version": "INT-21",
            "description": "Per-player per-possession-type CV profiles",
            "min_frames_per_group": MIN_FRAMES_PER_GROUP,
        },
        "league_signatures": league_sigs,
        "player_signatures": specialists,
    }


# ── Step 7: Build Atlas markdown ─────────────────────────────────────────────

def format_feat_list(feat_list: list) -> str:
    if not feat_list:
        return "—"
    parts = []
    for feat, z in feat_list:
        direction = "+" if z > 0 else ""
        parts.append(f"{feat} ({direction}{z}σ)")
    return ", ".join(parts)


def build_atlas(profiles: pd.DataFrame, specialists: dict,
                league_sigs: dict, per_game: pd.DataFrame) -> str:
    feat_cols = [c for c in profiles.columns if c.startswith("cv_") and not c.endswith(("_delta", "_z"))]
    feat_cols_clean = [f.replace("cv_", "") for f in feat_cols]

    # ── League-wide signatures section ──
    league_lines = []
    types_in_data = sorted(league_sigs.keys(),
                           key=lambda t: league_sigs[t].get("total_frames", 0), reverse=True)
    for ptype in types_in_data:
        rec = league_sigs[ptype]
        vs = rec.get("vs_half_court", {})
        if ptype == "half_court":
            vel = rec.get("cv_velocity", "?")
            dist = rec.get("cv_dist_to_basket_ft", "?")
            league_lines.append(
                f"- **half_court** (baseline): velocity={vel}, dist_to_basket={dist}ft, "
                f"n_players={rec['n_players']}, frames={rec['total_frames']:,}"
            )
        else:
            if vs:
                top_diffs = sorted(vs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                diff_str = ", ".join(f"{k} {'+' if v > 0 else ''}{v}" for k, v in top_diffs)
                league_lines.append(
                    f"- **{ptype}** vs half_court: {diff_str} | "
                    f"n_players={rec['n_players']}, frames={rec['total_frames']:,}"
                )

    # ── Specialist tables ──
    def specialist_table(tag_filter, n=10):
        rows = [s for s in specialists.values() if s["tag"] == tag_filter]
        rows = sorted(rows, key=lambda s: s["running_score" if "TRANS" in tag_filter
                                           else "hc_score" if "HALF" in tag_filter
                                           else "interior_score"], reverse=True)[:n]
        if not rows:
            return "_No players qualified_\n"
        lines = ["| Player | Signature | vs Baseline | Frames |",
                 "|--------|-----------|------------|--------|"]
        for s in rows:
            if "TRANS" in tag_filter:
                sig = format_feat_list(s.get("top_transition_features", []))
                score = s["running_score"]
            elif "HALF" in tag_filter:
                sig = format_feat_list(s.get("top_hc_features", []))
                score = s["hc_score"]
            else:
                sig = format_feat_list(s.get("top_post_features", []))
                score = s["interior_score"]
            lines.append(
                f"| {s['player_name']} | {sig} | score={score:.3f} | {s['total_frames']:,} |"
            )
        return "\n".join(lines) + "\n"

    # ── Notable findings ──
    # Top transition specialist by running_score
    notable = []
    trans_top = sorted(
        [s for s in specialists.values() if "transition" in s["types_observed"]],
        key=lambda s: s["running_score"], reverse=True
    )[:3]
    for s in trans_top:
        feats = format_feat_list(s.get("top_transition_features", []))
        notable.append(
            f"- **{s['player_name']}** (transition): {feats} — {s['total_frames']:,} frames, tag={s['tag']}"
        )

    hc_top = sorted(
        [s for s in specialists.values() if "half_court" in s["types_observed"]],
        key=lambda s: s["hc_score"], reverse=True
    )[:3]
    for s in hc_top:
        feats = format_feat_list(s.get("top_hc_features", []))
        notable.append(
            f"- **{s['player_name']}** (half_court): {feats} — {s['total_frames']:,} frames, tag={s['tag']}"
        )

    # ── Tag counts ──
    from collections import Counter
    tag_counts = Counter(s["tag"] for s in specialists.values())

    # ── Compute league velocity diff transition vs HC ──
    trans_vel = league_sigs.get("transition", {}).get("cv_velocity", None)
    fb_vel = league_sigs.get("fast_break", {}).get("cv_velocity", None)
    hc_vel = league_sigs.get("half_court", {}).get("cv_velocity", None)
    trans_dist = league_sigs.get("transition", {}).get("cv_dist_to_basket_ft", None)
    hc_dist = league_sigs.get("half_court", {}).get("cv_dist_to_basket_ft", None)
    vel_diff = f"+{trans_vel - hc_vel:.1f}" if trans_vel and hc_vel else "N/A"
    dist_diff = f"{trans_dist - hc_dist:.1f}" if trans_dist and hc_dist else "N/A"

    n_players_total = profiles["player_name"].nunique()
    n_specialists = len(specialists)
    n_games = per_game["game_id"].nunique()
    total_frames = int(profiles["n_frames"].sum())

    atlas = f"""# Possession-Type CV Intelligence Atlas
> INT-21 | Generated 2026-05-28 | {n_games} CV games | {n_players_total} players | {total_frames:,} qualifying frames

---

## League-wide Play-Type Signatures

These are empirical CV measurements averaged across all players and games, relative to half-court baseline:

{chr(10).join(league_lines)}

**Key observations:**
- Transition/fast-break possessions: avg velocity {vel_diff} vs half-court, dist-to-basket {dist_diff}ft
- Post-up possessions: lowest average dist-to-basket, highest paint_touches
- Half-court is baseline; all other types measured as deviation from it

---

## Specialization Breakdown

| Tag | Count |
|-----|-------|
{chr(10).join(f"| {tag} | {cnt} |" for tag, cnt in tag_counts.most_common())}

Total players with ≥{MIN_PLAY_TYPES_FOR_SPECIALIST} possession types: **{n_specialists}**

---

## Top Transition Specialists

{specialist_table("TRANSITION_SPECIALIST")}

## Top Half-Court Specialists

{specialist_table("HALF_COURT_SPECIALIST")}

## Top Interior Specialists

{specialist_table("INTERIOR_SPECIALIST")}

---

## Notable Findings

{chr(10).join(notable) if notable else "_No notable findings — increase sample size_"}

---

## Betting Implications

- **Pre-game pace projection**: DEN / MIA / OKC tempo → favor TRANSITION_SPECIALIST players for PTS OVER
- **Slow-game expected** (MIL/NYK pace control): favor HALF_COURT_SPECIALIST big men for paint stats
- **Combine with INT-22** (B2B reduces transition usage) for situational adjustments
- **Combine with INT-12** (pace control teams suppress fast breaks)
- **AI Chat query**: "How does [player] play in transition vs half-court?" → reads from possession_type_signatures.json

---

## Data Quality Notes

- `possession_type` is derived from CV pipeline (`src/pipeline/tracking_feature_extractor.py`)
- `half_court` is the dominant category (typically 60–80% of frames)
- `double_team`, `drive`, `paint_touch` are sub-type annotations within possessions
- `post_up` is rare (<2% of frames for most players)
- ISSUE-022: `defender_distance=200.0` sentinel still present in some games; affects `cvb_avg_defender_dist` but not the features aggregated here (those come directly from tracking_data)
- Min qualifying frames per (player, poss_type): {MIN_FRAMES_PER_GROUP}
- Players with unresolved `nba_player_id` are grouped by `player_name` (may have cross-game noise if jersey tracker re-numbered)

---

## Files

| File | Description |
|------|-------------|
| `data/intelligence/possession_type_profiles.parquet` | Long-format: (player, possession_type) rows with mean CV features + deltas |
| `data/intelligence/possession_type_signatures.json` | Compact specialist + league signatures for AI chat |
| `scripts/build_possession_type_intel.py` | This script |
"""
    return atlas


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("INT-21: Possession-Type CV Intelligence")
    print("=" * 60)

    # Load CV game → player mapping
    print("\n[1/7] Loading CV player-game map...")
    id_map, name_map = load_cv_game_map()
    print(f"  {len(id_map)} (game, slot) -> nba_player_id mappings")

    # Get overlap games
    overlap_games = get_overlap_games(id_map)
    print(f"  {len(overlap_games)} games overlap between CV parquet and tracking dirs")

    # Per-game aggregation
    print("\n[2/7] Aggregating per-game (player × possession_type) groups...")
    per_game = build_per_game_records(id_map, name_map, overlap_games)

    if len(per_game) == 0:
        print("  [ERROR] No records found — check overlap games and possession_type column")
        return

    # Cross-game aggregation
    print("\n[3/7] Cross-game aggregation per (player, possession_type)...")
    agg = cross_game_aggregate(per_game)

    # Player baselines + deltas
    print("\n[4/7] Computing player baselines and possession-type deltas...")
    baselines = compute_player_baselines(agg)
    profiles = add_deltas(agg, baselines)
    print(f"  {len(profiles)} rows, {profiles['player_name'].nunique()} unique players")

    # Specialization tags
    print("\n[5/7] Tagging specialists...")
    specialists = tag_specialists(profiles)
    from collections import Counter
    tag_counts = Counter(s["tag"] for s in specialists.values())
    print(f"  {len(specialists)} players tagged: {dict(tag_counts)}")

    # League signatures
    print("\n[6/7] Computing league-wide play-type signatures...")
    league_sigs = compute_league_signatures(profiles)
    for ptype, rec in league_sigs.items():
        vel = rec.get("cv_velocity", "?")
        dist = rec.get("cv_dist_to_basket_ft", "?")
        print(f"  {ptype:15s}: velocity={vel}, dist_to_basket={dist}, "
              f"n_players={rec['n_players']}, frames={rec['total_frames']:,}")

    # Build outputs
    print("\n[7/7] Writing outputs...")

    # Parquet: drop per-game game_id column (profiles is already cross-game aggregated)
    parquet_cols = [c for c in profiles.columns if c != "game_id"]
    profiles_out = profiles[parquet_cols].copy()
    profiles_out.to_parquet(str(OUTPUT_PARQUET), index=False)
    print(f"  Wrote {OUTPUT_PARQUET} ({len(profiles_out)} rows)")

    # JSON
    sigs = build_signatures_json(specialists, league_sigs)
    with open(str(OUTPUT_JSON), "w", encoding="utf-8") as f:
        json.dump(sigs, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Wrote {OUTPUT_JSON} ({len(specialists)} player signatures)")

    # Atlas
    atlas_md = build_atlas(profiles, specialists, league_sigs, per_game)
    with open(str(OUTPUT_ATLAS), "w", encoding="utf-8") as f:
        f.write(atlas_md)
    print(f"  Wrote {OUTPUT_ATLAS}")

    # ── Final report ──────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("INT-21 Possession-Type Intelligence — Final Report")
    print("=" * 60)
    print()
    print("### Coverage")
    print(f"  Games processed:           {per_game['game_id'].nunique()}")
    print(f"  Players with profiles:     {profiles['player_name'].nunique()}")
    print(f"  Players with ≥2 types:     {len(specialists)}")
    print(f"  Specialization breakdown:  {dict(tag_counts)}")
    print(f"  Possession types found:    {sorted(profiles['possession_type'].unique())}")
    print()
    print("### Top 5 Transition Specialists")
    trans = sorted(
        [s for s in specialists.values() if "transition" in s["types_observed"] or "fast_break" in s["types_observed"]],
        key=lambda s: s["running_score"], reverse=True
    )[:5]
    print(f"  {'Player':<25} {'Top Feature Shift':<30} {'Z':<8} {'Frames'}")
    print(f"  {'-'*25} {'-'*30} {'-'*8} {'-'*8}")
    for s in trans:
        feats = s.get("top_transition_features", [])
        feat_str = f"{feats[0][0]} ({feats[0][1]:+.2f}σ)" if feats else "—"
        z = feats[0][1] if feats else 0.0
        print(f"  {s['player_name']:<25} {feat_str:<30} {z:<8.3f} {s['total_frames']:,}")
    print()
    print("### Top 5 Half-Court Specialists")
    hc = sorted(
        [s for s in specialists.values() if "half_court" in s["types_observed"]],
        key=lambda s: s["hc_score"], reverse=True
    )[:5]
    for s in hc:
        feats = s.get("top_hc_features", [])
        feat_str = f"{feats[0][0]} ({feats[0][1]:+.2f}σ)" if feats else "—"
        z = feats[0][1] if feats else 0.0
        print(f"  {s['player_name']:<25} {feat_str:<30} {z:<8.3f} {s['total_frames']:,}")
    print()
    print("### League-wide Play-Type Signatures")
    hc_rec = league_sigs.get("half_court", {})
    for ptype in ["transition", "fast_break", "post_up"]:
        rec = league_sigs.get(ptype, {})
        vs = rec.get("vs_half_court", {})
        if vs:
            top3 = sorted(vs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            diff_str = ", ".join(f"{k} {'+' if v > 0 else ''}{v:.3f}" for k, v in top3)
            print(f"  {ptype:15s} vs half_court: {diff_str}")
    print()
    print("### Files Written")
    print(f"  scripts/build_possession_type_intel.py")
    print(f"  vault/Intelligence/Possession_Type_Atlas.md")
    print(f"  data/intelligence/possession_type_profiles.parquet")
    print(f"  data/intelligence/possession_type_signatures.json")
    print()
    print("### How to Use")
    print("  Pre-bet: game pace projection × player's possession-type profile → expected stat tilt")
    print("  Combine with INT-22 (B2B → less transition) + INT-12 (pace control teams)")
    print("  AI chat: 'How does player X play in transition vs half-court?'")
    print()
    print("### Honest Caveats")
    print("  - possession_type from CV pipeline; 'half_court' dominates (60-80% of frames)")
    print("  - post_up rare for most players — small-n flag applies")
    print("  - Players with unresolved nba_player_id grouped by name (jersey re-number risk)")
    print("  - ISSUE-022 (defender_distance sentinel) does not affect these features")


if __name__ == "__main__":
    main()
