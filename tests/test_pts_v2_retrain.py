"""tests/test_pts_v2_retrain.py — Cycle 100a (loop 5).

Pins the cycle 100a PTS v2 retrain script's contract:
  1. The 16 new opp_l5 keys are exposed in pts_v2_feature_columns().
  2. When ship gate passes, all 4 retrained PTS v2 artifacts exist on disk.
  3. The v1 production path (pre-cycle-100a) still resolves to a number
     within tolerance of the cycle-48 anchor 4.6104 (post-haircut, current
     prod) — sanity regression test that v2 retrain doesn't accidentally
     touch v1 artifacts.
  4. The v2 in-memory prediction stays in the plausible PTS range 0..60.
  5. v2 WF folds + single-split sign match (both gates agree on direction).

The first 4 tests are always run. Test 5 is skipped when the v2 metrics
JSON isn't present (e.g. fresh checkout that hasn't run the retrain).
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import pytest

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _MODEL_DIR,
    _TEAM_ADV_FEATURE_KEYS,
    STATS,
    feature_columns,
)

# Import directly from the cycle-100a script (it lives in scripts/).
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
from retrain_pts_v2_opp_features import (  # noqa: E402
    _NEW_OPP_KEYS,
    pts_v2_feature_columns,
)

V2_METRICS_PATH = os.path.join(_MODEL_DIR, "pts_v2_metrics.json")
V2_XGB_PATH        = os.path.join(_MODEL_DIR, "pts_v2_xgb.json")
V2_LGB_PATH        = os.path.join(_MODEL_DIR, "pts_v2_lgb.pkl")
V2_MLP_PATH        = os.path.join(_MODEL_DIR, "pts_v2_mlp.pkl")
V2_MLP_SCALER_PATH = os.path.join(_MODEL_DIR, "pts_v2_mlp_scaler.pkl")
V2_META_PATH       = os.path.join(_MODEL_DIR, "pts_v2_meta.json")


def _shipped() -> bool:
    if not os.path.exists(V2_METRICS_PATH):
        return False
    try:
        with open(V2_METRICS_PATH, encoding="utf-8") as f:
            return bool(json.load(f).get("ship_gate", {}).get("shipped", False))
    except Exception:
        return False


def test_pts_v2_feature_columns_includes_16_new_keys() -> None:
    """pts_v2_feature_columns appends the 16 cycle-99e opp_l5 keys to the
    baseline 85-col feature_columns()."""
    base = feature_columns()
    v2 = pts_v2_feature_columns()
    assert len(v2) == len(base) + 16, (
        f"expected len(base)+16={len(base) + 16}, got {len(v2)}"
    )
    assert set(_NEW_OPP_KEYS).issubset(set(v2))
    # 9 opp_team_<col>_l5 + 7 opp_def_<stat>_l5 = 16
    assert len(_TEAM_ADV_FEATURE_KEYS) == 9
    assert len([k for k in _NEW_OPP_KEYS if k.startswith("opp_def_")
                and k.endswith("_l5")]) == 7
    # All STATS present in the opp_def L5 subset
    for s in STATS:
        assert f"opp_def_{s}_l5" in _NEW_OPP_KEYS


def test_pts_v2_artifacts_persisted_when_shipped() -> None:
    """When ship gate passes, all 5 PTS v2 artifact files must exist."""
    if not _shipped():
        pytest.skip("cycle 100a not shipped (metrics absent or ship_gate=false)")
    for p in (V2_XGB_PATH, V2_LGB_PATH, V2_MLP_PATH,
              V2_MLP_SCALER_PATH, V2_META_PATH):
        assert os.path.exists(p), f"missing v2 artifact: {p}"


def test_pts_v1_production_anchor_still_holds() -> None:
    """v1 PTS production prediction path stays within tolerance of the
    cycle-48 post-haircut anchor 4.6104 — regression guard that the v2
    retrain didn't clobber v1 artifacts."""
    if not os.path.exists(os.path.join(PROJECT_DIR, "data", "nba")):
        pytest.skip("nba gamelog cache missing — fresh checkout")

    import numpy as np

    from src.prediction.prop_pergame import (
        _META_WEIGHTS_FILENAME, _SQRT_HUBER_STATS,
        apply_garbage_time_haircut, build_pergame_dataset,
        load_pergame_model,
    )

    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        pytest.skip("no rows built — gamelog likely empty")
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    y = np.array([float(r["target_pts"]) for r in holdout], dtype=float)

    models = load_pergame_model("pts")
    if not models or len(models) < 2:
        pytest.skip("PTS v1 artifacts missing on disk")

    parts = []
    for entry in models:
        if isinstance(entry, tuple):
            scaler, m = entry
            parts.append(np.clip(m.predict(scaler.transform(X)), 0.0, None) ** 2)
        else:
            parts.append(np.clip(entry.predict(X), 0.0, None) ** 2)
    assert "pts" in _SQRT_HUBER_STATS

    wmap_path = os.path.join(_MODEL_DIR, _META_WEIGHTS_FILENAME)
    with open(wmap_path, encoding="utf-8") as f:
        wmap = json.load(f)
    w = wmap.get("pts", {})
    if len(parts) == 3:
        blend = (float(w.get("w_xgb", 1 / 3)) * parts[0]
                 + float(w.get("w_lgb", 1 / 3)) * parts[1]
                 + float(w.get("w_mlp", 1 / 3)) * parts[2])
    else:
        blend = np.mean(np.column_stack(parts), axis=1)
    blend = np.clip(blend, 0.0, None)
    spreads = [r.get("home_spread") for r in holdout]
    pred = np.array([apply_garbage_time_haircut(float(p), "pts", hs)
                     for p, hs in zip(blend, spreads)], dtype=float)
    mae = float(np.mean(np.abs(pred - y)))
    anchor = 4.6104
    assert abs(mae - anchor) <= 0.02, (
        f"PTS v1 production MAE {mae:.4f} drifted from anchor {anchor:.4f} "
        f"(delta {mae - anchor:+.4f}). v2 retrain shouldn't touch v1."
    )


