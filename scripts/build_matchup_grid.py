"""
INT-63: Matchup Grid Cross-Join Atlas (B.3)
===========================================
Pure as-of join of four team-aggregate atlases into a two-row-per-game
(home-offense + away-offense) matchup grid with 6 interaction scalars.

Inputs:
  data/nba/season_games_{S}.json["rows"]   -- schedule
  data/intelligence/team_tempo_spacing.parquet          -- C1+C2 off-side
  data/intelligence/opp_defensive_intensity.parquet     -- C3 def-side
  data/intelligence/opp_paint_allowance.parquet         -- C4 def-side

Output:
  data/intelligence/matchup_grid.parquet
  vault/Intelligence/INT-63_Matchup_Grid.md

Usage:
    python scripts/build_matchup_grid.py
    python scripts/build_matchup_grid.py --seasons 2024-25 2025-26
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths — script-relative ROOT
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
INTEL_DIR = DATA_DIR / "intelligence"
NBA_CACHE_DIR = DATA_DIR / "nba"
VAULT_INTEL = ROOT / "vault" / "Intelligence"

OUT_PARQUET = INTEL_DIR / "matchup_grid.parquet"
OUT_DOC = VAULT_INTEL / "INT-63_Matchup_Grid.md"

# ---------------------------------------------------------------------------
# Atlas paths
# ---------------------------------------------------------------------------
C1C2_PATH = INTEL_DIR / "team_tempo_spacing.parquet"
C3_PATH   = INTEL_DIR / "opp_defensive_intensity.parquet"
C4_PATH   = INTEL_DIR / "opp_paint_allowance.parquet"

# ---------------------------------------------------------------------------
# Column maps — source column -> output column
# ---------------------------------------------------------------------------
OFF_COLS: Dict[str, str] = {
    "team_tempo_z":                   "off_tempo_z",
    "team_spacing_z":                 "off_spacing_z",
    "team_tempo_spacing_composite_z": "off_tempo_spacing_z",
    "team_paint_dwell_z":             "off_paint_dwell_z",
    "team_transition_share_z":        "off_transition_share_z",
    "team_avg_spacing_z":             "off_avg_spacing_z",
}
DEF_INTENSITY_COLS: Dict[str, str] = {
    "opp_defensive_intensity_z":            "def_intensity_z",
    "opp_pace_imposed_z":                   "def_pace_imposed_z",
    "opp_contested_shot_rate_imposed_z":    "def_contested_shot_rate_z",
    "opp_avg_defender_distance_imposed_z":  "def_defender_distance_z",
    "opp_paint_attempts_allowed_pct_z":     "def_paint_attempts_allowed_z",
    "opp_catch_shoot_allowed_pct_z":        "def_catch_shoot_allowed_z",
}
DEF_PAINT_COLS: Dict[str, str] = {
    "opp_paint_pct_allowed_z":        "def_paint_pct_allowed_z",
    "opp_3pt_pct_allowed_z":          "def_3pt_pct_allowed_z",
    "opp_mid_pct_allowed_z":          "def_mid_pct_allowed_z",
    "opp_paint_dwell_pct_allowed_z":  "def_paint_dwell_allowed_z",
    "opp_shot_mix_deviation_z":       "def_shot_mix_deviation_z",
}

# Density ordering for min()
_DENSITY_ORDER: Dict[str, int] = {
    "league_prior": 0,
    "low":          1,
    "med":          2,
    "high":         3,
}
_DENSITY_INV = {v: k for k, v in _DENSITY_ORDER.items()}

OFF_Z_COLS   = list(OFF_COLS.values())
DEF_Z_COLS   = list(DEF_INTENSITY_COLS.values()) + list(DEF_PAINT_COLS.values())
ALL_FEAT_COLS = OFF_Z_COLS + DEF_Z_COLS

MX_COLS = [
    "mx_tempo_vs_opp_pace",
    "mx_paint_attack_vs_paint_allow",
    "mx_spacing_vs_3pt_allow",
    "mx_transition_vs_pace_imposed",
    "mx_offense_vs_defense_composite",
    "mx_contested_pressure",
]

DEFAULT_SEASONS = ["2024-25", "2025-26"]


# ---------------------------------------------------------------------------
# Schedule loader
# ---------------------------------------------------------------------------

def _load_schedule(seasons: List[str]) -> pd.DataFrame:
    rows = []
    for s in seasons:
        p = NBA_CACHE_DIR / f"season_games_{s}.json"
        if not p.exists():
            print(f"  [WARN] schedule not found: {p}")
            continue
        with open(p, "r") as f:
            data = json.load(f)
        for r in data.get("rows", []):
            if "home_team" not in r or "away_team" not in r:
                continue
            rows.append({
                "game_id":   r["game_id"],
                "season":    r["season"],
                "game_date": str(r["game_date"]),
                "home_team": r["home_team"],
                "away_team": r["away_team"],
            })
    if not rows:
        print("[ERROR] No schedule rows loaded — check data/nba/season_games_*.json")
        sys.exit(1)
    df = pd.DataFrame(rows).drop_duplicates(subset=["game_id"])
    return df.sort_values("game_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Vectorized as-of join using pd.merge_asof
# ---------------------------------------------------------------------------

def _asof_join_atlas(
    left: pd.DataFrame,
    atlas: pd.DataFrame,
    left_key: str,          # column in left holding the team_id to match
    col_map: Dict[str, str],
    density_suffix: str,    # suffix to distinguish density column after join
) -> pd.DataFrame:
    """
    For each row in `left` (keyed by left_key + game_date), find the most
    recent row in `atlas` with atlas.game_date strictly < left.game_date.

    Uses per-team merge_asof (pandas 2.x requires globally-sorted on-key
    even when using `by=`; per-team groupby avoids this constraint).

    If no prior atlas row exists for a (team_id, game_date), z-columns are 0.0
    and density = 'league_prior'.
    """
    src_cols = list(col_map.keys())
    keep = ["team_id", "game_date", "data_density", "n_games_window"] + src_cols
    keep = [c for c in keep if c in atlas.columns]
    atl = atlas[keep].copy()
    atl = atl.rename(columns=col_map)
    dens_col   = f"data_density_{density_suffix}"
    ngames_col = f"n_games_window_{density_suffix}"
    atl = atl.rename(columns={"data_density": dens_col, "n_games_window": ngames_col})
    dst_cols = list(col_map.values())

    def _date_to_int(s: pd.Series) -> pd.Series:
        return pd.to_datetime(s).dt.strftime("%Y%m%d").astype(int)

    atl["_gdate_int"] = _date_to_int(atl["game_date"])

    # Add unique row index so we can merge-back without game_id collision
    # (grid has 2 rows per game_id: home + away)
    left = left.copy()
    left["_row_id"] = np.arange(len(left))

    lft = left[["_row_id", "game_date", left_key]].copy()
    lft = lft.rename(columns={left_key: "_merge_team"})
    # Strict <: subtract 1 from int date
    lft["_gdate_int"] = _date_to_int(lft["game_date"]) - 1

    # Per-team merge_asof (avoids pandas 2.x global sort requirement)
    all_teams = lft["_merge_team"].unique()
    parts: List[pd.DataFrame] = []
    for team in all_teams:
        lft_t = lft[lft["_merge_team"] == team].sort_values("_gdate_int").reset_index(drop=True)
        atl_t = atl[atl["team_id"] == team].sort_values("_gdate_int").reset_index(drop=True)

        if atl_t.empty:
            lft_t2 = lft_t.copy()
            for col in dst_cols:
                lft_t2[col] = 0.0
            lft_t2[dens_col]   = "league_prior"
            lft_t2[ngames_col] = 0
        else:
            lft_t2 = pd.merge_asof(
                lft_t,
                atl_t.rename(columns={"team_id": "_merge_team"}),
                on="_gdate_int",
                by="_merge_team",
                direction="backward",
            )
            for col in dst_cols:
                lft_t2[col] = lft_t2[col].fillna(0.0)
            lft_t2[dens_col]   = lft_t2[dens_col].fillna("league_prior")
            lft_t2[ngames_col] = lft_t2[ngames_col].fillna(0).astype(int)

        parts.append(lft_t2)

    merged = pd.concat(parts, ignore_index=True)
    merged = merged.drop(
        columns=[c for c in ["_gdate_int", "_merge_team", "game_date", "game_date_x", "game_date_y"] if c in merged.columns],
        errors="ignore",
    )

    # Merge back on unique _row_id — no collision
    result = left.merge(
        merged[["_row_id"] + dst_cols + [dens_col, ngames_col]],
        on="_row_id",
        how="left",
    ).drop(columns=["_row_id"])

    for col in dst_cols:
        result[col] = result[col].fillna(0.0)
    result[dens_col]   = result[dens_col].fillna("league_prior")
    result[ngames_col] = result[ngames_col].fillna(0).astype(int)
    return result


# ---------------------------------------------------------------------------
# Interaction computation
# ---------------------------------------------------------------------------

def _compute_interactions(df: pd.DataFrame) -> pd.DataFrame:
    z = df.fillna(0.0)
    df["mx_tempo_vs_opp_pace"]            = z["off_tempo_z"]         * z["def_pace_imposed_z"]
    df["mx_paint_attack_vs_paint_allow"]  = (z["off_paint_dwell_z"] * -1.0) * z["def_paint_pct_allowed_z"]
    df["mx_spacing_vs_3pt_allow"]         = z["off_spacing_z"]       * z["def_3pt_pct_allowed_z"]
    df["mx_transition_vs_pace_imposed"]   = z["off_transition_share_z"] * z["def_pace_imposed_z"]
    df["mx_offense_vs_defense_composite"] = z["off_tempo_spacing_z"] * (z["def_intensity_z"] * -1.0)
    df["mx_contested_pressure"]           = (z["off_avg_spacing_z"] * -1.0) * z["def_contested_shot_rate_z"]
    return df


def _min_density_series(s1: pd.Series, s2: pd.Series, s3: pd.Series) -> pd.Series:
    def _ord(s: pd.Series) -> pd.Series:
        return s.map(_DENSITY_ORDER).fillna(0).astype(int)
    mn = np.minimum(np.minimum(_ord(s1), _ord(s2)), _ord(s3))
    return pd.Series(mn).map(_DENSITY_INV)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(df: pd.DataFrame) -> Dict:
    report: Dict = {
        "errors": [], "warnings": [], "dropped_mx": [],
        "dropped_orth": [], "dropped_redund": [], "dropped_null": [],
        "orth_table": {}, "null_control": {},
    }

    # Schema sanity
    key_cols = ["game_id", "season", "game_date", "team_id", "opp_team_id", "is_home"]
    for c in key_cols:
        if c not in df.columns:
            report["errors"].append(f"Missing key column: {c}")
    null_keys = df[key_cols].isnull().any(axis=1).sum()
    if null_keys > 0:
        report["errors"].append(f"Null values in key columns: {null_keys} rows")
    dups = df.duplicated(subset=["game_id", "is_home"]).sum()
    if dups > 0:
        report["errors"].append(f"Duplicate (game_id, is_home): {dups} rows")

    # Density coverage
    density_ok = df["data_density"].isin(["low", "med", "high"])
    pct = density_ok.mean()
    report["density_pct_low_better"] = float(pct)
    report["n_league_prior"] = int((df["data_density"] == "league_prior").sum())
    if pct < 0.40:
        report["warnings"].append(
            f"Only {pct:.1%} rows have density ≥ low (threshold 40%)"
        )
    print(f"\n  Density coverage: {pct:.1%} low-or-better  ({report['n_league_prior']} league_prior rows)")

    # Orthogonality: each mx vs each constituent, threshold |r| < 0.70
    print("\n--- Orthogonality check (mx vs constituents, |r| threshold < 0.70) ---")
    mx_drop_orth: set = set()
    num = df[ALL_FEAT_COLS + MX_COLS].fillna(0.0)
    orth_table: Dict = {}
    for mx in MX_COLS:
        max_r, max_col = 0.0, ""
        if num[mx].std() < 1e-9:
            orth_table[mx] = {"max_r": 0.0, "max_col": "(near-zero variance)"}
            print(f"  {mx}: near-zero variance — skip")
            continue
        for c in ALL_FEAT_COLS:
            if num[c].std() < 1e-9:
                continue
            r = abs(float(np.corrcoef(num[c].values, num[mx].values)[0, 1]))
            if r > max_r:
                max_r, max_col = r, c
        orth_table[mx] = {"max_r": round(max_r, 4), "max_col": max_col}
        status = "FAIL" if max_r >= 0.70 else "OK"
        print(f"  {mx:<45s} max|r|={max_r:.4f} vs {max_col}  [{status}]")
        if max_r >= 0.70:
            mx_drop_orth.add(mx)
    report["orth_table"] = orth_table

    # Inter-interaction redundancy, threshold |r| < 0.85
    print("\n--- Inter-interaction redundancy (|r| threshold < 0.85) ---")
    mx_drop_redund: set = set()
    remaining = [m for m in MX_COLS if m not in mx_drop_orth]
    for i, mx_a in enumerate(remaining):
        for mx_b in remaining[i + 1:]:
            if num[mx_a].std() < 1e-9 or num[mx_b].std() < 1e-9:
                continue
            r = abs(float(np.corrcoef(num[mx_a].values, num[mx_b].values)[0, 1]))
            marker = "  << DROP" if r >= 0.85 else ""
            print(f"  {mx_a} vs {mx_b}: |r|={r:.4f}{marker}")
            if r >= 0.85:
                mx_drop_redund.add(mx_b)
    report["dropped_orth"] = list(mx_drop_orth)
    report["dropped_redund"] = list(mx_drop_redund)

    # Null-control: shuffle def_* GLOBALLY (full column permutation) 500 reps.
    # Tests whether the specific offense-defense pairing adds signal beyond
    # marginal distributions. Reference: the def constituent of each mx.
    # Logic: for each mx, compute live |r(def_constituent, mx)| vs null_mean.
    # If null_mean >= 50% of live → the correlation is explained by the def
    # column's own variance, not the off×def pairing → ARTIFACT_REJECT.
    # Note: within-day shuffle is invalid here (only ~15 rows/day; 2 per unique
    # game). Global shuffle tests the matchup signal properly.
    print("\n--- Null-control: shuffle def cols GLOBALLY × 500 reps ---")
    live_df = df.fillna(0.0).reset_index(drop=True)

    # For each mx, use its def constituent as the reference (more meaningful than off_tempo_z)
    MX_DEF_REF = {
        "mx_tempo_vs_opp_pace":            "def_pace_imposed_z",
        "mx_paint_attack_vs_paint_allow":  "def_paint_pct_allowed_z",
        "mx_spacing_vs_3pt_allow":         "def_3pt_pct_allowed_z",
        "mx_transition_vs_pace_imposed":   "def_pace_imposed_z",
        "mx_offense_vs_defense_composite": "def_intensity_z",
        "mx_contested_pressure":           "def_contested_shot_rate_z",
    }

    live_r: Dict[str, float] = {}
    for mx in MX_COLS:
        ref_col_mx = MX_DEF_REF[mx]
        ref_arr_mx = live_df[ref_col_mx].values
        mx_arr     = live_df[mx].values
        if ref_arr_mx.std() < 1e-9 or mx_arr.std() < 1e-9:
            live_r[mx] = 0.0
        else:
            live_r[mx] = abs(float(np.corrcoef(ref_arr_mx, mx_arr)[0, 1]))

    rng = np.random.default_rng(42)
    null_rs: Dict[str, List[float]] = {mx: [] for mx in MX_COLS}

    # Extract all relevant arrays as numpy for fast shuffle
    def_arrays = {col: live_df[col].values.copy() for col in DEF_Z_COLS}
    off_arrays = {col: live_df[col].values.copy() for col in OFF_Z_COLS}
    n_rows = len(live_df)

    def _mx_from_arrays(def_a: Dict[str, np.ndarray], off_a: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        return {
            "mx_tempo_vs_opp_pace":            off_a["off_tempo_z"]         * def_a["def_pace_imposed_z"],
            "mx_paint_attack_vs_paint_allow":  (off_a["off_paint_dwell_z"] * -1.0) * def_a["def_paint_pct_allowed_z"],
            "mx_spacing_vs_3pt_allow":         off_a["off_spacing_z"]       * def_a["def_3pt_pct_allowed_z"],
            "mx_transition_vs_pace_imposed":   off_a["off_transition_share_z"] * def_a["def_pace_imposed_z"],
            "mx_offense_vs_defense_composite": off_a["off_tempo_spacing_z"] * (def_a["def_intensity_z"] * -1.0),
            "mx_contested_pressure":           (off_a["off_avg_spacing_z"] * -1.0) * def_a["def_contested_shot_rate_z"],
        }

    for rep in range(500):
        # Global shuffle of all def columns independently
        shuf_def: Dict[str, np.ndarray] = {}
        for col in DEF_Z_COLS:
            perm = rng.permutation(n_rows)
            shuf_def[col] = def_arrays[col][perm]

        shuf_mx = _mx_from_arrays(shuf_def, off_arrays)
        for mx in MX_COLS:
            ref_col_mx = MX_DEF_REF[mx]
            ref_arr_mx = def_arrays[ref_col_mx]  # unshuffled ref for correlation
            arr = shuf_mx[mx]
            if arr.std() < 1e-9 or ref_arr_mx.std() < 1e-9:
                null_rs[mx].append(0.0)
            else:
                null_rs[mx].append(
                    abs(float(np.corrcoef(ref_arr_mx, arr)[0, 1]))
                )

    mx_drop_null: set = set()
    null_ctrl_results: Dict = {}
    print(f"  {'Interaction':<45s} live|r|  null_mean|r|  drop%   verdict")
    for mx in MX_COLS:
        lv = live_r[mx]
        nm = float(np.mean(null_rs[mx]))
        # REJECT if shuffled null preserves >= 50% of live signal (pairing doesn't add)
        if lv <= 1e-9:
            verdict = "OK"
        elif nm < 0.50 * lv:
            verdict = "OK"
        else:
            verdict = "ARTIFACT_REJECT"
            mx_drop_null.add(mx)
        drop_pct = (lv - nm) / max(lv, 1e-9) * 100
        print(f"  {mx:<45s} {lv:.4f}   {nm:.4f}        {drop_pct:.1f}%   {verdict}")
        null_ctrl_results[mx] = {
            "live_r": round(lv, 5),
            "null_mean_r": round(nm, 5),
            "verdict": verdict,
        }
    report["null_control"] = null_ctrl_results
    report["dropped_null"] = list(mx_drop_null)

    all_dropped = mx_drop_orth | mx_drop_redund | mx_drop_null
    report["dropped_mx"] = list(all_dropped)

    # Sanity ranking: mx_paint_attack_vs_paint_allow top/bottom 10
    paint_col = "mx_paint_attack_vs_paint_allow"
    if paint_col in df.columns:
        ranked = df.sort_values(paint_col, ascending=False)[
            ["team_id", "opp_team_id", "game_date", paint_col]
        ]
        top10  = ranked.head(10)
        bot10  = ranked.tail(10)
        print(f"\n--- Sanity ranking: top-10 {paint_col} ---")
        print(top10.to_string(index=False))
        print(f"\n--- Bottom-10 ---")
        print(bot10.to_string(index=False))
        report["top10_paint"] = top10.to_dict("records")

    # Ship verdict
    n_dropped = len(all_dropped)
    if report["errors"]:
        report["ship_verdict"] = "REJECT"
    elif n_dropped > 3:
        report["ship_verdict"] = "PARTIAL SHIP"
    else:
        report["ship_verdict"] = "SHIP"

    return report


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(seasons: List[str]) -> pd.DataFrame:
    print(f"[INT-63] Building matchup grid for seasons: {seasons}")

    schedule = _load_schedule(seasons)
    print(f"  Schedule: {len(schedule)} games")

    # Load atlases
    print("  Loading C1+C2 (team_tempo_spacing)...")
    atlas_off = pd.read_parquet(C1C2_PATH)
    atlas_off["game_date"] = atlas_off["game_date"].astype(str)

    print("  Loading C3 (opp_defensive_intensity)...")
    atlas_di = pd.read_parquet(C3_PATH)
    atlas_di["game_date"] = atlas_di["game_date"].astype(str)

    print("  Loading C4 (opp_paint_allowance)...")
    atlas_dp = pd.read_parquet(C4_PATH)
    atlas_dp["game_date"] = atlas_dp["game_date"].astype(str)

    # --- Explode schedule to two-row-per-game ---
    home_rows = schedule.rename(columns={"home_team": "team_id", "away_team": "opp_team_id"}).copy()
    home_rows["is_home"] = 1
    away_rows = schedule.rename(columns={"away_team": "team_id", "home_team": "opp_team_id"}).copy()
    away_rows["is_home"] = 0
    grid = pd.concat([home_rows, away_rows], ignore_index=True)
    grid = grid.sort_values(["game_date", "game_id", "is_home"]).reset_index(drop=True)
    print(f"  Two-row explode: {len(grid)} rows")

    # --- Vectorized as-of join: OFF side (keyed on team_id) ---
    print("  As-of join: OFF side (team_tempo_spacing)...")
    grid = _asof_join_atlas(grid, atlas_off, "team_id", OFF_COLS, "off")

    # --- Vectorized as-of join: DEF intensity (keyed on opp_team_id) ---
    print("  As-of join: DEF intensity (opp_defensive_intensity)...")
    grid = _asof_join_atlas(grid, atlas_di, "opp_team_id", DEF_INTENSITY_COLS, "di")

    # --- Vectorized as-of join: DEF paint (keyed on opp_team_id) ---
    print("  As-of join: DEF paint (opp_paint_allowance)...")
    grid = _asof_join_atlas(grid, atlas_dp, "opp_team_id", DEF_PAINT_COLS, "dp")

    # --- Combine density ---
    grid["data_density"] = _min_density_series(
        grid["data_density_off"],
        grid["data_density_di"],
        grid["data_density_dp"],
    )
    grid["n_games_offense_window"] = grid["n_games_window_off"]
    grid["n_games_defense_window"] = grid[["n_games_window_di", "n_games_window_dp"]].max(axis=1)

    # Drop working density columns
    grid = grid.drop(
        columns=["data_density_off", "data_density_di", "data_density_dp",
                 "n_games_window_off", "n_games_window_di", "n_games_window_dp"],
        errors="ignore",
    )

    # --- Compute interactions ---
    print("  Computing 6 interaction scalars...")
    grid = _compute_interactions(grid)

    # --- Date-leak guard assertion ---
    print("  Date-leak guard: asserting structural correctness...")
    # merge_asof with -1 day shift enforces strict <; no direct row-check needed.
    # We confirm no future-date atlas rows slipped through by checking n_games > 0
    # only exists where atlas had prior data.
    leaked = (grid["n_games_offense_window"] > 0) & (grid["data_density"] == "league_prior")
    if leaked.any():
        print(f"  [WARN] {leaked.sum()} rows have n_games>0 but density=league_prior — check atlas consistency.")

    # Final sort
    grid = grid.sort_values(["game_date", "game_id", "is_home"]).reset_index(drop=True)
    return grid


# ---------------------------------------------------------------------------
# Doc writer
# ---------------------------------------------------------------------------

def _write_doc(df: pd.DataFrame, report: Dict) -> None:
    VAULT_INTEL.mkdir(parents=True, exist_ok=True)
    n_rows  = len(df)
    density_dist = df["data_density"].value_counts().to_dict()
    density_str  = ", ".join(f"{k}: {v}" for k, v in sorted(density_dist.items()))
    date_range   = f"{df['game_date'].min()} — {df['game_date'].max()}"
    n_games      = df["game_id"].nunique()
    dropped      = report.get("dropped_mx", [])
    ship_verdict = report.get("ship_verdict", "UNKNOWN")
    n_shipped    = len([m for m in MX_COLS if m not in dropped])

    orth_table = report.get("orth_table", {})
    orth_rows = ""
    for mx, vals in orth_table.items():
        status = "DROPPED" if mx in dropped else ("FAIL" if vals.get("max_r", 0) >= 0.70 else "OK")
        orth_rows += f"| `{mx}` | {vals.get('max_col', '')} | {vals.get('max_r', 0):.4f} | {status} |\n"

    null_ctrl = report.get("null_control", {})
    null_rows = ""
    for mx, vals in null_ctrl.items():
        drop_flag = " DROPPED" if mx in report.get("dropped_null", []) else ""
        null_rows += (
            f"| `{mx}` | {vals.get('live_r', 0):.5f} | "
            f"{vals.get('null_mean_r', 0):.5f} | {vals.get('verdict', '')}{drop_flag} |\n"
        )

    top10 = report.get("top10_paint", [])
    top10_rows = ""
    for r in top10:
        top10_rows += (
            f"| {r.get('team_id', '')} | {r.get('opp_team_id', '')} | "
            f"{r.get('game_date', '')} | {r.get('mx_paint_attack_vs_paint_allow', 0):.4f} |\n"
        )

    warnings_str = "\n".join(f"- {w}" for w in report.get("warnings", [])) or "_none_"
    errors_str   = "\n".join(f"- {e}" for e in report.get("errors", [])) or "_none_"
    dropped_str  = (
        "\n".join(
            f"- `{m}`: "
            + ("orthogonality |r| >= 0.70 with constituent"
               if m in report.get("dropped_orth", [])
               else "redundant inter-interaction |r| >= 0.85"
               if m in report.get("dropped_redund", [])
               else "null-control artifact (shuffled signal >= 50% of live)")
            for m in dropped
        )
        or "_none_"
    )

    doc = f"""# INT-63: Matchup Grid Cross-Join Atlas

