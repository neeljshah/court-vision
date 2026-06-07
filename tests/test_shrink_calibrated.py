"""tests/test_shrink_calibrated.py -- W-016 (CV_SHRINK_CALIBRATED).

Tests for the calibrated time-remaining shrinkage weight curve:
  l5floor:12:0.30 = linear:12 with a hard floor w <= 0.30 when mp < 5.

Test plan:
 1. Flag OFF -> _live_shrink_weight is byte-identical to the sigmoid:14:4 baseline.
 2. Flag ON -> curve is linear:12 (w = min(1, mp/12)), confirmed at several mp values.
 3. Flag ON + mp < 5 -> live weight is capped at 0.30 (early-safety floor).
 4. Flag ON + mp == 0 -> returns 0.0 (no-activity guard).
 5. Flag ON + mp = None -> returns 0.0.
 6. Flag ON + mp = 12 -> returns 1.0 (linear fully reaches pure-live at T=12).
 7. Flag ON + mp = 24 -> returns 1.0 (already at or past full weight).
 8. Flag OFF vs ON comparison at mp=14 (sigmoid center): flag-OFF != flag-ON, confirming
    the curve actually changes when ON.
 9. Flag ON + mp = 3 -> floor is active; weight == 0.25 capped to 0.30 -> 0.25.
    (3/12 = 0.25 which is already <= 0.30, so no cap effect; floor only bites when
    linear would exceed 0.30, i.e. mp between 3.6 and 5.0.)
10. Flag ON + mp = 4 -> linear = 4/12 = 0.333 > 0.30 => capped to 0.30.
11. Flag ON + mp = 5 -> linear = 5/12 = 0.4167 > 0.30 but mp == 5.0 is NOT < 5 =>
    floor does NOT apply; w = 0.4167.
12. Flag ON + mp = 6 -> linear = 0.50; floor not active.
13. Byte-identical-OFF check: run with CV_SHRINK_CALIBRATED unset vs explicitly "0",
    confirm both match pure sigmoid (no env contamination).
14. CV_SHRINK_CALIBRATED="off" (case-insensitive) -> treated as OFF, sigmoid returned.
15. CV_SHRINK_CALIBRATED="false" -> treated as OFF.
"""
from __future__ import annotations

import importlib
import math
import os
import sys
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Load the function directly by importing the module.  We patch os.environ on the
# module side to avoid cross-test state leakage.
import api.courtvision_router as _router  # noqa: E402

_live_shrink_weight = _router._live_shrink_weight


# ── helpers ──────────────────────────────────────────────────────────────────

def _sigmoid_14_4(mp: float) -> float:
    """Baseline production curve sigmoid:14:4."""
    if mp is None or mp <= 0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-(mp - 14.0) / 4.0))


def _linear12_floor030(mp: float) -> float:
    """Expected l5floor:12:0.30 curve (reference implementation for tests)."""
    if mp is None or mp <= 0:
        return 0.0
    w = min(1.0, mp / 12.0)
    if mp < 5.0:
        w = min(w, 0.30)
    return w


