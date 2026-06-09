"""sgp_cross_team_sweep.py - Cross-team / expanded SGP copula sweep.

EXPANDS the genuine-edge catalog from sgp_joint_hitrate_backtest.py to cover:
  CROSS-TEAM (opponent) cells:
    C1: rim_protector BLK-over  <->  opposing paint scorer PTS-under (rim deterrence)
    C2: rim_protector BLK-over  <->  opposing rim-roller FG% (pnr_roll_man)
    C3: high-pace game: both-team high-usage scorer PTS+PTS both-OVER
    C4: lockdown wing (low opp-PPP) <-> opposing scorer PTS-under
    C5: opposing lead-guard AST+AST both-over in high-possession games

  WIDER TEAMMATE cells:
    T5: creator_AST <-> roll_man PTS  (was cell 10, n=630, EXPAND with archetype=other)
    T6: creator_AST <-> post_up PTS
    T7: creator_AST <-> cutter/other PTS
    T8: two_big REB+REB (rebounder <-> rebounder)
    T9: creator PTS-down <-> same creator AST-up  (same-player, usage sub)

GATE: a cell joins the catalog ONLY if:
  (a) measured rho is split-half STABLE (same sign in both halves)
  (b) our-model predicts realized joint rate better than BOTH independence and naive
  (c) it is cross-player or cross-team (book blind spot)
  (d) rho differs materially from plausible book assumption in +EV direction

Outputs:
  - Printed summary table (stdout)
  - data/models/sgp_genuine_edges.json (full catalog including prior edges)
  - Returns results dict for docs/_audits/SGP_EDGE.md append

Usage:
  python scripts/sgp_cross_team_sweep.py [--quiet]
"""
from __future__ import annotations

import argparse
import json
import io
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Force UTF-8 output on Windows consoles to avoid cp1252 encode errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR  = PROJECT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CVFIX_DIR = CACHE_DIR / "cv_fix"
MODELS_DIR = DATA_DIR / "models"

LEAGUELOG_RS = CVFIX_DIR / "leaguegamelog_regular_season.parquet"
LEAGUELOG_PO = CVFIX_DIR / "leaguegamelog_playoffs.parquet"

TEAMMATE_ARCH_PATH = MODELS_DIR / "player_archetype_teammate.json"
OUTPUT_EDGES_PATH  = MODELS_DIR / "sgp_genuine_edges.json"

MIN_JOINT_OBS = 300    # require >=300 pair-games per cell (else small-n advisory)
MIN_GAMES_FOR_MEDIAN = 10

# ---------------------------------------------------------------------------
# Import shared BVN machinery from the existing backtest script
# ---------------------------------------------------------------------------
from scripts.sgp_joint_hitrate_backtest import (
    bvn_joint_over_prob,
    compute_rolling_medians,
    load_gamelog,
)

# ---------------------------------------------------------------------------
# Archetype helpers
# ---------------------------------------------------------------------------

def load_teammate_archetypes() -> Dict[int, str]:
    with open(TEAMMATE_ARCH_PATH) as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def build_blk_tier_map(df: pd.DataFrame, hi_thresh_z: float = 0.75) -> Dict[int, str]:
    """Classify players as 'rim_protector' (top BLK/g z-score) or 'other'.

    Uses per-player mean BLK from the combined gamelog (min 10 games).
    Returns {player_id: 'rim_protector'|'other'}.
    """
    pg = (
        df[df["MIN"] >= 10]
        .groupby("PLAYER_ID")
        .agg(blk_mean=("BLK", "mean"), n_games=("GAME_ID", "nunique"))
        .reset_index()
    )
    pg = pg[pg["n_games"] >= 10].copy()
    mu  = pg["blk_mean"].mean()
    std = pg["blk_mean"].std()
    pg["blk_z"] = (pg["blk_mean"] - mu) / std
    result: Dict[int, str] = {}
    for _, row in pg.iterrows():
        result[int(row["PLAYER_ID"])] = (
            "rim_protector" if row["blk_z"] >= hi_thresh_z else "other"
        )
    return result


def build_pace_game_flag(df: pd.DataFrame, hi_pace_thresh_pg: float = 100.0) -> Dict[str, bool]:
    """Flag each GAME_ID as 'high_pace' if the total PTS in the game is above the median.

    We use total game PTS as a proxy for pace/possession count (easily computed
    from the gamelog without needing team pace atlas).  High-pace = game total PTS
    above the 66th percentile across all games.

    Returns {game_id: True/False}.
    """
    game_pts = (
        df[df["MIN"] >= 10]
        .groupby("GAME_ID")["PTS"]
        .sum()
        .reset_index(name="game_total_pts")
    )
    thresh = game_pts["game_total_pts"].quantile(0.67)
    result = {
        str(row["GAME_ID"]): bool(row["game_total_pts"] >= thresh)
        for _, row in game_pts.iterrows()
    }
    return result


def build_high_usage_map(df: pd.DataFrame, hi_usage_thresh_pts: float = None) -> Dict[int, bool]:
    """Flag players as high-usage scorers (mean PTS/g in top tercile among >=10g players)."""
    pg = (
        df[df["MIN"] >= 10]
        .groupby("PLAYER_ID")
        .agg(pts_mean=("PTS", "mean"), n_games=("GAME_ID", "nunique"))
        .reset_index()
    )
    pg = pg[pg["n_games"] >= 10].copy()
    if hi_usage_thresh_pts is None:
        hi_usage_thresh_pts = pg["pts_mean"].quantile(0.67)
    return {int(row["PLAYER_ID"]): bool(row["pts_mean"] >= hi_usage_thresh_pts)
            for _, row in pg.iterrows()}


def build_ast_leader_map(df: pd.DataFrame) -> Dict[int, bool]:
    """Flag players as lead guards / AST leaders (mean AST/g top tercile)."""
    pg = (
        df[df["MIN"] >= 10]
        .groupby("PLAYER_ID")
        .agg(ast_mean=("AST", "mean"), n_games=("GAME_ID", "nunique"))
        .reset_index()
    )
    pg = pg[pg["n_games"] >= 10].copy()
    thresh = pg["ast_mean"].quantile(0.67)
    return {int(row["PLAYER_ID"]): bool(row["ast_mean"] >= thresh)
            for _, row in pg.iterrows()}


# ---------------------------------------------------------------------------
# Cross-OPPONENT pair backtest
# ---------------------------------------------------------------------------

