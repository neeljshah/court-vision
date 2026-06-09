"""
build_player_cards.py — INT-2 Player Intelligence Cards
Generates per-player CV behavioral profile cards for the analytics dashboard.

Usage:
    python scripts/build_player_cards.py

Output:
    vault/Intelligence/Players/<player_id>_<name>.md  — one file per player
    vault/Intelligence/_Player_Index.md               — searchable index

Data sources:
    - data/nba_ai.db :: cv_features table
    - data/intelligence/player_fingerprints.parquet   — archetype + comparables
    - data/nba/player_full_2024-25.json               — name + team lookup
"""

from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "nba_ai.db"
FINGERPRINTS_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
ARCHETYPE_DEFS_PATH = ROOT / "data" / "intelligence" / "player_archetype_definitions.json"
ROSTER_PATH_2425 = ROOT / "data" / "nba" / "player_full_2024-25.json"
ROSTER_PATH_2526 = ROOT / "data" / "nba" / "player_full_2025-26.json"
OUT_DIR = ROOT / "vault" / "Intelligence" / "Players"
INDEX_PATH = ROOT / "vault" / "Intelligence" / "_Player_Index.md"

TODAY = date.today().isoformat()

# ── CV feature metadata ────────────────────────────────────────────────────
# Tuples: (column, display_label, unit_note)
FEATURE_META: dict[str, dict[str, str]] = {
    "paint_dwell_pct":         {"label": "Paint dwell",              "fmt": "pct"},
    "shot_zone_paint_pct":     {"label": "Shot zone — paint",        "fmt": "pct"},
    "shot_zone_mid_range_pct": {"label": "Shot zone — mid-range",    "fmt": "pct"},
    "shot_zone_3pt_pct":       {"label": "Shot zone — 3PT",          "fmt": "pct"},
    "avg_shot_distance":       {"label": "Avg shot distance",        "fmt": "ft"},
    "touches_per_game":        {"label": "Touches per game",         "fmt": "num"},
    "shots_per_possession":    {"label": "Shots per possession",     "fmt": "dec2"},
    "possession_duration_avg": {"label": "Avg possession duration",  "fmt": "sec"},
    "second_chance_rate":      {"label": "Second chance rate",       "fmt": "pct"},
    "potential_assists":       {"label": "Potential assists",        "fmt": "dec1"},
    "preshot_velocity_peak":   {"label": "Pre-shot velocity peak",   "fmt": "vel"},
    "defender_approach_speed": {"label": "Defender approach speed",  "fmt": "vel"},
    "play_type_transition_pct":{"label": "Transition play %",        "fmt": "pct"},
    "play_type_isolation_pct": {"label": "Isolation play %",         "fmt": "pct"},
    "play_type_post_pct":      {"label": "Post-up play %",           "fmt": "pct"},
    "catch_shoot_pct":         {"label": "Catch-and-shoot %",        "fmt": "pct"},
    "avg_dribble_count":       {"label": "Avg dribbles before shot", "fmt": "dec1"},
    "contested_shot_rate":     {"label": "Contested shot rate",      "fmt": "pct"},
    "avg_defender_distance":   {"label": "Avg defender distance",    "fmt": "ft"},
    "avg_spacing":             {"label": "Avg court spacing",        "fmt": "ft"},
    "avg_fatigue_proxy":       {"label": "Fatigue proxy (CV)",       "fmt": "dec2"},
    "n_shots_tracked":         {"label": "Shots tracked",            "fmt": "num"},
    "made_pct":                {"label": "CV made %",                "fmt": "pct"},
    "avg_shot_clock_at_shot":  {"label": "Shot clock at shot",       "fmt": "sec"},
    "avg_contest_arm_angle":   {"label": "Avg contest arm angle",    "fmt": "dec2"},
    "cv_xast_pred":            {"label": "xAST (CV model)",         "fmt": "dec1"},
}


