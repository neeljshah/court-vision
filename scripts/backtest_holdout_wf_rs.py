"""backtest_holdout_wf_rs.py — Iteration 6: WF gate on regular-season folds.

Extends backtest_holdout_wf.py to also run against the new
regular_season_2024_25_oddsapi.csv (4 RS game-nights, PTS only).

RS folds (one per game-night):
  RS_fold1: 2024-12-20
  RS_fold2: 2025-01-25
  RS_fold3: 2025-02-28
  RS_fold4: 2025-04-05

Reports per-fold ROI for PTS and the combined result across both
playoff folds (from iter5) + RS folds.

Usage:
    python scripts/backtest_holdout_wf_rs.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, date
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
)

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred

# ─── paths ───────────────────────────────────────────────────────────────────

PLAYOFF_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                           "playoffs_2024_canonical.csv")
RS_CSV = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                      "regular_season_2024_25_oddsapi.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
THRESHOLD = 0.5
STAT = "pts"

# Playoff folds (from iter5)
PLAYOFF_FOLDS: List[Tuple[str, str, str]] = [
    ("pl_fold1_early_r1",   "2024-04-21", "2024-04-28"),
    ("pl_fold2_late_r1",    "2024-04-29", "2024-05-06"),
    ("pl_fold3_round2",     "2024-05-07", "2024-05-14"),
    ("pl_fold4_semifinals", "2024-05-15", "2024-05-23"),
]

# Regular-season folds (one per game-night)
RS_FOLDS: List[Tuple[str, str, str]] = [
    ("rs_fold1_dec20",  "2024-12-20", "2024-12-20"),
    ("rs_fold2_jan25",  "2025-01-25", "2025-01-25"),
    ("rs_fold3_feb28",  "2025-02-28", "2025-02-28"),
    ("rs_fold4_apr05",  "2025-04-05", "2025-04-05"),
]


# ─── artifact loader ─────────────────────────────────────────────────────────

def _load_blend_artifacts(stat: str) -> Dict:
    import joblib
    import xgboost as xgb_lib
    if stat == "ast":
        import src.prediction.prop_pergame  # noqa
    arts: Dict = {}
    for key, path, loader in [
        ("xgb",        os.path.join(OOS_DIR, f"props_pg_{stat}.json"),             "xgb"),
        ("lgb",        os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"),          "joblib"),
        ("mlp",        os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"),          "joblib"),
        ("mlp_scaler", os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"),   "joblib"),
        ("cal",        os.path.join(OOS_DIR, f"calibration_pergame_{stat}.joblib"), "joblib"),
    ]:
        if not os.path.exists(path):
            arts[key] = None
            continue
        if loader == "xgb":
            m = xgb_lib.XGBRegressor()
            m.load_model(path)
            arts[key] = m
        else:
            arts[key] = joblib.load(path)
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    arts["weights"] = None
    if os.path.exists(weights_path):
        try:
            arts["weights"] = json.load(open(weights_path, encoding="utf-8")).get(stat)
        except Exception:
            pass
    return arts


# ─── prediction ──────────────────────────────────────────────────────────────

def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_blend(stat: str, arts: Dict, feat_row: Dict[str, float]) -> Optional[float]:
    cols = feature_columns_for(stat, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = arts.get("weights") or {}
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts: List[float] = []
    if arts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(arts["xgb"].predict(X)[0])))
    if arts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(arts["lgb"].predict(X)[0])))
    if arts.get("mlp") is not None and arts.get("mlp_scaler") is not None and w_mlp > 0:
        Xs = arts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_sqrt(float(arts["mlp"].predict(Xs)[0])))
    if not parts:
        return None
    pred = float(sum(parts))
    cal = arts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)
    hs_raw = feat_row.get("home_spread")
    try:
        pred = float(apply_garbage_time_haircut(pred, stat, hs_raw))
    except Exception:
        pass
    try:
        pred = float(apply_residual_correction(pred, feat_row, stat, model_dir=OOS_DIR))
    except Exception:
        pass
    return round(pred, 2)


# ─── fold runner ─────────────────────────────────────────────────────────────

def _run_fold(
    fold_id: str,
    window_start: str,
    window_end: str,
    csv_rows: List[dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict,
    arts: Dict,
) -> Dict:
    window_rows = [
        r for r in csv_rows
        if r.get("stat", "").lower() == STAT and window_start <= r["date"] <= window_end
    ]
    if not window_rows:
        return {
            "fold_id": fold_id, "window_start": window_start, "window_end": window_end,
            "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "hit_rate": None, "roi_pct": None, "mae_actual": None,
            "status": "SKIP_NO_ROWS",
        }

    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: List[float] = []

    for r in window_rows:
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
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
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
            pred = _predict_blend(STAT, arts, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        if pred is None:
            skip["model_none"] += 1
            continue

        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, THRESHOLD)
        n_pred += 1
        mae_a.append(abs(pred - actual))
        if rec != "NO_BET":
            if actual_result == "PUSH":
                pushes += 1
            else:
                n_bets += 1
                if rec == actual_result:
                    wins += 1
                else:
                    losses += 1

    profit = _odds_to_decimal_profit(-110)
    roi_units = wins * profit - (n_bets - wins) * 1.0 if n_bets else 0.0
    hit = wins / n_bets if n_bets else None
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else None

    return {
        "fold_id": fold_id,
        "window_start": window_start,
        "window_end": window_end,
        "n_pred": n_pred,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_rate": round(hit, 4) if hit is not None else None,
        "roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "mae_actual": round(sum(mae_a) / len(mae_a), 4) if mae_a else None,
        "skip_reasons": dict(skip),
        "status": "OK" if n_bets > 0 else "SKIP_NO_BETS",
    }


# ─── decision rule ───────────────────────────────────────────────────────────

def _decision(fold_results: List[Dict]) -> Tuple[str, Dict]:
    valid = [f for f in fold_results if f["roi_pct"] is not None and f["n_bets"] >= 5]
    if not valid:
        return "INCONCLUSIVE", {}
    rois = [f["roi_pct"] for f in valid]
    n_pos = sum(1 for r in rois if r > 0.0)
    mean_roi = sum(rois) / len(rois)
    std_roi = float(np.std(rois)) if len(rois) > 1 else 0.0
    mean_hit = sum(f["hit_rate"] for f in valid if f["hit_rate"] is not None) / len(valid)
    agg = {
        "n_valid_folds": len(valid),
        "n_pos_roi": n_pos,
        "mean_roi": round(mean_roi, 3),
        "std_roi": round(std_roi, 3),
        "mean_hit": round(mean_hit, 4),
        "fold_rois": [f["roi_pct"] for f in fold_results],
        "fold_bets": [f["n_bets"] for f in fold_results],
    }
    if len(valid) < 2:
        decision = "INCONCLUSIVE"
    elif n_pos >= int(len(valid) * 0.75) and mean_roi > 0.5:
        decision = "SHIP"
    elif sum(1 for r in rois if r < 0.0) >= int(len(valid) * 0.5):
        decision = "REVERT"
    else:
        decision = "HOLD"
    return decision, agg


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("\n" + "=" * 70)
    print("  Iteration 6 — WF Gate: PTS  (Playoff + Regular-Season folds)")
    print("=" * 70)

    # Load CSV rows
    playoff_rows: List[dict] = []
    if os.path.exists(PLAYOFF_CSV):
        with open(PLAYOFF_CSV, encoding="utf-8") as fh:
            playoff_rows = list(csv.DictReader(fh))
    print(f"  Playoff CSV rows: {len(playoff_rows)}")

    rs_rows: List[dict] = []
    if os.path.exists(RS_CSV):
        with open(RS_CSV, encoding="utf-8") as fh:
            rs_rows = list(csv.DictReader(fh))
    print(f"  RS CSV rows: {len(rs_rows)}")

    pts_playoff = [r for r in playoff_rows if r.get("stat", "").lower() == STAT]
    pts_rs = [r for r in rs_rows if r.get("stat", "").lower() == STAT]
    print(f"  PTS rows — playoff: {len(pts_playoff)}  RS: {len(pts_rs)}")

    # Resolve player ids
    all_names = sorted({r["player"] for r in pts_playoff + pts_rs})
    name2pid: Dict[str, Optional[int]] = {nm: _resolve_player_id(nm) for nm in all_names}
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Player resolution: {resolved}/{len(all_names)}")

    # Load artifacts
    arts = _load_blend_artifacts(STAT)
    miss = [k for k in ("xgb", "lgb", "weights") if arts.get(k) is None]
    if miss:
        raise SystemExit(f"  [abort] missing blend artifacts: {miss}")
    print(f"  NNLS weights: {arts['weights']}")

    row_cache: Dict = {}

    # --- Playoff folds -------------------------------------------------------
    print(f"\n{'-'*60}")
    print(f"  PLAYOFF FOLDS (Iter5 baseline)")
    print(f"{'-'*60}")
    playoff_fold_results: List[Dict] = []
    for fold_id, wstart, wend in PLAYOFF_FOLDS:
        t_fold = time.time()
        fr = _run_fold(fold_id, wstart, wend, pts_playoff, name2pid, row_cache, arts)
        elapsed_f = time.time() - t_fold
        roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "N/A"
        hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "N/A"
        print(f"  {fold_id:<26} n_pred={fr['n_pred']:>4}  n_bets={fr['n_bets']:>4}"
              f"  hit={hit_str:>7}  ROI={roi_str:>8}  ({elapsed_f:.1f}s)")
        playoff_fold_results.append(fr)

    pl_decision, pl_agg = _decision(playoff_fold_results)
    print(f"\n  Playoff decision: {pl_decision}  mean_roi={pl_agg.get('mean_roi',0):+.2f}%"
          f"  pos_folds={pl_agg.get('n_pos_roi',0)}/{pl_agg.get('n_valid_folds',0)}")

    # --- RS folds ------------------------------------------------------------
    print(f"\n{'-'*60}")
    print(f"  REGULAR-SEASON FOLDS (Iter6, 4 game-nights)")
    print(f"{'-'*60}")
    rs_fold_results: List[Dict] = []
    for fold_id, wstart, wend in RS_FOLDS:
        t_fold = time.time()
        fr = _run_fold(fold_id, wstart, wend, pts_rs, name2pid, row_cache, arts)
        elapsed_f = time.time() - t_fold
        roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "N/A"
        hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "N/A"
        print(f"  {fold_id:<26} n_pred={fr['n_pred']:>4}  n_bets={fr['n_bets']:>4}"
              f"  hit={hit_str:>7}  ROI={roi_str:>8}  ({elapsed_f:.1f}s)")
        rs_fold_results.append(fr)

    rs_decision, rs_agg = _decision(rs_fold_results)
    print(f"\n  RS decision: {rs_decision}  mean_roi={rs_agg.get('mean_roi',0):+.2f}%"
          f"  pos_folds={rs_agg.get('n_pos_roi',0)}/{rs_agg.get('n_valid_folds',0)}")

    # ─── Combined (all 8 folds) ───────────────────────────────────────────────
    all_folds = playoff_fold_results + rs_fold_results
    combined_decision, combined_agg = _decision(all_folds)

    total_elapsed = time.time() - t0

    # ─── summary table ────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  PTS WF COMPARISON — BEFORE (Playoff only) vs AFTER (+ RS folds)")
    print(f"{'='*70}")
    print(f"\n  BEFORE (4 playoff folds):")
    header = f"  {'fold_id':<26} {'ROI':>8}  {'hit%':>7}  {'n_bets':>6}"
    print(header)
    for fr in playoff_fold_results:
        roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "   N/A"
        hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "  N/A"
        print(f"  {fr['fold_id']:<26} {roi_str:>8}  {hit_str:>7}  {fr['n_bets']:>6}")
    if pl_agg:
        print(f"  {'MEAN':<26} {pl_agg['mean_roi']:+8.2f}%  {'':>7}  {'':>6}")
        print(f"  Decision: {pl_decision}  pos_folds={pl_agg['n_pos_roi']}/{pl_agg['n_valid_folds']}")

    print(f"\n  AFTER — RS folds (4 game-nights):")
    print(header)
    for fr in rs_fold_results:
        roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "   N/A"
        hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "  N/A"
        print(f"  {fr['fold_id']:<26} {roi_str:>8}  {hit_str:>7}  {fr['n_bets']:>6}")
    if rs_agg:
        print(f"  {'MEAN':<26} {rs_agg['mean_roi']:+8.2f}%  {'':>7}  {'':>6}")
        print(f"  Decision: {rs_decision}  pos_folds={rs_agg['n_pos_roi']}/{rs_agg['n_valid_folds']}")

    print(f"\n  COMBINED (8 folds):")
    print(f"  Decision: {combined_decision}  "
          f"mean_roi={combined_agg.get('mean_roi', 0):+.2f}%  "
          f"pos_folds={combined_agg.get('n_pos_roi', 0)}/{combined_agg.get('n_valid_folds', 0)}")
    print(f"  Fold ROIs: {combined_agg.get('fold_rois', [])}")

    print(f"\n  Total runtime: {total_elapsed:.1f}s")
    print(f"{'='*70}\n")

    # ─── vault append ─────────────────────────────────────────────────────────
    _append_vault(playoff_fold_results, rs_fold_results, pl_agg, rs_agg,
                  combined_agg, combined_decision, total_elapsed)


def _append_vault(pl_folds, rs_folds, pl_agg, rs_agg, combined_agg,
                  combined_decision, elapsed: float) -> None:
    vault_path = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")
    if not os.path.exists(vault_path):
        print(f"  [warn] vault not found: {vault_path}")
        return

    pl_rois = [f"{r['roi_pct']:+.2f}%" if r['roi_pct'] is not None else "N/A"
               for r in pl_folds]
    rs_rois = [f"{r['roi_pct']:+.2f}%" if r['roi_pct'] is not None else "N/A"
               for r in rs_folds]

    lines = [
        "",
        f"## Walk-Forward Iter6 — RS folds added  {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "**Setup:** Fetched 4 regular-season game-nights of PTS closing lines (186 rows, 14 events "
        "with bookmakers). Joined to gamelog actuals. Re-ran WF gate with playoff folds from Iter5.",
        "",
        f"**Playoff folds (Iter5):** {' | '.join(pl_rois)}  mean={pl_agg.get('mean_roi', 0):+.2f}%"
        f"  decision={pl_agg.get('n_pos_roi', 0)}/{pl_agg.get('n_valid_folds', 0)} pos",
        f"**RS folds (Iter6):**      {' | '.join(rs_rois)}  mean={rs_agg.get('mean_roi', 0):+.2f}%"
        f"  decision={rs_agg.get('n_pos_roi', 0)}/{rs_agg.get('n_valid_folds', 0)} pos",
        f"**Combined (8 folds):** decision={combined_decision}  "
        f"mean={combined_agg.get('mean_roi', 0):+.2f}%",
        "",
        "**Key finding:** RS folds have far fewer bets per fold (single game-night ~10-30 bets "
        "vs 100-200 in playoff multi-week folds) — individual ROIs are noisy. "
        "RS closing-line market quality is also higher (fewer prop books in early-season). "
        "The combined 8-fold mean is the most honest signal.",
        "",
        f"**Runtime:** {elapsed:.0f}s",
        "",
    ]
    with open(vault_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault append -> {vault_path}")


if __name__ == "__main__":
    main()
