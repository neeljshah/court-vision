"""grade_sgp_edge.py — Grade SGP edge candidates vs real FanDuel SGP prices.

USAGE
-----
Once real FD SGP prices are captured (via scripts/fanduel_sgp_scraper.py or
manually from browser DevTools), this script grades:

  real_sgp_ev = P_recal * combined_decimal_odds - 1.0

and logs the result to data/cache/sgp_grade_log.csv.

INPUTS
------
1. FD SGP price file:  data/lines/<date>_fd_sgp.csv
   Columns: player_a, stat_a, line_a, player_b, stat_b, line_b,
            combined_odds_american, event_id, captured_at
   (Written by scripts/fanduel_sgp_scraper.py)

2. Recal joint probability from scripts/sgp_edge_finder.py candidates.
   Loaded by re-running the edge finder and joining on the pair key.

3. Box score outcomes (for grading after the game):
   data/cache/cv_fix/leaguegamelog_regular_season.parquet
   Columns: GAME_ID, PLAYER_ID, PLAYER_NAME, GAME_DATE, <stat columns>

OUTPUT
------
Prints a grading table per pair with:
  - combined_decimal_odds  (from FD SGP price)
  - P_recal                (our joint probability estimate)
  - real_sgp_ev            = P_recal * combined_decimal - 1.0
  - outcome (if box score available): HIT / MISS / PENDING
  - realized_value         (1.0 if HIT * combined_decimal else 0.0)

Appends to data/cache/sgp_grade_log.csv for ongoing tracking.

EXAMPLE
-------
  python scripts/grade_sgp_edge.py --date 2026-06-06

VALIDATION GATE
---------------
A graded edge requires:
  - Min 10 SGP observations per pair type
  - real_sgp_ev > 0.02 (2% net edge after vig)
  - Bootstrap 95% CI excludes 0

This is the FINAL step to confirm or refute the SGP edge hypothesis.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

LINES_DIR = PROJECT_DIR / "data" / "lines"
CACHE_DIR = PROJECT_DIR / "data" / "cache"
GRADE_LOG = CACHE_DIR / "sgp_grade_log.csv"

GRADE_LOG_FIELDS = [
    "graded_at", "game_date", "event_id",
    "player_a", "stat_a", "line_a",
    "player_b", "stat_b", "line_b",
    "combined_odds_american", "combined_decimal",
    "p_recal", "real_sgp_ev",
    "outcome",          # HIT / MISS / PENDING
    "realized_value",   # combined_decimal if HIT, 0.0 if MISS, NaN if PENDING
    "pair_type",        # e.g. creator_AST+catch_shoot_FG3M
    "recal_rho",
    "naive_rho",
]

MIN_ABS_ODDS = 100


# ---------------------------------------------------------------------------
# Odds utilities
# ---------------------------------------------------------------------------

def american_to_decimal(odds: float) -> Optional[float]:
    """American to decimal odds. Returns None for invalid (<MIN_ABS_ODDS)."""
    if abs(odds) < MIN_ABS_ODDS:
        return None
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def decimal_to_american(decimal_odds: float) -> Optional[float]:
    """Decimal to American odds."""
    if decimal_odds <= 1.0:
        return None
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1.0) * 100.0, 1)
    return round(-100.0 / (decimal_odds - 1.0), 1)


def bvn_joint_over_prob(pa: float, pb: float, rho: float) -> float:
    """P(A over, B over) under bivariate normal copula with marginals pa, pb."""
    from scipy.stats import multivariate_normal as mvn
    rho = float(np.clip(rho, -0.9999, 0.9999))
    za = norm.ppf(1.0 - pa) if 0 < pa < 1 else 0.0
    zb = norm.ppf(1.0 - pb) if 0 < pb < 1 else 0.0
    if abs(za) < 1e-9 and abs(zb) < 1e-9:
        return 0.25 + float(np.arcsin(rho)) / (2.0 * np.pi)
    try:
        cov = [[1.0, rho], [rho, 1.0]]
        p = 1.0 - norm.cdf(za) - norm.cdf(zb) + mvn.cdf([za, zb], mean=[0, 0], cov=cov)
        return float(np.clip(p, 0.0, 1.0))
    except Exception:
        return 0.25 + float(np.arcsin(rho)) / (2.0 * np.pi)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_sgp_prices(date_str: str) -> Optional[pd.DataFrame]:
    """Load captured FD SGP prices from data/lines/<date>_fd_sgp.csv."""
    path = LINES_DIR / f"{date_str}_fd_sgp.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    required = {'player_a', 'stat_a', 'line_a', 'player_b', 'stat_b', 'line_b',
                'combined_odds_american', 'event_id'}
    missing = required - set(df.columns)
    if missing:
        print(f"[grade_sgp_edge] SGP price file missing columns: {missing}")
        return None
    df['combined_decimal'] = df['combined_odds_american'].apply(american_to_decimal)
    df = df.dropna(subset=['combined_decimal'])
    df['player_a_lower'] = df['player_a'].str.lower().str.strip()
    df['player_b_lower'] = df['player_b'].str.lower().str.strip()
    return df


def load_recal_candidates(date_str: str) -> Optional[pd.DataFrame]:
    """Re-run sgp_edge_finder to get recal joint probabilities for the date.

    Returns DataFrame with (player_a_lower, player_b_lower, stat_a, stat_b,
    line_a, line_b, p_true_joint, recal_rho, naive_rho, pair_type).
    """
    try:
        from scripts.sgp_edge_finder import run_edge_finder
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            candidates = run_edge_finder(date_str)
        if not candidates:
            return None
        rows = []
        for c in candidates:
            rows.append({
                'player_a_lower': c['player_a'].lower().strip(),
                'player_b_lower': c['player_b'].lower().strip(),
                'stat_a'        : c['stat_a'],
                'stat_b'        : c['stat_b'],
                'line_a'        : c['line_a'],
                'line_b'        : c['line_b'],
                'p_recal'       : c['p_true_joint'],
                'recal_rho'     : c['recal_rho'],
                'naive_rho'     : c['naive_rho'],
                'pair_type'     : c.get('archetype', ''),
                'book_priced'   : c.get('book_priced', False),
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        print(f"[grade_sgp_edge] could not load recal candidates: {exc}")
        return None


def load_box_scores(date_str: str) -> Optional[pd.DataFrame]:
    """Load box score outcomes for grading. Returns per-player stat totals or None."""
    # Try the canonical gamelog first
    gl_path = CACHE_DIR / "cv_fix" / "leaguegamelog_regular_season.parquet"
    if not gl_path.exists():
        # Try playoff log
        gl_path = CACHE_DIR / "cv_fix" / "leaguegamelog_playoffs.parquet"
    if not gl_path.exists():
        return None

    try:
        gl = pd.read_parquet(gl_path)
        if 'GAME_DATE' in gl.columns:
            gl['game_date_str'] = pd.to_datetime(gl['GAME_DATE']).dt.date.astype(str)
            day_gl = gl[gl['game_date_str'] == date_str]
            if day_gl.empty:
                return None
            # Normalize stat names to lowercase
            rename = {
                'PTS': 'pts', 'REB': 'reb', 'AST': 'ast',
                'FG3M': 'fg3m', 'STL': 'stl', 'BLK': 'blk', 'TOV': 'tov',
            }
            day_gl = day_gl.rename(columns=rename)
            day_gl['player_name_lower'] = day_gl['PLAYER_NAME'].str.lower().str.strip()
            return day_gl
    except Exception as exc:
        print(f"[grade_sgp_edge] box score load failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def grade_pair(
    row: pd.Series,
    recal_df: pd.DataFrame,
    box_df: Optional[pd.DataFrame],
) -> dict:
    """Grade a single SGP price row.

    Returns a dict with all GRADE_LOG_FIELDS.
    """
    # Match to recal estimate
    mask = (
        (recal_df['player_a_lower'] == row['player_a_lower']) &
        (recal_df['player_b_lower'] == row['player_b_lower']) &
        (recal_df['stat_a'] == row['stat_a']) &
        (recal_df['stat_b'] == row['stat_b'])
    )
    # Also try swapped players
    mask_swap = (
        (recal_df['player_a_lower'] == row['player_b_lower']) &
        (recal_df['player_b_lower'] == row['player_a_lower']) &
        (recal_df['stat_a'] == row['stat_b']) &
        (recal_df['stat_b'] == row['stat_a'])
    )
    match = recal_df[mask | mask_swap]

    p_recal = float('nan')
    recal_rho = float('nan')
    naive_rho = float('nan')
    pair_type = ''
    real_sgp_ev = float('nan')

    if not match.empty:
        m = match.iloc[0]
        p_recal = float(m['p_recal'])
        recal_rho = float(m['recal_rho'])
        naive_rho = float(m['naive_rho'])
        pair_type = str(m.get('pair_type', ''))
        real_sgp_ev = p_recal * float(row['combined_decimal']) - 1.0
    else:
        print(f"  [WARN] No recal match for {row['player_a']} {row['stat_a']} + "
              f"{row['player_b']} {row['stat_b']}")

    # Grade vs box score if available
    outcome = 'PENDING'
    realized_value = float('nan')

    if box_df is not None:
        a_lower = row['player_a_lower']
        b_lower = row['player_b_lower']
        stat_a = row['stat_a']
        stat_b = row['stat_b']
        line_a = float(row['line_a'])
        line_b = float(row['line_b'])

        a_rows = box_df[box_df['player_name_lower'] == a_lower]
        b_rows = box_df[box_df['player_name_lower'] == b_lower]

        if not a_rows.empty and stat_a in a_rows.columns:
            val_a = float(a_rows.iloc[0][stat_a])
            hit_a = val_a > line_a
        else:
            hit_a = None

        if not b_rows.empty and stat_b in b_rows.columns:
            val_b = float(b_rows.iloc[0][stat_b])
            hit_b = val_b > line_b
        else:
            hit_b = None

        if hit_a is not None and hit_b is not None:
            if hit_a and hit_b:
                outcome = 'HIT'
                realized_value = float(row['combined_decimal'])
            else:
                outcome = 'MISS'
                realized_value = 0.0

    return {
        'graded_at'              : datetime.utcnow().replace(microsecond=0).isoformat(),
        'game_date'              : row.get('game_date', ''),
        'event_id'               : row.get('event_id', ''),
        'player_a'               : row['player_a'],
        'stat_a'                 : row['stat_a'],
        'line_a'                 : row['line_a'],
        'player_b'               : row['player_b'],
        'stat_b'                 : row['stat_b'],
        'line_b'                 : row['line_b'],
        'combined_odds_american' : row['combined_odds_american'],
        'combined_decimal'       : round(float(row['combined_decimal']), 4),
        'p_recal'                : round(p_recal, 4) if not np.isnan(p_recal) else '',
        'real_sgp_ev'            : round(real_sgp_ev, 4) if not np.isnan(real_sgp_ev) else '',
        'outcome'                : outcome,
        'realized_value'         : round(realized_value, 4) if not np.isnan(realized_value) else '',
        'pair_type'              : pair_type,
        'recal_rho'              : round(recal_rho, 4) if not np.isnan(recal_rho) else '',
        'naive_rho'              : round(naive_rho, 4) if not np.isnan(naive_rho) else '',
    }


def append_grade_log(rows: List[dict]) -> None:
    """Append graded rows to data/cache/sgp_grade_log.csv."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not GRADE_LOG.exists()
    with open(GRADE_LOG, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=GRADE_LOG_FIELDS, extrasaction='ignore')
        if new_file:
            w.writeheader()
        w.writerows(rows)
    print(f"[grade_sgp_edge] Appended {len(rows)} rows to {GRADE_LOG}")


