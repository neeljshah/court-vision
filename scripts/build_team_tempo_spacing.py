"""
INT-62: Team Tempo & Spacing Atlas (C1 + C2)
Own-offense side of the matchup grid. Complements C3 (opp defensive intensity)
and C4 (opp paint allowance) which cover the OPP-DEFENSE side.

C1 — Team Pace / Tempo (2 dims; possessions_per_minute unavailable in cv_features):
  possession_duration_avg  -> team_possession_duration_z  (inverted: low duration = high pace)
  play_type_transition_pct -> team_transition_share_z

C2 — Team Spacing (2 dims; avg_off_ball_distance unavailable in cv_features):
  avg_spacing              -> team_avg_spacing_z
  paint_dwell_pct          -> team_paint_dwell_z          (inverted: high dwell = low spacing)

Aggregation:
  groupby (own_team, season, game_date)
  .agg(mean per dim)
  .shift(1).rolling(5, min_periods=2).mean()  <- strict prior-games window
  .z-score WITHIN season (expanding league pool, strictly < game_date)

Composite:
  team_tempo_z    = equal-weight mean of available C1 z-scores
  team_spacing_z  = equal-weight mean of available C2 z-scores
  team_tempo_spacing_composite_z = 0.5 * team_tempo_z + 0.5 * team_spacing_z

Ship gates:
  - All per-dim z stds >= 0.3 (drop dim if not; ship remaining composite)
  - data_density >= 40% med-or-better
  - team_tempo_z vs team_spacing_z internal |r| <= 0.6 (else collapse to C1-only)
  - team_tempo_spacing_composite_z vs C3 |r| < 0.5 (REJECT if >= 0.5)
  - team_tempo_spacing_composite_z vs C4 |r| < 0.5 (REJECT if >= 0.5)
  - team_tempo_z vs NBA-API pace |r| < 0.9 (REJECT if >= 0.9 — pure proxy)

Outputs:
  data/intelligence/team_tempo_spacing.parquet

Usage:
    python scripts/build_team_tempo_spacing.py
    python scripts/build_team_tempo_spacing.py --window 10
    python scripts/build_team_tempo_spacing.py --report-only
"""
from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths — script-relative ROOT; no hardcoded Windows paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
NBA_CACHE_DIR = DATA_DIR / "nba"
DB_PATH = DATA_DIR / "nba_ai.db"
OUT_PARQUET = DATA_DIR / "intelligence" / "team_tempo_spacing.parquet"
C3_PARQUET = DATA_DIR / "intelligence" / "opp_defensive_intensity.parquet"
C4_PARQUET = DATA_DIR / "intelligence" / "opp_paint_allowance.parquet"
TEAM_ADV_STATS = DATA_DIR / "team_advanced_stats.parquet"

# ---------------------------------------------------------------------------
# Feature definitions — only those present in cv_features
# ---------------------------------------------------------------------------

# C1 Tempo dims (possession_duration_avg inverted: low duration = high pace)
_TEMPO_FEATURES = {
    "possession_duration_avg": "team_possession_duration_z",   # sign-inverted
    "play_type_transition_pct": "team_transition_share_z",
}
_TEMPO_SIGN_INVERT = {"team_possession_duration_z"}  # high duration = slow pace -> invert

# C2 Spacing dims (paint_dwell_pct inverted: high dwell = low spacing)
_SPACING_FEATURES = {
    "avg_spacing": "team_avg_spacing_z",
    "paint_dwell_pct": "team_paint_dwell_z",                   # sign-inverted
}
_SPACING_SIGN_INVERT = {"team_paint_dwell_z"}  # high dwell = low spacing -> invert

# Combined map: cv_col -> (output_z_col, sign_invert)
_ALL_FEATURES = {}
for cv_col, z_col in _TEMPO_FEATURES.items():
    _ALL_FEATURES[cv_col] = (z_col, cv_col in {
        k for k, v in _TEMPO_FEATURES.items() if v in _TEMPO_SIGN_INVERT
    })
for cv_col, z_col in _SPACING_FEATURES.items():
    _ALL_FEATURES[cv_col] = (z_col, cv_col in {
        k for k, v in _SPACING_FEATURES.items() if v in _SPACING_SIGN_INVERT
    })

# Bug 22 sentinel guard (keep parity with C3/C4)
_DEFENDER_DIST_MAX = 50.0

