"""
diagnose_per_stat_cv_corrs.py — D4 substitute diagnostic deliverable.

For each stat in {pts, fg3m, stl, blk, tov}:
  For each CV feature in the D4 candidate set:
    For each n_cv_prior threshold in {1, 3, 5}:
      - Compute Pearson(cv_feature_l5, target_stat) with strict shift(1) prior
      - Track fold-4 coverage
  Emit JSON keyed by stat to data/training/x<stat>_v1_diagnostics.json

Strict shift(1) discipline: rolling-5 CV feature values are computed from
games strictly BEFORE the target game_date — no leakage.

Usage:
    conda activate basketball_ai
    python scripts/diagnose_per_stat_cv_corrs.py [--stat pts,fg3m,stl,blk,tov]
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
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
TRAIN_DIR = ROOT / "data" / "training"

# Recipe thresholds (same as A3/A4)
_CORR_THRESHOLD = 0.15
_MIN_CV_PRIOR = 5
_MIN_COVERAGE_FOLD4 = 25.0

# Stat -> (target key in prop_pergame row, output file stem)
_STAT_MAP = {
    "pts":  ("target_pts",  "xpts_v1_diagnostics.json"),
    "fg3m": ("target_fg3m", "xfg3m_v1_diagnostics.json"),
    "stl":  ("target_stl",  "xstl_v1_diagnostics.json"),
    "blk":  ("target_blk",  "xblk_v1_diagnostics.json"),
    "tov":  ("target_tov",  "xtov_v1_diagnostics.json"),
}

# CV features to evaluate for each stat (D4 candidate set from recipe)
_CV_FEATURES = [
    "paint_dwell_pct",
    "avg_spacing",
    "contested_shot_rate",
    "catch_shoot_pct",
    "avg_defender_distance",
    "touches_per_game",
    "shots_per_possession",
]

# DB-level feature names (some stored without _l5 suffix)
_CV_FETCH_NAMES = list(_CV_FEATURES)


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
    nba_dir = ROOT / "data" / "nba"
    for fpath in glob.glob(str(nba_dir / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as fp:
                data = json.load(fp)
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


def _build_cv_history(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """
    Returns {player_id: [(iso_date, {feat: val, ...}), ...]} sorted oldest-first.
    Fetches all D4 candidate features in a single query.
    """
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ",".join("?" for _ in _CV_FETCH_NAMES)
    c = conn.cursor()
    c.execute(
        f"SELECT game_id, player_id, feature_name, feature_value FROM cv_features "
        f"WHERE feature_name IN ({placeholders})",
        _CV_FETCH_NAMES,
    )
    raw = c.fetchall()
    conn.close()

    grouped: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    for game_id, player_id, feat, val in raw:
        if val is not None:
            grouped[(str(game_id), int(player_id))][feat] = float(val)

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
    Strict shift(1): only games with date < before_date are included.
    """
    entries = history.get(player_id)
    if not entries:
        return {}, 0
    prior = [(d, fv) for d, fv in entries if d < before_date]
    if not prior:
        return {}, 0
    recent = prior[-n:]
    feat_sums: Dict[str, float] = {}
    feat_counts: Dict[str, int] = {}
    for _, fv in recent:
        for feat, val in fv.items():
            feat_sums[feat] = feat_sums.get(feat, 0.0) + val
            feat_counts[feat] = feat_counts.get(feat, 0) + 1
    means = {f: feat_sums[f] / feat_counts[f] for f in feat_sums}
    return means, len(prior)


# ── diagnostic for one stat ───────────────────────────────────────────────────

