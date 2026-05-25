"""test_pts_stratified.py — cycle 104e PTS stratified-by-position ship-script tests.

6 tests mirror the BLK 102d test suite, adapted for PTS sqrt+Huber blend:
  1. position_bucket classification + artifact map shape.
  2. main() persists 3 head files (xgb/lgb/mlp/mlp_scaler) per bucket on SHIP.
  3. Sample inference per position returns the correct dispatch.
  4. Position-unknown rows fall through to the global model.
  5. WF + single-split signs surfaced in metrics JSON.
  6. Preflight: any bucket below MIN_ROWS_PER_BUCKET → REJECT, no artifacts.

Uses tmp_path for all writes — production artifacts never touched.
"""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_pts_stratified_by_position import (  # noqa: E402
    ALL_BUCKETS, BASELINE_MAE, BUCKET_ARTIFACTS, BUCKET_BIG,
    BUCKET_FORWARD, BUCKET_GUARD, MIN_ROWS_PER_BUCKET,
    _bucket_counts, _pts_params, position_bucket,
)


# ── 1. bucket classifier + artifact map ──────────────────────────────────────

def test_position_bucket_and_artifact_map():
    assert position_bucket("Center") == BUCKET_BIG
    assert position_bucket("Forward") == BUCKET_FORWARD
    assert position_bucket("Guard") == BUCKET_GUARD
    assert position_bucket("Center-Forward") == BUCKET_BIG
    assert position_bucket("Forward-Center") == BUCKET_BIG
    assert position_bucket("Forward-Guard") == BUCKET_FORWARD
    assert position_bucket("Guard-Forward") == BUCKET_FORWARD
    assert position_bucket(None) is None
    assert position_bucket("") is None
    assert position_bucket("Unknown") is None

    # Each bucket has 4 artifact files (xgb json + lgb pkl + mlp pkl + scaler pkl).
    assert set(BUCKET_ARTIFACTS.keys()) == set(ALL_BUCKETS)
    for bucket, files in BUCKET_ARTIFACTS.items():
        assert set(files.keys()) == {"xgb", "lgb", "mlp", "mlp_scaler"}
        assert files["xgb"].endswith(".json")
        for k in ("lgb", "mlp", "mlp_scaler"):
            assert files[k].endswith(".pkl")
        assert bucket in files["xgb"]

    # Anchor cycle-18 PTS params — guard against drift.
    p = _pts_params()
    assert p["max_depth"] == 6
    assert p["learning_rate"] == 0.025
    assert p["n_estimators"] == 800
    assert p["min_child_weight"] == 20
    assert p["reg_lambda"] == 4.0


# ── 2. ship path persists 4 head files per bucket ────────────────────────────

class _StubXGB:
    """XGB stub with save_model() returning a tiny json file."""
    def save_model(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("{\"stub\": true}")

    def predict(self, X):
        return np.zeros(len(X), dtype=float)


class _StubModel:
    def __init__(self, tag=0.0):
        self._tag = float(tag)

    def predict(self, X):
        return np.full(len(X), self._tag, dtype=float)


class _StubScaler:
    """Picklable identity scaler stub."""
    def transform(self, X):
        return X

    def fit_transform(self, X):
        return X


def _stub_art(tag=0.0):
    """Build a fake (xgb, lgb, scaler, mlp, wx, wl, wm) tuple."""
    return (_StubXGB(), _StubModel(tag), _StubScaler(), _StubModel(tag),
            1.0, 0.0, 0.0)


def test_main_ships_and_persists_per_bucket(tmp_path):
    import scripts.retrain_pts_stratified_by_position as mod

    # Enough rows in each bucket to clear MIN_ROWS_PER_BUCKET preflight.
    n_per = 9000
    synth_rows = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(n_per):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_pts": 12.0, "position": pos,
            })
    synth_rows.sort(key=lambda r: r["date"])

    fake_artifacts = {b: _stub_art() for b in ALL_BUCKETS}
    fake_ss = {
        "n_rows": len(synth_rows), "n_train": 17500, "n_val": 4050,
        "n_holdout": 5400,
        "mae_global_baseline": 4.65,
        "mae_dispatched": 4.55,
        "delta_mae": -0.10, "mae_vs_anchor": 4.55 - BASELINE_MAE,
        "per_bucket_train_meta": {b: {"n_train": 5800, "n_val": 900,
                                      "trained": True, "skip_reason": None}
                                  for b in ALL_BUCKETS},
        "per_bucket_holdout_mae": {b: 4.55 for b in ALL_BUCKETS},
        "dispatch_counts": {**{b: 1700 for b in ALL_BUCKETS},
                            "fallback_global": 100},
        "per_bucket_artifacts": fake_artifacts,
        "global_artifact": _stub_art(),
    }
    fake_wf = {
        "folds": [{"fold": i, "mae_base": 4.65, "mae_dispatched": 4.55,
                   "delta_mae": -0.10, "bucket_train_meta": {}}
                  for i in range(1, 5)],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.10, "delta_mae_std": 0.0,
    }

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "_MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        ret = mod.main()

    assert ret == 0
    # 4 files per bucket.
    for bucket in ALL_BUCKETS:
        for k, fname in BUCKET_ARTIFACTS[bucket].items():
            assert (tmp_model_dir / fname).exists(), f"missing {bucket}/{k}"
    meta = json.loads((tmp_model_dir / "pts_stratified_metrics.json").read_text())
    assert meta["ship"] is True
    assert meta["single_split"]["mae_dispatched"] == 4.55
    assert meta["walk_forward"]["wf_4_of_4_negative"] is True
    assert set(meta["artifacts"].keys()) == set(ALL_BUCKETS)
    # NNLS weights are surfaced in the persisted metadata for the bot loop.
    for bucket in ALL_BUCKETS:
        for k in ("w_xgb", "w_lgb", "w_mlp"):
            assert k in meta["artifacts"][bucket]


