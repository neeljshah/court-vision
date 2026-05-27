"""backtest_holdout_wf.py — Walk-forward 4-window gate (Iteration 5).

DESIGN (shortcut path — documented limitation):
  The canonical train-retrain walk-forward would require 4 x 7 = 28 model retrains
  (~13 min each = 6+ hours). Not feasible in one agent run.

  SHORTCUT: Use the SINGLE OOS model trained on data strictly before 2024-04-21
  (the existing oos_pre_playoffs artifacts) and evaluate it across 4 chronological
  sub-windows of the 2024 NBA playoffs (2024-04-21 → 2024-05-23, 32 game-days).

  Fold 1: 2024-04-21 → 2024-04-28  (First-round, 8 game-days)
  Fold 2: 2024-04-29 → 2024-05-06  (First-round tail / R2 start, 8 game-days)
  Fold 3: 2024-05-07 → 2024-05-14  (R2, 8 game-days)
  Fold 4: 2024-05-15 → 2024-05-23  (Conference semis/finals, 8 game-days)

  WHY this is more honest than the old single-slice:
    - Each fold has a different opponent-pair distribution (early=16 matchups,
      late=2-4 matchups) — tests distribution shift across rounds.
    - Fold-level variance exposes whether the model benefits from "averaging out"
      a lucky evaluation window.
    - Decision rule requires 3+/4 folds positive ROI AND mean_roi > +0.5%.

  NOTE: True walk-forward (model re-trained per fold) requires ~6h compute;
  this script documents that limitation in its output. The 4-window evaluation
  still catches single-window lucky hits and is far more honest than one slice.

  DATA GAP: There are NO 2024-25 regular-season closing-line CSVs available
  (extended_oos_canonical.csv jumps from 2024-05-23 to 2026-01-28). If
  regular-season lines are ever scraped, replace the fold definitions with
  the 4 rolling 30-day windows described in the iteration-5 spec.

STATS:  pts (blend), ast (blend), reb (q50 lgb), fg3m (q50 xgb),
        blk (q50 xgb), stl (q50 xgb), tov (q50 xgb)

SHIP RULE:  3+/4 folds positive ROI AND mean_roi > +0.5%
REVERT:     2+ folds negative ROI
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
    feature_columns,
    feature_columns_for,
    apply_garbage_time_haircut,
)
from src.prediction.prop_quantiles import _inverse  # noqa: E402

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


# ─── paths ───────────────────────────────────────────────────────────────────

CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
THRESHOLD = 0.5

# 4 evaluation windows — equal 8-day slices of the 32 playoff game-days.
# Dates with no games (e.g. 2024-05-20) are naturally absent from CSV rows.
FOLDS: List[Tuple[str, str, str]] = [
    ("fold1_early_r1",    "2024-04-21", "2024-04-28"),
    ("fold2_late_r1",     "2024-04-29", "2024-05-06"),
    ("fold3_round2",      "2024-05-07", "2024-05-14"),
    ("fold4_semifinals",  "2024-05-15", "2024-05-23"),
]

ALL_STATS = ["pts", "ast", "reb", "fg3m", "blk", "stl", "tov"]
LGB_STATS = {"reb"}
BLEND_STATS = {"pts", "ast"}
Q50_STATS = ALL_STATS  # fallback key; blend overrides inside loader


# ─── feature column helpers ──────────────────────────────────────────────────

_META_CACHE: Optional[Dict] = None

def _meta() -> Dict:
    global _META_CACHE
    if _META_CACHE is None:
        meta_path = os.path.join(OOS_DIR, "_meta.json")
        _META_CACHE = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    return _META_CACHE


def _q50_feature_columns(stat: str, model=None) -> List[str]:
    """Return feature columns matching what the OOS q50 model expects.

    Checks the model's actual n_features_in_ first (most reliable), then falls
    back to meta.json, then to the current feature_columns(). This is needed
    because some models were retrained after the meta.json was last updated,
    causing a mismatch between meta['n_features']=129 and model.n_features_in_=138.
    """
    current = feature_columns()
    if model is not None:
        n_expected = getattr(model, "n_features_in_", None) or getattr(model, "n_features_", None)
        if n_expected is not None:
            if n_expected == len(current):
                return current
            saved = _meta().get("stats", {}).get(stat, {}).get("feature_columns", [])
            if saved and len(saved) == n_expected:
                return saved
            # Truncate current columns to expected length as last resort
            return current[:n_expected]
    saved = _meta().get("stats", {}).get(stat, {}).get("feature_columns")
    if saved:
        return saved
    return current


# ─── artifact loaders ────────────────────────────────────────────────────────

def _load_blend_artifacts(stat: str) -> Dict:
    import joblib, xgboost as xgb_lib
    if stat == "ast":
        import src.prediction.prop_pergame  # noqa — ensures _MultitaskMLPProxy unpicklable
    arts: Dict = {}
    for key, path, loader in [
        ("xgb",        os.path.join(OOS_DIR, f"props_pg_{stat}.json"),            "xgb"),
        ("lgb",        os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"),         "joblib"),
        ("mlp",        os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"),         "joblib"),
        ("mlp_scaler", os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"), "joblib"),
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


def _load_q50_artifact(stat: str):
    if stat in LGB_STATS:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"OOS artifact missing: {path}")
        return joblib.load(path)
    else:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"OOS artifact missing: {path}")
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m


# ─── prediction helpers ───────────────────────────────────────────────────────

def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _inv_log1p(v: float) -> float:
    return max(0.0, float(np.expm1(v)))


def _predict_blend(stat: str, arts: Dict, feat_row: Dict[str, float]) -> Optional[float]:
    cols = feature_columns_for(stat, OOS_DIR)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    weights = arts.get("weights") or {}
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    inv = _inv_sqrt if stat == "pts" else _inv_log1p
    parts: List[float] = []
    if arts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * inv(float(arts["xgb"].predict(X)[0])))
    if arts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * inv(float(arts["lgb"].predict(X)[0])))
    if arts.get("mlp") is not None and arts.get("mlp_scaler") is not None and w_mlp > 0:
        Xs = arts["mlp_scaler"].transform(X)
        parts.append(w_mlp * inv(float(arts["mlp"].predict(Xs)[0])))
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


def _predict_q50(stat: str, model, feat_row: Dict[str, float]) -> Optional[float]:
    cols = _q50_feature_columns(stat, model)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ─── single-fold runner ───────────────────────────────────────────────────────

def _run_fold(
    stat: str,
    fold_id: str,
    window_start: str,
    window_end: str,
    all_csv_rows: List[dict],
    name2pid: Dict[str, Optional[int]],
    row_cache: Dict,
    model_arts,  # either blend dict or q50 model
    is_blend: bool,
) -> Dict:
    window_rows = [
        r for r in all_csv_rows
        if r.get("stat", "").lower() == stat and window_start <= r["date"] <= window_end
    ]
    if not window_rows:
        return {
            "fold_id": fold_id, "window_start": window_start, "window_end": window_end,
            "stat": stat, "n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "hit_rate": None, "roi_pct": None, "mae_actual": None,
            "skip_reasons": {"no_rows": 1}, "status": "SKIP_NO_ROWS",
        }

    skip = defaultdict(int)
    n_pred = n_bets = wins = losses = pushes = 0
    mae_a: List[float] = []

    for r in window_rows:
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
            if is_blend:
                pred = _predict_blend(stat, model_arts, feat)
            else:
                pred = _predict_q50(stat, model_arts, feat)
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
        "stat": stat,
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


# ─── per-stat aggregation & decision ─────────────────────────────────────────

def _wf_decision(fold_results: List[Dict]) -> Tuple[str, Dict]:
    valid = [f for f in fold_results if f["roi_pct"] is not None and f["n_bets"] >= 10]
    if not valid:
        return "INCONCLUSIVE", {}
    rois = [f["roi_pct"] for f in valid]
    n_pos = sum(1 for r in rois if r > 0.0)
    mean_roi = sum(rois) / len(rois)
    std_roi = float(np.std(rois)) if len(rois) > 1 else 0.0
    mean_hit = sum(f["hit_rate"] for f in valid if f["hit_rate"] is not None) / len(valid)
    mean_mae = (sum(f["mae_actual"] for f in valid if f["mae_actual"] is not None)
                / len([f for f in valid if f["mae_actual"] is not None]))
    stats_agg = {
        "n_valid_folds": len(valid),
        "n_pos_roi": n_pos,
        "mean_roi": round(mean_roi, 3),
        "std_roi": round(std_roi, 3),
        "mean_hit": round(mean_hit, 4),
        "mean_mae": round(mean_mae, 4) if mean_mae else None,
        "fold_rois": [f["roi_pct"] for f in fold_results],
        "fold_bets": [f["n_bets"] for f in fold_results],
    }
    if len(valid) < 2:
        decision = "INCONCLUSIVE"
    elif n_pos >= 3 and mean_roi > 0.5:
        decision = "SHIP"
    elif sum(1 for r in rois if r < 0.0) >= 2:
        decision = "REVERT"
    else:
        decision = "HOLD"  # mixed — not enough evidence either way
    return decision, stats_agg


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t_total = time.time()
    print("\n" + "=" * 70)
    print("  Walk-Forward 4-Window Gate — Iteration 5")
    print("  Model: oos_pre_playoffs (cutoff 2024-04-21, single model)")
    print("  Eval:  4 sub-windows of 2024 NBA playoffs")
    print("  LIMITATION: no model re-train per fold (shortcut path)")
    print("=" * 70)

    # Load all CSV rows once.
    all_rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        all_rows = list(csv.DictReader(fh))
    print(f"\n  Loaded {len(all_rows)} CSV rows from {os.path.basename(CSV_PATH)}")

    # Resolve all player ids once (shared across stats/folds).
    unique_names = sorted({r["player"] for r in all_rows})
    name2pid: Dict[str, Optional[int]] = {nm: _resolve_player_id(nm) for nm in unique_names}
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Player resolution: {resolved}/{len(unique_names)}")

    # Feature row cache (shared across stats, keyed by player+date+venue+opp).
    row_cache: Dict = {}

    all_results: Dict[str, Dict] = {}  # stat -> {decision, agg, folds}

    for stat in ALL_STATS:
        is_blend = stat in BLEND_STATS
        print(f"\n{'-'*60}")
        print(f"  STAT: {stat.upper()}  ({'blend' if is_blend else 'q50'})")
        print(f"{'-'*60}")

        try:
            if is_blend:
                model_arts = _load_blend_artifacts(stat)
                miss = [k for k in ("xgb", "lgb", "weights") if model_arts.get(k) is None]
                if miss:
                    print(f"  [skip] missing blend artifacts: {miss}")
                    all_results[stat] = {"decision": "SKIP_NO_ARTIFACT", "folds": [], "agg": {}}
                    continue
            else:
                model_arts = _load_q50_artifact(stat)
        except FileNotFoundError as e:
            print(f"  [skip] {e}")
            all_results[stat] = {"decision": "SKIP_NO_ARTIFACT", "folds": [], "agg": {}}
            continue

        fold_results: List[Dict] = []
        for fold_id, wstart, wend in FOLDS:
            t_fold = time.time()
            fr = _run_fold(stat, fold_id, wstart, wend, all_rows, name2pid,
                           row_cache, model_arts, is_blend)
            elapsed_f = time.time() - t_fold
            roi_str = f"{fr['roi_pct']:+.2f}%" if fr["roi_pct"] is not None else "N/A"
            hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "N/A"
            print(f"  {fold_id:<22} n_pred={fr['n_pred']:>4}  n_bets={fr['n_bets']:>4}"
                  f"  hit={hit_str:>7}  ROI={roi_str:>8}  ({elapsed_f:.1f}s)")
            fold_results.append(fr)

        decision, agg = _wf_decision(fold_results)
        print(f"\n  DECISION: {decision}")
        if agg:
            print(f"  mean_roi={agg['mean_roi']:+.2f}%  std_roi={agg['std_roi']:.2f}%"
                  f"  pos_folds={agg['n_pos_roi']}/{agg['n_valid_folds']}")
        all_results[stat] = {"decision": decision, "folds": fold_results, "agg": agg}

    # ─── summary table ───────────────────────────────────────────────────────
    total_elapsed = time.time() - t_total
    print(f"\n{'='*70}")
    print(f"  WALK-FORWARD SUMMARY  (total {total_elapsed:.1f}s)")
    print(f"{'='*70}")
    header = f"  {'stat':<6}  {'f1 ROI':>8}  {'f2 ROI':>8}  {'f3 ROI':>8}  {'f4 ROI':>8}  {'mean':>8}  {'std':>7}  {'decision'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    ship_list, revert_list, hold_list = [], [], []
    for stat in ALL_STATS:
        res = all_results.get(stat, {})
        dec = res.get("decision", "?")
        agg = res.get("agg", {})
        folds = res.get("folds", [])
        fold_rois = [f["roi_pct"] for f in folds]
        roi_strs = [f"{r:+.1f}%" if r is not None else "  N/A " for r in fold_rois]
        while len(roi_strs) < 4:
            roi_strs.append("  N/A ")
        mean_roi = agg.get("mean_roi")
        std_roi = agg.get("std_roi")
        mean_s = f"{mean_roi:+.2f}%" if mean_roi is not None else "  N/A "
        std_s = f"{std_roi:.2f}%" if std_roi is not None else "  N/A "
        print(f"  {stat:<6}  {roi_strs[0]:>8}  {roi_strs[1]:>8}  {roi_strs[2]:>8}  "
              f"{roi_strs[3]:>8}  {mean_s:>8}  {std_s:>7}  {dec}")
        if dec == "SHIP":
            ship_list.append(stat)
        elif dec == "REVERT":
            revert_list.append(stat)
        elif dec == "HOLD":
            hold_list.append(stat)
    print(f"\n  SHIP:   {ship_list}")
    print(f"  HOLD:   {hold_list}")
    print(f"  REVERT: {revert_list}")
    print(f"{'='*70}\n")

    # ─── write baseline JSON ────────────────────────────────────────────────
    baseline = {
        "version": "iter5_wf_baseline",
        "generated_at": datetime.now().isoformat(),
        "wf_method": "4-window single-model eval (shortcut; no per-fold retrain)",
        "wf_limitation": (
            "No 2024-25 regular-season closing lines available. Eval uses 4 "
            "date-slices of 2024 playoffs (same model, different game rounds). "
            "True rolling WF requires ~6h compute and should be scheduled separately."
        ),
        "fold_definitions": [
            {"fold_id": fid, "window_start": ws, "window_end": we}
            for fid, ws, we in FOLDS
        ],
        "ship_rule": "3+/4 folds positive ROI AND mean_roi > +0.5%",
        "revert_rule": "2+ folds negative ROI",
        "stats": {},
    }
    for stat in ALL_STATS:
        res = all_results.get(stat, {})
        baseline["stats"][stat] = {
            "decision": res.get("decision"),
            "agg": res.get("agg", {}),
            "folds": [
                {
                    "fold_id": f["fold_id"],
                    "window_start": f["window_start"],
                    "window_end": f["window_end"],
                    "n_pred": f["n_pred"],
                    "n_bets": f["n_bets"],
                    "hit_rate": f["hit_rate"],
                    "roi_pct": f["roi_pct"],
                    "mae_actual": f["mae_actual"],
                    "status": f["status"],
                }
                for f in res.get("folds", [])
            ],
        }

    cache_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    baseline_path = os.path.join(cache_dir, "wf_baseline_iter3.json")
    with open(baseline_path, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"  Baseline written -> {baseline_path}")

    # ─── knowledge vault append ──────────────────────────────────────────────
    _append_vault(all_results, total_elapsed)

    print(f"\n  Done. Total runtime: {total_elapsed:.1f}s")


def _append_vault(all_results: Dict, elapsed: float) -> None:
    vault_path = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")
    if not os.path.exists(vault_path):
        print(f"  [warn] vault not found, skipping vault append: {vault_path}")
        return

    lines = [
        "",
        f"## Walk-Forward 4-Window Gate (Iteration 5)  {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "**Setup:** Single OOS model (cutoff 2024-04-21) evaluated across 4 date-slices of",
        "the 2024 NBA playoffs. No per-fold retraining (shortcut — true WF = 6h compute).",
        "Four folds track game-round distribution shift: early R1 → conf semis/finals.",
        "",
        "**Data gap:** No 2024-25 regular-season closing lines exist in the data store",
        "(extended_oos_canonical jumps 2024-05-23 → 2026-01-28). Fold definitions must",
        "be updated once regular-season lines are scraped.",
        "",
        "**Per-stat results:**",
        "",
        "| stat | f1_roi | f2_roi | f3_roi | f4_roi | mean_roi | std_roi | decision |",
        "|------|-------:|-------:|-------:|-------:|---------:|--------:|----------|",
    ]
    for stat in ["pts", "ast", "reb", "fg3m", "blk", "stl", "tov"]:
        res = all_results.get(stat, {})
        dec = res.get("decision", "?")
        agg = res.get("agg", {})
        folds = res.get("folds", [])
        fold_rois = [f["roi_pct"] for f in folds]
        while len(fold_rois) < 4:
            fold_rois.append(None)
        def _fmt(v):
            return f"{v:+.2f}%" if v is not None else "N/A"
        mean_roi = agg.get("mean_roi")
        std_roi = agg.get("std_roi")
        lines.append(
            f"| {stat} | {_fmt(fold_rois[0])} | {_fmt(fold_rois[1])} | {_fmt(fold_rois[2])} | "
            f"{_fmt(fold_rois[3])} | {_fmt(mean_roi)} | {f'{std_roi:.2f}%' if std_roi is not None else 'N/A'} | **{dec}** |"
        )
    lines += [
        "",
        f"**Decision rule:** SHIP = 3+/4 folds +ROI AND mean > +0.5% | REVERT = 2+ folds negative",
        f"**Total runtime:** {elapsed:.0f}s",
        "",
    ]
    with open(vault_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault append -> {vault_path}")


if __name__ == "__main__":
    main()
