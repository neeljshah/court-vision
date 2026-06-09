"""
INT-86: Build Teammate Correlation Matrix.

For each canonical (team, player_a, player_b) pair that shared >= 10 games,
compute all 49 stat-pair Pearson correlations on OOF residuals, then
PSD-project the joint 14x14 (a + b) matrix and emit cells.

Usage:
    python scripts/build_teammate_correlation.py
    python scripts/build_teammate_correlation.py --validate
"""

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parent.parent

OOF_PATH = ROOT / "data" / "cache" / "pregame_oof.parquet"
STAT_CORR_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"
OUT_PATH = ROOT / "data" / "intelligence" / "teammate_correlation.parquet"
SEASON_GAMES_DIR = ROOT / "data" / "nba"
GAMELOG_DIR = ROOT / "data" / "nba"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
N_STATS = len(STATS)
STAT_IDX = {s: i for i, s in enumerate(STATS)}

MIN_GAMES_PAIR = 10          # minimum shared games to emit pair
MIN_CORR_GAMES = 10          # minimum non-NaN rows for a single stat-pair correlation
MIN_MINUTES = 10.0           # skip player-game if played < 10 min
TOP_BY_MIN_PER_SEASON = 8    # keep top-8 by average minutes per team-season


# ---------------------------------------------------------------------------
# Reuse INT-84 PSD helper (eigen-clip + renormalize diagonal)
# ---------------------------------------------------------------------------

