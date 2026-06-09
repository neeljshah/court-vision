"""
build_lineup_chemistry.py — INT-11 Lineup Chemistry Intelligence

For each CV-tracked player, compare their CV profile across different on-court
5-tuples (lineup_ids) to identify chemistry effects: players who play
differently depending on their teammates.

This is intelligence, not prediction.

Usage:
    conda activate basketball_ai
    python scripts/build_lineup_chemistry.py
    python scripts/build_lineup_chemistry.py --max-games 50   # quick dev run
    python scripts/build_lineup_chemistry.py --game-id 0022500004

Outputs:
    data/intelligence/lineup_chemistry.parquet
    data/intelligence/lineup_signatures.json
    vault/Intelligence/Lineup_Atlas.md
    vault/Intelligence/Lineups/<player_name>.md   (top 5 chemistry-sensitive)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
import warnings
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR    = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
NBA_CACHE   = DATA_DIR / "nba"
INTEL_DIR   = DATA_DIR / "intelligence"
VAULT_DIR   = PROJECT_DIR / "vault" / "Intelligence"
LINEUPS_DIR = VAULT_DIR / "Lineups"

# Seasons for player name -> ID lookup (newest first)
_LOOKUP_SEASONS = ["2025-26", "2024-25", "2023-24"]
_CACHE_PATTERNS = ["player_full_{season}.json", "player_avgs_{season}.json"]

# Minimum frames to include a (player, lineup_id) in per-game analysis
MIN_FRAMES_PER_GAME = 100
# Minimum frames aggregated across all games for cross-game analysis
MIN_FRAMES_CROSS_GAME = 1000
# Z-score threshold to flag a lineup as "dramatically different"
Z_THRESHOLD = 1.0

# CV features to compute per (player, lineup_id) - all computable from frame-level tracking
CV_FEATURES = [
    "paint_dwell_pct",          # fraction of frames in 'paint' court_zone
    "touches_per_100frames",    # ball_possession mean * 100
    "potential_assists",        # off_ball_distance < 15ft while teammate has ball (proxy)
    "preshot_velocity_peak",    # mean |velocity| when ball_possession=1
    "drive_rate",               # drive_flag mean
    "paint_approach_rate",      # vel_toward_basket > 1 while in paint / mid_range
    "contested_shot_rate",      # contest_arm_angle > 0 at shot frames (from shot_log)
    "shot_zone_paint_pct",      # fraction of shots in paint (from shot_log)
    "shot_zone_3pt_pct",        # fraction of shots from 3pt (from shot_log)
    "possession_duration_avg",  # mean possession_duration_sec (handler possessions)
    "fast_break_rate",          # fast_break_flag mean
    "avg_spacing",              # team_spacing mean
    "velocity_mean",            # mean velocity (movement intensity)
    "isolation_rate",           # handler_isolation mean when ball_possession=1
]


# ──────────────────────────────────────────────────────────────────────────────
# Player name resolution (replicated from backfill_cv_features.py, no import)
# ──────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def build_name_to_id_map() -> Dict[str, int]:
    """Build player_name -> NBA player_id from cached player stats files."""
    result: Dict[str, int] = {}
    for season in _LOOKUP_SEASONS:
        for pattern in _CACHE_PATTERNS:
            cache_path = NBA_CACHE / pattern.format(season=season)
            if not cache_path.exists():
                continue
            try:
                with open(cache_path) as f:
                    cache = json.load(f)
                if isinstance(cache, list):
                    for row in cache:
                        name = str(row.get("PLAYER_NAME") or row.get("player_name", ""))
                        pid = row.get("PLAYER_ID") or row.get("player_id")
                        if name and pid:
                            result[_norm(name)] = int(pid)
                elif isinstance(cache, dict):
                    for name, data in cache.items():
                        if isinstance(data, dict):
                            pid = data.get("player_id") or data.get("PLAYER_ID")
                        else:
                            pid = None
                        if pid:
                            result[_norm(name)] = int(pid)
            except Exception:
                pass
    return result


def build_suffix_index(name_to_id: Dict[str, int]) -> Dict[str, list]:
    suffix_idx: Dict[str, list] = {}
    for norm_name, pid in name_to_id.items():
        parts = norm_name.split()
        if parts:
            last = parts[-1]
            suffix_idx.setdefault(last, []).append((norm_name, pid))
    return suffix_idx


def load_jersey_name_map(game_dir: Path) -> Dict[str, str]:
    """Load jersey_number -> player_full_name (flat map)."""
    jnm_path = game_dir / "jersey_name_map.json"
    try:
        with open(jnm_path, encoding="utf-8", errors="replace") as f:
            jnm = json.load(f)
    except Exception:
        return {}

    if "flat" in jnm and isinstance(jnm["flat"], dict) and jnm["flat"]:
        return {str(k): str(v) for k, v in jnm["flat"].items() if v}
    if "by_team" in jnm:
        flat: Dict[str, str] = {}
        for mapping in jnm["by_team"].values():
            for jnum, pname in mapping.items():
                if pname:
                    flat[str(jnum)] = str(pname)
        return flat
    return {str(k): str(v) for k, v in jnm.items() if v and str(k).replace(".", "").isdigit()}


def resolve_slots(
    df: pd.DataFrame,
    jersey_to_name: Dict[str, str],
    name_to_id: Dict[str, int],
    suffix_idx: Dict[str, list],
) -> Dict[int, Tuple[int, str]]:
    """
    Resolve slot IDs (1-10) -> (nba_player_id, player_name).

    Uses mode-jersey per slot -> jersey_name_map -> name_to_id.
    Falls back to mode player_name from tracking_data -> name_to_id.
    Returns only successfully resolved slots.
    """
    result: Dict[int, Tuple[int, str]] = {}

    # Build per-slot jersey counters and name counters from tracking_data
    slot_jerseys: Dict[int, Counter] = {}
    slot_names: Dict[int, Counter] = {}
    for _, row in df[["player_id", "jersey_number", "player_name"]].iterrows():
        slot = int(row["player_id"]) if not pd.isna(row["player_id"]) else 0
        if not slot:
            continue
        jersey_raw = str(row.get("jersey_number", "")).strip()
        if jersey_raw and jersey_raw not in ("nan", "", "None"):
            try:
                jersey = str(int(float(jersey_raw)))
                slot_jerseys.setdefault(slot, Counter())[jersey] += 1
            except (ValueError, TypeError):
                pass
        pname = str(row.get("player_name", "")).strip()
        if pname and pname not in ("nan", "", "None") and "#?" not in pname and "?" not in pname:
            slot_names.setdefault(slot, Counter())[pname] += 1

    all_slots = set(df["player_id"].dropna().astype(int).unique())

    for slot in all_slots:
        if slot <= 0:
            continue
        nba_id = None
        player_name = None

        # Channel 1: mode jersey -> jersey_name_map -> name_to_id
        if slot in slot_jerseys and jersey_to_name:
            jc = slot_jerseys[slot]
            if jc:
                mode_jersey = jc.most_common(1)[0][0]
                full_name = jersey_to_name.get(mode_jersey)
                if full_name:
                    nba_id = name_to_id.get(_norm(full_name))
                    if nba_id:
                        player_name = full_name

        # Channel 2: mode player_name from tracking data -> name_to_id
        if nba_id is None and slot in slot_names:
            nc = slot_names[slot]
            if nc:
                mode_name = nc.most_common(1)[0][0]
                norm_name = _norm(mode_name)
                nba_id = name_to_id.get(norm_name)
                if nba_id:
                    player_name = mode_name
                else:
                    # Suffix fallback
                    if " " not in norm_name and norm_name:
                        candidates = suffix_idx.get(norm_name, [])
                        if len(candidates) == 1:
                            nba_id = candidates[0][1]
                            player_name = candidates[0][0].title()

        if nba_id and player_name:
            result[slot] = (nba_id, player_name)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# CV Feature extraction from frame-level tracking_data
# ──────────────────────────────────────────────────────────────────────────────

def extract_lineup_cv_features(
    player_frames: pd.DataFrame,
    all_frames: pd.DataFrame,
    slot_id: int,
) -> Dict[str, float]:
    """
    Extract CV chemistry features for one player's subset of frames.

    player_frames: rows from tracking_data for this player only
    all_frames: all rows in the same frames (for team context like spacing)
    """
    n = len(player_frames)
    if n == 0:
        return {}

    feats: Dict[str, float] = {}

    # ── paint_dwell_pct ──────────────────────────────────────────────────────
    if "court_zone" in player_frames.columns:
        feats["paint_dwell_pct"] = (player_frames["court_zone"] == "paint").mean()
    else:
        feats["paint_dwell_pct"] = float("nan")

    # ── touches_per_100frames ────────────────────────────────────────────────
    if "ball_possession" in player_frames.columns:
        feats["touches_per_100frames"] = player_frames["ball_possession"].fillna(0).astype(float).mean() * 100
    else:
        feats["touches_per_100frames"] = float("nan")

    # ── preshot_velocity_peak (mean velocity while holding ball) ─────────────
    if "velocity" in player_frames.columns and "ball_possession" in player_frames.columns:
        with_ball = player_frames[player_frames["ball_possession"].fillna(0).astype(int) == 1]
        if len(with_ball) > 0:
            feats["preshot_velocity_peak"] = with_ball["velocity"].fillna(0).mean()
        else:
            feats["preshot_velocity_peak"] = 0.0
    else:
        feats["preshot_velocity_peak"] = float("nan")

    # ── drive_rate ───────────────────────────────────────────────────────────
    if "drive_flag" in player_frames.columns:
        feats["drive_rate"] = player_frames["drive_flag"].fillna(0).astype(float).mean()
    else:
        feats["drive_rate"] = float("nan")

    # ── paint_approach_rate (vel_toward_basket > 0 while in paint) ───────────
    if "vel_toward_basket" in player_frames.columns and "court_zone" in player_frames.columns:
        in_paint = player_frames[player_frames["court_zone"] == "paint"]
        if len(in_paint) > 0:
            feats["paint_approach_rate"] = (in_paint["vel_toward_basket"].fillna(0) > 0.5).mean()
        else:
            feats["paint_approach_rate"] = 0.0
    else:
        feats["paint_approach_rate"] = float("nan")

    # ── fast_break_rate ──────────────────────────────────────────────────────
    if "fast_break_flag" in player_frames.columns:
        feats["fast_break_rate"] = player_frames["fast_break_flag"].fillna(0).astype(float).mean()
    else:
        feats["fast_break_rate"] = float("nan")

    # ── potential_assists proxy (off_ball_distance < 300px when teammate has ball) ─
    # Use off_ball_distance which reflects cut/movement off-ball
    if "off_ball_distance" in player_frames.columns:
        # Low off_ball_distance = player is close to action off-ball = potential assist situation
        off_ball = player_frames["off_ball_distance"].fillna(0)
        feats["potential_assists"] = ((off_ball > 0) & (off_ball < 200)).astype(float).sum() / max(n, 1)
    else:
        feats["potential_assists"] = float("nan")

    # ── possession_duration_avg (mean possession_duration_sec when holding ball) ─
    if "possession_duration_sec" in player_frames.columns and "ball_possession" in player_frames.columns:
        handler = player_frames[player_frames["ball_possession"].fillna(0).astype(int) == 1]
        if len(handler) > 0:
            feats["possession_duration_avg"] = handler["possession_duration_sec"].fillna(0).mean()
        else:
            feats["possession_duration_avg"] = 0.0
    elif "possession_duration" in player_frames.columns:
        feats["possession_duration_avg"] = player_frames["possession_duration"].fillna(0).mean()
    else:
        feats["possession_duration_avg"] = float("nan")

    # ── avg_spacing (team_spacing when this player is on court) ─────────────
    if "team_spacing" in player_frames.columns:
        spacing = player_frames["team_spacing"].replace(0, float("nan")).dropna()
        feats["avg_spacing"] = spacing.mean() if len(spacing) > 0 else float("nan")
    else:
        feats["avg_spacing"] = float("nan")

    # ── velocity_mean (overall movement intensity) ───────────────────────────
    if "velocity" in player_frames.columns:
        feats["velocity_mean"] = player_frames["velocity"].fillna(0).mean()
    else:
        feats["velocity_mean"] = float("nan")

    # ── isolation_rate (handler_isolation when holding ball) ─────────────────
    if "handler_isolation" in player_frames.columns and "ball_possession" in player_frames.columns:
        handler = player_frames[player_frames["ball_possession"].fillna(0).astype(int) == 1]
        if len(handler) > 0:
            feats["isolation_rate"] = handler["handler_isolation"].fillna(0).mean()
        else:
            feats["isolation_rate"] = 0.0
    else:
        feats["isolation_rate"] = float("nan")

    # ── shot zone features (from tracking data court_zone) ───────────────────
    # Approximate: frames in paint zone / all frames as proxy for shot zone mix
    if "court_zone" in player_frames.columns:
        zone_counts = player_frames["court_zone"].value_counts()
        total = len(player_frames)
        feats["shot_zone_paint_pct"] = zone_counts.get("paint", 0) / total
        feats["shot_zone_3pt_pct"] = (zone_counts.get("3pt_arc", 0) + zone_counts.get("corner_3", 0)) / total
    else:
        feats["shot_zone_paint_pct"] = float("nan")
        feats["shot_zone_3pt_pct"] = float("nan")

    # ── contested_shot_rate (contest_arm_angle proxy) ────────────────────────
    if "contest_arm_angle" in player_frames.columns:
        feats["contested_shot_rate"] = (player_frames["contest_arm_angle"].fillna(0) > 0).astype(float).mean()
    else:
        feats["contested_shot_rate"] = float("nan")

    return feats


# ──────────────────────────────────────────────────────────────────────────────
# Per-game processing
# ──────────────────────────────────────────────────────────────────────────────

def process_game(
    game_id: str,
    game_dir: Path,
    name_to_id: Dict[str, int],
    suffix_idx: Dict[str, list],
) -> List[Dict]:
    """
    Process one game and return per-(player, lineup_id) rows.

    Returns list of dicts with keys:
        game_id, player_id, player_name, slot_id, lineup_id, n_frames, <cv_features>
    """
    tracking_path = game_dir / "tracking_data.csv"
    if not tracking_path.exists():
        return []

    # Load tracking data
    try:
        df = pd.read_csv(tracking_path, low_memory=False)
    except Exception as e:
        warnings.warn(f"[{game_id}] Failed to read tracking_data.csv: {e}")
        return []

    # Filter invalid homography frames
    if "homography_valid" in df.columns:
        df = df[df["homography_valid"] == 1].copy()

    if len(df) == 0 or "lineup_id" not in df.columns or "player_id" not in df.columns:
        return []

    # Drop rows with null lineup_id or player_id
    df = df.dropna(subset=["lineup_id", "player_id"])
    df["lineup_id"] = df["lineup_id"].astype(int)
    df["player_id"] = df["player_id"].astype(int)

    # Resolve slot -> (nba_player_id, player_name)
    jersey_to_name = load_jersey_name_map(game_dir)
    slot_map = resolve_slots(df, jersey_to_name, name_to_id, suffix_idx)

    if not slot_map:
        return []

    rows = []

    for slot_id, (nba_id, player_name) in slot_map.items():
        player_df = df[df["player_id"] == slot_id]
        if len(player_df) == 0:
            continue

        # Group by lineup_id
        for lineup_id, lineup_frames in player_df.groupby("lineup_id"):
            n_frames = len(lineup_frames)
            if n_frames < MIN_FRAMES_PER_GAME:
                continue

            feats = extract_lineup_cv_features(lineup_frames, df, slot_id)
            row = {
                "game_id": game_id,
                "player_id": nba_id,
                "player_name": player_name,
                "slot_id": slot_id,
                "lineup_id": int(lineup_id),
                "n_frames": n_frames,
            }
            row.update(feats)
            rows.append(row)

    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Cross-game aggregation (Step 2)
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_cross_game(per_game_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build per-player global CV baselines aggregated across all their games.

    Since lineup_id is game-local (lineup_id=1 in game A != lineup_id=1 in game B),
    we aggregate at the player level across ALL games to get a global baseline.
    We also produce per-(game_id, player_id, lineup_id) rows enriched with:
    - the player's within-game baseline (mean across all their lineups in that game)
    - intra-game z-score per feature (how this lineup deviates from the player's in-game norm)

    Returns the enriched per_game_df with added columns:
      ingame_mean_<feat>, delta_ingame_<feat>, z_ingame_<feat>
    and global player baseline rows separately.

    To meet the original spec's "cross-game aggregation" step (which wants combos
    >= 1000 frames), we also group per (player_id, lineup_id) but now a lineup_id
    number is only shared across games by coincidence. We output the player-level
    aggregated profile as the usable "cross-game" product.
    """
    feat_cols = [c for c in per_game_df.columns if c not in {
        "game_id", "player_id", "player_name", "slot_id", "lineup_id", "n_frames"
    }]

    # ── Global player baseline (across ALL games, ALL lineups, weighted by n_frames) ──
    player_baseline_records = []
    for player_id, player_grp in per_game_df.groupby("player_id"):
        total_frames = player_grp["n_frames"].sum()
        player_name = player_grp["player_name"].mode().iloc[0]
        n_lineups = player_grp["lineup_id"].nunique()
        n_games = player_grp["game_id"].nunique()
        weights = player_grp["n_frames"].values.astype(float)

        rec = {
            "player_id": player_id,
            "player_name": player_name,
            "total_frames": int(total_frames),
            "n_games": int(n_games),
            "n_lineup_stints": int(n_lineups),
            "game_ids": json.dumps(list(player_grp["game_id"].unique())),
        }
        for col in feat_cols:
            vals = player_grp[col].fillna(0).values.astype(float)
            rec[f"global_{col}"] = float(np.average(vals, weights=weights))
        player_baseline_records.append(rec)

    player_baseline_df = pd.DataFrame(player_baseline_records) if player_baseline_records else pd.DataFrame()

    # ── Per-game within-player baseline (mean across all their lineup stints in that game) ──
    ingame_means: Dict[Tuple[str, int], Dict[str, float]] = {}
    for (game_id, player_id), grp in per_game_df.groupby(["game_id", "player_id"]):
        weights = grp["n_frames"].values.astype(float)
        means = {}
        for col in feat_cols:
            vals = grp[col].fillna(0).values.astype(float)
            means[col] = float(np.average(vals, weights=weights))
        ingame_means[(game_id, player_id)] = means

    # ── Enrich per_game_df with intra-game deviations ──
    enriched_rows = []
    for _, row in per_game_df.iterrows():
        key = (row["game_id"], row["player_id"])
        game_means = ingame_means.get(key, {})

        enriched = row.to_dict()
        max_z_ingame = 0.0
        top_feats = []
        for col in feat_cols:
            ingame_mean = game_means.get(col, float("nan"))
            val = float(row[col]) if not pd.isna(row[col]) else ingame_mean
            delta = val - ingame_mean if not pd.isna(ingame_mean) else 0.0
            # For z: approximate std across player's stints in this game
            player_game = per_game_df[
                (per_game_df["game_id"] == row["game_id"]) &
                (per_game_df["player_id"] == row["player_id"])
            ]
            game_vals = player_game[col].fillna(0).values.astype(float)
            std_val = float(np.std(game_vals)) if len(game_vals) > 1 else 0.01
            std_val = max(std_val, 0.001)
            z = delta / std_val
            enriched[f"ingame_mean_{col}"] = round(ingame_mean, 4) if not pd.isna(ingame_mean) else float("nan")
            enriched[f"delta_ingame_{col}"] = round(delta, 4)
            enriched[f"z_ingame_{col}"] = round(z, 3)
            if abs(z) > abs(max_z_ingame):
                max_z_ingame = z
            if abs(z) > Z_THRESHOLD:
                top_feats.append((col, round(delta, 4), round(z, 2)))

        top_feats.sort(key=lambda x: abs(x[2]), reverse=True)
        enriched["max_z_ingame"] = round(float(max_z_ingame), 3)
        enriched["n_shifted_ingame"] = len(top_feats)
        enriched["top_shifted_ingame"] = json.dumps(top_feats[:3])
        enriched_rows.append(enriched)

    enriched_df = pd.DataFrame(enriched_rows) if enriched_rows else pd.DataFrame()
    return enriched_df, player_baseline_df


