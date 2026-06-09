"""
INT-66: Opponent-Normalized CV Profile (B2)
============================================
Z-scores both player CV signals and opp-imposed atlas signals separately,
then subtracts to produce residuals:
  residual > 0 => player exceeded opp baseline
  residual < 0 => player was suppressed below opp baseline

Dimensions:
  paint_dwell_pct        x  opp_paint_pct_allowed_z      => paint_dwell_norm
  avg_defender_distance  x  opp_avg_defender_distance_z  => defender_dist_norm
  contested_shot_rate    x  opp_contested_shot_rate_z    => contested_norm

Output schema (per player_id, game_date, game_id):
  paint_dwell_norm_l5, defender_dist_norm_l5, contested_norm_l5,
  paint_dwell_raw_l5, defender_dist_raw_l5, contested_raw_l5,
  opp_join_density, n_cv_prior

Both validation gates run inline:
  Gate 1: corr(norm_l5, raw_l5) < 0.90
  Gate 2: delta_real / delta_null in [0.85, 1.15] => REJECT

ROOT = Path(__file__).resolve().parent.parent  (script-relative, no hardcoded paths)
"""
from __future__ import annotations

import glob
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths — script-relative ROOT
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
NBA_CACHE_DIR = DATA_DIR / "nba"
DB_PATH = DATA_DIR / "nba_ai.db"
PAINT_ATLAS = DATA_DIR / "intelligence" / "opp_paint_allowance.parquet"
DEF_ATLAS = DATA_DIR / "intelligence" / "opp_defensive_intensity.parquet"
OUT_PARQUET = DATA_DIR / "intelligence" / "opp_normalized_cv.parquet"
VAULT_DOC = ROOT / "vault" / "Intelligence" / "INT-66_Opp_Normalized_CV.md"

# Bug 22 sentinel: defender_distance >= 50.0 is 200.0 artifact — exclude
_DEFENDER_DIST_MAX = 50.0

# Rolling window for priors
_L5_WINDOW = 5
_L5_MIN_PERIODS = 2

# ---------------------------------------------------------------------------
# Step 1: Load game_id -> {date, home_team, away_team}
# ---------------------------------------------------------------------------

def _load_game_info_map() -> Dict[str, dict]:
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
# Step 2: Load player_id -> team_abbrev
# ---------------------------------------------------------------------------

def _load_player_team_map() -> Dict[int, str]:
    pid_to_team: Dict[int, str] = {}
    for fname in ["player_full_2025-26.json", "player_full_2024-25.json",
                  "player_full_2023-24.json"]:
        fpath = NBA_CACHE_DIR / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [warn] {fpath}: {e}")
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
# Step 3: Load boxscore JSON for home/away rosters (memoized)
# Two formats:
#   old: {home_team, away_team, players: [{player_id, team_abbreviation}]}
#   new: {teams: [{team_id, team_abbreviation}], players: [{player_id, team_id, team_abbreviation}]}
# ---------------------------------------------------------------------------

_boxscore_cache: Dict[str, Optional[dict]] = {}


def _load_boxscore(game_id: str) -> Optional[dict]:
    if game_id in _boxscore_cache:
        return _boxscore_cache[game_id]
    path = NBA_CACHE_DIR / f"boxscore_{game_id}.json"
    if not path.exists():
        _boxscore_cache[game_id] = None
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        _boxscore_cache[game_id] = d
        return d
    except Exception:
        _boxscore_cache[game_id] = None
        return None


def _player_team_from_boxscore(player_id: int, game_id: str) -> Optional[str]:
    """Return team_abbreviation for player_id in game_id from boxscore JSON, or None."""
    d = _load_boxscore(game_id)
    if d is None:
        return None
    players = d.get("players", [])
    for p in players:
        pid = p.get("player_id")
        if pid is None:
            continue
        if int(pid) == player_id:
            return p.get("team_abbreviation")
    return None


def _teams_from_boxscore(game_id: str):
    """Return (home_team_abbrev, away_team_abbrev) or (None, None)."""
    d = _load_boxscore(game_id)
    if d is None:
        return None, None
    # Old format
    if d.get("home_team") and d.get("away_team"):
        return d["home_team"], d["away_team"]
    # New format: derive from teams list using pts or position
    # We fall back to game_info_map instead
    return None, None


