"""
build_xreb_v2.py — A4 xREB residual head v2 diagnostic + early-stop probe.

Formulates REB as a residual head on OOF base prediction:
  target_residual = target_reb - oof_reb_pred
  oof_reb_pred = mean(l5_reb, ewma_reb) if OOF parquet absent

Early-stop probe (recipe thresholds — REB noisier than AST):
  corr(paint_dwell_pct_l5, target_reb) at n_cv_prior >= 5
  corr(opp_paint_pct_allowed_z, target_reb) at n_cv_prior >= 5
  BOTH < 0.15 (lower than A3's 0.20 because REB is noisier) -> EARLY STOP
  Fold-4 coverage < 25% -> EARLY STOP

Training filter (applied only if probe passes):
  n_cv_prior >= 5 AND player_id in player_fingerprints

Usage:
    conda activate basketball_ai
    python scripts/build_xreb_v2.py
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = ROOT / "data" / "nba_ai.db"
SCHEDULE_DIR = ROOT / "data" / "nba" / "schedule"
INTEL_DIR = ROOT / "data" / "intelligence"
TRAIN_DIR = ROOT / "data" / "training"

FINGERPRINTS_PARQUET = INTEL_DIR / "player_fingerprints.parquet"
OPP_PAINT_PARQUET = INTEL_DIR / "opp_paint_allowance.parquet"
DIAG_OUT = TRAIN_DIR / "xreb_v2_diagnostics.json"

# Recipe thresholds
_CORR_THRESHOLD = 0.15       # lower than A3 (0.20) — REB is noisier
_MIN_CV_PRIOR = 5            # n_cv_prior >= 5 per recipe
_MIN_COVERAGE_FOLD4 = 25.0   # pct rows non-default in fold-4

# CV features we need for REB
_CV_FEATURES_REB = [
    "paint_dwell_pct",
    "touches_per_game",
    "shot_zone_paint_pct",
    "avg_off_ball_distance",
    "avg_spacing",
]

# Atlas archetypes relevant to REB (by NAME, not cluster ID)
_REB_ARCHETYPES = [
    "Versatile Big",
    "Off-Ball Big",
    "Stretch Big",
    "Versatile Forward",
    "Off-Ball Forward",
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_game_date_map() -> Dict[str, str]:
    """Build game_id -> ISO date string from schedule JSON files."""
    game_date_map: Dict[str, str] = {}
    for f in glob.glob(str(SCHEDULE_DIR / "*.json")):
        try:
            with open(f) as fp:
                games = json.load(fp)
            for g in games:
                gid = g.get("game_id")
                date = g.get("date")
                if gid and date:
                    game_date_map[str(gid)] = str(date)[:10]
        except Exception:
            pass
    # Also load from season_games JSON for date coverage
    nba_dir = ROOT / "data" / "nba"
    for fpath in glob.glob(str(nba_dir / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row:
                    gid = str(row["game_id"])
                    date = row.get("game_date", "")
                    if gid and date:
                        game_date_map.setdefault(gid, str(date)[:10])
        except Exception:
            pass
    return game_date_map


def _build_cv_feature_history(
    game_date_map: Dict[str, str],
    feature_names: List[str],
) -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """
    Returns {player_id: [(iso_date, {feat: val, ...}), ...]} sorted oldest-first.
    Only includes rows where at least one of the requested features is present.
    """
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ",".join("?" for _ in feature_names)
    c = conn.cursor()
    c.execute(
        f"SELECT game_id, player_id, feature_name, feature_value FROM cv_features "
        f"WHERE feature_name IN ({placeholders})",
        feature_names,
    )
    rows = c.fetchall()
    conn.close()

    # Group by (game_id, player_id)
    grouped: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    for game_id, player_id, feat, val in rows:
        if val is not None:
            grouped[(str(game_id), int(player_id))][feat] = float(val)

    # Convert to per-player history
    history: Dict[int, List[Tuple[str, Dict[str, float]]]] = defaultdict(list)
    for (game_id, player_id), feat_dict in grouped.items():
        date = game_date_map.get(game_id)
        if date:
            history[player_id].append((date, feat_dict))

    for pid in history:
        history[pid].sort(key=lambda x: x[0])

    return dict(history)


def _get_cv_l5(
    player_id: int,
    before_date: str,
    history: Dict[int, List[Tuple[str, Dict[str, float]]]],
    n: int = 5,
) -> Tuple[Dict[str, float], int]:
    """
    Returns (mean_feats_last_n, n_prior_games) strictly before before_date.
    Returns ({}, 0) if insufficient history.
    """
    entries = history.get(player_id)
    if not entries:
        return {}, 0
    prior = [(d, fv) for d, fv in entries if d < before_date]
    if not prior:
        return {}, 0
    recent = prior[-n:]
    # Average each feature
    feat_sums: Dict[str, float] = {}
    feat_counts: Dict[str, int] = {}
    for _, fv in recent:
        for feat, val in fv.items():
            feat_sums[feat] = feat_sums.get(feat, 0.0) + val
            feat_counts[feat] = feat_counts.get(feat, 0) + 1
    means = {f: feat_sums[f] / feat_counts[f] for f in feat_sums}
    return means, len(prior)


# ── diagnostic pass ───────────────────────────────────────────────────────────

def run_diagnostic(
    cv_history: Dict[int, List[Tuple[str, Dict[str, float]]]],
) -> Dict:
    """
    Build paired (cv_feats_l5, target_reb, opp_paint_z) dataset
    and compute early-stop probe diagnostics.
    """
    from src.prediction.prop_pergame import build_pergame_dataset

    log.info("Loading prop_pergame dataset for diagnostics...")
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: str(r.get("date", "")))
    n_total = len(rows)
    log.info("  %d rows loaded", n_total)

    # Load opp_paint_allowance for C4 join
    opp_paint_df: Optional[pd.DataFrame] = None
    if OPP_PAINT_PARQUET.exists():
        opp_paint_df = pd.read_parquet(OPP_PAINT_PARQUET)
        log.info("  opp_paint_allowance loaded: %d rows", len(opp_paint_df))
    else:
        log.warning("  opp_paint_allowance.parquet not found; C4 join skipped")

    def _get_opp_paint_z(opp_team: str, game_date: str) -> Optional[float]:
        if opp_paint_df is None or not opp_team:
            return None
        subset = opp_paint_df[
            (opp_paint_df["team_id"] == opp_team.upper()) &
            (opp_paint_df["game_date"] < game_date)
        ]
        if subset.empty:
            return None
        return float(subset.sort_values("game_date").iloc[-1]["opp_paint_pct_allowed_z"])

    # Build diagnostic at multiple n_cv_prior thresholds
    diag_results = {}

    for min_prior in [1, 3, 5]:
        paint_dwell_vals = []
        opp_paint_z_vals = []
        reb_vals = []
        covered = 0

        for r in rows:
            date_iso = str(r.get("date", ""))[:10]
            pid = int(r.get("player_id") or 0)
            t_reb = r.get("target_reb")
            if not pid or t_reb is None:
                continue

            cv_feats, n_prior = _get_cv_l5(pid, date_iso, cv_history)
            if n_prior >= min_prior and cv_feats:
                pd_val = cv_feats.get("paint_dwell_pct")
                if pd_val is not None:
                    paint_dwell_vals.append(pd_val)
                    reb_vals.append(float(t_reb))
                    covered += 1

                    opp_team = r.get("opp_team") or r.get("opponent") or ""
                    opp_z = _get_opp_paint_z(str(opp_team), date_iso)
                    opp_paint_z_vals.append(opp_z if opp_z is not None else float("nan"))

        n = len(paint_dwell_vals)
        corr_pd = float(np.corrcoef(paint_dwell_vals, reb_vals)[0, 1]) if n > 10 else 0.0

        opp_z_arr = np.array(opp_paint_z_vals)
        reb_arr = np.array(reb_vals)
        mask = ~np.isnan(opp_z_arr)
        corr_opp = (
            float(np.corrcoef(opp_z_arr[mask], reb_arr[mask])[0, 1])
            if mask.sum() > 10 else float("nan")
        )

        coverage_pct = 100.0 * n / n_total

        diag_results[f"min_prior_{min_prior}"] = {
            "n_rows": n,
            "coverage_pct": round(coverage_pct, 2),
            "corr_paint_dwell_l5_vs_reb": round(corr_pd, 4),
            "corr_opp_paint_z_vs_reb": round(corr_opp, 4) if not np.isnan(corr_opp) else None,
            "n_opp_paint_z_matched": int(mask.sum()) if opp_paint_df is not None else 0,
            "passes_corr_threshold_pd": abs(corr_pd) >= _CORR_THRESHOLD,
            "passes_corr_threshold_opp": (
                abs(corr_opp) >= _CORR_THRESHOLD if not np.isnan(corr_opp) else False
            ),
        }
        log.info(
            "  n_cv_prior>=%d: n=%d (%.1f%%), corr_pd=%.4f, corr_opp=%s",
            min_prior, n, coverage_pct, corr_pd,
            f"{corr_opp:.4f}" if not np.isnan(corr_opp) else "N/A",
        )

    # Fold-4 holdout coverage
    tr_end = int(n_total * 0.8)
    te_end = n_total
    va_end = tr_end + int((te_end - tr_end) * 0.4)
    fo4_rows = rows[va_end:]

    fold4_coverage = {}
    for min_prior in [1, 3, 5]:
        covered_f4 = 0
        total_f4 = 0
        for r in fo4_rows:
            date_iso = str(r.get("date", ""))[:10]
            pid = int(r.get("player_id") or 0)
            if not pid:
                continue
            total_f4 += 1
            _, n_prior = _get_cv_l5(pid, date_iso, cv_history)
            cv_feats_check, _ = _get_cv_l5(pid, date_iso, cv_history)
            if n_prior >= min_prior and cv_feats_check.get("paint_dwell_pct") is not None:
                covered_f4 += 1
        fold4_coverage[f"n_cv_prior_ge_{min_prior}"] = {
            "covered": covered_f4,
            "total": total_f4,
            "pct": round(100.0 * covered_f4 / max(1, total_f4), 1),
        }

    diag_results["fold4_holdout_coverage"] = fold4_coverage
    diag_results["fold4_date_range"] = [
        str(fo4_rows[0]["date"])[:10] if fo4_rows else "N/A",
        str(fo4_rows[-1]["date"])[:10] if fo4_rows else "N/A",
    ]

    # Early-stop verdict at recipe threshold (n_cv_prior >= 5)
    recipe_key = f"min_prior_{_MIN_CV_PRIOR}"
    recipe_data = diag_results.get(recipe_key, {})
    fold4_recipe = fold4_coverage.get(f"n_cv_prior_ge_{_MIN_CV_PRIOR}", {})
    fold4_pct = fold4_recipe.get("pct", 0.0)

    corr_pd_recipe = recipe_data.get("corr_paint_dwell_l5_vs_reb", 0.0)
    corr_opp_recipe = recipe_data.get("corr_opp_paint_z_vs_reb") or 0.0
    both_below = (
        abs(corr_pd_recipe) < _CORR_THRESHOLD and
        abs(corr_opp_recipe) < _CORR_THRESHOLD
    )
    coverage_fail = fold4_pct < _MIN_COVERAGE_FOLD4

    early_stop = both_below or coverage_fail
    reasons = []
    if both_below:
        reasons.append(
            f"BOTH corr(paint_dwell_l5, target_reb)={corr_pd_recipe:.4f} "
            f"and corr(opp_paint_z, target_reb)={corr_opp_recipe:.4f} "
            f"< {_CORR_THRESHOLD} threshold"
        )
    if coverage_fail:
        reasons.append(
            f"fold-4 coverage at n_cv_prior>={_MIN_CV_PRIOR} = {fold4_pct:.1f}% "
            f"< {_MIN_COVERAGE_FOLD4}% gate"
        )

    diag_results["verdict"] = {
        "recipe_threshold_n_cv_prior": _MIN_CV_PRIOR,
        "corr_threshold": _CORR_THRESHOLD,
        "fold4_coverage_pct": fold4_pct,
        "fold4_gate_required": _MIN_COVERAGE_FOLD4,
        "corr_paint_dwell_at_recipe_threshold": corr_pd_recipe,
        "corr_opp_paint_z_at_recipe_threshold": corr_opp_recipe,
        "both_corr_below_threshold": both_below,
        "coverage_gate_fail": coverage_fail,
        "early_stop_triggered": early_stop,
        "reasons": reasons,
    }

    return diag_results


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> Dict:
    log.info("=== A4 xREB Residual Head v2 — Diagnostic Pass ===")

    game_date_map = _build_game_date_map()
    log.info("  %d game_id -> date mappings", len(game_date_map))

    cv_history = _build_cv_feature_history(game_date_map, _CV_FEATURES_REB)
    log.info("  %d players with CV feature history", len(cv_history))

    diagnostics = run_diagnostic(cv_history)

    # Print report
    print("\n" + "=" * 70)
    print("## A4 xREB Residual Head v2 — Diagnostic Report")
    print("=" * 70)

    print("\n### Correlation and coverage by n_cv_prior threshold")
    print(f"  {'threshold':<15} {'n_rows':>8} {'coverage%':>10} {'corr_pd':>10} {'corr_opp':>10}")
    for k in ["min_prior_1", "min_prior_3", "min_prior_5"]:
        d = diagnostics.get(k, {})
        thresh = k.split("_")[-1]
        corr_pd = d.get("corr_paint_dwell_l5_vs_reb", 0.0)
        corr_opp = d.get("corr_opp_paint_z_vs_reb")
        corr_opp_str = f"{corr_opp:.4f}" if corr_opp is not None else "  N/A "
        pd_pass = "PASS" if abs(corr_pd) >= _CORR_THRESHOLD else "FAIL"
        print(
            f"  n_cv_prior>={thresh}  {d.get('n_rows', 0):>8,} {d.get('coverage_pct', 0):>10.1f} "
            f"{corr_pd:>10.4f} {corr_opp_str:>10}  [{pd_pass}]"
        )

    print("\n### Fold-4 holdout coverage")
    fo4 = diagnostics.get("fold4_holdout_coverage", {})
    dr = diagnostics.get("fold4_date_range", ["N/A", "N/A"])
    print(f"  Holdout date range: {dr[0]} -> {dr[1]}")
    for k, v in fo4.items():
        gate_flag = "PASS" if v["pct"] >= _MIN_COVERAGE_FOLD4 else "FAIL"
        print(f"  {k}: {v['covered']}/{v['total']} ({v['pct']:.1f}%) [{gate_flag}]")

    v = diagnostics["verdict"]
    print("\n### Verdict")
    print(f"  early_stop_triggered: {v['early_stop_triggered']}")
    if v["reasons"]:
        for r in v["reasons"]:
            print(f"  reason: {r}")
    if not v["early_stop_triggered"]:
        print("  => PROBE PASSED: proceed to train_xreb_residual.py")
    else:
        print("  => REJECT / EARLY STOP (do not train model or write predictions)")
    print("=" * 70 + "\n")

    # Save diagnostics JSON
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with open(DIAG_OUT, "w") as f:
        json.dump(diagnostics, f, indent=2)
    log.info("Diagnostics saved to %s", DIAG_OUT)

    if v["early_stop_triggered"]:
        log.info("=== EARLY STOP: no model trained, no predictions written ===")
    else:
        log.info("=== PROBE PASSED: run train_xreb_residual.py to proceed ===")

    return diagnostics


if __name__ == "__main__":
    main()
