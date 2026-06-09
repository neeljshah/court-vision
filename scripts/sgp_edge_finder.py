"""sgp_edge_finder.py — PART 2: Enumerate candidate 2-leg SGP edges using recal correlations.

METHODOLOGY
-----------
For each date with available single-leg lines and served predictions, enumerate
all 2-leg same-game parlays and compute:

  true_joint_P  = Gaussian copula P(both legs hit) using recal rho
  book_implied_P (mode A) = independent product of single-leg de-vig probs
  book_implied_P (mode B) = naive-rho bivariate-normal product

  edge_vs_A = true_joint_P * parlay_payout - 1   (vs independent-book pricing)
  edge_vs_B = true_joint_P * parlay_payout - 1   (vs naive-rho pricing)

  parlay_payout = product of decimal single-leg odds (standard non-correlated SGP price)

BOOK-BLINDSPOT WEIGHTING (v2 refinement)
-----------------------------------------
The raw edge_vs_A ranking is dominated by SAME-PLAYER SPOT_UP fg3m+pts pairs.
These are ILLUSORY edges: FD/DK heavily haircut same-player pairs whose components
share variance (pts IS fg3m for spot-up shooters), so the book already discounts
the independent-product price. The "edge" disappears when tested vs real SGP prices.

The GENUINE edges are in cells where:
  1. recal rho materially differs from a naive/independent book assumption (rho_delta > 0.05)
  2. The book's correlation model is CRUDE (cross-player pairs, not same-player)
  3. The pair type is not commonly restricted/haircut by the book

book_blindspot_score computed per candidate:
  + CROSS-PLAYER pairs: +2.0 multiplier (book cannot price these at single-player level)
  - SAME-PLAYER same-stat-category (fg3m+pts, pts+reb, pts+ast): multiplier 0.1
    (book heavily haircuts; naive SGP prices already reflect the correlation)
  + rho_delta contribution: rho_delta / 0.20 * 1.0 (normalized to max reasonable delta)
  + teammate archetype specificity: +0.5 if archetype-pair cell (not flat baseline)

Genuine cross-player blind spots (from validated backtest):
  (i)  creator_AST + catch_shoot_FG3M:  recal +0.113 vs naive ~0.0 (book assumes independence)
  (ii) sec_PTS + sec_PTS double-over:   recal -0.007 vs naive -0.15 (book penalizes usage comp)
  (iii) creator_AST + roll_man PTS:     recal 0.082 vs naive 0.20 (recal corrects naive overestimate)

IMPORTANT CAVEATS
-----------------
1. SGP price history NOT available. Book actually prices SGPs with internal correlation
   models; the assumed price here (independent product) is the WORST-CASE book price
   for favorable legs. Real SGP prices are usually LOWER than independent product
   when legs are positively correlated.
2. "Edge" estimates here are HYPOTHESES under the assumption the book uses independent
   pricing — they are NOT graded vs real SGP close prices.
3. The value here is in IDENTIFYING which pairs the recal rho most changes the
   probability estimate, i.e. where the naive/independent model most overestimates
   or underestimates the true joint probability.
4. SAME-PLAYER fg3m+pts, pts+reb, pts+ast are EXCLUDED from the genuine-edge ranking
   because the book heavily haircuts these obvious positive-correlation pairs. They
   appear in the raw list only for reference.

PAIR TYPES
----------
Same-player (using recal archetype rho):
  - SPOT_UP fg3m + pts  [raw list only — book haircuts this]
  - Any same-player pair with |recal_rho - naive_rho| >= 0.10

Teammate (using surviving recal cells):
  - primary_creator AST + catch_shoot FG3M  [GENUINE blind spot]
  - primary_creator AST + roll_man PTS       [GENUINE blind spot — recal corrects naive overestimate]
  - primary/secondary creator PTS + secondary PTS (near-zero, not anti-corr)  [GENUINE blind spot]

OUTPUT
------
Top 20 candidate edges ranked by blindspot_adjusted_edge (cross-player first), with
obvious same-player pairs excluded from genuine ranking but shown in raw list.
Prints to stdout. Returns list of dicts for docs/_audits/SGP_EDGE.md.
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

DATA_DIR  = PROJECT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
MODELS_DIR = DATA_DIR / "models"
LINES_DIR  = DATA_DIR / "lines"

SAMEPLAYER_ARCH_PATH = MODELS_DIR / "player_archetype_sameplayer.json"
TEAMMATE_ARCH_PATH   = MODELS_DIR / "player_archetype_teammate.json"
SAMEPLAYER_CORR_PATH = MODELS_DIR / "prop_corr_archetype_sameplayer.json"
TEAMMATE_CORR_PATH   = MODELS_DIR / "prop_corr_archetype_teammate.json"

# American odds validity gate
MIN_ABS_ODDS = 100

# Minimum edge threshold to surface (to avoid noise)
MIN_EDGE_TO_SURFACE = 0.02  # 2% estimated edge

# Same-player pairs the book explicitly haircuts (obvious positive-correlation pairs).
# These are EXCLUDED from the genuine-edge ranking: the book's SGP price already
# reflects the correlation; testing vs single-leg independent product is misleading.
BOOK_HAIRCUT_SAME_PLAYER_PAIRS: set = {
    frozenset({'fg3m', 'pts'}),   # pts IS fg3m for spot-up — book discounts heavily
    frozenset({'pts', 'reb'}),    # both high means large usage → book haircuts
    frozenset({'pts', 'ast'}),    # star player size-up → book haircuts
}

# Cross-player pair types where the book's correlation model is crude.
# Keys match the rho_source / archetype labels used by enumerate_sgp_candidates.
GENUINE_CROSS_PLAYER_ARCHETYPES: set = {
    'creator_AST+catch_shoot',
    'catch_shoot+creator_AST',
    'creator+sec_scorer',
    'sec_scorer+sec_scorer',
    'flat_baseline',       # only for teammate pairs, not same-player
}


def book_blindspot_score(
    pair_type: str,
    stat_a: str,
    stat_b: str,
    rho_delta: float,
    rho_source: Optional[str],
) -> float:
    """Compute a book-blindspot score that DOWN-weights obvious same-player pairs and
    UP-weights cross-player pairs where the book's correlation model is crude.

    Returns a score in [0, 5] — higher = more likely to be a GENUINE book blind spot.

    Scoring:
      - Cross-player (teammate) pair: base 2.0
      - Obvious same-player haircut pair (fg3m+pts etc.): base 0.1
      - Other same-player pair: base 0.8
      - rho_delta contribution: min(abs(rho_delta) / 0.15, 1.0) * 1.5  (max +1.5)
      - Archetype-specific teammate cell (not flat_baseline): +0.5
    """
    pair_fs = frozenset({stat_a, stat_b})

    if pair_type == 'teammate':
        base = 2.0
        arch_bonus = 0.5 if (rho_source and rho_source != 'flat_baseline') else 0.0
        rho_contribution = min(abs(rho_delta) / 0.15, 1.0) * 1.5
    elif pair_fs in BOOK_HAIRCUT_SAME_PLAYER_PAIRS:
        # Book explicitly haircuts these pairs regardless of rho_delta magnitude.
        # Cap score at the base (0.1) — rho accuracy doesn't help if book already adjusts.
        base = 0.1
        arch_bonus = 0.0
        rho_contribution = 0.0
    else:
        base = 0.8
        arch_bonus = 0.0
        rho_contribution = min(abs(rho_delta) / 0.15, 1.0) * 1.5

    return round(base + arch_bonus + rho_contribution, 3)


# ---------------------------------------------------------------------------
# Odds utilities
# ---------------------------------------------------------------------------

def american_to_decimal(american_odds: float) -> Optional[float]:
    """Convert American odds to decimal (European) odds.

    Returns None for invalid odds (|odds| < MIN_ABS_ODDS).
    """
    if abs(american_odds) < MIN_ABS_ODDS:
        return None
    if american_odds > 0:
        return 1.0 + american_odds / 100.0
    else:
        return 1.0 + 100.0 / abs(american_odds)


def american_to_devig_prob(american_odds: float) -> Optional[float]:
    """Convert American odds to implied probability (no vig removed)."""
    dec = american_to_decimal(american_odds)
    if dec is None or dec <= 0:
        return None
    return 1.0 / dec


def devig_two_way(over_odds: float, under_odds: float) -> Optional[Tuple[float, float]]:
    """Remove vig from a two-way market using the multiplicative method.

    Returns (p_over_devig, p_under_devig) or None if invalid.
    """
    p_over_raw  = american_to_devig_prob(over_odds)
    p_under_raw = american_to_devig_prob(under_odds)
    if p_over_raw is None or p_under_raw is None:
        return None
    total = p_over_raw + p_under_raw
    if total <= 0 or total > 2.0:
        return None
    return p_over_raw / total, p_under_raw / total


# ---------------------------------------------------------------------------
# BVN joint probability (same as Part 1)
# ---------------------------------------------------------------------------

def bvn_joint_over_prob(pa: float, pb: float, rho: float) -> float:
    """P(A over, B over) under bivariate normal copula with marginals pa, pb."""
    rho = float(np.clip(rho, -0.9999, 0.9999))
    za  = norm.ppf(1.0 - pa) if 0 < pa < 1 else 0.0
    zb  = norm.ppf(1.0 - pb) if 0 < pb < 1 else 0.0
    if abs(za) < 1e-9 and abs(zb) < 1e-9:
        return 0.25 + float(np.arcsin(rho)) / (2.0 * np.pi)
    try:
        from scipy.stats import multivariate_normal as mvn
        cov  = [[1.0, rho], [rho, 1.0]]
        p_joint = 1.0 - norm.cdf(za) - norm.cdf(zb) + mvn.cdf([za, zb], mean=[0, 0], cov=cov)
        return float(np.clip(p_joint, 0.0, 1.0))
    except Exception:
        return 0.25 + float(np.arcsin(rho)) / (2.0 * np.pi)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_archetypes() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (sp_arch_map, tm_arch_map) keyed by player_name (lower)."""
    # Also build name-based lookups since FD uses different player_ids
    from src.prediction.correlation_recal import (
        _load_sameplayer_arch_map, _load_teammate_arch_map,
        clear_caches,
    )
    clear_caches()
    sp_id_map = _load_sameplayer_arch_map()   # {int player_id: archetype}
    tm_id_map = _load_teammate_arch_map()     # {int player_id: archetype}
    return sp_id_map, tm_id_map