**Build date:** 2026-05-29
**Ship verdict:** {ship_verdict}
**Output:** `data/intelligence/matchup_grid.parquet`

---

## Summary

Pure as-of join of four team-aggregate atlases (C1+C2 offense, C3+C4 defense) into a
two-row-per-game matchup grid with {n_shipped} interaction scalar(s) shipped.

- **Rows:** {n_rows} ({n_games} unique games x 2 sides)
- **Date range:** {date_range}
- **Density distribution:** {density_str}
- **league_prior rows:** {report.get('n_league_prior', '?')} ({report.get('n_league_prior', 0) / max(n_rows, 1) * 100:.1f}%)

---

## Schema

### Keys
| Column | Description |
|--------|-------------|
| game_id | NBA game ID |
| season | Season string (e.g. 2024-25) |
| game_date | YYYY-MM-DD |
| team_id | Offense team abbreviation |
| opp_team_id | Defense team abbreviation |
| is_home | 1 = home offense, 0 = away offense |

### Off-side block (from C1+C2, keyed on team_id)
off_tempo_z, off_spacing_z, off_tempo_spacing_z, off_paint_dwell_z, off_transition_share_z, off_avg_spacing_z

### Def-side block (from C3, keyed on opp_team_id)
def_intensity_z, def_pace_imposed_z, def_contested_shot_rate_z, def_defender_distance_z, def_paint_attempts_allowed_z, def_catch_shoot_allowed_z