# ---------------------------------------------------------------------------
# Step 4: Load cv_features wide
# ---------------------------------------------------------------------------

def _load_cv_wide() -> pd.DataFrame:
    conn = sqlite3.connect(str(DB_PATH))
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
# Step 5: Assign game_date, offensive_team, opp_team_id per row
# Strategy: boxscore first (per-player), fall back to game_info + player_team_map
# Skip row if opp cannot be resolved
# ---------------------------------------------------------------------------

def _assign_opp_team(
    wide: pd.DataFrame,
    game_info: Dict[str, dict],
    pid_to_team: Dict[int, str],
) -> pd.DataFrame:
    game_dates = []
    off_teams = []
    opp_teams = []

    for _, row in wide.iterrows():
        gid = str(row["game_id"])
        pid = int(row["player_id"])

        gi = game_info.get(gid, {})
        gdate = gi.get("date", "")
        home = gi.get("home_team", "")
        away = gi.get("away_team", "")

        # Resolve player's team: boxscore first, then player_full map
        player_team = _player_team_from_boxscore(pid, gid)
        if player_team is None:
            player_team = pid_to_team.get(pid)

        # Derive opp team
        if player_team and home and away:
            pt_upper = str(player_team).upper()
            if pt_upper == home.upper():
                opp = away
            elif pt_upper == away.upper():
                opp = home
            else:
                opp = None  # trade artifact / mapping miss
        else:
            opp = None

        game_dates.append(gdate)
        off_teams.append(player_team)
        opp_teams.append(opp)

    wide = wide.copy()
    wide["game_date"] = game_dates
    wide["offensive_team"] = off_teams
    wide["opp_team_id"] = opp_teams

    before = len(wide)
    wide = wide[
        wide["game_date"].notna() & (wide["game_date"] != "") &
        wide["opp_team_id"].notna()
    ].copy()
    after = len(wide)
    print(f"  Rows after opp assignment: {after} (skipped {before - after} unmapped)")
    return wide


# ---------------------------------------------------------------------------
# Step 6: As-of opp atlas lookup (strict < game_date)
# Returns (z_value, density_tag)
# If no prior row: density_tag = "league_prior", z_value = 0.0 (residual ~ 0)
# ---------------------------------------------------------------------------

def _build_atlas_lookup(atlas: pd.DataFrame, z_col: str):
    """Return function: (team_abbrev, game_date_str) -> (z_val, density_tag)."""
    atlas = atlas.copy()
    atlas["game_date"] = pd.to_datetime(atlas["game_date"], errors="coerce")
    atlas = atlas.dropna(subset=["game_date", z_col])
    # Sort for searchsorted
    atlas = atlas.sort_values(["team_id", "game_date"]).reset_index(drop=True)

    # Group by team
    by_team: Dict[str, pd.DataFrame] = {}
    for team, grp in atlas.groupby("team_id"):
        by_team[str(team).upper()] = grp.reset_index(drop=True)

    def lookup(team: str, game_date_str: str):
        if not team or not game_date_str:
            return 0.0, "league_prior"
        gd = pd.Timestamp(game_date_str)
        grp = by_team.get(str(team).upper())
        if grp is None or len(grp) == 0:
            return 0.0, "league_prior"
        # strict < game_date
        prior = grp[grp["game_date"] < gd]
        if len(prior) == 0:
            return 0.0, "league_prior"
        row = prior.iloc[-1]
        return float(row[z_col]), str(row.get("data_density", "low"))

    return lookup


# ---------------------------------------------------------------------------
# Step 7: League z-score parameters (precomputed once from cv_features)
# ---------------------------------------------------------------------------

def _compute_league_zparams(wide: pd.DataFrame):
    params = {}
    for col, sentinel in [
        ("paint_dwell_pct", None),
        ("avg_defender_distance", _DEFENDER_DIST_MAX),
        ("contested_shot_rate", None),
    ]:
        if col not in wide.columns:
            params[col] = (0.0, 1.0)
            continue
        vals = wide[col].dropna()
        if sentinel is not None:
            vals = vals[vals < sentinel]
        # log1p for right-skewed paint_dwell_pct
        if col == "paint_dwell_pct":
            vals = np.log1p(vals)
        mu = float(vals.mean()) if len(vals) > 0 else 0.0
        sigma = float(vals.std()) if len(vals) > 1 else 1.0
        if sigma < 1e-9:
            sigma = 1.0
        params[col] = (mu, sigma)
    return params