# ── 3. dispatch routes each position to correct model ────────────────────────

def test_dispatch_routes_each_position_to_correct_model():
    import scripts.retrain_pts_stratified_by_position as mod

    # _train_blend stub returns bucket-specific constant in sqrt space.
    call_counter = {"i": 0}

    def fake_train(X_tr, y_tr, X_val, y_val, sw):
        call_counter["i"] += 1
        # Order: global, then per-bucket in ALL_BUCKETS order.
        # sqrt -> _inv_sqrt -> raw points
        raw_targets = {1: 10.0, 2: 25.0, 3: 18.0, 4: 12.0}
        raw = raw_targets[call_counter["i"]]
        tag = np.sqrt(raw)
        scaler = mock.MagicMock()
        scaler.transform = lambda X: X
        scaler.fit_transform = lambda X: X
        return (_StubModel(tag), _StubModel(tag), scaler, _StubModel(tag),
                1.0, 0.0, 0.0)

    synth = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(9000):
            synth.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_pts": 15.0, "position": pos,
            })
    synth.sort(key=lambda r: r["date"])

    with mock.patch.object(mod, "_train_blend", side_effect=fake_train):
        ss = mod.single_split_eval(synth, cols=[])

    for bucket in ALL_BUCKETS:
        assert ss["per_bucket_train_meta"][bucket]["trained"]
    # Per-bucket MAE: target=15.0 → |15 - bucket_pred|
    # Big=25 → 10; Forward=18 → 3; Guard=12 → 3
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_BIG]     - 10.0) < 1e-4
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_FORWARD] -  3.0) < 1e-4
    assert abs(ss["per_bucket_holdout_mae"][BUCKET_GUARD]   -  3.0) < 1e-4


# ── 4. unknown-position fallback ─────────────────────────────────────────────

def test_unknown_position_falls_through_to_global():
    import scripts.retrain_pts_stratified_by_position as mod

    counter = {"i": 0}

    def fake_train(X_tr, y_tr, X_val, y_val, sw):
        counter["i"] += 1
        # global predicts 50 raw points (very wrong vs target 15) so we can
        # detect unknowns being dispatched through it.
        raw = 50.0 if counter["i"] == 1 else 15.0
        tag = np.sqrt(raw)
        scaler = mock.MagicMock()
        scaler.transform = lambda X: X
        scaler.fit_transform = lambda X: X
        return (_StubModel(tag), _StubModel(tag), scaler, _StubModel(tag),
                1.0, 0.0, 0.0)

    synth = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(9000):
            synth.append({"date": f"2023-{(i % 12) + 1:02d}-01",
                          "target_pts": 15.0, "position": pos})
    # Tail rows with unknown position → land in holdout, route to global.
    for i in range(1500):
        synth.append({"date": f"2025-06-{(i % 28) + 1:02d}",
                      "target_pts": 15.0, "position": None})
    synth.sort(key=lambda r: r["date"])

    with mock.patch.object(mod, "_train_blend", side_effect=fake_train):
        ss = mod.single_split_eval(synth, cols=[])

    assert ss["dispatch_counts"]["fallback_global"] > 0
    # Combined dispatched MAE pulled up by unknown rows hitting global=50.
    assert ss["mae_dispatched"] > 5.0


# ── 5. WF + single-split signs surfaced in metrics JSON on reject ────────────