def _call_with_flag(mp, flag_value):
    """Call _live_shrink_weight with CV_SHRINK_CALIBRATED set to flag_value."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CV_SHRINK_CALIBRATED", "CV_INGAME_L5_ANCHOR")}
    if flag_value is not None:
        env["CV_SHRINK_CALIBRATED"] = flag_value
    with mock.patch.dict(os.environ, env, clear=True):
        return _live_shrink_weight(mp)


def _call_flag_off(mp):
    return _call_with_flag(mp, None)


def _call_flag_on(mp):
    return _call_with_flag(mp, "1")


# ── test 1: flag-OFF is byte-identical to sigmoid:14:4 ───────────────────────

class TestFlagOffByteIdentical:
    """With CV_SHRINK_CALIBRATED unset, output must match sigmoid:14:4 exactly."""

    def test_mp_4(self):
        assert _call_flag_off(4.0) == _sigmoid_14_4(4.0)

    def test_mp_14(self):
        assert _call_flag_off(14.0) == _sigmoid_14_4(14.0)

    def test_mp_24(self):
        assert _call_flag_off(24.0) == _sigmoid_14_4(24.0)

    def test_mp_36(self):
        assert _call_flag_off(36.0) == _sigmoid_14_4(36.0)

    def test_mp_0(self):
        assert _call_flag_off(0.0) == 0.0

    def test_mp_none(self):
        assert _call_flag_off(None) == 0.0


# ── test 2-12: flag-ON uses l5floor:12:0.30 ──────────────────────────────────

class TestFlagOnCalibratedCurve:
    """With flag ON, the curve must match l5floor:12:0.30."""

    def test_mp_0_returns_zero(self):
        assert _call_flag_on(0.0) == 0.0

    def test_mp_none_returns_zero(self):
        assert _call_flag_on(None) == 0.0

    def test_mp_3_below_floor_no_cap_needed(self):
        # 3/12 = 0.25 < 0.30 => floor does not bite; returns 0.25
        w = _call_flag_on(3.0)
        assert abs(w - 0.25) < 1e-9, f"expected 0.25, got {w}"

    def test_mp_4_floor_bites(self):
        # 4/12 = 0.333... > 0.30 and mp < 5 => cap to 0.30
        w = _call_flag_on(4.0)
        assert abs(w - 0.30) < 1e-9, f"expected 0.30 (cap), got {w}"

    def test_mp_4p5_floor_bites(self):
        # 4.5/12 = 0.375 > 0.30 and mp < 5 => cap to 0.30
        w = _call_flag_on(4.5)
        assert abs(w - 0.30) < 1e-9, f"expected 0.30 (cap), got {w}"

    def test_mp_5_floor_does_not_bite(self):
        # mp == 5.0 is NOT < 5.0 => floor condition does not apply
        # 5/12 = 0.4167
        w = _call_flag_on(5.0)
        expected = 5.0 / 12.0
        assert abs(w - expected) < 1e-9, f"expected {expected}, got {w}"

    def test_mp_6_linear_half(self):
        w = _call_flag_on(6.0)
        assert abs(w - 0.5) < 1e-9, f"expected 0.5, got {w}"

    def test_mp_12_reaches_one(self):
        w = _call_flag_on(12.0)
        assert abs(w - 1.0) < 1e-9, f"expected 1.0, got {w}"

    def test_mp_24_stays_one(self):
        w = _call_flag_on(24.0)
        assert abs(w - 1.0) < 1e-9, f"expected 1.0 (clamped), got {w}"

    def test_flag_on_differs_from_flag_off_at_mp14(self):
        # sigmoid:14:4 at mp=14 is 0.5; l5floor at mp=14 is min(1, 14/12) = 1.0
        w_off = _call_flag_off(14.0)
        w_on = _call_flag_on(14.0)
        assert w_on != w_off, (
            f"flag-ON and flag-OFF must differ at mp=14 (off={w_off:.4f} on={w_on:.4f})"
        )
        # Specifically ON should be 1.0 and OFF should be 0.5
        assert abs(w_on - 1.0) < 1e-9, f"flag-ON at mp=14 should be 1.0, got {w_on}"
        assert abs(w_off - 0.5) < 1e-9, f"flag-OFF at mp=14 should be 0.5, got {w_off}"

    def test_reference_implementation_matches(self):
        """flag-ON output must match the reference l5floor:12:0.30 at many mp values."""
        for mp in (0.0, 1.0, 2.0, 3.0, 3.6, 4.0, 4.9, 5.0, 6.0, 8.0, 10.0,
                   12.0, 15.0, 24.0, 36.0):
            w = _call_flag_on(mp)
            expected = _linear12_floor030(mp)
            assert abs(w - expected) < 1e-9, (
                f"mp={mp}: expected {expected:.6f}, got {w:.6f}"
            )


# ── test 13-15: off-value variants treated as OFF ────────────────────────────

class TestFlagOffVariants:
    """Various falsy flag values must all behave like OFF (sigmoid:14:4)."""

    def test_explicit_zero(self):
        w = _call_with_flag(14.0, "0")
        assert abs(w - _sigmoid_14_4(14.0)) < 1e-9

    def test_empty_string(self):
        w = _call_with_flag(14.0, "")
        assert abs(w - _sigmoid_14_4(14.0)) < 1e-9

    def test_false_string(self):
        w = _call_with_flag(14.0, "false")
        assert abs(w - _sigmoid_14_4(14.0)) < 1e-9

    def test_off_string(self):
        w = _call_with_flag(14.0, "off")
        assert abs(w - _sigmoid_14_4(14.0)) < 1e-9

    def test_off_string_uppercase(self):
        w = _call_with_flag(14.0, "OFF")
        assert abs(w - _sigmoid_14_4(14.0)) < 1e-9

    def test_on_string_activates(self):
        # "on" is not in the off-list => treated as ON => calibrated curve fires
        w = _call_with_flag(14.0, "on")
        assert abs(w - 1.0) < 1e-9, f"flag='on' should activate calibrated curve at mp=14, got {w}"
