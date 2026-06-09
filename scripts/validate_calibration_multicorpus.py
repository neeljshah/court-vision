"""scripts/validate_calibration_multicorpus.py — EX-7 multi-corpus leak-free calibration validation.

Trains rolling-cut (pre-eval-start) XGBoost calibrators per corpus per stat,
grades calibrated vs raw ROI at blend weights a in {0.0, 0.5, 1.0}, and applies
a >=2-corpus acceptance rule to produce a justified enabled/blend recommendation.

Design:
- INDEPENDENT corpora: benashkar_2026, regular_season_2024_25_oddsapi,
  regular_season_2025_26_oddsapi. Playoffs excluded (beyond calframe max date).
  extended_oos excluded (same-window key mirror of benashkar).
- ROLLING CUT: for each corpus, train only on calframe rows with date < eval_start.
- COHERENCE guard: skip any corpus where blind-over + blind-under ROI sum >= 0.
- AST hard-excluded from calibration (raw always; only its raw ROI is reported).
- ACCEPTANCE: stat accepted into enabled with weight a* if calibrated ROI > raw ROI
  on >=2 independent corpora with n>=30 per stat per corpus (thin corpora don't
  count toward the >=2 gate). Prefer smallest a* in {0.5, 1.0} satisfying >=2.
- GPU: device=cuda with cpu fallback (per repo rule).
- Read-only: no model/corpus mutation, no production writes.

Run:
    python scripts/validate_calibration_multicorpus.py [corpus1.csv corpus2.csv ...]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.pit.intel_grade import (  # noqa: E402
    load_corpus, attach_pred, coherence, roi, _payout,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COVS: List[str] = [
    "pred", "l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
    "rest_days", "is_b2b", "is_home", "opp_pace", "opp_def",
    "vac_min", "vac_pts", "n_out", "l5_pts_pm", "l5_reb_pm",
    "month", "days_into_season",
]

CALFRAME_PATH = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"

DEFAULT_CORPORA: List[str] = [
    "benashkar_2026_canonical.csv",
    "regular_season_2024_25_oddsapi.csv",
    "regular_season_2025_26_oddsapi.csv",
]

# Stats to calibrate (AST always hard-excluded = never in candidates)
CANDIDATE_STATS: List[str] = ["pts", "reb", "fg3m"]
CANDIDATE_BLENDS: Tuple[float, ...] = (0.0, 0.5, 1.0)
MIN_TRAIN_ROWS = 500
MIN_CORPUS_N = 30  # minimum per-stat n in a corpus for it to count toward >=2

XGB_PARAMS = {
    "objective": "reg:absoluteerror",
    "max_depth": 4,
    "eta": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
}
NUM_BOOST_ROUND = 450

# ---------------------------------------------------------------------------
# Calframe loader (cached)
# ---------------------------------------------------------------------------

_CALFRAME: Optional[pd.DataFrame] = None


def _calframe() -> pd.DataFrame:
    global _CALFRAME
    if _CALFRAME is None:
        df = pd.read_parquet(CALFRAME_PATH)
        df["d"] = pd.to_datetime(df["date"]).dt.normalize()
        _CALFRAME = df
    return _CALFRAME


# ---------------------------------------------------------------------------
# Covariate index: (player_id, date, stat) -> full COVS row as dict
# ---------------------------------------------------------------------------

_COV_IDX: Optional[Dict[tuple, dict]] = None


def _build_cov_idx() -> Dict[tuple, dict]:
    global _COV_IDX
    if _COV_IDX is not None:
        return _COV_IDX
    df = _calframe()
    idx: Dict[tuple, dict] = {}
    for r in df.itertuples(index=False):
        key = (int(r.player_id), r.d, r.stat)
        idx[key] = {c: getattr(r, c) for c in COVS}
    _COV_IDX = idx
    return _COV_IDX


def _get_covs_for_bet(b: dict) -> Optional[dict]:
    """Return the full COVS dict from calframe for this bet, or None if not found."""
    idx = _build_cov_idx()
    return idx.get((b["pid"], b["gdate"], b["stat"]))


# ---------------------------------------------------------------------------
# Rolling-cut calibrator training
# ---------------------------------------------------------------------------

def _train_calibrator(stat: str, eval_start: pd.Timestamp):
    """Train a calibration booster using only calframe rows BEFORE eval_start.

    Returns (booster, feature_names) or None if not enough data.
    Leak guard: asserts train max date < eval_start.
    """
    try:
        import xgboost as xgb
    except ImportError:
        print("  [ERROR] xgboost not available")
        return None

    df = _calframe()
    train = df[(df["stat"] == stat) & (df["d"] < eval_start)].copy()

    if len(train) < MIN_TRAIN_ROWS:
        print(f"  [{stat}] SKIP — only {len(train)} train rows (need {MIN_TRAIN_ROWS})")
        return None

    # Leak guard
    assert train["d"].max() < eval_start, (
        f"Leak: train max date {train['d'].max()} >= eval_start {eval_start}"
    )

    # Drop rows with any NaN in COVS
    train_clean = train.dropna(subset=COVS)
    if len(train_clean) < MIN_TRAIN_ROWS:
        print(f"  [{stat}] SKIP after dropna — only {len(train_clean)} rows")
        return None

    print(f"  [{stat}] Training on {len(train_clean):,} rows (d < {eval_start.date()}) ...", end="", flush=True)

    params = dict(XGB_PARAMS, device="cuda")
    dtrain = xgb.DMatrix(train_clean[COVS], label=train_clean["actual"],
                         feature_names=COVS)

    try:
        booster = xgb.train(params, dtrain, num_boost_round=NUM_BOOST_ROUND,
                            verbose_eval=False)
    except Exception:
        params["device"] = "cpu"
        params.pop("tree_method", None)
        booster = xgb.train(params, dtrain, num_boost_round=NUM_BOOST_ROUND,
                            verbose_eval=False)

    print(" done.")
    return booster


# ---------------------------------------------------------------------------
# Grade blended ROI for one corpus
# ---------------------------------------------------------------------------

def _blend_roi(bets_stat: List[dict], booster, a: float) -> Dict:
    """Grade ROI using blend a*cal + (1-a)*pred for a single stat's bets."""
    try:
        import xgboost as xgb
    except ImportError:
        return roi(bets_stat, predictor="pred")

    if a <= 0.0 or booster is None:
        return roi(bets_stat, predictor="pred")

    # Predict calibrated values for all bets in this stat
    enriched = []
    for b in bets_stat:
        covs_dict = _get_covs_for_bet(b)
        if covs_dict is None:
            # fallback to raw pred; covariate missing NaNs become XGB missing natively
            row_vals = {c: b.get(c, float("nan")) for c in COVS}
            row_vals["pred"] = b["pred"]
            covs_dict = row_vals
        # Build feature row; missing covariate values become NaN (XGBoost handles)
        row = [float(covs_dict.get(c, float("nan"))) for c in COVS]
        enriched.append((b, row))

    if not enriched:
        return roi(bets_stat, predictor="pred")

    rows = [r for _, r in enriched]
    try:
        dm = xgb.DMatrix(rows, feature_names=COVS)
        cal_preds = booster.predict(dm)
    except Exception as e:
        print(f"    [WARN] predict failed ({e}), falling back to raw pred")
        return roi(bets_stat, predictor="pred")

    # Attach blended pred
    blended_bets = []
    for (b, _), cal in zip(enriched, cal_preds):
        bc = dict(b)
        bc["pred_blend"] = float(a * cal + (1.0 - a) * b["pred"])
        blended_bets.append(bc)

    return roi(blended_bets, predictor="pred_blend")


