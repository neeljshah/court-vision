"""tests/test_R30_W1_m2_retrain.py — R30_W1 third-attempt retrain guards.

Six checks (>=5 required by spec):
  1. all 20 m2_family artifacts loadable
  2. predictions reproducible byte-for-byte from the same fitted ensemble
  3. R20_M7 wire still active in src/prediction/game_models.py
  4. _predict_m2_family returns no NaN values when artifacts present
  5. probe results JSON, if present, has the schema downstream code expects
  6. predictions for a known plausible-game feature row land in expected magnitude
"""
from __future__ import annotations

import json
import math
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "models")) else PROJECT_DIR


_ROOT_DIR = _resolve_root()
_M2_DIR = os.path.join(_ROOT_DIR, "data", "models", "m2_family")
_MANIFEST = os.path.join(_M2_DIR, "manifest.json")
_FEAT_COLS = os.path.join(_M2_DIR, "feature_cols.json")
_RESULTS = os.path.join(_ROOT_DIR, "data", "cache", "probe_R30_W1_results.json")

_LGB_SEEDS = (42, 7, 100)
_XGB_SEEDS = (42, 7)
_TARGETS = ("total", "spread", "home_pts", "away_pts")


def _artifacts_present() -> bool:
    return os.path.exists(_MANIFEST) and os.path.exists(_FEAT_COLS)


# ── Test 1 — all 20 artifacts loadable ─────────────────────────────────────
def test_all_twenty_artifacts_loadable():
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent (fresh worktree clone)")
    import joblib  # noqa: PLC0415
    n_loaded = 0
    for tgt in _TARGETS:
        for seed in _LGB_SEEDS:
            p = os.path.join(_M2_DIR, f"{tgt}_lgb_s{seed}.joblib")
            assert os.path.exists(p), f"missing artifact: {p}"
            m = joblib.load(p)
            assert hasattr(m, "predict"), f"loaded {p} lacks .predict"
            n_loaded += 1
        for seed in _XGB_SEEDS:
            p = os.path.join(_M2_DIR, f"{tgt}_xgb_s{seed}.joblib")
            assert os.path.exists(p), f"missing artifact: {p}"
            m = joblib.load(p)
            assert hasattr(m, "predict"), f"loaded {p} lacks .predict"
            n_loaded += 1
    assert n_loaded == 20, f"expected 20 artifacts, loaded {n_loaded}"


# ── Test 2 — predictions reproducible from the same fitted model ────────────
def test_predictions_reproducible():
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent")
    import joblib  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    with open(_FEAT_COLS, encoding="utf-8") as f:
        feats = json.load(f)
    rng = np.random.default_rng(123)
    X = rng.normal(0, 1, size=(5, len(feats))).astype("float32")
    m = joblib.load(os.path.join(_M2_DIR, "total_lgb_s42.joblib"))
    p1 = m.predict(X)
    p2 = m.predict(X)
    assert (p1 == p2).all(), ".predict not deterministic — artifact corrupted"


# ── Test 3 — R20_M7 wire still active in game_models.py ─────────────────────
def test_R20_M7_wire_still_active():
    p = os.path.join(PROJECT_DIR, "src", "prediction", "game_models.py")
    if not os.path.exists(p):
        p = os.path.join(_ROOT_DIR, "src", "prediction", "game_models.py")
    assert os.path.exists(p), "game_models.py missing entirely"
    with open(p, encoding="utf-8") as f:
        src = f.read()
    assert "_predict_m2_family" in src, "R20_M7 _predict_m2_family helper gone"
    assert "m2_family_used" in src, "R20_M7 m2_family_used flag/output gone"
    assert "total_est" in src and "spread_est" in src, (
        "predict() no longer exposes total_est / spread_est"
    )


# ── Test 4 — no NaN predictions when artifacts present ─────────────────────
def test_no_nan_predictions_when_artifacts_present(monkeypatch):
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent")
    from src.prediction import game_models  # noqa: PLC0415

    monkeypatch.setattr(game_models, "_M2_FAMILY_DIR", _M2_DIR)
    monkeypatch.setattr(game_models, "_M2_FAMILY_CACHE", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_FEATS", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_MANIFEST", None)

    if not game_models._try_load_m2_family():
        pytest.skip("m2_family failed to load")

    row = {
        "home_off_rtg": 115.0, "home_def_rtg": 112.0, "home_pace": 100.0,
        "away_off_rtg": 113.0, "away_def_rtg": 114.0, "away_pace": 99.0,
        "home_net_rtg": 3.0, "away_net_rtg": -1.0,
        "net_rtg_diff": 4.0, "pace_diff": 1.0, "home_advantage": 1.0,
        "home_efg_pct": 0.55, "away_efg_pct": 0.54,
        "home_ts_pct": 0.58,  "away_ts_pct": 0.57,
        "home_tov_pct": 0.13, "away_tov_pct": 0.14,
        "home_rest_days": 1,  "away_rest_days": 2,
        "home_back_to_back": 0, "away_back_to_back": 0,
        "home_last5_wins": 3, "away_last5_wins": 2,
        "home_season_win_pct": 0.55, "away_season_win_pct": 0.50,
        "game_id": "RA_R30W1_TEST_GID",
    }
    out = game_models._predict_m2_family(row, game_id="RA_R30W1_TEST_GID")
    assert out is not None, "predict returned None despite artifacts loaded"
    for key in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        v = out.get(key)
        assert v is not None, f"missing key {key}"
        assert not math.isnan(float(v)), f"NaN prediction for {key}: {v}"
        assert math.isfinite(float(v)), f"non-finite prediction for {key}: {v}"
    game_models.clear_m2_pred_cache()


