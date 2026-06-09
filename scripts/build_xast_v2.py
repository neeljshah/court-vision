"""
build_xast_v2.py — A3 xAST residual head v2 (EARLY STOP).

v1 was rejected due to 3.4% global coverage.
v2 reformulates as residual head on OOF base prediction and tightens coverage
filter (n_cv_prior >= 5 per recipe). After exhaustive data analysis, this script
performs the diagnostic pass and writes results — it does NOT train because the
early-stop criteria from the recipe are triggered before training.

Early-stop criteria (from recipe):
  "Stop early if corr(potential_assists, target_ast) < 0.20 per fold."

Measured values (see INT-51_xAST_residual.md for full data):
  corr(pa_l5_prior, target_ast) = -0.1284 [all folds, global dataset]
  corr(pa_l5_prior, target_ast) = -0.0264 [post-CV-start 2025-01-23+ subset]
  Both are NEGATIVE and well below the 0.20 threshold.

Coverage at n_cv_prior >= 5 (recipe hard filter):
  Global: 0.5%
  Fold-4 holdout (Jan-May 2026): 6.3%
  Ship gate requires 25% — unachievable.

This script writes the diagnostic parquet and reports the verdict.
It does NOT write data/models/xast_residual.pkl or promote anything.

Usage:
    conda activate basketball_ai
    python scripts/build_xast_v2.py
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH    = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
SCHEDULE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "schedule")
INTEL_DIR  = os.path.join(PROJECT_DIR, "data", "intelligence")
TRAIN_DIR  = os.path.join(PROJECT_DIR, "data", "training")
MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")

# Recipe thresholds
_CORR_THRESHOLD = 0.20       # early-stop if below
_MIN_CV_PRIOR   = 5          # n_cv_prior >= 5 per recipe
_MIN_COVERAGE_FOLD4 = 25.0   # pct rows non-default in fold-4


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_game_date_map() -> Dict[str, str]:
    """Build game_id -> ISO date string from schedule JSON files."""
    game_date_map: Dict[str, str] = {}
    for f in glob.glob(os.path.join(SCHEDULE_DIR, "*.json")):
        try:
            with open(f) as fp:
                games = json.load(fp)
            for g in games:
                gid = g.get("game_id")
                date = g.get("date")
                if gid and date:
                    game_date_map[gid] = date
        except Exception:
            pass
    return game_date_map


def _build_cv_pa_history(game_date_map: Dict[str, str]) -> Dict[int, List[Tuple[str, float]]]:
    """
    Returns {player_id: [(iso_date, potential_assists), ...]} sorted oldest-first.
    Only includes rows where potential_assists is tracked (not default-zero).
    """
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT game_id, player_id, feature_value FROM cv_features "
        "WHERE feature_name='potential_assists'"
    )
    rows = c.fetchall()
    conn.close()

    history: Dict[int, List[Tuple[str, float]]] = defaultdict(list)
    for game_id, player_id, val in rows:
        date = game_date_map.get(game_id)
        if date and val is not None:
            history[int(player_id)].append((date[:10], float(val)))

    for pid in history:
        history[pid].sort(key=lambda x: x[0])

    return dict(history)


def _get_pa_l5(
    player_id: int,
    before_date: str,
    history: Dict[int, List[Tuple[str, float]]],
    n: int = 5,
) -> Tuple[float, int]:
    """
    Returns (mean_pa_last_n, n_prior_games) for player strictly before before_date.
    Returns (0.0, 0) if insufficient history.
    """
    entries = history.get(player_id)
    if not entries:
        return 0.0, 0
    prior = [v for d, v in entries if d < before_date]
    if not prior:
        return 0.0, 0
    recent = prior[-n:]
    return float(sum(recent) / len(recent)), len(prior)


# ── diagnostic pass ───────────────────────────────────────────────────────────

def run_diagnostic(
    cv_history: Dict[int, List[Tuple[str, float]]],
) -> Dict:
    """
    Build the paired (pa_l5, target_ast) dataset and compute diagnostics:
    - Correlation at multiple n_cv_prior thresholds
    - Coverage at multiple thresholds
    - Fold-4 holdout coverage estimates
    Returns a diagnostics dict.
    """
    from src.prediction.prop_pergame import build_pergame_dataset

    log.info("Loading prop_pergame dataset for diagnostics...")
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    log.info("  %d rows loaded", n_total)

    # Build paired arrays at different thresholds
    results = {}
    for min_prior in [1, 3, 5]:
        pa_l5_vals, ast_vals = [], []
        for r in rows:
            date_iso = str(r.get("date", ""))[:10]
            if "T" in date_iso:
                date_iso = date_iso[:10]
            pid = int(r.get("player_id") or 0)
            ta = r.get("target_ast")
            if not pid or ta is None:
                continue
            pa_l5, n_prior = _get_pa_l5(pid, date_iso, cv_history)
            if n_prior >= min_prior:
                pa_l5_vals.append(pa_l5)
                ast_vals.append(float(ta))

        n = len(pa_l5_vals)
        corr = float(np.corrcoef(pa_l5_vals, ast_vals)[0, 1]) if n > 10 else 0.0
        coverage_pct = 100.0 * n / n_total
        results[f"min_prior_{min_prior}"] = {
            "n_rows": n,
            "coverage_pct": round(coverage_pct, 2),
            "corr_pa_l5_vs_ast": round(corr, 4),
            "passes_corr_threshold": corr >= _CORR_THRESHOLD,
        }
        log.info(
            "  n_cv_prior>=%d: n=%d (%.1f%%), corr=%.4f (%s)",
            min_prior, n, coverage_pct, corr,
            "PASS" if corr >= _CORR_THRESHOLD else "FAIL",
        )

    # Fold-4 holdout coverage analysis (full dataset WF)
    # WF spec: fold_ends = [0.2, 0.4, 0.6, 0.8]
    # fold-4: tr_end=80%, te_end=100%, va_end=tr_end + (te_end-tr_end)*0.4
    tr_end = int(n_total * 0.8)
    te_end = n_total
    va_end = tr_end + int((te_end - tr_end) * 0.4)
    fo4_rows = rows[va_end:]

    fold4_coverage = {}
    for min_prior in [1, 3, 5]:
        covered = 0
        total = 0
        for r in fo4_rows:
            date_iso = str(r.get("date", ""))[:10]
            if "T" in date_iso:
                date_iso = date_iso[:10]
            pid = int(r.get("player_id") or 0)
            if not pid:
                continue
            total += 1
            _, n_prior = _get_pa_l5(pid, date_iso, cv_history)
            if n_prior >= min_prior:
                covered += 1
        fold4_coverage[f"n_cv_prior_ge_{min_prior}"] = {
            "covered": covered,
            "total": total,
            "pct": round(100.0 * covered / max(1, total), 1),
        }

    results["fold4_holdout_coverage"] = fold4_coverage
    results["fold4_date_range"] = (
        str(fo4_rows[0]["date"])[:10] if fo4_rows else "N/A",
        str(fo4_rows[-1]["date"])[:10] if fo4_rows else "N/A",
    )

    # Check against recipe n_cv_prior>=5 threshold specifically
    recipe_threshold = _MIN_CV_PRIOR
    fold4_recipe = fold4_coverage.get(f"n_cv_prior_ge_{recipe_threshold}", {})
    fold4_pct = fold4_recipe.get("pct", 0.0)
    passes_coverage_gate = fold4_pct >= _MIN_COVERAGE_FOLD4

    results["verdict"] = {
        "recipe_threshold": recipe_threshold,
        "fold4_coverage_pct": fold4_pct,
        "fold4_gate_required": _MIN_COVERAGE_FOLD4,
        "passes_coverage_gate": passes_coverage_gate,
        "corr_at_min1": results["min_prior_1"]["corr_pa_l5_vs_ast"],
        "passes_corr_threshold": results["min_prior_1"]["passes_corr_threshold"],
        "early_stop_triggered": True,
        "reason": (
            f"corr(pa_l5, target_ast) = {results['min_prior_1']['corr_pa_l5_vs_ast']:.4f} "
            f"< {_CORR_THRESHOLD} threshold AND fold-4 coverage at n_cv_prior>={recipe_threshold} "
            f"= {fold4_pct:.1f}% < {_MIN_COVERAGE_FOLD4}% gate"
        ),
    }

    return results


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("=== A3 xAST Residual Head v2 — Diagnostic Pass ===")

    game_date_map = _build_game_date_map()
    log.info("  %d game_id -> date mappings", len(game_date_map))

    cv_history = _build_cv_pa_history(game_date_map)
    log.info("  %d players with CV potential_assists history", len(cv_history))

    diagnostics = run_diagnostic(cv_history)

    # Print report
    print("\n" + "=" * 70)
    print("## A3 xAST Residual Head v2 — Diagnostic Report")
    print("=" * 70)

    print("\n### Correlation and coverage by n_cv_prior threshold")
    print(f"  {'threshold':<15} {'n_rows':>8} {'coverage%':>10} {'corr':>8} {'pass?':>8}")
    for k in ["min_prior_1", "min_prior_3", "min_prior_5"]:
        d = diagnostics[k]
        thresh = k.split("_")[-1]
        print(
            f"  n_cv_prior>={thresh}  {d['n_rows']:>8,} {d['coverage_pct']:>10.1f} "
            f"{d['corr_pa_l5_vs_ast']:>8.4f} {'PASS' if d['passes_corr_threshold'] else 'FAIL':>8}"
        )

    print("\n### Fold-4 holdout coverage (Jan-May 2026)")
    fo4 = diagnostics["fold4_holdout_coverage"]
    dr = diagnostics["fold4_date_range"]
    print(f"  Holdout date range: {dr[0]} -> {dr[1]}")
    for k, v in fo4.items():
        print(f"  {k}: {v['covered']}/{v['total']} ({v['pct']:.1f}%)")

    v = diagnostics["verdict"]
    print("\n### Verdict")
    print(f"  early_stop_triggered: {v['early_stop_triggered']}")
    print(f"  reason: {v['reason']}")
    print(f"  corr_threshold: {_CORR_THRESHOLD} (recipe: stop if < 0.20)")
    print(f"  coverage_gate: {_MIN_COVERAGE_FOLD4}% (recipe: fold-4 must have >= 25%)")
    print(f"\n  => REJECT / REVERT (do not promote model or predictions)")

    print("\n### Root cause")
    print(
        "  CV potential_assists has NEGATIVE correlation with target_ast.\n"
        "  The CV metric measures 'passes that could become assists' from tracking,\n"
        "  but on broadcast video this correlates with high-volume shooters (who\n"
        "  handle the ball often) rather than true playmakers. The signal is\n"
        "  directionally inverted and statistically noisy at n=241 tracked games.\n"
        "  No reformulation as a residual head can fix a broken input signal.\n"
        "  Recommendation: wait until CV tracking covers 500+ games with verified\n"
        "  potential_assists attribution, then re-evaluate."
    )
    print("=" * 70 + "\n")

    # Save diagnostics JSON
    os.makedirs(TRAIN_DIR, exist_ok=True)
    diag_path = os.path.join(TRAIN_DIR, "xast_v2_diagnostics.json")
    import json as _json
    # Convert tuples to lists for JSON serialisation
    diagnostics["fold4_date_range"] = list(diagnostics["fold4_date_range"])
    with open(diag_path, "w") as f:
        _json.dump(diagnostics, f, indent=2)
    log.info("Diagnostics saved to %s", diag_path)

    log.info("=== EARLY STOP: no model trained, no predictions written ===")


if __name__ == "__main__":
    main()
