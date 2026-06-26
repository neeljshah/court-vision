"""Per-file pytest for aci_online.
Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_aci_online.py -q
NEVER run the full suite (freezes the box).
"""
from __future__ import annotations

import math
import pytest
import numpy as np

from scripts.platformkit.ingame.aci_online import (
    aci_update,
    apply_aci_to_band,
    run_aci_stream,
    run_planted_null,
    gate_aci_on_stream,
    _pinball_loss,
    INSUFFICIENT_DATA,
    _DEFAULT_ALPHA_TARGET,
    _DEFAULT_GAMMA,
    _MIN_STREAM_LEN,
)

# ---------------------------------------------------------------------------
# Forbidden field names (no $ / edge / profit signals)
# ---------------------------------------------------------------------------
_FORBIDDEN = {
    "pnl", "roi", "edge", "profit", "dollar", "bankroll", "kelly",
    "wager", "stake", "ev", "expected_value",
}


def _all_keys_recursive(obj, depth: int = 0) -> list:
    """Recursively collect all string keys from nested dicts."""
    if depth > 10:
        return []
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k).lower())
            keys.extend(_all_keys_recursive(v, depth + 1))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys_recursive(item, depth + 1))
    return keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_calibrated_stream(n: int = 1000, sigma: float = 1.0, seed: int = 0):
    """N(0,sigma) y, base band = +/- 1.645*sigma for ~90% coverage."""
    rng = np.random.default_rng(seed)
    y = rng.standard_normal(n) * sigma
    hw = 1.645 * sigma
    base_lo = np.full(n, -hw)
    base_hi = np.full(n, hw)
    return base_lo, base_hi, y


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_aci_update_basic():
    a = 0.10
    # err_t=1 (miss) -> alpha decreases (need more coverage)
    a_miss = aci_update(a, 1, alpha_target=0.10, gamma=0.01)
    assert a_miss < a, f"Expected decrease on miss, got {a_miss}"
    # err_t=0 (hit) -> alpha increases (can afford less coverage)
    a_hit = aci_update(a, 0, alpha_target=0.10, gamma=0.01)
    assert a_hit > a, f"Expected increase on hit, got {a_hit}"


def test_aci_update_clipped():
    # High alpha + hit -> clips at 1.0
    a_up = aci_update(0.99, 0, alpha_target=0.10, gamma=0.50)
    assert a_up <= 1.0
    assert math.isclose(a_up, 1.0, abs_tol=1e-9)
    # Near-zero alpha + miss -> clips at 0.0
    a_down = aci_update(0.001, 1, alpha_target=0.10, gamma=0.50)
    assert a_down >= 0.0
    assert math.isclose(a_down, 0.0, abs_tol=1e-9)


def test_aci_update_rejects_bad_err():
    with pytest.raises(ValueError):
        aci_update(0.10, 0.5)
    with pytest.raises(ValueError):
        aci_update(0.10, 2)


def test_apply_aci_to_band_identity_at_target():
    lo, hi = apply_aci_to_band(-1.0, 1.0, q_static=1.0,
                                alpha_t=0.10, alpha_target=0.10)
    assert math.isclose(lo, -1.0, abs_tol=1e-9)
    assert math.isclose(hi, 1.0, abs_tol=1e-9)


def test_apply_aci_to_band_widens_when_alpha_drops():
    # alpha_t < alpha_target -> need more coverage -> wider band
    lo, hi = apply_aci_to_band(-1.0, 1.0, q_static=1.0,
                                alpha_t=0.05, alpha_target=0.10)
    assert hi - lo > 2.0, f"Expected wider band, got width {hi - lo}"


def test_apply_aci_to_band_narrows_when_alpha_rises():
    # alpha_t > alpha_target -> less coverage needed -> narrower band
    lo, hi = apply_aci_to_band(-1.0, 1.0, q_static=1.0,
                                alpha_t=0.20, alpha_target=0.10)
    assert hi - lo < 2.0, f"Expected narrower band, got width {hi - lo}"