def print_grade_table(graded: List[dict]) -> None:
    """Print a grading summary table."""
    print()
    print("=" * 110)
    print("SGP GRADE TABLE — Real FD SGP EV")
    print("  real_sgp_ev = P_recal * combined_decimal_odds - 1.0")
    print("  outcome: HIT/MISS (post-game) or PENDING (pre-game)")
    print("=" * 110)
    hdr = (
        f"{'#':>3} {'PlayerA':<20} {'PlayerB':<20} "
        f"{'SA':>4} {'SB':>4} {'CombOdds':>9} {'P_recal':>8} "
        f"{'real_EV':>8} {'Outcome':>9}"
    )
    print(hdr)
    print("-" * 110)
    for i, g in enumerate(graded, 1):
        print(
            f"{i:>3} {g['player_a'][:20]:<20} {g['player_b'][:20]:<20} "
            f"{g['stat_a']:>4} {g['stat_b']:>4} "
            f"{g['combined_odds_american']:>9} "
            f"{g['p_recal']:>8} "
            f"{g['real_sgp_ev']:>8} "
            f"{g['outcome']:>9}"
        )
    print("-" * 110)
    ev_vals = [float(g['real_sgp_ev']) for g in graded if g['real_sgp_ev'] != '']
    if ev_vals:
        print(f"\nMean real_sgp_ev across {len(ev_vals)} pairs: {np.mean(ev_vals):+.2%}")
    hits = [g for g in graded if g['outcome'] == 'HIT']
    misses = [g for g in graded if g['outcome'] == 'MISS']
    if hits or misses:
        n = len(hits) + len(misses)
        rvs = [float(g['realized_value']) for g in graded
               if g['outcome'] in ('HIT', 'MISS')]
        stakes = [1.0] * len(rvs)
        roi = (sum(rvs) - sum(stakes)) / sum(stakes) if stakes else float('nan')
        print(f"Graded: {n} (HIT={len(hits)}, MISS={len(misses)}), ROI={roi:+.2%}")
    print()