def psd_project(C: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """Eigen-clip negative eigenvalues to `floor`, renormalize diagonal to 1."""
    eigvals, eigvecs = np.linalg.eigh(C)
    eigvals_clipped = np.maximum(eigvals, floor)
    C_psd = eigvecs @ np.diag(eigvals_clipped) @ eigvecs.T
    d = np.sqrt(np.diag(C_psd))
    d = np.where(d == 0, 1.0, d)
    C_psd = C_psd / np.outer(d, d)
    return C_psd


def frobenius_dist(A: np.ndarray, B: np.ndarray) -> float:
    return float(np.linalg.norm(A - B, "fro"))


# ---------------------------------------------------------------------------
# Step 1: Build game_id -> (home_team, away_team, game_date) index
# ---------------------------------------------------------------------------

def build_game_index() -> dict:
    """Load all season_games_*.json and return game_id -> {home_team, away_team, game_date}."""
    idx = {}
    for f in SEASON_GAMES_DIR.glob("season_games_*.json"):
        with open(f) as fh:
            data = json.load(fh)
        for row in data.get("rows", []):
            gid = row.get("game_id", "")
            if gid:
                idx[gid] = {
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "game_date": row.get("game_date", ""),
                }
    return idx


# ---------------------------------------------------------------------------
# Step 2: Build (player_id, game_date_iso) -> (team_abbr, minutes) from gamelogs
# ---------------------------------------------------------------------------

def _parse_gamelog_date(raw: str) -> str:
    """'Apr 06, 2023' -> '2023-04-06'; return '' on failure."""
    try:
        return datetime.strptime(raw.strip(), "%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return ""


def build_player_game_info(player_ids: list) -> pd.DataFrame:
    """
    For each player_id, load all gamelog_*.json files, extract:
      player_id, game_date_iso, team_abbr, minutes

    MATCHUP format: 'XXX vs. YYY' or 'XXX @ YYY'  — player's team is always first token.
    """
    records = []
    pid_set = set(player_ids)
    all_gl_files = list(GAMELOG_DIR.glob("gamelog_*.json"))
    # Group by player_id
    pid_to_files: dict[int, list[Path]] = {}
    for f in all_gl_files:
        m = re.search(r"gamelog_(\d+)_", f.name)
        if m:
            pid = int(m.group(1))
            if pid in pid_set:
                pid_to_files.setdefault(pid, []).append(f)

    for pid, files in pid_to_files.items():
        for f in files:
            try:
                with open(f) as fh:
                    rows = json.load(fh)
            except Exception:
                continue
            for r in rows:
                raw_date = r.get("GAME_DATE", "") or r.get("game_date", "")
                date_iso = _parse_gamelog_date(raw_date)
                if not date_iso:
                    continue
                matchup = r.get("MATCHUP", "") or r.get("matchup", "")
                team_abbr = matchup.split()[0].upper() if matchup else ""
                minutes = r.get("MIN", 0)
                if minutes is None:
                    minutes = 0
                try:
                    minutes = float(minutes)
                except (TypeError, ValueError):
                    # handle 'MM:SS' format from some formats
                    if isinstance(minutes, str) and ":" in minutes:
                        parts = minutes.split(":")
                        try:
                            minutes = int(parts[0]) + int(parts[1]) / 60.0
                        except Exception:
                            minutes = 0.0
                    else:
                        minutes = 0.0
                records.append({
                    "player_id": pid,
                    "game_date": date_iso,
                    "team_abbr": team_abbr,
                    "minutes": minutes,
                })

    df = pd.DataFrame(records)
    if df.empty:
        return df
    # Deduplicate: keep one row per (player_id, game_date) — max minutes
    df = df.sort_values("minutes", ascending=False)
    df = df.drop_duplicates(subset=["player_id", "game_date"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 3: Build residuals with team + minutes info
# ---------------------------------------------------------------------------

def build_residuals_with_meta(
    oof: pd.DataFrame,
    game_index: dict,
    player_game_info: pd.DataFrame,
) -> pd.DataFrame:
    """
    Returns a wide residual DataFrame:
    columns: player_id, game_id, game_date, team_abbr, minutes, pts, reb, ast, fg3m, stl, blk, tov
    (residual = actual - oof_pred)
    """
    # Compute per-row residual in long format
    oof_wide_act = oof.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values="actual",
        aggfunc="first",
    )
    oof_wide_pred = oof.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values="oof_pred",
        aggfunc="first",
    )
    stats_avail = [s for s in STATS if s in oof_wide_act.columns]
    missing = [s for s in STATS if s not in oof_wide_act.columns]
    if missing:
        print(f"  WARNING: stats missing from OOF: {missing}")

    act = oof_wide_act[stats_avail].copy()
    pred = oof_wide_pred[stats_avail].copy()

    # Drop rows where any actual is NaN
    mask_nan = act.isnull().any(axis=1)
    act = act[~mask_nan]
    pred = pred[~mask_nan]

    # Drop DNP rows
    dnp_cols = [s for s in ["pts", "reb", "ast"] if s in act.columns]
    dnp_mask = (act[dnp_cols] == 0).all(axis=1)
    act = act[~dnp_mask]
    pred = pred[~dnp_mask]

    resid = (act - pred).reset_index()
    resid.columns.name = None

    # Attach game_date from game_index
    resid["game_date_lookup"] = resid["game_id"].map(
        lambda gid: game_index.get(gid, {}).get("game_date", "")
    )
    # Use OOF game_date if available and consistent (use lookup as primary)
    resid["game_date"] = resid["game_date_lookup"].where(
        resid["game_date_lookup"] != "", resid["game_date"]
    )

    # Merge player_game_info to get team_abbr + minutes
    pgi = player_game_info[["player_id", "game_date", "team_abbr", "minutes"]]
    resid = resid.merge(pgi, on=["player_id", "game_date"], how="left")

    # Apply minutes filter
    resid = resid[resid["minutes"].fillna(0) >= MIN_MINUTES].copy()
    print(f"  After min>={MIN_MINUTES} filter: {len(resid):,} player-game rows")
    print(f"  Team abbr coverage: {resid['team_abbr'].notna().mean():.1%}")
    return resid, stats_avail


# ---------------------------------------------------------------------------
# Step 4: Top-8 by minutes per team-season
# ---------------------------------------------------------------------------

def filter_top8_by_minutes(resid: pd.DataFrame, game_index: dict) -> pd.DataFrame:
    """
    For each (team_abbr, season), keep only top-8 players by average minutes.
    Season is derived from game_id prefix (002YYXXX -> year).
    """
    # Derive season from game_id: e.g., '0022300149' -> season_year=23 -> '2023-24'
    def game_id_to_season(gid: str) -> str:
        try:
            season_code = int(str(gid)[3:5])
            return f"20{season_code:02d}-{(season_code+1):02d}"
        except Exception:
            return "unknown"

    resid = resid.copy()
    resid["season"] = resid["game_id"].apply(game_id_to_season)

    # Compute avg minutes per (player_id, team_abbr, season)
    avg_min = (
        resid.groupby(["player_id", "team_abbr", "season"])["minutes"]
        .mean()
        .reset_index(name="avg_min")
    )
    # Rank within (team_abbr, season)
    avg_min["rank"] = avg_min.groupby(["team_abbr", "season"])["avg_min"].rank(
        ascending=False, method="first"
    )
    top8 = avg_min[avg_min["rank"] <= TOP_BY_MIN_PER_SEASON][
        ["player_id", "team_abbr", "season"]
    ]
    resid = resid.merge(top8, on=["player_id", "team_abbr", "season"], how="inner")
    print(f"  After top-{TOP_BY_MIN_PER_SEASON}/team-season filter: {len(resid):,} rows")
    return resid


# ---------------------------------------------------------------------------
# Step 5: Build player name map (from fingerprints or gamelog paths)
# ---------------------------------------------------------------------------

def build_player_name_map() -> dict:
    fp_path = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
    name_map: dict[int, str] = {}
    if fp_path.exists():
        fp = pd.read_parquet(fp_path)
        if "player_name" in fp.columns:
            for pid, row in fp.iterrows():
                name_map[int(pid)] = str(row["player_name"])
    return name_map


# ---------------------------------------------------------------------------
# Step 6: Compute pair correlations
# ---------------------------------------------------------------------------

def compute_pair_correlations(
    resid: pd.DataFrame,
    stats: list,
    int84_league: np.ndarray,
) -> list[dict]:
    """
    For each (team_abbr, player_a, player_b) canonical pair:
    1. Find shared games
    2. Compute 49 raw Pearson correlations on residuals
    3. Build joint 14x14 matrix (using INT-84 within-player diagonal blocks)
    4. PSD-project joint matrix
    5. Extract cross-block M (rows 0:7, cols 7:14), emit cells
    """
    name_map = build_player_name_map()
    stat_pairs = [(sa, sb) for sa in stats for sb in stats]  # 49 pairs
    n = len(stats)

    records = []
    total_pairs_processed = 0
    pairs_skipped_sparse = 0

    # Group by team_abbr
    team_groups = resid.groupby("team_abbr")

    for team_id, team_df in team_groups:
        if not team_id or str(team_id) == "nan":
            continue

        players = team_df["player_id"].unique()
        if len(players) < 2:
            continue

        # Build pivot: game_id x (player_id, stat)
        # Aggregate duplicates (same player can appear twice if team changed mid-season)
        pivot_cols = {}
        for pid in players:
            pdf = team_df[team_df["player_id"] == pid].copy()
            # Deduplicate by game_id: keep highest-minutes entry
            pdf = pdf.sort_values("minutes", ascending=False).drop_duplicates("game_id")
            pdf = pdf.set_index("game_id")
            for stat in stats:
                if stat in pdf.columns:
                    pivot_cols[(pid, stat)] = pdf[stat]

        if not pivot_cols:
            continue

        wide = pd.DataFrame(pivot_cols)
        wide.index.name = "game_id"

        # Enumerate canonical pairs
        player_list = sorted(players)
        for i, pid_a in enumerate(player_list):
            for pid_b in player_list[i + 1:]:
                # Check columns exist
                cols_a = [(pid_a, s) for s in stats if (pid_a, s) in wide.columns]
                cols_b = [(pid_b, s) for s in stats if (pid_b, s) in wide.columns]
                if not cols_a or not cols_b:
                    continue

                # Shared non-NaN games across all stats
                sub_a = wide[[c for c in cols_a if c in wide.columns]]
                sub_b = wide[[c for c in cols_b if c in wide.columns]]
                combined = pd.concat([sub_a, sub_b], axis=1).dropna()
                n_shared = len(combined)

                if n_shared < MIN_GAMES_PAIR:
                    pairs_skipped_sparse += 1
                    continue

                total_pairs_processed += 1

                # Build 7x7 cross-correlation matrix M[i,j] = corr(res_a_stats[i], res_b_stats[j])
                M_raw = np.zeros((n, n))
                for ii, sa in enumerate(stats):
                    for jj, sb in enumerate(stats):
                        col_a = (pid_a, sa)
                        col_b = (pid_b, sb)
                        if col_a not in combined.columns or col_b not in combined.columns:
                            continue
                        va = combined[col_a].values
                        vb = combined[col_b].values
                        if len(va) < MIN_CORR_GAMES:
                            continue
                        try:
                            r, _ = pearsonr(va, vb)
                            if np.isnan(r):
                                r = 0.0
                        except Exception:
                            r = 0.0
                        M_raw[ii, jj] = r

                # Build joint 14x14 from:
                #   top-left  7x7: within-player A (from INT-84 league)
                #   bot-right 7x7: within-player B (from INT-84 league)
                #   top-right 7x7: M_raw (cross)
                #   bot-left  7x7: M_raw.T
                C14_raw = np.zeros((14, 14))
                C14_raw[:n, :n] = int84_league           # C_aa
                C14_raw[n:, n:] = int84_league           # C_bb (same league avg)
                C14_raw[:n, n:] = M_raw                  # M
                C14_raw[n:, :n] = M_raw.T               # M.T

                # PSD project
                C14_psd = psd_project(C14_raw)
                M_psd = C14_psd[:n, n:]                  # extract cross block

                # Emit cells
                for ii, sa in enumerate(stats):
                    for jj, sb in enumerate(stats):
                        records.append({
                            "team_id": str(team_id),
                            "player_id_a": int(pid_a),
                            "player_a_name": name_map.get(int(pid_a), f"pid_{pid_a}"),
                            "player_id_b": int(pid_b),
                            "player_b_name": name_map.get(int(pid_b), f"pid_{pid_b}"),
                            "n_games": int(n_shared),
                            "stat_a": sa,
                            "stat_b": sb,
                            "corr": float(M_psd[ii, jj]),
                            "corr_raw_pre_PSD": float(M_raw[ii, jj]),
                        })

    print(f"  Pairs processed: {total_pairs_processed:,}, skipped (sparse): {pairs_skipped_sparse:,}")
    return records


# ---------------------------------------------------------------------------
# Step 7: Load INT-84 league matrix
# ---------------------------------------------------------------------------

def load_int84_league_matrix(stats: list) -> np.ndarray:
    """Load INT-84 league-scope PSD matrix as np.ndarray (n_stats x n_stats)."""
    if not STAT_CORR_PATH.exists():
        print(f"  WARNING: {STAT_CORR_PATH} not found — using identity for within-player blocks")
        return np.eye(len(stats))

    sc = pd.read_parquet(STAT_CORR_PATH)
    league = sc[sc["scope"] == "league"]
    n = len(stats)
    M = np.eye(n)
    for _, row in league.iterrows():
        sa, sb = row["stat_a"], row["stat_b"]
        if sa in STAT_IDX and sb in STAT_IDX:
            i, j = STAT_IDX[sa], STAT_IDX[sb]
            M[i, j] = float(row["corr"])
    return M


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def run_validation(out_df: pd.DataFrame) -> bool:
    """Run sanity checks; return True if all hard asserts pass."""
    ok = True
    print("\n=== Validation ===")

    # 1. min eigenvalue check per pair
    # We do spot check on joint PSD rather than recomputing — instead check corr bounds
    corr_vals = out_df["corr"].values
    bad_corr = np.sum((corr_vals < -1.0 - 1e-6) | (corr_vals > 1.0 + 1e-6))
    if bad_corr > 0:
        print(f"  FAIL: {bad_corr} corr values outside [-1,1]")
        ok = False
    else:
        print(f"  OK  : all corr values in [-1,1]")

    # 2. Median PTS_a x PTS_b across top-30 star pairs < 0
    pts_pts = out_df[(out_df.stat_a == "pts") & (out_df.stat_b == "pts")].copy()
    if len(pts_pts) > 0:
        # top-30 star pairs by n_games
        top30 = pts_pts.nlargest(30, "n_games")
        median_pts_pts = top30["corr"].median()
        print(f"  Median PTS x PTS (top-30 by n_games): {median_pts_pts:.4f}")
        if median_pts_pts >= 0:
            print(f"  WARN: expected < 0 for usage-steal signal (got {median_pts_pts:.4f})")
        else:
            print(f"  OK  : median PTS x PTS < 0 (usage steal signal present)")
    else:
        print("  WARN: no pts x pts rows found")

    # 3. Median PTS_a x REB_b within +-0.05
    pts_reb = out_df[(out_df.stat_a == "pts") & (out_df.stat_b == "reb")]
    if len(pts_reb) > 0:
        med_pr = pts_reb["corr"].median()
        print(f"  Median PTS_a x REB_b: {med_pr:.4f}")
        if abs(med_pr) > 0.05:
            print(f"  WARN: expected within +-0.05 of 0 (got {med_pr:.4f})")
        else:
            print(f"  OK  : PTS_a x REB_b median within +-0.05")
    else:
        print("  WARN: no pts x reb rows")

    # 4. n_games distribution
    ngames = out_df.drop_duplicates(["player_id_a", "player_id_b", "team_id"])["n_games"]
    pcts = np.percentile(ngames, [10, 25, 50, 75, 90])
    print(f"  n_games distribution (p10/p25/p50/p75/p90): "
          f"{pcts[0]:.0f}/{pcts[1]:.0f}/{pcts[2]:.0f}/{pcts[3]:.0f}/{pcts[4]:.0f}")
    if pcts[2] < 25:
        print(f"  WARN: median n_games={pcts[2]:.0f} < 25 (high noise)")
    else:
        print(f"  OK  : median n_games >= 25")

    # 5. Frobenius drift
    pairs_dists = []
    for (pid_a, pid_b, team), grp in out_df.groupby(["player_id_a", "player_id_b", "team_id"]):
        if len(grp) == 49:
            raw_vals = grp.sort_values(["stat_a", "stat_b"])["corr_raw_pre_PSD"].values.reshape(7, 7)
            psd_vals = grp.sort_values(["stat_a", "stat_b"])["corr"].values.reshape(7, 7)
            pairs_dists.append(frobenius_dist(raw_vals, psd_vals))
    if pairs_dists:
        med_fro = float(np.median(pairs_dists))
        print(f"  Frobenius drift (raw vs PSD cross-block) median: {med_fro:.5f}")
        if med_fro >= 0.10:
            print(f"  WARN: median Frobenius drift {med_fro:.4f} >= 0.10 (high distortion)")
        else:
            print(f"  OK  : median Frobenius drift < 0.10")
    else:
        med_fro = float("nan")
        print("  INFO: could not compute Frobenius drift (no complete 49-cell pairs)")

    # 6. Specific pair checks (warn only)
    def check_pair(name_a, name_b, stat, expected_sign, df=pts_pts):
        # Find by player name
        sub_stat = out_df[
            (out_df.stat_a == stat) & (out_df.stat_b == stat) &
            (
                (out_df.player_a_name.str.contains(name_a, case=False, na=False) &
                 out_df.player_b_name.str.contains(name_b, case=False, na=False)) |
                (out_df.player_a_name.str.contains(name_b, case=False, na=False) &
                 out_df.player_b_name.str.contains(name_a, case=False, na=False))
            )
        ]
        if len(sub_stat) > 0:
            corr_val = sub_stat.iloc[0]["corr"]
            passed = (corr_val < expected_sign)
            tag = "OK  " if passed else "WARN"
            print(f"  {tag}: corr({name_a},{name_b},{stat})={corr_val:.4f} (expect < {expected_sign})")

    check_pair("LeBron", "Davis", "pts", -0.05)
    check_pair("Curry", "Thompson", "pts", -0.05)

    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(validate: bool = False) -> None:
    print("=== INT-86: build_teammate_correlation ===")

    # 1. Load OOF
    if not OOF_PATH.exists():
        print(f"HALT: {OOF_PATH} not found")
        sys.exit(1)

    oof = pd.read_parquet(OOF_PATH)
    expected_cols = {"player_id", "game_id", "stat", "oof_pred", "actual", "game_date"}
    missing = expected_cols - set(oof.columns)
    if missing:
        print(f"HALT: pregame_oof.parquet missing columns: {missing}")
        sys.exit(1)
    print(f"  OOF: {oof.shape[0]:,} rows, {oof.player_id.nunique()} players, "
          f"{oof.game_id.nunique()} games")

    # 2. Build game index
    print("\n--- Building game index ---")
    game_index = build_game_index()
    print(f"  Games indexed from season_games: {len(game_index):,}")

    # 3. Build player game info (team + minutes)
    print("\n--- Building player game info from gamelogs ---")
    unique_players = list(oof.player_id.unique())
    player_game_info = build_player_game_info(unique_players)
    if player_game_info.empty:
        print("HALT: no player game info loaded from gamelogs")
        sys.exit(1)
    print(f"  Player-game entries (post dedup): {len(player_game_info):,}")
    print(f"  Players covered: {player_game_info.player_id.nunique()}")
    print(f"  Avg minutes distribution: "
          f"p25={player_game_info.minutes.quantile(0.25):.1f}, "
          f"p50={player_game_info.minutes.quantile(0.50):.1f}, "
          f"p75={player_game_info.minutes.quantile(0.75):.1f}")

    # 4. Build residuals with meta
    print("\n--- Building residuals ---")
    resid, stats_avail = build_residuals_with_meta(oof, game_index, player_game_info)

    # 5. Filter top-8 by minutes per team-season
    print("\n--- Filtering top-8 per team-season ---")
    resid_filtered = filter_top8_by_minutes(resid, game_index)

    # Drop rows with missing team
    resid_filtered = resid_filtered[
        resid_filtered["team_abbr"].notna() & (resid_filtered["team_abbr"] != "")
    ].copy()
    print(f"  After dropping missing team rows: {len(resid_filtered):,}")

    # 6. Load INT-84 league matrix for within-player diagonal blocks
    print("\n--- Loading INT-84 league correlation matrix ---")
    int84_league = load_int84_league_matrix(stats_avail)
    print(f"  INT-84 league matrix shape: {int84_league.shape}")

    # 7. Compute pair correlations
    print("\n--- Computing pair correlations ---")
    records = compute_pair_correlations(resid_filtered, stats_avail, int84_league)

    if not records:
        print("HALT: no pair records generated — check team coverage and game count requirements")
        sys.exit(1)

    out_df = pd.DataFrame(records)
    print(f"\n  Output rows: {len(out_df):,}")

    # Sort for readability
    out_df = out_df.sort_values(
        ["team_id", "player_id_a", "player_id_b", "stat_a", "stat_b"]
    ).reset_index(drop=True)

    # 8. Run validation
    if validate or True:  # always run basic checks
        run_validation(out_df)

    # 9. Print top/bottom pairs for PTS x PTS
    print("\n--- Top-10 most-negative PTS x PTS pairs (usage steal) ---")
    pts_pts = out_df[(out_df.stat_a == "pts") & (out_df.stat_b == "pts")].copy()
    if len(pts_pts) > 0:
        bottom10 = pts_pts.nsmallest(10, "corr")
        for _, row in bottom10.iterrows():
            print(f"  {str(row.team_id):4s}  {str(row.player_a_name):<22s}  {str(row.player_b_name):<22s}  "
                  f"n={row.n_games:3d}  corr={row['corr']:+.4f}")

        print("\n--- Top-10 most-positive PTS x PTS pairs ---")
        top10 = pts_pts.nlargest(10, "corr")
        for _, row in top10.iterrows():
            print(f"  {str(row.team_id):4s}  {str(row.player_a_name):<22s}  {str(row.player_b_name):<22s}  "
                  f"n={row.n_games:3d}  corr={row['corr']:+.4f}")

    # 10. Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUT_PATH, index=False)
    print(f"\n  Saved: {OUT_PATH}")
    print(f"  Rows: {len(out_df):,}")
    print(f"  Unique pairs: {out_df[['player_id_a','player_id_b','team_id']].drop_duplicates().shape[0]:,}")
    print(f"  Teams: {out_df.team_id.nunique()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    main(validate=args.validate)
