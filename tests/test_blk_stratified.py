"""test_blk_stratified.py — cycle 102d ship-script + dispatch smoke tests.

6 tests:
  1. position_bucket classifies coarse / hyphen / unknown inputs correctly.
  2. main() trains, saves, and ships when both gates pass (mocked).
  3. Per-bucket dispatch on a synthetic holdout returns the bucket model's
     prediction (and global model for unknowns).
  4. Position-unknown row falls through to the global model in single_split_eval.
  5. WF and single-split signs are surfaced in the metrics JSON for the bot
     loop to consume.
  6. Spec floor: any bucket below 1000 training rows -> REJECT preflight.

The tests do NOT touch production model artifacts (use tmp_path everywhere)
and do NOT require the full per-game dataset to be built.
"""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_blk_stratified_by_position import (  # noqa: E402
    ALL_BUCKETS, BASELINE_MAE, BUCKET_ARTIFACT, BUCKET_BIG,
    BUCKET_FORWARD, BUCKET_GUARD, MIN_ROWS_PER_BUCKET,
    _blk_params, _bucket_counts, position_bucket,
)


# ── 1. bucket classifier ──────────────────────────────────────────────────────

def test_position_bucket_classification():
    """position_bucket maps every coarse + hybrid string to exactly one
    bucket, with documented precedence: Big > Forward > Guard."""
    # Coarse
    assert position_bucket("Center") == BUCKET_BIG
    assert position_bucket("Forward") == BUCKET_FORWARD
    assert position_bucket("Guard") == BUCKET_GUARD
    # Hybrids → precedence rule
    assert position_bucket("Center-Forward") == BUCKET_BIG  # has "Center"
    assert position_bucket("Forward-Center") == BUCKET_BIG  # has "Center"
    assert position_bucket("Forward-Guard") == BUCKET_FORWARD
    assert position_bucket("Guard-Forward") == BUCKET_FORWARD
    # Unknown / missing
    assert position_bucket(None) is None
    assert position_bucket("") is None
    assert position_bucket("Unknown") is None  # no Center/Forward/Guard token

    # Sanity-check the canonical artifact map.
    assert set(BUCKET_ARTIFACT.keys()) == set(ALL_BUCKETS)
    for path in BUCKET_ARTIFACT.values():
        assert path.endswith(".pkl")
    # _blk_params anchors the cycle-29 recipe — guard against accidental drift.
    p = _blk_params()
    assert p["max_depth"] == 3
    assert p["learning_rate"] == 0.06
    assert p["min_child_weight"] == 25
    assert p["reg_lambda"] == 4.0
    assert p["gamma"] == 0.4
    assert p["colsample_bytree"] == 1.0
    assert p["n_estimators"] == 800


# ── 2. ship-path artifact save (mocked) ───────────────────────────────────────

def test_main_ships_artifacts_when_gates_pass(tmp_path):
    """When BOTH gates PASS, main() persists one .pkl per bucket + metrics JSON."""
    import scripts.retrain_blk_stratified_by_position as mod

    # Synthetic dataset: enough rows in each bucket to clear the preflight
    # MIN_ROWS_PER_BUCKET floor (1000 train rows ≈ 1540 total at 65%).
    n_per_bucket = 2000
    synth_rows = []
    for bucket_pos in ["Center", "Forward", "Guard"]:
        for i in range(n_per_bucket):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_blk": 0.5, "position": bucket_pos,
            })
    # Sort chronologically so the preflight train slice draws from every bucket.
    synth_rows.sort(key=lambda r: r["date"])

    # Mocked eval — skip the expensive LGB fit.
    fake_bucket_models = {b: {"_synthetic_blk_q50": b} for b in ALL_BUCKETS}
    fake_ss = {
        "n_rows": len(synth_rows), "n_train": 4000, "n_val": 900,
        "n_holdout": 1100,
        "mae_global_baseline": 0.45,
        "mae_dispatched": 0.43,
        "delta_mae": -0.02, "mae_vs_cycle27": -0.0098,
        "per_bucket_train_meta": {b: {"n_train": 1300, "n_val": 200,
                                      "trained": True, "skip_reason": None}
                                  for b in ALL_BUCKETS},
        "per_bucket_holdout_mae": {b: 0.43 for b in ALL_BUCKETS},
        "dispatch_counts": {**{b: 350 for b in ALL_BUCKETS},
                            "fallback_global": 50},
        "per_bucket_models": fake_bucket_models,
        "global_model": {"_synthetic_blk_q50": "global"},
    }
    fake_wf = {
        "folds": [{"fold": i, "mae_base": 0.45, "mae_dispatched": 0.43,
                   "delta_mae": -0.02, "bucket_train_meta": {}}
                  for i in range(1, 5)],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.02, "delta_mae_std": 0.0,
    }

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        ret = mod.main()

    assert ret == 0
    for bucket in ALL_BUCKETS:
        artifact = tmp_model_dir / BUCKET_ARTIFACT[bucket]
        assert artifact.exists(), f"missing {bucket} artifact"
    metrics = tmp_model_dir / "blk_q50_stratified_metrics.json"
    assert metrics.exists()
    meta = json.loads(metrics.read_text())
    assert meta["ship"] is True
    assert meta["single_split"]["mae_dispatched"] == 0.43
    assert meta["walk_forward"]["wf_4_of_4_negative"] is True
    assert set(meta["artifacts"].keys()) == set(ALL_BUCKETS)