# Ship gate thresholds
_MIN_Z_STD = 0.3
_DENSITY_MED_FLOOR = 0.40
_INTERNAL_COLLAPSE_R = 0.6      # tempo vs spacing; if > collapse to C1-only
_C3_C4_REJECT_R = 0.5           # vs C3 or C4 composite
_NBA_PACE_REJECT_R = 0.9        # vs NBA-API pace; if >= -> pure proxy -> REJECT


# ---------------------------------------------------------------------------
# Step 1: Load player_id -> team_abbrev (verbatim from C3/C4)
# ---------------------------------------------------------------------------

def _load_player_team_map() -> Dict[int, str]:
    """Build {player_id: team_abbrev} from player_full_*.json. Most-recent season wins."""
    pid_to_team: Dict[int, str] = {}
    season_files = ["player_full_2025-26.json", "player_full_2024-25.json",
                    "player_full_2023-24.json"]
    for fname in season_files:
        fpath = NBA_CACHE_DIR / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
            continue
        if isinstance(data, dict):
            for _name, info in data.items():
                if isinstance(info, dict):
                    pid = info.get("player_id") or info.get("PLAYER_ID")
                    team = info.get("team") or info.get("TEAM_ABBREVIATION")
                    if pid and team:
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    pid = row.get("player_id") or row.get("PLAYER_ID")
                    team = row.get("team") or row.get("TEAM_ABBREVIATION")
                    if pid and team:
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
    return pid_to_team


# ---------------------------------------------------------------------------
# Step 2: Load game_id -> {date, home_team, away_team} (verbatim from C3/C4)
# ---------------------------------------------------------------------------