# ---------------------------------------------------------------------------
# Main corpus grading loop
# ---------------------------------------------------------------------------

def grade_corpus(name: str) -> Optional[Dict]:
    """Load, pred-join, coherence-check, rolling-cut calibrate, and grade one corpus.

    Returns a dict with per-stat ROI at each blend level, or None if skipped.
    """
    print(f"\n{'='*70}")
    print(f"CORPUS: {name}")
    print(f"{'='*70}")

    bets = load_corpus(name)
    if not bets:
        print("  SKIP — no bets loaded")
        return None

    bets = attach_pred(bets)
    if not bets:
        print("  SKIP — no bets joined to pred")
        return None

    print(f"  Joined-to-pred: {len(bets):,} bets")

    # Coherence check
    coh = coherence(bets)
    print(f"  COHERENCE: blind-over {coh['over']['roi_pct']:+.2f}% + "
          f"blind-under {coh['under']['roi_pct']:+.2f}% = {coh['sum']:+.2f}%  "
          f"({'OK' if coh['coherent'] else 'CORRUPT'})")
    if not coh["coherent"]:
        print("  SKIP — incoherent odds (sum >= 0), refusing to grade")
        return None

    # Rolling cut
    eval_start = min(b["gdate"] for b in bets)
    print(f"  Eval window: {eval_start.date()} -> {max(b['gdate'] for b in bets).date()}")

    # Group bets by stat
    bets_by_stat: Dict[str, List[dict]] = {}
    for b in bets:
        bets_by_stat.setdefault(b["stat"], []).append(b)

    # Report AST raw (no calibration)
    ast_bets = bets_by_stat.get("ast", [])
    if ast_bets:
        ast_r = roi(ast_bets, predictor="pred")
        print(f"\n  AST (always raw, never calibrated): "
              f"n={ast_r['n']} roi={ast_r['roi_pct']:+.2f}%  [guard-rail]")

    results: Dict[str, Dict[float, Dict]] = {}

    for stat in CANDIDATE_STATS:
        sb = bets_by_stat.get(stat, [])
        n_stat = len(sb)
        print(f"\n  --- {stat.upper()} (n={n_stat}) ---")

        if n_stat < 1:
            print(f"    SKIP — no bets for this stat")
            continue

        # Train rolling-cut calibrator
        booster = _train_calibrator(stat, eval_start)

        stat_rois: Dict[float, Dict] = {}
        for a in CANDIDATE_BLENDS:
            r = _blend_roi(sb, booster, a)
            stat_rois[a] = r
            delta = r["roi_pct"] - stat_rois[0.0]["roi_pct"] if a > 0 else 0.0
            delta_str = f" (delta {delta:+.2f}pp)" if a > 0 else ""
            print(f"    a={a:.1f}: n={r['n']:4d}  win={r['win_pct']:5.1f}%  "
                  f"roi={r['roi_pct']:+7.2f}%{delta_str}")

        results[stat] = stat_rois

    return {
        "name": name,
        "n_total": len(bets),
        "eval_start": eval_start,
        "bets_by_stat": {s: len(v) for s, v in bets_by_stat.items()},
        "results": results,
    }


