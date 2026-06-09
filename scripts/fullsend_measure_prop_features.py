"""fullsend_measure_prop_features.py -- Honest MAE delta: base vs base+line_movement+atlas.

Runs the same expanding-window walk-forward harness as eval_atlas_lift.py, but
extended to include BOTH the new feature families behind CV_PROP_EXTRA_FEATURES:
  - prop_line_movement  (7 features, currently all-zero = neutral on current data)
  - atlas_*             (player atlas sections, same join as eval_atlas_lift.py)

The "base" condition sets CV_PROP_EXTRA_FEATURES=0 (flag OFF) so it is
byte-identical to the pre-change path.  The "extra" condition sets it to 1.

Because the line-movement features return the neutral zero vector on all current
training rows (no data/lines/ CSVs cover historical game dates), the only real
delta comes from the atlas columns -- identical to what eval_atlas_lift.py already
measured.  Both deltas are printed side-by-side so the caller can compare.

Run:
    set NBA_OFFLINE=1
    python scripts/fullsend_measure_prop_features.py --device auto
    python scripts/fullsend_measure_prop_features.py --splits 4 --stats pts,reb,ast,fg3m,stl,blk,tov
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STATS_DEFAULT = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_MIN_TRAIN_ROWS = 5000
_MIN_HOLDOUT_ROWS = 2000
_XGB_DEVICE: str = "cpu"


def _resolve_device(device_arg: str) -> str:
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return device_arg


def _matrix(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[_cell(r.get(c, np.nan)) for c in cols] for r in rows], dtype=float)


def _cell(v: Any) -> float:
    if v is None:
        return float("nan")
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float("nan")


def _impute(train: np.ndarray, *mats: np.ndarray) -> Tuple[np.ndarray, ...]:
    if train.shape[1] == 0:
        return (train, *mats)
    med = np.nanmedian(train, axis=0)
    med = np.where(np.isnan(med), 0.0, med)

    def fill(a: np.ndarray) -> np.ndarray:
        out = a.copy()
        idx = np.where(np.isnan(out))
        out[idx] = np.take(med, idx[1])
        return out

    return tuple(fill(m) for m in (train, *mats))


def _fit_predict(X_tr: np.ndarray, y_tr: np.ndarray, X_ho: np.ndarray,
                 sw: Optional[np.ndarray]) -> np.ndarray:
    try:
        import xgboost as xgb
    except Exception:
        coef, *_ = np.linalg.lstsq(np.nan_to_num(X_tr), y_tr, rcond=None)
        return np.nan_to_num(X_ho) @ coef
    kwargs: Dict[str, Any] = dict(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42, n_jobs=-1,
        objective="reg:squarederror", eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        kwargs["device"] = "cuda"
    try:
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, sample_weight=sw, verbose=False)
    except Exception:
        kwargs.pop("device", None)
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, sample_weight=sw, verbose=False)
    return m.predict(X_ho)


def _fold_bounds(n: int, n_splits: int) -> List[Tuple[int, int, int]]:
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    out: List[Tuple[int, int, int]] = []
    for i, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if i == n_splits - 1 else int(n * fold_ends[i + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        out.append((tr_end, va_end, te_end))
    return out


def _sample_weights(rows: List[dict], tr_end: int) -> np.ndarray:
    tr_dates = [datetime.fromisoformat(rows[i]["date"][:19]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    return np.exp(-0.5 * age)


def _join_atlas(rows: List[dict]) -> List[str]:
    """Join atlas features into rows in place; return new atlas_* column names."""
    try:
        from src.loop.atlas_features import join_atlas_features
    except Exception as exc:
        print(f"[fullsend] atlas_features unavailable ({exc}); atlas cols = 0")
        return []
    try:
        join_atlas_features(rows, entity_type="player", id_key="player_id", date_key="date")
    except Exception as exc:
        print(f"[fullsend] join_atlas_features failed ({exc}); atlas cols = 0")
        return []
    seen: set = set()
    for r in rows:
        for k, v in r.items():
            if k.startswith("atlas_") and isinstance(v, (int, float)):
                seen.add(k)
    cols = sorted(seen)
    if not cols:
        print("[fullsend] no numeric atlas columns materialised -> base+atlas == base")
    return cols


def _join_line_movement(rows: List[dict]) -> List[str]:
    """Join prop_line_movement features into rows in place; return new column names.

    On current data every call returns the neutral zero vector (no data/lines/
    CSVs exist for historical game dates) so this is a no-op until lines are
    captured alongside historical rows.  We wire it anyway so the flag-on path
    exercises the real code path.

    asof is set to None -> always the neutral vector (no leak, no signal yet).
    """
    try:
        from src.ingest.prop_line_movement import get_prop_line_movement as _plm, feature_keys
    except Exception as exc:
        print(f"[fullsend] prop_line_movement unavailable ({exc}); plm cols = 0")
        return []

    plm_keys = feature_keys()
    added: set = set()
    for row in rows:
        gdate = str(row.get("date", ""))[:10]
        pname = str(row.get("player_name", ""))
        if not gdate or not pname:
            continue
        # asof=None -> always neutral zero vector (leak-safe, no lookahead)
        try:
            feats = _plm(pname, "pts", gdate, asof=None)
        except Exception:
            feats = {k: 0.0 for k in plm_keys}
        for k, v in feats.items():
            if k not in row:
                row[k] = float(v)
                added.add(k)
    cols = [k for k in plm_keys if k in added]
    if not cols:
        print("[fullsend] no prop_line_movement columns added (all-zero / no player_name in rows)")
    return cols


def run_comparison(stats: List[str], n_splits: int = 4) -> Dict[str, Any]:
    """Base vs base+atlas+line_movement walk-forward comparison.

    Mirrors eval_atlas_lift.py:eval_lift() exactly, extended with line-movement.
    """
    from src.prediction.prop_pergame import build_pergame_dataset  # type: ignore

    print("[fullsend] loading prop dataset (build_pergame_dataset)...")
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"[fullsend] rows={n}, base features={len(base_cols)}")

    # Join all extra features into the row dicts (in place)
    print("[fullsend] joining atlas features...")
    atlas_cols = _join_atlas(rows)
    print(f"[fullsend] atlas columns: {len(atlas_cols)}")

    print("[fullsend] joining prop_line_movement features...")
    plm_cols = _join_line_movement(rows)
    print(f"[fullsend] line_movement columns: {len(plm_cols)}")

    extra_cols = atlas_cols + [c for c in plm_cols if c not in atlas_cols]
    aug_cols = list(base_cols) + extra_cols
    print(f"[fullsend] total extra cols={len(extra_cols)}, augmented matrix width={len(aug_cols)}")

    X_base = _matrix(rows, list(base_cols))
    X_aug = _matrix(rows, aug_cols)
    bounds = _fold_bounds(n, n_splits)

    per_stat: Dict[str, Any] = {}
    for stat in stats:
        y = np.array([r.get(f"target_{stat}", np.nan) for r in rows], dtype=float)
        base_maes, aug_maes, deltas = [], [], []
        for fi, (tr_end, va_end, te_end) in enumerate(bounds):
            if tr_end < _MIN_TRAIN_ROWS or (te_end - va_end) < _MIN_HOLDOUT_ROWS:
                continue
            ok_tr = ~np.isnan(y[:tr_end])
            ho = slice(va_end, te_end)
            ok_ho = ~np.isnan(y[ho])
            if not ok_tr.any() or not ok_ho.any():
                continue
            sw = _sample_weights(rows, tr_end)
            yb_tr, yb_ho = y[:tr_end], y[ho]
            # base
            b_tr, b_ho = _impute(X_base[:tr_end], X_base[ho])
            pb = _fit_predict(b_tr, yb_tr, b_ho, sw)
            mae_b = float(np.mean(np.abs(pb - yb_ho)))
            # base+extra
            a_tr, a_ho = _impute(X_aug[:tr_end], X_aug[ho])
            pa = _fit_predict(a_tr, yb_tr, a_ho, sw)
            mae_a = float(np.mean(np.abs(pa - yb_ho)))
            deltas.append(mae_a - mae_b)
            base_maes.append(mae_b)
            aug_maes.append(mae_a)
            print(f"  {stat.upper():4s} fold{fi + 1}: base={mae_b:.4f} "
                  f"extra={mae_a:.4f} delta={mae_a - mae_b:+.4f}", flush=True)
        if not deltas:
            per_stat[stat] = {"evaluated": False, "reason": "no evaluable fold"}
            continue
        n_neg = sum(1 for d in deltas if d < 0)
        per_stat[stat] = {
            "evaluated": True,
            "base_mae_mean": float(np.mean(base_maes)),
            "extra_mae_mean": float(np.mean(aug_maes)),
            "delta_mae_mean": float(np.mean(deltas)),
            "deltas": deltas,
            "neg_folds": n_neg,
            "n_folds": len(deltas),
            "all_improve": bool(n_neg == len(deltas)),
        }
    return {
        "run_timestamp": datetime.now().isoformat(),
        "device": _XGB_DEVICE,
        "n_rows": n,
        "n_base_features": len(base_cols),
        "n_atlas_features": len(atlas_cols),
        "n_plm_features": len(plm_cols),
        "n_extra_features": len(extra_cols),
        "n_splits": n_splits,
        "per_stat": per_stat,
    }


def _print_summary(result: Dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("  FULLSEND MEASURE -- per-stat holdout MAE delta (base+extra - base)")
    print("  extra = atlas features + prop_line_movement (7 features, all-zero now)")
    print("  negative delta = extra features REDUCE error")
    print("  positive delta = REGRESSION vs production baseline")
    print("=" * 72)
    print(f"  atlas cols={result['n_atlas_features']}  "
          f"plm cols={result['n_plm_features']}  "
          f"device={result['device']}")
    print(f"  {'stat':5s} | {'base_mae':>9s} | {'extra_mae':>9s} | "
          f"{'delta':>9s} | verdict")
    print("  " + "-" * 62)
    helped = 0
    regressed = 0
    evaluated = 0
    for stat, v in result["per_stat"].items():
        if not v.get("evaluated"):
            print(f"  {stat.upper():5s} | {'--':>9s} | {'--':>9s} | "
                  f"{'--':>9s} | {v.get('reason', 'n/a')}")
            continue
        evaluated += 1
        d = v["delta_mae_mean"]
        verdict = "HELPS" if d < -0.005 else ("REGRESSES" if d > 0.005 else "neutral")
        if d < -0.005:
            helped += 1
        elif d > 0.005:
            regressed += 1
        print(f"  {stat.upper():5s} | {v['base_mae_mean']:9.4f} | "
              f"{v['extra_mae_mean']:9.4f} | {d:+9.4f} | {verdict}")
    print("  " + "-" * 62)
    if result["n_atlas_features"] == 0 and result["n_plm_features"] == 0:
        print("  NOTE: 0 extra features available -> base+extra identical to base.")
    elif result["n_plm_features"] == 0:
        print("  NOTE: prop_line_movement = 0 cols (no player_name in dataset rows) "
              "-- delta is atlas-only, same as eval_atlas_lift.py.")
    print(f"  VERDICT: helps {helped}/{evaluated}, regresses {regressed}/{evaluated} "
          f"evaluated stats")
    if regressed > helped:
        print("  RECOMMENDATION: DO NOT enable by default -- REGRESSES production edge.")
    elif helped > regressed:
        print("  RECOMMENDATION: Extra features likely helpful. Validate ROI before ship.")
    else:
        print("  RECOMMENDATION: Marginal / mixed -- owner decision.")
    print("=" * 72)
    print("\nTo disable (revert to production baseline): set CV_PROP_EXTRA_FEATURES=0")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--stats", default=",".join(STATS_DEFAULT))
    ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[fullsend] device={_XGB_DEVICE}  NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")
    print(f"[fullsend] CV_PROP_EXTRA_FEATURES={os.environ.get('CV_PROP_EXTRA_FEATURES', '1 (default)')}")

    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    t0 = time.time()
    result = run_comparison(stats, n_splits=args.splits)
    result["wall_seconds"] = round(time.time() - t0, 1)

    _print_summary(result)

    out_path = args.out or os.path.join(
        PROJECT_DIR, "data", "models", "fullsend_extra_features_lift.json")
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n[fullsend] wrote {out_path}")
    except Exception as exc:
        print(f"[fullsend] could not write summary JSON ({exc})")


if __name__ == "__main__":
    main()
