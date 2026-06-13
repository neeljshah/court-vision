"""tests/platform/test_recal_board.py — unit tests for the board recalibration glue.

All synthetic (MagicMock bundles) — NO parquet, NO adapter loads, NO slow paths.
Covers: recal applied when n > min_history · passthrough tag when n <= min_history ·
output in [0,1] · warmup passthrough · leak-free (flipping FUTURE outcomes does not
change a current calibrated value) · NaN raw passes through · tag is never the bare
lie "calibrated" · end-to-end MagicMock bundle.

HONESTY: calibration != edge.  These tests assert the tag is honest, not that the
recalibration confers any betting edge.

Run:  python -m pytest tests/platform/test_recal_board.py -q
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from scripts.platformkit.frontend.recal_board import (
    recalibrate_signal,
    recalibrated_board_rows,
)


def _make_bundle(n: int, *, seed: int = 7, raw=None, target=None) -> MagicMock:
    """MagicMock feature bundle — mirrors the fixture in tests/platform/test_board.py."""
    rng = np.random.default_rng(seed)
    b = MagicMock()
    b.signal_col = rng.uniform(0.30, 0.70, size=n) if raw is None else np.asarray(raw, float)
    b.target = (
        rng.integers(0, 2, size=n).astype(float) if target is None else np.asarray(target, float)
    )
    b.dates = [f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]
    return b


# --------------------------------------------------------------------------- #
# tag behaviour
# --------------------------------------------------------------------------- #


def test_recal_applied_when_n_gt_min_history():
    bundle = _make_bundle(100)
    cal, tag = recalibrated_board_rows("basketball_nba", bundle, min_history=50)
    assert tag == "recalibrated"
    assert len(cal) == 100


def test_passthrough_tag_when_n_le_min_history():
    raw = np.linspace(0.1, 0.9, 30)  # all in [0,1] so clip is a no-op
    bundle = _make_bundle(30, raw=raw)
    cal, tag = recalibrated_board_rows("basketball_nba", bundle, min_history=50)
    assert tag == "raw"
    assert np.array_equal(cal, raw)  # cal == raw exactly


def test_tag_never_bare_calibrated():
    for n in (10, 30, 51, 100, 200):
        _, tag = recalibrated_board_rows("basketball_nba", _make_bundle(n), min_history=50)
        assert tag in {"recalibrated", "raw"}
        assert tag != "calibrated"


# --------------------------------------------------------------------------- #
# value behaviour
# --------------------------------------------------------------------------- #


def test_output_in_0_1():
    # Deliberately miscalibrated raw values (some <0, some >1) -> must be clipped.
    raw = np.concatenate([
        np.full(60, -0.5),
        np.full(60, 1.7),
    ])
    y = np.concatenate([np.zeros(60), np.ones(60)])
    cal = recalibrate_signal(raw, y, min_history=50)
    # Ignore warmup passthrough (which preserves the raw out-of-range values);
    # the recalibrated tail must be bounded.
    tail = cal[50:]
    assert float(np.nanmin(tail)) >= 0.0
    assert float(np.nanmax(tail)) <= 1.0


def test_warmup_passthrough():
    raw = np.clip(np.random.default_rng(1).uniform(0.0, 1.0, 120), 0.0, 1.0)
    y = np.random.default_rng(2).integers(0, 2, 120).astype(float)
    cal = recalibrate_signal(raw, y, min_history=50)
    assert np.array_equal(cal[:50], raw[:50])  # warmup rows pass through unchanged


def test_flip_future_outcomes_no_change():
    """Leak-free proof: changing outcomes AFTER min_history cannot move cal[min_history]."""
    mh = 50
    rng = np.random.default_rng(3)
    raw = rng.uniform(0.1, 0.9, 120)
    base = rng.integers(0, 2, 120).astype(float)
    a = base.copy()
    b = base.copy()
    b[mh:] = 1.0 - b[mh:]  # differ ONLY in the future of index mh
    cal_a = recalibrate_signal(raw, a, min_history=mh)
    cal_b = recalibrate_signal(raw, b, min_history=mh)
    assert abs(cal_a[mh] - cal_b[mh]) < 1e-12


def test_nan_raw_passes_through():
    mh = 50
    rng = np.random.default_rng(4)
    raw = rng.uniform(0.1, 0.9, 120)
    y = rng.integers(0, 2, 120).astype(float)
    k = 80  # a recalibrated index (> min_history)
    raw[k] = np.nan
    cal = recalibrate_signal(raw, y, min_history=mh)  # must not crash
    assert np.isnan(cal[k])


# --------------------------------------------------------------------------- #
# end-to-end
# --------------------------------------------------------------------------- #


def test_end_to_end_magicmock_bundle():
    bundle = _make_bundle(120)
    cal, tag = recalibrated_board_rows("basketball_nba", bundle)
    assert len(cal) == 120
    assert tag == "recalibrated"