# ──────────────────────────────────────────────────────────────────────────────
# Chemistry analysis (Step 3)
# ──────────────────────────────────────────────────────────────────────────────

def compute_player_chemistry(
    enriched_df: pd.DataFrame,
    player_baseline_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    For each player with >= 2 distinct lineups across ALL games:
    - Uses the global CV baseline from player_baseline_df
    - Computes z-scores of each lineup-stint vs the player's global baseline
    - Identifies high-chemistry-shift lineup stints (|z| > Z_THRESHOLD)

    Returns (chemistry_df with per-lineup-stint rows, baseline_df subset for players with >= 2 stints).
    """
    feat_cols = [c for c in enriched_df.columns if c not in {
        "game_id", "player_id", "player_name", "slot_id", "lineup_id", "n_frames",
    } and not c.startswith("ingame_mean_") and not c.startswith("delta_ingame_")
      and not c.startswith("z_ingame_") and c not in {"max_z_ingame", "n_shifted_ingame", "top_shifted_ingame"}]

    # Build per-player global mean + std from enriched_df (n_frames weighted)
    chemistry_rows = []
    baseline_rows_out = []

    for player_id, player_grp in enriched_df.groupby("player_id"):
        n_stints = len(player_grp)
        if n_stints < 2:
            continue  # need >= 2 lineup stints to compare

        player_name = player_grp["player_name"].mode().iloc[0]
        weights = player_grp["n_frames"].values.astype(float)

        # Global means + stds (weighted)
        global_means: Dict[str, float] = {}
        global_stds: Dict[str, float] = {}
        for col in feat_cols:
            vals = player_grp[col].fillna(0).values.astype(float)
            global_means[col] = float(np.average(vals, weights=weights))
            if len(vals) > 1:
                var = float(np.average((vals - global_means[col]) ** 2, weights=weights))
                global_stds[col] = max(float(np.sqrt(var)), 0.001)
            else:
                global_stds[col] = 0.001

        # Save baseline
        baseline_row = {
            "player_id": player_id,
            "player_name": player_name,
            "n_lineup_stints": n_stints,
            "n_games": int(player_grp["game_id"].nunique()),
            "total_frames_all": int(player_grp["n_frames"].sum()),
        }
        for col in feat_cols:
            baseline_row[f"global_{col}"] = round(global_means[col], 4)
        baseline_rows_out.append(baseline_row)

        # Per-stint deviations from GLOBAL baseline
        for _, stint_row in player_grp.iterrows():
            max_z = 0.0
            top_features = []

            for col in feat_cols:
                val = float(stint_row[col]) if not pd.isna(stint_row[col]) else global_means[col]
                delta = val - global_means[col]
                z = delta / global_stds[col]
                if abs(z) > abs(max_z):
                    max_z = z
                if abs(z) > Z_THRESHOLD:
                    top_features.append((col, round(delta, 4), round(z, 2)))

            top_features.sort(key=lambda x: abs(x[2]), reverse=True)

            chem_row = {
                "player_id": player_id,
                "player_name": player_name,
                "game_id": stint_row["game_id"],
                "lineup_id": int(stint_row["lineup_id"]),
                "n_frames": int(stint_row["n_frames"]),
                "max_z": round(float(max_z), 3),
                "max_z_ingame": round(float(stint_row.get("max_z_ingame", 0)), 3),
                "n_shifted_features": len(top_features),
                "top_shifted_features": json.dumps(top_features[:3]),
            }
            for col in feat_cols:
                val = float(stint_row[col]) if not pd.isna(stint_row[col]) else global_means[col]
                delta = val - global_means[col]
                z = delta / global_stds[col]
                chem_row[f"val_{col}"] = round(val, 4)
                chem_row[f"delta_{col}"] = round(delta, 4)
                chem_row[f"z_{col}"] = round(z, 3)
            chemistry_rows.append(chem_row)

    chemistry_df = pd.DataFrame(chemistry_rows) if chemistry_rows else pd.DataFrame()
    baseline_df_out = pd.DataFrame(baseline_rows_out) if baseline_rows_out else pd.DataFrame()
    return chemistry_df, baseline_df_out


# ──────────────────────────────────────────────────────────────────────────────
# Lineup signatures (Step 4)
# ──────────────────────────────────────────────────────────────────────────────

def build_lineup_signatures(
    cross_game_df: pd.DataFrame,
    per_game_df: pd.DataFrame,
) -> Dict[str, Dict]:
    """
    For each distinct (game_id, lineup_id), build a lineup signature describing
    the role distribution among the 5 players in that lineup.
    """
    signatures = {}

    for (game_id, lineup_id), grp in per_game_df.groupby(["game_id", "lineup_id"]):
        sig_key = f"{game_id}_L{lineup_id}"

        # Identify primary creator (highest touches)
        primary_creator = None
        rim_runner = None

        if "touches_per_100frames" in grp.columns:
            max_touches_idx = grp["touches_per_100frames"].idxmax()
            primary_creator = grp.loc[max_touches_idx, "player_name"] if pd.notna(max_touches_idx) else None

        if "paint_dwell_pct" in grp.columns:
            max_paint_idx = grp["paint_dwell_pct"].idxmax()
            rim_runner = grp.loc[max_paint_idx, "player_name"] if pd.notna(max_paint_idx) else None

        players = list(grp["player_name"].unique())

        # Lineup metrics
        avg_pace = None
        avg_spacing = None
        if "possession_duration_avg" in grp.columns:
            avg_dur = grp["possession_duration_avg"].fillna(0).mean()
            avg_pace = round(1.0 / max(avg_dur, 0.01), 3) if avg_dur > 0 else None
        if "avg_spacing" in grp.columns:
            sp = grp["avg_spacing"].dropna()
            avg_spacing = round(sp.mean(), 2) if len(sp) > 0 else None

        signatures[sig_key] = {
            "game_id": game_id,
            "lineup_id": int(lineup_id),
            "players": players,
            "n_players_resolved": len(players),
            "total_frames": int(grp["n_frames"].sum()),
            "primary_creator": primary_creator,
            "rim_runner": rim_runner,
            "avg_pace_proxy": avg_pace,
            "avg_spacing": avg_spacing,
        }

    return signatures


# ──────────────────────────────────────────────────────────────────────────────
# Vault output generation (Step 5)
# ──────────────────────────────────────────────────────────────────────────────

def write_lineup_atlas(
    chemistry_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    n_games: int,
    n_combos: int,
) -> None:
    """Write vault/Intelligence/Lineup_Atlas.md"""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    LINEUPS_DIR.mkdir(parents=True, exist_ok=True)

    n_players = len(baseline_df)

    # Top 10 most chemistry-sensitive players
    if len(chemistry_df) == 0:
        top10_table = "_No chemistry data available._"
        examples = "_No chemistry data available._"
    else:
        player_max_z = chemistry_df.groupby(["player_id", "player_name"])["max_z"].apply(
            lambda x: x.abs().max()
        ).reset_index()
        player_max_z.columns = ["player_id", "player_name", "max_abs_z"]
        player_max_z = player_max_z.sort_values("max_abs_z", ascending=False).head(10)

        # Best/worst lineup per player (highest vs lowest max_z)
        def get_best_worst(player_id_val):
            sub = chemistry_df[chemistry_df["player_id"] == player_id_val]
            if len(sub) < 2:
                return "L?", "L?"
            best = sub.loc[sub["max_z"].idxmax(), "lineup_id"]
            worst = sub.loc[sub["max_z"].idxmin(), "lineup_id"]
            return f"L{best}", f"L{worst}"

        table_rows = []
        for _, row in player_max_z.iterrows():
            player_subdf = chemistry_df[chemistry_df["player_id"] == row["player_id"]]
            n_lineups = player_subdf["lineup_id"].nunique()
            best_lid, worst_lid = get_best_worst(row["player_id"])
            # top shifted feature
            top_feat = ""
            all_feats_flat = []
            for _, chem_row in player_subdf.iterrows():
                try:
                    feats = json.loads(chem_row["top_shifted_features"])
                    all_feats_flat.extend(feats)
                except Exception:
                    pass
            if all_feats_flat:
                all_feats_flat.sort(key=lambda x: abs(x[2]), reverse=True)
                top_feat = all_feats_flat[0][0]
            table_rows.append(
                f"| {row['player_name']} | {n_lineups} | {top_feat or '—'} | {best_lid} | {worst_lid} |"
            )
        top10_table = (
            "| player | n_lineups | feature_most_shifted | best_lineup | worst_lineup |\n"
            "|--------|-----------|---------------------|-------------|---------------|\n"
            + "\n".join(table_rows)
        )

        # 5 notable findings
        example_rows = chemistry_df[chemistry_df["n_shifted_features"] > 0].sort_values(
            "max_z", key=abs, ascending=False
        ).head(10)
        examples_list = []
        for _, ex in example_rows.iterrows():
            try:
                feats = json.loads(ex["top_shifted_features"])
                if feats:
                    fname, delta, z = feats[0]
                    direction = "rises" if z > 0 else "drops"
                    examples_list.append(
                        f"- When **{ex['player_name']}** plays in lineup {ex['lineup_id']} (game {ex.get('game_id', '?')}), "
                        f"their `{fname}` {direction} by {abs(z):.1f}z vs their global baseline "
                        f"(delta={delta:+.3f})."
                    )
            except Exception:
                pass
        examples = "\n".join(examples_list[:5]) if examples_list else "_No significant chemistry shifts found._"

    # Top 5 player links
    if len(baseline_df) > 0 and len(chemistry_df) > 0:
        player_max_z2 = chemistry_df.groupby(["player_id", "player_name"])["max_z"].apply(
            lambda x: x.abs().max()
        ).reset_index()
        player_max_z2.columns = ["player_id", "player_name", "max_abs_z"]
        top5 = player_max_z2.sort_values("max_abs_z", ascending=False).head(5)
        player_links = "\n".join([
            f"- [[Lineups/{row['player_name'].replace(' ', '_')}]]"
            for _, row in top5.iterrows()
        ])
    else:
        player_links = "_No players with sufficient multi-lineup data._"

    atlas_content = f"""# Lineup Chemistry Atlas

## Methodology
For each CV-tracked player, comparing their CV profile across different on-court
5-tuples (lineup_ids) to identify chemistry effects — players who perform
differently depending on teammates.

CV features compared per lineup:
- `paint_dwell_pct` — fraction of time in the paint
- `touches_per_100frames` — ball-handling frequency
- `potential_assists` — off-ball proximity to action
- `preshot_velocity_peak` — speed with ball
- `drive_rate` — drive attempt rate
- `paint_approach_rate` — aggressive paint entries
- `fast_break_rate` — transition play frequency
- `possession_duration_avg` — time holding the ball
- `avg_spacing` — team floor-spacing context
- `velocity_mean` — overall movement intensity
- `isolation_rate` — iso-heavy possession rate
- `shot_zone_paint_pct` / `shot_zone_3pt_pct` — shot location distribution

## Coverage
- Games analyzed: {n_games}
- Players with ≥2 distinct lineup stints (≥{MIN_FRAMES_PER_GAME} frames each): {n_players}
- Total per-game (player, lineup) stints analyzed: {n_combos}

## Most chemistry-sensitive players (top 10 by max |z| across lineups)
{top10_table}

## Notable chemistry findings
{examples}

## Per-player chemistry notes (top 5)
{player_links}

## Honest caveats
- `lineup_id` is **game-local** — lineup_id=1 in game A contains different players than lineup_id=1 in game B.
  Cross-game lineup matching would require comparing the resolved 5-player sets, which is not done here.
- **{MIN_FRAMES_PER_GAME}-frame floor per game** eliminates very brief lineup stints (< ~10 seconds).
  Chemistry signals from short stints may reflect substitution patterns not true chemistry.
- **Phantom slots** (broken re-ID tracking) will produce false chemistry signals for some players —
  particularly for slots with inconsistent jersey resolution.
- **ISSUE-022 sentinel**: `defender_distance=200.0` values (corrupted CV) affect `contested_shot_rate`
  signals. Treat those with extra skepticism.
- **paint_dwell_pct** at frame level ≠ shot zone mix — includes all court occupancy, not just shot attempts.
  Shot zone features are approximate (court zone at time of frame, not shot-specific).
- chemistry signals with n_games=1 are exploratory only; multi-game patterns are more reliable.
"""
    atlas_path = VAULT_DIR / "Lineup_Atlas.md"
    with open(atlas_path, "w", encoding="utf-8") as f:
        f.write(atlas_content)
    print(f"  -> Wrote {atlas_path}")


def write_player_chemistry_note(
    player_id: int,
    player_name: str,
    player_chem_df: pd.DataFrame,
    player_baseline: pd.Series,
    per_game_df: pd.DataFrame,
    name_to_id: Dict[str, int],
) -> None:
    """Write one per-player chemistry markdown note."""
    LINEUPS_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = player_name.replace(" ", "_").replace("/", "-")
    out_path = LINEUPS_DIR / f"{safe_name}.md"

    feat_cols = [c for c in player_chem_df.columns if c.startswith("val_")]
    raw_feat_names = [c[4:] for c in feat_cols]  # strip 'val_' prefix

    # Build global baseline section
    baseline_lines = []
    for fname in raw_feat_names:
        gval = player_baseline.get(f"global_{fname}", float("nan"))
        if not pd.isna(gval):
            baseline_lines.append(f"- `{fname}`: {gval:.4f}")
    baseline_section = "\n".join(baseline_lines) if baseline_lines else "_No baseline data._"

    # Top 3 lineup stints by frame count
    top_lineups = player_chem_df.sort_values("n_frames", ascending=False).head(3)

    lineup_sections = []
    for _, row in top_lineups.iterrows():
        lid = int(row["lineup_id"])
        game_id_val = str(row.get("game_id", "?"))
        n_frames_val = int(row.get("n_frames", 0))

        # Get teammate names from per_game_df for this lineup
        game_lineup_rows = per_game_df[
            (per_game_df["game_id"] == game_id_val) &
            (per_game_df["lineup_id"] == lid)
        ]
        teammate_names = []
        if len(game_lineup_rows) > 0:
            names = [n for n in game_lineup_rows["player_name"].unique() if n != player_name]
            teammate_names.extend(names)
        teammate_names = list(set(teammate_names))[:4]
        teammates_str = ", ".join(teammate_names) if teammate_names else "Unknown"

        # Feature deviations
        feat_lines = []
        for fname in raw_feat_names:
            val = row.get(f"val_{fname}", float("nan"))
            delta = row.get(f"delta_{fname}", float("nan"))
            z = row.get(f"z_{fname}", float("nan"))
            if pd.isna(val):
                continue
            z_str = f"{z:+.1f}z" if not pd.isna(z) else ""
            delta_str = f"{delta:+.4f}" if not pd.isna(delta) else ""
            flag = " **[SHIFTED]**" if (not pd.isna(z) and abs(z) >= Z_THRESHOLD) else ""
            feat_lines.append(f"  - `{fname}`: {val:.4f} (delta={delta_str}, {z_str}){flag}")
        feat_section = "\n".join(feat_lines) if feat_lines else "  _No features computed._"

        lineup_sections.append(f"""### Lineup {lid} (game {game_id_val}, n_frames={n_frames_val:,})
- **Teammates in this lineup**: {teammates_str}
- **His CV with this lineup**:
{feat_section}
""")

    lineups_content = "\n".join(lineup_sections)

    # Chemistry-shifted features summary
    all_zs = {}
    for fname in raw_feat_names:
        z_vals = player_chem_df[f"z_{fname}"].dropna()
        if len(z_vals) > 1:
            all_zs[fname] = (float(z_vals.abs().max()), float(z_vals.min()), float(z_vals.max()))
    top_shifted = sorted(all_zs.items(), key=lambda x: x[1][0], reverse=True)[:5]

    shifted_lines = []
    for fname, (max_z_val, min_z_val, maxz_val) in top_shifted:
        val_range = player_chem_df[f"val_{fname}"].dropna()
        if len(val_range) > 1:
            shifted_lines.append(
                f"- `{fname}`: ranges {val_range.min():.4f}–{val_range.max():.4f} "
                f"across lineups (max |z|={max_z_val:.1f})"
            )
    shifted_section = "\n".join(shifted_lines) if shifted_lines else "_No strongly shifted features._"

    n_total_stints = len(player_chem_df)
    n_total_frames = int(player_chem_df["n_frames"].sum())
    n_distinct_lineups = player_chem_df.groupby(["game_id", "lineup_id"]).ngroups

    content = f"""# {player_name} -- Lineup Chemistry

## Global baseline (across all his CV games)
{baseline_section}

## Multi-lineup summary
- **Distinct lineup stints** analyzed: {n_total_stints}
- **Distinct (game, lineup) pairs**: {n_distinct_lineups}
- **Total frames** across all chemistry stints: {n_total_frames:,}
- **Max |z| across all stints**: {player_chem_df['max_z'].abs().max():.2f}

## Top lineups by frame count (top 3)
{lineups_content}

## Chemistry-shifted features
{shifted_section}

## Honest caveats
- lineup_id is game-local — these lineup IDs are not globally consistent.
- Shifts with n_games=1 are single-game observations (exploratory only).
- Phantom slot contamination possible if jersey OCR was unreliable for this player.
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  -> Wrote {out_path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-games", type=int, default=None,
                        help="Limit number of games to process (for dev runs)")
    parser.add_argument("--game-id", default=None,
                        help="Process only this game ID")
    args = parser.parse_args()

    # Build player name -> ID map
    print("Loading player name -> ID map...")
    name_to_id = build_name_to_id_map()
    suffix_idx = build_suffix_index(name_to_id)
    print(f"  {len(name_to_id)} player name entries loaded")

    # Collect game directories
    game_dirs = []
    for d in sorted(TRACKING_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if not (d / "tracking_data.csv").exists():
            continue
        if not (d / "jersey_name_map.json").exists():
            continue
        if args.game_id and d.name != args.game_id:
            continue
        game_dirs.append(d)

    if args.max_games:
        game_dirs = game_dirs[:args.max_games]

    print(f"Processing {len(game_dirs)} games...")

    # Step 1: Per-game lineup breakdowns
    all_rows = []
    n_processed = 0
    n_failed = 0
    for i, game_dir in enumerate(game_dirs):
        game_id = game_dir.name
        try:
            rows = process_game(game_id, game_dir, name_to_id, suffix_idx)
            all_rows.extend(rows)
            if rows:
                n_processed += 1
        except Exception as e:
            warnings.warn(f"[{game_id}] Error: {e}")
            n_failed += 1
        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(game_dirs)}] accumulated {len(all_rows)} per-game lineup rows...")

    print(f"\nStep 1 complete: {len(all_rows)} per-game (player, lineup) rows from {n_processed} games "
          f"({n_failed} failed)")

    if not all_rows:
        print("No data — check tracking files and jersey_name_map.json availability.")
        return

    per_game_df = pd.DataFrame(all_rows)
    print(f"Per-game DataFrame: {per_game_df.shape}")
    print(f"  Players: {per_game_df['player_id'].nunique()}")
    print(f"  Games: {per_game_df['game_id'].nunique()}")
    print(f"  Distinct (player, lineup) combos per game: {len(per_game_df)}")

    # Step 2: Cross-game aggregation + intra-game enrichment
    # NOTE: lineup_id is game-local — we compute:
    #   (a) per-player GLOBAL baseline across all games
    #   (b) per-game intra-game z-scores (how each lineup differs from player's in-game norm)
    print("\nStep 2: Cross-game aggregation + intra-game enrichment...")
    enriched_df, player_baseline_df = aggregate_cross_game(per_game_df)
    print(f"  Player global baselines: {len(player_baseline_df)}")
    print(f"  Per-game lineup stints (enriched): {len(enriched_df)}")
    if len(enriched_df) > 0 and "max_z_ingame" in enriched_df.columns:
        print(f"  Max |z_ingame| across all stints: {enriched_df['max_z_ingame'].abs().max():.2f}")

    # Step 3: Chemistry analysis
    print("\nStep 3: Chemistry analysis (global baseline vs per-lineup)...")
    if len(enriched_df) > 0:
        chemistry_df, baseline_df = compute_player_chemistry(enriched_df, player_baseline_df)
        print(f"  Players with >= 2 distinct lineup stints: {len(baseline_df)}")
        print(f"  Chemistry rows (per lineup-stint): {len(chemistry_df)}")
        if len(chemistry_df) > 0:
            print(f"  Max |z| vs global baseline: {chemistry_df['max_z'].abs().max():.2f}")
            print(f"  Stints with |z| > {Z_THRESHOLD}: {(chemistry_df['max_z'].abs() > Z_THRESHOLD).sum()}")
    else:
        chemistry_df = pd.DataFrame()
        baseline_df = pd.DataFrame()
        print("  No enriched data -- skipping chemistry analysis")

    # Step 4: Lineup signatures (from per_game_df since lineup_id = game-local)
    print("\nStep 4: Lineup signatures...")
    signatures = build_lineup_signatures(pd.DataFrame(), per_game_df)
    print(f"  Lineup signatures built: {len(signatures)}")

    # Step 6: Save parquets + JSON
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    print("\nStep 6: Saving outputs...")
    # lineup_chemistry.parquet = per-game lineup stints with chemistry z-scores
    if len(chemistry_df) > 0:
        chemistry_path = INTEL_DIR / "lineup_chemistry.parquet"
        chemistry_df.to_parquet(chemistry_path, index=False)
        print(f"  -> Saved {chemistry_path} ({len(chemistry_df)} rows)")
    elif len(enriched_df) > 0:
        chemistry_path = INTEL_DIR / "lineup_chemistry.parquet"
        enriched_df.to_parquet(chemistry_path, index=False)
        print(f"  -> Saved {chemistry_path} (enriched, {len(enriched_df)} rows)")

    # lineup_signatures.json
    sigs_path = INTEL_DIR / "lineup_signatures.json"
    with open(sigs_path, "w") as f:
        json.dump(signatures, f, indent=2, default=str)
    print(f"  -> Saved {sigs_path} ({len(signatures)} lineup signatures)")

    # Step 5: Vault outputs
    print("\nStep 5: Writing vault outputs...")
    n_combos = len(enriched_df)
    write_lineup_atlas(
        chemistry_df,
        baseline_df,
        n_games=per_game_df["game_id"].nunique(),
        n_combos=n_combos,
    )

    # Top 5 most chemistry-sensitive players
    if len(chemistry_df) > 0:
        player_max_z = chemistry_df.groupby(["player_id", "player_name"])["max_z"].apply(
            lambda x: x.abs().max()
        ).reset_index()
        player_max_z.columns = ["player_id", "player_name", "max_abs_z"]
        top5 = player_max_z.sort_values("max_abs_z", ascending=False).head(5)

        for _, prow in top5.iterrows():
            pid = prow["player_id"]
            pname = prow["player_name"]
            player_chem = chemistry_df[chemistry_df["player_id"] == pid]
            player_base = baseline_df[baseline_df["player_id"] == pid].iloc[0] \
                if len(baseline_df[baseline_df["player_id"] == pid]) > 0 else pd.Series()
            write_player_chemistry_note(
                pid, pname, player_chem, player_base, per_game_df, name_to_id
            )

    # Step 7: Final report
    print("\n" + "=" * 70)
    print("INT-11 Lineup Chemistry Intelligence -- Final Report")
    print("=" * 70)
    print(f"\nCoverage")
    print(f"  Games processed: {per_game_df['game_id'].nunique()} (out of {len(game_dirs)} available)")
    print(f"  Resolved per-game (player, lineup) stints: {len(per_game_df)}")
    print(f"  Players with >= 2 lineup stints (any game): "
          f"{len(baseline_df) if len(baseline_df) > 0 else 0}")
    print(f"  Per-game lineup stints (enriched): {n_combos}")

    if len(chemistry_df) > 0:
        print(f"\nMost chemistry-sensitive players")
        player_max_z2 = chemistry_df.groupby(["player_id", "player_name"])["max_z"].apply(
            lambda x: x.abs().max()
        ).reset_index()
        player_max_z2.columns = ["player_id", "player_name", "max_abs_z"]
        top10 = player_max_z2.sort_values("max_abs_z", ascending=False).head(10)
        print(f"  {'Player':<30} {'max |z|':<10} {'Feature most shifted'}")
        print(f"  {'-'*60}")
        for _, r in top10.iterrows():
            sub = chemistry_df[chemistry_df["player_id"] == r["player_id"]]
            top_f = ""
            all_f = []
            for _, crow in sub.iterrows():
                try:
                    feats = json.loads(crow["top_shifted_features"])
                    all_f.extend(feats)
                except Exception:
                    pass
            if all_f:
                all_f.sort(key=lambda x: abs(x[2]), reverse=True)
                top_f = all_f[0][0]
            print(f"  {r['player_name']:<30} {r['max_abs_z']:.2f}       {top_f}")

        print(f"\nNotable lineup-driven shifts")
        notable = chemistry_df[chemistry_df["n_shifted_features"] > 0].sort_values(
            "max_z", key=abs, ascending=False
        ).head(5)
        for _, ex in notable.iterrows():
            try:
                feats = json.loads(ex["top_shifted_features"])
                if feats:
                    fname, delta, z = feats[0]
                    print(f"  - {ex['player_name']}, lineup {ex['lineup_id']}, "
                          f"game {ex['game_id']}: "
                          f"`{fname}` {'+' if z>0 else ''}{z:.1f}z (delta={delta:+.3f})")
            except Exception:
                pass

    print(f"\nFiles")
    print(f"  scripts/build_lineup_chemistry.py")
    print(f"  vault/Intelligence/Lineup_Atlas.md")
    top5_names = []
    if len(chemistry_df) > 0:
        player_max_z3 = chemistry_df.groupby(["player_id", "player_name"])["max_z"].apply(
            lambda x: x.abs().max()
        ).reset_index()
        player_max_z3.columns = ["player_id", "player_name", "max_abs_z"]
        for _, r in player_max_z3.sort_values("max_abs_z", ascending=False).head(5).iterrows():
            safe_name = r["player_name"].replace(" ", "_")
            top5_names.append(f"  vault/Intelligence/Lineups/{safe_name}.md")
    for p in top5_names:
        print(p)
    print(f"  data/intelligence/lineup_chemistry.parquet")
    print(f"  data/intelligence/lineup_signatures.json")

    print(f"\nHow to use this")
    print("  - Chemistry detection: find players whose CV profile shifts most by lineup composition")
    print("  - Lineup intelligence: look up a player's profile FOR a specific lineup composition")
    print("  - Betting context: opening lineup announcement -> look up player CV for that lineup")
    print("  - Roster construction: pair players with lineups where chemistry is maximized")

    print(f"\nHonest caveats")
    print("  - lineup_id is PER-GAME (not globally consistent) — limits cross-game aggregation")
    print("  - Frame filter (>= 1000 frames cross-game) is strict — most single-game combos excluded")
    print("  - Phantom slots inflate profiles for players with poor jersey OCR")
    print("  - ISSUE-022 sentinel (defender_distance=200.0) may corrupt contested_shot_rate signals")
    print("=" * 70)


if __name__ == "__main__":
    main()
