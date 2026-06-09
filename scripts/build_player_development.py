"""
INT-15: Cross-Season Player Development Intelligence
Builds season-over-season CV feature trends to identify breakouts, declines,
and role shifts for NBA players tracked across multiple seasons.

Usage:
    python scripts/build_player_development.py

Outputs:
    data/intelligence/player_development.parquet
    data/intelligence/breakout_signals.json
    vault/Intelligence/Development_Atlas.md
    vault/Intelligence/Development/<player_name>.md  (top 15 most-developed)
"""
import sqlite3
import json
import os
import sys
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nba_ai.db"
PLAYER_FULL_JSON = PROJECT_ROOT / "data" / "nba" / "player_full_2024-25.json"
SEASON_GAMES_24 = PROJECT_ROOT / "data" / "nba" / "season_games_2024-25.json"
SEASON_GAMES_25 = PROJECT_ROOT / "data" / "nba" / "season_games_2025-26.json"
FINGERPRINTS_PARQUET = PROJECT_ROOT / "data" / "intelligence" / "player_fingerprints.parquet"

OUT_PARQUET = PROJECT_ROOT / "data" / "intelligence" / "player_development.parquet"
OUT_SIGNALS = PROJECT_ROOT / "data" / "intelligence" / "breakout_signals.json"
ATLAS_MD = PROJECT_ROOT / "vault" / "Intelligence" / "Development_Atlas.md"
DEV_DIR = PROJECT_ROOT / "vault" / "Intelligence" / "Development"

DEV_DIR.mkdir(parents=True, exist_ok=True)
(PROJECT_ROOT / "data" / "intelligence").mkdir(parents=True, exist_ok=True)

# Features with known cross-season SCALE INCONSISTENCIES due to pipeline version changes
# between 2024-25 and 2025-26 — excluded from primary trend analysis.
# (Identified by comparing per-season population means: ratio > 2x or < 0.5x)
SCALE_INCONSISTENT_FEATURES = {
    "avg_closeout_speed",         # all zeros both seasons
    "avg_contest_arm_angle",      # 0.050 vs 0.008 — 6x diff
    "avg_dribble_count",          # 0.008 vs 0.023 — 3x diff (very sparse)
    "avg_shot_clock_at_shot",     # 1.7 vs 4.9 — pipeline version change
    "avg_shot_distance",          # 19.0 vs 9.9 — 1.9x diff; outliers up to 89 feet (court coords)
    "avg_spacing",                # 9.0 vs 6.7 — outliers up to 94 feet (court pixel coords)
    "catch_shoot_pct",            # 0.49 vs 0.20 — 2.4x diff
    "contested_shot_rate",        # 0.028 vs 0.111 — 4x diff
    "cv_xast_pred",               # 1.85 vs 3.28 — growth partially pipeline version
    "defender_approach_speed",    # 0.052 vs 0.009 — 6x diff + ISSUE-022
    "made_pct",                   # 0.097 vs 0.211 — 2.2x diff
    "n_shots_tracked",            # 4.9 vs 1.2 — 4x diff (pipeline change)
    "play_type_drive_pct",        # all near-zero both seasons
    "play_type_isolation_pct",    # near-zero, dominated by sparse games
    "play_type_post_pct",         # all near-zero
    "preshot_velocity_peak",      # sparse; bimodal distribution
    "second_chance_rate",         # 0.054 vs 0.129 — 2.4x diff
    "shot_zone_3pt_pct",          # 0.306 vs 0.127 — 2.4x diff
    "shots_per_possession",       # 0.092 vs 0.025 — 3.7x diff
    "touches_per_game",           # 35.6 vs 15.2 — 2.3x diff (raw count vs normalized)
}

# Feature classification for trend categorisation
# Only features with CONSISTENT cross-season scale are used (ratio < 1.5x mean)
VOLUME_USAGE_FEATURES = {
    "paint_dwell_pct",           # stable: 0.030 vs 0.040 (1.3x)
    "potential_assists",         # stable: 0.97 vs 1.91 — growth is real (directional)
    "possession_duration_avg",   # stable: 10.4 vs 8.7 (1.2x)
    "play_type_transition_pct",  # stable: 0.173 vs 0.098 (1.8x — borderline)
}

STYLE_FEATURES = {
    "shot_zone_mid_range_pct",   # stable: 0.224 vs 0.342 (1.5x)
    "shot_zone_paint_pct",       # stable: 0.087 vs 0.058 (1.5x)
    "avg_fatigue_proxy",         # stable: 0.236 vs 0.216 (1.1x)
    "avg_defender_distance",     # 18.3 vs 9.3 — included but ISSUE-022 cautioned
}

# Features corrupted by ISSUE-022 — treat with caution
ISSUE_022_FEATURES = {"avg_defender_distance", "defender_approach_speed"}