def test_reject_when_wf_fails_emits_signs(tmp_path):
    import scripts.retrain_pts_stratified_by_position as mod

    synth_rows = []
    for pos in ["Center", "Forward", "Guard"]:
        for i in range(9000):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_pts": 12.0, "position": pos,
            })
    synth_rows.sort(key=lambda r: r["date"])

    fake_ss = {
        "n_rows": len(synth_rows), "n_train": 17500, "n_val": 4050,
        "n_holdout": 5400,
        "mae_global_baseline": 4.65,
        "mae_dispatched": 4.60,  # passes single-split (< 4.6210)
        "delta_mae": -0.05, "mae_vs_anchor": 4.60 - BASELINE_MAE,
        "per_bucket_train_meta": {b: {"n_train": 5800, "n_val": 900,
                                      "trained": True, "skip_reason": None}
                                  for b in ALL_BUCKETS},
        "per_bucket_holdout_mae": {b: 4.60 for b in ALL_BUCKETS},
        "dispatch_counts": {**{b: 1700 for b in ALL_BUCKETS},
                            "fallback_global": 100},
        "per_bucket_artifacts": {b: _stub_art() for b in ALL_BUCKETS},
        "global_artifact": _stub_art(),
    }
    # WF: only 2/4 folds improved → fail.
    fake_wf = {
        "folds": [
            {"fold": 1, "mae_base": 4.7, "mae_dispatched": 4.6, "delta_mae": -0.1,
             "bucket_train_meta": {}},
            {"fold": 2, "mae_base": 4.7, "mae_dispatched": 4.6, "delta_mae": -0.1,
             "bucket_train_meta": {}},
            {"fold": 3, "mae_base": 4.6, "mae_dispatched": 4.7, "delta_mae": +0.1,
             "bucket_train_meta": {}},
            {"fold": 4, "mae_base": 4.6, "mae_dispatched": 4.7, "delta_mae": +0.1,
             "bucket_train_meta": {}},
        ],
        "n_folds": 4, "n_folds_negative": 2, "wf_4_of_4_negative": False,
        "delta_mae_mean": 0.0, "delta_mae_std": 0.1,
    }

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "_MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        mod.main()

    meta = json.loads((tmp_model_dir / "pts_stratified_metrics.json").read_text())
    assert meta["ship"] is False
    assert meta["reason"] == "wf_failed"
    assert meta["walk_forward"]["n_folds_negative"] == 2
    assert meta["single_split"]["mae_dispatched"] == 4.60
    # Back-compat: no bucket artifacts written when ship=False.
    for bucket in ALL_BUCKETS:
        for fname in BUCKET_ARTIFACTS[bucket].values():
            assert not (tmp_model_dir / fname).exists()


# ── 6. preflight floor (back-compat: missing stratified -> global) ───────────

def test_preflight_rejects_when_bucket_below_floor(tmp_path):
    import scripts.retrain_pts_stratified_by_position as mod

    # Only 200 Center rows — far below MIN_ROWS_PER_BUCKET (5000) floor.
    synth_rows = []
    for pos, n in [("Center", 200), ("Forward", 9000), ("Guard", 9000)]:
        for i in range(n):
            synth_rows.append({
                "date": f"2024-{(i % 12) + 1:02d}-{((i // 12) % 28) + 1:02d}",
                "target_pts": 12.0, "position": pos,
            })
    synth_rows.sort(key=lambda r: r["date"])

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "_MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval") as ss_mock, \
         mock.patch.object(mod, "walk_forward_eval") as wf_mock:
        mod.main()

    # Preflight fires BEFORE either eval call → back-compat: production uses
    # existing global heads, no stratified artifacts produced.
    ss_mock.assert_not_called()
    wf_mock.assert_not_called()

    meta = json.loads((tmp_model_dir / "pts_stratified_metrics.json").read_text())
    assert meta["ship"] is False
    assert f"< floor {MIN_ROWS_PER_BUCKET}" in meta["reason"]
    assert meta["min_rows_per_bucket"] == MIN_ROWS_PER_BUCKET
    assert meta["baseline_anchor"] == BASELINE_MAE
    assert "bucket_counts" in meta
    assert "train_bucket_counts" in meta
    # No artifact files written.
    for bucket in ALL_BUCKETS:
        for fname in BUCKET_ARTIFACTS[bucket].values():
            assert not (tmp_model_dir / fname).exists()

    # _bucket_counts sanity check.
    counts = _bucket_counts(synth_rows)
    assert counts[BUCKET_BIG] == 200
    assert counts[BUCKET_FORWARD] == 9000
    assert counts[BUCKET_GUARD] == 9000