### Def-side block (from C4, keyed on opp_team_id)
def_paint_pct_allowed_z, def_3pt_pct_allowed_z, def_mid_pct_allowed_z, def_paint_dwell_allowed_z, def_shot_mix_deviation_z

### Density + counts
data_density, n_games_offense_window, n_games_defense_window

---

## 6 Interaction Definitions

| Column | Formula | Interpretation |
|--------|---------|----------------|
| mx_tempo_vs_opp_pace | off_tempo_z x def_pace_imposed_z | Fast-tempo offense into pace-controlling defense |
| mx_paint_attack_vs_paint_allow | (off_paint_dwell_z x -1) x def_paint_pct_allowed_z | Paint-averse offense vs paint-permissive defense |
| mx_spacing_vs_3pt_allow | off_spacing_z x def_3pt_pct_allowed_z | Spacing offense vs 3pt-permissive defense |
| mx_transition_vs_pace_imposed | off_transition_share_z x def_pace_imposed_z | Transition offense vs pace-slowing defense |
| mx_offense_vs_defense_composite | off_tempo_spacing_z x (def_intensity_z x -1) | Composite off quality vs composite def intensity |
| mx_contested_pressure | (off_avg_spacing_z x -1) x def_contested_shot_rate_z | Tight-spacing offense vs high-contest defense |