def fmt_val(val: float, fmt: str) -> str:
    """Format a numeric value according to its feature type."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if fmt == "pct":
        return f"{val * 100:.1f}%"
    if fmt == "ft":
        return f"{val:.1f} ft"
    if fmt == "sec":
        return f"{val:.1f}s"
    if fmt == "vel":
        return f"{val:.2f} ft/frame"
    if fmt == "dec1":
        return f"{val:.1f}"
    if fmt == "dec2":
        return f"{val:.2f}"
    if fmt == "num":
        return f"{val:.0f}"
    return f"{val:.2f}"


def percentile_label(pct: float) -> str:
    """Convert percentile (0-100) to descriptive text."""
    if pct >= 90:
        return "very high (top 10%)"
    if pct >= 75:
        return "high (top 25%)"
    if pct >= 50:
        return "above avg"
    if pct >= 25:
        return "below avg"
    if pct >= 10:
        return "low (bottom 25%)"
    return "very low (bottom 10%)"


def trend_arrow(change_pct: float) -> str:
    """Return arrow symbol for trend direction."""
    if change_pct > 0:
        return "↑"
    if change_pct < 0:
        return "↓"
    return "→"


# ── Data loading ───────────────────────────────────────────────────────────

def load_player_lookup() -> dict[int, dict[str, str]]:
    """Build player_id -> {name, team} from roster JSON(s)."""
    lookup: dict[int, dict[str, str]] = {}

    for path in [ROSTER_PATH_2425, ROSTER_PATH_2526]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for raw_name, info in data.items():
            pid = info.get("player_id")
            team = info.get("team", "UNK")
            if not pid:
                continue
            pid = int(pid)
            # Proper-case name
            proper = " ".join(
                w if w.upper() in ("II", "III", "IV", "JR", "SR") else w.capitalize()
                for w in raw_name.split()
            )
            if pid not in lookup:
                lookup[pid] = {"name": proper, "team": team}
    return lookup


def load_cv_data() -> pd.DataFrame:
    """
    Load cv_features from DB and pivot to wide format.
    Returns DataFrame indexed by (player_id, game_id) with one column per feature.
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()

    # Bug 27 guard: potential_assists=0 means xAST submodule did not run for that
    # game (45.1% of CV games are all-zero).  Null zeros before pivot so all
    # downstream means/percentiles/outlier-flags exclude PA-inactive games.
    pa_mask = (df["feature_name"] == "potential_assists") & (df["feature_value"] == 0.0)
    df.loc[pa_mask, "feature_value"] = float("nan")  # Bug 27 guard

    # Pivot: rows = (player_id, game_id), cols = features
    wide = df.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    )
    wide.columns.name = None
    wide = wide.reset_index()
    return wide


def load_fingerprints() -> pd.DataFrame:
    """Load the INT-1 fingerprints parquet."""
    if not FINGERPRINTS_PATH.exists():
        return pd.DataFrame()
    fp = pd.read_parquet(FINGERPRINTS_PATH)
    fp.index = fp.index.astype(int)
    return fp


