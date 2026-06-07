"""tests/test_asym_hit_prob.py — H5 fix: asymmetric calibrated band consumed
as a SPLIT-NORMAL hit prob instead of a symmetric Gaussian sigma collapse.

The fix is gated behind CV_ASYM_HIT_PROB (default OFF). These tests assert:

  (a) flag OFF  -> hit prob is BYTE-IDENTICAL to the legacy symmetric formula;
  (b) flag ON, SYMMETRIC band (cal_q10/q90 symmetric about q50) -> equals the
      symmetric result (the split-normal reduces to a Normal);
  (c) flag ON, ASYMMETRIC AST band (upper tail widened) -> P(OVER) at an upper
      line is STRICTLY HIGHER than the symmetric collapse — matching the bug
      analysis (symmetric sigma under-states AST OVER at upper lines).

Both producer scripts (compare_to_lines, backtest_vs_closing_lines) share the
identical split-normal math, so each property is checked on BOTH.
"""
from __future__ import annotations

import os
import sys
from math import erf, sqrt

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, SCRIPTS_DIR)

from scripts import backtest_vs_closing_lines as bvc  # noqa: E402
import compare_to_lines as ctl  # noqa: E402


# ---------------------------------------------------------------------------
# Reference (legacy) symmetric hit prob — the exact formula the OFF path must
# reproduce byte-for-byte. Centred at point_pred, sigma from full 80% width.
# ---------------------------------------------------------------------------
def _legacy_symmetric_p(point_pred, cal_q10, cal_q90, line, side):
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    z = (line - point_pred) / sigma
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf
    return p_over if side == "OVER" else 1 - p_over


def _set_flag(monkeypatch, on: bool):
    if on:
        monkeypatch.setenv("CV_ASYM_HIT_PROB", "1")
    else:
        monkeypatch.delenv("CV_ASYM_HIT_PROB", raising=False)


def _patch_cal(monkeypatch, module, cal_q10, cal_q90):
    """Force apply_quantile_calibration to a known (cal_q10, cal_q90) so the
    test is independent of whatever is in data/models/quantile_calibration.json."""
    monkeypatch.setattr(module, "apply_quantile_calibration",
                        lambda stat, q10, q50, q90: (cal_q10, cal_q90))


# A symmetric envelope (cal band symmetric about q50) — both modules.
_SYM = {"q10": 18.0, "q50": 24.0, "q90": 30.0}      # cal stays symmetric -> 24±6
# An ASYMMETRIC AST band: q50=5, calibrated lower floor near 0, upper widened.
# cal_q10 = 0.5 (q50-0.5 = 4.5 lower half), cal_q90 = 9.5 (4.5 upper half...).
# Make the upper STRICTLY wider than the lower so the asymmetry bites:
_AST_Q = {"q10": 2.0, "q50": 5.0, "q90": 8.0}


# ---------------------------------------------------------------------------
# (a) flag OFF -> byte-identical to the legacy symmetric formula
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [bvc, ctl], ids=["backtest", "compare"])
@pytest.mark.parametrize("point_pred,line,side", [
    (24.0, 22.5, "OVER"),
    (24.0, 27.5, "OVER"),
    (24.0, 22.5, "UNDER"),
    (5.2, 6.5, "OVER"),
    (5.2, 4.5, "UNDER"),
])
def test_off_is_byte_identical_to_symmetric(monkeypatch, module, point_pred, line, side):
    _set_flag(monkeypatch, on=False)
    cal_q10, cal_q90 = 17.0, 31.0     # arbitrary asymmetric *cal* band
    _patch_cal(monkeypatch, module, cal_q10, cal_q90)
    qint = {"q10": 18.0, "q50": 24.0, "q90": 30.0}
    got = module._model_hit_prob("pts", point_pred, qint, line, side)
    want = _legacy_symmetric_p(point_pred, cal_q10, cal_q90, line, side)
    assert got == pytest.approx(want, abs=1e-12), (
        f"{module.__name__}: OFF path must be byte-identical to symmetric formula"
    )