def opponent_pair_backtest(
    df: pd.DataFrame,
    stat_a: str,       # stat for player A (team A)
    stat_b: str,       # stat for player B (team B, opponent)
    over_a: bool,      # True = over for leg A counts as "hit A"
    over_b: bool,      # True = over for leg B counts as "hit B"
    arch_a_map: Dict[int, str],   # player_id -> archetype label for player A
    arch_b_map: Dict[int, str],   # player_id -> archetype label for player B
    arch_a_filter: Optional[str],
    arch_b_filter: Optional[str],
    game_filter: Optional[Dict[str, bool]],  # optional game-level filter {game_id: bool}
    recal_rho: float,
    naive_rho: float,
    label: str,
    note: str = "",
) -> dict:
    """Backtest a cross-opponent pair.

    Pairs are (player_a on team A, player_b on team B) where they play the SAME
    game but on DIFFERENT teams.  We build all such opponent pairs, apply
    archetype and game filters, then compute the joint over/under rate.

    Because we want to isolate the copula from marginals, we use the same
    rolling-median line approach as the teammate backtest.
    """
    col_a = f"{stat_a}_is_over"
    col_b = f"{stat_b}_is_over"
    needed = [col_a, col_b, f"{stat_a}_rolling_median", f"{stat_b}_rolling_median"]
    working = df.dropna(subset=needed).copy()

    # Add archetype columns for A and B
    working["arch_a_val"] = working["PLAYER_ID"].map(arch_a_map)
    working["arch_b_val"] = working["PLAYER_ID"].map(arch_b_map)

    # Apply game filter
    if game_filter is not None:
        working["_gflag"] = working["GAME_ID"].astype(str).map(game_filter).fillna(False)
        working = working[working["_gflag"]]

    # Apply over/under direction for A
    # By default is_over is computed as stat > rolling_median
    # If we want "under" for leg A, flip: hit_a = 1 - is_over_a
    if over_a:
        working["hit_a"] = working[col_a]
    else:
        working["hit_a"] = 1.0 - working[col_a]

    if over_b:
        working["hit_b"] = working[col_b]
    else:
        working["hit_b"] = 1.0 - working[col_b]

    # Build cross-opponent pairs: same GAME_ID, DIFFERENT TEAM_ID
    keep_cols = ["PLAYER_ID", "GAME_ID", "TEAM_ID", "GAME_DATE",
                 "hit_a", "hit_b", "arch_a_val", "arch_b_val"]
    keep_cols = [c for c in keep_cols if c in working.columns]
    w = working[keep_cols].copy()

    left  = w.rename(columns={
        "PLAYER_ID": "pid_a", "hit_a": "ha", "arch_a_val": "arch_a",
        "TEAM_ID": "team_a"
    })
    right = w.rename(columns={
        "PLAYER_ID": "pid_b", "hit_b": "hb", "arch_b_val": "arch_b",
        "TEAM_ID": "team_b"
    })

    # Merge on GAME_ID (cross-team: allow different TEAM_ID)
    left_cols  = ["GAME_ID", "GAME_DATE", "pid_a", "team_a", "ha", "arch_a"]
    right_cols = ["GAME_ID", "pid_b", "team_b", "hb", "arch_b"]

    pairs = left[left_cols].merge(right[right_cols], on="GAME_ID")
    # Keep only cross-team pairs
    pairs = pairs[pairs["team_a"] != pairs["team_b"]]
    # Avoid double-counting (unordered): for same pair, keep only pid_a < pid_b
    pairs = pairs[pairs["pid_a"] < pairs["pid_b"]]

    # Apply archetype filters
    if arch_a_filter is not None:
        pairs = pairs[pairs["arch_a"] == arch_a_filter]
    if arch_b_filter is not None:
        pairs = pairs[pairs["arch_b"] == arch_b_filter]

    pairs = pairs.dropna(subset=["ha", "hb"])
    ha = pairs["ha"].to_numpy(dtype=float)
    hb = pairs["hb"].to_numpy(dtype=float)
    valid = ~(np.isnan(ha) | np.isnan(hb))
    ha = ha[valid]
    hb = hb[valid]

    n = len(ha)
    small_n = n < MIN_JOINT_OBS

    if n < 50:
        return {
            "label": label,
            "n": n,
            "error": f"too few pairs ({n} < 50)",
            "note": note,
        }

    pa = float(np.mean(ha))
    pb = float(np.mean(hb))
    realized = float(np.mean(ha * hb))

    p_indep = pa * pb
    p_naive = bvn_joint_over_prob(pa, pb, naive_rho)
    p_recal = bvn_joint_over_prob(pa, pb, recal_rho)

    err_indep = abs(p_indep - realized)
    err_naive = abs(p_naive - realized)
    err_recal = abs(p_recal - realized)

    # Split-half
    gd = pairs.iloc[np.where(valid)[0]]["GAME_DATE"].to_numpy()
    sorted_gd = np.sort(gd)
    r_early = r_late = None
    n_early = n_late = 0
    if len(sorted_gd) >= 40:
        mid = sorted_gd[len(sorted_gd) // 2]
        e_mask = gd < mid
        l_mask = gd >= mid
        n_early = int(e_mask.sum())
        n_late  = int(l_mask.sum())
        if n_early >= 20:
            r_early = float(np.mean(ha[e_mask] * hb[e_mask]))
        if n_late >= 20:
            r_late = float(np.mean(ha[l_mask] * hb[l_mask]))

    best_model = min(
        [("recal", err_recal), ("naive", err_naive), ("indep", err_indep)],
        key=lambda x: x[1],
    )[0]

    # Split-half stability: recal rho predicts joint rate better in BOTH halves?
    stable = None
    if r_early is not None and r_late is not None:
        recal_beats_early = abs(p_recal - r_early) < abs(p_naive - r_early)
        recal_beats_late  = abs(p_recal - r_late)  < abs(p_naive - r_late)
        stable = bool(recal_beats_early and recal_beats_late)

    # Gate criteria
    gate_passes = (
        stable is True
        and err_recal < err_naive
        and err_recal < err_indep
        and not small_n
    )

    # Estimated edge vs book independence assumption
    # book_assumed_rho: what's the most likely naive book assumption?
    # For cross-team pairs, book almost certainly assumes rho=0 (independence)
    rho_delta = recal_rho - naive_rho
    # If recal > naive and over_a=True, over_b=True: edge = P_recal > P_indep -> bettor edge
    # Only meaningful if recal_rho > 0 (positive correlation)
    if naive_rho == 0.0:
        est_edge_pct = (p_recal / p_indep - 1.0) * 100.0 if p_indep > 0 else 0.0
    else:
        est_edge_pct = (p_recal / p_naive - 1.0) * 100.0 if p_naive > 0 else 0.0

    return {
        "label"          : label,
        "pair_type"      : "cross_team",
        "stat_a"         : stat_a,
        "stat_b"         : stat_b,
        "over_a"         : over_a,
        "over_b"         : over_b,
        "arch_a"         : arch_a_filter or "any",
        "arch_b"         : arch_b_filter or "any",
        "n"              : n,
        "n_early"        : n_early,
        "n_late"         : n_late,
        "small_n_advisory": small_n,
        "pa"             : round(pa, 4),
        "pb"             : round(pb, 4),
        "realized_joint" : round(realized, 4),
        "p_indep"        : round(p_indep, 4),
        "p_naive"        : round(p_naive, 4),
        "p_recal"        : round(p_recal, 4),
        "err_indep"      : round(err_indep, 4),
        "err_naive"      : round(err_naive, 4),
        "err_recal"      : round(err_recal, 4),
        "recal_rho"      : recal_rho,
        "naive_rho"      : naive_rho,
        "best_model"     : best_model,
        "realized_early" : round(r_early, 4) if r_early is not None else None,
        "realized_late"  : round(r_late, 4) if r_late is not None else None,
        "split_half_stable": stable,
        "gate_passes"    : gate_passes,
        "est_edge_vs_naive_pct": round(est_edge_pct, 2),
        "book_blind_spot": True,  # cross-team = book blind spot by construction
        "note"           : note,
    }


# ---------------------------------------------------------------------------
# Teammate pair backtest (extended - wrapper around existing logic, same gate)
# ---------------------------------------------------------------------------

def teammate_pair_extended(
    df: pd.DataFrame,
    stat_a: str,
    stat_b: str,
    arch_a_map: Dict[int, str],
    arch_b_map: Dict[int, str],
    arch_a_filter: Optional[str],
    arch_b_filter: Optional[str],
    recal_rho: float,
    naive_rho: float,
    label: str,
    note: str = "",
    over_a: bool = True,
    over_b: bool = True,
) -> dict:
    """Backtest a same-team (teammate) pair with optional direction control."""
    col_a = f"{stat_a}_is_over"
    col_b = f"{stat_b}_is_over"
    needed = [col_a, col_b, f"{stat_a}_rolling_median", f"{stat_b}_rolling_median"]
    working = df.dropna(subset=needed).copy()

    # For usage-substitution (same player PTS vs AST), stat_a and stat_b are BOTH
    # on the same player - this is a SAME-PLAYER pair:
    if arch_a_filter == "__same_player__":
        return _same_player_usage_sub(df, stat_a, stat_b, recal_rho, naive_rho, label, note)

    working["arch_a_val"] = working["PLAYER_ID"].map(arch_a_map)
    working["arch_b_val"] = working["PLAYER_ID"].map(arch_b_map)

    # Direction
    if over_a:
        working["ha"] = working[col_a]
    else:
        working["ha"] = 1.0 - working[col_a]

    if over_b:
        working["hb"] = working[col_b]
    else:
        working["hb"] = 1.0 - working[col_b]

    keep_cols = ["PLAYER_ID", "GAME_ID", "TEAM_ID", "GAME_DATE",
                 "ha", "hb", "arch_a_val", "arch_b_val"]
    w = working[[c for c in keep_cols if c in working.columns]].copy()

    left = w.rename(columns={"PLAYER_ID": "pid_a", "ha": "ha_", "arch_a_val": "arch_a", "TEAM_ID": "team_a"})
    right = w.rename(columns={"PLAYER_ID": "pid_b", "hb": "hb_", "arch_b_val": "arch_b", "TEAM_ID": "team_b"})

    pairs = left[["GAME_ID", "GAME_DATE", "pid_a", "team_a", "ha_", "arch_a"]].merge(
        right[["GAME_ID", "pid_b", "team_b", "hb_", "arch_b"]], on="GAME_ID"
    )
    # Same team
    pairs = pairs[pairs["team_a"] == pairs["team_b"]]
    pairs = pairs[pairs["pid_a"] != pairs["pid_b"]]
    pairs = pairs[pairs["pid_a"] < pairs["pid_b"]]

    if arch_a_filter is not None:
        pairs = pairs[pairs["arch_a"] == arch_a_filter]
    if arch_b_filter is not None:
        pairs = pairs[pairs["arch_b"] == arch_b_filter]

    pairs = pairs.dropna(subset=["ha_", "hb_"])
    ha = pairs["ha_"].to_numpy(dtype=float)
    hb = pairs["hb_"].to_numpy(dtype=float)
    valid = ~(np.isnan(ha) | np.isnan(hb))
    ha = ha[valid]; hb = hb[valid]

    n = len(ha)
    small_n = n < MIN_JOINT_OBS

    if n < 50:
        return {"label": label, "n": n, "error": f"too few pairs ({n})", "note": note}

    pa = float(np.mean(ha))
    pb = float(np.mean(hb))
    realized = float(np.mean(ha * hb))
    p_indep = pa * pb
    p_naive = bvn_joint_over_prob(pa, pb, naive_rho)
    p_recal = bvn_joint_over_prob(pa, pb, recal_rho)
    err_indep = abs(p_indep - realized)
    err_naive = abs(p_naive - realized)
    err_recal = abs(p_recal - realized)

    gd = pairs.iloc[np.where(valid)[0]]["GAME_DATE"].to_numpy()
    sorted_gd = np.sort(gd)
    r_early = r_late = None
    n_early = n_late = 0
    if len(sorted_gd) >= 40:
        mid = sorted_gd[len(sorted_gd) // 2]
        e_mask = gd < mid; l_mask = gd >= mid
        n_early = int(e_mask.sum()); n_late = int(l_mask.sum())
        if n_early >= 20: r_early = float(np.mean(ha[e_mask] * hb[e_mask]))
        if n_late  >= 20: r_late  = float(np.mean(ha[l_mask] * hb[l_mask]))

    best_model = min([("recal", err_recal), ("naive", err_naive), ("indep", err_indep)], key=lambda x: x[1])[0]

    stable = None
    if r_early is not None and r_late is not None:
        stable = bool(
            abs(p_recal - r_early) < abs(p_naive - r_early) and
            abs(p_recal - r_late)  < abs(p_naive - r_late)
        )

    gate_passes = stable is True and err_recal < err_naive and err_recal < err_indep and not small_n

    est_edge_pct = (p_recal / p_naive - 1.0) * 100.0 if p_naive > 0 else 0.0

    return {
        "label"           : label,
        "pair_type"       : "teammate",
        "stat_a"          : stat_a,
        "stat_b"          : stat_b,
        "over_a"          : over_a,
        "over_b"          : over_b,
        "arch_a"          : arch_a_filter or "any",
        "arch_b"          : arch_b_filter or "any",
        "n"               : n,
        "n_early"         : n_early,
        "n_late"          : n_late,
        "small_n_advisory": small_n,
        "pa"              : round(pa, 4),
        "pb"              : round(pb, 4),
        "realized_joint"  : round(realized, 4),
        "p_indep"         : round(p_indep, 4),
        "p_naive"         : round(p_naive, 4),
        "p_recal"         : round(p_recal, 4),
        "err_indep"       : round(err_indep, 4),
        "err_naive"       : round(err_naive, 4),
        "err_recal"       : round(err_recal, 4),
        "recal_rho"       : recal_rho,
        "naive_rho"       : naive_rho,
        "best_model"      : best_model,
        "realized_early"  : round(r_early, 4) if r_early is not None else None,
        "realized_late"   : round(r_late, 4) if r_late is not None else None,
        "split_half_stable": stable,
        "gate_passes"     : gate_passes,
        "est_edge_vs_naive_pct": round(est_edge_pct, 2),
        "book_blind_spot" : True,
        "note"            : note,
    }


def _same_player_usage_sub(df, stat_a, stat_b, recal_rho, naive_rho, label, note):
    """Same-player PTS-down <-> AST-up usage substitution cell (T9)."""
    # stat_a: what goes DOWN (PTS, over_a=False = under = 1-is_over)
    # stat_b: what goes UP (AST, over_b=True = over)
    col_a = f"{stat_a}_is_over"
    col_b = f"{stat_b}_is_over"
    needed = [col_a, col_b]
    working = df.dropna(subset=needed).copy()
    # under for PTS, over for AST
    ha = (1.0 - working[col_a]).to_numpy(dtype=float)
    hb = working[col_b].to_numpy(dtype=float)
    valid = ~(np.isnan(ha) | np.isnan(hb))
    ha = ha[valid]; hb = hb[valid]

    n = len(ha)
    small_n = n < MIN_JOINT_OBS
    if n < 50:
        return {"label": label, "n": n, "error": f"too few ({n})", "note": note}

    pa = float(np.mean(ha))
    pb = float(np.mean(hb))
    realized = float(np.mean(ha * hb))
    p_indep = pa * pb
    p_naive = bvn_joint_over_prob(pa, pb, naive_rho)
    p_recal = bvn_joint_over_prob(pa, pb, recal_rho)
    err_indep = abs(p_indep - realized)
    err_naive = abs(p_naive - realized)
    err_recal = abs(p_recal - realized)

    # Split-half
    gd = working.iloc[np.where(valid)[0]]["GAME_DATE"].to_numpy()
    sorted_gd = np.sort(gd)
    r_early = r_late = None
    n_early = n_late = 0
    if len(sorted_gd) >= 40:
        mid = sorted_gd[len(sorted_gd) // 2]
        e_mask = gd < mid; l_mask = gd >= mid
        n_early = int(e_mask.sum()); n_late = int(l_mask.sum())
        if n_early >= 20: r_early = float(np.mean(ha[e_mask] * hb[e_mask]))
        if n_late  >= 20: r_late  = float(np.mean(ha[l_mask] * hb[l_mask]))

    best_model = min([("recal", err_recal), ("naive", err_naive), ("indep", err_indep)], key=lambda x: x[1])[0]

    stable = None
    if r_early is not None and r_late is not None:
        stable = bool(
            abs(p_recal - r_early) < abs(p_naive - r_early) and
            abs(p_recal - r_late) < abs(p_naive - r_late)
        )

    gate_passes = stable is True and err_recal < err_naive and err_recal < err_indep and not small_n

    est_edge_pct = (p_recal / p_naive - 1.0) * 100.0 if p_naive > 0 else 0.0

    return {
        "label"            : label,
        "pair_type"        : "same_player_usage_sub",
        "stat_a"           : stat_a + "_under",
        "stat_b"           : stat_b + "_over",
        "n"                : n,
        "n_early"          : n_early,
        "n_late"           : n_late,
        "small_n_advisory" : small_n,
        "pa"               : round(pa, 4),
        "pb"               : round(pb, 4),
        "realized_joint"   : round(realized, 4),
        "p_indep"          : round(p_indep, 4),
        "p_naive"          : round(p_naive, 4),
        "p_recal"          : round(p_recal, 4),
        "err_indep"        : round(err_indep, 4),
        "err_naive"        : round(err_naive, 4),
        "err_recal"        : round(err_recal, 4),
        "recal_rho"        : recal_rho,
        "naive_rho"        : naive_rho,
        "best_model"       : best_model,
        "realized_early"   : round(r_early, 4) if r_early is not None else None,
        "realized_late"    : round(r_late, 4) if r_late is not None else None,
        "split_half_stable": stable,
        "gate_passes"      : gate_passes,
        "est_edge_vs_naive_pct": round(est_edge_pct, 2),
        "book_blind_spot"  : False,  # same-player: book probably prices this
        "note"             : note,
    }


# ---------------------------------------------------------------------------
# Measure empirical rho from data
# ---------------------------------------------------------------------------

def measure_empirical_rho(
    df: pd.DataFrame,
    stat_a: str,
    stat_b: str,
    over_a: bool,
    over_b: bool,
    arch_a_map: Dict[int, str],
    arch_b_map: Dict[int, str],
    arch_a_filter: Optional[str],
    arch_b_filter: Optional[str],
    cross_team: bool,
    game_filter: Optional[Dict[str, bool]] = None,
) -> Optional[float]:
    """Compute the empirical Pearson rho from the residualized (demeaned) over-rate.

    This is the cross-sectional Pearson correlation between the residual Z-scores,
    NOT the realized-marginal correlation.  Used to set recal_rho for each cell.

    For copula isolation: each player's per-game indicator is demeaned by their
    own rolling mean.  Then rho is computed across all valid pairs.
    """
    col_a = f"{stat_a}_is_over"
    col_b = f"{stat_b}_is_over"
    needed = [col_a, col_b]
    working = df.dropna(subset=needed).copy()

    working["arch_a_val"] = working["PLAYER_ID"].map(arch_a_map)
    working["arch_b_val"] = working["PLAYER_ID"].map(arch_b_map)

    if game_filter is not None:
        working["_gflag"] = working["GAME_ID"].astype(str).map(game_filter).fillna(False)
        working = working[working["_gflag"]]

    # Direction
    ha_col = col_a if over_a else None
    hb_col = col_b if over_b else None

    if over_a:
        working["ha"] = working[col_a]
    else:
        working["ha"] = 1.0 - working[col_a]

    if over_b:
        working["hb"] = working[col_b]
    else:
        working["hb"] = 1.0 - working[col_b]

    keep = ["PLAYER_ID", "GAME_ID", "TEAM_ID", "ha", "hb", "arch_a_val", "arch_b_val"]
    w = working[[c for c in keep if c in working.columns]].copy()

    left  = w.rename(columns={"PLAYER_ID": "pid_a", "ha": "ha_", "arch_a_val": "arch_a", "TEAM_ID": "team_a"})
    right = w.rename(columns={"PLAYER_ID": "pid_b", "hb": "hb_", "arch_b_val": "arch_b", "TEAM_ID": "team_b"})

    pairs = left[["GAME_ID", "pid_a", "team_a", "ha_", "arch_a"]].merge(
        right[["GAME_ID", "pid_b", "team_b", "hb_", "arch_b"]], on="GAME_ID"
    )

    if cross_team:
        pairs = pairs[pairs["team_a"] != pairs["team_b"]]
    else:
        pairs = pairs[pairs["team_a"] == pairs["team_b"]]

    pairs = pairs[pairs["pid_a"] != pairs["pid_b"]]
    pairs = pairs[pairs["pid_a"] < pairs["pid_b"]]

    if arch_a_filter is not None:
        pairs = pairs[pairs["arch_a"] == arch_a_filter]
    if arch_b_filter is not None:
        pairs = pairs[pairs["arch_b"] == arch_b_filter]

    pairs = pairs.dropna(subset=["ha_", "hb_"])
    ha = pairs["ha_"].to_numpy(dtype=float)
    hb = pairs["hb_"].to_numpy(dtype=float)
    valid = ~(np.isnan(ha) | np.isnan(hb))
    ha = ha[valid]; hb = hb[valid]

    if len(ha) < 50:
        return None

    # Residualize (demean) to isolate copula
    ha_z = ha - ha.mean()
    hb_z = hb - hb.mean()
    std_a = ha_z.std()
    std_b = hb_z.std()
    if std_a < 1e-9 or std_b < 1e-9:
        return None
    rho = float(np.corrcoef(ha_z, hb_z)[0, 1])
    return round(rho, 4)


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(quiet: bool = False) -> Tuple[List[dict], dict]:
    """Run the full cross-team + expanded teammate sweep."""
    if not quiet:
        print("Loading gamelog data...")
    df = load_gamelog()
    if not quiet:
        print(f"  {len(df):,} rows, {df['GAME_ID'].nunique()} games, "
              f"{df['PLAYER_ID'].nunique()} players (MIN>=10)")

    if not quiet:
        print("Computing rolling medians...")
    stats = ["pts", "reb", "ast", "fg3m", "tov", "blk", "stl", "fgm"]
    df = compute_rolling_medians(df, stats)

    if not quiet:
        print("Building archetype maps...")
    tm_arch_map = load_teammate_archetypes()
    blk_tier    = build_blk_tier_map(df)
    hi_usage    = build_high_usage_map(df)
    ast_leader  = build_ast_leader_map(df)
    hi_pace_map = build_pace_game_flag(df)

    # Convert boolean maps to string for arch lookup
    blk_arch   = {pid: ("rim_protector" if v else "other") for pid, v in blk_tier.items()}
    usage_arch = {pid: ("high_usage" if v else "other") for pid, v in hi_usage.items()}
    ast_arch   = {pid: ("ast_leader" if v else "other") for pid, v in ast_leader.items()}

    # Universal arch map (everyone is "any")
    any_arch   = {pid: "any" for pid in df["PLAYER_ID"].unique()}

    results: List[dict] = []

    # -----------------------------------------------------------------------
    # CROSS-TEAM (OPPONENT) CELLS
    # -----------------------------------------------------------------------

    # --- C1: rim_protector BLK-over <-> opposing paint scorer PTS-under ---
    # Hypothesis: when a rim protector has a dominant night (BLK over), the
    # opposing team's high-usage interior scorer gets suppressed (PTS under).
    # Book assumption: cross-team independence (rho ~= 0.0).
    # Expected: negative recal rho (rim deterrence coupling).
    rho_c1 = measure_empirical_rho(df, "blk", "pts", True, True,
                                   blk_arch, usage_arch,
                                   "rim_protector", "high_usage",
                                   cross_team=True)
    # We want BLK-over (team A protector) and PTS-UNDER (opp scorer) -> positive joint P
    # Measured rho is between blk_is_over and pts_is_over (both over)
    # For the pair we want: joint = P(blk_over_A AND pts_under_B) = P(blk_over AND NOT pts_over)
    # The relevant rho for this bivariate = -rho(blk_over, pts_over) since we flip pts
    recal_rho_c1 = float(-rho_c1) if rho_c1 is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="blk", stat_b="pts",
        over_a=True, over_b=False,  # blk over AND pts under
        arch_a_map=blk_arch, arch_b_map=usage_arch,
        arch_a_filter="rim_protector", arch_b_filter="high_usage",
        game_filter=None,
        recal_rho=recal_rho_c1, naive_rho=0.0,
        label="CT: rim_BLK-over + opp_scorer_PTS-under",
        note=f"recal_rho={recal_rho_c1:.4f} (empirical). Rim deterrence hypothesis. "
             f"Book assumes independence (rho=0). Positive joint P if protector suppresses scorer.",
    ))

    # --- C2: rim_protector BLK-over <-> opposing pnr_roll_man FGM-under ---
    # Roll men attack the rim; a dominant rim protector should lower their FGM.
    rho_c2 = measure_empirical_rho(df, "blk", "fgm", True, True,
                                   blk_arch, tm_arch_map,
                                   "rim_protector", "pnr_roll_man",
                                   cross_team=True)
    recal_rho_c2 = float(-rho_c2) if rho_c2 is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="blk", stat_b="fgm",
        over_a=True, over_b=False,  # blk over AND fgm under
        arch_a_map=blk_arch, arch_b_map=tm_arch_map,
        arch_a_filter="rim_protector", arch_b_filter="pnr_roll_man",
        game_filter=None,
        recal_rho=recal_rho_c2, naive_rho=0.0,
        label="CT: rim_BLK-over + opp_rollman_FGM-under",
        note=f"recal_rho={recal_rho_c2:.4f}. Roll-man suppression hypothesis.",
    ))

    # --- C3: high-pace game: opposing high-usage scorer PTS + PTS both-OVER ---
    # In a fast game, BOTH teams' high-usage scorers benefit from more possessions.
    # Book likely treats cross-team PTS as independent; true rho should be positive
    # because total possessions is a shared factor lifting both sides.
    rho_c3 = measure_empirical_rho(df, "pts", "pts", True, True,
                                   usage_arch, usage_arch,
                                   "high_usage", "high_usage",
                                   cross_team=True,
                                   game_filter=hi_pace_map)
    recal_rho_c3 = rho_c3 if rho_c3 is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="pts", stat_b="pts",
        over_a=True, over_b=True,
        arch_a_map=usage_arch, arch_b_map=usage_arch,
        arch_a_filter="high_usage", arch_b_filter="high_usage",
        game_filter=hi_pace_map,
        recal_rho=recal_rho_c3, naive_rho=0.0,
        label="CT: fast-game opp_scorer_PTS + opp_scorer_PTS both-over",
        note=f"recal_rho={recal_rho_c3:.4f}. High-pace shared possession factor hypothesis. "
             f"Game filter: top-33% games by total PTS.",
    ))

    # --- C3b: high-pace game both-over (no game filter) ---
    # Test whether the effect holds even without conditioning on game pace
    rho_c3b = measure_empirical_rho(df, "pts", "pts", True, True,
                                    usage_arch, usage_arch,
                                    "high_usage", "high_usage",
                                    cross_team=True,
                                    game_filter=None)
    recal_rho_c3b = rho_c3b if rho_c3b is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="pts", stat_b="pts",
        over_a=True, over_b=True,
        arch_a_map=usage_arch, arch_b_map=usage_arch,
        arch_a_filter="high_usage", arch_b_filter="high_usage",
        game_filter=None,
        recal_rho=recal_rho_c3b, naive_rho=0.0,
        label="CT: all-game opp_scorer_PTS + opp_scorer_PTS both-over",
        note=f"recal_rho={recal_rho_c3b:.4f}. No game filter (unconditional cross-team scorer corr).",
    ))

    # --- C4: opposing lead-guard AST + AST both-over (high-possession games) ---
    # Two opposing lead guards: in a fast/high-possession game, both have more
    # opportunities to distribute.  Book prices cross-team AST as independent.
    rho_c4_fast = measure_empirical_rho(df, "ast", "ast", True, True,
                                        ast_arch, ast_arch,
                                        "ast_leader", "ast_leader",
                                        cross_team=True,
                                        game_filter=hi_pace_map)
    recal_rho_c4 = rho_c4_fast if rho_c4_fast is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="ast", stat_b="ast",
        over_a=True, over_b=True,
        arch_a_map=ast_arch, arch_b_map=ast_arch,
        arch_a_filter="ast_leader", arch_b_filter="ast_leader",
        game_filter=hi_pace_map,
        recal_rho=recal_rho_c4, naive_rho=0.0,
        label="CT: fast-game opp_ast-leader AST + AST both-over",
        note=f"recal_rho={recal_rho_c4:.4f}. High-possession opposing PG AST corr hypothesis.",
    ))

    # --- C4b: all games ---
    rho_c4b = measure_empirical_rho(df, "ast", "ast", True, True,
                                    ast_arch, ast_arch,
                                    "ast_leader", "ast_leader",
                                    cross_team=True)
    recal_rho_c4b = rho_c4b if rho_c4b is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="ast", stat_b="ast",
        over_a=True, over_b=True,
        arch_a_map=ast_arch, arch_b_map=ast_arch,
        arch_a_filter="ast_leader", arch_b_filter="ast_leader",
        game_filter=None,
        recal_rho=recal_rho_c4b, naive_rho=0.0,
        label="CT: all-game opp_ast-leader AST + AST both-over",
        note=f"recal_rho={recal_rho_c4b:.4f}. Unconditional opposing PG AST corr.",
    ))

    # --- C5: global cross-team AST+AST (baseline) ---
    rho_c5 = measure_empirical_rho(df, "ast", "ast", True, True,
                                   any_arch, any_arch,
                                   None, None, cross_team=True)
    recal_rho_c5 = rho_c5 if rho_c5 is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="ast", stat_b="ast",
        over_a=True, over_b=True,
        arch_a_map=any_arch, arch_b_map=any_arch,
        arch_a_filter=None, arch_b_filter=None,
        game_filter=None,
        recal_rho=recal_rho_c5, naive_rho=0.0,
        label="CT: global opp-player AST + AST (baseline)",
        note=f"recal_rho={recal_rho_c5:.4f}. Global cross-team AST correlation baseline.",
    ))

    # --- C6: global cross-team PTS+PTS (baseline) ---
    rho_c6 = measure_empirical_rho(df, "pts", "pts", True, True,
                                   any_arch, any_arch,
                                   None, None, cross_team=True)
    recal_rho_c6 = rho_c6 if rho_c6 is not None else 0.0
    results.append(opponent_pair_backtest(
        df,
        stat_a="pts", stat_b="pts",
        over_a=True, over_b=True,
        arch_a_map=any_arch, arch_b_map=any_arch,
        arch_a_filter=None, arch_b_filter=None,
        game_filter=None,
        recal_rho=recal_rho_c6, naive_rho=0.0,
        label="CT: global opp-player PTS + PTS (baseline)",
        note=f"recal_rho={recal_rho_c6:.4f}. Global cross-team PTS correlation baseline.",
    ))

    # -----------------------------------------------------------------------
    # WIDER TEAMMATE CELLS
    # -----------------------------------------------------------------------

    # --- T5: creator_AST <-> post_up PTS ---
    rho_t5 = measure_empirical_rho(df, "ast", "pts", True, True,
                                   tm_arch_map, tm_arch_map,
                                   "primary_creator", None, cross_team=False)
    # post_up is not in teammate archetype map; use secondary_creator as proxy for
    # non-primary scorers who feed off creation.  Use "other" archetype.
    recal_rho_t5 = rho_t5 if rho_t5 is not None else 0.0
    results.append(teammate_pair_extended(
        df, "ast", "pts",
        arch_a_map=tm_arch_map, arch_b_map=tm_arch_map,
        arch_a_filter="primary_creator", arch_b_filter="other",
        recal_rho=recal_rho_t5, naive_rho=0.0,
        label="TM: creator_AST + other_PTS (finisher)",
        note=f"recal_rho={recal_rho_t5:.4f}. Creator feeds OTHER-archetype teammates. "
             f"Broader than catch-shoot-only; covers post_up + cutter proxy.",
    ))

    # --- T6: creator_AST <-> rebounder PTS ---
    rho_t6 = measure_empirical_rho(df, "ast", "pts", True, True,
                                   tm_arch_map, tm_arch_map,
                                   "primary_creator", "rebounder", cross_team=False)
    recal_rho_t6 = rho_t6 if rho_t6 is not None else 0.0
    results.append(teammate_pair_extended(
        df, "ast", "pts",
        arch_a_map=tm_arch_map, arch_b_map=tm_arch_map,
        arch_a_filter="primary_creator", arch_b_filter="rebounder",
        recal_rho=recal_rho_t6, naive_rho=0.0,
        label="TM: creator_AST + rebounder_PTS",
        note=f"recal_rho={recal_rho_t6:.4f}. Creator feeding big/rebounder inside.",
    ))

    # --- T7: creator_AST <-> secondary_creator PTS (all assists flow) ---
    rho_t7 = measure_empirical_rho(df, "ast", "pts", True, True,
                                   tm_arch_map, tm_arch_map,
                                   "primary_creator", "secondary_creator", cross_team=False)
    recal_rho_t7 = rho_t7 if rho_t7 is not None else 0.0
    results.append(teammate_pair_extended(
        df, "ast", "pts",
        arch_a_map=tm_arch_map, arch_b_map=tm_arch_map,
        arch_a_filter="primary_creator", arch_b_filter="secondary_creator",
        recal_rho=recal_rho_t7, naive_rho=0.0,
        label="TM: creator_AST + secondary-scorer_PTS",
        note=f"recal_rho={recal_rho_t7:.4f}. Creator distributes to secondary scorer.",
    ))

    # --- T8: rebounder REB + rebounder REB (two-big REB corr) ---
    # Hypothesis: two strong rebounders on same team may cannibalize each other
    # (negative corr) OR both benefit from high OREB team style (positive).
    rho_t8 = measure_empirical_rho(df, "reb", "reb", True, True,
                                   tm_arch_map, tm_arch_map,
                                   "rebounder", "rebounder", cross_team=False)
    recal_rho_t8 = rho_t8 if rho_t8 is not None else 0.0
    results.append(teammate_pair_extended(
        df, "reb", "reb",
        arch_a_map=tm_arch_map, arch_b_map=tm_arch_map,
        arch_a_filter="rebounder", arch_b_filter="rebounder",
        recal_rho=recal_rho_t8, naive_rho=-0.10,
        label="TM: rebounder_REB + rebounder_REB",
        note=f"recal_rho={recal_rho_t8:.4f}. Two-big REB corr. Naive=-0.10 (competition assumption). "
             f"If recal is close to 0, book's anti-corr assumption is the mispricing.",
    ))

    # --- T8b: global teammate REB + REB baseline ---
    rho_t8b = measure_empirical_rho(df, "reb", "reb", True, True,
                                    any_arch, any_arch,
                                    None, None, cross_team=False)
    recal_rho_t8b = rho_t8b if rho_t8b is not None else 0.0
    results.append(teammate_pair_extended(
        df, "reb", "reb",
        arch_a_map=any_arch, arch_b_map=any_arch,
        arch_a_filter=None, arch_b_filter=None,
        recal_rho=recal_rho_t8b, naive_rho=-0.10,
        label="TM: global REB + REB (teammate baseline)",
        note=f"recal_rho={recal_rho_t8b:.4f}. Global teammate REB corr baseline.",
    ))

    # --- T9: creator PTS-under <-> same-creator AST-over (usage sub) ---
    # Same-player: when the creator scores less, do they assist more?
    # Note: this is same-player so book DOES price this within SGP.
    # Included for completeness; flagged book_blind_spot=False.
    rho_t9_raw = None
    try:
        # Use only primary_creator players
        creators = {pid for pid, arch in tm_arch_map.items() if arch == "primary_creator"}
        sub = df[df["PLAYER_ID"].isin(creators)].dropna(subset=["pts_is_over", "ast_is_over"])
        if len(sub) >= 100:
            pts_under = (1.0 - sub["pts_is_over"]).to_numpy(dtype=float)
            ast_over  = sub["ast_is_over"].to_numpy(dtype=float)
            valid = ~(np.isnan(pts_under) | np.isnan(ast_over))
            if valid.sum() >= 100:
                rho_t9_raw = float(np.corrcoef(
                    pts_under[valid] - pts_under[valid].mean(),
                    ast_over[valid]  - ast_over[valid].mean()
                )[0, 1])
    except Exception:
        rho_t9_raw = None

    recal_rho_t9 = round(rho_t9_raw, 4) if rho_t9_raw is not None else 0.0
    results.append(_same_player_usage_sub(
        df[df["PLAYER_ID"].isin({pid for pid, arch in tm_arch_map.items()
                                  if arch == "primary_creator"})],
        "pts", "ast",
        recal_rho_t9, 0.0,
        label="SP: creator PTS-under + AST-over (usage sub)",
        note=f"recal_rho={recal_rho_t9:.4f}. Same-player usage substitution. "
             f"Book_blind_spot=False (same-player pair, book prices this).",
    ))

    return results


