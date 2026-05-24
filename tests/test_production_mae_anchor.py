"""tests/test_production_mae_anchor.py — pin cycle-48 verified production MAE.

Runs the same vectorised production-dispatch path as `verify_production_mae.py`
on the 80/20 chronological holdout and asserts that no stat has drifted by
more than the tolerance from the cycle-48 honest-baseline anchors documented
in `PREDICTIONS_QUICKSTART.md` (and reproduced in the WHY-this-matters block of
the loop-5 cycle-93b cycle).

If this test fails, EITHER the production prediction path has silently
regressed (most likely: someone added a feature in a way that perturbs the
dispatch) OR the models on disk were retrained without updating the anchors.

Anchors (cycle 48, verified by `scripts/verify_production_mae.py` in cycle 93b):
    PTS 4.6210 REB 1.9023 AST 1.3559 FG3M 0.8943 STL 0.7153 BLK 0.4398 TOV 0.8932

Tolerance: 0.02 MAE per stat (matches verify_production_mae.py).
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from typing import Optional

import numpy as np
import pytest

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _USE_Q50_STATS,
    _LOG_TRANSFORM_STATS,
    _SQRT_HUBER_STATS,
    _MODEL_DIR,
    _META_WEIGHTS_FILENAME,
    build_pergame_dataset,
    feature_columns,
    _load_q50_model,
    load_pergame_model,
)

# Cycle-48 verified anchors (also pinned in PREDICTIONS_QUICKSTART.md).
ANCHORS = {
    "pts":  4.6210,
    "reb":  1.9023,
    "ast":  1.3559,
    "fg3m": 0.8943,
    "stl":  0.7153,
    "blk":  0.4398,
    "tov":  0.8932,
}
TOLERANCE = 0.02


def _inv(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _bulk_predict(stat: str, X: np.ndarray) -> Optional[np.ndarray]:
    """Mirror of verify_production_mae._score_q50/_score_blend dispatch."""
    if stat in _USE_Q50_STATS:
        m = _load_q50_model(stat, _MODEL_DIR)
        if m is None:
            return None
        return _inv(stat, m.predict(X))
    models = load_pergame_model(stat, _MODEL_DIR)
    if not models:
        return None
    parts = []
    for entry in models:
        if isinstance(entry, tuple):
            scaler, m = entry
            parts.append(m.predict(scaler.transform(X)))
        else:
            parts.append(entry.predict(X))
    parts = [_inv(stat, p) for p in parts]
    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    try:
        with open(wmap_path, encoding="utf-8") as f:
            wmap = json.load(f)
    except Exception:
        wmap = {}
    w = wmap.get(stat) or {}
    if len(parts) == 3:
        blend = (float(w.get("w_xgb", 1 / 3)) * parts[0]
                 + float(w.get("w_lgb", 1 / 3)) * parts[1]
                 + float(w.get("w_mlp", 1 / 3)) * parts[2])
    else:
        blend = np.mean(np.column_stack(parts), axis=1)
    return np.clip(blend, 0.0, None)


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_DIR, "data", "nba")),
    reason="pergame dataset directory missing — skip on fresh checkout",
)
def test_production_mae_matches_cycle48_anchors() -> None:
    """No stat may drift more than TOLERANCE from its cycle-48 verified anchor."""
    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        pytest.skip("no rows built — gamelog cache likely empty")
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array(
        [[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
        dtype=float,
    )

    drift = []
    for stat in STATS:
        y_true = np.array([float(r[f"target_{stat}"]) for r in holdout], dtype=float)
        pred = _bulk_predict(stat, X)
        if pred is None:
            pytest.skip(f"{stat}: model artifact missing on disk")
        mae = float(np.mean(np.abs(pred - y_true)))
        anchor = ANCHORS[stat]
        delta = mae - anchor
        if abs(delta) > TOLERANCE:
            drift.append((stat, anchor, mae, delta))

    assert not drift, (
        "Production MAE drifted from cycle-48 anchors:\n"
        + "\n".join(
            f"  {s}: anchor {a:.4f}, live {m:.4f} (delta {d:+.4f})"
            for s, a, m, d in drift
        )
    )