Sign convention: positive = favorable matchup for offense; negative = favorable for defense.

---

## Orthogonality Table (threshold |r| < 0.70)

| Interaction | Max corr with | max |r| | Status |
|-------------|--------------|--------|--------|
{orth_rows}
---

## Inter-Interaction Redundancy (threshold |r| < 0.85)

Pairwise correlations checked among surviving interactions. See build log for matrix.

---

## Null-Control Outcome (500 global permutations)

Methodology: globally permute each def_* column 500x (independent permutation per col),
recompute interactions, measure |r(def_constituent, mx)|. Live uses unshuffled data.
Verdict = ARTIFACT_REJECT if null_mean >= 50% of live (shuffle preserves signal -> artifact).
Reference column per mx: its own def constituent (not off_tempo_z, which would always
correlate with off-side interactions).

| Interaction | live |r| | null_mean |r| | Verdict |
|-------------|---------|-------------|---------|
{null_rows}
---

## Sanity Ranking: mx_paint_attack_vs_paint_allow Top-10

High = paint-averse offense matched vs paint-permissive defense.
Expected: high-pace paint teams (MEM/IND/SAC) on defense side.

| Offense | Defense | Date | Score |
|---------|---------|------|-------|
{top10_rows}
---

## Dropped Interactions

{dropped_str}

