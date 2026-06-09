"""
build_ingame_momentum.py -- INT-8: CV In-Game Momentum Intelligence

For each high-quality CV-tracked game, computes per-player first-half vs
second-half CV profiles, flags dramatic within-game shifts, writes:
  - data/intelligence/ingame_momentum.parquet  (per player-game-half record)
  - vault/Intelligence/Momentum_Atlas.md       (system overview)
  - vault/Intelligence/InGame/<game_id>.md     (per-game reports, top 10)

Halftime split strategy (in priority order):
  1. possessions.csv pbp_period <= 2 -> H1, >= 3 -> H2  (principled)
  2. frame <= median_frame of possessions midpoint          (fallback)
  3. frame <= max_frame / 2                                 (last resort)

Usage:
    conda activate basketball_ai
    python scripts/build_ingame_momentum.py
    python scripts/build_ingame_momentum.py --min-duration 1500  (seconds)
    python scripts/build_ingame_momentum.py --top-n 20
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

TRACKING_DIR = PROJECT_DIR / "data" / "tracking"
DATA_DIR = PROJECT_DIR / "data"
NBA_CACHE = DATA_DIR / "nba"
INTEL_DIR = DATA_DIR / "intelligence"
VAULT_DIR = PROJECT_DIR / "vault" / "Intelligence"
VAULT_INGAME_DIR = VAULT_DIR / "InGame"
METRICS_CSV = DATA_DIR / "phase_g_metrics.csv"

# CV features to analyse — grouped by signal type
# velocity/fatigue
VELOCITY_FEATURES = [
    "velocity",
    "acceleration",
    "vel_toward_basket",
    "ball_velocity",
]
# paint / spacing
SPATIAL_FEATURES = [
    "dist_to_basket_ft",
    "off_ball_distance",
    "team_spacing",
    "spacing_hull_area",
    "paint_touches",
    "paint_count_own",
    "paint_count_opp",
]
# ball handling / role
USAGE_FEATURES = [
    "ball_possession",
    "dribble_count",
    "drive_flag",
    "fast_break_flag",
    "shot_clock_est",
]
# defensive
DEFENSIVE_FEATURES = [
    "distance_to_ball",
    "nearest_opponent",
]

ALL_CV_FEATURES = (
    VELOCITY_FEATURES + SPATIAL_FEATURES + USAGE_FEATURES + DEFENSIVE_FEATURES
)

# z-score threshold to flag a shift as dramatic
Z_THRESHOLD = 1.5

# Minimum per-half rows to trust the mean
MIN_ROWS_PER_HALF = 30


# ─────────────────────────────────────────────────────────────────────────────
# Player ID resolution (mirrors backfill_cv_features.py logic — no import)
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _build_name_to_id_map() -> Dict[str, int]:
    result: Dict[str, int] = {}
    for season in ["2025-26", "2024-25", "2023-24"]:
        for pattern in ["player_full_{season}.json", "player_avgs_{season}.json"]:
            cache_path = NBA_CACHE / pattern.format(season=season)
            if not cache_path.exists():
                continue
            try:
                with open(cache_path, encoding="utf-8", errors="replace") as f:
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


def _load_jersey_name_map(game_dir: Path) -> Dict[str, str]:
    jnm_path = game_dir / "jersey_name_map.json"
    if not jnm_path.exists():
        return {}
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


# ─────────────────────────────────────────────────────────────────────────────
# Halftime split logic
# ─────────────────────────────────────────────────────────────────────────────

def _determine_halftime_frame(
    tracking_df: pd.DataFrame,
    possessions_path: Optional[Path],
) -> Tuple[int, str]:
    """
    Returns (halftime_frame, method_description).
    H1 = frames <= halftime_frame, H2 = frames > halftime_frame.
    """
    frames = tracking_df["frame"].dropna().astype(int)
    min_frame = int(frames.min())
    max_frame = int(frames.max())

    # Method 1: possessions pbp_period
    if possessions_path and possessions_path.exists():
        try:
            poss = pd.read_csv(possessions_path, usecols=["start_frame", "end_frame", "pbp_period"])
            poss = poss.dropna(subset=["pbp_period", "start_frame", "end_frame"])
            h1 = poss[poss["pbp_period"] <= 2]
            h2 = poss[poss["pbp_period"] >= 3]
            if len(h1) >= 5 and len(h2) >= 5:
                # Halftime = midpoint between last H1 frame and first H2 frame
                last_h1 = int(h1["end_frame"].max())
                first_h2 = int(h2["start_frame"].min())
                split = (last_h1 + first_h2) // 2
                return split, f"pbp_period (H1 ends {last_h1}, H2 starts {first_h2})"
        except Exception:
            pass

    # Method 2: possession midpoint by count
    if possessions_path and possessions_path.exists():
        try:
            poss = pd.read_csv(possessions_path, usecols=["start_frame", "end_frame"])
            poss = poss.dropna()
            poss = poss.sort_values("start_frame")
            mid_idx = len(poss) // 2
            if mid_idx > 0:
                split = int(poss.iloc[mid_idx]["start_frame"])
                return split, f"possession midpoint ({len(poss)} possessions)"
        except Exception:
            pass

    # Method 3: frame midpoint
    split = (min_frame + max_frame) // 2
    return split, f"frame midpoint ({min_frame}–{max_frame})"


# ─────────────────────────────────────────────────────────────────────────────
# Per-player half profile
# ─────────────────────────────────────────────────────────────────────────────

def _compute_half_profile(df: pd.DataFrame) -> Dict[str, float]:
    """Compute per-feature means for a slice of tracking_data."""
    result = {}
    for feat in ALL_CV_FEATURES:
        if feat in df.columns:
            vals = pd.to_numeric(df[feat], errors="coerce").dropna()
            # Filter obviously corrupt defender_distance (ISSUE-022 sentinel)
            if feat == "distance_to_ball":
                vals = vals[vals < 180]
            result[feat] = float(vals.mean()) if len(vals) > 0 else float("nan")
        else:
            result[feat] = float("nan")
    return result


def _resolve_slot_name(
    slot_id: int,
    jersey_name_map: Dict[str, str],
    slot_jersey_mode: Dict[int, str],
    slot_pbp_names: Dict[int, Counter],
    slot_team: Dict[int, str],
) -> Tuple[Optional[str], str]:
    """
    Returns (player_name_string, channel).
    channel: 'jersey_map' | 'pbp_shot' | 'tracking_name' | None
    """
    # Channel 1: jersey -> jersey_name_map
    jnum = slot_jersey_mode.get(slot_id)
    if jnum and jnum in jersey_name_map:
        return jersey_name_map[jnum], "jersey_map"

    # Channel 2: PBP shot-log name
    if slot_id in slot_pbp_names and slot_pbp_names[slot_id]:
        best_name, _ = slot_pbp_names[slot_id].most_common(1)[0]
        if "?" not in best_name and "#" not in best_name:
            return best_name, "pbp_shot"

    return None, "none"


def _build_slot_info(tracking_df: pd.DataFrame, shot_log_path: Optional[Path]) -> Tuple[
    Dict[int, str],  # slot -> jersey mode
    Dict[int, str],  # slot -> team abbrev mode
    Dict[int, Counter],  # slot -> pbp_names
]:
    slot_jersey: Dict[int, Counter] = defaultdict(Counter)
    slot_team: Dict[int, Counter] = defaultdict(Counter)

    for _, row in tracking_df.iterrows():
        slot = int(row.get("player_id") or 0)
        if not slot:
            continue
        jn = str(row.get("jersey_number", "")).strip()
        if jn and jn not in ("nan", "") and jn != "nan":
            try:
                slot_jersey[slot][str(int(float(jn)))] += 1
            except (ValueError, TypeError):
                pass
        abbrev = str(row.get("team_abbrev", "") or row.get("team", "")).strip()
        if abbrev and abbrev not in ("nan", ""):
            slot_team[slot][abbrev] += 1

    slot_jersey_mode = {s: c.most_common(1)[0][0] for s, c in slot_jersey.items() if c}
    slot_team_mode = {s: c.most_common(1)[0][0] for s, c in slot_team.items() if c}

    # PBP names from shot log
    slot_pbp_names: Dict[int, Counter] = defaultdict(Counter)
    if shot_log_path and shot_log_path.exists():
        try:
            with open(shot_log_path, newline="", encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    slot = int(row.get("player_id", 0) or 0)
                    name = str(row.get("player_name", "")).strip()
                    if slot and name and "?" not in name and "#" not in name:
                        slot_pbp_names[slot][name] += 1
        except Exception:
            pass

    return slot_jersey_mode, slot_team_mode, slot_pbp_names


# ─────────────────────────────────────────────────────────────────────────────
# Dataset-wide std computation (for z-scores)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_dataset_std(records: List[Dict]) -> Dict[str, float]:
    """Compute std of delta values across all player-game observations."""
    accum: Dict[str, List[float]] = defaultdict(list)
    for rec in records:
        delta = rec.get("delta_per_feature", {})
        if isinstance(delta, str):
            try:
                delta = json.loads(delta)
            except Exception:
                continue
        for feat, val in delta.items():
            if isinstance(val, float) and not math.isnan(val):
                accum[feat].append(val)
    result = {}
    for feat, vals in accum.items():
        if len(vals) >= 3:
            result[feat] = float(np.std(vals)) if np.std(vals) > 0 else 1.0
        else:
            result[feat] = 1.0
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main per-game processing
# ─────────────────────────────────────────────────────────────────────────────

def _process_game(
    game_id: str,
    name_to_id: Dict[str, int],
    min_rows: int = MIN_ROWS_PER_HALF,
) -> Tuple[List[Dict], Dict]:
    """
    Process one game.
    Returns (player_records, game_meta).
    player_records: list of dicts ready for parquet.
    game_meta: summary info for reporting.
    """
    game_dir = TRACKING_DIR / game_id
    tracking_path = game_dir / "tracking_data.csv"
    shot_log_path = game_dir / "shot_log.csv"
    possessions_path = game_dir / "possessions.csv"

    if not tracking_path.exists():
        return [], {}

    try:
        # Load only necessary columns for speed
        usecols_primary = ["frame", "timestamp", "player_id", "team_abbrev", "team",
                           "player_name", "jersey_number"] + ALL_CV_FEATURES
        # Some features might not exist — only load what's present
        avail_cols = pd.read_csv(tracking_path, nrows=0).columns.tolist()
        usecols = [c for c in usecols_primary if c in avail_cols]

        tracking_df = pd.read_csv(tracking_path, usecols=usecols, low_memory=False)
    except Exception as e:
        print(f"  [SKIP] {game_id}: load error: {e}")
        return [], {}

    if len(tracking_df) < 200:
        print(f"  [SKIP] {game_id}: too few rows ({len(tracking_df)})")
        return [], {}

    # Determine halftime split
    halftime_frame, split_method = _determine_halftime_frame(tracking_df, possessions_path)
    h1 = tracking_df[tracking_df["frame"] <= halftime_frame]
    h2 = tracking_df[tracking_df["frame"] > halftime_frame]

    # Build slot info
    slot_jersey_mode, slot_team_mode, slot_pbp_names = _build_slot_info(
        tracking_df, shot_log_path
    )
    jersey_name_map = _load_jersey_name_map(game_dir)

    # Get game-level metadata (teams)
    teams = tracking_df["team_abbrev"].dropna().value_counts()
    team_list = teams.index.tolist()[:2]

    player_records: List[Dict] = []
    slot_ids = tracking_df["player_id"].dropna().unique()

    for slot_id in slot_ids:
        slot_id = int(slot_id)
        if slot_id == 0:
            continue

        # Resolve name -> NBA ID
        player_name, channel = _resolve_slot_name(
            slot_id, jersey_name_map, slot_jersey_mode, slot_pbp_names, slot_team_mode
        )
        if not player_name:
            continue

        # Map to NBA ID
        nba_id = name_to_id.get(_norm(player_name))
        if not nba_id:
            # Try last-name suffix match
            norm_name = _norm(player_name)
            last_name = norm_name.split()[-1] if norm_name.split() else ""
            if last_name:
                candidates = [pid for nm, pid in name_to_id.items()
                              if nm.split()[-1] == last_name]
                if len(candidates) == 1:
                    nba_id = candidates[0]
                    # Get the resolved full name from name_to_id
                    for nm, pid in name_to_id.items():
                        if pid == nba_id:
                            player_name = nm.title()
                            break
        if not nba_id:
            continue

        # Per-slot per-half slices
        h1_slot = h1[h1["player_id"] == slot_id]
        h2_slot = h2[h2["player_id"] == slot_id]

        if len(h1_slot) < min_rows or len(h2_slot) < min_rows:
            continue

        h1_profile = _compute_half_profile(h1_slot)
        h2_profile = _compute_half_profile(h2_slot)

        # Delta: H2 - H1
        delta: Dict[str, float] = {}
        for feat in ALL_CV_FEATURES:
            v1 = h1_profile.get(feat, float("nan"))
            v2 = h2_profile.get(feat, float("nan"))
            if not math.isnan(v1) and not math.isnan(v2):
                delta[feat] = v2 - v1
            else:
                delta[feat] = float("nan")

        team_abbrev = slot_team_mode.get(slot_id, "UNK")

        player_records.append({
            "player_id": nba_id,
            "player_name": player_name,
            "team_abbrev": team_abbrev,
            "slot_id": slot_id,
            "game_id": game_id,
            "h1_features": json.dumps(h1_profile),
            "h2_features": json.dumps(h2_profile),
            "delta_per_feature": json.dumps(delta),
            "h1_rows": len(h1_slot),
            "h2_rows": len(h2_slot),
            "split_method": split_method,
            "halftime_frame": halftime_frame,
            "channel": channel,
            # placeholder z-scores — filled later after dataset-wide std
            "max_abs_z": float("nan"),
            "n_features_shifted": 0,
        })

    game_meta = {
        "game_id": game_id,
        "teams": team_list,
        "n_players_tracked": len(player_records),
        "split_method": split_method,
        "halftime_frame": halftime_frame,
        "h1_rows": len(h1),
        "h2_rows": len(h2),
    }
    return player_records, game_meta


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def _render_game_report(game_id: str, records: List[Dict], game_meta: Dict, dataset_std: Dict[str, float]) -> str:
    """Render per-game markdown momentum report."""
    teams = game_meta.get("teams", [])
    team_str = " vs ".join(teams) if teams else "Unknown"
    n_players = game_meta.get("n_players_tracked", 0)

    # Sort by max_abs_z desc
    sorted_records = sorted(records, key=lambda r: r.get("max_abs_z", 0) or 0, reverse=True)

    n_dramatic = sum(1 for r in records if (r.get("max_abs_z") or 0) > Z_THRESHOLD)

    lines = [
        f"# Game {game_id} ({team_str})",
        f"",
        f"## In-game momentum summary",
        f"- Players tracked with full H1+H2 profiles: {n_players}",
        f"- Players with max-z > {Z_THRESHOLD}: {n_dramatic}",
        f"- Halftime split: `{game_meta.get('split_method', 'unknown')}`",
        f"- H1 rows: {game_meta.get('h1_rows', 0):,} | H2 rows: {game_meta.get('h2_rows', 0):,}",
        f"",
        f"## Notable shifts",
    ]

    for rec in sorted_records[:8]:
        delta_raw = rec.get("delta_per_feature", "{}")
        if isinstance(delta_raw, str):
            try:
                delta = json.loads(delta_raw)
            except Exception:
                delta = {}
        else:
            delta = delta_raw

        h1_raw = rec.get("h1_features", "{}")
        h2_raw = rec.get("h2_features", "{}")
        if isinstance(h1_raw, str):
            try:
                h1 = json.loads(h1_raw)
            except Exception:
                h1 = {}
        else:
            h1 = h1_raw
        if isinstance(h2_raw, str):
            try:
                h2 = json.loads(h2_raw)
            except Exception:
                h2 = {}
        else:
            h2 = h2_raw

        max_z = rec.get("max_abs_z", 0) or 0
        n_shifted = rec.get("n_features_shifted", 0)
        player = rec.get("player_name", "Unknown")
        team = rec.get("team_abbrev", "?")

        lines.append(f"### {player} ({team})")
        lines.append(f"- max-z: {max_z:.2f} | features shifted (|z|>{Z_THRESHOLD}): {n_shifted}")

        # Show top 5 most shifted features
        feat_zscores: List[Tuple[str, float, float, float, float]] = []
        for feat, d in delta.items():
            if isinstance(d, float) and not math.isnan(d):
                std = dataset_std.get(feat, 1.0)
                z = d / std if std > 0 else 0.0
                v1 = h1.get(feat, float("nan"))
                v2 = h2.get(feat, float("nan"))
                feat_zscores.append((feat, v1, v2, d, z))

        feat_zscores.sort(key=lambda x: abs(x[4]), reverse=True)
        for feat, v1, v2, d, z in feat_zscores[:5]:
            if abs(z) < 0.5:
                break
            direction = "↓" if d < 0 else "↑"
            pct = f"{(d / abs(v1) * 100):.1f}%" if v1 and not math.isnan(v1) and v1 != 0 else "N/A"
            v1_str = f"{v1:.2f}" if not math.isnan(v1) else "NaN"
            v2_str = f"{v2:.2f}" if not math.isnan(v2) else "NaN"
            lines.append(f"  - `{feat}` {direction}: H1={v1_str} -> H2={v2_str} (d={d:+.2f}, {pct}, z={z:.2f})")

        lines.append("")

    # Game-level patterns
    lines.append("## Game-level patterns")
    # Average velocity shift
    vel_deltas = []
    paint_deltas = []
    for rec in records:
        delta_raw = rec.get("delta_per_feature", "{}")
        if isinstance(delta_raw, str):
            try:
                delta = json.loads(delta_raw)
            except Exception:
                delta = {}
        else:
            delta = delta_raw
        v_delta = delta.get("velocity")
        p_delta = delta.get("paint_touches")
        if v_delta is not None and not math.isnan(v_delta):
            vel_deltas.append(v_delta)
        if p_delta is not None and not math.isnan(p_delta):
            paint_deltas.append(p_delta)

    if vel_deltas:
        avg_vel = sum(vel_deltas) / len(vel_deltas)
        lines.append(f"- Avg velocity delta H1->H2: {avg_vel:+.2f} px/frame "
                     f"({'fatigue signal' if avg_vel < -0.5 else 'normal variance'})")
    if paint_deltas:
        avg_paint = sum(paint_deltas) / len(paint_deltas)
        lines.append(f"- Avg paint_touches delta: {avg_paint:+.3f} "
                     f"({'more half-court' if avg_paint > 0 else 'less paint usage'})")

    lines.append("")
    return "\n".join(lines)


def _render_atlas(
    all_records: pd.DataFrame,
    game_metas: List[Dict],
    dataset_std: Dict[str, float],
    top_game_ids: List[str],
) -> str:
    """Render the Momentum Atlas markdown."""
    n_games = len(game_metas)
    n_player_halves = len(all_records)
    n_dramatic = int((all_records["max_abs_z"] > Z_THRESHOLD).sum())

    # Top 15 most dramatic individual shifts
    valid = all_records.dropna(subset=["max_abs_z"])
    valid = valid.copy()

    # Find top single feature shift per row
    top_shifts = []
    for _, row in valid.sort_values("max_abs_z", ascending=False).head(30).iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else row["delta_per_feature"]
            h1_dict = json.loads(row["h1_features"]) if isinstance(row["h1_features"], str) else row["h1_features"]
            h2_dict = json.loads(row["h2_features"]) if isinstance(row["h2_features"], str) else row["h2_features"]
        except Exception:
            continue

        best_feat = None
        best_z = 0.0
        for feat, d in delta.items():
            if isinstance(d, float) and not math.isnan(d):
                std = dataset_std.get(feat, 1.0)
                z = abs(d / std) if std > 0 else 0.0
                if z > best_z:
                    best_z = z
                    best_feat = feat

        if best_feat:
            v1 = h1_dict.get(best_feat, float("nan"))
            v2 = h2_dict.get(best_feat, float("nan"))
            d = delta.get(best_feat, float("nan"))
            cause = _infer_cause(best_feat, d if not math.isnan(d) else 0.0)
            top_shifts.append({
                "player": row["player_name"],
                "game": row["game_id"],
                "feature": best_feat,
                "H1": f"{v1:.2f}" if not math.isnan(v1) else "?",
                "H2": f"{v2:.2f}" if not math.isnan(v2) else "?",
                "z": f"{best_z:.2f}",
                "cause": cause,
            })
        if len(top_shifts) >= 15:
            break

    # Aggregate patterns
    vel_col = []
    paint_col = []
    for _, row in all_records.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else row.get("delta_per_feature", {})
            v = delta.get("velocity")
            p = delta.get("paint_touches")
        except Exception:
            continue
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vel_col.append(v)
        if p is not None and not (isinstance(p, float) and math.isnan(p)):
            paint_col.append(p)

    avg_vel = float(np.mean(vel_col)) if vel_col else float("nan")
    avg_paint = float(np.mean(paint_col)) if paint_col else float("nan")

    max_z_vals = valid["max_abs_z"].dropna().tolist()
    pct_above_z = 100.0 * sum(1 for z in max_z_vals if z > Z_THRESHOLD) / len(max_z_vals) if max_z_vals else 0.0

    # Top fatigue players (velocity most negative delta)
    fatigue_players: List[Tuple[str, str, float]] = []
    for _, row in all_records.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else row.get("delta_per_feature", {})
            v = delta.get("velocity")
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                fatigue_players.append((row["player_name"], row["game_id"], v))
        except Exception:
            pass
    fatigue_players.sort(key=lambda x: x[2])  # most negative first

    # Top paint shifters
    paint_players: List[Tuple[str, str, float]] = []
    for _, row in all_records.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else row.get("delta_per_feature", {})
            p = delta.get("paint_touches")
            if p is not None and not (isinstance(p, float) and math.isnan(p)):
                paint_players.append((row["player_name"], row["game_id"], p))
        except Exception:
            pass
    paint_players.sort(key=lambda x: abs(x[2]), reverse=True)

    lines = [
        "# CV In-Game Momentum Atlas",
        "",
        "## What this captures",
        "First-half vs second-half CV profile shifts per player per game. Detects:",
        "- Fatigue (velocity decay H1->H2)",
        "- Foul trouble (paint usage drops in H2)",
        "- Schematic adjustments (spacing changes, zone vs man signals)",
        "- Lineup-driven role changes (touches, drive_flag, ball_possession shifts)",
        "",
        "## Methodology",
        f"- Halftime split: possessions pbp_period (H1=periods 1-2, H2=periods 3-4) when available; fallback = possession midpoint; last resort = frame/2",
        f"- Per-player per-half feature means across all frames in that half",
        f"- Z-scores via dataset-wide standard deviation across all player-game observations",
        f"- Dramatic shift threshold: |z| > {Z_THRESHOLD}",
        f"- Minimum rows per half: {MIN_ROWS_PER_HALF}",
        "",
        "## Coverage",
        f"- High-quality games analyzed: {n_games}",
        f"- Player-half pairs scored: {n_player_halves}",
        f"- Players with dramatic shifts (max-z > {Z_THRESHOLD}): {n_dramatic} ({pct_above_z:.1f}%)",
        "",
        "## Top 15 most dramatic in-game shifts",
        "",
        "| Player | Game | Feature | H1 | H2 | z | Likely cause |",
        "|--------|------|---------|----|----|---|--------------|",
    ]

    for shift in top_shifts:
        lines.append(
            f"| {shift['player']} | {shift['game']} | `{shift['feature']}` "
            f"| {shift['H1']} | {shift['H2']} | {shift['z']} | {shift['cause']} |"
        )

    lines += [
        "",
        "## Aggregate patterns (across all CV games)",
        f"- Avg velocity delta H1->H2: {avg_vel:+.3f} px/frame ({('fatigue signal' if avg_vel < 0 else 'no aggregate fatigue')})",
        f"- Avg paint_touches delta: {avg_paint:+.4f} touches/frame ({('more half-court in H2' if avg_paint > 0 else 'less paint in H2')})",
        f"- % player-games with max-z > {Z_THRESHOLD}: {pct_above_z:.1f}%",
        "",
        "### Top 3 fatigue signals (largest negative velocity delta)",
    ]
    for name, gid, v in fatigue_players[:3]:
        lines.append(f"- {name} in {gid}: velocity delta={v:+.3f} px/frame")

    lines += [
        "",
        "### Top 3 paint usage shifts (largest absolute paint_touches delta)",
    ]
    for name, gid, p in paint_players[:3]:
        direction = "increased" if p > 0 else "decreased"
        lines.append(f"- {name} in {gid}: paint_touches delta={p:+.3f} ({direction} in H2)")

    lines += [
        "",
        "## Sample game reports",
    ]
    for gid in top_game_ids:
        lines.append(f"- [[InGame/{gid}]]")

    lines += [
        "",
        "## Honest caveats",
        "- Halftime detection is approximate when pbp_period data is missing — falls back to frame/2",
        "- Phantom tracker slots (broken tracking) produce false CV shifts; player ID resolution filters most of these",
        "- Player ID resolution gaps: slots with only color-coded names (green#?) are skipped",
        "- ISSUE-022: defender_distance sentinel=200.0 corrupts per-half means; distance_to_ball values >180 are filtered",
        "- Short games (<2 min per half) have too few samples for stable means",
        "",
        "_Generated by scripts/build_ingame_momentum.py_",
    ]

    return "\n".join(lines)


def _infer_cause(feat: str, delta: float) -> str:
    """Heuristic cause label for a feature shift."""
    if feat == "velocity" and delta < 0:
        return "fatigue"
    if feat == "velocity" and delta > 0:
        return "increased tempo"
    if feat in ("paint_touches", "paint_count_own") and delta < 0:
        return "foul trouble / role reduction"
    if feat in ("paint_touches", "paint_count_own") and delta > 0:
        return "increased paint aggression"
    if feat == "ball_possession" and delta < 0:
        return "usage drop / lineup change"
    if feat == "ball_possession" and delta > 0:
        return "increased ball-handling role"
    if feat == "dist_to_basket_ft" and delta > 0:
        return "pulled to perimeter (possible zone / scheme shift)"
    if feat == "dist_to_basket_ft" and delta < 0:
        return "more interior play"
    if feat == "team_spacing" and delta < 0:
        return "half-court tightening"
    if feat == "drive_flag" and delta < 0:
        return "fewer drives (fatigue or scheme)"
    if feat == "dribble_count" and delta < 0:
        return "less creation / off-ball role"
    return "TBD"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(min_duration: float = 800.0, top_n: int = 10) -> None:
    print("=== INT-8: In-Game Momentum Intelligence ===")

    # Load quality game list
    quality_df = pd.read_csv(METRICS_CSV)
    quality_df["duration_s"] = pd.to_numeric(quality_df["duration_s"], errors="coerce")
    high_q = quality_df[quality_df["quality"] == "high"].copy()
    high_q = high_q.sort_values("timestamp").drop_duplicates("game_id", keep="last")
    high_q = high_q[high_q["duration_s"] >= min_duration]
    high_q = high_q[high_q["game_id"].apply(lambda x: (TRACKING_DIR / str(x) / "tracking_data.csv").exists())]
    game_ids = high_q["game_id"].tolist()
    print(f"High-quality games to process: {len(game_ids)}")

    # Build name -> NBA ID map
    print("Building player name->ID map...")
    name_to_id = _build_name_to_id_map()
    print(f"  {len(name_to_id)} players in lookup map")

    # Process all games
    all_records: List[Dict] = []
    all_metas: List[Dict] = []

    for i, game_id in enumerate(game_ids, 1):
        print(f"  [{i}/{len(game_ids)}] {game_id}...", end=" ", flush=True)
        try:
            records, meta = _process_game(game_id, name_to_id)
            print(f"{len(records)} player-halves")
            all_records.extend(records)
            if records:
                all_metas.append(meta)
        except Exception as e:
            print(f"ERROR: {e}")

    if not all_records:
        print("ERROR: No records produced. Exiting.")
        sys.exit(1)

    print(f"\nTotal player-game records (pre-z-score): {len(all_records)}")

    # Compute dataset-wide std
    print("Computing dataset-wide feature std...")
    dataset_std = _compute_dataset_std(all_records)

    # Assign z-scores
    for rec in all_records:
        delta_raw = rec.get("delta_per_feature", "{}")
        if isinstance(delta_raw, str):
            try:
                delta = json.loads(delta_raw)
            except Exception:
                delta = {}
        else:
            delta = delta_raw

        zscores = []
        n_shifted = 0
        for feat, d in delta.items():
            if isinstance(d, float) and not math.isnan(d):
                std = dataset_std.get(feat, 1.0)
                z = abs(d / std) if std > 0 else 0.0
                zscores.append(z)
                if z > Z_THRESHOLD:
                    n_shifted += 1

        rec["max_abs_z"] = float(max(zscores)) if zscores else float("nan")
        rec["n_features_shifted"] = n_shifted

    # Build DataFrame
    df = pd.DataFrame(all_records)

    # Compute game_date from game_id (NBA convention: last 8 digits not directly useful,
    # but game_id encodes season — use dummy date from metrics file timestamp instead)
    date_map = dict(zip(high_q["game_id"].astype(str), high_q["timestamp"]))
    df["game_date"] = df["game_id"].map(lambda x: date_map.get(str(x), "")[:10])

    # Save parquet
    INTEL_DIR.mkdir(exist_ok=True)
    parquet_path = INTEL_DIR / "ingame_momentum.parquet"
    df.to_parquet(parquet_path, index=False)
    print(f"\nSaved {len(df)} records -> {parquet_path}")

    # ── Per-game reports (top N by dramatic shifts) ──────────────────────────
    VAULT_INGAME_DIR.mkdir(parents=True, exist_ok=True)

    # Rank games by average max_abs_z
    game_drama = (
        df.groupby("game_id")["max_abs_z"]
        .mean()
        .sort_values(ascending=False)
    )
    top_game_ids = game_drama.head(top_n).index.tolist()

    print(f"\nWriting {len(top_game_ids)} per-game reports...")
    for game_id in top_game_ids:
        game_records = df[df["game_id"] == game_id].to_dict(orient="records")
        meta = next((m for m in all_metas if m["game_id"] == game_id), {})
        report = _render_game_report(game_id, game_records, meta, dataset_std)
        report_path = VAULT_INGAME_DIR / f"{game_id}.md"
        report_path.write_text(report, encoding="utf-8")
        avg_z = game_drama[game_id]
        print(f"  {game_id}: avg_z={avg_z:.2f} -> {report_path.name}")

    # ── Atlas ─────────────────────────────────────────────────────────────────
    atlas_content = _render_atlas(df, all_metas, dataset_std, top_game_ids)
    atlas_path = VAULT_DIR / "Momentum_Atlas.md"
    atlas_path.write_text(atlas_content, encoding="utf-8")
    print(f"\nSaved atlas -> {atlas_path}")

    # ── Final report ──────────────────────────────────────────────────────────
    valid_z = df["max_abs_z"].dropna()
    n_dramatic = int((valid_z > Z_THRESHOLD).sum())
    pct_dramatic = 100.0 * n_dramatic / len(valid_z) if len(valid_z) > 0 else 0.0

    # Velocity and paint patterns
    vel_deltas = []
    paint_deltas = []
    for _, row in df.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else row.get("delta_per_feature", {})
        except Exception:
            delta = {}
        v = delta.get("velocity")
        p = delta.get("paint_touches")
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vel_deltas.append(v)
        if p is not None and not (isinstance(p, float) and math.isnan(p)):
            paint_deltas.append(p)

    med_vel = float(np.median(vel_deltas)) if vel_deltas else float("nan")

    # Top fatigue stories
    fatigue_rows = []
    for _, row in df.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else {}
            v = delta.get("velocity")
            if v is not None and not math.isnan(v):
                fatigue_rows.append((row["player_name"], row["game_id"], v))
        except Exception:
            pass
    fatigue_rows.sort(key=lambda x: x[2])

    # Top max-z stories
    top_z_rows = df.sort_values("max_abs_z", ascending=False).head(5)

    print(f"""