def _zscore_player(value: float, col: str, params: dict) -> float:
    mu, sigma = params[col]
    if col == "paint_dwell_pct":
        value = np.log1p(max(value, 0.0))
    return (value - mu) / sigma


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build():
    print("=== INT-66: Opponent-Normalized CV Profile (B2) ===")

    # 1. Load atlases
    print("\n[1] Loading atlases...")
    df_paint_atlas = pd.read_parquet(str(PAINT_ATLAS))
    df_def_atlas = pd.read_parquet(str(DEF_ATLAS))
    print(f"  Paint atlas: {len(df_paint_atlas)} rows, {df_paint_atlas['team_id'].nunique()} teams")
    print(f"  Def atlas:   {len(df_def_atlas)} rows, {df_def_atlas['team_id'].nunique()} teams")

    # 2. Build atlas lookup functions
    lookup_paint = _build_atlas_lookup(df_paint_atlas, "opp_paint_pct_allowed_z")
    lookup_def_dist = _build_atlas_lookup(df_def_atlas, "opp_avg_defender_distance_imposed_z")
    lookup_contested = _build_atlas_lookup(df_def_atlas, "opp_contested_shot_rate_imposed_z")

    # 3. Load game info and player-team maps
    print("\n[2] Loading game metadata...")
    game_info = _load_game_info_map()
    pid_to_team = _load_player_team_map()
    print(f"  game_info entries: {len(game_info)}")
    print(f"  player_team entries: {len(pid_to_team)}")

    # 4. Load cv_features wide
    print("\n[3] Loading cv_features wide...")
    wide = _load_cv_wide()
    print(f"  cv_features rows: {len(wide)}, game_ids: {wide['game_id'].nunique()}")

    # 5. Assign opp_team_id and game_date
    print("\n[4] Assigning opp_team_id per player-game...")
    wide = _assign_opp_team(wide, game_info, pid_to_team)

    # 6. Compute league z-score params from cv_features
    print("\n[5] Computing league z-score params...")
    league_params = _compute_league_zparams(wide)
    for col, (mu, sigma) in league_params.items():
        print(f"  {col}: mean={mu:.4f}, std={sigma:.4f}")

    # 7. Build per-row residuals
    print("\n[6] Computing residuals (player_z - opp_z)...")
    records = []
    for _, row in wide.iterrows():
        gid = str(row["game_id"])
        pid = int(row["player_id"])
        gdate = str(row["game_date"])
        opp = str(row["opp_team_id"])

        # --- paint_dwell ---
        raw_paint = row.get("paint_dwell_pct", np.nan)
        if pd.isna(raw_paint):
            z_paint_player = np.nan
        else:
            z_paint_player = _zscore_player(float(raw_paint), "paint_dwell_pct", league_params)
        z_paint_opp, density_paint = lookup_paint(opp, gdate)
        paint_residual = (z_paint_player - z_paint_opp) if not np.isnan(z_paint_player) else np.nan

        # --- avg_defender_distance ---
        raw_def = row.get("avg_defender_distance", np.nan)
        if pd.isna(raw_def) or (not pd.isna(raw_def) and float(raw_def) >= _DEFENDER_DIST_MAX):
            raw_def = np.nan
            z_def_player = np.nan
        else:
            z_def_player = _zscore_player(float(raw_def), "avg_defender_distance", league_params)
        z_def_opp, density_def = lookup_def_dist(opp, gdate)
        def_residual = (z_def_player - z_def_opp) if not np.isnan(z_def_player) else np.nan

        # --- contested_shot_rate ---
        raw_cont = row.get("contested_shot_rate", np.nan)
        if pd.isna(raw_cont):
            z_cont_player = np.nan
        else:
            z_cont_player = _zscore_player(float(raw_cont), "contested_shot_rate", league_params)
        z_cont_opp, density_cont = lookup_contested(opp, gdate)
        cont_residual = (z_cont_player - z_cont_opp) if not np.isnan(z_cont_player) else np.nan

        # Density: take the worst (most uncertain) of the 3 lookups
        density_order = {"high": 3, "med": 2, "low": 1, "league_prior": 0}
        density_val = min(
            [density_paint, density_def, density_cont],
            key=lambda x: density_order.get(x, 0),
        )

        records.append({
            "player_id": pid,
            "game_id": gid,
            "game_date": gdate,
            "opp_team_id": opp,
            "paint_dwell_residual": paint_residual,
            "defender_dist_residual": def_residual,
            "contested_residual": cont_residual,
            "paint_dwell_raw": float(raw_paint) if not pd.isna(raw_paint) else np.nan,
            "defender_dist_raw": float(raw_def) if not pd.isna(raw_def) else np.nan,
            "contested_raw": float(raw_cont) if not pd.isna(raw_cont) else np.nan,
            "opp_join_density": density_val,
        })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df = df.dropna(subset=["game_date"])
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    print(f"  Residual rows: {len(df)}")

    density_counts = df["opp_join_density"].value_counts()
    print(f"  Density distribution:")
    for k, v in density_counts.items():
        print(f"    {k}: {v} ({100*v/len(df):.1f}%)")

    # 8. Rolling-5 priors (strict shift(1))
    print("\n[7] Computing rolling-5 priors...")

    def _rolling_l5(col: str, out_col: str):
        df[out_col] = (
            df.groupby("player_id")[col]
            .transform(lambda s: s.shift(1).rolling(_L5_WINDOW, min_periods=_L5_MIN_PERIODS).mean())
        )

    _rolling_l5("paint_dwell_residual", "paint_dwell_norm_l5")
    _rolling_l5("defender_dist_residual", "defender_dist_norm_l5")
    _rolling_l5("contested_residual", "contested_norm_l5")
    _rolling_l5("paint_dwell_raw", "paint_dwell_raw_l5")
    _rolling_l5("defender_dist_raw", "defender_dist_raw_l5")
    _rolling_l5("contested_raw", "contested_raw_l5")

    # n_cv_prior: count of non-null prior residuals in rolling window
    df["n_cv_prior"] = (
        df.groupby("player_id")["paint_dwell_residual"]
        .transform(lambda s: s.shift(1).rolling(_L5_WINDOW, min_periods=1).count())
    ).astype(int)

    # Keep only rows with at least 1 prior (rolling output is meaningful)
    df_out = df.dropna(subset=["paint_dwell_norm_l5", "defender_dist_norm_l5", "contested_norm_l5"],
                        how="all").copy()
    print(f"  Rows with at least one l5 value: {len(df_out)}")

    # Select output columns
    df_out = df_out[[
        "player_id", "game_date", "game_id",
        "paint_dwell_norm_l5", "defender_dist_norm_l5", "contested_norm_l5",
        "paint_dwell_raw_l5", "defender_dist_raw_l5", "contested_raw_l5",
        "opp_join_density", "n_cv_prior",
    ]].copy()

    # -------------------------------------------------------------------------
    # GATE 1: Residual independence
    # corr(norm_l5, raw_l5) — if > 0.90: REJECT; [0.70, 0.90]: SUPPLEMENTARY; < 0.70: PRIMARY
    # Run on full population AND high/med-density subset
    # -------------------------------------------------------------------------
    print("\n=== GATE 1: Residual Independence ===")

    def _gate1_report(label: str, subset: pd.DataFrame):
        results = {}
        for norm_col, raw_col, name in [
            ("paint_dwell_norm_l5", "paint_dwell_raw_l5", "paint"),
            ("defender_dist_norm_l5", "defender_dist_raw_l5", "def_dist"),
            ("contested_norm_l5", "contested_raw_l5", "contested"),
        ]:
            valid = subset[[norm_col, raw_col]].dropna()
            if len(valid) < 10:
                r = np.nan
            else:
                r = float(valid[norm_col].corr(valid[raw_col]))
            results[name] = r
            print(f"  [{label}] r_{name} = {r:.4f}")
        max_r = max(abs(v) for v in results.values() if not np.isnan(v))
        print(f"  [{label}] max|r| = {max_r:.4f}")
        if max_r > 0.90:
            verdict = "REJECT"
        elif max_r >= 0.70:
            verdict = "SUPPLEMENTARY"
        else:
            verdict = "PRIMARY"
        print(f"  [{label}] Gate 1 verdict: {verdict}")
        return results, max_r, verdict

    full_results, full_max_r, full_verdict = _gate1_report("FULL", df_out)

    hm_subset = df_out[df_out["opp_join_density"].isin(["high", "med"])]
    print(f"  High/med density rows: {len(hm_subset)}")
    if len(hm_subset) >= 10:
        hm_results, hm_max_r, hm_verdict = _gate1_report("HIGH/MED", hm_subset)
    else:
        hm_results, hm_max_r, hm_verdict = {}, np.nan, "INSUFFICIENT_DATA"
        print(f"  [HIGH/MED] Insufficient rows for gate ({len(hm_subset)})")

    # -------------------------------------------------------------------------
    # GATE 2: Null control — shuffle opp_team_id to random other team
    # -------------------------------------------------------------------------
    print("\n=== GATE 2: Null Control ===")

    all_teams = list(df_paint_atlas["team_id"].unique())

    def _null_shuffle(df_base: pd.DataFrame) -> pd.DataFrame:
        """Recompute residuals with shuffled opp_team_id."""
        df_s = df.copy()  # work from raw residual rows
        rng = random.Random(42)
        opp_col = df_s["opp_team_id"].tolist()
        shuffled = []
        for real_opp in opp_col:
            others = [t for t in all_teams if t != real_opp]
            shuffled.append(rng.choice(others) if others else real_opp)
        df_s["opp_team_id_null"] = shuffled

        # Recompute residuals with null opp
        null_paint = []
        null_def = []
        null_cont = []
        for _, row in df_s.iterrows():
            null_opp = str(row["opp_team_id_null"])
            gdate = str(row["game_date"])
            raw_paint = row["paint_dwell_raw"]
            raw_def = row["defender_dist_raw"]
            raw_cont = row["contested_raw"]

            z_po, _ = lookup_paint(null_opp, gdate)
            z_do, _ = lookup_def_dist(null_opp, gdate)
            z_co, _ = lookup_contested(null_opp, gdate)

            if pd.isna(raw_paint):
                z_pp = np.nan
            else:
                z_pp = _zscore_player(float(raw_paint), "paint_dwell_pct", league_params)
            if pd.isna(raw_def):
                z_dp = np.nan
            else:
                z_dp = _zscore_player(float(raw_def), "avg_defender_distance", league_params)
            if pd.isna(raw_cont):
                z_cp = np.nan
            else:
                z_cp = _zscore_player(float(raw_cont), "contested_shot_rate", league_params)

            null_paint.append((z_pp - z_po) if not np.isnan(z_pp) else np.nan)
            null_def.append((z_dp - z_do) if not np.isnan(z_dp) else np.nan)
            null_cont.append((z_cp - z_co) if not np.isnan(z_cp) else np.nan)

        df_s["paint_null"] = null_paint
        df_s["def_null"] = null_def
        df_s["cont_null"] = null_cont

        # Rolling l5 on null
        df_s = df_s.sort_values(["player_id", "game_date"])
        for col, out in [("paint_null", "pn_l5"), ("def_null", "dn_l5"), ("cont_null", "cn_l5")]:
            df_s[out] = (
                df_s.groupby("player_id")[col]
                .transform(lambda s: s.shift(1).rolling(_L5_WINDOW, min_periods=_L5_MIN_PERIODS).mean())
            )
        return df_s

    print("  Computing null shuffle (this may take ~30s)...")
    df_null = _null_shuffle(df_out)

    # delta_real: mean |paint_dwell_norm_l5 - paint_dwell_raw_l5|
    # delta_null: mean |paint_null_l5 - paint_dwell_raw_l5|
    valid_real = df_out[["paint_dwell_norm_l5", "paint_dwell_raw_l5"]].dropna()
    delta_real_paint = float(np.mean(np.abs(valid_real["paint_dwell_norm_l5"] - valid_real["paint_dwell_raw_l5"])))

    # Match indices
    df_null_merged = df_null[["player_id", "game_id", "pn_l5", "paint_dwell_raw_l5"]].dropna()
    delta_null_paint = float(np.mean(np.abs(df_null_merged["pn_l5"] - df_null_merged["paint_dwell_raw_l5"])))

    ratio = delta_real_paint / delta_null_paint if delta_null_paint > 0 else np.nan
    print(f"  delta_real (paint): {delta_real_paint:.4f}")
    print(f"  delta_null (paint): {delta_null_paint:.4f}")
    print(f"  ratio (real/null):  {ratio:.4f}")
    if 0.85 <= ratio <= 1.15:
        gate2_verdict = "REJECT"
        print("  Gate 2 verdict: REJECT (normalization indistinguishable from random)")
    else:
        gate2_verdict = "PASS"
        print("  Gate 2 verdict: PASS")

    # -------------------------------------------------------------------------
    # Final decision
    # -------------------------------------------------------------------------
    print("\n=== FINAL DECISION ===")
    gate1_fail = (full_verdict == "REJECT") and (hm_verdict not in ["PRIMARY", "SUPPLEMENTARY"])
    gate2_fail = (gate2_verdict == "REJECT")

    if gate2_fail:
        decision = "REJECT"
    elif full_verdict == "REJECT" and hm_verdict in ["PRIMARY", "SUPPLEMENTARY"]:
        decision = "SHIP SUPPLEMENTARY (density-filtered)"
    elif full_verdict == "SUPPLEMENTARY":
        decision = "SHIP SUPPLEMENTARY"
    elif full_verdict == "PRIMARY":
        decision = "SHIP PRIMARY"
    else:
        decision = "REJECT"

    print(f"  Gate 1 (full): {full_verdict} (max|r|={full_max_r:.4f})")
    print(f"  Gate 1 (high/med): {hm_verdict}")
    print(f"  Gate 2: {gate2_verdict} (ratio={ratio:.4f})")
    print(f"  >> DECISION: {decision}")

    # -------------------------------------------------------------------------
    # Write parquet
    # -------------------------------------------------------------------------
    print("\n[8] Writing output parquet...")
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_parquet(str(OUT_PARQUET), index=False)
    print(f"  Written: {OUT_PARQUET} ({len(df_out)} rows)")

    # -------------------------------------------------------------------------
    # Write INT-66 vault doc
    # -------------------------------------------------------------------------
    _write_vault_doc(
        df_out=df_out,
        density_counts=density_counts,
        full_results=full_results,
        full_max_r=full_max_r,
        full_verdict=full_verdict,
        hm_results=hm_results,
        hm_max_r=hm_max_r,
        hm_verdict=hm_verdict,
        delta_real=delta_real_paint,
        delta_null=delta_null_paint,
        ratio=ratio,
        gate2_verdict=gate2_verdict,
        decision=decision,
    )
    print(f"  Written: {VAULT_DOC}")

    return decision