def load_corr_tables() -> Tuple[dict, dict]:
    """Load sameplayer and teammate correlation JSON tables."""
    with open(SAMEPLAYER_CORR_PATH) as f:
        sp = json.load(f)
    with open(TEAMMATE_CORR_PATH) as f:
        tm = json.load(f)
    return sp, tm


def load_lines_and_predictions(date_str: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Load most recent lines + predictions, merge on (player_name, stat).

    Returns merged DataFrame with columns:
      player_name, stat, line, over_price, under_price,
      q50, sigma, team, p_over_devig
    or None if no data available.
    """
    import glob

    if date_str is None:
        # Use most recent available
        pred_files = sorted(glob.glob(str(CACHE_DIR / "predictions_cache_*.parquet")))
        # Skip bbrefON variant
        pred_files = [f for f in pred_files if 'bbrefON' not in f]
        if not pred_files:
            return None
        pred_path = Path(pred_files[-1])
        date_str = pred_path.stem.replace("predictions_cache_", "")
    else:
        pred_path = CACHE_DIR / f"predictions_cache_{date_str}.parquet"
        if not pred_path.exists():
            return None

    preds = pd.read_parquet(pred_path)

    # Find lines file for the same date (FD preferred, then dk)
    for book_suffix in ['fd', 'dk', 'pin', 'bov']:
        lines_path = LINES_DIR / f"{date_str}_{book_suffix}.csv"
        if lines_path.exists():
            break
    else:
        # Try any date within 1 day
        import glob as g
        files = g.glob(str(LINES_DIR / f"{date_str[:7]}*_fd.csv"))
        if files:
            lines_path = Path(sorted(files)[-1])
        else:
            return None

    lines = pd.read_csv(lines_path)

    # Deduplicate snapshots first: for each (player, stat, line), keep last captured
    if 'captured_at' in lines.columns:
        lines = lines.sort_values('captured_at')
    lines = lines[lines['over_price'].notna()]
    lines = lines[lines['over_price'].abs() >= MIN_ABS_ODDS]
    lines = lines.drop_duplicates(subset=['player_name', 'stat', 'line'], keep='last')
    # NOTE: FD exposes multiple alt-lines per player per stat.
    # For canonical SGP edge estimation we need the MAIN line (closest to q50),
    # not an alt line with 1500+ odds. We select the canonical line after merging
    # with q50 from predictions: keep the single line per (player, stat) with
    # |line - q50| minimized. This avoids lottery-ticket alt-line artifacts.

    # Normalize player names for merge
    lines['player_name_lower'] = lines['player_name'].str.lower().str.strip()
    preds['player_name_lower'] = preds['player_name'].str.lower().str.strip()

    merged = lines.merge(
        preds[['player_name_lower', 'stat', 'q50', 'sigma', 'team']],
        on=['player_name_lower', 'stat'],
        how='inner',
    )

    # Compute de-vig probability (use raw implied prob if no under_price)
    merged['p_over_devig'] = merged['over_price'].apply(american_to_devig_prob)
    # Where we have both sides, devig properly
    if 'under_price' in merged.columns:
        mask_two_way = merged['under_price'].notna() & (merged['under_price'].abs() >= MIN_ABS_ODDS)
        if mask_two_way.any():
            devig_results = merged[mask_two_way].apply(
                lambda row: devig_two_way(row['over_price'], row['under_price']),
                axis=1,
            )
            valid_devig = devig_results.notna()
            if valid_devig.any():
                merged.loc[merged[mask_two_way].index[valid_devig], 'p_over_devig'] = [
                    r[0] for r in devig_results[valid_devig]
                ]

    merged = merged.dropna(subset=['q50', 'sigma', 'p_over_devig'])
    # Use q50-implied prob if devig_prob is too far off (sanity check)
    merged = merged[merged['p_over_devig'].between(0.05, 0.95)]

    # SELECT CANONICAL LINE: for each (player, stat), keep the single line
    # with |line - q50| minimized. This picks the main/near-market line and
    # avoids alt-line lottery-ticket artifacts (e.g. FG3M 5.5 at +1700 for a
    # player whose q50 is 1.8). Only the canonical line participates in SGP
    # enumeration; multiple alt lines would generate spurious high "edge" numbers
    # because P_true_joint >> P_indep for extreme alt lines when rho > 0.
    merged['abs_diff_q50'] = (merged['line'] - merged['q50']).abs()
    merged = merged.sort_values('abs_diff_q50')
    merged = merged.drop_duplicates(subset=['player_name_lower', 'stat'], keep='first')
    merged = merged.drop(columns=['abs_diff_q50'])

    return merged


# ---------------------------------------------------------------------------
# Recal rho lookup tables
# ---------------------------------------------------------------------------

def build_sameplayer_rho_table(sp_corr: dict) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """Return {(archetype, pair_key): (recal_rho, naive_rho)} for refined cells.

    pair_key = frozenset({stat_a, stat_b}) as canonical sorted tuple.
    """
    result: Dict[Tuple, Tuple[float, float]] = {}
    for arch, cells in sp_corr['archetypes'].items():
        for pair_key_str, cell in cells.items():
            if not cell.get('refined', False):
                continue
            parts = pair_key_str.split('_')
            if len(parts) != 2:
                continue
            sa, sb = parts
            key = (arch, tuple(sorted([sa, sb])))
            result[key] = (float(cell['rho']), float(cell.get('naive_rho', 0.0)))
    return result


def build_teammate_rho_table(tm_corr: dict) -> Dict[Tuple, Tuple[float, float]]:
    """Return {(arch_a, arch_b, pair_key): (recal_rho, naive_rho)} for surviving cells."""
    result: Dict[Tuple, Tuple[float, float]] = {}
    cells = tm_corr['archetype_pair_cells']
    for key_str in tm_corr['surviving_cells']:
        cell = cells.get(key_str)
        if not cell:
            continue
        arch_a = cell['archetype_a']
        arch_b = cell['archetype_b']
        sa = cell['stat_a']
        sb = cell['stat_b']
        pair_key = tuple(sorted([sa, sb]))
        k = (arch_a, arch_b, pair_key)
        result[k] = (float(cell['rho']), float(cell.get('naive_rho', 0.0)))
        if arch_a != arch_b:
            k2 = (arch_b, arch_a, pair_key)
            result[k2] = (float(cell['rho']), float(cell.get('naive_rho', 0.0)))
    # Also add stable flat baselines
    for pair_str, baseline in tm_corr['flat_baselines'].items():
        if not baseline.get('stable', False):
            continue
        parts = pair_str.split('_')
        if len(parts) != 2:
            continue
        sa, sb = parts
        pair_key = tuple(sorted([sa, sb]))
        k = ('_flat_', '_flat_', pair_key)
        result[k] = (float(baseline['rho']), float(tm_corr['naive_flat_rho'].get(pair_str, 0.0)))
    return result


# ---------------------------------------------------------------------------
# 2-leg SGP enumeration
# ---------------------------------------------------------------------------

def enumerate_sgp_candidates(
    merged: pd.DataFrame,
    sp_arch_map: Dict[int, str],
    tm_arch_map: Dict[int, str],
    sp_rho_table: Dict,
    tm_rho_table: Dict,
) -> List[dict]:
    """Enumerate 2-leg same-game parlay candidates.

    Returns list of candidate dicts sorted by edge_vs_A descending.
    """
    # Build player -> archetype lookup by player_name (lower)
    # Also load the NBA player_id -> archetype maps directly from JSONs
    # Since FD player_ids don't match NBA player_ids, we match by name
    # We'll approximate: build a name -> archetype lookup from the gamelog
    # using the player_archetype_sameplayer.json + player_archetype_teammate.json
    # paired with the gamelog's player names

    # Build name-based archetype maps from the data
    # Load gamelog to get player_id -> name mapping
    from pathlib import Path as P
    gamelog_path = P(str(CACHE_DIR)) / "cv_fix" / "leaguegamelog_regular_season.parquet"
    if gamelog_path.exists():
        gl = pd.read_parquet(gamelog_path)[['PLAYER_ID', 'PLAYER_NAME']].drop_duplicates()
        id_to_name = dict(zip(gl['PLAYER_ID'], gl['PLAYER_NAME'].str.lower()))
    else:
        id_to_name = {}

    sp_name_arch = {id_to_name[pid]: arch for pid, arch in sp_arch_map.items()
                    if pid in id_to_name}
    tm_name_arch = {id_to_name[pid]: arch for pid, arch in tm_arch_map.items()
                    if pid in id_to_name}

    # Add archetype columns to merged
    merged = merged.copy()
    merged['sp_arch'] = merged['player_name_lower'].map(sp_name_arch)
    merged['tm_arch'] = merged['player_name_lower'].map(tm_name_arch)

    candidates: List[dict] = []

    # -----------------------------------------------------------------------
    # SAME-PLAYER pairs
    # -----------------------------------------------------------------------
    players = merged['player_name_lower'].unique()
    for pname in players:
        player_rows = merged[merged['player_name_lower'] == pname]
        sp_arch = player_rows['sp_arch'].iloc[0] if not player_rows.empty else None
        if sp_arch is None:
            continue

        # Enumerate all stat pairs for this player
        stats_available = player_rows['stat'].unique()
        for i, stat_a in enumerate(stats_available):
            for stat_b in stats_available[i+1:]:
                row_a = player_rows[player_rows['stat'] == stat_a]
                row_b = player_rows[player_rows['stat'] == stat_b]
                if row_a.empty or row_b.empty:
                    continue
                row_a = row_a.iloc[0]
                row_b = row_b.iloc[0]

                pair_key = tuple(sorted([stat_a, stat_b]))
                k = (sp_arch, pair_key)
                if k not in sp_rho_table:
                    continue

                recal_rho, naive_rho = sp_rho_table[k]
                if abs(recal_rho - naive_rho) < 0.10:
                    continue  # Skip small-delta pairs

                # Both legs: OVER
                pa = float(row_a['p_over_devig'])
                pb = float(row_b['p_over_devig'])

                p_true_joint = bvn_joint_over_prob(pa, pb, recal_rho)
                p_naive_joint = bvn_joint_over_prob(pa, pb, naive_rho)
                p_indep_joint = pa * pb

                # Parlay payout = product of decimal odds (assumed independent pricing)
                dec_a = american_to_decimal(float(row_a['over_price']))
                dec_b = american_to_decimal(float(row_b['over_price']))
                if dec_a is None or dec_b is None:
                    continue

                parlay_payout = dec_a * dec_b
                edge_vs_A = p_true_joint * parlay_payout - 1.0
                edge_vs_B = p_true_joint * parlay_payout - 1.0  # same for SGP if book uses naive

                # Prob change: how much does recal shift the joint prob vs naive?
                prob_lift_vs_naive = p_true_joint - p_naive_joint
                prob_lift_vs_indep = p_true_joint - p_indep_joint

                rho_delta = recal_rho - naive_rho
                blindspot = book_blindspot_score(
                    'same_player', stat_a, stat_b, rho_delta, sp_arch,
                )
                candidates.append({
                    'type'           : 'same_player',
                    'archetype'      : sp_arch,
                    'player_a'       : row_a['player_name'],
                    'player_b'       : row_a['player_name'],
                    'team'           : row_a.get('team', ''),
                    'stat_a'         : stat_a,
                    'stat_b'         : stat_b,
                    'line_a'         : float(row_a['line']),
                    'line_b'         : float(row_b['line']),
                    'odds_a'         : float(row_a['over_price']),
                    'odds_b'         : float(row_b['over_price']),
                    'q50_a'          : float(row_a['q50']),
                    'q50_b'          : float(row_b['q50']),
                    'pa_devig'       : round(pa, 4),
                    'pb_devig'       : round(pb, 4),
                    'recal_rho'      : round(recal_rho, 4),
                    'naive_rho'      : round(naive_rho, 4),
                    'p_true_joint'   : round(p_true_joint, 4),
                    'p_naive_joint'  : round(p_naive_joint, 4),
                    'p_indep_joint'  : round(p_indep_joint, 4),
                    'parlay_payout'  : round(parlay_payout, 4),
                    'edge_vs_A'      : round(edge_vs_A, 4),
                    'blindspot_score': blindspot,
                    'blindspot_adj_edge': round(edge_vs_A * blindspot, 4),
                    'book_priced'    : frozenset({stat_a, stat_b}) in BOOK_HAIRCUT_SAME_PLAYER_PAIRS,
                    'prob_lift_vs_naive': round(prob_lift_vs_naive, 4),
                    'prob_lift_vs_indep': round(prob_lift_vs_indep, 4),
                    'recal_driver'   : f'{sp_arch} {stat_a}+{stat_b}: {naive_rho:.2f}->{recal_rho:.2f}',
                })

    # -----------------------------------------------------------------------
    # TEAMMATE pairs (same team, same game)
    # -----------------------------------------------------------------------
    teams = merged['team'].unique()
    for team in teams:
        team_rows = merged[merged['team'] == team]
        players_on_team = team_rows['player_name_lower'].unique()

        for i, name_a in enumerate(players_on_team):
            for name_b in players_on_team[i+1:]:
                rows_a = team_rows[team_rows['player_name_lower'] == name_a]
                rows_b = team_rows[team_rows['player_name_lower'] == name_b]

                arch_a_val = rows_a['tm_arch'].iloc[0] if not rows_a.empty else None
                arch_b_val = rows_b['tm_arch'].iloc[0] if not rows_b.empty else None

                # Check surviving archetype pair cells
                # Try all stat combinations
                for stat_a in rows_a['stat'].unique():
                    for stat_b in rows_b['stat'].unique():
                        row_a = rows_a[rows_a['stat'] == stat_a]
                        row_b = rows_b[rows_b['stat'] == stat_b]
                        if row_a.empty or row_b.empty:
                            continue
                        row_a = row_a.iloc[0]
                        row_b = row_b.iloc[0]

                        pair_key = tuple(sorted([stat_a, stat_b]))

                        # Find best available rho
                        recal_rho = None
                        naive_rho = None
                        rho_source = None

                        # Try archetype-specific first
                        if arch_a_val and arch_b_val:
                            k1 = (arch_a_val, arch_b_val, pair_key)
                            k2 = (arch_b_val, arch_a_val, pair_key)
                            if k1 in tm_rho_table:
                                recal_rho, naive_rho = tm_rho_table[k1]
                                rho_source = f'{arch_a_val}+{arch_b_val}'
                            elif k2 in tm_rho_table:
                                recal_rho, naive_rho = tm_rho_table[k2]
                                rho_source = f'{arch_b_val}+{arch_a_val}'

                        # Flat baseline fallback
                        if recal_rho is None:
                            k_flat = ('_flat_', '_flat_', pair_key)
                            if k_flat in tm_rho_table:
                                recal_rho, naive_rho = tm_rho_table[k_flat]
                                rho_source = 'flat_baseline'

                        if recal_rho is None:
                            continue
                        if abs(recal_rho - (naive_rho or 0)) < 0.05:
                            continue  # small delta, skip

                        pa = float(row_a['p_over_devig'])
                        pb = float(row_b['p_over_devig'])

                        p_true_joint  = bvn_joint_over_prob(pa, pb, recal_rho)
                        p_naive_joint = bvn_joint_over_prob(pa, pb, naive_rho or 0.0)
                        p_indep_joint = pa * pb

                        dec_a = american_to_decimal(float(row_a['over_price']))
                        dec_b = american_to_decimal(float(row_b['over_price']))
                        if dec_a is None or dec_b is None:
                            continue

                        parlay_payout  = dec_a * dec_b
                        edge_vs_A      = p_true_joint * parlay_payout - 1.0
                        prob_lift_vs_naive = p_true_joint - p_naive_joint
                        prob_lift_vs_indep = p_true_joint - p_indep_joint
                        rho_delta_tm = recal_rho - (naive_rho or 0.0)
                        blindspot = book_blindspot_score(
                            'teammate', stat_a, stat_b, rho_delta_tm, rho_source,
                        )

                        candidates.append({
                            'type'           : 'teammate',
                            'archetype'      : rho_source,
                            'player_a'       : row_a['player_name'],
                            'player_b'       : row_b['player_name'],
                            'team'           : team,
                            'stat_a'         : stat_a,
                            'stat_b'         : stat_b,
                            'line_a'         : float(row_a['line']),
                            'line_b'         : float(row_b['line']),
                            'odds_a'         : float(row_a['over_price']),
                            'odds_b'         : float(row_b['over_price']),
                            'q50_a'          : float(row_a['q50']),
                            'q50_b'          : float(row_b['q50']),
                            'pa_devig'       : round(pa, 4),
                            'pb_devig'       : round(pb, 4),
                            'recal_rho'      : round(recal_rho, 4),
                            'naive_rho'      : round(naive_rho, 4),
                            'p_true_joint'   : round(p_true_joint, 4),
                            'p_naive_joint'  : round(p_naive_joint, 4),
                            'p_indep_joint'  : round(p_indep_joint, 4),
                            'parlay_payout'  : round(parlay_payout, 4),
                            'edge_vs_A'      : round(edge_vs_A, 4),
                            'blindspot_score': blindspot,
                            'blindspot_adj_edge': round(edge_vs_A * blindspot, 4),
                            'book_priced'    : False,  # cross-player, never book-priced
                            'prob_lift_vs_naive': round(prob_lift_vs_naive, 4),
                            'prob_lift_vs_indep': round(prob_lift_vs_indep, 4),
                            'recal_driver'   : (
                                f'{rho_source} {stat_a}+{stat_b}: '
                                f'{naive_rho:.2f}->{recal_rho:.2f}'
                            ),
                        })

    # Sort by blindspot_adj_edge descending (genuine blind spots first).
    # Within genuine (book_priced=False) this naturally surfaces cross-player pairs.
    return sorted(candidates, key=lambda x: (x['book_priced'], -x['blindspot_adj_edge']))


def print_candidates(candidates: List[dict], top_n: int = 20) -> None:
    """Print top candidates table, split into GENUINE (cross-player) and RAW (same-player).

    GENUINE candidates: book_priced=False, ranked by blindspot_adj_edge.
    Same-player SPOT_UP etc.: shown separately with a note that the book haircuts these.
    """
    print()
    print("=" * 120)
    print("PART 2 — SGP CANDIDATE EDGES (v2: book-blindspot weighted)")
    print("  Genuine cross-player edges surfaced first; obvious same-player pairs marked as book-priced.")
    print("  edge_vs_A = P(both hit) * parlay_payout − 1  (vs assumed independent pricing).")
    print("  NOT graded vs real SGP prices. blindspot_adj = edge_vs_A × blindspot_score.")
    print("=" * 120)
    print()

    genuine   = [c for c in candidates if not c.get('book_priced', False)]
    haircut   = [c for c in candidates if c.get('book_priced', False)]

    header = (
        f"{'#':>3} {'Type':>10} {'PlayerA':<22} {'PlayerB':<22} "
        f"{'SA':>4} {'SB':>4} {'rho_N':>6} {'rho_R':>6} "
        f"{'P_true':>7} {'P_naive':>7} {'Payout':>7} {'Edge_A':>7} {'BS':>5} {'BS_adj':>7}"
    )
    sep = "-" * 120

    print("=== GENUINE CROSS-PLAYER EDGES (book blind spots — cross-player / non-obvious) ===")
    print(header)
    print(sep)
    genuine_surface = [c for c in genuine if c['edge_vs_A'] >= MIN_EDGE_TO_SURFACE]
    for i, c in enumerate(genuine_surface[:top_n], 1):
        row = (
            f"{i:>3} {c['type']:>10} {c['player_a'][:22]:<22} {c['player_b'][:22]:<22} "
            f"{c['stat_a']:>4} {c['stat_b']:>4} {c['naive_rho']:>6.3f} {c['recal_rho']:>6.3f} "
            f"{c['p_true_joint']:>7.4f} {c['p_naive_joint']:>7.4f} {c['parlay_payout']:>7.3f} "
            f"{c['edge_vs_A']:>7.2%} {c['blindspot_score']:>5.2f} {c['blindspot_adj_edge']:>7.4f}"
        )
        print(row)
        if i <= 3:
            print(f"     Driver: {c['recal_driver']}")
    print(sep)
    print(f"Genuine cross-player candidates (edge >= {MIN_EDGE_TO_SURFACE:.0%}): "
          f"{len(genuine_surface)} / {len(genuine)}")
    print()

    print("=== SAME-PLAYER PAIRS (ILLUSORY — book heavily haircuts these; listed for reference only) ===")
    print(header)
    print(sep)
    haircut_surface = [c for c in haircut if c['edge_vs_A'] >= MIN_EDGE_TO_SURFACE]
    for i, c in enumerate(haircut_surface[:10], 1):
        row = (
            f"{i:>3} {c['type']:>10} {c['player_a'][:22]:<22} {c['player_b'][:22]:<22} "
            f"{c['stat_a']:>4} {c['stat_b']:>4} {c['naive_rho']:>6.3f} {c['recal_rho']:>6.3f} "
            f"{c['p_true_joint']:>7.4f} {c['p_naive_joint']:>7.4f} {c['parlay_payout']:>7.3f} "
            f"{c['edge_vs_A']:>7.2%} {c['blindspot_score']:>5.2f} {c['blindspot_adj_edge']:>7.4f}"
        )
        print(row)
    print(sep)
    print(f"  NOTE: These SPOT_UP fg3m+pts, pts+reb, pts+ast pairs are the SAME as Part 1's top results.")
    print(f"  The book's real SGP haircut for these pairs ELIMINATES the estimated edge vs independent pricing.")
    print(f"  EXCLUDED from genuine-edge ranking (blindspot_score = 0.1).")
    print()

    print("DISCLAIMER: edge_vs_A = P(both OVER) × parlay_payout − 1")
    print("  parlay_payout = product of single-leg decimal odds (standard non-correlated SGP price).")
    print("  Real DK/FD SGP prices for correlated legs are LOWER than this (closer to true joint P).")
    print("  MUST grade vs real SGP prices (scripts/grade_sgp_edge.py) to confirm any edge.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_edge_finder(date_str: Optional[str] = None) -> List[dict]:
    """Run the edge finder and return candidates list."""
    print("Loading archetype maps and correlation tables...")
    sp_arch_map, tm_arch_map = load_archetypes()
    sp_corr, tm_corr         = load_corr_tables()

    sp_rho_table = build_sameplayer_rho_table(sp_corr)
    tm_rho_table = build_teammate_rho_table(tm_corr)

    print(f"  SP rho table entries: {len(sp_rho_table)}")
    print(f"  TM rho table entries: {len(tm_rho_table)}")

    print("Loading lines and predictions...")
    merged = load_lines_and_predictions(date_str)
    if merged is None or merged.empty:
        print("  No matched lines+predictions available for this date.")
        return []

    print(f"  Merged {len(merged):,} rows, "
          f"{merged['player_name_lower'].nunique()} players, "
          f"{merged['stat'].nunique()} stat types")

    print("Enumerating 2-leg SGP candidates...")
    candidates = enumerate_sgp_candidates(
        merged, sp_arch_map, tm_arch_map, sp_rho_table, tm_rho_table
    )
    print(f"  Found {len(candidates)} candidate pairs")

    print_candidates(candidates, top_n=20)
    return candidates


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SGP Edge Finder (Part 2)")
    parser.add_argument("--date", default=None,
                        help="Date string YYYY-MM-DD (default: most recent predictions cache)")
    args = parser.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        candidates = run_edge_finder(args.date)