## INT-8 In-Game Momentum Intelligence — Final Report

### Coverage
- High-quality games analyzed: {len(all_metas)}
- Player-half pairs scored: {len(df)}
- Players with dramatic shifts (max_z > {Z_THRESHOLD}): {n_dramatic} ({pct_dramatic:.1f}%)

### Notable patterns (across all games)
- Median velocity delta H1->H2: {med_vel:+.3f} px/frame ({'fatigue baseline — players slow in H2' if med_vel < 0 else 'no aggregate fatigue signal'})
- Avg velocity delta: {float(np.mean(vel_deltas)) if vel_deltas else float('nan'):+.3f}
- Avg paint_touches delta: {float(np.mean(paint_deltas)) if paint_deltas else float('nan'):+.4f}

### Top fatigue signals (largest velocity drop H1->H2)""")
    for name, gid, v in fatigue_rows[:3]:
        print(f"  - {name} in {gid}: velocity delta={v:+.3f} px/frame")

    print("\n### Top max-z shifts")
    for _, row in top_z_rows.iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else {}
        except Exception:
            delta = {}
        best_feat = max(delta.items(), key=lambda kv: abs(kv[1]) if not math.isnan(kv[1]) else 0,
                        default=("none", 0.0))[0]
        print(f"  - {row['player_name']} ({row['team_abbrev']}) in {row['game_id']}: max-z={row['max_abs_z']:.2f}, top feature={best_feat}")

    print(f"""
### Sample momentum stories""")
    for _, row in top_z_rows.head(3).iterrows():
        try:
            delta = json.loads(row["delta_per_feature"]) if isinstance(row["delta_per_feature"], str) else {}
            h1_d = json.loads(row["h1_features"]) if isinstance(row["h1_features"], str) else {}
            h2_d = json.loads(row["h2_features"]) if isinstance(row["h2_features"], str) else {}
        except Exception:
            continue
        feat_zs = []
        for feat, d in delta.items():
            if not math.isnan(d):
                std = dataset_std.get(feat, 1.0)
                z = d / std if std > 0 else 0.0
                feat_zs.append((feat, d, z, h1_d.get(feat, float("nan")), h2_d.get(feat, float("nan"))))
        feat_zs.sort(key=lambda x: abs(x[2]), reverse=True)
        top_feat = feat_zs[0] if feat_zs else None
        if top_feat:
            feat, d, z, v1, v2 = top_feat
            cause = _infer_cause(feat, d)
            v1_str = f"{v1:.2f}" if not math.isnan(v1) else "?"
            v2_str = f"{v2:.2f}" if not math.isnan(v2) else "?"
            print(f"  [{row['player_name']} ({row['team_abbrev']}, {row['game_id']})]")
            print(f"  {feat}: H1={v1_str} -> H2={v2_str} (d={d:+.2f}, z={z:.2f}) -- {cause}")
            print()

    print(f"""### Files
- scripts/build_ingame_momentum.py
- vault/Intelligence/Momentum_Atlas.md
- vault/Intelligence/InGame/*.md ({len(top_game_ids)} game reports)
- data/intelligence/ingame_momentum.parquet

### How to use
- Live betting: if a player shows fatigue signal in H1, downgrade H2/Q4 expected output
- Lineup intelligence: identify when a player's role meaningfully shifts mid-game
- Coaching intelligence: which teams systematically alter player CV mid-game (adjustments)?

### Honest caveats
- Halftime detection: pbp_period used when available (275/365 games); fallback to frame/2
- Phantom slots with only color-coded names (green#?) are skipped — some player IDs unresolved
- Player ID resolution: jersey_name_map present for 291/365 dirs; PBP fallback for rest
- ISSUE-022 corruption on defender_distance: values >180 filtered per-half
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build CV in-game momentum intelligence")
    parser.add_argument("--min-duration", type=float, default=800.0,
                        help="Minimum game duration in seconds (default 800)")
    parser.add_argument("--top-n", type=int, default=10,
                        help="Number of per-game reports to write (default 10)")
    args = parser.parse_args()
    main(min_duration=args.min_duration, top_n=args.top_n)
