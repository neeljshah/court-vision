"""ablate_pts_features.py - Iter-6d: feature-group ablation for PTS ROI collapse.

Mirrors ablate_ast_features.py but for PTS (sqrt_huber_blend path).
Runs across BOTH slices:
  - data/external/historical_lines/playoffs_2024_canonical.csv
  - data/external/historical_lines/regular_season_2024_25_oddsapi.csv

For each candidate feature group added in Iters 2-3, zeros those columns in
the prediction input and re-runs the same closing-line ROI computation.
No retraining — pure prediction-path ablation on frozen OOS artifacts.

Usage:
    python scripts/ablate_pts_features.py
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
    def apply_residual_correction(pred, row, stat, model_dir=None):  # type: ignore[misc]
        return pred

STAT = "pts"
PLAYOFF_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                           "playoffs_2024_canonical.csv")
RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2024_25_oddsapi.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Models", "PTS Ablation 2026-05-27.md")
THRESHOLD = 0.5

# bbref keys are prefixed when wired as features
_BBREF_EXTRA_COLS: Tuple[str, ...] = tuple(f"bbref_{k}" for k in _BBREF_EXTRA_KEYS)

# Feature groups to ablate — (label, tuple-of-column-names-to-zero)
ABLATION_GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("baseline",    ()),                                   # no zeroing — current ROI
    ("dmatch",      _DMATCH_KEYS),                        # 7 cols: defender matchup
    ("prof",        _PROF_KEYS),                          # 12 cols: static player profile
    ("bbref_extra", _BBREF_EXTRA_COLS),                   # 5 cols: orb_pct/drb_pct/trb_pct/bpm/ws
    ("officials",   _OFFICIALS_ROLLING_KEYS),             # 5 cols: ref rolling fouls/fta
    ("foul",        _FOUL_FEATURE_KEYS),                  # 5 cols: pf/36 + trouble
    ("dnp_team",    _DNP_TEAM_KEYS),                      # 4 cols: DNP counts
    ("adv_splits",  _ADV_SPLITS_KEYS),                    # 6 cols: usage/ts expanding + opp
    # combo blocks
    ("wave3_all",   _OFFICIALS_ROLLING_KEYS + _FOUL_FEATURE_KEYS
                    + _DNP_TEAM_KEYS + _ADV_SPLITS_KEYS), # 20 cols: all Iter-3 groups
    ("wave2b_all",  _DMATCH_KEYS + _PROF_KEYS + _BBREF_EXTRA_COLS),  # 24 cols: Wave-2b
]


def _load_oos_artifacts() -> Dict:
    import joblib
    import xgboost as xgb_lib

    arts: Dict = {}
    xgb_path = os.path.join(OOS_DIR, f"props_pg_{STAT}.json")
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        arts["xgb"] = m
    else:
        arts["xgb"] = None

    for key, fname in [
        ("lgb",        f"props_pg_lgb_{STAT}.pkl"),
        ("mlp",        f"props_pg_mlp_{STAT}.pkl"),
        ("mlp_scaler", f"props_pg_mlp_scaler_{STAT}.pkl"),
        ("cal",        f"calibration_pergame_{STAT}.joblib"),
    ]:
        p = os.path.join(OOS_DIR, fname)
        arts[key] = joblib.load(p) if os.path.exists(p) else None

    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    arts["weights"] = None
    if os.path.exists(weights_path):
        try:
            arts["weights"] = json.load(
                open(weights_path, encoding="utf-8")
            ).get(STAT)
        except Exception:
            pass
    return arts


def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_blend(
    artifacts: Dict,
    feat_row: Dict[str, float],
    zero_cols: Tuple[str, ...],
) -> Optional[float]:
    """Predict PTS with specified columns zeroed in the feature vector."""
    cols = feature_columns_for(STAT, OOS_DIR)
    row_copy = {
        k: (0.0 if k in zero_cols else float(feat_row.get(k, 0.0) or 0.0))
        for k in cols
    }
    X = np.array([[row_copy[c] for c in cols]], dtype=float)

    weights = artifacts.get("weights") or {}
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))

    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))

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


def _run_one_slice(
    artifacts: Dict,
    csv_rows: List[Dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict,
    zero_cols: Tuple[str, ...],
) -> Dict:
    """Run ROI computation for one slice (playoffs or RS) with given zeroed columns."""
    skip: Dict[str, int] = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0

    for r in csv_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except Exception:
            skip["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = r["venue"] == "home"
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
    hit = wins / n_bets if n_bets else 0.0
    roi_pct = roi_units / n_bets * 100.0 if n_bets else 0.0

    return {
        "n_pred": n_pred, "n_bets": n_bets, "wins": wins,
        "losses": losses, "pushes": pushes,
        "hit_rate": hit, "roi_pct": roi_pct,
        "skip": dict(skip),
    }


def _load_csv_pts_rows(path: str) -> List[Dict]:
    rows: List[Dict] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() == STAT:
                rows.append(r)
    return rows


def _combined_roi(pl: Dict, rs: Dict) -> Tuple[float, float, int]:
    """Return (combined_roi_pct, combined_hit, combined_n_bets) across both slices."""
    total_bets = pl["n_bets"] + rs["n_bets"]
    if total_bets == 0:
        return 0.0, 0.0, 0
    total_wins = pl["wins"] + rs["wins"]
    profit_per_win = _odds_to_decimal_profit(-110)
    roi_units = total_wins * profit_per_win - (total_bets - total_wins) * 1.0
    roi_pct = roi_units / total_bets * 100.0
    hit = total_wins / total_bets
    return roi_pct, hit, total_bets


def main() -> None:
    print("\n  Iter-6d: PTS feature ablation (playoffs + RS combined)")
    artifacts = _load_oos_artifacts()
    miss = [k for k in ("xgb", "lgb", "weights") if artifacts.get(k) is None]
    if miss:
        raise SystemExit(f"  [abort] missing OOS artifacts: {miss}")
    print(f"  NNLS weights: {artifacts['weights']}")

    pl_rows = _load_csv_pts_rows(PLAYOFF_CSV)
    rs_rows = _load_csv_pts_rows(RS_CSV)
    print(f"  PTS rows: playoffs={len(pl_rows)}  RS={len(rs_rows)}")

    all_players = {r["player"] for r in pl_rows} | {r["player"] for r in rs_rows}
    name2pid: Dict[str, Optional[int]] = {
        nm: _resolve_player_id(nm) for nm in sorted(all_players)
    }
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  player resolution: {n_resolved}/{len(name2pid)}")

    # Shared row caches — built lazily, reused across ablations for speed
    pl_cache: Dict = {}
    rs_cache: Dict = {}

    results: List[Dict] = []
    t_total = time.time()

    for label, zero_cols in ABLATION_GROUPS:
        t0 = time.time()
        pl_res = _run_one_slice(artifacts, pl_rows, name2pid, pl_cache, zero_cols)
        rs_res = _run_one_slice(artifacts, rs_rows, name2pid, rs_cache, zero_cols)
        comb_roi, comb_hit, comb_bets = _combined_roi(pl_res, rs_res)
        elapsed = time.time() - t0
        print(
            f"  [{label:>15}]  "
            f"PL ROI={pl_res['roi_pct']:+7.2f}%  "
            f"RS ROI={rs_res['roi_pct']:+7.2f}%  "
            f"COMB ROI={comb_roi:+7.2f}%  "
            f"hit={comb_hit*100:5.2f}%  "
            f"zeroed={len(zero_cols)}  ({elapsed:.1f}s)"
        )
        results.append({
            "label": label,
            "n_zeroed": len(zero_cols),
            "pl": pl_res,
            "rs": rs_res,
            "comb_roi": comb_roi,
            "comb_hit": comb_hit,
            "comb_bets": comb_bets,
        })

    print(f"\n  Total time: {time.time()-t_total:.1f}s")

    baseline = next(r for r in results if r["label"] == "baseline")
    ablations = [r for r in results if r["label"] != "baseline"]
    ablations_sorted = sorted(ablations, key=lambda x: x["comb_roi"], reverse=True)

    print("\n  === Ablation ranking — combined ROI (best first) ===")
    print(f"  {'group':>15}  {'PL_ROI':>8}  {'RS_ROI':>8}  {'COMB_ROI':>9}  "
          f"{'delta':>8}  {'hit%':>7}  {'bets':>6}")
    b = baseline
    print(f"  {'baseline':>15}  {b['pl']['roi_pct']:>8.2f}  "
          f"{b['rs']['roi_pct']:>8.2f}  {b['comb_roi']:>9.2f}  "
          f"{'---':>8}  {b['comb_hit']*100:>7.2f}  {b['comb_bets']:>6}")
    for r in ablations_sorted:
        delta = r["comb_roi"] - baseline["comb_roi"]
        print(f"  {r['label']:>15}  {r['pl']['roi_pct']:>8.2f}  "
              f"{r['rs']['roi_pct']:>8.2f}  {r['comb_roi']:>9.2f}  "
              f"{delta:>+8.2f}  {r['comb_hit']*100:>7.2f}  {r['comb_bets']:>6}")

    _save_report(baseline, ablations_sorted, artifacts["weights"])
    print(f"\n  Report saved: {REPORT_PATH}")


def _save_report(
    baseline: Dict,
    ablations_sorted: List[Dict],
    weights: Optional[Dict],
) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    b = baseline
    lines: List[str] = []
    lines.append("# PTS Feature Ablation — Iter-6d (2026-05-27)\n")
    lines.append(
        "Ablation of Iter 2-3 feature groups to diagnose PTS ROI collapse "
        "(-4.56% mean ROI across 8 WF folds, 2/8 positive).\n"
    )
    lines.append(
        "Method: zero each feature group in the prediction input; "
        "re-run ROI computation WITHOUT retraining. "
        "Uses frozen OOS artifacts from `data/models/oos_pre_playoffs/`.\n"
    )
    lines.append(f"NNLS weights: `{json.dumps(weights)}`\n")
    lines.append("## Results\n")
    lines.append(
        "| group | n_zeroed | PTS_ROI_playoffs | PTS_ROI_RS | "
        "PTS_ROI_combined | PTS_hit_combined | n_bets_combined | delta_comb_ROI |"
    )
    lines.append("|-------|----------|-----------------|------------|"
                 "-----------------|-----------------|-----------------|----------------|")

    def _fmt_row(r: Dict, delta: Optional[float] = None) -> str:
        d_str = f"{delta:+.2f}pp" if delta is not None else "---"
        return (
            f"| {r['label']} | {r['n_zeroed']} "
            f"| {r['pl']['roi_pct']:+.2f}% "
            f"| {r['rs']['roi_pct']:+.2f}% "
            f"| {r['comb_roi']:+.2f}% "
            f"| {r['comb_hit']*100:.2f}% "
            f"| {r['comb_bets']} "
            f"| {d_str} |"
        )

    lines.append(_fmt_row(b))
    for r in ablations_sorted:
        delta = r["comb_roi"] - b["comb_roi"]
        lines.append(_fmt_row(r, delta))

    lines.append("")
    lines.append("## Interpretation\n")
    best = ablations_sorted[0]
    delta_best = best["comb_roi"] - b["comb_roi"]
    lines.append(f"- Best ablation: **{best['label']}** ({delta_best:+.2f}pp combined ROI improvement)")
    if len(ablations_sorted) >= 2:
        second = ablations_sorted[1]
        delta_2nd = second["comb_roi"] - b["comb_roi"]
        lines.append(f"- Second best: **{second['label']}** ({delta_2nd:+.2f}pp)")
    lines.append("")
    lines.append("## Recommendation\n")
    if delta_best > 2.0:
        lines.append(
            f"Drop **{best['label']}** columns from `feature_columns()` for PTS "
            "specifically (per-stat exclusion, no retrain of other stats needed). "
            "Retrain PTS without these columns to bake in the signal removal."
        )
    elif delta_best > 0.5:
        lines.append(
            f"Weak signal: **{best['label']}** improves combined ROI by only "
            f"{delta_best:+.2f}pp. Consider dropping and retraining PTS to confirm "
            "improvement holds on walk-forward folds."
        )
    else:
        lines.append(
            "No single group dominates. Consider reverting ALL Iter 2-3 features "
            "for PTS (use the pre-Wave-2b 85-col baseline) and retraining."
        )
    lines.append("")
    lines.append("## Feature groups tested\n")
    group_desc = [
        ("dmatch",     "7 cols: defender matchup (dmatch_fg_pct_l10 … dmatch_3p_pct_l10)"),
        ("prof",       "12 cols: static player profile (prof_height_in … prof_season_exp)"),
        ("bbref_extra","5 cols: orb_pct, drb_pct, trb_pct, bpm, ws (prefixed bbref_*)"),
        ("officials",  "5 cols: ref_l5_fouls, ref_l5_fta, ref_fouls_z, ref_fta_z, ref_home_advantage"),
        ("foul",       "5 cols: foul_pf36_l5, foul_pf36_l10, foul_trouble_l10, foul_last_pf, foul_min_l5"),
        ("dnp_team",   "4 cols: dnp_in_game, dnp_l5_avg, dnp_l10_avg, dnp_prior_game"),
        ("adv_splits", "6 cols: adv_usage_std, adv_ts_std, adv_efg_std, adv_usage_vs_opp_l3, adv_ts_vs_opp_l3, adv_usage_z"),
        ("wave3_all",  "20 cols: all Iter-3 groups combined (officials+foul+dnp_team+adv_splits)"),
        ("wave2b_all", "24 cols: all Wave-2b groups combined (dmatch+prof+bbref_extra)"),
    ]
    for lbl, desc in group_desc:
        lines.append(f"- **{lbl}**: {desc}")
    lines.append("")
    lines.append("## Data sources\n")
    lines.append(f"- Playoffs: `data/external/historical_lines/playoffs_2024_canonical.csv`")
    lines.append(f"- Regular season: `data/external/historical_lines/regular_season_2024_25_oddsapi.csv`")
    lines.append(f"- OOS artifacts: `data/models/oos_pre_playoffs/`")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
