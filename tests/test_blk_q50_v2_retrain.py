"""tests/test_blk_q50_v2_retrain.py — Cycle 99a (loop 5).

Five tests around scripts/retrain_blk_q50_v2.py:

  1. blk_v2_feature_columns surfaces the position one-hot columns (and the
     q1_blk_l5 column is intentionally EXCLUDED because its holdout
     coverage is below the 30% spec gate).
  2. The v2 metrics JSON has been written by the retrain run.
  3. No-op regression: predicting against the cycle-29 v1 artifact on the
     canonical holdout yields the cycle-29 anchor MAE (sanity that the
     retrain did not silently corrupt v1).
  4. The newly trained v2 model emits predictions in a reasonable BLK
     range (0-10 per game). Only loaded when v2 actually shipped.
  5. Walk-forward fold sign matches the single-split direction (consistency
     check — if single-split improves but WF degrades on every fold, the
     retrain script's ship gate must catch and reject).
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pytest

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from src.prediction.prop_pergame import (  # noqa: E402
    _MODEL_DIR,
    _LOG_TRANSFORM_STATS,
    feature_columns,
    _load_q50_model,
    build_pergame_dataset,
)

import retrain_blk_q50_v2 as r99a  # noqa: E402


_METRICS_PATH = os.path.join(_MODEL_DIR, "blk_q50_v2_metrics.json")
_V2_PATH = os.path.join(_MODEL_DIR, "blk_q50_v2.pkl")
_ANCHOR = 0.4398


def _load_metrics():
    if not os.path.exists(_METRICS_PATH):
        pytest.skip("blk_q50_v2_metrics.json missing — run retrain_blk_q50_v2.py")
    with open(_METRICS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── 1. feature_columns surface ───────────────────────────────────────────────

def test_blk_v2_feature_columns_include_position_one_hots():
    """v2 feature columns must contain the three position buckets at the tail
    AND must NOT contain q1_blk_l5 (rejected by the < 30% coverage gate)."""
    cols = r99a.blk_v2_feature_columns()
    base = feature_columns()
    assert cols[: len(base)] == base, "baseline columns must come first"
    for k in r99a._POSITION_BUCKETS:
        assert k in cols, f"missing position one-hot column {k}"
    assert "q1_blk_l5" not in cols, (
        "q1_blk_l5 must be EXCLUDED — its holdout coverage is 0% and fails "
        "the spec's 30% gate"
    )
    assert len(cols) == len(base) + 3


# ── 2. metrics artifact written ──────────────────────────────────────────────

def test_blk_v2_metrics_artifact_written():
    """retrain_blk_q50_v2.py must persist a metrics JSON irrespective of
    ship/reject so downstream cycles can inspect deltas."""
    m = _load_metrics()
    assert m["cycle"] == "99a"
    assert "single_split" in m
    assert "walk_forward" in m
    assert "ship_gate" in m
    assert m["single_split"]["anchor_v1"] == pytest.approx(_ANCHOR)
    assert isinstance(m["ship_gate"]["shipped"], bool)


# ── 3. no-op regression vs cycle-29 v1 ───────────────────────────────────────

@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_DIR, "data", "nba")),
    reason="pergame dataset directory missing — skip on fresh checkout",
)
def test_blk_v1_anchor_unchanged():
    """Predicting against the cycle-29 BLK v1 q50 model on the 80/20
    chronological holdout must still produce the anchor 0.4398 MAE — proves
    the retrain script did not corrupt v1 nor change the production loader."""
    v1 = _load_q50_model("blk", _MODEL_DIR)
    if v1 is None:
        pytest.skip("blk q50 v1 model missing on disk")
    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        pytest.skip("no rows built — gamelog cache empty")
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array(
        [[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
        dtype=float,
    )
    y = np.array([float(r["target_blk"]) for r in holdout], dtype=float)
    pred_t = v1.predict(X)
    # BLK is in _LOG_TRANSFORM_STATS so inverse via expm1.
    assert "blk" in _LOG_TRANSFORM_STATS
    pred = np.clip(np.expm1(pred_t), 0.0, None)
    mae = float(np.mean(np.abs(pred - y)))
    assert abs(mae - _ANCHOR) < 0.02, (
        f"BLK v1 holdout MAE drifted: {mae:.4f} vs anchor {_ANCHOR:.4f}"
    )


# ── 4. v2 predictions in reasonable BLK range ────────────────────────────────

def test_blk_v2_predictions_in_reasonable_range():
    """When v2 actually shipped (artifact on disk), its predictions on the
    holdout must all lie in [0, 10] BLK per game (the BLK distribution has
    max ~9 per game; anything outside is a sign of inverse-transform
    corruption)."""
    if not os.path.exists(_V2_PATH):
        pytest.skip(
            "blk_q50_v2.pkl not on disk — retrain ship gate failed (expected)."
        )
    if not os.path.exists(os.path.join(PROJECT_DIR, "data", "nba")):
        pytest.skip("pergame dataset directory missing")
    import joblib
    v2 = joblib.load(_V2_PATH)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    extra = list(r99a._POSITION_BUCKETS)
    X = r99a._build_X(holdout, cols, extra)
    pred_t = v2.predict(X)
    pred = np.clip(np.expm1(pred_t), 0.0, None)
    assert pred.min() >= 0.0, f"v2 negative BLK prediction: min={pred.min()}"
    assert pred.max() <= 10.0, f"v2 unrealistic BLK prediction: max={pred.max()}"
    # And the mean should be near the empirical BLK mean (~0.5 per game).
    assert 0.2 <= pred.mean() <= 1.5, (
        f"v2 mean prediction {pred.mean():.3f} far from empirical BLK ~0.5"
    )


# ── 5. WF sign consistency with single-split ─────────────────────────────────

def test_blk_v2_wf_sign_check_matches_single_split():
    """Consistency check: the script's ship gate requires BOTH (single_split
    MAE < anchor) AND (WF 4/4 folds negative). When WF folds don't all agree
    with the single-split sign, the ship_gate.shipped flag MUST be False —
    this is the safety net that catches split-specific noise."""
    m = _load_metrics()
    single_ok = m["ship_gate"]["single_split_ok"]
    wf_ok = m["ship_gate"]["walk_forward_ok"]
    shipped = m["ship_gate"]["shipped"]
    # Logical: shipped iff both flags True.
    assert shipped == (single_ok and wf_ok), (
        "ship_gate inconsistent: shipped must equal (single AND wf)"
    )
    # Sanity: when the script reports WF n_negative != n_folds, wf_ok is False.
    wf = m["walk_forward"]
    expected_wf_ok = (wf["n_negative"] == wf["n_folds"])
    assert wf_ok == expected_wf_ok, (
        f"walk_forward_ok flag disagrees with n_negative=={wf['n_negative']} "
        f"of n_folds=={wf['n_folds']}"
    )
    # When this assertion runs, the single-split delta should be reported
    # in the metrics — verify it matches the v2-vs-v1 sign.
    ss = m["single_split"]
    assert "delta" in ss and "mae_v2_new" in ss and "mae_v1_recompute" in ss
    assert ss["delta"] == pytest.approx(
        ss["mae_v2_new"] - ss["mae_v1_recompute"], abs=1e-6
    )