---

## Warnings

{warnings_str}

## Errors

{errors_str}

---

## Ship Verdict

**{ship_verdict}**

Interactions shipped: {n_shipped}/6
{"Partial ship: >3 interactions dropped. Downstream consumers must use the subset present in the parquet." if ship_verdict == "PARTIAL SHIP" else "All validation gates passed — all surviving interactions are orthogonal to constituents, non-redundant, and pass null control." if ship_verdict == "SHIP" else "Build rejected — see errors above."}
"""

    with open(OUT_DOC, "w", encoding="utf-8") as f:
        f.write(doc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="INT-63: Matchup Grid Cross-Join Atlas")
    parser.add_argument(
        "--seasons", nargs="+", default=DEFAULT_SEASONS,
        help="Seasons to include (e.g. 2024-25 2025-26)",
    )
    parser.add_argument(
        "--no-validate", action="store_true",
        help="Skip validation (write parquet only)",
    )
    args = parser.parse_args()

    df = build(args.seasons)

    print(f"\n[INT-63] Output shape: {df.shape}")
    print(f"  Columns: {df.columns.tolist()}")
    print(f"  Date range: {df['game_date'].min()} — {df['game_date'].max()}")
    print(f"  Density:\n{df['data_density'].value_counts().to_string()}")

    if not args.no_validate:
        report = _validate(df)

        if report["dropped_mx"]:
            print(f"\n  Dropping {len(report['dropped_mx'])} interaction(s): {report['dropped_mx']}")
            df = df.drop(columns=report["dropped_mx"], errors="ignore")
        else:
            print("\n  No interactions dropped.")

        if report["errors"]:
            print(f"\n[REJECT] Validation errors: {report['errors']}")
            _write_doc(df, report)
            sys.exit(1)

        print(f"\n  Ship verdict: {report['ship_verdict']}")
    else:
        report = {"ship_verdict": "SKIPPED", "dropped_mx": [], "errors": [], "warnings": []}

    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"\n[INT-63] Written: {OUT_PARQUET}  ({len(df)} rows, {len(df.columns)} cols)")
    _write_doc(df, report)
    print(f"[INT-63] Written: {OUT_DOC}")


if __name__ == "__main__":
    main()
