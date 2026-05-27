"""ablate_ast_features.py - Iter-6b: feature-group ablation for AST ROI collapse.

For each candidate feature group added in Iters 1-3, zero those columns in the
prediction input and re-run the same closing-line ROI computation as
backtest_ast_oos.py. The group whose removal most IMPROVES ROI is the culprit.

No retraining — pure prediction-path ablation using the frozen OOS artifacts.

Usage:
    python scripts/ablate_ast_features.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import (  # noqa: E402
    feature_columns_for,
    apply_garbage_time_haircut,
    _DMATCH_KEYS,
    _PROF_KEYS,
    _BBREF_EXTRA_KEYS,
    _OFFICIALS_ROLLING_KEYS,
    _FOUL_FEATURE_KEYS,
    _DNP_TEAM_KEYS,
    _ADV_SPLITS_KEYS,
)

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred

STAT = "ast"
CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Models", "AST Ablation 2026-05-27.md")
THRESHOLD = 0.5

# Feature groups to ablate — each entry: (label, tuple-of-column-names)
# bbref_extra: use prefixed names
_BBREF_EXTRA_COLS = tuple(f"bbref_{k}" for k in _BBREF_EXTRA_KEYS)

ABLATION_GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("baseline",       ()),                   # no zeroing — establishes current ROI
    ("dmatch",         _DMATCH_KEYS),         # 7 cols: defender matchup
    ("prof",           _PROF_KEYS),           # 12 cols: player profile static
    ("bbref_extra",    _BBREF_EXTRA_COLS),    # 5 cols: orb_pct/drb_pct/trb_pct/bpm/ws
    ("officials",      _OFFICIALS_ROLLING_KEYS),  # 5 cols: ref rolling fouls/fta
    ("foul",           _FOUL_FEATURE_KEYS),   # 5 cols: pf/36 + trouble
    ("dnp_team",       _DNP_TEAM_KEYS),       # 4 cols: DNP counts
    ("adv_splits",     _ADV_SPLITS_KEYS),     # 6 cols: usage/ts expanding + opp
    # combo: wave-3 block (all 4 iter-3 groups)
    ("wave3_all",      _OFFICIALS_ROLLING_KEYS + _FOUL_FEATURE_KEYS
                       + _DNP_TEAM_KEYS + _ADV_SPLITS_KEYS),
    # combo: wave-2b block (dmatch + prof + bbref_extra)
    ("wave2b_all",     _DMATCH_KEYS + _PROF_KEYS + _BBREF_EXTRA_COLS),
]


def _load_oos_artifacts() -> dict:
    import joblib
    import xgboost as xgb_lib
    import src.prediction.prop_pergame  # noqa: F401 — ensures _MultitaskMLPProxy unpickles

    arts: dict = {}
    xgb_path = os.path.join(OOS_DIR, f"props_pg_{STAT}.json")
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        arts["xgb"] = m
    else:
        arts["xgb"] = None

    for key, fname in [("lgb", f"props_pg_lgb_{STAT}.pkl"),
                       ("mlp", f"props_pg_mlp_{STAT}.pkl"),
                       ("mlp_scaler", f"props_pg_mlp_scaler_{STAT}.pkl"),
                       ("cal", f"calibration_pergame_{STAT}.joblib")]:
        p = os.path.join(OOS_DIR, fname)
        arts[key] = joblib.load(p) if os.path.exists(p) else None

    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    arts["weights"] = None
    if os.path.exists(weights_path):
        try:
            w_all = json.load(open(weights_path, encoding="utf-8"))
            arts["weights"] = w_all.get(STAT)
        except Exception:
            pass

    return arts


def _inv_log1p(v: float) -> float:
    return max(0.0, float(np.expm1(v)))


def _predict_blend(artifacts: dict, feat_row: Dict[str, float],
                   zero_cols: Tuple[str, ...]) -> Optional[float]:
    """Predict AST with specified columns zeroed in the feature vector."""
    cols = feature_columns_for(STAT, OOS_DIR)
    row_copy = {k: (0.0 if k in zero_cols else float(feat_row.get(k, 0.0) or 0.0))
                for k in cols}
    X = np.array([[row_copy[c] for c in cols]], dtype=float)

    weights = artifacts["weights"]
    if not weights:
        return None

    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))

    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_log1p(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_log1p(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_log1p(float(artifacts["mlp"].predict(Xs)[0])))

    if not parts:
        return None
    pred = float(sum(parts))

    cal = artifacts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)

    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, STAT, hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, STAT, model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


def _run_one_ablation(
    artifacts: dict,
    all_rows: List[dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict[Tuple, Optional[Dict[str, float]]],
    zero_cols: Tuple[str, ...],
) -> dict:
    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0

    for r in all_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key: Tuple = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue

        try:
            pred = _predict_blend(artifacts, feat, zero_cols)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skip["model_missing"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)

        n_pred += 1
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    profit_per_win = _odds_to_decimal_profit(-110)
    roi_units = wins * profit_per_win - (n_bets - wins) * 1.0
    hit = (wins / n_bets) if n_bets else 0.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else 0.0

    return {
        "n_pred": n_pred, "n_bets": n_bets, "wins": wins, "losses": losses,
        "pushes": pushes, "hit_rate": hit, "roi_pct": roi_pct,
        "skip": dict(skip),
    }


def main() -> None:
    print("\n  Iter-6b: AST feature ablation")
    artifacts = _load_oos_artifacts()
    miss = [k for k in ("xgb", "lgb", "weights") if artifacts.get(k) is None]
    if miss:
        raise SystemExit(f"  [abort] missing OOS artifacts: {miss}")
    print(f"  NNLS weights: {artifacts['weights']}")

    all_rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == STAT:
                all_rows.append(r)
    print(f"  CSV AST rows: {len(all_rows)}")

    name2pid: Dict[str, Optional[int]] = {
        nm: _resolve_player_id(nm)
        for nm in sorted({r["player"] for r in all_rows})
    }
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  player resolution: {n_resolved}/{len(name2pid)}")

    # Build feat cache once (baseline pass) — reused for all ablations
    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}

    results: List[dict] = []
    t_total = time.time()

    for label, zero_cols in ABLATION_GROUPS:
        t0 = time.time()
        r = _run_one_ablation(artifacts, all_rows, name2pid, row_cache, zero_cols)
        elapsed = time.time() - t0
        n_zeroed = len(zero_cols)
        print(f"  [{label:>15}] n_pred={r['n_pred']:4d}  n_bets={r['n_bets']:4d}  "
              f"hit={r['hit_rate']*100:5.2f}%  ROI={r['roi_pct']:+7.2f}%  "
              f"zeroed={n_zeroed}  ({elapsed:.1f}s)")
        results.append({"label": label, "n_zeroed": n_zeroed, **r})

    print(f"\n  Total time: {time.time()-t_total:.1f}s")

    # Sort by ROI descending (best ablation = highest ROI improvement vs baseline)
    baseline = next(r for r in results if r["label"] == "baseline")
    ablations = [r for r in results if r["label"] != "baseline"]
    ablations_sorted = sorted(ablations, key=lambda x: x["roi_pct"], reverse=True)

    print("\n  === Ablation ranking (best ROI first) ===")
    print(f"  {'group':>15}  {'ROI%':>8}  {'delta_ROI':>10}  {'hit%':>7}  {'n_bets':>7}")
    print(f"  {'baseline':>15}  {baseline['roi_pct']:>8.2f}  {'---':>10}  "
          f"{baseline['hit_rate']*100:>7.2f}  {baseline['n_bets']:>7}")
    for r in ablations_sorted:
        delta = r["roi_pct"] - baseline["roi_pct"]
        print(f"  {r['label']:>15}  {r['roi_pct']:>8.2f}  {delta:>+10.2f}  "
              f"{r['hit_rate']*100:>7.2f}  {r['n_bets']:>7}")

    _save_report(baseline, ablations_sorted, results)
    print(f"\n  Report saved: {REPORT_PATH}")


def _save_report(baseline: dict, ablations_sorted: List[dict],
                 all_results: List[dict]) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    lines: List[str] = []
    lines.append("# AST Feature Ablation — Iter-6b (2026-05-27)\n")
    lines.append("Ablation of Iter 1-3 feature groups to diagnose AST ROI collapse "
                 "(-12.01% ROI, 46.09% hit, 831 bets on 2024 playoff closing lines).\n")
    lines.append("Method: zero each feature group in the prediction input; "
                 "re-run ROI computation without retraining.\n")
    lines.append("## Results\n")
    lines.append("| group | n_zeroed | n_bets | hit% | ROI% | delta_ROI |")
    lines.append("|-------|----------|--------|------|------|-----------|")

    def _row(r: dict, delta: Optional[float] = None) -> str:
        d_str = f"{delta:+.2f}pp" if delta is not None else "---"
        return (f"| {r['label']} | {r['n_zeroed']} | {r['n_bets']} "
                f"| {r['hit_rate']*100:.2f}% | {r['roi_pct']:+.2f}% | {d_str} |")

    lines.append(_row(baseline))
    for r in ablations_sorted:
        delta = r["roi_pct"] - baseline["roi_pct"]
        lines.append(_row(r, delta))

    lines.append("")
    lines.append("## Interpretation")
    best = ablations_sorted[0]
    delta_best = best["roi_pct"] - baseline["roi_pct"]
    lines.append(f"- Best ablation: **{best['label']}** ({delta_best:+.2f}pp ROI improvement)")
    if len(ablations_sorted) >= 2:
        second = ablations_sorted[1]
        delta_2nd = second["roi_pct"] - baseline["roi_pct"]
        lines.append(f"- Second best: **{second['label']}** ({delta_2nd:+.2f}pp)")
    lines.append("")
    lines.append("## Recommendation")
    if delta_best > 2.0:
        lines.append(f"Drop **{best['label']}** columns from `feature_columns()` "
                     "for AST specifically (per-stat feature subset in multitask training).")
    else:
        lines.append("No single group dominates — consider reverting all Iter 2-3 "
                     "features for AST (use the 85-col pre-Wave-2b baseline).")
    lines.append("")
    lines.append("## Feature groups tested")
    for label, cols in [
        ("dmatch", "7 cols: defender matchup (dmatch_fg_pct_l10 … dmatch_3p_pct_l10)"),
        ("prof", "12 cols: static player profile (prof_height_in … prof_season_exp)"),
        ("bbref_extra", "5 cols: orb_pct, drb_pct, trb_pct, bpm, ws"),
        ("officials", "5 cols: ref_l5_fouls, ref_l5_fta, ref_fouls_z, ref_fta_z, ref_home_advantage"),
        ("foul", "5 cols: foul_pf36_l5, foul_pf36_l10, foul_trouble_l10, foul_last_pf, foul_min_l5"),
        ("dnp_team", "4 cols: dnp_in_game, dnp_l5_avg, dnp_l10_avg, dnp_prior_game"),
        ("adv_splits", "6 cols: adv_usage_std, adv_ts_std, adv_efg_std, adv_usage_vs_opp_l3, adv_ts_vs_opp_l3, adv_usage_z"),
        ("wave3_all", "20 cols: all Iter-3 groups combined"),
        ("wave2b_all", "24 cols: all Wave-2b groups combined (dmatch+prof+bbref_extra)"),
    ]:
        lines.append(f"- **{label}**: {cols}")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