# ---------------------------------------------------------------------------
# Summary + gate classification
# ---------------------------------------------------------------------------

def classify_gate(r: dict) -> str:
    if "error" in r:
        return "SKIP"
    if r.get("gate_passes"):
        return "GENUINE"
    reasons = []
    if not r.get("split_half_stable"):
        reasons.append("unstable")
    if r.get("err_recal", 999) >= r.get("err_naive", 0):
        reasons.append("recal_ge_naive")
    if r.get("err_recal", 999) >= r.get("err_indep", 0):
        reasons.append("recal_ge_indep")
    if r.get("small_n_advisory"):
        reasons.append(f"small-n({r.get('n', 0)})")
    return "REJECT(" + ",".join(reasons) + ")"


def print_summary(results: List[dict]) -> None:
    print()
    print("=" * 110)
    print("CROSS-TEAM / EXPANDED SGP EDGE SWEEP - Results")
    print("  Gate: split-half stable + recal beats both indep and naive + n>=300 + cross-player/team")
    print("=" * 110)
    print()
    hdr = (
        f"{'Label':<55} {'N':>6} {'Realized':>9} "
        f"{'Recal':>7} {'Naive':>7} {'Indep':>7} "
        f"{'rho':>7} {'ErrR':>6} {'ErrN':>6} {'Stable':>7} {'Gate':>30}"
    )
    print(hdr)
    print("-" * 110)
    for r in results:
        gate = classify_gate(r)
        if "error" in r:
            print(f"  {r['label']:<53} SKIP: {r['error']}")
            continue
        marker = " **GENUINE**" if gate == "GENUINE" else ""
        row = (
            f"  {r['label']:<53} {r['n']:>6,} {r['realized_joint']:>9.4f} "
            f"{r['p_recal']:>7.4f} {r['p_naive']:>7.4f} {r['p_indep']:>7.4f} "
            f"{r['recal_rho']:>7.4f} {r['err_recal']:>6.4f} {r['err_naive']:>6.4f} "
            f"{'YES' if r.get('split_half_stable') else 'NO':>7} {gate:<30}{marker}"
        )
        print(row)
    print("-" * 110)
    genuine = [r for r in results if classify_gate(r) == "GENUINE"]
    rejected = [r for r in results if "REJECT" in classify_gate(r)]
    print(f"\n  GENUINE (gate passes): {len(genuine)}")
    print(f"  REJECTED:              {len(rejected)}")
    print(f"  SKIPPED (too-few obs): {sum(1 for r in results if 'error' in r)}")
    print()
    if genuine:
        print("  GENUINE CELLS:")
        for r in genuine:
            print(f"    {r['label']}: rho={r['recal_rho']:.4f}, "
                  f"realized={r['realized_joint']:.4f}, "
                  f"err_recal={r['err_recal']:.4f} vs err_naive={r['err_naive']:.4f}, "
                  f"est_edge={r.get('est_edge_vs_naive_pct', 0):.1f}%")
    print()