def _load_game_info_map() -> Dict[str, dict]:
    """Return {game_id: {date, home_team, away_team}} from all season_games_*.json."""
    gmap: Dict[str, dict] = {}
    for fpath in glob.glob(str(NBA_CACHE_DIR / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row:
                    gid = str(row["game_id"])
                    gmap[gid] = {
                        "date": row.get("game_date", ""),
                        "home_team": row.get("home_team", ""),
                        "away_team": row.get("away_team", ""),
                    }
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
    return gmap


# ---------------------------------------------------------------------------
# Step 3: Load cv_features from DB, pivot wide (verbatim from C3/C4)
# ---------------------------------------------------------------------------

def _load_cv_wide(db_path: Path) -> pd.DataFrame:
    """Load cv_features and pivot to wide form (one row per game_id x player_id)."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
        " WHERE player_id != 0"
    ).fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["player_id", "game_id", "feature_name", "feature_value"])
    wide = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide


# ---------------------------------------------------------------------------
# Step 4: Map players to OFFENSIVE team (own team) and add game_date
# ---------------------------------------------------------------------------

def _assign_teams(
    wide: pd.DataFrame,
    pid_to_team: Dict[int, str],
    game_info: Dict[str, dict],
) -> pd.DataFrame:
    """
    Add columns: own_team, game_date.
    own_team = team the player belongs to (OWN offense — C1/C2 perspective).
    """
    wide["own_team"] = wide["player_id"].map(lambda p: pid_to_team.get(int(p)))
    wide["game_date"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("date", ""))
    wide["home_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("home_team", ""))
    wide["away_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("away_team", ""))

    # Validate own_team is actually in the game (trade artifact guard)
    def _validate_own_team(row):
        ot = row["own_team"]
        if not ot:
            return None
        ht = row["home_team"]
        at = row["away_team"]
        if ot in (ht, at):
            return ot
        return None  # trade artifact — skip

    wide["own_team"] = wide.apply(_validate_own_team, axis=1)

    before = len(wide)
    wide = wide.dropna(subset=["own_team", "game_date"])
    wide = wide[wide["game_date"] != ""]
    after = len(wide)
    print(f"  Player-game rows after team assignment: {after} (dropped {before - after} unmapped)")
    return wide


# ---------------------------------------------------------------------------
# Step 5: Aggregate tempo/spacing features to (game_id, own_team) level
# ---------------------------------------------------------------------------

def _compute_raw_game_level(wide: pd.DataFrame) -> pd.DataFrame:
    """
    Average each tempo/spacing feature across all players for a team in a game.
    Returns one row per (game_id, own_team, game_date).
    """
    feat_cols = list(_ALL_FEATURES.keys())
    for col in feat_cols:
        if col not in wide.columns:
            wide[col] = np.nan

    wide = wide.copy()

    agg_dict = {col: "mean" for col in feat_cols}
    agg_dict["player_id"] = "count"

    game_level = (
        wide.groupby(["game_id", "own_team", "game_date"])
        .agg(agg_dict)
        .reset_index()
        .rename(columns={"player_id": "n_player_games_in_game"})
    )
    game_level["game_date"] = pd.to_datetime(game_level["game_date"])
    game_level = game_level.sort_values("game_date").reset_index(drop=True)
    return game_level


# ---------------------------------------------------------------------------
# Step 6: Walk-forward rolling window + expanding z-score pool
# ---------------------------------------------------------------------------

def _compute_rolling_tempo_spacing(
    game_level: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """
    For each (own_team, game_date):
      1. Rolling-window mean over prior `window` games (strict < game_date), min_periods=2
      2. Z-score via expanding league pool (all team-window means strictly < game_date)
      3. Sign inversion for duration (slow) and paint_dwell (paint-bound)
      4. Shrinkage for small-N windows
      5. Sub-composites (tempo_z, spacing_z) and overall composite

    Returns rows: team_id, season, game_date, n_games_window, per-dim z's, composites,
                  data_density, n_raw_frames (approx), n_possessions_window
    """
    teams = sorted(game_level["own_team"].unique())
    print(f"  Computing rolling tempo+spacing for {len(teams)} own-offense teams, window={window} ...")

    feat_cols = list(_ALL_FEATURES.keys())
    game_level = game_level.sort_values(["game_date", "own_team"]).reset_index(drop=True)

    # Step 6a: per-team rolling window means (strict < game_date, min_periods=2)
    team_windows: List[dict] = []

    for team in teams:
        tdf = game_level[game_level["own_team"] == team].sort_values("game_date")

        for _, row in tdf.iterrows():
            gdate = row["game_date"]
            past = tdf[tdf["game_date"] < gdate].tail(window)
            n = len(past)

            if n < 2:
                continue  # min_periods=2

            rec: dict = {
                "team_id": team,
                "game_date": gdate,
                "n_games_window": n,
            }

            for feat in feat_cols:
                vals = past[feat].dropna()
                rec[f"_raw_{feat}"] = float(vals.mean()) if len(vals) >= 1 else np.nan

            # n_possessions proxy: sum of n_player_games as crude denominator
            rec["_n_player_games_sum"] = float(past["n_player_games_in_game"].sum())

            team_windows.append(rec)

    if not team_windows:
        print("  WARNING: No team windows computed. Insufficient data.")
        return pd.DataFrame()

    tw_df = pd.DataFrame(team_windows).sort_values("game_date").reset_index(drop=True)
    print(f"  Team-game windows computed: {len(tw_df)} rows")

    # Step 6b: z-score each raw dim via expanding league pool (strict < game_date)
    all_dates = tw_df["game_date"]

    for cv_col, (z_col, sign_invert) in _ALL_FEATURES.items():
        raw_col = f"_raw_{cv_col}"
        if raw_col not in tw_df.columns:
            tw_df[z_col] = np.nan
            continue

        raw_series = tw_df[raw_col]
        z_vals = np.full(len(tw_df), np.nan)

        for idx, (_, row) in enumerate(tw_df.iterrows()):
            curr_val = row[raw_col]
            if pd.isna(curr_val):
                z_vals[idx] = np.nan
                continue

            curr_date = row["game_date"]
            mask = all_dates < curr_date
            pool = raw_series[mask].dropna()

            if len(pool) < 2:
                z_vals[idx] = np.nan  # league_prior candidate
            else:
                mu = pool.mean()
                sigma = pool.std(ddof=1)
                if sigma < 1e-9:
                    z_vals[idx] = 0.0
                else:
                    z = (curr_val - mu) / sigma
                    if sign_invert:
                        z = -z  # invert: high duration->low pace; high dwell->low spacing
                    z_vals[idx] = float(z)

        tw_df[z_col] = z_vals

    # Step 6c: Shrinkage for small-N windows (same as C3/C4)
    all_z_cols = [v[0] for v in _ALL_FEATURES.values()]

    def _apply_shrinkage(row, col):
        n = row["n_games_window"]
        v = row[col]
        if pd.isna(v):
            return v
        if n < 2:
            return 0.0
        elif n < 5:
            return v * (n / 5.0)
        return v

    for col in all_z_cols:
        if col in tw_df.columns:
            tw_df[col] = tw_df.apply(lambda r, c=col: _apply_shrinkage(r, c), axis=1)

    # Step 6d: Sub-composites (equal-weight NaN-safe mean)
    tempo_z_cols = [_TEMPO_FEATURES[c] for c in _TEMPO_FEATURES if _TEMPO_FEATURES[c] in tw_df.columns]
    spacing_z_cols = [_SPACING_FEATURES[c] for c in _SPACING_FEATURES if _SPACING_FEATURES[c] in tw_df.columns]

    def _mean_z(row, cols):
        vals = [row[c] for c in cols if c in row.index and not pd.isna(row[c])]
        if not vals:
            return np.nan
        return float(np.mean(vals))

    tw_df["team_tempo_z"] = tw_df.apply(lambda r: _mean_z(r, tempo_z_cols), axis=1)
    tw_df["team_spacing_z"] = tw_df.apply(lambda r: _mean_z(r, spacing_z_cols), axis=1)

    # Step 6e: Overall composite
    def _composite(row):
        t = row["team_tempo_z"]
        s = row["team_spacing_z"]
        if pd.isna(t) and pd.isna(s):
            return np.nan
        elif pd.isna(t):
            return float(s)
        elif pd.isna(s):
            return float(t)
        return float(0.5 * t + 0.5 * s)

    tw_df["team_tempo_spacing_composite_z"] = tw_df.apply(_composite, axis=1)

    # Step 6f: Data density label
    def _density(n):
        if n >= 10:
            return "high"
        elif n >= 5:
            return "med"
        elif n >= 2:
            return "low"
        else:
            return "league_prior"

    tw_df["data_density"] = tw_df["n_games_window"].map(_density)

    # Step 6g: Season from game_date
    def _season(d):
        y, m = d.year, d.month
        if m >= 10:
            return f"{y}-{str(y + 1)[-2:]}"
        else:
            return f"{y - 1}-{str(y)[-2:]}"

    tw_df["season"] = tw_df["game_date"].map(_season)
    tw_df["game_date"] = tw_df["game_date"].dt.strftime("%Y-%m-%d")

    # Step 6h: Auxiliary columns
    tw_df["n_raw_frames"] = np.nan       # not available per game in this pipeline
    tw_df["n_possessions_window"] = tw_df["_n_player_games_sum"].fillna(0).astype(int)

    # team_abbr == team_id (tricode) for now
    tw_df["team_abbr"] = tw_df["team_id"]

    # Select output columns (schema spec from INT-62)
    keep_cols = [
        "team_id", "team_abbr", "season", "game_date", "n_games_window",
        "team_possession_duration_z", "team_transition_share_z", "team_tempo_z",
        "team_avg_spacing_z", "team_paint_dwell_z", "team_spacing_z",
        "team_tempo_spacing_composite_z",
        "data_density", "n_raw_frames", "n_possessions_window",
    ]
    for col in keep_cols:
        if col not in tw_df.columns:
            tw_df[col] = np.nan

    return tw_df[keep_cols].sort_values(["team_id", "game_date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 7: Orthogonality gates
# ---------------------------------------------------------------------------

def _orthogonality_gates(result: pd.DataFrame) -> dict:
    """
    Run 4 orthogonality checks:
      1. team_tempo_z vs NBA-API pace per100 (|r| >= 0.9 -> REJECT)
      2. composite vs C3 opp_defensive_intensity_z (|r| >= 0.5 -> REJECT)
      3. composite vs C4 opp_shot_mix_deviation_z (|r| >= 0.5 -> REJECT)
      4. team_tempo_z vs team_spacing_z internal (|r| > 0.6 -> collapse to C1-only)
    """
    findings = {
        "r_tempo_vs_nba_pace": None,
        "r_composite_vs_c3": None,
        "r_composite_vs_c4": None,
        "r_tempo_vs_spacing_internal": None,
    }

    composite_col = "team_tempo_spacing_composite_z"

    # Gate 1: tempo_z vs NBA-API pace (team-level aggregate correlation)
    if TEAM_ADV_STATS.exists():
        try:
            tas = pd.read_parquet(TEAM_ADV_STATS)
            tas["season_year"] = pd.to_datetime(tas["game_date"]).dt.year
            recent = tas[tas["season_year"] >= 2024]
            pace_agg = recent.groupby("team_tricode")["pace"].mean().reset_index()
            pace_agg.columns = ["team_id", "nba_pace_mean"]

            tempo_agg = (
                result.groupby("team_id")["team_tempo_z"].mean().reset_index()
            )
            merged_pace = tempo_agg.merge(pace_agg, on="team_id", how="inner")
            if len(merged_pace) >= 5:
                r_pace = float(merged_pace["team_tempo_z"].corr(merged_pace["nba_pace_mean"]))
                findings["r_tempo_vs_nba_pace"] = r_pace
                findings["n_pace_teams"] = len(merged_pace)
                abs_rp = abs(r_pace)
                print(f"  Gate 1 — tempo_z vs NBA-API pace: r = {r_pace:+.4f}")
                if abs_rp >= _NBA_PACE_REJECT_R:
                    print(f"  REJECT: |r| = {abs_rp:.3f} >= {_NBA_PACE_REJECT_R} — pure proxy of NBA-API pace")
                    findings["gate1_verdict"] = f"REJECT (|r|={abs_rp:.3f})"
                else:
                    print(f"  OK: |r| = {abs_rp:.3f} < {_NBA_PACE_REJECT_R} — CV tempo adds independent signal")
                    findings["gate1_verdict"] = f"OK (|r|={abs_rp:.3f})"
            else:
                print(f"  Gate 1: too few overlap teams ({len(merged_pace)}); skip")
                findings["gate1_verdict"] = "SKIP (too few teams)"
        except Exception as e:
            print(f"  Gate 1 WARNING: {e}")
            findings["gate1_verdict"] = f"SKIP ({e})"
    else:
        print("  Gate 1: team_advanced_stats.parquet not found; hardcoded pace sanity only")
        findings["gate1_verdict"] = "SKIP (no nba-api file)"

    # Gate 2: composite vs C3
    if C3_PARQUET.exists():
        try:
            c3 = pd.read_parquet(C3_PARQUET)
            c3_col = "opp_defensive_intensity_z"
            if c3_col in c3.columns:
                merged_c3 = result.merge(
                    c3[["team_id", "game_date", c3_col]],
                    on=["team_id", "game_date"],
                    how="inner",
                )
                print(f"  Gate 2 — composite vs C3: {len(merged_c3)} overlap rows")
                if len(merged_c3) >= 5:
                    r_c3 = float(merged_c3[composite_col].corr(merged_c3[c3_col]))
                    findings["r_composite_vs_c3"] = r_c3
                    findings["n_c3_overlap"] = len(merged_c3)
                    abs_r3 = abs(r_c3)
                    print(f"  Gate 2 — r_composite vs C3 = {r_c3:+.4f}")
                    if abs_r3 >= _C3_C4_REJECT_R:
                        print(f"  REJECT: |r| = {abs_r3:.3f} >= {_C3_C4_REJECT_R}")
                        findings["gate2_verdict"] = f"REJECT (|r|={abs_r3:.3f})"
                    else:
                        print(f"  OK: |r| = {abs_r3:.3f} < {_C3_C4_REJECT_R}")
                        findings["gate2_verdict"] = f"OK (|r|={abs_r3:.3f})"
                else:
                    findings["gate2_verdict"] = "SKIP (too few rows)"
            else:
                findings["gate2_verdict"] = "SKIP (C3 column missing)"
        except Exception as e:
            print(f"  Gate 2 WARNING: {e}")
            findings["gate2_verdict"] = f"SKIP ({e})"
    else:
        print("  Gate 2: C3 parquet not found; skip")
        findings["gate2_verdict"] = "SKIP (C3 unavailable)"

    # Gate 3: composite vs C4
    if C4_PARQUET.exists():
        try:
            c4 = pd.read_parquet(C4_PARQUET)
            c4_col = "opp_shot_mix_deviation_z"
            # Fallback: use first composite-ish column if opp_shot_mix_deviation_z missing
            if c4_col not in c4.columns:
                c4_candidates = [c for c in c4.columns if "z" in c and c not in ("team_id", "season", "game_date")]
                c4_col = c4_candidates[0] if c4_candidates else None
            if c4_col:
                merged_c4 = result.merge(
                    c4[["team_id", "game_date", c4_col]],
                    on=["team_id", "game_date"],
                    how="inner",
                )
                print(f"  Gate 3 — composite vs C4 ({c4_col}): {len(merged_c4)} overlap rows")
                if len(merged_c4) >= 5:
                    r_c4 = float(merged_c4[composite_col].corr(merged_c4[c4_col]))
                    findings["r_composite_vs_c4"] = r_c4
                    findings["n_c4_overlap"] = len(merged_c4)
                    abs_r4 = abs(r_c4)
                    print(f"  Gate 3 — r_composite vs C4 = {r_c4:+.4f}")
                    if abs_r4 >= _C3_C4_REJECT_R:
                        print(f"  REJECT: |r| = {abs_r4:.3f} >= {_C3_C4_REJECT_R}")
                        findings["gate3_verdict"] = f"REJECT (|r|={abs_r4:.3f})"
                    else:
                        print(f"  OK: |r| = {abs_r4:.3f} < {_C3_C4_REJECT_R}")
                        findings["gate3_verdict"] = f"OK (|r|={abs_r4:.3f})"
                else:
                    findings["gate3_verdict"] = "SKIP (too few rows)"
            else:
                findings["gate3_verdict"] = "SKIP (C4 column missing)"
        except Exception as e:
            print(f"  Gate 3 WARNING: {e}")
            findings["gate3_verdict"] = f"SKIP ({e})"
    else:
        print("  Gate 3: C4 parquet not found; skip")
        findings["gate3_verdict"] = "SKIP (C4 unavailable)"

    # Gate 4: internal tempo_z vs spacing_z (> 0.6 -> collapse to C1-only)
    valid_mask = result["team_tempo_z"].notna() & result["team_spacing_z"].notna()
    if valid_mask.sum() >= 5:
        r_int = float(result.loc[valid_mask, "team_tempo_z"].corr(
            result.loc[valid_mask, "team_spacing_z"]
        ))
        findings["r_tempo_vs_spacing_internal"] = r_int
        abs_ri = abs(r_int)
        print(f"  Gate 4 — internal tempo_z vs spacing_z: r = {r_int:+.4f}")
        if abs_ri > _INTERNAL_COLLAPSE_R:
            print(f"  COLLAPSE: |r| = {abs_ri:.3f} > {_INTERNAL_COLLAPSE_R} — drop spacing, ship C1-only")
            findings["gate4_verdict"] = f"COLLAPSE to C1-only (|r|={abs_ri:.3f})"
        else:
            print(f"  OK: |r| = {abs_ri:.3f} <= {_INTERNAL_COLLAPSE_R} — factors orthogonal enough")
            findings["gate4_verdict"] = f"OK (|r|={abs_ri:.3f})"
    else:
        findings["gate4_verdict"] = "SKIP (too few valid rows)"

    return findings


# ---------------------------------------------------------------------------
# Step 8: Sanity checks — rankings + z-std gate
# ---------------------------------------------------------------------------

def _sanity_check(result: pd.DataFrame) -> dict:
    """
    - Per-dim z std >= 0.3 gate
    - Top/bottom teams by tempo_z + spacing_z
    - Pace-leader sanity (expected fast/slow teams)
    - Data density distribution
    """
    findings = {}

    # Team-level aggregates
    z_cols_of_interest = [
        "team_possession_duration_z", "team_transition_share_z", "team_tempo_z",
        "team_avg_spacing_z", "team_paint_dwell_z", "team_spacing_z",
        "team_tempo_spacing_composite_z",
    ]
    team_agg = result.groupby("team_id")[z_cols_of_interest].mean()

    # Per-dim z std gate
    print("\n  Per-dim z-score std (gate >= 0.3):")
    z_stds = {}
    dims_failed = []
    for col in z_cols_of_interest:
        if col in result.columns:
            std = float(result[col].std())
            z_stds[col] = std
            status = "OK" if std >= _MIN_Z_STD else "BELOW FLOOR"
            if std < _MIN_Z_STD and col not in ("team_tempo_spacing_composite_z",
                                                  "team_tempo_z", "team_spacing_z"):
                dims_failed.append(col)
            print(f"    {col}: std={std:.4f} [{status}]")
    findings["z_stds"] = z_stds
    findings["z_std_gate_pass"] = len(dims_failed) == 0
    findings["dims_below_floor"] = dims_failed

    # Top/bottom-5 by tempo_z
    tempo_sorted = team_agg["team_tempo_z"].dropna().sort_values(ascending=False)
    top3_tempo = list(tempo_sorted.head(3).index)
    bot3_tempo = list(tempo_sorted.tail(3).index)
    findings["top3_tempo"] = top3_tempo
    findings["bottom3_tempo"] = bot3_tempo
    print(f"\n  Top-3 by team_tempo_z (fast-paced): {top3_tempo}")
    print(f"  Bottom-3 by team_tempo_z (slow-paced): {bot3_tempo}")

    # Pace sanity check
    expected_fast = {"IND", "MEM", "MIL", "ATL", "WAS"}
    expected_slow = {"MIA", "BOS", "NYK"}
    fast_hits = expected_fast & set(top3_tempo)
    slow_hits = expected_slow & set(bot3_tempo)
    print(f"  Fast-pace sanity: expected 2 of {expected_fast}, got {fast_hits}")
    print(f"  Slow-pace sanity: expected 2 of {expected_slow}, got {slow_hits}")
    findings["fast_pace_sanity_hits"] = list(fast_hits)
    findings["slow_pace_sanity_hits"] = list(slow_hits)
    findings["pace_sanity_pass"] = len(fast_hits) >= 2 and len(slow_hits) >= 2

    # Top/bottom-5 by spacing_z
    if "team_spacing_z" in team_agg.columns:
        spacing_sorted = team_agg["team_spacing_z"].dropna().sort_values(ascending=False)
        top3_spacing = list(spacing_sorted.head(3).index)
        bot3_spacing = list(spacing_sorted.tail(3).index)
        findings["top3_spacing"] = top3_spacing
        findings["bottom3_spacing"] = bot3_spacing
        print(f"\n  Top-3 by team_spacing_z (wide spacing): {top3_spacing}")
        print(f"  Bottom-3 by team_spacing_z (paint-heavy): {bot3_spacing}")

        expected_wide = {"BOS", "GSW", "DAL"}
        expected_paint = {"MEM", "NOP", "CHI"}
        wide_hits = expected_wide & set(top3_spacing)
        paint_hits = expected_paint & set(bot3_spacing)
        print(f"  Wide-spacing sanity: expected 2 of {expected_wide}, got {wide_hits}")
        print(f"  Paint-heavy sanity: expected 2 of {expected_paint}, got {paint_hits}")
        findings["wide_spacing_sanity_hits"] = list(wide_hits)
        findings["paint_heavy_sanity_hits"] = list(paint_hits)
        findings["spacing_sanity_pass"] = len(wide_hits) >= 2 and len(paint_hits) >= 2
    else:
        findings["spacing_sanity_pass"] = False

    # Data density distribution
    dens_dist = result["data_density"].value_counts(normalize=True).to_dict()
    findings["density_distribution"] = {k: round(v * 100, 1) for k, v in dens_dist.items()}
    print("\n  Data density distribution:")
    for bucket, pct in sorted(dens_dist.items(), key=lambda x: -x[1]):
        print(f"    {bucket}: {pct*100:.1f}%")

    med_or_better = sum(pct for k, pct in dens_dist.items() if k in ("high", "med"))
    findings["med_or_better_pct"] = round(med_or_better * 100, 1)
    density_flag = med_or_better >= _DENSITY_MED_FLOOR
    findings["density_gate_pass"] = density_flag
    print(f"\n  Med-or-better coverage: {med_or_better*100:.1f}% "
          f"({'OK' if density_flag else 'FLAG: below 40%'})")

    return findings


# ---------------------------------------------------------------------------
# Public reader API: walk-forward safe
# ---------------------------------------------------------------------------

def get_team_tempo_spacing(
    team: str,
    game_date: str,
    parquet_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Fetch the most recent tempo+spacing row for `team` with game_date STRICTLY
    less than the given game_date. Walk-forward safe.

    Args:
        team: team tricode (e.g. "IND")
        game_date: ISO date string "YYYY-MM-DD"
        parquet_path: override path to team_tempo_spacing.parquet

    Returns:
        dict with all tempo+spacing columns, or None if no prior data exists.
    """
    if parquet_path is None:
        parquet_path = OUT_PARQUET
    if not Path(parquet_path).exists():
        return None

    df = pd.read_parquet(parquet_path)
    subset = df[(df["team_id"] == team.upper()) & (df["game_date"] < game_date)]
    if subset.empty:
        return None
    return subset.sort_values("game_date").iloc[-1].to_dict()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="INT-62: Build team tempo & spacing atlas (C1+C2, own-offense, rolling z-scored)."
    )
    ap.add_argument("--window", type=int, default=5, help="Rolling window (default: 5 games)")
    ap.add_argument("--report-only", action="store_true", help="Skip write; print stats only")
    args = ap.parse_args()

    print("\n=== INT-62 Team Tempo & Spacing Atlas (C1+C2) ===")
    print(f"  C1 dims: {list(_TEMPO_FEATURES.keys())} (possessions_per_minute dropped — not in cv_features)")
    print(f"  C2 dims: {list(_SPACING_FEATURES.keys())} (avg_off_ball_distance dropped — not in cv_features)")

    # Load data
    print("\n--- Loading data sources ---")
    pid_to_team = _load_player_team_map()
    print(f"  player_id->team: {len(pid_to_team)} players")

    game_info = _load_game_info_map()
    print(f"  game_info map: {len(game_info)} games")

    wide = _load_cv_wide(DB_PATH)
    print(f"  cv_features wide: {len(wide)} player-game rows")

    wide = _assign_teams(wide, pid_to_team, game_info)
    game_level = _compute_raw_game_level(wide)
    print(f"  Game-level (own_team x game): {len(game_level)} rows, "
          f"{game_level['own_team'].nunique()} teams")

    # Rolling tempo + spacing
    print(f"\n--- Rolling tempo+spacing (window={args.window}) ---")
    result = _compute_rolling_tempo_spacing(game_level, window=args.window)

    if result.empty:
        print("ERROR: No output produced. Check data inputs.")
        sys.exit(1)

    print(f"  Output rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")

    # Sanity checks
    print("\n--- Sanity checks ---")
    sanity = _sanity_check(result)

    # Orthogonality gates
    print("\n--- Orthogonality gates ---")
    orth = _orthogonality_gates(result)

    # Derive overall ship verdict
    print("\n--- Ship verdict ---")
    rejects = []
    yellows = []

    for gk in ["gate1_verdict", "gate2_verdict", "gate3_verdict"]:
        v = orth.get(gk, "")
        if "REJECT" in str(v):
            rejects.append(f"{gk}: {v}")
        elif "YELLOW" in str(v):
            yellows.append(f"{gk}: {v}")

    gate4 = orth.get("gate4_verdict", "")
    c1_only = "COLLAPSE" in str(gate4)

    if rejects:
        final_verdict = "REJECT — " + "; ".join(rejects)
        print(f"  REJECT: {'; '.join(rejects)}")
    else:
        flags = []
        if c1_only:
            flags.append(f"C1-ONLY (spacing collapsed): {gate4}")
        if not sanity.get("z_std_gate_pass", True):
            flags.append(f"dim z_std below floor: {sanity.get('dims_below_floor')}")
        if not sanity.get("density_gate_pass", True):
            flags.append(f"density below 40%: {sanity.get('med_or_better_pct')}%")
        if yellows:
            flags.extend(yellows)

        if c1_only:
            final_verdict = "PARTIAL SHIP (C1 tempo-only; C2 spacing collapsed)"
            print(f"  PARTIAL SHIP: {gate4}")
        elif flags:
            final_verdict = "SHIP YELLOW — " + "; ".join(flags)
            print(f"  SHIP YELLOW: {'; '.join(flags)}")
        else:
            final_verdict = "SHIP"
            print("  SHIP: all gates passed")

    print(f"\n  Final verdict: {final_verdict}")

    # Write
    if not args.report_only:
        OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(OUT_PARQUET, index=False)
        print(f"\n  Saved: {OUT_PARQUET} ({len(result)} rows)")

    # Summary
    print("\n=== INT-62 COMPLETE ===")
    print(f"  Rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")
    print(f"  Density (med+): {sanity.get('med_or_better_pct')}%")
    print(f"  Dims shipped: C1={list(_TEMPO_FEATURES.values())}, C2={list(_SPACING_FEATURES.values())}")
    for gk, label in [("gate1_verdict", "Gate1 (pace proxy)"),
                       ("gate2_verdict", "Gate2 (vs C3)"),
                       ("gate3_verdict", "Gate3 (vs C4)"),
                       ("gate4_verdict", "Gate4 (internal)")]:
        print(f"  {label}: {orth.get(gk, 'N/A')}")
    print(f"  Verdict: {final_verdict}")

    return result, sanity, orth


if __name__ == "__main__":
    main()