def _write_vault_doc(
    df_out, density_counts, full_results, full_max_r, full_verdict,
    hm_results, hm_max_r, hm_verdict, delta_real, delta_null, ratio,
    gate2_verdict, decision,
):
    VAULT_DOC.parent.mkdir(parents=True, exist_ok=True)
    n_rows = len(df_out)
    density_str = "\n".join(f"  - {k}: {v} ({100*v/n_rows:.1f}%)" for k, v in density_counts.items())

    def fmt_r(results: dict) -> str:
        lines = []
        for name, r in results.items():
            lines.append(f"  - r_{name} = {r:.4f}" if not np.isnan(r) else f"  - r_{name} = N/A")
        return "\n".join(lines)

    doc = f"""# INT-66: Opponent-Normalized CV Profile (B2)

**Generated:** 2026-05-29
**Status:** {decision}
**Output:** data/intelligence/opp_normalized_cv.parquet

---

## Hypothesis

Raw CV signals (paint_dwell_pct, avg_defender_distance, contested_shot_rate) are confounded
by opponent defensive profile. A player guarded by a team that systematically reduces paint
access will show lower paint_dwell_pct regardless of their own tendencies. B2 removes this
confounder by subtracting the opponent's as-of z-scored defensive profile from the player's
own z-scored signal. The residual captures how much the player exceeded or was suppressed
relative to that specific opponent's defensive baseline.

**Sign convention:** positive = player exceeded opponent baseline; negative = player was suppressed.

---

## Method

### Dimensions
1. **paint_dwell_norm**: log1p(paint_dwell_pct) z-scored vs league → minus opp_paint_pct_allowed_z
2. **defender_dist_norm**: avg_defender_distance z-scored vs league (sentineled at 50ft) → minus opp_avg_defender_distance_imposed_z
3. **contested_norm**: contested_shot_rate z-scored vs league → minus opp_contested_shot_rate_imposed_z

### Opponent Resolution
- Primary: boxscore_{{game_id}}.json per-player team lookup
- Fallback: player_full_*.json season roster
- If both fail: row skipped (no imputation)

### As-of Atlas Lookup
- Strict < game_date to prevent leakage
- If no prior atlas row: density_tag = "league_prior", opp z = 0.0 (residual collapses to raw player z)

### Rolling Priors
- shift(1).rolling(5, min_periods=2).mean() per player_id, sorted by game_date
- Leak-safe: current game excluded from its own prior

---

## Row Count and Density Distribution

Total rows with at least one l5 value: {n_rows}

Density distribution (opp_join_density):
{density_str}

---

## Gate 1: Residual Independence

**Threshold:** max|r| > 0.90 → REJECT; [0.70, 0.90] → SUPPLEMENTARY; < 0.70 → PRIMARY

### Full Population (all density tags)

{fmt_r(full_results)}
  - max|r| = {full_max_r:.4f}
  - Verdict: **{full_verdict}**

### High/Med Density Only

{fmt_r(hm_results)}
  - max|r| = {hm_max_r:.4f}
  - Verdict: **{hm_verdict}**

**Interpretation:** The dense-data subset is the primary signal of whether normalization adds
information. If the full population fails but high/med passes, the failure is driven by
league_prior rows (where opp z = 0, so residual = raw player z exactly). Ship with
density-filter requirement in that case.

---

## Gate 2: Null Control

Shuffle each row's opp_team_id to a random OTHER team, recompute residuals, roll l5.
Ratio near 1.0 means the normalization is indistinguishable from random noise.

  - delta_real (paint): {delta_real:.4f}
  - delta_null (paint): {delta_null:.4f}
  - ratio = {ratio:.4f}
  - Verdict: **{gate2_verdict}**{"" if gate2_verdict == "PASS" else " — ratio in [0.85, 1.15] means normalization adds no real signal"}

---

## Decision

**{decision}**

---

## Risks

1. **Coverage ceiling:** 195/241 cv_features game_ids have boxscore JSON; ~19% rely on player_full roster which may have stale team assignment post-trade.
2. **Atlas sparsity:** No "high" density rows in current atlas (max = "med"); reduces Gate 1 high/med subset.
3. **log1p asymmetry:** paint_dwell_pct is log1p-transformed on the player side but atlas opp_paint_pct_allowed_z was computed on raw values. This creates mild unit mismatch; acceptable for a residual signal but not for magnitude interpretation.
4. **Temporal gap:** Atlas date range starts 2025-02-28; ~4 cv_features games predate this, falling back to league_prior.
5. **17-revert pattern:** Feature additions have consistently failed walk-forward. This signal should be validated against WF gate before wiring into prop_pergame.

---

## Downstream Wire-in Spec (if shipping)

Join on `(player_id, game_date)` or `(player_id, game_id)` in build_pergame_dataset.py.
Use `paint_dwell_norm_l5`, `defender_dist_norm_l5`, `contested_norm_l5` as additive features.
Filter to `opp_join_density in ('high', 'med')` if decision is SUPPLEMENTARY.
Gate against prop_pergame walk-forward (4/4 positive folds) before merging to production dataset.
"""
    with open(str(VAULT_DOC), "w", encoding="utf-8") as f:
        f.write(doc)


if __name__ == "__main__":
    decision = build()
    sys.exit(0 if "SHIP" in decision or "REJECT" not in decision else 1)