# ---------------------------------------------------------------------------
# (b) flag ON, SYMMETRIC band -> equals the symmetric result
#     (split-normal collapses to a Normal when sigma_lo == sigma_hi).
#     NB: when the cal band is symmetric about q50 AND point_pred == q50, the
#     split-normal centred at q50 must reproduce the legacy symmetric centred at
#     point_pred exactly.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [bvc, ctl], ids=["backtest", "compare"])
@pytest.mark.parametrize("line,side", [
    (22.5, "OVER"), (27.5, "OVER"), (24.0, "OVER"),
    (22.5, "UNDER"), (27.5, "UNDER"),
])
def test_on_symmetric_band_equals_symmetric(monkeypatch, module, line, side):
    _set_flag(monkeypatch, on=True)
    q50 = _SYM["q50"]
    cal_q10, cal_q90 = 18.0, 30.0      # symmetric about q50=24 (±6)
    _patch_cal(monkeypatch, module, cal_q10, cal_q90)
    # point_pred == q50 so the two centers coincide.
    got = module._model_hit_prob("pts", q50, _SYM, line, side)
    want = _legacy_symmetric_p(q50, cal_q10, cal_q90, line, side)
    assert got == pytest.approx(want, abs=1e-9), (
        f"{module.__name__}: ON split-normal on a symmetric band must equal the Normal"
    )


# ---------------------------------------------------------------------------
# (c) flag ON, ASYMMETRIC AST band (upper tail widened) -> P(OVER) at an UPPER
#     line is STRICTLY HIGHER than the symmetric collapse.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [bvc, ctl], ids=["backtest", "compare"])
def test_on_asymmetric_ast_upper_line_raises_p_over(monkeypatch, module):
    q50 = _AST_Q["q50"]                       # 5.0, also use as point_pred
    # Real AST cal is asymmetric: lower floor preserved (~0.5), upper widened.
    cal_q10, cal_q90 = 0.5, 9.5               # lower half 4.5, upper half 4.5? -> widen upper
    # Force a genuinely upper-skewed band: upper half wider than lower half.
    cal_q10, cal_q90 = 2.5, 11.0              # lower half = 2.5, upper half = 6.0
    _patch_cal(monkeypatch, module, cal_q10, cal_q90)
    line = 7.5                                # an UPPER line (above q50=5.0)

    _set_flag(monkeypatch, on=True)
    p_asym = module._model_hit_prob("ast", q50, _AST_Q, line, "OVER")

    _set_flag(monkeypatch, on=False)
    p_sym = module._model_hit_prob("ast", q50, _AST_Q, line, "OVER")

    assert p_asym > p_sym + 1e-4, (
        f"{module.__name__}: asym P(OVER@{line})={p_asym:.4f} must exceed "
        f"symmetric collapse {p_sym:.4f} when the upper tail is widened"
    )
    # And the CDF anchor sanity: at the median P(OVER)=0.5 under the split-normal.
    _set_flag(monkeypatch, on=True)
    p_at_median = module._model_hit_prob("ast", q50, _AST_Q, q50, "OVER")
    assert p_at_median == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Extra: split-normal CDF passes through the calibrated quantiles by design.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [bvc, ctl], ids=["backtest", "compare"])
def test_on_cdf_passes_through_calibrated_quantiles(monkeypatch, module):
    _set_flag(monkeypatch, on=True)
    q50 = 5.0
    cal_q10, cal_q90 = 1.5, 11.0
    _patch_cal(monkeypatch, module, cal_q10, cal_q90)
    qint = {"q10": 2.0, "q50": q50, "q90": 8.0}
    # P(OVER at cal_q10) should be ~0.90 (10% mass below it).
    p_over_at_q10 = module._model_hit_prob("ast", q50, qint, cal_q10, "OVER")
    # P(OVER at cal_q90) should be ~0.10 (90% mass below it).
    p_over_at_q90 = module._model_hit_prob("ast", q50, qint, cal_q90, "OVER")
    assert p_over_at_q10 == pytest.approx(0.90, abs=1e-3)
    assert p_over_at_q90 == pytest.approx(0.10, abs=1e-3)