def run_stat_diagnostic(
    stat: str,
    target_key: str,
    rows: list,
    cv_history: Dict[int, List[Tuple[str, Dict[str, float]]]],
) -> Dict:
    """Run full diagnostic for one stat across all CV features and thresholds."""
    n_total = len(rows)
    log.info("  [%s] n_total_rows=%d", stat, n_total)

    # Fold-4 boundary (same logic as build_xreb_v2.py)
    tr_end = int(n_total * 0.8)
    te_end = n_total
    va_end = tr_end + int((te_end - tr_end) * 0.4)
    fo4_rows = rows[va_end:]
    fold4_dates = [str(r.get("date", ""))[:10] for r in fo4_rows if r.get("date")]
    fold4_date_range = [
        min(fold4_dates) if fold4_dates else "N/A",
        max(fold4_dates) if fold4_dates else "N/A",
    ]

    feature_correlations: Dict[str, Dict] = {}

    for feat in _CV_FEATURES:
        feat_result: Dict[str, object] = {}
        for min_prior in [1, 3, 5]:
            feat_vals: List[float] = []
            target_vals: List[float] = []
            for r in rows:
                date_iso = str(r.get("date", ""))[:10]
                pid = int(r.get("player_id") or 0)
                t_val = r.get(target_key)
                if not pid or t_val is None:
                    continue
                cv_feats, n_prior = _get_cv_l5(pid, date_iso, cv_history)
                if n_prior >= min_prior:
                    fv = cv_feats.get(feat)
                    if fv is not None:
                        feat_vals.append(fv)
                        target_vals.append(float(t_val))

            n = len(feat_vals)
            corr = (
                float(np.corrcoef(feat_vals, target_vals)[0, 1])
                if n > 10
                else float("nan")
            )
            feat_result[f"n_>={min_prior}"] = n
            feat_result[f"corr_>={min_prior}"] = round(corr, 4) if not np.isnan(corr) else None

        feature_correlations[f"{feat}_l5"] = feat_result

    # Fold-4 coverage: rows where player has cv data with any feature present
    fold4_coverage: Dict[str, Dict] = {}
    for min_prior in [1, 3, 5]:
        covered = 0
        total = 0
        for r in fo4_rows:
            date_iso = str(r.get("date", ""))[:10]
            pid = int(r.get("player_id") or 0)
            if not pid:
                continue
            total += 1
            cv_feats, n_prior = _get_cv_l5(pid, date_iso, cv_history)
            if n_prior >= min_prior and cv_feats:
                covered += 1
        fold4_coverage[f"n_>={min_prior}"] = {
            "covered": covered,
            "total": total,
            "pct": round(100.0 * covered / max(1, total), 1),
        }

    # Verdict: top feature at recipe threshold
    top_feat = None
    top_corr: Optional[float] = None
    feats_above_threshold = []
    for feat_key, feat_data in feature_correlations.items():
        c = feat_data.get(f"corr_>={_MIN_CV_PRIOR}")
        if c is not None and not (isinstance(c, float) and np.isnan(c)):
            if top_corr is None or abs(float(c)) > abs(top_corr):
                top_feat = feat_key
                top_corr = float(c)
            if float(c) >= _CORR_THRESHOLD:
                feats_above_threshold.append(feat_key)

    fold4_pct_recipe = fold4_coverage.get(f"n_>={_MIN_CV_PRIOR}", {}).get("pct", 0.0)
    coverage_gate_fail = fold4_pct_recipe < _MIN_COVERAGE_FOLD4

    verdict = {
        "stat": stat,
        "corr_threshold": _CORR_THRESHOLD,
        "recipe_n_cv_prior": _MIN_CV_PRIOR,
        "top_cv_feature_at_recipe_threshold": top_feat,
        "top_corr_at_recipe_threshold": round(top_corr, 4) if top_corr is not None else None,
        "n_features_above_threshold": len(feats_above_threshold),
        "features_above_threshold": feats_above_threshold,
        "fold4_coverage_pct_at_n5": fold4_pct_recipe,
        "fold4_gate_required": _MIN_COVERAGE_FOLD4,
        "coverage_gate_fail": coverage_gate_fail,
        "d4_eligible": len(feats_above_threshold) >= 2 and not coverage_gate_fail,
    }

    log.info(
        "  [%s] top_feat=%s top_corr=%s n_above_threshold=%d fold4_cov=%.1f%%",
        stat,
        top_feat,
        f"{top_corr:.4f}" if top_corr is not None else "N/A",
        len(feats_above_threshold),
        fold4_pct_recipe,
    )

    return {
        "n_train_total": n_total,
        "feature_correlations": feature_correlations,
        "fold_4_coverage": fold4_coverage,
        "fold4_date_range": fold4_date_range,
        "verdict": verdict,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main(stats: Optional[List[str]] = None) -> Dict[str, Dict]:
    if stats is None:
        stats = list(_STAT_MAP.keys())

    log.info("=== D4 Substitute Diagnostic: per-stat CV correlations ===")
    log.info("Stats: %s", stats)
    log.info("CV features: %s", _CV_FEATURES)

    game_date_map = _build_game_date_map()
    log.info("game_date_map: %d entries", len(game_date_map))

    cv_history = _build_cv_history(game_date_map)
    log.info("cv_history: %d players", len(cv_history))

    # Load prop_pergame dataset once
    from src.prediction.prop_pergame import build_pergame_dataset
    log.info("Loading prop_pergame dataset...")
    all_rows, _ = build_pergame_dataset(min_prior=0)
    all_rows.sort(key=lambda r: str(r.get("date", "")))
    log.info("prop_pergame dataset: %d rows", len(all_rows))

    results: Dict[str, Dict] = {}
    summary_rows = []

    for stat in stats:
        if stat not in _STAT_MAP:
            log.warning("Unknown stat %s — skipping", stat)
            continue
        target_key, out_filename = _STAT_MAP[stat]
        log.info("--- Running diagnostic for %s (target=%s) ---", stat, target_key)

        diag = run_stat_diagnostic(stat, target_key, all_rows, cv_history)
        results[stat] = diag

        # Write individual JSON
        out_path = TRAIN_DIR / out_filename
        TRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as fp:
            json.dump(diag, fp, indent=2)
        log.info("  Wrote %s", out_path)

        v = diag["verdict"]
        summary_rows.append({
            "stat": stat,
            "top_feature": v.get("top_cv_feature_at_recipe_threshold", "N/A"),
            "top_corr": v.get("top_corr_at_recipe_threshold"),
            "n_above_0.15": v.get("n_features_above_threshold", 0),
            "fold4_cov_%": v.get("fold4_coverage_pct_at_n5", 0.0),
            "d4_eligible": v.get("d4_eligible", False),
        })

    # Print summary table
    print("\n" + "=" * 80)
    print("## D4 Substitute Diagnostic — Summary Table")
    print("=" * 80)
    print(f"  {'stat':<6} {'top_cv_feature':<30} {'corr@n5':>8} {'n>=0.15':>8} {'fold4%':>8} {'D4?':>6}")
    print("  " + "-" * 72)
    for sr in summary_rows:
        corr_str = f"{sr['top_corr']:.4f}" if sr["top_corr"] is not None else "   N/A"
        d4_flag = "YES" if sr["d4_eligible"] else "no"
        print(
            f"  {sr['stat']:<6} {str(sr['top_feature']):<30} {corr_str:>8} "
            f"{sr['n_above_0.15']:>8} {sr['fold4_cov_%']:>8.1f} {d4_flag:>6}"
        )
    print("=" * 80)
    print(f"\nD4 re-open requires: >=2 features with corr>=+0.15 AND fold4 coverage>=20%")
    print(f"Threshold used: corr_threshold={_CORR_THRESHOLD}, n_cv_prior={_MIN_CV_PRIOR}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="D4 per-stat CV correlation diagnostic")
    parser.add_argument(
        "--stat",
        default=",".join(_STAT_MAP.keys()),
        help="Comma-separated stats to run (default: all 5)",
    )
    args = parser.parse_args()
    stat_list = [s.strip().lower() for s in args.stat.split(",") if s.strip()]
    main(stat_list)
