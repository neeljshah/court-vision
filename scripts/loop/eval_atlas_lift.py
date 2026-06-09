"""eval_atlas_lift.py -- does the ARM-B intelligence layer actually improve predictions?

This CLI quantifies the prediction LIFT of the shipped atlas sections. It runs the
existing prop walk-forward harness twice per stat -- once on the FULL production
feature matrix (``base``), once on the same matrix augmented with the leak-safe
``atlas_*`` features from ``src.loop.atlas_features`` (``base+atlas``) -- and prints
the per-stat holdout MAE delta (``base+atlas`` minus ``base``). A NEGATIVE delta means
the atlas intelligence REDUCES error (the intelligence is paying its way).

This is an ABLATION, mirroring the honest gate (``src/loop/gate.py``): the atlas
columns are evaluated as a marginal addition to the FULL model, never in isolation,
on the same expanding-window chronological folds the canonical harness uses
(``scripts/prop_pergame_walk_forward.py`` -- folds at ``(i+1)/(n_splits+1)``).

Design notes:
  * Leak-safe: atlas features are joined per row keyed on that row's own ``date``
    (``join_atlas_features``), so no future intelligence enters a historical row.
  * GPU: XGBoost ``device="cuda"`` (XGB 2.x) with a CPU fallback, the canonical
    ``_resolve_device`` pattern from ``prop_pergame_walk_forward_built.py``.
  * Robust import: ``atlas_features`` may be partial / produce zero columns. We import
    it defensively; if no atlas columns materialise the delta is reported as 0.0 and
    the run still completes (so this script never blocks the loop).

Run:
    set NBA_OFFLINE=1
    python scripts/loop/eval_atlas_lift.py --device auto
    python scripts/loop/eval_atlas_lift.py --splits 4 --stats pts,reb,ast --device cpu
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

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STATS_DEFAULT = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# Mirror the gate's fold-skip floor scaled to the prod row counts.
_MIN_TRAIN_ROWS = 5000
_MIN_HOLDOUT_ROWS = 2000

# Module-level device, set in main() (mirrors the canonical probe scripts).
_XGB_DEVICE: str = "cpu"


def _resolve_device(device_arg: str) -> str:
    """Resolve 'auto' -> 'cuda' if torch reports a GPU, else 'cpu'."""
    if device_arg == "auto":
        try:
            import torch  # optional dependency
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return device_arg


def _load_atlas_join():
    """Import the atlas read-side bridge defensively.

    Returns ``(join_fn, names_fn)`` or ``(None, None)`` if the helper is absent or
    only partially built. The caller treats a missing helper as "no atlas columns"
    and still completes the run, so this script imports cleanly regardless.
    """
    try:
        from src.loop.atlas_features import (  # type: ignore
            join_atlas_features, atlas_feature_names)
        return join_atlas_features, atlas_feature_names
    except Exception as exc:  # partial / missing module
        print(f"[eval_atlas_lift] atlas_features unavailable ({exc}); "
              f"atlas columns = none, deltas will be 0.0")
        return None, None


def _atlas_columns(rows: List[dict], join_fn, names_fn) -> List[str]:
    """Join atlas features into ``rows`` (in place) and return the new column names.

    The atlas columns are exactly the keys present after the join that start with
    ``atlas_``. We restrict to numeric leaves (drop categorical strings) so the
    matrix stays purely numeric. Returns an empty list when no atlas data exists.
    """
    if join_fn is None:
        return []
    try:
        join_fn(rows, entity_type="player", id_key="player_id", date_key="date")
    except Exception as exc:
        print(f"[eval_atlas_lift] join_atlas_features failed ({exc}); atlas cols = none")
        return []
    seen: set = set()
    for r in rows:
        for k, v in r.items():
            if k.startswith("atlas_") and isinstance(v, (int, float)):
                seen.add(k)
    cols = sorted(seen)
    if not cols:
        print("[eval_atlas_lift] no numeric atlas columns materialised "
              "(empty coverage at these dates) -> base+atlas == base")
    return cols


def _matrix(rows: List[dict], cols: List[str]) -> np.ndarray:
    """Build an (n, len(cols)) float matrix; NaN where a row lacks a column."""
    return np.array(
        [[_cell(r.get(c, np.nan)) for c in cols] for r in rows], dtype=float)


def _cell(v: Any) -> float:
    """Coerce one cell to float; non-numeric / None -> NaN."""
    if v is None:
        return float("nan")
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return float("nan")


def _impute(train: np.ndarray, *mats: np.ndarray) -> Tuple[np.ndarray, ...]:
    """Fill NaNs with per-column TRAIN medians (no leakage); mirrors gate._impute."""
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
    """Train one XGB regressor (GPU with CPU fallback) and predict the holdout.

    Mirrors the canonical ``device="cuda"`` (XGB 2.x) try/except CPU-fallback pattern.
    """
    try:
        import xgboost as xgb
    except Exception:  # degenerate linear fallback so the run still yields a number
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
    except Exception:  # GPU unavailable / OOM -> CPU retry
        kwargs.pop("device", None)
        m = xgb.XGBRegressor(**kwargs)
        m.fit(X_tr, y_tr, sample_weight=sw, verbose=False)
    return m.predict(X_ho)


def _fold_bounds(n: int, n_splits: int) -> List[Tuple[int, int, int]]:
    """Expanding-window (tr_end, va_end, te_end) per fold (prop_pergame style)."""
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    out: List[Tuple[int, int, int]] = []
    for i, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if i == n_splits - 1 else int(n * fold_ends[i + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        out.append((tr_end, va_end, te_end))
    return out


def _sample_weights(rows: List[dict], tr_end: int) -> np.ndarray:
    """Recency-decay weights exp(-0.5*age_years) over the train slice."""
    tr_dates = [datetime.fromisoformat(rows[i]["date"][:19]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    return np.exp(-0.5 * age)


def eval_lift(stats: List[str], n_splits: int = 4) -> Dict[str, Any]:
    """Run the base-vs-base+atlas ablation per stat and return the summary.

    For each fold we train two XGB models on identical (train, holdout) row slices:
    one on the FULL base feature matrix, one on base+atlas. The reported per-stat
    metric is the mean over folds of ``MAE(base+atlas) - MAE(base)`` (negative = the
    atlas intelligence reduces error).
    """
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns

    print("[eval_atlas_lift] loading prop dataset (build_pergame_dataset)...")
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"[eval_atlas_lift] rows={n}, base features={len(base_cols)}")

    join_fn, names_fn = _load_atlas_join()
    atlas_cols = _atlas_columns(rows, join_fn, names_fn)
    print(f"[eval_atlas_lift] atlas columns joined: {len(atlas_cols)}")
    aug_cols = list(base_cols) + atlas_cols

    X_base = _matrix(rows, list(base_cols))
    X_aug = _matrix(rows, aug_cols)
    bounds = _fold_bounds(n, n_splits)

    per_stat: Dict[str, Any] = {}
    for stat in stats:
        y = np.array([r.get(f"target_{stat}", np.nan) for r in rows], dtype=float)
        deltas: List[float] = []
        base_maes: List[float] = []
        aug_maes: List[float] = []
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
            # base+atlas (identical slices; only the columns differ)
            a_tr, a_ho = _impute(X_aug[:tr_end], X_aug[ho])
            pa = _fit_predict(a_tr, yb_tr, a_ho, sw)
            mae_a = float(np.mean(np.abs(pa - yb_ho)))
            deltas.append(mae_a - mae_b)
            base_maes.append(mae_b)
            aug_maes.append(mae_a)
            print(f"  {stat.upper():4s} fold{fi + 1}: base={mae_b:.4f} "
                  f"atlas={mae_a:.4f} delta={mae_a - mae_b:+.4f}", flush=True)
        if not deltas:
            per_stat[stat] = {"evaluated": False, "reason": "no evaluable fold"}
            continue
        n_neg = sum(1 for d in deltas if d < 0)
        per_stat[stat] = {
            "evaluated": True,
            "base_mae_mean": float(np.mean(base_maes)),
            "atlas_mae_mean": float(np.mean(aug_maes)),
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
        "atlas_features": atlas_cols,
        "n_splits": n_splits,
        "per_stat": per_stat,
    }


def _print_summary(result: Dict[str, Any]) -> None:
    """Print the headline per-stat MAE-delta table (negative = atlas helps)."""
    print("\n" + "=" * 64)
    print("  ATLAS LIFT -- per-stat holdout MAE delta (base+atlas - base)")
    print("  negative delta = atlas intelligence REDUCES error")
    print("=" * 64)
    print(f"  {'stat':5s} | {'base_mae':>9s} | {'atlas_mae':>9s} | "
          f"{'delta':>9s} | folds")
    print("  " + "-" * 56)
    helped = 0
    evaluated = 0
    for stat, v in result["per_stat"].items():
        if not v.get("evaluated"):
            print(f"  {stat.upper():5s} | {'--':>9s} | {'--':>9s} | "
                  f"{'--':>9s} | {v.get('reason', 'n/a')}")
            continue
        evaluated += 1
        d = v["delta_mae_mean"]
        if d < 0:
            helped += 1
        print(f"  {stat.upper():5s} | {v['base_mae_mean']:9.4f} | "
              f"{v['atlas_mae_mean']:9.4f} | {d:+9.4f} | "
              f"{v['neg_folds']}/{v['n_folds']} neg")
    print("  " + "-" * 56)
    if result["n_atlas_features"] == 0:
        print("  NOTE: 0 atlas features available -> base+atlas identical to base.")
    print(f"  atlas helps {helped}/{evaluated} evaluated stats "
          f"({result['n_atlas_features']} atlas features, device={result['device']})")
    print("=" * 64)


def main() -> None:
    """Parse args, run the ablation, print + persist the per-stat MAE-delta summary."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=4, help="walk-forward folds")
    ap.add_argument("--stats", default=",".join(STATS_DEFAULT),
                    help="comma-separated stats (default: all 7)")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto)")
    ap.add_argument("--out", default=None,
                    help="output JSON path (default: data/models/atlas_lift.json)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[eval_atlas_lift] device={_XGB_DEVICE}  NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}")

    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    t0 = time.time()
    result = eval_lift(stats, n_splits=args.splits)
    result["wall_seconds"] = round(time.time() - t0, 1)

    _print_summary(result)

    out_path = args.out or os.path.join(
        PROJECT_DIR, "data", "models", "atlas_lift.json")
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n[eval_atlas_lift] wrote {out_path}")
    except Exception as exc:
        print(f"[eval_atlas_lift] could not write summary JSON ({exc})")


if __name__ == "__main__":
    main()