# ---------------------------------------------------------------------------
# Acceptance rule
# ---------------------------------------------------------------------------

def apply_acceptance_rule(corpus_results: List[Dict]) -> Dict:
    """Apply >=2-corpus acceptance rule per stat.

    A stat gets blend weight a* if:
    - calibrated ROI (at a*) > raw ROI (a=0) on >=2 independent corpora
    - each counted corpus must have n>=MIN_CORPUS_N for that stat
    - a* = smallest in {0.5, 1.0} satisfying the >=2 gate
    - AST is always hard-excluded (never in enabled)

    Returns dict: {stat: {"a_star": float, "verdict": str, "evidence": ...}}
    """
    outcomes: Dict[str, Dict] = {}

    for stat in CANDIDATE_STATS:
        raw_better_counts: Dict[float, int] = {0.5: 0, 1.0: 0}
        cal_better_counts: Dict[float, int] = {0.5: 0, 1.0: 0}
        evidence: List[str] = []

        for cr in corpus_results:
            if cr is None:
                continue
            res = cr["results"].get(stat)
            if res is None:
                continue
            n = cr["bets_by_stat"].get(stat, 0)
            if n < MIN_CORPUS_N:
                evidence.append(f"  {cr['name']}: n={n} < {MIN_CORPUS_N} (thin, not counted)")
                continue

            raw_roi = res.get(0.0, {}).get("roi_pct", float("nan"))
            for a in (0.5, 1.0):
                a_roi = res.get(a, {}).get("roi_pct", float("nan"))
                if not (np.isnan(raw_roi) or np.isnan(a_roi)):
                    if a_roi > raw_roi:
                        cal_better_counts[a] += 1
                    else:
                        raw_better_counts[a] += 1
                    evidence.append(
                        f"  {cr['name']}: raw={raw_roi:+.2f}% a={a}={a_roi:+.2f}% "
                        f"delta={a_roi-raw_roi:+.2f}pp "
                        f"({'CAL wins' if a_roi > raw_roi else 'RAW wins'})"
                    )

        # Pick smallest a* that beats raw on >=2 corpora
        a_star = 0.0
        verdict = "RAW (calibration not robust — stays disabled)"
        for a in (0.5, 1.0):
            if cal_better_counts[a] >= 2:
                a_star = a
                verdict = f"CALIBRATE with a={a} (cal beats raw on {cal_better_counts[a]} corpora)"
                break

        outcomes[stat] = {
            "a_star": a_star,
            "verdict": verdict,
            "cal_better_counts": dict(cal_better_counts),
            "raw_better_counts": dict(raw_better_counts),
            "evidence": evidence,
        }

    return outcomes


# ---------------------------------------------------------------------------
# Print summary table
# ---------------------------------------------------------------------------