def test_run_aci_stream_basic_coverage():
    base_lo, base_hi, y = _make_calibrated_stream(n=1000, seed=42)
    result = run_aci_stream(base_lo, base_hi, y)
    assert isinstance(result, dict)
    nom = result["nominal_coverage"]
    assert abs(result["aci_coverage"] - nom) <= 0.03, (
        f"ACI coverage {result['aci_coverage']:.3f} more than 3pp from nominal {nom:.3f}"
    )
    assert abs(result["static_coverage"] - nom) <= 0.03, (
        f"Static coverage {result['static_coverage']:.3f} more than 3pp from nominal {nom:.3f}"
    )


def test_run_aci_stream_under_drift_tracks_better():
    """Non-stationary: sigma doubles at tick 500. ACI should adapt, tracking closer to nominal."""
    rng = np.random.default_rng(99)
    n = 2000
    sigma = np.where(np.arange(n) < 500, 1.0, 2.0)
    y = rng.standard_normal(n) * sigma
    # Base band calibrated to sigma=1
    base_lo = np.full(n, -1.645)
    base_hi = np.full(n, 1.645)

    result = run_aci_stream(base_lo, base_hi, y, gamma=0.05)
    assert isinstance(result, dict)
    nom = result["nominal_coverage"]
    aci_gap = abs(result["aci_coverage"] - nom)
    static_gap = abs(result["static_coverage"] - nom)
    assert aci_gap <= static_gap, (
        f"ACI gap {aci_gap:.4f} should be <= static gap {static_gap:.4f} under drift"
    )


def test_run_aci_stream_insufficient_data():
    n = _MIN_STREAM_LEN - 1
    base_lo = np.zeros(n)
    base_hi = np.ones(n)
    y = np.full(n, 0.5)
    result = run_aci_stream(base_lo, base_hi, y)
    assert result == INSUFFICIENT_DATA


def test_run_planted_null_collapses():
    """On a perfectly-stationary calibrated stream, null_collapses=True."""
    base_lo, base_hi, y = _make_calibrated_stream(n=500, seed=7)
    result = run_planted_null(base_lo, base_hi, y)
    assert isinstance(result, dict)
    assert result.get("null_collapses") is True, (
        f"Expected null_collapses=True, got {result.get('null_collapses')}; "
        f"aci_cov={result.get('aci_coverage')}, static_cov={result.get('static_coverage')}, "
        f"alpha_std={np.std(result.get('alpha_trajectory', [0])):.4f}"
    )


def test_gate_aci_on_stream_shape():
    base_lo, base_hi, y = _make_calibrated_stream(n=200, seed=3)
    result = gate_aci_on_stream(base_lo, base_hi, y)
    assert isinstance(result, dict)
    required_keys = {
        "stream_result", "null_result", "ship_recommendation", "honest_note",
    }
    for k in required_keys:
        assert k in result, f"Missing key: {k}"
    ship = result["ship_recommendation"]
    assert ship == "SHIP" or ship.startswith("REJECT:"), f"Bad verdict: {ship}"
    # No forbidden fields anywhere
    all_keys = _all_keys_recursive(result)
    for k in all_keys:
        assert k not in _FORBIDDEN, f"Forbidden field '{k}' found in gate output"


def test_alpha_trajectory_length():
    base_lo, base_hi, y = _make_calibrated_stream(n=100, seed=5)
    result = run_aci_stream(base_lo, base_hi, y)
    assert isinstance(result, dict)
    traj = result["alpha_trajectory"]
    assert len(traj) == len(y) + 1, (
        f"alpha_trajectory length {len(traj)} != {len(y)+1}"
    )


def test_no_forbidden_fields():
    base_lo, base_hi, y = _make_calibrated_stream(n=200, seed=11)
    result = gate_aci_on_stream(base_lo, base_hi, y)
    all_keys = _all_keys_recursive(result)
    bad = [k for k in all_keys if k in _FORBIDDEN]
    assert not bad, f"Forbidden fields found: {bad}"