MIN_GAMES_Y1 = 1   # 2024-25 CV coverage is sparse (14 games total) — allow 1-game Y1 with caveat
MIN_GAMES_Y2 = 3   # require at least 3 games in 2025-26 for a stable Y2 mean
MIN_GAMES_PER_SEASON = MIN_GAMES_Y1  # used in rookies filter (Y2 only)
TOP_N_NOTES = 15          # per-player markdown notes for top N most-developed
TOP_N_ATLAS = 10          # rows in each atlas table


# ──────────────────────────────────────────────────────────────────────────────
# Step 0 — Load data
# ──────────────────────────────────────────────────────────────────────────────

def load_cv_features() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT game_id, player_id, feature_name, feature_value FROM cv_features", conn)
    conn.close()
    return df


def load_player_name_map() -> dict:
    """Returns {nba_player_id: player_name} from player_full JSON."""
    if not PLAYER_FULL_JSON.exists():
        return {}
    with open(PLAYER_FULL_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        return {v["player_id"]: k.title() for k, v in raw.items() if "player_id" in v}
    return {}


def load_boxscore_names() -> dict:
    """Returns {player_id: player_name} from data/nba/boxscore_*.json as supplementary map."""
    nba_dir = PROJECT_ROOT / "data" / "nba"
    name_map = {}
    if not nba_dir.exists():
        return name_map
    for fname in nba_dir.iterdir():
        if fname.name.startswith("boxscore_") and fname.suffix == ".json":
            try:
                with open(fname, encoding="utf-8") as f:
                    bs = json.load(f)
                for p in bs.get("players", []):
                    if isinstance(p, dict):
                        pid = p.get("player_id")
                        pname = p.get("player_name") or p.get("name")
                        if pid and pname and pid not in name_map:
                            name_map[int(pid)] = pname
            except Exception:
                continue
    return name_map


def load_game_dates() -> dict:
    """Returns {game_id: game_date_str}."""
    dates = {}
    for path in [SEASON_GAMES_24, SEASON_GAMES_25]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        rows = raw.get("rows", []) if isinstance(raw, dict) else raw
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    gid = row.get("game_id", "")
                    gdate = row.get("game_date", "")
                    if gid:
                        dates[gid] = gdate
    return dates


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 — Build per-player season profiles
# ──────────────────────────────────────────────────────────────────────────────

def build_season_profiles(df_raw: pd.DataFrame, name_map: dict, game_dates: dict) -> dict:
    """
    Returns a dict:
        {player_id: {
            'name': str,
            'seasons': {season_str: {'mean': {feat: val}, 'n_games': int}}
        }}
    Only keeps players with valid nba_player_ids and multi-season records.
    """
    # Assign seasons based on game_id prefix
    df_raw["season"] = df_raw["game_id"].apply(
        lambda x: "2024-25" if x.startswith("00224") else ("2025-26" if x.startswith("00225") else "other")
    )
    df_raw = df_raw[df_raw["season"] != "other"].copy()

    # Pivot to wide format
    wide = df_raw.pivot_table(
        index=["game_id", "player_id", "season"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()

    # Numeric feature columns only
    feat_cols = [c for c in wide.columns if c not in ("game_id", "player_id", "season", "cv_archetype")]

    # Bug 27 guard: potential_assists=0 means xAST submodule did not run for that
    # game.  Null zeros so per-season mean is computed only over PA-active games.
    if "potential_assists" in wide.columns:
        wide.loc[wide["potential_assists"] == 0.0, "potential_assists"] = np.nan  # Bug 27 guard

    profiles = {}
    for player_id, grp in wide.groupby("player_id"):
        season_data = {}
        for season, sg in grp.groupby("season"):
            n_games = sg["game_id"].nunique()
            means = sg[feat_cols].mean(skipna=True).to_dict()
            season_data[season] = {"mean": means, "n_games": n_games}

        if len(season_data) < 2:
            continue  # need at least 2 seasons

        name = name_map.get(int(player_id), f"Player_{player_id}")
        profiles[int(player_id)] = {
            "name": name,
            "seasons": season_data,
        }

    return profiles, feat_cols


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 — Compute season-over-season deltas and z-scores
# ──────────────────────────────────────────────────────────────────────────────

def compute_population_stats(profiles: dict, feat_cols: list) -> dict:
    """
    Compute across all players (who have both seasons) the mean and std
    of their individual feature means, so we can z-score deltas.
    """
    all_vals = {f: [] for f in feat_cols}
    for pid, pdata in profiles.items():
        for season, sdata in pdata["seasons"].items():
            for f in feat_cols:
                v = sdata["mean"].get(f)
                if v is not None and not math.isnan(v):
                    all_vals[f].append(v)

    pop_stats = {}
    for f in feat_cols:
        vals = all_vals[f]
        if len(vals) > 1:
            pop_stats[f] = {"mean": float(np.mean(vals)), "std": max(float(np.std(vals)), 1e-6)}
        else:
            pop_stats[f] = {"mean": 0.0, "std": 1.0}
    return pop_stats


def compute_cross_season_deltas(profiles: dict, feat_cols: list, pop_stats: dict) -> list:
    """
    For each player with 2024-25 AND 2025-26, compute per-feature deltas.
    Returns list of player-level records.
    """
    records = []
    for player_id, pdata in profiles.items():
        seasons = pdata["seasons"]
        if "2024-25" not in seasons or "2025-26" not in seasons:
            continue

        s1 = seasons["2024-25"]
        s2 = seasons["2025-26"]
        n1 = s1["n_games"]
        n2 = s2["n_games"]

        if n1 < MIN_GAMES_Y1 or n2 < MIN_GAMES_Y2:
            continue  # not enough data

        deltas = {}
        z_scores = {}
        for f in feat_cols:
            # Skip features with known cross-season scale inconsistencies
            if f in SCALE_INCONSISTENT_FEATURES:
                deltas[f] = None
                z_scores[f] = None
                continue
            v1 = s1["mean"].get(f)
            v2 = s2["mean"].get(f)
            if v1 is None or v2 is None or math.isnan(v1) or math.isnan(v2):
                deltas[f] = None
                z_scores[f] = None
                continue
            delta = v2 - v1
            deltas[f] = round(float(delta), 4)
            std = pop_stats[f]["std"]
            z_scores[f] = round(float(delta / std), 3)

        records.append({
            "player_id": player_id,
            "player_name": pdata["name"],
            "season1": "2024-25",
            "season2": "2025-26",
            "n_games_y1": n1,
            "n_games_y2": n2,
            "s1_means": s1["mean"],
            "s2_means": s2["mean"],
            "deltas": deltas,
            "z_scores": z_scores,
        })

    return records


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 — Trend categorisation
# ──────────────────────────────────────────────────────────────────────────────

Z_BREAKOUT_THRESHOLD = 1.0
Z_DECLINE_THRESHOLD = -1.0
Z_ROLE_SHIFT_THRESHOLD = 1.0
Z_STABLE_THRESHOLD = 0.5


def classify_player(record: dict, feat_cols: list) -> dict:
    """
    Returns enriched record with:
        dev_tag: BREAKOUT | DECLINE | ROLE_SHIFT | STABLE
        dev_score: sum of |z| across top-5 most-shifted features
        top_shifts: list of (feature, delta, z, interpretation) for top-3 shifts
        breakout_features: list
        decline_features: list
        role_shift_features: list
    """
    z = record["z_scores"]
    deltas = record["deltas"]

    breakouts = []
    declines = []
    role_shifts = []

    for f in VOLUME_USAGE_FEATURES:
        zv = z.get(f)
        if zv is None:
            continue
        if zv > Z_BREAKOUT_THRESHOLD:
            breakouts.append((f, deltas[f], zv))
        elif zv < Z_DECLINE_THRESHOLD:
            declines.append((f, deltas[f], zv))

    for f in STYLE_FEATURES:
        zv = z.get(f)
        if zv is None:
            continue
        if abs(zv) > Z_ROLE_SHIFT_THRESHOLD:
            role_shifts.append((f, deltas[f], zv))

    # Dev tag priority: breakout > decline > role_shift > stable
    if breakouts:
        dev_tag = "BREAKOUT"
    elif declines:
        dev_tag = "DECLINE"
    elif role_shifts:
        dev_tag = "ROLE_SHIFT"
    else:
        dev_tag = "STABLE"

    # Development score = sum |z| of top-5 most-shifted features
    # Only use scale-consistent features for scoring
    all_zabs = [(f, deltas[f], z[f]) for f in feat_cols
                if z.get(f) is not None and not math.isnan(z[f])
                and f not in SCALE_INCONSISTENT_FEATURES]
    all_zabs.sort(key=lambda x: abs(x[2]), reverse=True)
    top5 = all_zabs[:5]
    dev_score = round(sum(abs(x[2]) for x in top5), 3)

    # Top-3 shifts with interpretation
    top3 = all_zabs[:3]
    top_shifts = []
    for f, d, zv in top3:
        interp = _interpret_shift(f, d, zv)
        top_shifts.append({"feature": f, "delta": d, "z": zv, "interpretation": interp})

    record = {**record}
    record["dev_tag"] = dev_tag
    record["dev_score"] = dev_score
    record["top_shifts"] = top_shifts
    record["breakout_features"] = [(f, d, zv) for f, d, zv in breakouts]
    record["decline_features"] = [(f, d, zv) for f, d, zv in declines]
    record["role_shift_features"] = [(f, d, zv) for f, d, zv in role_shifts]
    return record


def _interpret_shift(feature: str, delta: float, z: float) -> str:
    direction = "increased" if delta > 0 else "decreased"
    magnitude = "sharply" if abs(z) > 2.0 else ("notably" if abs(z) > 1.0 else "slightly")
    interp_map = {
        "touches_per_game": f"Ball touches {direction} {magnitude} — role expansion" if delta > 0 else f"Ball touches {direction} {magnitude} — reduced usage",
        "paint_dwell_pct": f"Paint dwell {direction} {magnitude} — {'more interior presence' if delta > 0 else 'more perimeter play'}",
        "potential_assists": f"Playmaking {direction} {magnitude} — {'more creation/passing role' if delta > 0 else 'less creation role'}",
        "catch_shoot_pct": f"Catch-and-shoot rate {direction} {magnitude} — {'more spot-up role' if delta > 0 else 'more off-dribble creation'}",
        "shot_zone_3pt_pct": f"Three-point shot rate {direction} {magnitude} — {'more perimeter scoring' if delta > 0 else 'fewer perimeter attempts'}",
        "shot_zone_paint_pct": f"Paint shot rate {direction} {magnitude} — {'more interior scoring' if delta > 0 else 'fewer paint finishes'}",
        "avg_shot_distance": f"Shot distance {direction} {magnitude} — {'extending range' if delta > 0 else 'attacking closer to basket'}",
        "play_type_isolation_pct": f"Isolation plays {direction} {magnitude} — {'more primary creator role' if delta > 0 else 'fewer isolation opportunities'}",
        "play_type_transition_pct": f"Transition frequency {direction} {magnitude} — {'more uptempo play' if delta > 0 else 'less transition involvement'}",
        "play_type_drive_pct": f"Drive frequency {direction} {magnitude} — {'more attacking off dribble' if delta > 0 else 'less aggressive driving'}",
        "contested_shot_rate": f"Shot contest rate {direction} {magnitude} — {'tougher shot selection' if delta > 0 else 'cleaner looks'}",
        "avg_dribble_count": f"Dribble count {direction} {magnitude} — {'more creation off dribble' if delta > 0 else 'more off-ball play'}",
        "avg_defender_distance": f"Avg defender distance {direction} {magnitude} — CAUTION: ISSUE-022 may corrupt this metric",
    }
    return interp_map.get(feature, f"{feature} {direction} {magnitude}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 — Rookies / new arrivals (only 2025-26 CV history)
# ──────────────────────────────────────────────────────────────────────────────

def find_rookies(profiles: dict, classified: list, name_map: dict, feat_cols: list) -> list:
    """
    Players who appear ONLY in 2025-26 CV data (no 2024-25 records).
    """
    classified_ids = {r["player_id"] for r in classified}
    rookies = []
    for player_id, pdata in profiles.items():
        seasons = pdata["seasons"]
        if "2025-26" in seasons and "2024-25" not in seasons:
            s = seasons["2025-26"]
            if s["n_games"] >= MIN_GAMES_Y2:
                rookies.append({
                    "player_id": player_id,
                    "player_name": pdata["name"],
                    "n_games": s["n_games"],
                    "season": "2025-26",
                    "cv_snapshot": {k: round(v, 4) for k, v in s["mean"].items()
                                   if v is not None and not math.isnan(v)},
                })
    return sorted(rookies, key=lambda x: x["n_games"], reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 — Generate per-player development notes (top N)
# ──────────────────────────────────────────────────────────────────────────────

STORYLINES = {
    "BREAKOUT": (
        "This player's CV profile shows a meaningful expansion of role and usage from "
        "{season1} to {season2}. The increase in {top_feat} ({top_delta:+.3f}, {top_z:+.1f}σ) "
        "suggests their team is featuring them more prominently, whether through increased "
        "ball-handling duties, more time in the paint, or expanded playmaking responsibility."
    ),
    "DECLINE": (
        "This player's CV profile indicates a contraction in volume and role from "
        "{season1} to {season2}. The shift in {top_feat} ({top_delta:+.3f}, {top_z:+.1f}σ) "
        "may reflect reduced minutes, a changed team context, or increased competition for "
        "usage from teammates. This warrants caution on over-projections."
    ),
    "ROLE_SHIFT": (
        "This player's overall volume has stayed relatively stable, but their play style "
        "changed materially from {season1} to {season2}. The shift in {top_feat} "
        "({top_delta:+.3f}, {top_z:+.1f}σ) suggests a role realignment — perhaps a move "
        "from a creation-heavy to a catch-and-shoot role, or a position shift within "
        "the offense."
    ),
    "STABLE": (
        "This player's CV profile is largely stable from {season1} to {season2}. "
        "The largest single-feature shift is {top_feat} ({top_delta:+.3f}, {top_z:+.1f}σ), "
        "which falls within normal variation. They represent a known, consistent quantity."
    ),
}


def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip().replace(" ", "_")


def generate_player_note(rec: dict, feat_cols: list) -> str:
    name = rec["player_name"]
    s1_label = rec["season1"]
    s2_label = rec["season2"]
    n1 = rec["n_games_y1"]
    n2 = rec["n_games_y2"]
    dev_tag = rec["dev_tag"]
    dev_score = rec["dev_score"]
    top_shifts = rec["top_shifts"]

    s1_means = rec["s1_means"]
    s2_means = rec["s2_means"]
    deltas = rec["deltas"]
    z_scores = rec["z_scores"]

    # Build season profile table — only scale-consistent features
    table_rows = []
    relevant_feats = [
        # Scale-consistent features (usable for cross-season comparison):
        "paint_dwell_pct", "potential_assists", "possession_duration_avg",
        "play_type_transition_pct", "avg_dribble_count",
        "shot_zone_mid_range_pct", "shot_zone_paint_pct",
        "avg_shot_distance", "avg_spacing", "cv_xast_pred",
        "preshot_velocity_peak", "avg_fatigue_proxy",
        "avg_defender_distance", "avg_contest_arm_angle",
        # Scale-inconsistent features shown for reference only (marked):
        "touches_per_game", "catch_shoot_pct", "shot_zone_3pt_pct",
        "n_shots_tracked", "shots_per_possession",
    ]
    for f in relevant_feats:
        v1 = s1_means.get(f)
        v2 = s2_means.get(f)
        d = deltas.get(f)
        z = z_scores.get(f)
        if v1 is None or v2 is None:
            continue
        if math.isnan(v1) or math.isnan(v2):
            continue
        if d is None or z is None:
            # show raw values for scale-inconsistent features, but skip z
            caution = " ⚠️ SCALE-INCONSISTENT (cross-season unreliable)"
            if f in ISSUE_022_FEATURES:
                caution += " + ISSUE-022"
            table_rows.append(
                f"| {f} | {v1:.4f} | {v2:.4f} | — | —{caution} |"
            )
        else:
            caution = " ⚠️ ISSUE-022" if f in ISSUE_022_FEATURES else ""
            table_rows.append(
                f"| {f} | {v1:.4f} | {v2:.4f} | {d:+.4f} | {z:+.2f}σ{caution} |"
            )

    table = "\n".join([
        "| feature | 2024-25 mean | 2025-26 mean | delta | z |",
        "|---|---|---|---|---|",
    ] + table_rows)

    # Breakout/decline/shift feature summaries
    bf = "; ".join(f"{f}({d:+.3f}, {z:+.1f}σ)" for f, d, z in rec["breakout_features"]) or "none"
    df_ = "; ".join(f"{f}({d:+.3f}, {z:+.1f}σ)" for f, d, z in rec["decline_features"]) or "none"
    rf = "; ".join(f"{f}({d:+.3f}, {z:+.1f}σ)" for f, d, z in rec["role_shift_features"]) or "none"
    dev_tag_line = f"**BREAKOUT** (↑ {bf})" if dev_tag == "BREAKOUT" \
        else f"**DECLINE** (↓ {df_})" if dev_tag == "DECLINE" \
        else f"**ROLE_SHIFT** ({rf})" if dev_tag == "ROLE_SHIFT" \
        else f"**STABLE** (max shift < 0.5σ)"

    # Storyline — use the most significant tag-relevant feature for narrative anchor
    if dev_tag == "BREAKOUT" and rec["breakout_features"]:
        anchor_feat, anchor_delta, anchor_z = rec["breakout_features"][0]
    elif dev_tag == "DECLINE" and rec["decline_features"]:
        anchor_feat, anchor_delta, anchor_z = rec["decline_features"][0]
    elif dev_tag == "ROLE_SHIFT" and rec["role_shift_features"]:
        anchor_feat, anchor_delta, anchor_z = rec["role_shift_features"][0]
    elif top_shifts:
        anchor_feat = top_shifts[0]["feature"]
        anchor_delta = top_shifts[0]["delta"]
        anchor_z = top_shifts[0]["z"]
    else:
        anchor_feat, anchor_delta, anchor_z = "—", 0.0, 0.0

    if anchor_feat != "—":
        storyline_template = STORYLINES[dev_tag]
        storyline = storyline_template.format(
            season1=s1_label,
            season2=s2_label,
            top_feat=anchor_feat,
            top_delta=anchor_delta,
            top_z=anchor_z,
        )
    else:
        storyline = "Insufficient features to generate narrative."

    # Comparable players placeholder (would require similarity engine)
    comparable = "*(Similarity engine cross-reference not yet wired — see INT-12)*"

    # Sample size caveat
    y1_reliability = "⚠️ single-game Y1 mean — very low reliability" if n1 <= 1 else ("⚠️ 2-game Y1 mean — low reliability" if n1 <= 2 else "moderate reliability")
    y2_reliability = "low" if n2 < 5 else "moderate"
    caveat_n = (
        f"- Sample sizes: **{n1} game(s) in {s1_label}** ({y1_reliability}), "
        f"**{n2} games in {s2_label}** ({y2_reliability} Y2 reliability). "
        f"With sparse Y1 data, the 'delta' reflects Y1-game → Y2-mean, not true season-over-season trend."
    )
    caveat_022 = "- ISSUE-022 (defender_distance corruption) makes `avg_defender_distance` and `defender_approach_speed` trends untrustworthy"
    caveat_trade = "- Player may have changed teams between seasons — a team change confounds role shifts"

    md = f"""# {name} — CV Development ({s1_label} → {s2_label})

## Season profiles
{table}

## Development tag: {dev_tag_line}

**Development score:** {dev_score:.2f} (sum |z| of top-5 shifted features)

### Top 3 shifted features
| # | feature | delta | z | interpretation |
|---|---|---|---|---|
"""
    for i, ts in enumerate(top_shifts[:3], 1):
        md += f"| {i} | {ts['feature']} | {ts['delta']:+.4f} | {ts['z']:+.2f}σ | {ts['interpretation']} |\n"

    md += f"""
## Storyline
{storyline}

## Comparable trajectories
{comparable}

## Caveats
{caveat_n}
{caveat_022}
{caveat_trade}
"""
    return md


# ──────────────────────────────────────────────────────────────────────────────
# Step 6 — Atlas
# ──────────────────────────────────────────────────────────────────────────────

def generate_atlas(classified: list, rookies: list, multi_season_count: int, reliable_count: int) -> str:
    breakouts = [r for r in classified if r["dev_tag"] == "BREAKOUT"]
    declines = [r for r in classified if r["dev_tag"] == "DECLINE"]
    role_shifts = [r for r in classified if r["dev_tag"] == "ROLE_SHIFT"]
    stable = [r for r in classified if r["dev_tag"] == "STABLE"]

    breakouts.sort(key=lambda x: x["dev_score"], reverse=True)
    declines.sort(key=lambda x: x["dev_score"], reverse=True)
    role_shifts.sort(key=lambda x: x["dev_score"], reverse=True)

    def table_rows(items, n=TOP_N_ATLAS):
        rows = []
        for r in items[:n]:
            ts = r["top_shifts"][0] if r["top_shifts"] else {"feature": "—", "delta": 0.0, "z": 0.0, "interpretation": "—"}
            dominant = f"{ts['feature']} ({ts['delta']:+.3f}, {ts['z']:+.1f}σ)"
            rows.append(
                f"| {r['player_name']} | {r['player_id']} | {r['dev_score']:.2f} | {r['n_games_y1']}g / {r['n_games_y2']}g | {dominant} |"
            )
        return "\n".join(rows)

    def rookie_rows(items, n=20):
        rows = []
        for r in items[:n]:
            snap = r["cv_snapshot"]
            key_vals = ", ".join(f"{k}={v:.3f}" for k, v in list(snap.items())[:3])
            rows.append(f"| {r['player_name']} | {r['player_id']} | {r['n_games']} | {key_vals} |")
        return "\n".join(rows)

    header = "| player | player_id | dev_score | games (Y1/Y2) | dominant_shift |"
    divider = "|---|---|---|---|---|"

    atlas = f"""# CV Player Development Atlas

*Generated: INT-15 | Seasons: 2024-25 → 2025-26*

## Methodology
Season-over-season CV profile comparison for NBA players tracked across multiple seasons.
For each player with games in BOTH seasons (≥{MIN_GAMES_Y1} game(s) in Y1, ≥{MIN_GAMES_Y2} in Y2),
we compute mean CV features per season, delta per feature, and z-score each delta against the
across-player standard deviation of that feature. Players are tagged BREAKOUT/DECLINE/ROLE_SHIFT/STABLE
based on which features show z > 1σ movement.

**NOTE: 2024-25 (Y1) CV data is very sparse — only 14 games are in the cv_features DB.
Most players have 1 Y1 game. Cross-season deltas should be treated as preliminary signals,
not robust measurements. Y2 requires ≥{MIN_GAMES_Y2} games for stability.**

## Coverage
- Players with CV data in multiple seasons: **{multi_season_count}**
- Players passing cross-season filter (≥{MIN_GAMES_Y1} game Y1, ≥{MIN_GAMES_Y2} games Y2): **{reliable_count}**
- BREAKOUT: **{len(breakouts)}** | DECLINE: **{len(declines)}** | ROLE_SHIFT: **{len(role_shifts)}** | STABLE: **{len(stable)}**
- Players with ONLY 2025-26 CV (rookies/new arrivals ≥{MIN_GAMES_Y2} games): **{len(rookies)}**

---

## Top {TOP_N_ATLAS} BREAKOUTS
*(positive movement on volume/usage features > +1σ)*

{header}
{divider}
{table_rows(breakouts)}

---

## Top {TOP_N_ATLAS} DECLINES
*(negative movement on volume/usage features < -1σ)*

{header}
{divider}
{table_rows(declines)}

---

## Top {TOP_N_ATLAS} ROLE SHIFTS
*(play-style features shifted > 1σ without matching volume change)*

{header}
{divider}
{table_rows(role_shifts)}

---

## Rookies / New Arrivals (2025-26 baseline only)
*Players with no 2024-25 CV history — their profile here is their introductory baseline.*

| player | player_id | n_games | cv_snapshot (top-3 features) |
|---|---|---|---|
{rookie_rows(rookies)}

---

## Honest Caveats
- **Sample sizes vary**: most players have only 1 Y1 game and {MIN_GAMES_Y2}-7 Y2 games. Y1 single-game means are not robust season estimates — interpret all cross-season deltas as preliminary signals.
- **Team trades confound shifts**: a player who changed teams between seasons may show a "role shift" that is entirely explained by the new system, not personal development.
- **ISSUE-022**: `avg_defender_distance` and `defender_approach_speed` are corrupted by a sentinel value bug (200.0 → should be NULL). Year-over-year changes in those features are unreliable.
- **2024-25 CV coverage is small** (14 games vs 252 in 2025-26). Cross-season comparison is anchored on a narrow 2024-25 sample — the "Y1 mean" may not represent a full season.
- **The dev_tag is heuristic**: it flags notable z-score shifts, not ground truth development.
- **Jersey-based tracking IDs** in some legacy game files (`player_cv_per_game.parquet`) are excluded — only records with resolved NBA player IDs from the `cv_features` DB are used.
"""
    return atlas


# ──────────────────────────────────────────────────────────────────────────────
# Step 7 — Parquet + JSON outputs
# ──────────────────────────────────────────────────────────────────────────────

def build_parquet(classified: list, feat_cols: list) -> pd.DataFrame:
    rows = []
    for r in classified:
        row = {
            "player_id": r["player_id"],
            "player_name": r["player_name"],
            "season1": r["season1"],
            "season2": r["season2"],
            "n_games_y1": r["n_games_y1"],
            "n_games_y2": r["n_games_y2"],
            "dev_tag": r["dev_tag"],
            "dev_score": r["dev_score"],
        }
        for f in feat_cols:
            row[f"delta_{f}"] = r["deltas"].get(f)
            row[f"z_{f}"] = r["z_scores"].get(f)
        rows.append(row)
    return pd.DataFrame(rows)


def build_signals_json(classified: list) -> dict:
    def fmt(r, tag_feats_key):
        shifts = [(f, d, z) for f, d, z in r.get(tag_feats_key, [])]
        top_shift = shifts[0] if shifts else (None, None, None)
        return {
            "player_id": r["player_id"],
            "name": r["player_name"],
            "score": r["dev_score"],
            "n_games_y1": r["n_games_y1"],
            "n_games_y2": r["n_games_y2"],
            "top_shift": {
                "feature": top_shift[0],
                "delta": top_shift[1],
                "z": top_shift[2],
            } if top_shift[0] else (r["top_shifts"][0] if r["top_shifts"] else {}),
        }

    breakouts = sorted([r for r in classified if r["dev_tag"] == "BREAKOUT"],
                       key=lambda x: x["dev_score"], reverse=True)
    declines = sorted([r for r in classified if r["dev_tag"] == "DECLINE"],
                      key=lambda x: x["dev_score"], reverse=True)
    role_shifts = sorted([r for r in classified if r["dev_tag"] == "ROLE_SHIFT"],
                         key=lambda x: x["dev_score"], reverse=True)

    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "breakouts": [fmt(r, "breakout_features") for r in breakouts],
        "declines": [fmt(r, "decline_features") for r in declines],
        "role_shifts": [fmt(r, "role_shift_features") for r in role_shifts],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=== INT-15 Player Development Intelligence ===")

    # Load
    print("Loading CV features from DB...")
    df_raw = load_cv_features()
    print(f"  {len(df_raw)} feature rows, {df_raw['game_id'].nunique()} games, "
          f"{df_raw['player_id'].nunique()} unique player_ids")

    name_map = load_player_name_map()
    # Supplement with boxscore player names for IDs not in player_full JSON
    boxscore_names = load_boxscore_names()
    for pid, pname in boxscore_names.items():
        if pid not in name_map:
            name_map[pid] = pname
    print(f"  Player name map loaded: {len(name_map)} entries (incl. {len(boxscore_names)} from boxscores)")

    game_dates = load_game_dates()
    print(f"  Game date map loaded: {len(game_dates)} entries")

    # Step 1 — Build season profiles
    print("Building per-player season profiles...")
    profiles, feat_cols = build_season_profiles(df_raw, name_map, game_dates)
    multi_season_count = sum(1 for p in profiles.values() if len(p["seasons"]) >= 2)
    print(f"  Players with multi-season CV data: {multi_season_count}")

    # Step 2 — Compute population stats + deltas
    print("Computing population statistics for z-scoring...")
    pop_stats = compute_population_stats(profiles, feat_cols)

    print("Computing cross-season deltas...")
    delta_records = compute_cross_season_deltas(profiles, feat_cols, pop_stats)
    reliable_count = len(delta_records)
    print(f"  Players with reliable cross-season comparison (>={MIN_GAMES_Y1} Y1, >={MIN_GAMES_Y2} Y2): {reliable_count}")

    # Step 3 — Classify
    print("Classifying player development trends...")
    classified = [classify_player(r, feat_cols) for r in delta_records]
    tag_counts = pd.Series([r["dev_tag"] for r in classified]).value_counts()
    print(f"  Tags: {dict(tag_counts)}")

    # Step 4 — Rookies
    print("Identifying 2025-26-only players (rookies/new arrivals)...")
    rookies = find_rookies(profiles, classified, name_map, feat_cols)
    print(f"  Rookies / new arrivals with >= {MIN_GAMES_Y2} games (2025-26 only): {len(rookies)}")

    # Step 5 — Per-player development notes for top N
    print(f"Writing per-player development notes (top {TOP_N_NOTES})...")
    all_developed = sorted(classified, key=lambda x: x["dev_score"], reverse=True)
    for i, rec in enumerate(all_developed[:TOP_N_NOTES]):
        note_md = generate_player_note(rec, feat_cols)
        fname = safe_filename(rec["player_name"]) + ".md"
        note_path = DEV_DIR / fname
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(note_md)
        print(f"  [{i+1}/{TOP_N_NOTES}] {rec['player_name']} ({rec['dev_tag']}, score={rec['dev_score']:.2f}) -> {fname}")

    # Step 6 — Atlas
    print("Generating Development Atlas...")
    atlas_md = generate_atlas(classified, rookies, multi_season_count, reliable_count)
    with open(ATLAS_MD, "w", encoding="utf-8") as f:
        f.write(atlas_md)
    print(f"  Wrote {ATLAS_MD}")

    # Step 7 — Parquet + JSON
    print("Writing parquet and signals JSON...")
    df_out = build_parquet(classified, feat_cols)
    df_out.to_parquet(OUT_PARQUET, index=False)
    print(f"  Wrote {OUT_PARQUET} — {len(df_out)} rows")

    signals = build_signals_json(classified)
    with open(OUT_SIGNALS, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)
    print(f"  Wrote {OUT_SIGNALS}")

    # Step 8 — Report
    print()
    print("=" * 60)
    print("## INT-15 Player Development Intelligence — Final Report")
    print("=" * 60)
    print()
    print("### Coverage")
    print(f"- Players with CV in 2+ seasons: {multi_season_count}")
    print(f"- Players with reliable cross-season comparison (>={MIN_GAMES_Y1} Y1, >={MIN_GAMES_Y2} Y2): {reliable_count}")
    print(f"- Rookies / new (only 2025-26): {len(rookies)}")
    print()

    for tag_name, key in [("Top 5 breakouts", "BREAKOUT"), ("Top 5 declines", "DECLINE"), ("Top 5 role shifts", "ROLE_SHIFT")]:
        subset = sorted([r for r in classified if r["dev_tag"] == key],
                        key=lambda x: x["dev_score"], reverse=True)
        print(f"### {tag_name} (by dev_score)")
        print(f"{'player':<30} {'top_shift_feature':<28} {'delta':>8} {'z':>6}  likely interpretation")
        print("-" * 100)
        for r in subset[:5]:
            if r["top_shifts"]:
                ts = r["top_shifts"][0]
                interp = ts["interpretation"][:55]
                print(f"  {r['player_name']:<28} {ts['feature']:<28} {ts['delta']:>+8.3f} {ts['z']:>+5.1f}σ  {interp}")
            else:
                print(f"  {r['player_name']:<28} — no shifts")
        print()

    print("### Files")
    print(f"  scripts/build_player_development.py")
    print(f"  vault/Intelligence/Development_Atlas.md")
    print(f"  vault/Intelligence/Development/ ({min(len(all_developed), TOP_N_NOTES)} player notes)")
    print(f"  data/intelligence/player_development.parquet ({len(df_out)} rows)")
    print(f"  data/intelligence/breakout_signals.json")
    print()
    print("### How to use this intelligence")
    print("  - Breakout candidates: players with large positive volume z-scores may be mispriced")
    print("    on season-long prop lines that haven't adjusted to new roles")
    print("  - Decline detection: fade OVER bets on declining players (reduced touches/usage)")
    print("  - Role shifts: rethink which stats to bet — a role-shifted player's stat profile is")
    print("    structurally different; last-season comps are less valid")
    print("  - Rookies: surface CV baseline for first time, useful for cold-start prop pricing")
    print()
    print("### Honest caveats")
    print("  - 2024-25 CV coverage is only 14 games — the Y1 season mean is anchored on a narrow sample")
    print("  - ISSUE-022: avg_defender_distance/defender_approach_speed deltas are unreliable")
    print("  - Trades between seasons confound role-shift detection")
    print(f"  - Minimum: {MIN_GAMES_Y1} game(s) in 2024-25 Y1, {MIN_GAMES_Y2} games in 2025-26 Y2")
    print(f"  - Most players have only 1 Y1 game — deltas are directional signals, not stable estimates")
    print("  - z-score thresholds (1σ) are heuristic — low dev_score STABLE players may still have real")
    print("    trends hidden by small within-season variance")


if __name__ == "__main__":
    main()
