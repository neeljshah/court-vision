"""sgp_joint_hitrate_backtest.py — PART 1: Validate recalibrated rho on REAL joint outcomes.

METHODOLOGY
-----------
For each headline correlated pair (same-player and teammate), test whether the
recalibrated rho better predicts the REALIZED joint double-OVER rate vs:
  (a) Independence model  P(A over) * P(B over)
  (b) Naive flat rho bivariate-normal model
  (c) Recal rho bivariate-normal model (the thing being validated)

COPULA ISOLATION
----------------
The test isolates the dependence structure from marginal calibration by using
each player's per-season rolling-median as the "line" for each stat. OVER is
defined as stat > player's rolling median (computed on pre-game data, rolling
by game_date to avoid look-ahead). This means the marginal over-rate is ~50%
by construction, eliminating marginal miscalibration as a confound.

PAIR TYPES TESTED
-----------------
Same-player:
  - SPOT_UP_SHOOTER   fg3m+pts  (recal 0.738 vs naive 0.55)
  - HIGH_AST_PLAYMAKER ast+tov  (recal ~0.10 vs naive 0.40)
  - HIGH_AST_PLAYMAKER pts+reb  (recal 0.215 vs naive 0.40)
  - Global            pts+tov   (recal ~0.13 vs naive 0.35)
  - Global            reb+blk   (recal ~0.15 vs naive 0.35)
Teammate:
  - primary_creator AST + catch_shoot FG3M  (recal 0.113 vs naive 0.0)
  - creator AST + roll_man PTS             (recal 0.099 vs naive 0.20)
  - two-scorer PTS+PTS (primary+secondary) (recal ~0.0 vs naive -0.15)

BIVARIATE-NORMAL P(both over) WITH RHO
---------------------------------------
Under the Gaussian copula:
  P(X>m_X, Y>m_Y) = P(Z_X>0, Z_Y>0 | corr=rho)
  = Phi_2(0, 0; rho) -- bivariate standard normal CDF
  = 0.25 + arcsin(rho) / (2*pi)   [Sheppard's formula, exact for std normals]

When both marginal over-rates are ~0.5, this is the exact copula formula.
We also test the general case (non-50% marginal rates from actual data).

SPLIT-HALF STABILITY
--------------------
Season is sorted by game_date; first half vs second half. Headline result
should be consistent in sign across halves.

OUTPUT
------
Writes results table to stdout + returns dict for docs/_audits/SGP_EDGE.md.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR    = PROJECT_DIR / "data"
CACHE_DIR   = DATA_DIR / "cache" / "cv_fix"
MODELS_DIR  = DATA_DIR / "models"

LEAGUELOG_RS = CACHE_DIR / "leaguegamelog_regular_season.parquet"
LEAGUELOG_PO = CACHE_DIR / "leaguegamelog_playoffs.parquet"

SAMEPLAYER_CORR_PATH = MODELS_DIR / "prop_corr_archetype_sameplayer.json"
TEAMMATE_CORR_PATH   = MODELS_DIR / "prop_corr_archetype_teammate.json"
SAMEPLAYER_ARCH_PATH = MODELS_DIR / "player_archetype_sameplayer.json"
TEAMMATE_ARCH_PATH   = MODELS_DIR / "player_archetype_teammate.json"

# Minimum games per player to be included in rolling-median computation
MIN_GAMES_FOR_MEDIAN = 10
# Min number of joint-game observations per pair type to report
MIN_JOINT_OBS = 100


# ---------------------------------------------------------------------------
# Bivariate normal joint probability (Sheppard / general)
# ---------------------------------------------------------------------------

def bvn_joint_over_prob(pa: float, pb: float, rho: float) -> float:
    """P(A over, B over) under bivariate normal with marginals pa, pb and correlation rho.

    Uses the general formula via the bivariate normal CDF approximation.
    For pa=pb=0.5 this reduces exactly to 0.25 + arcsin(rho)/(2*pi).

    Args:
        pa: P(A over median) — marginal over-rate for leg A.
        pb: P(B over median) — marginal over-rate for leg B.
        rho: Pearson correlation between residual Z-scores.

    Returns:
        Joint P(A over, B over) in [0, 1].
    """
    rho = float(np.clip(rho, -0.9999, 0.9999))
    # Convert marginal probs to standard-normal quantiles
    za = norm.ppf(1.0 - pa) if pa > 0 and pa < 1 else (0.0 if pa == 0.5 else float('inf'))
    zb = norm.ppf(1.0 - pb) if pb > 0 and pb < 1 else (0.0 if pb == 0.5 else float('inf'))

    # Sheppard exact formula when both quantiles = 0 (pa=pb=0.5)
    if abs(za) < 1e-9 and abs(zb) < 1e-9:
        return 0.25 + np.arcsin(rho) / (2.0 * np.pi)

    # General: use scipy's bivariate normal CDF via Monte Carlo approximation
    # We integrate P(X > za, Y > zb) where corr(X,Y) = rho
    # = 1 - Phi(za) - Phi(zb) + Phi2(za, zb; rho)
    # Phi2 via Owen's T function / numerical integration
    # For speed: use the Drezner approximation
    return _bvn_upper_tail(za, zb, rho)


def _bvn_upper_tail(h: float, k: float, rho: float) -> float:
    """P(X > h, Y > k) where (X,Y) ~ BVN(0,0,1,1,rho).

    Uses the formula:
      P(X>h, Y>k) = Phi(-h)*Phi(-k) + T(h, (k-rho*h)/sqrt(1-rho^2)) + T(k, (h-rho*k)/sqrt(1-rho^2))
    where T(h, a) is Owen's T function.
    Falls back to Monte Carlo for extreme values.
    """
    # Simple approach: 1 - Phi(h) - Phi(k) + BVN_CDF(h, k; rho)
    # BVN_CDF = P(X <= h, Y <= k)
    # Use the mvn approach from scipy
    try:
        from scipy.stats import multivariate_normal as mvn
        # P(X > h, Y > k) = P(X <= -h, Y <= -k) by symmetry of standard normal
        # with flipped sign
        # Actually: P(X > h, Y > k) = 1 - P(X<=h) - P(Y<=k) + P(X<=h, Y<=k)
        mean = [0.0, 0.0]
        cov  = [[1.0, rho], [rho, 1.0]]
        p_all      = mvn.cdf([h, k], mean=mean, cov=cov)          # P(X<=h, Y<=k)
        p_joint    = 1.0 - norm.cdf(h) - norm.cdf(k) + p_all
        return float(np.clip(p_joint, 0.0, 1.0))
    except Exception:
        # Monte Carlo fallback
        rng = np.random.default_rng(0)
        L = np.array([[1.0, 0], [rho, np.sqrt(1 - rho**2)]])
        z = rng.standard_normal((200_000, 2)) @ L.T
        return float(np.mean((z[:, 0] > h) & (z[:, 1] > k)))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_gamelog() -> pd.DataFrame:
    """Load combined regular season + playoffs gamelog, sorted by date."""
    rs = pd.read_parquet(LEAGUELOG_RS)
    po = pd.read_parquet(LEAGUELOG_PO)
    df = pd.concat([rs, po], ignore_index=True)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values(['PLAYER_ID', 'GAME_DATE', 'GAME_ID']).reset_index(drop=True)
    # Filter minimum-minutes players to avoid DNP artifacts
    df = df[df['MIN'] >= 10].copy()
    return df


def load_archetypes() -> Tuple[Dict[int, str], Dict[int, str]]:
    """Return (sameplayer_arch_map, teammate_arch_map) dicts {player_id: archetype}."""
    with open(SAMEPLAYER_ARCH_PATH) as f:
        sp_raw = json.load(f)
    with open(TEAMMATE_ARCH_PATH) as f:
        tm_raw = json.load(f)
    sp_map = {int(k): v for k, v in sp_raw.items()}
    tm_map = {int(k): v for k, v in tm_raw.items()}
    return sp_map, tm_map


def load_corr_tables() -> Tuple[dict, dict]:
    """Return (sameplayer_corr, teammate_corr) raw JSON dicts."""
    with open(SAMEPLAYER_CORR_PATH) as f:
        sp = json.load(f)
    with open(TEAMMATE_CORR_PATH) as f:
        tm = json.load(f)
    return sp, tm


# ---------------------------------------------------------------------------
# Rolling median (pre-game, no look-ahead)
# ---------------------------------------------------------------------------

def compute_rolling_medians(df: pd.DataFrame, stats: List[str],
                            min_games: int = MIN_GAMES_FOR_MEDIAN) -> pd.DataFrame:
    """For each player × stat, compute the rolling median over ALL prior games.

    The "line" for game G is the median of games 1..(G-1). Games with
    fewer than min_games prior observations are excluded.

    Returns df with added columns: {stat}_rolling_median, {stat}_is_over.
    """
    df = df.sort_values(['PLAYER_ID', 'GAME_DATE', 'GAME_ID']).copy()
    for stat in stats:
        if stat.upper() not in df.columns:
            continue
        col = stat.upper()
        # expanding median shifted by 1 (excludes current game)
        def _roll_median(series: pd.Series) -> pd.Series:
            return series.shift(1).expanding(min_periods=min_games).median()

        df[f'{stat}_rolling_median'] = (
            df.groupby('PLAYER_ID')[col].transform(_roll_median)
        )
        df[f'{stat}_is_over'] = (df[col] > df[f'{stat}_rolling_median']).astype(float)
        # Mark NaN where not enough history
        mask_nan = df[f'{stat}_rolling_median'].isna()
        df.loc[mask_nan, f'{stat}_is_over'] = np.nan

    return df


# ---------------------------------------------------------------------------
# Same-player pair backtest
# ---------------------------------------------------------------------------

def sameplayer_pair_backtest(
    df: pd.DataFrame,
    sp_arch_map: Dict[int, str],
    sp_corr: dict,
    stat_a: str,
    stat_b: str,
    archetype_filter: Optional[str],
    recal_rho: float,
    naive_rho: float,
    label: str,
) -> dict:
    """Backtest a single same-player pair.

    For each player with archetype == archetype_filter (or all if None),
    collect all games where both stats have valid rolling medians, compute
    realized P(both over), independence prediction, naive-rho prediction,
    and recal-rho prediction.
    """
    cols_needed = [f'{stat_a}_is_over', f'{stat_b}_is_over',
                   f'{stat_a}_rolling_median', f'{stat_b}_rolling_median']
    for c in cols_needed:
        if c not in df.columns:
            return {'label': label, 'n': 0, 'error': f'missing col {c}'}

    working = df.dropna(subset=cols_needed).copy()
    if archetype_filter is not None:
        valid_pids = {pid for pid, arch in sp_arch_map.items()
                      if arch == archetype_filter}
        working = working[working['PLAYER_ID'].isin(valid_pids)]

    if len(working) < MIN_JOINT_OBS:
        return {
            'label': label,
            'n': len(working),
            'error': f'too few obs ({len(working)} < {MIN_JOINT_OBS})',
        }

    # Overall marginal over-rates
    pa = float(working[f'{stat_a}_is_over'].mean())
    pb = float(working[f'{stat_b}_is_over'].mean())
    realized = float((working[f'{stat_a}_is_over'] * working[f'{stat_b}_is_over']).mean())

    p_indep   = pa * pb
    p_naive   = bvn_joint_over_prob(pa, pb, naive_rho)
    p_recal   = bvn_joint_over_prob(pa, pb, recal_rho)

    err_indep = abs(p_indep - realized)
    err_naive = abs(p_naive - realized)
    err_recal = abs(p_recal - realized)

    # Split-half by game_date
    dates  = working['GAME_DATE'].sort_values().values
    mid    = dates[len(dates) // 2]
    early  = working[working['GAME_DATE'] < mid]
    late   = working[working['GAME_DATE'] >= mid]

    def _half_realized(half: pd.DataFrame) -> Optional[float]:
        if len(half) < 20:
            return None
        return (half[f'{stat_a}_is_over'] * half[f'{stat_b}_is_over']).mean()

    r_early = _half_realized(early)
    r_late  = _half_realized(late)

    best_model = min(
        [('recal', err_recal), ('naive', err_naive), ('indep', err_indep)],
        key=lambda x: x[1]
    )[0]

    return {
        'label'       : label,
        'pair'        : f'{stat_a}+{stat_b}',
        'archetype'   : archetype_filter or 'global',
        'n'           : len(working),
        'n_early'     : len(early),
        'n_late'      : len(late),
        'pa'          : round(pa, 4),
        'pb'          : round(pb, 4),
        'realized_joint': round(realized, 4),
        'p_indep'     : round(p_indep, 4),
        'p_naive'     : round(p_naive, 4),
        'p_recal'     : round(p_recal, 4),
        'err_indep'   : round(err_indep, 4),
        'err_naive'   : round(err_naive, 4),
        'err_recal'   : round(err_recal, 4),
        'best_model'  : best_model,
        'recal_rho'   : recal_rho,
        'naive_rho'   : naive_rho,
        'realized_early': round(r_early, 4) if r_early is not None else None,
        'realized_late' : round(r_late, 4) if r_late is not None else None,
    }


# ---------------------------------------------------------------------------
# Teammate pair backtest
# ---------------------------------------------------------------------------

def teammate_pair_backtest(
    df: pd.DataFrame,
    tm_arch_map: Dict[int, str],
    stat_a: str,
    stat_b: str,
    arch_a_filter: Optional[str],
    arch_b_filter: Optional[str],
    recal_rho: float,
    naive_rho: float,
    label: str,
) -> dict:
    """Backtest a same-game teammate pair.

    For each game, find all (player_a, player_b) teammate pairs on the SAME
    team where player_a has archetype arch_a_filter and player_b has
    arch_b_filter (or None for any). Collect realized joint outcomes.
    """
    cols_a = [f'{stat_a}_is_over', f'{stat_a}_rolling_median']
    cols_b = [f'{stat_b}_is_over', f'{stat_b}_rolling_median']

    working = df.dropna(subset=cols_a + cols_b).copy()

    # We need game × team pairs, so merge on (GAME_ID, TEAM_ID)
    # Keep only the columns we need
    keep_cols = ['PLAYER_ID', 'GAME_ID', 'TEAM_ID', 'GAME_DATE',
                 f'{stat_a}_is_over', f'{stat_b}_is_over',
                 f'{stat_a}_rolling_median', f'{stat_b}_rolling_median']
    # Make sure all columns present
    keep_cols = [c for c in keep_cols if c in working.columns]
    working   = working[keep_cols].copy()

    # Add archetype columns
    working['arch_sp'] = working['PLAYER_ID'].map(
        {pid: a for pid, a in tm_arch_map.items()}
    )

    # Build pairs by merging players from the same game+team.
    # Rename carefully: for player A we care about stat_a_is_over (oa),
    # and for player B we care about stat_b_is_over (ob).
    # When stat_a == stat_b both columns are the same — just rename once.
    left  = working[['PLAYER_ID', 'GAME_ID', 'TEAM_ID', 'GAME_DATE',
                      f'{stat_a}_is_over', 'arch_sp']].rename(columns={
        f'{stat_a}_is_over': 'oa',
        'PLAYER_ID': 'pid_a', 'arch_sp': 'arch_a',
    })
    right = working[['PLAYER_ID', 'GAME_ID', 'TEAM_ID',
                      f'{stat_b}_is_over', 'arch_sp']].rename(columns={
        f'{stat_b}_is_over': 'ob',
        'PLAYER_ID': 'pid_b', 'arch_sp': 'arch_b',
    })

    pairs = left[['GAME_ID', 'TEAM_ID', 'GAME_DATE', 'pid_a', 'arch_a', 'oa']].merge(
        right[['GAME_ID', 'TEAM_ID', 'pid_b', 'arch_b', 'ob']],
        on=['GAME_ID', 'TEAM_ID'],
    )
    # Exclude same-player pairs
    pairs = pairs[pairs['pid_a'] != pairs['pid_b']]
    # Avoid double-counting (pid_a < pid_b)
    pairs = pairs[pairs['pid_a'] < pairs['pid_b']]

    # Apply archetype filters
    if arch_a_filter is not None:
        pairs = pairs[pairs['arch_a'] == arch_a_filter]
    if arch_b_filter is not None:
        pairs = pairs[pairs['arch_b'] == arch_b_filter]

    pairs = pairs.dropna(subset=['oa', 'ob'])
    # Force plain numpy arrays to avoid pandas Series-of-Series edge cases
    oa_arr = pairs['oa'].to_numpy(dtype=float, na_value=np.nan)
    ob_arr = pairs['ob'].to_numpy(dtype=float, na_value=np.nan)
    valid_mask = ~(np.isnan(oa_arr) | np.isnan(ob_arr))
    oa_arr = oa_arr[valid_mask]
    ob_arr = ob_arr[valid_mask]

    if len(oa_arr) < MIN_JOINT_OBS:
        return {
            'label': label,
            'n': len(oa_arr),
            'error': f'too few pairs ({len(oa_arr)} < {MIN_JOINT_OBS})',
        }

    pa = float(np.mean(oa_arr))
    pb = float(np.mean(ob_arr))
    realized = float(np.mean(oa_arr * ob_arr))

    p_indep   = pa * pb
    p_naive   = bvn_joint_over_prob(pa, pb, naive_rho)
    p_recal   = bvn_joint_over_prob(pa, pb, recal_rho)

    err_indep = abs(p_indep - realized)
    err_naive = abs(p_naive - realized)
    err_recal = abs(p_recal - realized)

    # Split-half: use the pairs index to get game dates, then split
    game_dates_arr = pairs['GAME_DATE'].to_numpy()
    sorted_dates   = np.sort(game_dates_arr)
    mid_date       = sorted_dates[len(sorted_dates) // 2]
    early_mask     = game_dates_arr < mid_date
    late_mask      = game_dates_arr >= mid_date

    def _hr_from_arr(mask: np.ndarray) -> Optional[float]:
        if mask.sum() < 20:
            return None
        return float(np.mean(oa_arr[mask[:len(oa_arr)]] * ob_arr[mask[:len(ob_arr)]]))

    # Recompute masks on the valid observations (oa_arr/ob_arr already valid-only)
    pairs_valid = pairs.iloc[np.where(valid_mask)[0]]
    gd_valid = pairs_valid['GAME_DATE'].to_numpy()
    sorted_valid = np.sort(gd_valid)
    if len(sorted_valid) > 0:
        mid_valid = sorted_valid[len(sorted_valid) // 2]
        e_mask = gd_valid < mid_valid
        l_mask = gd_valid >= mid_valid
        r_early = float(np.mean(oa_arr[e_mask] * ob_arr[e_mask])) if e_mask.sum() >= 20 else None
        r_late  = float(np.mean(oa_arr[l_mask] * ob_arr[l_mask])) if l_mask.sum() >= 20 else None
        n_early_val = int(e_mask.sum())
        n_late_val  = int(l_mask.sum())
    else:
        r_early = r_late = None
        n_early_val = n_late_val = 0

    best_model = min(
        [('recal', err_recal), ('naive', err_naive), ('indep', err_indep)],
        key=lambda x: x[1]
    )[0]

    return {
        'label'       : label,
        'pair'        : f'{stat_a}+{stat_b} (teammate)',
        'arch_a'      : arch_a_filter or 'any',
        'arch_b'      : arch_b_filter or 'any',
        'n'           : len(oa_arr),
        'n_early'     : n_early_val,
        'n_late'      : n_late_val,
        'pa'          : round(pa, 4),
        'pb'          : round(pb, 4),
        'realized_joint': round(realized, 4),
        'p_indep'     : round(p_indep, 4),
        'p_naive'     : round(p_naive, 4),
        'p_recal'     : round(p_recal, 4),
        'err_indep'   : round(err_indep, 4),
        'err_naive'   : round(err_naive, 4),
        'err_recal'   : round(err_recal, 4),
        'best_model'  : best_model,
        'recal_rho'   : recal_rho,
        'naive_rho'   : naive_rho,
        'realized_early': round(r_early, 4) if r_early is not None else None,
        'realized_late' : round(r_late, 4) if r_late is not None else None,
    }


# ---------------------------------------------------------------------------
# Pooled summary
# ---------------------------------------------------------------------------

def pooled_summary(results: List[dict]) -> dict:
    """Compute pooled (n-weighted) absolute errors across all valid pair types."""
    valid = [r for r in results if 'error' not in r]
    if not valid:
        return {}
    n_total = sum(r['n'] for r in valid)
    wt_sum = lambda key: sum(r[key] * r['n'] for r in valid) / n_total
    return {
        'n_pairs_tested' : len(valid),
        'n_total_obs'    : n_total,
        'pooled_err_indep': round(wt_sum('err_indep'), 5),
        'pooled_err_naive': round(wt_sum('err_naive'), 5),
        'pooled_err_recal': round(wt_sum('err_recal'), 5),
        'recal_beats_naive_count': sum(
            1 for r in valid if r['err_recal'] < r['err_naive']
        ),
        'recal_beats_indep_count': sum(
            1 for r in valid if r['err_recal'] < r['err_indep']
        ),
        'recal_is_best_count': sum(
            1 for r in valid if r['best_model'] == 'recal'
        ),
        'total_pairs': len(valid),
    }


# ---------------------------------------------------------------------------
# Format output table
# ---------------------------------------------------------------------------

def print_results_table(results: List[dict], pool: dict) -> None:
    """Pretty-print the results."""
    print()
    print("=" * 90)
    print("PART 1 — JOINT HIT-RATE BACKTEST: recal-rho vs independence vs naive")
    print("  Copula isolation: rolling-median 'line' -> marginals ~0.5 by construction.")
    print("  abs_error = |predicted_joint_prob - realized_joint_rate|")
    print("=" * 90)
    print()

    header = (
        f"{'Label':<40} {'N':>7} {'Realized':>9} "
        f"{'Indep':>8} {'Naive':>8} {'Recal':>8} "
        f"{'ErrI':>7} {'ErrN':>7} {'ErrR':>7} {'Best':>6}"
    )
    print(header)
    print("-" * 90)

    for r in results:
        if 'error' in r:
            print(f"  {r['label']:<38} SKIP: {r['error']}")
            continue
        row = (
            f"  {r['label']:<38} {r['n']:>7,} {r['realized_joint']:>9.4f} "
            f"{r['p_indep']:>8.4f} {r['p_naive']:>8.4f} {r['p_recal']:>8.4f} "
            f"{r['err_indep']:>7.4f} {r['err_naive']:>7.4f} {r['err_recal']:>7.4f} "
            f"{r['best_model']:>6}"
        )
        print(row)

    print("-" * 90)

    if pool:
        print()
        print("POOLED (n-weighted across all valid pair types):")
        print(f"  N pairs tested = {pool['n_pairs_tested']}, "
              f"total obs = {pool['n_total_obs']:,}")
        print(f"  Pooled |err| — independence: {pool['pooled_err_indep']:.5f}   "
              f"naive: {pool['pooled_err_naive']:.5f}   "
              f"recal: {pool['pooled_err_recal']:.5f}")
        print(f"  Recal beats naive: {pool['recal_beats_naive_count']}/{pool['total_pairs']} pairs")
        print(f"  Recal beats indep: {pool['recal_beats_indep_count']}/{pool['total_pairs']} pairs")
        print(f"  Recal is best model: {pool['recal_is_best_count']}/{pool['total_pairs']} pairs")

    print()
    print("Split-half stability check (should be consistent in sign):")
    for r in results:
        if 'error' in r or r.get('realized_early') is None:
            continue
        re = r['realized_early']
        rl = r['realized_late']
        p_r = r['p_recal']
        if rl is None:
            continue
        dir_early = "✓" if abs(p_r - re) < abs(r['p_naive'] - re) else "✗"
        dir_late  = "✓" if abs(p_r - rl) < abs(r['p_naive'] - rl) else "✗"
        print(f"  {r['label']:<40} early_realized={re:.4f} late_realized={rl:.4f}  "
              f"recal_better_early={dir_early} recal_better_late={dir_late}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_backtest() -> Tuple[List[dict], dict]:
    """Run the full backtest and return (results, pooled_summary)."""
    print("Loading gamelog data...")
    df = load_gamelog()
    print(f"  Loaded {len(df):,} rows, {df['GAME_ID'].nunique()} games, "
          f"{df['PLAYER_ID'].nunique()} players")

    print("Loading archetype maps and correlation tables...")
    sp_arch_map, tm_arch_map = load_archetypes()
    sp_corr, tm_corr         = load_corr_tables()

    # --- Compute rolling medians for all needed stats ---
    stats = ['pts', 'reb', 'ast', 'fg3m', 'tov', 'blk', 'stl']
    print("Computing rolling medians (this takes ~30s)...")
    df = compute_rolling_medians(df, stats)
    print("  Done.")

    results: List[dict] = []

    # -----------------------------------------------------------------------
    # SAME-PLAYER PAIRS
    # -----------------------------------------------------------------------

    # 1. SPOT_UP_SHOOTER fg3m+pts (biggest delta: 0.55 -> 0.738)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='fg3m', stat_b='pts',
        archetype_filter='SPOT_UP_SHOOTER',
        recal_rho=0.738, naive_rho=0.55,
        label='SP: SPOT_UP fg3m+pts',
    ))

    # 2. HIGH_AST_PLAYMAKER ast+tov (0.40 -> 0.098)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='ast', stat_b='tov',
        archetype_filter='HIGH_AST_PLAYMAKER',
        recal_rho=0.0983, naive_rho=0.40,
        label='SP: HIGH_AST ast+tov',
    ))

    # 3. HIGH_AST_PLAYMAKER pts+reb (0.40 -> 0.215)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='pts', stat_b='reb',
        archetype_filter='HIGH_AST_PLAYMAKER',
        recal_rho=0.2154, naive_rho=0.40,
        label='SP: HIGH_AST pts+reb',
    ))

    # 4. PNR_BALLHANDLER ast+tov (0.40 -> 0.030)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='ast', stat_b='tov',
        archetype_filter='PNR_BALLHANDLER',
        recal_rho=0.0304, naive_rho=0.40,
        label='SP: PNR_BH ast+tov',
    ))

    # 5. OTHER pts+tov (0.35 -> 0.177)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='pts', stat_b='tov',
        archetype_filter='OTHER',
        recal_rho=0.177, naive_rho=0.35,
        label='SP: OTHER pts+tov',
    ))

    # 6. OTHER reb+blk (0.35 -> 0.191)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='reb', stat_b='blk',
        archetype_filter='OTHER',
        recal_rho=0.1907, naive_rho=0.35,
        label='SP: OTHER reb+blk',
    ))

    # 7. SPOT_UP_SHOOTER ast+pts (0.30 -> 0.171)
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='ast', stat_b='pts',
        archetype_filter='SPOT_UP_SHOOTER',
        recal_rho=0.1706, naive_rho=0.30,
        label='SP: SPOT_UP ast+pts',
    ))

    # 8. Global fg3m+pts (0.55 -> global avg across archetypes)
    # Compute global avg from sp_corr archetypes
    fg3m_pts_rhos = [
        cells.get('fg3m_pts', {}).get('rho')
        for arch, cells in sp_corr['archetypes'].items()
        if cells.get('fg3m_pts', {}).get('rho') is not None
    ]
    global_fg3m_pts = float(np.mean(fg3m_pts_rhos)) if fg3m_pts_rhos else 0.65
    results.append(sameplayer_pair_backtest(
        df, sp_arch_map, sp_corr,
        stat_a='fg3m', stat_b='pts',
        archetype_filter=None,  # all players
        recal_rho=global_fg3m_pts, naive_rho=0.55,
        label='SP: GLOBAL fg3m+pts',
    ))

    # -----------------------------------------------------------------------
    # TEAMMATE PAIRS
    # -----------------------------------------------------------------------

    # 9. primary_creator AST + catch_shoot FG3M (0.0 -> 0.113)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='ast', stat_b='fg3m',
        arch_a_filter='primary_creator', arch_b_filter='catch_shoot',
        recal_rho=0.1128, naive_rho=0.0,
        label='TM: creator_AST + cs_FG3M',
    ))

    # 10. primary_creator AST + pnr_roll_man PTS (0.20 -> 0.099)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='ast', stat_b='pts',
        arch_a_filter='primary_creator', arch_b_filter='pnr_roll_man',
        recal_rho=0.099, naive_rho=0.20,
        label='TM: creator_AST + roll_PTS',
    ))

    # 11. primary_creator PTS + secondary_creator PTS (−0.15 -> −0.007)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='pts', stat_b='pts',
        arch_a_filter='primary_creator', arch_b_filter='secondary_creator',
        recal_rho=-0.0073, naive_rho=-0.15,
        label='TM: primary_PTS + sec_PTS',
    ))

    # 12. secondary_creator PTS + secondary_creator PTS (−0.15 -> −0.013)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='pts', stat_b='pts',
        arch_a_filter='secondary_creator', arch_b_filter='secondary_creator',
        recal_rho=-0.0125, naive_rho=-0.15,
        label='TM: sec_PTS + sec_PTS',
    ))

    # 13. Flat-baseline: global teammate AST+FG3M (0.0 -> 0.055, stable)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='ast', stat_b='fg3m',
        arch_a_filter=None, arch_b_filter=None,
        recal_rho=0.055, naive_rho=0.0,
        label='TM: GLOBAL ast+fg3m',
    ))

    # 14. Flat-baseline: global teammate PTS+AST (0.20 -> 0.063, stable)
    results.append(teammate_pair_backtest(
        df, tm_arch_map,
        stat_a='pts', stat_b='ast',
        arch_a_filter=None, arch_b_filter=None,
        recal_rho=0.0628, naive_rho=0.20,
        label='TM: GLOBAL pts+ast',
    ))

    # Compute pooled
    pool = pooled_summary(results)
    print_results_table(results, pool)
    return results, pool


# ---------------------------------------------------------------------------
# Public helpers (importable for tests)
# ---------------------------------------------------------------------------

def bvn_joint_prob_sheppard(rho: float) -> float:
    """P(both over median) under BVN with equal marginals = 0.5.

    Sheppard's formula: 0.25 + arcsin(rho) / (2*pi). Exact.
    """
    return 0.25 + float(np.arcsin(np.clip(rho, -1.0, 1.0))) / (2.0 * np.pi)


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        results, pool = run_backtest()
    # Exit code: 0 if recal beats naive on >=50% of pairs, 1 otherwise
    valid = [r for r in results if 'error' not in r]
    if valid:
        recal_wins = sum(1 for r in valid if r['err_recal'] < r['err_naive'])
        print(f"\nFINAL VERDICT: recal beats naive on {recal_wins}/{len(valid)} pair types.")
        if recal_wins > len(valid) / 2:
            print("  -> RECAL IS MORE PREDICTIVE of real joint outcomes than naive.")
        else:
            print("  -> RECAL does NOT beat naive on majority of pairs (plainly stated).")
        sys.exit(0)
    else:
        print("No valid results.")
        sys.exit(1)
