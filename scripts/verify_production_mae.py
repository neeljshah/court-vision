"""verify_production_mae.py — sanity check the honest MAEs claimed in PREDICTIONS_QUICKSTART.

Loads the pergame dataset, takes the same 80/20 chronological holdout that
training uses, and scores the production model on the whole holdout in one
shot per stat (load model once, vectorized predict). Respects the cycle-27
_USE_Q50_STATS dispatch so this is the same prediction path used by
predict_pergame() at inference time.

Reports per-stat MAE/R² + delta vs PREDICTIONS_QUICKSTART claims. Exits 0 if
no claim is off by more than ±0.02 MAE; exits 1 otherwise so a future bot
loop catches drift.

Run:
    python scripts/verify_production_mae.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _USE_Q50_STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MODEL_DIR, _META_WEIGHTS_FILENAME,
    build_pergame_dataset, feature_columns,
    _load_q50_model, load_pergame_model,
)
import json

# Claims from PREDICTIONS_QUICKSTART.md (cycle 40 honest table).
QUICKSTART_MAE = {
    "pts":  4.62,
    "reb":  1.90,
    "ast":  1.36,
    "fg3m": 0.89,
    "stl":  0.72,
    "blk":  0.44,
    "tov":  0.89,
}

TOLERANCE = 0.02


def _holdout_slice(rows):
    """Replicate the 80/20 chronological split prop_pergame.train uses."""
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    val_end = int(n * 0.80)
    return rows[val_end:]


def _inv(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _score_q50(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    """Single q50 model predicting transformed-space."""
    m = _load_q50_model(stat, _MODEL_DIR)
    if m is None:
        return None
    pred_t = m.predict(X)
    return _inv(stat, pred_t)


def _score_blend(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    """NNLS-weighted 3-way blend reflecting production load_pergame_model."""
    models = load_pergame_model(stat)
    if not models:
        return None
    # Determine entry types: XGB, LGB are raw learners with .predict on X
    # directly; MLP entries are (scaler, model) tuples that need scaling.
    parts = []
    for entry in models:
        if isinstance(entry, tuple):
            scaler, m = entry
            parts.append(m.predict(scaler.transform(X)))
        else:
            parts.append(entry.predict(X))
    # Inverse-transform per learner (each was trained on the transformed target).
    parts = [_inv(stat, p) for p in parts]
    # NNLS weights live in meta_weights_pergame.json — read directly.
    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    try:
        with open(wmap_path, encoding="utf-8") as f:
            wmap = json.load(f)
    except Exception:
        wmap = {}
    w = wmap.get(stat) or {}
    w_xgb = float(w.get("xgb", 1.0 / max(1, len(parts))))
    w_lgb = float(w.get("lgb", 1.0 / max(1, len(parts))))
    w_mlp = float(w.get("mlp", 1.0 / max(1, len(parts))))
    if len(parts) == 3:
        blend = w_xgb * parts[0] + w_lgb * parts[1] + w_mlp * parts[2]
    else:
        blend = np.mean(np.column_stack(parts), axis=1)
    return np.clip(blend, 0.0, None)


def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    holdout = _holdout_slice(rows)
    cols = feature_columns()
    print(f"  rows={len(rows)} | holdout={len(holdout)} | features={len(cols)}\n",
          flush=True)

    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)

    drift = []
    print(f"{'stat':<5} {'claim':>6} {'live':>7} {'delta':>7}  {'dispatch':<8}  {'verdict':<10}")
    print("-" * 56)
    for stat in STATS:
        y_true = np.array([float(r[f"target_{stat}"]) for r in holdout], dtype=float)
        dispatch = "q50" if stat in _USE_Q50_STATS else "blend"
        if stat in _USE_Q50_STATS:
            pred = _score_q50(stat, X)
        else:
            pred = _score_blend(stat, X)
        if pred is None:
            print(f"{stat:<5} (model missing on disk — cannot verify)")
            drift.append(stat)
            continue
        mae = float(np.mean(np.abs(pred - y_true)))
        claim = QUICKSTART_MAE[stat]
        delta = mae - claim
        within = abs(delta) <= TOLERANCE
        verdict = "OK" if within else ("WORSE" if delta > 0 else "BETTER")
        if not within:
            drift.append((stat, claim, mae, delta))
        print(f"{stat:<5} {claim:>6.2f} {mae:>7.4f} {delta:>+7.4f}  {dispatch:<8}  {verdict:<10}")

    print()
    if not drift:
        print(f"ALL within +-{TOLERANCE} MAE of quickstart. Production matches claims.")
        return 0
    print(f"DRIFT detected on {len(drift)} stat(s) vs PREDICTIONS_QUICKSTART:")
    for d in drift:
        if isinstance(d, tuple):
            s, c, m, dl = d
            print(f"  {s}: claim {c:.2f}, live {m:.4f} (d={dl:+.4f})")
        else:
            print(f"  {d}: model missing or unloadable on disk")
    print("\nNext steps: either retrain (train_pergame_models) or update the "
          "quickstart with the new live MAEs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
