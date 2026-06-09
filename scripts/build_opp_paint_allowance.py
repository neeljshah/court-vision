"""
INT-58: Opponent Paint Allowance Signal (C4)
Rolling per-team-per-date zone-distribution z-scores (walk-forward safe).
Measures WHICH ZONE a defensive team is most permissive to — allocation shape,
not intensity level (orthogonal to INT-52 C3).

4 zone dimensions:
  shot_zone_paint_pct   -> opp_paint_pct_allowed_z      (high = more paint shots allowed)
  shot_zone_3pt_pct     -> opp_3pt_pct_allowed_z        (high = more 3pt shots allowed)
  shot_zone_mid_range_pct -> opp_mid_pct_allowed_z      (high = more mid-range allowed)
  paint_dwell_pct       -> opp_paint_dwell_pct_allowed_z (high = more paint dwell allowed)

NO sign inversion  — high pct already means "allowed more of this zone"
NO quality residualization — keep allocation shape, not level

Composite = RMS of first 3 zone z-scores (excluding paint_dwell):
  opp_shot_mix_deviation_z = sqrt(mean([z_paint^2, z_3pt^2, z_mid^2]))
  Magnitude only — "this team distorts shot-zone mix unusually"

Inputs:
  data/nba_ai.db              cv_features (long-form)
  data/nba/season_games_*.json  game_id -> date + home/away
  data/nba/player_full_*.json   player_id -> team
  data/intelligence/opp_defensive_intensity.parquet  (C3 — orthogonality gate)

Outputs:
  data/intelligence/opp_paint_allowance.parquet

Usage:
    python scripts/build_opp_paint_allowance.py
    python scripts/build_opp_paint_allowance.py --window 10
    python scripts/build_opp_paint_allowance.py --report-only
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
OUT_PARQUET = DATA_DIR / "intelligence" / "opp_paint_allowance.parquet"
C3_PARQUET = DATA_DIR / "intelligence" / "opp_defensive_intensity.parquet"

# ---------------------------------------------------------------------------
# Bug 22 sentinel guard: defender_distance >= 50 is 200.0 artifact
# (not used in zone features but kept for parity with C3)
# ---------------------------------------------------------------------------
_DEFENDER_DIST_MAX = 50.0

# Zone feature columns and their output z-score names
_ZONE_FEATURES = {
    "shot_zone_paint_pct": "opp_paint_pct_allowed_z",
    "shot_zone_3pt_pct": "opp_3pt_pct_allowed_z",
    "shot_zone_mid_range_pct": "opp_mid_pct_allowed_z",
    "paint_dwell_pct": "opp_paint_dwell_pct_allowed_z",
}

# Composite RMS uses these 3 dims (paint_dwell excluded)
_RMS_DIMS = ["opp_paint_pct_allowed_z", "opp_3pt_pct_allowed_z", "opp_mid_pct_allowed_z"]

# Orthogonality gate thresholds vs C3
_CORR_REJECT = 0.7
_CORR_YELLOW = 0.5

# Ship gate: each per-zone z std must be >= this
_MIN_Z_STD = 0.3

# Density distribution gate: prefer >40% medium-or-better
_DENSITY_MED_FLOOR = 0.40


# ---------------------------------------------------------------------------
# Step 1: Load player_id -> team_abbrev (verbatim from C3)
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
# Step 2: Load game_id -> {date, home_team, away_team} (verbatim from C3)
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
# Step 3: Load cv_features from DB, pivot wide (verbatim from C3)
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
# Step 4: Map players to offensive + defensive teams (verbatim from C3)
# ---------------------------------------------------------------------------

def _assign_teams(
    wide: pd.DataFrame,
    pid_to_team: Dict[int, str],
    game_info: Dict[str, dict],
) -> pd.DataFrame:
    """Add: offensive_team, defensive_team, game_date."""
    wide["offensive_team"] = wide["player_id"].map(lambda p: pid_to_team.get(int(p)))
    wide["game_date"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("date", ""))
    wide["home_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("home_team", ""))
    wide["away_team"] = wide["game_id"].map(lambda g: game_info.get(g, {}).get("away_team", ""))

    def _get_def_team(row):
        ot = row["offensive_team"]
        if not ot:
            return None
        ht = row["home_team"]
        at = row["away_team"]
        if ot == ht:
            return at
        elif ot == at:
            return ht
        else:
            return None  # trade artifact — skip

    wide["defensive_team"] = wide.apply(_get_def_team, axis=1)

    before = len(wide)
    wide = wide.dropna(subset=["offensive_team", "defensive_team", "game_date"])
    wide = wide[wide["game_date"] != ""]
    after = len(wide)
    print(f"  Player-game rows after team assignment: {after} (dropped {before - after} unmapped)")
    return wide


# ---------------------------------------------------------------------------
# Step 5: Aggregate zone features to (game_id, defensive_team) level
# ---------------------------------------------------------------------------

def _compute_raw_game_level(wide: pd.DataFrame) -> pd.DataFrame:
    """
    Average each zone pct across all offensive players per (game_id, defensive_team).
    NOTE: unweighted mean — 1-shot game counts equally with 15-shot game (v1 limitation).
    """
    feat_cols = list(_ZONE_FEATURES.keys())
    for col in feat_cols:
        if col not in wide.columns:
            wide[col] = np.nan

    agg_dict = {col: "mean" for col in feat_cols}
    agg_dict["player_id"] = "count"

    game_level = (
        wide.groupby(["game_id", "defensive_team", "game_date"])
        .agg(agg_dict)
        .reset_index()
        .rename(columns={"player_id": "n_player_games_in_game"})
    )
    game_level["game_date"] = pd.to_datetime(game_level["game_date"])
    game_level = game_level.sort_values("game_date").reset_index(drop=True)
    return game_level


# ---------------------------------------------------------------------------
# Step 6: Walk-forward rolling window + expanding z-score pool (adapted from C3)
# ---------------------------------------------------------------------------

def _compute_rolling_allowance(
    game_level: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """
    For each (defensive_team, game_date):
      1. Rolling-window mean of zone pct over prior `window` games (strict < game_date)
      2. Z-score via expanding league pool (strict < game_date)
      3. Shrinkage for small-N windows
      4. Composite RMS of 3 zone z's (opp_shot_mix_deviation_z)

    Returns rows: team_id, season, game_date, n_games_window, 4 zone z's, composite, data_density
    """
    teams = sorted(game_level["defensive_team"].unique())
    print(f"  Computing rolling allowance for {len(teams)} defensive teams, window={window} ...")

    feat_cols = list(_ZONE_FEATURES.keys())
    game_level = game_level.sort_values(["game_date", "defensive_team"]).reset_index(drop=True)

    # Step 6a: compute per-team rolling window means
    team_windows: List[dict] = []

    for team in teams:
        tdf = game_level[game_level["defensive_team"] == team].sort_values("game_date")

        for _, row in tdf.iterrows():
            gdate = row["game_date"]
            past = tdf[tdf["game_date"] < gdate].tail(window)
            n = len(past)

            if n == 0:
                continue  # no prior data

            rec: dict = {
                "team_id": team,
                "game_date": gdate,
                "n_games_window": n,
            }
            for feat in feat_cols:
                vals = past[feat].dropna()
                rec[f"_raw_{feat}"] = float(vals.mean()) if len(vals) else np.nan

            team_windows.append(rec)

    if not team_windows:
        print("  WARNING: No team windows computed. Insufficient data.")
        return pd.DataFrame()

    tw_df = pd.DataFrame(team_windows).sort_values("game_date").reset_index(drop=True)
    print(f"  Team-game windows computed: {len(tw_df)} rows")

    # Step 6b: z-score each raw dimension via expanding league pool (< game_date)
    raw_feature_map = {
        out_col: f"_raw_{feat}"
        for feat, out_col in _ZONE_FEATURES.items()
    }
    all_dates = tw_df["game_date"]

    for dim_col, raw_col in raw_feature_map.items():
        if raw_col not in tw_df.columns:
            tw_df[dim_col] = np.nan
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
                    # NO sign inversion — high pct already = more allowed
                    z_vals[idx] = float((curr_val - mu) / sigma)

        tw_df[dim_col] = z_vals

    # Step 6c: Shrinkage for small-N windows (same as C3)
    # n >= 5: use raw z directly
    # n 2-4: shrink toward 0 at weight n/5
    # n < 2: league prior (0)
    z_cols = list(_ZONE_FEATURES.values())

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

    for col in z_cols:
        if col in tw_df.columns:
            tw_df[col] = tw_df.apply(lambda r, c=col: _apply_shrinkage(r, c), axis=1)

    # Step 6d: Composite RMS of 3 zone z-scores (paint_dwell excluded by design)
    def _rms_composite(row):
        vals = []
        for dim in _RMS_DIMS:
            v = row.get(dim, np.nan)
            if not pd.isna(v):
                vals.append(v)
        if len(vals) == 0:
            return np.nan
        return float(np.sqrt(np.mean(np.square(vals))))

    tw_df["opp_shot_mix_deviation_z"] = tw_df.apply(_rms_composite, axis=1)

    # Step 6e: Data density label (same thresholds as C3)
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

    # Step 6f: Season from game_date
    def _season(d):
        y, m = d.year, d.month
        if m >= 10:
            return f"{y}-{str(y+1)[-2:]}"
        else:
            return f"{y-1}-{str(y)[-2:]}"

    tw_df["season"] = tw_df["game_date"].map(_season)
    tw_df["game_date"] = tw_df["game_date"].dt.strftime("%Y-%m-%d")

    # Select output columns
    keep_cols = [
        "team_id", "season", "game_date", "n_games_window",
        "opp_paint_pct_allowed_z",
        "opp_3pt_pct_allowed_z",
        "opp_mid_pct_allowed_z",
        "opp_paint_dwell_pct_allowed_z",
        "opp_shot_mix_deviation_z",
        "data_density",
    ]
    for col in keep_cols:
        if col not in tw_df.columns:
            tw_df[col] = np.nan

    return tw_df[keep_cols].sort_values(["team_id", "game_date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 7: Orthogonality gate vs C3
# ---------------------------------------------------------------------------

def _orthogonality_gate(result: pd.DataFrame) -> dict:
    """
    Correlate opp_shot_mix_deviation_z and opp_paint_pct_allowed_z vs
    C3's opp_defensive_intensity_z. Gate: |r| < 0.5 = SHIP, 0.5-0.7 = YELLOW, >0.7 = REJECT.
    """
    findings = {}

    if not C3_PARQUET.exists():
        print("  [warn] C3 parquet not found; orthogonality gate skipped")
        findings["c3_available"] = False
        findings["r_composite"] = None
        findings["r_paint"] = None
        findings["verdict"] = "SHIP (C3 unavailable; gate skipped)"
        return findings

    c3 = pd.read_parquet(C3_PARQUET)
    c3_cols = ["team_id", "game_date", "opp_defensive_intensity_z"]
    if not all(c in c3.columns for c in c3_cols):
        print("  [warn] C3 parquet missing expected columns; gate skipped")
        findings["c3_available"] = False
        findings["r_composite"] = None
        findings["r_paint"] = None
        findings["verdict"] = "SHIP (C3 schema mismatch; gate skipped)"
        return findings

    merged = result.merge(
        c3[c3_cols],
        on=["team_id", "game_date"],
        how="inner",
    )
    print(f"  Orthogonality gate: {len(merged)} matched rows for correlation")

    if len(merged) < 5:
        print("  [warn] Too few matched rows for meaningful correlation")
        findings["c3_available"] = True
        findings["r_composite"] = None
        findings["r_paint"] = None
        findings["verdict"] = "SHIP (too few overlap rows; gate inconclusive)"
        return findings

    r_composite = float(merged["opp_shot_mix_deviation_z"].corr(
        merged["opp_defensive_intensity_z"]
    ))
    r_paint = float(merged["opp_paint_pct_allowed_z"].corr(
        merged["opp_defensive_intensity_z"]
    ))

    findings["c3_available"] = True
    findings["r_composite"] = r_composite
    findings["r_paint"] = r_paint
    findings["n_overlap"] = len(merged)

    abs_rc = abs(r_composite)
    print(f"  r_composite vs C3 = {r_composite:+.4f}")
    print(f"  r_paint vs C3     = {r_paint:+.4f}")

    if abs_rc > _CORR_REJECT:
        findings["orthogonality_verdict"] = f"REJECT: |r_composite|={abs_rc:.3f} > {_CORR_REJECT}"
        print(f"  REJECT: |r| > {_CORR_REJECT} — C3 already covers this signal")
    elif abs_rc > _CORR_YELLOW:
        findings["orthogonality_verdict"] = f"SHIP YELLOW: |r_composite|={abs_rc:.3f} in ({_CORR_YELLOW},{_CORR_REJECT})"
        print(f"  SHIP YELLOW: |r| in ({_CORR_YELLOW},{_CORR_REJECT}) — document overlap")
    else:
        findings["orthogonality_verdict"] = f"SHIP: |r_composite|={abs_rc:.3f} < {_CORR_YELLOW}"
        print(f"  SHIP: |r| < {_CORR_YELLOW} — orthogonal to C3")

    return findings


# ---------------------------------------------------------------------------
# Step 8: Sanity checks
# ---------------------------------------------------------------------------

def _sanity_check(result: pd.DataFrame) -> dict:
    """
    Compute sanity metrics:
    - Top/bottom-10 by opp_paint_pct_allowed_z (team-level mean)
    - Per-zone z std (gate: >= 0.3)
    - Density distribution
    Returns dict with findings.
    """
    findings = {}

    # Team-level aggregate by opp_paint_pct_allowed_z
    team_agg = (
        result.groupby("team_id")[["opp_paint_pct_allowed_z", "opp_3pt_pct_allowed_z",
                                    "opp_mid_pct_allowed_z", "opp_paint_dwell_pct_allowed_z",
                                    "opp_shot_mix_deviation_z"]]
        .agg(["mean", "std", "count"])
    )
    # Flatten multi-index
    team_agg.columns = ["_".join(c) for c in team_agg.columns]
    team_agg = team_agg.sort_values("opp_paint_pct_allowed_z_mean", ascending=False)

    findings["top_10_paint"] = team_agg.head(10).reset_index().to_dict("records")
    findings["bottom_10_paint"] = team_agg.tail(10).reset_index().to_dict("records")

    print("\n  Top-10 teams most permissive to paint shots (opp_paint_pct_allowed_z mean):")
    for i, row in enumerate(findings["top_10_paint"][:10]):
        print(f"    {i+1:2d}. {row['team_id']:4s}  "
              f"paint_z={row['opp_paint_pct_allowed_z_mean']:+.3f}  "
              f"n={int(row['opp_paint_pct_allowed_z_count'])}")

    print("\n  Bottom-10 teams (fewest paint shots allowed):")
    for i, row in enumerate(findings["bottom_10_paint"][:10]):
        print(f"    {i+1:2d}. {row['team_id']:4s}  "
              f"paint_z={row['opp_paint_pct_allowed_z_mean']:+.3f}  "
              f"n={int(row['opp_paint_pct_allowed_z_count'])}")

    # Per-zone z-score std (ship gate)
    z_cols = ["opp_paint_pct_allowed_z", "opp_3pt_pct_allowed_z",
              "opp_mid_pct_allowed_z", "opp_paint_dwell_pct_allowed_z",
              "opp_shot_mix_deviation_z"]
    z_stds = {}
    print("\n  Per-zone z-score std (gate >= 0.3):")
    all_above_floor = True
    for col in z_cols:
        if col in result.columns:
            std = float(result[col].std())
            z_stds[col] = std
            status = "OK" if std >= _MIN_Z_STD else "BELOW FLOOR"
            if std < _MIN_Z_STD and col != "opp_shot_mix_deviation_z":
                all_above_floor = False
            print(f"    {col}: std={std:.4f} [{status}]")
    findings["z_stds"] = z_stds
    findings["z_std_gate_pass"] = all_above_floor

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
          f"({'OK' if density_flag else 'FLAG: low_confidence'})")

    # Zone row counts (coverage transparency)
    for feat, z_col in _ZONE_FEATURES.items():
        nonzero = (result[z_col].notna() & (result[z_col] != 0)).sum()
        total = result[z_col].notna().sum()
        findings[f"{z_col}_nonzero"] = int(nonzero)
        findings[f"{z_col}_total_nonnan"] = int(total)

    return findings


# ---------------------------------------------------------------------------
# Public reader API: walk-forward safe
# ---------------------------------------------------------------------------

def get_opp_paint_allowance(
    opp_team: str,
    game_date: str,
    parquet_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Fetch the most recent allowance row for opp_team with game_date STRICTLY
    less than the given game_date. Walk-forward safe.

    Args:
        opp_team: team tricode (e.g. "CHA")
        game_date: ISO date string "YYYY-MM-DD"
        parquet_path: override path to opp_paint_allowance.parquet

    Returns:
        dict with all allowance columns, or None if no prior data exists.
    """
    if parquet_path is None:
        parquet_path = OUT_PARQUET
    if not Path(parquet_path).exists():
        return None

    df = pd.read_parquet(parquet_path)
    subset = df[(df["team_id"] == opp_team.upper()) & (df["game_date"] < game_date)]
    if subset.empty:
        return None
    return subset.sort_values("game_date").iloc[-1].to_dict()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="INT-58: Build opponent paint allowance atlas (rolling z-scored zone allocation)."
    )
    ap.add_argument("--window", type=int, default=5, help="Rolling window (default: 5 games)")
    ap.add_argument("--report-only", action="store_true", help="Skip write; print stats only")
    args = ap.parse_args()

    print("\n=== INT-58 Opponent Paint Allowance Atlas ===")

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
    print(f"  Game-level (defensive_team x game): {len(game_level)} rows, "
          f"{game_level['defensive_team'].nunique()} teams")

    # Rolling zone allowance
    print(f"\n--- Rolling allowance (window={args.window}) ---")
    result = _compute_rolling_allowance(game_level, window=args.window)

    if result.empty:
        print("ERROR: No output produced. Check data inputs.")
        sys.exit(1)

    print(f"  Output rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")

    # Sanity checks
    print("\n--- Sanity checks ---")
    sanity = _sanity_check(result)

    # Orthogonality gate vs C3
    print("\n--- Orthogonality gate vs C3 ---")
    orth = _orthogonality_gate(result)

    # Derive overall ship verdict
    z_std_ok = sanity.get("z_std_gate_pass", False)
    density_ok = sanity.get("density_gate_pass", False)
    orth_verdict = orth.get("orthogonality_verdict", "")

    print("\n--- Ship verdict ---")
    if "REJECT" in orth_verdict:
        final_verdict = "REJECT"
        print(f"  REJECT: orthogonality gate failed — {orth_verdict}")
    else:
        flags = []
        if not z_std_ok:
            flags.append("z_std below floor on >=1 dim")
        if not density_ok:
            flags.append(f"low_confidence: med-or-better={sanity.get('med_or_better_pct')}%")
        if "YELLOW" in orth_verdict:
            flags.append(f"C3 overlap: {orth_verdict}")

        if flags:
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
    print("\n=== INT-58 COMPLETE ===")
    print(f"  Rows: {len(result)}")
    print(f"  Teams: {result['team_id'].nunique()}")
    print(f"  Date range: {result['game_date'].min()} -> {result['game_date'].max()}")
    print(f"  Density (med+): {sanity.get('med_or_better_pct')}%")
    r_comp = orth.get("r_composite")
    r_paint = orth.get("r_paint")
    if r_comp is not None:
        print(f"  r_composite vs C3: {r_comp:+.4f}")
    if r_paint is not None:
        print(f"  r_paint vs C3:     {r_paint:+.4f}")
    print(f"  Verdict: {final_verdict}")

    return result, sanity, orth


if __name__ == "__main__":
    main()