# ── 3. per-bucket dispatch returns the bucket model's prediction ──────────────

def test_dispatch_routes_each_position_to_correct_model():
    """A tiny single_split_eval over a synthetic dataset where each bucket's
    model returns a distinctive constant verifies per-row dispatch."""
    import scripts.retrain_blk_stratified_by_position as mod

    # Mock _train_lgb_q50 to return models whose .predict() outputs a
    # bucket-specific constant — that way we can verify which model
    # handled which holdout row via the dispatched prediction values.
    class _StubModel:
        def __init__(self, tag: float, n_features: int):
            self._tag = tag
            self.n_features_in_ = n_features

        def predict(self, X):
            # Returns log1p-space constant; the eval inverts via expm1.
            return np.full(len(X), float(self._tag), dtype=float)

    call_counter = {"i": 0}

    def fake_train(X_tr, yt_tr, X_val, yt_val, sw):
        call_counter["i"] += 1
        # 4 fits per single_split: global + big + forward + guard.
        # Use the order of calls to assign tags; mod.single_split_eval calls
        # global first, then per-bucket in ALL_BUCKETS order.
        tag_map = {1: 0.0,  # global LGB-q50 — predicts 0 -> 0.0 raw blocks
                   2: np.log1p(2.0),   # big bucket -> 2.0 raw blocks
                   3: np.log1p(1.0),   # forward    -> 1.0 raw blocks
                   4: np.log1p(0.3)}   # guard      -> 0.3 raw blocks
        return _StubModel(tag_map[call_counter["i"]],
                          n_features=X_tr.shape[1])

    # Synthetic rows: 5000 per bucket + 100 unknown-position rows (route to global).
    synth = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(5000):
            synth.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_blk": 0.5, "position": pos,
            })
    # Append unknown-position rows at the tail so they land in the holdout.
    for i in range(100):
        synth.append({
            "date": f"2025-01-{(i % 28) + 1:02d}",
            "target_blk": 0.5, "position": None,
        })
    synth.sort(key=lambda r: r["date"])
    cols = []  # _build_X with empty cols yields (n, 0) arrays — LGB never sees them

    with mock.patch.object(mod, "_train_lgb_q50", side_effect=fake_train):
        ss = mod.single_split_eval(synth, cols)

    # Each bucket trained
    for bucket in ALL_BUCKETS:
        assert ss["per_bucket_train_meta"][bucket]["trained"]
    # Per-bucket holdout MAE matches the per-bucket constant: target=0.5 so
    # MAE = |0.5 - bucket_pred|. Big=2.0 -> 1.5; Forward=1.0 -> 0.5; Guard=0.3 -> 0.2.
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_BIG]     - 1.5) < 1e-6
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_FORWARD] - 0.5) < 1e-6
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_GUARD]   - 0.2) < 1e-6
    # Unknown-position rows are dispatched to the global model.
    assert ss["dispatch_counts"]["fallback_global"] > 0


# ── 4. unknown-position fallback ──────────────────────────────────────────────

def test_unknown_position_falls_through_to_global():
    """A holdout row with position=None must be routed to the global model
    so dispatch never crashes on missing position metadata."""
    import scripts.retrain_blk_stratified_by_position as mod

    class _StubModel:
        def __init__(self, tag, n_features):
            self._tag = float(tag)
            self.n_features_in_ = n_features

        def predict(self, X):
            return np.full(len(X), self._tag, dtype=float)

    counter = {"i": 0}

    def fake_train(X_tr, yt_tr, X_val, yt_val, sw):
        counter["i"] += 1
        # global=42 (so a global dispatch is unambiguous), buckets all=0.
        tag = np.log1p(42.0) if counter["i"] == 1 else np.log1p(0.0)
        return _StubModel(tag, X_tr.shape[1])

    # Mostly unknown-position rows so the fallback path is exercised.
    synth = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(2000):
            synth.append({"date": f"2023-{(i % 12) + 1:02d}-01",
                          "target_blk": 0.5, "position": pos})
    for i in range(500):
        synth.append({"date": f"2025-06-{(i % 28) + 1:02d}",
                      "target_blk": 0.5, "position": None})
    synth.sort(key=lambda r: r["date"])

    with mock.patch.object(mod, "_train_lgb_q50", side_effect=fake_train):
        ss = mod.single_split_eval(synth, [])

    assert ss["dispatch_counts"]["fallback_global"] > 0
    # Unknown rows dispatched through global which predicts 42 -> MAE for
    # those rows >> 0. (Combined dispatched MAE is dominated by unknown rows
    # since they make up most of the holdout slice given the date sort.)
    assert ss["mae_dispatched"] > 1.0