def test_pts_v2_prediction_in_plausible_range() -> None:
    """A handful of v2 predictions must land in 0..60 (NBA single-game PTS
    floor/ceiling), per ship spec sanity gate."""
    if not _shipped():
        pytest.skip("cycle 100a not shipped (metrics absent or ship_gate=false)")
    if not os.path.exists(os.path.join(PROJECT_DIR, "data", "nba")):
        pytest.skip("nba gamelog cache missing — fresh checkout")

    import joblib
    import numpy as np
    import xgboost as xgb

    from src.prediction.prop_pergame import build_pergame_dataset

    cols_v2 = pts_v2_feature_columns()
    rows, _ = build_pergame_dataset(min_prior=0)
    if not rows:
        pytest.skip("no rows built")
    rows.sort(key=lambda r: r["date"])
    sample = rows[-200:]  # most recent 200 holdout rows
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols_v2]
                  for r in sample], dtype=float)

    xgb_m = xgb.XGBRegressor()
    xgb_m.load_model(V2_XGB_PATH)
    lgb_m = joblib.load(V2_LGB_PATH)
    scaler = joblib.load(V2_MLP_SCALER_PATH)
    mlp_m = joblib.load(V2_MLP_PATH)

    with open(V2_META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    w = meta["weights"]

    def _inv(v):
        return np.clip(v, 0.0, None) ** 2

    pred = (w["w_xgb"] * _inv(xgb_m.predict(X))
            + w["w_lgb"] * _inv(lgb_m.predict(X))
            + w["w_mlp"] * _inv(mlp_m.predict(scaler.transform(X))))
    pred = np.clip(pred, 0.0, None)
    assert pred.min() >= 0.0, f"v2 pts min {pred.min():.2f} < 0"
    assert pred.max() <= 60.0, f"v2 pts max {pred.max():.2f} > 60 (implausible)"
    # Median should sit in a sane NBA PTS range (~5..20 per-game across all
    # players including bench).
    median = float(np.median(pred))
    assert 2.0 <= median <= 30.0, f"v2 pts median {median:.2f} outside 2..30"


def test_pts_v2_wf_single_split_sign_agreement() -> None:
    """If both ship gates pass, the WF mean delta must be negative AND the
    single-split delta must be negative — sign agreement is the ship spec."""
    if not os.path.exists(V2_METRICS_PATH):
        pytest.skip("cycle 100a metrics absent — run retrain script first")
    with open(V2_METRICS_PATH, encoding="utf-8") as f:
        m = json.load(f)
    ss_delta = float(m["single_split"]["delta"])
    wf_mean  = float(m["walk_forward"]["mean_delta"])
    shipped  = bool(m["ship_gate"]["shipped"])
    if shipped:
        # ship spec requires both gates pass — i.e. both deltas negative.
        assert ss_delta < 0.0, (
            f"ship gate says SHIP but single-split delta {ss_delta:+.4f} >= 0"
        )
        assert wf_mean < 0.0, (
            f"ship gate says SHIP but WF mean delta {wf_mean:+.4f} >= 0"
        )
    else:
        # When rejected, at least one gate must explain why.
        ss_ok = bool(m["ship_gate"]["single_split_ok"])
        wf_ok = bool(m["ship_gate"]["walk_forward_ok"])
        assert not (ss_ok and wf_ok), (
            "ship_gate.shipped=false but both single_split_ok and "
            "walk_forward_ok are true — contradiction"
        )
