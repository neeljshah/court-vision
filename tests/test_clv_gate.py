"""tests/test_clv_gate.py -- R9 C8 CLV-positive ship gate unit tests."""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.improve_loop.clv_gate import (  # noqa: E402
    check_clv_gate,
    compose_with_mae,
    BEAT_RATE_FLOOR,
    MIN_BETS,
    SIZING_CLV_FLOOR,
)


# ── check_clv_gate ───────────────────────────────────────────────────────────

def test_model_change_passes_with_strong_metrics():
    metrics = {
        "beat_rate": 0.55,
        "mean_pct": 0.012,
        "n_bets": 250,
        "wf_folds": [0.02, 0.02, 0.02, 0.02],
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "model")
    assert passed is True, reason
    assert "ok" in reason.lower()


def test_model_change_fails_when_beat_rate_too_low():
    metrics = {
        "beat_rate": 0.49,
        "mean_pct": 0.012,
        "n_bets": 250,
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "model")
    assert passed is False
    assert "beat_rate" in reason and "0.49" in reason


def test_sizing_timing_fails_when_mean_pct_below_one_percent():
    # 0.5% < 1.0% floor
    metrics = {
        "beat_rate": 0.55,
        "mean_pct": 0.005,
        "n_bets": 300,
        "wf_folds": [0.005, 0.005, 0.005, 0.005],
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "sizing_timing")
    assert passed is False
    assert "0.005" in reason or "0.01" in reason
    assert "sizing" in reason.lower() or "<" in reason


def test_sizing_timing_passes_at_strict_bar():
    metrics = {
        "beat_rate": 0.55,
        "mean_pct": 0.015,
        "n_bets": 300,
        "wf_folds": [0.012, 0.014, 0.013, 0.020],
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "sizing_timing")
    assert passed is True, reason


def test_sizing_timing_fails_when_one_wf_fold_negative():
    metrics = {
        "beat_rate": 0.55,
        "mean_pct": 0.015,
        "n_bets": 300,
        "wf_folds": [0.012, 0.014, -0.002, 0.020],  # 3/4 positive
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "sizing_timing")
    assert passed is False
    assert "WF" in reason or "wf" in reason.lower()


def test_model_change_fails_below_min_bets():
    metrics = {
        "beat_rate": 0.60,
        "mean_pct": 0.02,
        "n_bets": 120,
    }
    passed, reason = check_clv_gate({"clv_metrics": metrics}, "model")
    assert passed is False
    assert "120" in reason and str(MIN_BETS) in reason


def test_legacy_probe_passes_through_for_model_change():
    """R0-R8 probes ship no clv_metrics -- they must still be adjudicated by
    MAE alone (CLV returns True with explanatory reason)."""
    passed, reason = check_clv_gate({}, "model")
    assert passed is True
    assert "legacy" in reason.lower() or "unavailable" in reason.lower()

    # Also when key is explicitly None.
    passed2, reason2 = check_clv_gate({"clv_metrics": None}, "model")
    assert passed2 is True
    assert "legacy" in reason2.lower() or "unavailable" in reason2.lower()


def test_legacy_probe_fails_for_sizing_timing():
    """Sizing/timing probes have no MAE signal; missing CLV is fatal."""
    passed, reason = check_clv_gate({}, "sizing_timing")
    assert passed is False
    assert "sizing" in reason.lower() or "unavailable" in reason.lower()


def test_unknown_change_type_fails_closed():
    passed, reason = check_clv_gate({"clv_metrics": {}}, "garbage")
    assert passed is False
    assert "unknown" in reason.lower()


# ── compose_with_mae ─────────────────────────────────────────────────────────

def test_compose_model_requires_both_pass():
    ship, reason = compose_with_mae(True, "MAE ok", True, "CLV ok", "model")
    assert ship is True
    ship, reason = compose_with_mae(True, "MAE ok", False, "CLV fail", "model")
    assert ship is False
    assert "CLV" in reason
    ship, reason = compose_with_mae(False, "MAE fail", True, "CLV ok", "model")
    assert ship is False
    assert "MAE" in reason


def test_compose_sizing_timing_bypasses_mae():
    """sizing_timing ships on CLV alone; MAE verdict is ignored."""
    ship, reason = compose_with_mae(False, "MAE fail (irrelevant)",
                                     True, "CLV ok", "sizing_timing")
    assert ship is True
    assert "sizing_timing" in reason.lower()
    ship, reason = compose_with_mae(True, "MAE ok",
                                     False, "CLV fail", "sizing_timing")
    assert ship is False


def test_feature_change_behaves_like_model():
    ship, _ = compose_with_mae(True, "MAE ok", True, "CLV ok", "feature")
    assert ship is True
    ship, _ = compose_with_mae(True, "MAE ok", False, "CLV fail", "feature")
    assert ship is False