# ── 5. WF + single-split sign surfaced in metrics ─────────────────────────────

def test_reject_when_wf_fails(tmp_path):
    """Single-split passes but WF only 2/4 negative → REJECT, no .pkl files."""
    import scripts.retrain_blk_stratified_by_position as mod

    synth_rows = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(2000):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_blk": 0.5, "position": pos,
            })
    synth_rows.sort(key=lambda r: r["date"])

    fake_ss = {
        "n_rows": len(synth_rows), "n_train": 4000, "n_val": 900,
        "n_holdout": 1100,
        "mae_global_baseline": 0.45,
        "mae_dispatched": 0.43,
        "delta_mae": -0.02, "mae_vs_cycle27": -0.0098,
        "per_bucket_train_meta": {b: {"n_train": 1300, "n_val": 200,
                                      "trained": True, "skip_reason": None}
                                  for b in ALL_BUCKETS},
        "per_bucket_holdout_mae": {b: 0.43 for b in ALL_BUCKETS},
        "dispatch_counts": {**{b: 350 for b in ALL_BUCKETS},
                            "fallback_global": 50},
        "per_bucket_models": {b: {"_stub": b} for b in ALL_BUCKETS},
        "global_model": {"_stub": "global"},
    }
    # WF: only 2/4 folds improved → fail
    fake_wf = {
        "folds": [{"fold": 1, "mae_base": 0.45, "mae_dispatched": 0.43,
                   "delta_mae": -0.02, "bucket_train_meta": {}},
                  {"fold": 2, "mae_base": 0.45, "mae_dispatched": 0.43,
                   "delta_mae": -0.02, "bucket_train_meta": {}},
                  {"fold": 3, "mae_base": 0.44, "mae_dispatched": 0.46,
                   "delta_mae": +0.02, "bucket_train_meta": {}},
                  {"fold": 4, "mae_base": 0.45, "mae_dispatched": 0.47,
                   "delta_mae": +0.02, "bucket_train_meta": {}}],
        "n_folds": 4, "n_folds_negative": 2, "wf_4_of_4_negative": False,
        "delta_mae_mean": 0.0, "delta_mae_std": 0.02,
    }

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        mod.main()

    metrics = tmp_model_dir / "blk_q50_stratified_metrics.json"
    meta = json.loads(metrics.read_text())
    assert meta["ship"] is False
    assert meta["reason"] == "wf_failed"
    assert meta["walk_forward"]["n_folds_negative"] == 2
    # No bucket artifacts written when ship=False.
    for bucket in ALL_BUCKETS:
        assert not (tmp_model_dir / BUCKET_ARTIFACT[bucket]).exists()


# ── 6. preflight floor ────────────────────────────────────────────────────────

def test_preflight_rejects_when_bucket_below_floor(tmp_path):
    """If any bucket has < MIN_ROWS_PER_BUCKET training rows, main() must
    REJECT before training and write a reason-tagged metrics JSON."""
    import scripts.retrain_blk_stratified_by_position as mod

    # Sparse Centers — only 100 Center rows; Guards and Forwards have plenty.
    synth_rows = []
    for pos, n in [("Center", 100), ("Forward", 2000), ("Guard", 2000)]:
        for i in range(n):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_blk": 0.5, "position": pos,
            })
    synth_rows.sort(key=lambda r: r["date"])

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval") as ss_mock, \
         mock.patch.object(mod, "walk_forward_eval") as wf_mock:
        mod.main()

    # Preflight must fire BEFORE either eval call.
    ss_mock.assert_not_called()
    wf_mock.assert_not_called()

    meta = json.loads((tmp_model_dir / "blk_q50_stratified_metrics.json").read_text())
    assert meta["ship"] is False
    assert f"< floor {MIN_ROWS_PER_BUCKET}" in meta["reason"]
    assert meta["min_rows_per_bucket"] == MIN_ROWS_PER_BUCKET
    assert meta["baseline_cycle27"] == BASELINE_MAE
    # Bucket counts are surfaced so the bot loop can see which bucket starved.
    assert "bucket_counts" in meta
    assert "train_bucket_counts" in meta

    # Helper coverage for _bucket_counts on a known mix.
    counts = _bucket_counts(synth_rows)
    assert counts[BUCKET_BIG] == 100
    assert counts[BUCKET_FORWARD] == 2000
    assert counts[BUCKET_GUARD] == 2000