# ── Test 5 — probe results JSON schema ─────────────────────────────────────
def test_R30_W1_results_json_schema_when_present():
    if not os.path.exists(_RESULTS):
        pytest.skip("probe_R30_W1_results.json not yet generated")
    with open(_RESULTS, encoding="utf-8") as f:
        data = json.load(f)
    required_top = {
        "probe", "decision", "runtime_min",
        "n_train_rows", "n_val_rows_2025_26",
        "per_target_mae_old", "per_target_mae_new", "per_target_delta_pct",
        "per_target_wf_folds_positive",
        "n_targets_improving", "worst_regress_pct",
        "wf_folds_passing", "wf_full_pass_targets",
    }
    missing = required_top - set(data.keys())
    assert not missing, f"results.json missing keys: {missing}"
    assert data["decision"] in ("SHIP", "REJECT"), (
        f"decision must be SHIP or REJECT, got {data['decision']!r}"
    )
    for t in _TARGETS:
        assert t in data["per_target_mae_new"], f"target {t} missing from mae_new"
        assert t in data["per_target_wf_folds_positive"], (
            f"target {t} missing from wf_folds_positive"
        )
        wf_pos = data["per_target_wf_folds_positive"][t]
        assert isinstance(wf_pos, int) and 0 <= wf_pos <= 4, (
            f"wf_folds_positive[{t}] must be int in [0,4], got {wf_pos!r}"
        )


# ── Test 6 — predictions for a known game land in plausible magnitude ──────
def test_known_game_predictions_in_expected_magnitude(monkeypatch):
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent")
    from src.prediction import game_models  # noqa: PLC0415

    monkeypatch.setattr(game_models, "_M2_FAMILY_DIR", _M2_DIR)
    monkeypatch.setattr(game_models, "_M2_FAMILY_CACHE", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_FEATS", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_MANIFEST", None)
    if not game_models._try_load_m2_family():
        pytest.skip("m2_family failed to load")

    # Strong home favourite vs weak away — predict skew positive spread + reasonable total.
    row = {
        "home_off_rtg": 120.0, "home_def_rtg": 108.0, "home_pace": 102.0,
        "away_off_rtg": 110.0, "away_def_rtg": 116.0, "away_pace": 100.0,
        "home_net_rtg": 12.0, "away_net_rtg": -6.0,
        "net_rtg_diff": 18.0, "pace_diff": 2.0, "home_advantage": 1.0,
        "home_efg_pct": 0.57, "away_efg_pct": 0.52,
        "home_ts_pct": 0.60,  "away_ts_pct": 0.54,
        "home_tov_pct": 0.12, "away_tov_pct": 0.15,
        "home_rest_days": 2,  "away_rest_days": 0,
        "home_back_to_back": 0, "away_back_to_back": 1,
        "home_last5_wins": 4, "away_last5_wins": 1,
        "home_season_win_pct": 0.70, "away_season_win_pct": 0.35,
        "game_id": "RA_R30W1_KNOWN_GAME",
    }
    out = game_models._predict_m2_family(row, game_id="RA_R30W1_KNOWN_GAME")
    assert out is not None
    total = float(out["total_est"])
    spread = float(out["spread_est"])
    home_pts = float(out["home_pts_est"])
    away_pts = float(out["away_pts_est"])

    # NBA totals: 200..260 plausible.
    assert 180 <= total <= 280, f"total_est out of NBA range: {total}"
    # spread should lean home (positive) given big positive net_rtg_diff
    assert spread > 0, f"strong home favourite should have positive spread, got {spread}"
    # home and away pts plausible
    assert 90 <= home_pts <= 150, f"home_pts_est out of range: {home_pts}"
    assert 85 <= away_pts <= 140, f"away_pts_est out of range: {away_pts}"
    # consistency: home_pts + away_pts approximately equals total (within small ensemble noise)
    assert abs((home_pts + away_pts) - total) < 30, (
        f"home_pts + away_pts ({home_pts + away_pts}) far from total ({total})"
    )
    game_models.clear_m2_pred_cache()
