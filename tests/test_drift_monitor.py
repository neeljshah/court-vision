"""Tests for drift monitor rolling MAE and prop_model_stack quarantine."""
import json
import os
import sys
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Import compute_rolling_mae directly without triggering streamlit top-level code
import importlib, types, unittest.mock as _mock

# Stub streamlit before importing the dashboard module
_st_stub = types.ModuleType("streamlit")
for _attr in ("set_page_config", "title", "subheader", "info", "success", "warning", "error", "dataframe", "cache_data"):
    setattr(_st_stub, _attr, lambda *a, **kw: None)

# cache_data must be a decorator factory
def _cache_data(ttl=None):
    def _dec(fn):
        return fn
    return _dec
_st_stub.cache_data = _cache_data  # type: ignore[assignment]

sys.modules.setdefault("streamlit", _st_stub)

from apps.dashboards.pages.drift_monitor import compute_rolling_mae


# ── Test 1: empty residuals ───────────────────────────────────────────────────

def test_compute_rolling_mae_empty():
    result = compute_rolling_mae([], "pts", window=30)
    assert result["n"] == 0
    assert result["drift"] is False
    assert result["baseline_mae"] is None
    assert result["window_mae"] is None


# ── Test 2: consistent residuals → no drift ───────────────────────────────────

def test_compute_rolling_mae_no_drift():
    # 60 residuals all perfectly consistent (MAE ~1.0 everywhere)
    residuals = [
        {"stat": "pts", "predicted": 20.0, "actual": 21.0}
        for _ in range(60)
    ]
    result = compute_rolling_mae(residuals, "pts", window=30)
    assert result["n"] == 60
    assert result["drift"] is False
    assert abs(result["baseline_mae"] - 1.0) < 0.01
    assert abs(result["window_mae"] - 1.0) < 0.01


# ── Test 3: inject bad recent predictions → drift detected ────────────────────

def test_compute_rolling_mae_drift_detected():
    # 30 good predictions (MAE = 1.0) followed by 30 bad ones (MAE = 10.0)
    good = [{"stat": "pts", "predicted": 20.0, "actual": 21.0} for _ in range(30)]
    bad  = [{"stat": "pts", "predicted": 20.0, "actual": 30.0} for _ in range(30)]
    residuals = good + bad
    result = compute_rolling_mae(residuals, "pts", window=30)
    assert result["drift"] is True
    # window MAE should be 10.0, baseline ~5.5; 10 > 5.5 * 1.5 = 8.25 → drift
    assert result["window_mae"] > result["baseline_mae"] * 1.5


# ── Test 4: quarantine_stat persists to disk ──────────────────────────────────

def test_quarantine_stat_persists(tmp_path, monkeypatch):
    import src.prediction.prop_model_stack as pms

    q_path = str(tmp_path / "quarantine_state.json")
    monkeypatch.setattr(pms, "_QUARANTINE_PATH", q_path)
    monkeypatch.setattr(pms, "_MODELS_DIR", str(tmp_path))

    pms.quarantine_stat("pts")
    loaded = pms._load_quarantine()
    assert "pts" in loaded


# ── Test 5: stack_predict skips quarantined stat ──────────────────────────────

def test_stack_predict_skips_quarantined(tmp_path, monkeypatch):
    import src.prediction.prop_model_stack as pms

    q_path = str(tmp_path / "quarantine_state.json")
    monkeypatch.setattr(pms, "_QUARANTINE_PATH", q_path)
    monkeypatch.setattr(pms, "_MODELS_DIR", str(tmp_path))

    # Write a quarantine file with 'pts' in it
    with open(q_path, "w") as f:
        json.dump({"quarantined": ["pts"]}, f)

    # Stub out heavy dependencies so stack_predict runs quickly
    monkeypatch.setattr(pms, "_get_dnp_prob", lambda pid: 0.0)
    monkeypatch.setattr(pms, "_get_injury_mult", lambda pid: 1.0)
    monkeypatch.setattr(pms, "_collect_micro_signals", lambda pid, gc: {
        "rest_mult": 1.0, "travel_adj": 1.0, "altitude_adj": 1.0,
        "home_away_adj": 1.0, "shot_type_mult": 1.0,
        "b2b_pts": 1.0, "b2b_reb": 1.0, "b2b_ast": 1.0,
        "starter_prob": 0.9, "garbage_time_prob": 0.0, "foul_out_prob": 0.0,
        "expected_min": 30.0, "proj_usg_pct": 0.25,
    })
    monkeypatch.setattr(pms, "_load_motivation_flags", lambda pid: {})
    monkeypatch.setattr(pms, "_get_cohort_calibrator", lambda: None)

    # Stub predict_props to return simple values
    with _mock.patch("src.prediction.player_props.predict_props", return_value={
        "pts": 20.0, "reb": 5.0, "ast": 4.0,
        "fg3m": 2.0, "stl": 1.0, "blk": 0.5, "tov": 2.0,
        "player_name": "Test Player",
    }):
        result = pms.stack_predict("2544", game_context={"season": "2025-26"})

    # pts should be None/suppressed; other stats should have predictions
    assert result.predictions.get("pts") is None
    assert result.confidence.get("pts") == 0.0
    # at least one non-quarantined stat should have a real prediction
    non_q_preds = [v for k, v in result.predictions.items() if k != "pts" and v is not None]
    assert len(non_q_preds) > 0