def print_summary_table(corpus_results: List[Dict], acceptance: Dict) -> None:
    """Print per-corpus per-stat ROI table and the final acceptance verdict."""

    print("\n\n" + "="*80)
    print("SUMMARY TABLE: Per-corpus per-stat calibrated vs raw ROI")
    print("="*80)

    graded_corpora = [cr for cr in corpus_results if cr is not None]

    # Header
    header = f"{'CORPUS':<42} {'STAT':<6} {'RAW':>8} {'a=0.5':>8} {'a=1.0':>8} {'DELTA@a*':>10}"
    print(header)
    print("-" * len(header))

    for cr in graded_corpora:
        for stat in CANDIDATE_STATS + ["ast"]:
            if stat == "ast":
                continue  # AST excluded from calibration table (printed as guard-rail inline)
            res = cr["results"].get(stat)
            if res is None:
                continue
            n = cr["bets_by_stat"].get(stat, 0)
            thin_flag = " (*thin)" if n < MIN_CORPUS_N else ""
            raw = res.get(0.0, {}).get("roi_pct", float("nan"))
            a05 = res.get(0.5, {}).get("roi_pct", float("nan"))
            a10 = res.get(1.0, {}).get("roi_pct", float("nan"))
            a_star = acceptance.get(stat, {}).get("a_star", 0.0)
            a_star_val = res.get(a_star, {}).get("roi_pct", raw) if a_star > 0 else raw
            delta = (a_star_val - raw) if a_star > 0 else 0.0
            print(f"{cr['name']:<42} {stat:<6} {raw:>+8.2f}% {a05:>+8.2f}% {a10:>+8.2f}% "
                  f"{delta:>+9.2f}pp  n={n}{thin_flag}")
        print()

    print("\n" + "="*80)
    print("ACCEPTANCE RULE (>=2 independent corpora where cal > raw, n>=30 per stat)")
    print("="*80)

    for stat in CANDIDATE_STATS:
        acc = acceptance[stat]
        print(f"\n{stat.upper()}:")
        for ev in acc["evidence"]:
            print(ev)
        print(f"  -> VERDICT: {acc['verdict']}")

    print("\nAST: hard-excluded (always raw; never in enabled set regardless of result)")

    # Build recommended config
    rec_enabled = [s for s in CANDIDATE_STATS if acceptance[s]["a_star"] > 0]
    rec_blend = {s: acceptance[s]["a_star"] for s in rec_enabled}

    shipped_enabled = ["pts", "reb", "fg3m"]
    shipped_blend = {"pts": 1.0, "reb": 0.5, "fg3m": 0.5}

    print("\n" + "="*80)
    print("RECOMMENDED enabled/blend vs SHIPPED")
    print("="*80)
    print(f"  SHIPPED  enabled={shipped_enabled}  blend={shipped_blend}")
    print(f"  RECOMMENDED enabled={rec_enabled}  blend={rec_blend}")

    changed = (set(rec_enabled) != set(shipped_enabled) or
               any(rec_blend.get(s, 0) != shipped_blend.get(s, 0) for s in CANDIDATE_STATS))
    if changed:
        removed = [s for s in shipped_enabled if s not in rec_enabled]
        added = [s for s in rec_enabled if s not in shipped_enabled]
        if removed:
            print(f"  CHANGE: REMOVE {removed} from enabled (calibration not robust on >=2 corpora)")
        if added:
            print(f"  CHANGE: ADD {added} to enabled")
        for s in set(rec_enabled) & set(shipped_enabled):
            if rec_blend.get(s) != shipped_blend.get(s):
                print(f"  CHANGE: {s} blend {shipped_blend[s]} -> {rec_blend[s]}")
    else:
        print("  NO CHANGE — shipped config matches recommendation")

    print("\nINTEGRATION NOTE:")
    print("  pregame_calibration.py reads enabled/blend from data/models/pregame_cal/meta.json.")
    print("  The serving code needs no change; only meta.json + train_pregame_calibrators.py BLEND")
    print("  need updating when the above verdict justifies a change.")
    print("  CV_PREGAME_CAL gate unchanged (default OFF, byte-identical when off).")

    return rec_enabled, rec_blend


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(corpora: Optional[List[str]] = None) -> int:
    if corpora is None:
        corpora = sys.argv[1:] or DEFAULT_CORPORA

    print("="*70)
    print("EX-7: Multi-corpus leak-free pregame calibration validation")
    print("="*70)
    print(f"\nCORPORA TO GRADE: {corpora}")
    print(f"EXCLUDED (explicitly):")
    print("  playoffs_2025_26_oddsapi.csv — dates 2026-04-20..05-25 are BEYOND calframe")
    print("    max (2026-04-12); no leak-free pred substrate exists. Cannot grade.")
    print("  extended_oos_canonical.csv  — same-window key mirror of benashkar (identical")
    print("    (pid, date, stat) join set post-calframe join). Not an independent corpus.")
    print(f"\nCANDIDATE STATS: {CANDIDATE_STATS}  (AST always raw, hard-excluded from blending)")
    print(f"ACCEPTANCE RULE: cal > raw on >=2 corpora with n>={MIN_CORPUS_N} per stat")

    corpus_results: List[Optional[Dict]] = []
    for name in corpora:
        result = grade_corpus(name)
        corpus_results.append(result)

    acceptance = apply_acceptance_rule(corpus_results)
    rec = print_summary_table(corpus_results, acceptance)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