def load_archetype_defs() -> dict[int, dict]:
    """Load archetype definitions JSON."""
    if not ARCHETYPE_DEFS_PATH.exists():
        return {}
    with open(ARCHETYPE_DEFS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


# ── Per-player computation ─────────────────────────────────────────────────

REAL_GAME_THRESHOLD = 5.0  # sum of all features must exceed this to count as "real"
CV_FINGERPRINT_FEATURES = [
    "paint_dwell_pct", "shot_zone_paint_pct", "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct", "avg_shot_distance", "touches_per_game",
    "shots_per_possession", "possession_duration_avg", "second_chance_rate",
    "potential_assists", "preshot_velocity_peak", "defender_approach_speed",
    "play_type_transition_pct", "play_type_isolation_pct", "play_type_post_pct",
    "catch_shoot_pct", "avg_dribble_count", "contested_shot_rate",
    "avg_defender_distance",
]


_META_FEATURES = {"cv_archetype", "cv_xast_pred"}


def game_is_real(row: pd.Series, features: list[str]) -> bool:
    """Return True if a game row has meaningful tracked data."""
    total = sum(row.get(f, 0) or 0 for f in features if f not in _META_FEATURES)
    return total > REAL_GAME_THRESHOLD


def season_from_game_id(game_id: str) -> str:
    """Derive NBA season string from game_id prefix."""
    if str(game_id).startswith("00224"):
        return "2024-25"
    if str(game_id).startswith("00225"):
        return "2025-26"
    return "unknown"


def compute_player_stats(
    player_rows: pd.DataFrame,
    all_player_means: pd.DataFrame,
    fingerprints: pd.DataFrame,
) -> dict[str, Any]:
    """Compute all stats needed for one player's intelligence card."""
    features = [c for c in player_rows.columns if c not in ("player_id", "game_id")]

    # Filter to real games only
    real_mask = player_rows.apply(lambda r: game_is_real(r, features), axis=1)
    real_rows = player_rows[real_mask].copy()
    n_real = len(real_rows)

    # All game IDs (including sparse)
    all_game_ids = sorted(player_rows["game_id"].tolist())
    real_game_ids = sorted(real_rows["game_id"].tolist())

    seasons = sorted(set(season_from_game_id(g) for g in real_game_ids))

    # Aggregate means over real games
    # Note: potential_assists zeros already nulled at load time (Bug 27 guard in load_cv_data)
    num_cols = [c for c in features if c not in ("game_id",)]
    means = real_rows[num_cols].mean() if n_real > 0 else pd.Series(dtype=float)

    # Per-game records (best/worst for key features)
    records: dict[str, dict] = {}
    key_record_features = [
        "paint_dwell_pct", "contested_shot_rate", "touches_per_game",
        "avg_shot_distance", "potential_assists", "preshot_velocity_peak",
    ]
    for feat in key_record_features:
        if feat not in real_rows.columns or n_real == 0:
            continue
        col = real_rows[feat].fillna(0)
        if col.max() == 0:
            continue
        best_idx = col.idxmax()
        worst_idx = col.idxmin()
        records[feat] = {
            "best_game": real_rows.loc[best_idx, "game_id"],
            "best_val": col.max(),
            "worst_game": real_rows.loc[worst_idx, "game_id"],
            "worst_val": col.min(),
        }

    # Trend: last 3 vs prior games (only meaningful if n_real > 3)
    trends: dict[str, dict] = {}
    if n_real > 3:
        recent = real_rows.tail(3)
        prior = real_rows.head(n_real - 3)
        for feat in CV_FINGERPRINT_FEATURES:
            if feat not in real_rows.columns:
                continue
            r_mean = recent[feat].mean()
            p_mean = prior[feat].mean()
            if p_mean == 0 or np.isnan(p_mean) or np.isnan(r_mean):
                continue
            change_pct = (r_mean - p_mean) / abs(p_mean) * 100
            if abs(change_pct) >= 15:
                trends[feat] = {
                    "recent_mean": r_mean,
                    "prior_mean": p_mean,
                    "change_pct": change_pct,
                }

    # Outlier flags: compare player mean to global distribution
    outlier_flags: list[str] = []
    if not all_player_means.empty and n_real >= 3:
        for feat in CV_FINGERPRINT_FEATURES:
            if feat not in means or feat not in all_player_means.columns:
                continue
            player_val = means.get(feat, 0)
            if np.isnan(player_val):
                continue
            col_data = all_player_means[feat].dropna()
            if len(col_data) < 5 or col_data.std() == 0:
                continue
            z = (player_val - col_data.mean()) / col_data.std()
            if abs(z) >= 2.0:
                direction = "above" if z > 0 else "below"
                outlier_flags.append(
                    f"`{feat}` — {fmt_val(player_val, FEATURE_META.get(feat, {}).get('fmt','dec2'))} "
                    f"({z:+.1f}σ {direction} global avg)"
                )

    # Comparable players from fingerprints (euclidean distance in z-scored CV space)
    comparables: list[dict] = []
    player_id = player_rows["player_id"].iloc[0]
    if not fingerprints.empty and player_id in fingerprints.index:
        fp_features = [f for f in CV_FINGERPRINT_FEATURES if f in fingerprints.columns]
        fp_data = fingerprints[fp_features].copy()
        # z-score
        fp_z = (fp_data - fp_data.mean()) / fp_data.std().replace(0, 1)
        if player_id in fp_z.index:
            player_vec = fp_z.loc[player_id].fillna(0)
            dists = fp_z.drop(index=player_id).fillna(0).apply(
                lambda row: np.sqrt(((row - player_vec) ** 2).sum()), axis=1
            )
            top5 = dists.nsmallest(5)
            for cmp_pid, dist in top5.items():
                cmp_name = (
                    fingerprints.loc[cmp_pid, "player_name"]
                    if cmp_pid in fingerprints.index and "player_name" in fingerprints.columns
                    else str(cmp_pid)
                )
                comparables.append({"name": cmp_name, "dist": dist, "player_id": cmp_pid})

    # Global percentiles for key features
    percentiles: dict[str, float] = {}
    if not all_player_means.empty and n_real >= 3:
        for feat in CV_FINGERPRINT_FEATURES:
            if feat not in means or feat not in all_player_means.columns:
                continue
            player_val = means.get(feat, 0)
            if np.isnan(player_val):
                continue
            col_data = all_player_means[feat].dropna()
            pct = float((col_data < player_val).mean() * 100)
            percentiles[feat] = pct

    return {
        "n_real": n_real,
        "n_total": len(all_game_ids),
        "real_game_ids": real_game_ids,
        "seasons": seasons,
        "means": means,
        "records": records,
        "trends": trends,
        "outlier_flags": outlier_flags,
        "comparables": comparables,
        "percentiles": percentiles,
        "small_sample": n_real <= 4,
    }


# ── Markdown rendering ─────────────────────────────────────────────────────

def render_card(
    player_id: int,
    player_info: dict[str, str],
    stats: dict[str, Any],
    fingerprints: pd.DataFrame,
    arch_defs: dict[int, dict],
) -> str:
    """Render a complete intelligence card as a markdown string."""
    name = player_info["name"]
    team = player_info["team"]
    n_games = stats["n_real"]
    seasons = stats["seasons"]
    means = stats["means"]
    records = stats["records"]
    trends = stats["trends"]
    outlier_flags = stats["outlier_flags"]
    comparables = stats["comparables"]
    percentiles = stats["percentiles"]
    small_sample = stats["small_sample"]

    seasons_str = ", ".join(seasons) if seasons else "unknown"
    n_seasons = len(seasons)

    # Archetype info from fingerprints
    archetype_name = "Unknown"
    archetype_id = None
    dist_from_centroid = None
    if not fingerprints.empty and player_id in fingerprints.index:
        row = fingerprints.loc[player_id]
        archetype_id = int(row.get("archetype_id", -1)) if not pd.isna(row.get("archetype_id")) else None
        archetype_name = str(row.get("archetype_name", "Unknown"))
        dist_from_centroid = float(row.get("dist_from_centroid", 0))

    def m(feat: str) -> float | None:
        """Get mean value for a feature."""
        val = means.get(feat)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return val

    def fv(feat: str) -> str:
        """Formatted mean value for a feature."""
        val = m(feat)
        if val is None:
            return "N/A"
        fmt = FEATURE_META.get(feat, {}).get("fmt", "dec2")
        return fmt_val(val, fmt)

    def pct_label(feat: str) -> str:
        """Percentile label for a feature."""
        p = percentiles.get(feat)
        if p is None:
            return ""
        return f" ({percentile_label(p)})"

    # ── YAML front matter
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    lines: list[str] = [
        "---",
        f"player_id: {player_id}",
        f"name: {name}",
        f"team: {team}",
        f"archetype: {archetype_name}",
        f"n_cv_games: {n_games}",
        f"n_seasons_tracked: {n_seasons}",
        f"last_updated: {TODAY}",
        "---",
        "",
    ]

    # ── Header
    sample_note = " ⚠️ Small sample — interpret with caution" if small_sample else ""
    lines += [
        f"# {name} ({team}) — CV Intelligence Card",
        "",
        f"## Behavioral Fingerprint ({n_games} CV games tracked across {seasons_str}){sample_note}",
        "",
        f"**Archetype:** {archetype_name}" +
        (f" (dist from centroid: {dist_from_centroid:.2f}σ)" if dist_from_centroid is not None else ""),
        "",
    ]

    # ── Position / shot zone profile
    paint_z = m("shot_zone_paint_pct")
    mid_z = m("shot_zone_mid_range_pct")
    arc_z = m("shot_zone_3pt_pct")
    shot_dist = m("avg_shot_distance")
    paint_dwell = m("paint_dwell_pct")

    lines += [
        "### Position Profile",
    ]
    if paint_z is not None:
        lines.append(f"- **Shot zones:** {fmt_val(paint_z,'pct')} paint, {fmt_val(mid_z,'pct') if mid_z is not None else 'N/A'} mid-range, {fmt_val(arc_z,'pct') if arc_z is not None else 'N/A'} from arc")
    if paint_dwell is not None:
        lines.append(f"- **Paint dwell:** {fmt_val(paint_dwell,'pct')} of tracked frames{pct_label('paint_dwell_pct')}")
    if shot_dist is not None:
        lines.append(f"- **Avg shot distance:** {fmt_val(shot_dist,'ft')}{pct_label('avg_shot_distance')}")
    lines.append("")

    # ── Possession profile
    touches = m("touches_per_game")
    poss_dur = m("possession_duration_avg")
    spp = m("shots_per_possession")

    lines += ["### Possession Profile"]
    if touches is not None:
        lines.append(f"- **Touches per game:** {fmt_val(touches,'num')}{pct_label('touches_per_game')}")
    if poss_dur is not None:
        lines.append(f"- **Avg possession duration:** {fmt_val(poss_dur,'sec')}{pct_label('possession_duration_avg')}")
    if spp is not None:
        lines.append(f"- **Shots per possession:** {fmt_val(spp,'dec2')}{pct_label('shots_per_possession')}")
    lines.append("")

    # ── Passing profile
    pot_ast = m("potential_assists")
    xast = m("cv_xast_pred")

    lines += ["### Passing Profile"]
    if pot_ast is not None:
        lines.append(f"- **Potential assists per game:** {fmt_val(pot_ast,'dec1')}{pct_label('potential_assists')}")
    if xast is not None:
        lines.append(f"- **xAST (CV model):** {fmt_val(xast,'dec1')}")
    lines.append("")

    # ── Movement / shot creation profile
    pv = m("preshot_velocity_peak")
    def_spd = m("defender_approach_speed")
    cs = m("catch_shoot_pct")
    dribbles = m("avg_dribble_count")
    iso = m("play_type_isolation_pct")
    trans = m("play_type_transition_pct")
    post = m("play_type_post_pct")

    lines += ["### Movement Profile"]
    if pv is not None:
        lines.append(f"- **Pre-shot velocity peak:** {fmt_val(pv,'vel')}{pct_label('preshot_velocity_peak')}")
    if def_spd is not None:
        lines.append(f"- **Defender approach speed at shot:** {fmt_val(def_spd,'vel')}")
    if cs is not None:
        lines.append(f"- **Catch-and-shoot rate:** {fmt_val(cs,'pct')}{pct_label('catch_shoot_pct')}")
    if dribbles is not None:
        lines.append(f"- **Avg dribbles before shot:** {fmt_val(dribbles,'dec1')}")

    play_types = []
    if trans is not None and trans > 0.01:
        play_types.append(f"transition {fmt_val(trans,'pct')}")
    if iso is not None and iso > 0.01:
        play_types.append(f"isolation {fmt_val(iso,'pct')}")
    if post is not None and post > 0.01:
        play_types.append(f"post-up {fmt_val(post,'pct')}")
    if play_types:
        lines.append(f"- **Play type mix:** {', '.join(play_types)}")
    lines.append("")

    # ── Defense faced
    def_dist = m("avg_defender_distance")
    csr = m("contested_shot_rate")
    spacing = m("avg_spacing")

    lines += ["### Defense Faced"]
    if def_dist is not None:
        sentinel_note = " *(may include sentinel values — interpret carefully)*" if def_dist > 50 else ""
        lines.append(f"- **Avg defender distance at shot:** {fmt_val(def_dist,'ft')}{sentinel_note}{pct_label('avg_defender_distance')}")
    if csr is not None:
        lines.append(f"- **Contested shot rate:** {fmt_val(csr,'pct')}{pct_label('contested_shot_rate')}")
    if spacing is not None:
        lines.append(f"- **Avg court spacing:** {fmt_val(spacing,'ft')}")
    lines.append("")

    # ── Additional CV metrics
    scr = m("second_chance_rate")
    fatigue = m("avg_fatigue_proxy")
    n_shots = m("n_shots_tracked")
    made_pct = m("made_pct")
    shot_clk = m("avg_shot_clock_at_shot")

    has_extra = any(v is not None for v in [scr, fatigue, n_shots, made_pct, shot_clk])
    if has_extra:
        lines += ["### Additional CV Metrics"]
        if n_shots is not None and n_shots > 0:
            lines.append(f"- **Shots tracked per game (avg):** {fmt_val(n_shots,'dec1')}")
        if made_pct is not None and n_shots is not None and n_shots > 0:
            lines.append(f"- **CV field goal % (tracked shots):** {fmt_val(made_pct,'pct')}")
        if scr is not None:
            lines.append(f"- **Second chance rate:** {fmt_val(scr,'pct')}{pct_label('second_chance_rate')}")
        if fatigue is not None and fatigue > 0:
            lines.append(f"- **Fatigue proxy (CV):** {fmt_val(fatigue,'dec2')}")
        if shot_clk is not None and shot_clk > 0:
            lines.append(f"- **Avg shot clock at shot:** {fmt_val(shot_clk,'sec')}")
        lines.append("")

    # ── Pattern flags section
    lines += ["## Pattern Flags", ""]

    # Outlier flags
    if outlier_flags:
        lines.append("### Outliers vs Global Population")
        for flag in outlier_flags:
            lines.append(f"- {flag}")
        lines.append("")

    # Trend flags
    if trends:
        lines.append("### Recent Trend (last 3 games vs prior games)")
        for feat, t in trends.items():
            meta = FEATURE_META.get(feat, {})
            fmt = meta.get("fmt", "dec2")
            label = meta.get("label", feat)
            arrow = trend_arrow(t["change_pct"])
            lines.append(
                f"- **{label}:** {fmt_val(t['prior_mean'], fmt)} → {fmt_val(t['recent_mean'], fmt)} "
                f"({arrow}{abs(t['change_pct']):.0f}%)"
            )
        lines.append("")
    elif n_games > 3:
        lines.append("*No features changed >15% in recent 3 games vs prior games.*")
        lines.append("")
    elif small_sample:
        lines.append("*Small sample — trend analysis requires >3 real games.*")
        lines.append("")

    # ── Comparable players
    lines += ["## Comparable Players (by CV Profile)", ""]
    if comparables:
        lines.append("Most similar by Euclidean distance in z-scored CV feature space:")
        lines.append("")
        for i, cmp in enumerate(comparables, 1):
            lines.append(f"{i}. **{cmp['name']}** — distance {cmp['dist']:.2f}")
        lines.append("")
    else:
        lines.append("*Fingerprints unavailable — comparables cannot be computed.*")
        lines.append("")

    # ── Notable per-game records
    lines += ["## Notable Per-Game Records", ""]
    if records:
        lines.append("| Feature | Best game | Best value | Worst game | Worst value |")
        lines.append("|---------|-----------|------------|------------|-------------|")
        for feat, rec in records.items():
            meta = FEATURE_META.get(feat, {})
            fmt = meta.get("fmt", "dec2")
            label = meta.get("label", feat)
            lines.append(
                f"| {label} | `{rec['best_game']}` | {fmt_val(rec['best_val'], fmt)} "
                f"| `{rec['worst_game']}` | {fmt_val(rec['worst_val'], fmt)} |"
            )
        lines.append("")
    else:
        lines.append("*No game-level records (insufficient tracked data).*")
        lines.append("")

    # ── Per-game breakdown table (collapsible for large datasets)
    lines += ["## Per-Game Breakdown", ""]
    game_feats = [
        "n_shots_tracked", "touches_per_game", "paint_dwell_pct",
        "shot_zone_3pt_pct", "catch_shoot_pct", "contested_shot_rate",
        "avg_defender_distance", "potential_assists",
    ]
    available_gf = [f for f in game_feats if f in means.index]

    if available_gf and n_games > 0:
        # Find the player's game rows in real_rows (re-fetched below as stats don't carry DataFrame)
        # We'll note this needs the raw game data — not stored in stats dict currently
        # Instead, list available game IDs and season
        lines.append("*Game IDs tracked (real data):*")
        game_season_pairs = [
            (g, season_from_game_id(g)) for g in stats["real_game_ids"]
        ]
        season_groups: dict[str, list[str]] = defaultdict(list)
        for gid, szn in game_season_pairs:
            season_groups[szn].append(gid)

        for szn, gids in sorted(season_groups.items()):
            lines.append(f"- **{szn}:** {', '.join(f'`{g}`' for g in gids)}")
        lines.append("")

    # ── Footer
    lines += [
        "---",
        f"*Generated by `scripts/build_player_cards.py` on {TODAY} | Source: `cv_features` table + INT-1 fingerprints*",
        f"*[[_Player_Index]] | [[Player_Atlas]]*",
        "",
    ]

    return "\n".join(lines)


# ── Index generation ────────────────────────────────────────────────────────

def render_index(
    cards_meta: list[dict],
    arch_defs: dict[int, dict],
    fingerprints: pd.DataFrame,
) -> str:
    """Render _Player_Index.md."""
    lines = [
        f"# Player Intelligence Index (v1, {TODAY})",
        "",
        "[[Player_Atlas]] — overall behavioral landscape",
        "",
        f"**Cards generated:** {len(cards_meta)} players with ≥3 real CV games",
        f"**Last updated:** {TODAY}",
        "",
        "---",
        "",
    ]

    # Group by archetype if fingerprints available
    if not fingerprints.empty and arch_defs:
        lines += ["## By Archetype", ""]

        # Group cards by archetype
        by_archetype: dict[int, list[dict]] = defaultdict(list)
        no_archetype: list[dict] = []
        for meta in cards_meta:
            pid = meta["player_id"]
            if not fingerprints.empty and pid in fingerprints.index:
                arch_id = fingerprints.loc[pid, "archetype_id"]
                if pd.isna(arch_id):
                    no_archetype.append(meta)
                else:
                    by_archetype[int(arch_id)].append(meta)
            else:
                no_archetype.append(meta)

        for arch_id in sorted(by_archetype.keys()):
            arch_info = arch_defs.get(arch_id, {})
            arch_name = arch_info.get("name", f"Archetype {arch_id}")
            players_in_arch = sorted(by_archetype[arch_id], key=lambda x: -x["n_games"])
            lines += [
                f"### {arch_name} (n={len(players_in_arch)} tracked)",
                "",
            ]
            for meta in players_in_arch:
                slug = meta["slug"]
                name = meta["name"]
                team = meta["team"]
                n = meta["n_games"]
                pid = meta["player_id"]
                lines.append(
                    f"- [{name}](Players/{pid}_{slug}.md) ({team}, {n} games)"
                )
            lines.append("")

        if no_archetype:
            lines += [f"### Unclassified (n={len(no_archetype)})", ""]
            for meta in sorted(no_archetype, key=lambda x: -x["n_games"]):
                slug = meta["slug"]
                name = meta["name"]
                team = meta["team"]
                n = meta["n_games"]
                pid = meta["player_id"]
                lines.append(
                    f"- [{name}](Players/{pid}_{slug}.md) ({team}, {n} games)"
                )
            lines.append("")

    else:
        lines += ["## All Players (sorted by games tracked)", ""]
        for meta in sorted(cards_meta, key=lambda x: -x["n_games"]):
            slug = meta["slug"]
            name = meta["name"]
            team = meta["team"]
            n = meta["n_games"]
            pid = meta["player_id"]
            lines.append(
                f"- [{name}](Players/{pid}_{slug}.md) ({team}, {n} games)"
            )
        lines.append("")

    # Top 25 most-tracked
    lines += ["---", "", "## Most CV-Tracked Players (top 25)", ""]
    top25 = sorted(cards_meta, key=lambda x: -x["n_games"])[:25]
    for i, meta in enumerate(top25, 1):
        slug = meta["slug"]
        name = meta["name"]
        team = meta["team"]
        n = meta["n_games"]
        pid = meta["player_id"]
        lines.append(f"{i}. [{name}](Players/{pid}_{slug}.md) ({team}) — {n} games")
    lines.append("")

    # Team coverage
    from collections import Counter
    team_counts = Counter(m["team"] for m in cards_meta)
    top_teams = team_counts.most_common(5)
    lines += ["---", "", "## Coverage by Team (top 5)", ""]
    for team, cnt in top_teams:
        lines.append(f"- **{team}:** {cnt} player cards")
    lines.append("")

    lines += [
        "---",
        f"*Generated by `scripts/build_player_cards.py` on {TODAY}*",
        "",
    ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("[INT-2] Building Player Intelligence Cards...\n")

    # ── Load data
    print("Loading player roster lookup...")
    player_lookup = load_player_lookup()
    print(f"  {len(player_lookup)} players in roster")

    print("Loading CV feature data from database...")
    wide_df = load_cv_data()
    print(f"  {len(wide_df)} (player, game) rows loaded")

    print("Loading INT-1 fingerprints...")
    fingerprints = load_fingerprints()
    print(f"  {len(fingerprints)} player fingerprints" if not fingerprints.empty else "  No fingerprints found — comparables + archetypes will be skipped")

    print("Loading archetype definitions...")
    arch_defs = load_archetype_defs()
    print(f"  {len(arch_defs)} archetypes defined")

    # ── Filter to players with >= 3 real games
    print("\nFiltering to players with >= 3 real games...")
    all_features = [c for c in wide_df.columns if c not in ("player_id", "game_id")]
    # Exclude meta/auxiliary features from real-game check (same exclusion as game_is_real)
    _sum_features = [f for f in all_features if f not in ("cv_archetype", "cv_xast_pred")]
    wide_df["_sum"] = wide_df[_sum_features].fillna(0).sum(axis=1)
    wide_df["_real"] = wide_df["_sum"] > REAL_GAME_THRESHOLD

    player_real_counts = wide_df.groupby("player_id")["_real"].sum()
    eligible_pids = player_real_counts[player_real_counts >= 3].index.tolist()
    print(f"  {len(eligible_pids)} players with >= 3 real games")

    # ── Build global player means (for outlier detection)
    print("Computing global feature means for outlier detection...")
    all_player_means_list = []
    for pid in eligible_pids:
        rows = wide_df[wide_df["player_id"] == pid]
        real_rows = rows[rows["_real"]]
        feat_means = real_rows[all_features].mean()
        feat_means["player_id"] = pid
        all_player_means_list.append(feat_means)

    all_player_means = pd.DataFrame(all_player_means_list).set_index("player_id")

    # ── Create output directory
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Generate cards
    print(f"\nGenerating cards -> {OUT_DIR}")
    cards_meta: list[dict] = []
    skipped_no_name: list[int] = []
    n_written = 0

    for pid in eligible_pids:
        player_info = player_lookup.get(pid)
        if not player_info:
            skipped_no_name.append(pid)
            continue

        rows = wide_df[wide_df["player_id"] == pid].drop(columns=["_sum", "_real"])

        stats = compute_player_stats(rows, all_player_means, fingerprints)

        if stats["n_real"] < 3:
            continue

        card_md = render_card(pid, player_info, stats, fingerprints, arch_defs)

        slug = re.sub(r"[^a-z0-9]+", "_", player_info["name"].lower()).strip("_")
        filename = f"{pid}_{slug}.md"
        out_path = OUT_DIR / filename

        out_path.write_text(card_md, encoding="utf-8")
        n_written += 1

        # Get archetype for index
        arch_name = "Unknown"
        if not fingerprints.empty and pid in fingerprints.index:
            arch_name = str(fingerprints.loc[pid, "archetype_name"])

        cards_meta.append({
            "player_id": pid,
            "name": player_info["name"],
            "team": player_info["team"],
            "n_games": stats["n_real"],
            "slug": slug,
            "archetype": arch_name,
        })

        if n_written % 20 == 0:
            print(f"  ... {n_written} cards written")

    print(f"  Total cards written: {n_written}")
    if skipped_no_name:
        print(f"  Skipped (unresolved name): {len(skipped_no_name)} players — IDs: {skipped_no_name}")

    # ── Generate index
    print(f"\nGenerating index → {INDEX_PATH}")
    index_md = render_index(cards_meta, arch_defs, fingerprints)
    INDEX_PATH.write_text(index_md, encoding="utf-8")
    print("  Index written.")

    # ── Final report
    print("\n" + "=" * 60)
    print("## INT-2 Player Intelligence Cards — Final Report")
    print("=" * 60)
    print(f"\nCards generated: {n_written}")
    print(f"  Players with >= 3 real games: {len(eligible_pids)}")
    print(f"  Cards written to: {OUT_DIR}")
    print(f"  Index at: {INDEX_PATH}")
    print(f"  Skipped (unresolved): {len(skipped_no_name)}")

    from collections import Counter
    team_dist = Counter(m["team"] for m in cards_meta)
    print("\nCoverage by team (top 5):")
    for team, cnt in team_dist.most_common(5):
        print(f"  {team}: {cnt} cards")

    print("\nTop 10 most-tracked players:")
    top10 = sorted(cards_meta, key=lambda x: -x["n_games"])[:10]
    for i, m in enumerate(top10, 1):
        print(f"  {i}. {m['name']} ({m['team']}) — {m['n_games']} games | {m['archetype']}")

    # Sample one card
    if cards_meta:
        sample_meta = sorted(cards_meta, key=lambda x: -x["n_games"])[0]
        sample_path = OUT_DIR / f"{sample_meta['player_id']}_{sample_meta['slug']}.md"
        print(f"\nSample card: {sample_path}")

    print("\nFiles:")
    print(f"  scripts/build_player_cards.py")
    print(f"  vault/Intelligence/_Player_Index.md")
    print(f"  vault/Intelligence/Players/*.md  ({n_written} files)")


if __name__ == "__main__":
    # Force UTF-8 stdout on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