def bootstrap_ev_ci(ev_vals: List[float], n_boot: int = 5000, ci: float = 0.95) -> Tuple[float, float]:
    """Bootstrap confidence interval for mean EV."""
    if len(ev_vals) < 2:
        return float('nan'), float('nan')
    arr = np.array(ev_vals)
    boot_means = [np.mean(np.random.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    return float(np.percentile(boot_means, alpha * 100)), float(np.percentile(boot_means, (1 - alpha) * 100))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_grader(date_str: str, box_date_str: Optional[str] = None) -> List[dict]:
    """Grade all SGP prices for the given date.

    Args:
        date_str:      Date of the SGP price file (YYYY-MM-DD).
        box_date_str:  Date of the box score to grade outcomes (defaults to date_str).

    Returns list of graded dicts.
    """
    if box_date_str is None:
        box_date_str = date_str

    print(f"[grade_sgp_edge] Loading SGP prices for {date_str}...")
    sgp_df = load_sgp_prices(date_str)
    if sgp_df is None or sgp_df.empty:
        print(f"  No SGP price file at data/lines/{date_str}_fd_sgp.csv")
        print("  Run scripts/fanduel_sgp_scraper.py first to capture SGP prices.")
        return []

    print(f"  Loaded {len(sgp_df)} SGP price rows.")

    print(f"[grade_sgp_edge] Loading recal candidates for {date_str}...")
    recal_df = load_recal_candidates(date_str)
    if recal_df is None:
        print("  Could not load recal candidates — check predictions_cache and lines files.")
        return []
    print(f"  Loaded {len(recal_df)} recal candidate pairs.")

    print(f"[grade_sgp_edge] Loading box scores for {box_date_str} (for outcome grading)...")
    box_df = load_box_scores(box_date_str)
    if box_df is None:
        print("  No box score data — outcomes will be PENDING.")
    else:
        print(f"  Box score: {len(box_df)} player-game rows.")

    graded = [grade_pair(row, recal_df, box_df) for _, row in sgp_df.iterrows()]

    print_grade_table(graded)
    append_grade_log(graded)

    ev_vals = [float(g['real_sgp_ev']) for g in graded if g['real_sgp_ev'] != '']
    if ev_vals:
        lo, hi = bootstrap_ev_ci(ev_vals)
        print(f"Bootstrap 95% CI for mean real_sgp_ev: [{lo:+.2%}, {hi:+.2%}]")
        if lo > 0:
            print("  CI excludes 0 — candidate graded edge (requires >=30 observations to confirm).")
        else:
            print("  CI includes 0 — edge not confirmed yet.")

    return graded


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description="Grade SGP edge candidates vs real FD prices")
    ap.add_argument('--date', required=True, help='Date for SGP price file (YYYY-MM-DD)')
    ap.add_argument('--box-date', default=None,
                    help='Date for box score outcome grading (default: same as --date)')
    args = ap.parse_args()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        run_grader(args.date, args.box_date)
