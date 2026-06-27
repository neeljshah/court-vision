"""Negative control (c): a collinear-with-base combo REJECTS; an orthogonal one passes."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.combo.combo_base_guard import collinear_with_base_reason

_RNG = np.random.default_rng(7)
_N = 400
_BASE = {
    "shipped_feat_a": _RNG.normal(size=_N),
    "shipped_feat_b": _RNG.normal(size=_N),
}


def test_combo_identical_to_shipped_feature_rejects():
    combo = _BASE["shipped_feat_a"].copy()        # literal re-expression
    reason = collinear_with_base_reason(combo, _BASE)
    assert reason is not None and reason.startswith("collinear_with_base")
    assert "shipped_feat_a" in reason


def test_combo_near_collinear_rejects():
    combo = 3.0 * _BASE["shipped_feat_b"] + 1e-3 * _RNG.normal(size=_N)
    reason = collinear_with_base_reason(combo, _BASE, tau=0.92)
    assert reason is not None and reason.startswith("collinear_with_base")
    assert "shipped_feat_b" in reason


def test_orthogonal_combo_passes():
    combo = _RNG.normal(size=_N)                  # independent of both base cols
    assert collinear_with_base_reason(combo, _BASE, tau=0.92) is None


def test_no_base_features_is_orthogonal_by_default():
    assert collinear_with_base_reason(_RNG.normal(size=_N), {}) is None


def test_constant_combo_is_degenerate_not_a_discovery():
    reason = collinear_with_base_reason(np.full(_N, 0.5), _BASE)
    assert reason is not None and reason.startswith("degenerate_input")


def test_malformed_input_never_raises():
    assert collinear_with_base_reason([], _BASE) is not None
    assert collinear_with_base_reason([np.nan] * 5, {"x": [1.0] * 5}) is not None
    # misaligned base column -> conservative reason, never a raise
    assert collinear_with_base_reason(_RNG.normal(size=_N), {"x": [1.0, 2.0]}) is not None