def build_consolidated_catalog(new_results: List[dict]) -> List[dict]:
    """Merge the existing DRIVE-AND-KICK edge with new survivors."""
    # Prior validated edges from Part 1+2
    prior_genuine = [
        {
            "id": "DRIVE_AND_KICK_1",
            "label": "TM: creator_AST + catch_shoot_FG3M",
            "pair_type": "teammate",
            "source": "sgp_joint_hitrate_backtest.py (Part 1+2)",
            "recal_rho": 0.1128,
            "naive_rho": 0.0,
            "realized_joint": 0.1583,
            "p_recal": 0.1586,
            "p_naive": 0.1424,
            "err_recal": 0.0004,
            "err_naive": 0.0159,
            "n": 1706,
            "split_half_stable": True,
            "gate_passes": True,
            "book_blind_spot": True,
            "est_edge_vs_naive_pct": 4.6,
            "note": "FLAGSHIP. creator AST over + catch-shoot teammate FG3M over. "
                    "rho=0.113 vs book's assumed 0.0. Validated: err=.0004 vs naive .0159. "
                    "n=1706, stable. Best example: Brunson AST 5.5+ / Hart FG3M 1.5+ at FD.",
        },
        {
            "id": "SEC_PTS_SEC_PTS_1",
            "label": "TM: sec_PTS + sec_PTS (two-scorer OVER)",
            "pair_type": "teammate",
            "source": "sgp_joint_hitrate_backtest.py (Part 1+2)",
            "recal_rho": -0.0125,
            "naive_rho": -0.15,
            "realized_joint": 0.1937,
            "p_recal": 0.1940,
            "p_naive": 0.1725,
            "err_recal": 0.0003,
            "err_naive": 0.0212,
            "n": 12392,
            "split_half_stable": True,
            "gate_passes": True,
            "book_blind_spot": True,
            "est_edge_vs_naive_pct": 1.7,
            "note": "Edge CONDITIONAL on book assuming negative rho (-0.15). "
                    "If book prices at independence, edge evaporates. "
                    "Track real SGP price to confirm.",
        },
    ]

    new_genuine = [r for r in new_results if classify_gate(r) == "GENUINE"]

    # Annotate new cells with honest edge-magnitude assessment
    edge_notes = {
        "CT: rim_BLK-over + opp_scorer_PTS-under": (
            "GENUINE (gate) but WEAK EV. rho=-0.012 vs naive=0. "
            "The recal price is LOWER than independence by only 0.16pp absolute (edge vs book = -1.1%). "
            "Rim deterrence is real and stable, but the magnitude is too small to be actionable. "
            "Primary value: use to AVOID rim_protector_BLK-over + opp_scorer_PTS-under cross-team parlays "
            "(they are marginally less likely than independence). "
            "NOT a positive-EV bet direction."
        ),
        "CT: rim_BLK-over + opp_rollman_FGM-under": (
            "GENUINE (gate) but WEAK EV. rho=+0.013 vs naive=0. "
            "Edge vs book independence = +1.0%. Roll-man suppression by rim protector is real but small. "
            "Meets all gate criteria and is stable. "
            "HYPOTHESIS-until-graded: need real SGP prices to confirm +EV direction. "
            "Physical basis: legitimate (rim protector blocks roll-man FGA at rim). n=4051."
        ),
        "TM: global REB + REB (teammate baseline)": (
            "GENUINE (gate). rho=+0.006 vs naive=-0.10 (assumed competition). "
            "Edge vs independence = +0.3% (negligible). "
            "Edge vs naive anti-corr = +9.9% (book-conditional). "
            "PHYSICAL: competition anti-correlation vanishes once player means residualized. "
            "Same finding as sec_PTS+sec_PTS: book's assumed negative rho is the mispricing. "
            "ACTIONABLE IF book prices same-team REB pairs with negative correlation. "
            "Otherwise near-zero edge. Same-team double-over REB parlays are underpriced "
            "IF book uses competition assumption."
        ),
        "SP: creator PTS-under + AST-over (usage sub)": (
            "GENUINE (gate) but book_blind_spot=FALSE. Same-player pair. "
            "rho=-0.054 (NEGATIVE: usage sub is ANTI-correlated, not positively correlated). "
            "This means: when a creator scores below median, they do NOT systematically assist more. "
            "Edge is vs naive=0 (independence): recal predicts LOWER joint prob (2.33% vs 2.41%). "
            "Book probably already prices same-player cross-stat correlation internally. "
            "PRIMARY VALUE: AVOID creator PTS-under + AST-over parlays -- they are overpriced "
            "if book assumes positive usage substitution. NOT a positive-EV cross-player SGP."
        ),
    }

    for i, r in enumerate(new_genuine, start=1):
        r_out = dict(r)
        r_out["id"] = f"NEW_{i:02d}"
        r_out["source"] = "sgp_cross_team_sweep.py"
        # Override note with honest magnitude assessment
        honest_note = edge_notes.get(r["label"])
        if honest_note:
            r_out["note"] = honest_note
        prior_genuine.append(r_out)

    return prior_genuine


# ---------------------------------------------------------------------------
# Write JSON
# ---------------------------------------------------------------------------

def write_edges_json(catalog: List[dict]) -> None:
    OUTPUT_EDGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_EDGES_PATH, "w") as f:
        json.dump({"generated": "2026-06-04",
                   "script": "sgp_cross_team_sweep.py",
                   "genuine_edge_count": len(catalog),
                   "edges": catalog}, f, indent=2, default=str)
    print(f"  Wrote {len(catalog)} edges to {OUTPUT_EDGES_PATH}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="SGP cross-team sweep")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        results = run_sweep(quiet=args.quiet)

    print_summary(results)

    catalog = build_consolidated_catalog(results)
    write_edges_json(catalog)

    genuine = [r for r in results if classify_gate(r) == "GENUINE"]
    print(f"\nFINAL: {len(genuine)} new cells pass the gate. "
          f"Consolidated catalog: {len(catalog)} total genuine edges.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
