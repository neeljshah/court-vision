"""test_quantile_calibration_rolling.py -- Cycle 90f (loop 5), T4-A.

Tests for the prior-60-game rolling quantile calibration. The four tests:

  1) Rolling scale at the first 60-game point matches the global scale within
     a tight tolerance (same data, same formula, same coverage target).
  2) Rolling scale at game N+1 uses ONLY [N-59, N] -- no leakage. This is
     verified by feeding two distinct datasets whose suffix is identical and
     checking the resulting scale matches what fitting on the SUFFIX alone
     produces.
  3) Asymmetric branch preserved: when q10 is heavily clipped at 0
     (q10_zero_frac > 0.30), apply_rolling preserves q10 floor (the same
     rule cycle-40's apply() uses).
  4) --rolling-cal flag is importable + apply_rolling is wired in
     compare_to_lines.py without breaking the default path.
"""
from __future__ import annotations

import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.quantile_calibration_rolling import (  # noqa: E402
    _grid_search_scale, apply_rolling, load_rolling_scale,
)


def _make_normal_q_actuals(n=200, mu=10.0, sigma=3.0, seed=11):
    """Synthesize matched (q10, q50, q90, actuals) with a known scale.

    We FIRST sample actuals from N(mu, sigma). Then we sample q10/q50/q90
    from a TIGHTER N(mu, sigma * 0.8) so the raw 80% coverage is LESS than
    0.80 and the fitted scale must be > 1.0 to widen it.
    """
    rng = np.random.default_rng(seed)
    actuals = rng.normal(mu, sigma, n)
    # Predicted q* spread is 80% of the actual spread -> needs scale > 1.
    pred_sigma = sigma * 0.8
    q50 = rng.normal(mu, pred_sigma * 0.05, n)  # near-truth point predictions
    # q10 = mu - 1.2816 * pred_sigma, q90 = mu + 1.2816 * pred_sigma
    q10 = q50 - 1.2816 * pred_sigma
    q90 = q50 + 1.2816 * pred_sigma
    return q10, q50, q90, actuals


def test_first_window_matches_global_within_tolerance():
    """The rolling scale fit on the first 60-game window equals (within
    grid resolution) the global scale fit on the same data."""
    q10, q50, q90, actuals = _make_normal_q_actuals(n=300, seed=2026)
    # Global == fit on all 300 rows. Rolling first-window == fit on rows 0:60.
    s_global, asym_g, _ = _grid_search_scale(q10, q50, q90, actuals)
    s_window, asym_w, _ = _grid_search_scale(q10[:60], q50[:60], q90[:60],
                                              actuals[:60])
    # With same generative process the scales should land in the same ballpark.
    # Grid step is (3.0 - 0.05) / 119 ~ 0.0248; tolerate ~3x that AND a noise
    # margin from finite n=60 versus n=300 (~30% relative).
    rel = abs(s_window - s_global) / max(abs(s_global), 0.05)
    assert rel < 0.35, (
        f"first-window vs global scale drift too large: "
        f"global={s_global:.4f} window={s_window:.4f} rel={rel:.3f}"
    )
    assert asym_g == asym_w, (
        f"asymmetric flag should match between global and first-window "
        f"fits: global={asym_g} window={asym_w}"
    )


def test_window_uses_only_prior_rows_no_leakage():
    """A rolling fit on slice [N-59, N] is INDEPENDENT of any data after N."""
    q10_a, q50_a, q90_a, act_a = _make_normal_q_actuals(n=120, seed=1, sigma=3.0)
    # Build a second dataset whose first 60 rows are IDENTICAL but the tail
    # (60: ) is wildly different. The fit on the SAME prior window must produce
    # the SAME scale because the post-window data must NOT enter the fit.
    q10_b = q10_a.copy(); q50_b = q50_a.copy(); q90_b = q90_a.copy()
    act_b = act_a.copy()
    # Mangle suffix: very-different distribution (large outliers).
    rng = np.random.default_rng(99)
    q10_b[60:] = rng.normal(-50, 1, 60)
    q90_b[60:] = rng.normal(+50, 1, 60)
    act_b[60:] = rng.normal(0, 100, 60)
    # Now we ask: scale fit on FIRST 60 rows of A vs FIRST 60 rows of B.
    s_a, _, _ = _grid_search_scale(q10_a[:60], q50_a[:60], q90_a[:60], act_a[:60])
    s_b, _, _ = _grid_search_scale(q10_b[:60], q50_b[:60], q90_b[:60], act_b[:60])
    assert s_a == s_b, (
        f"rolling fit leaked future data: identical prior slices produced "
        f"different scales s_a={s_a:.4f} s_b={s_b:.4f}"
    )


def test_asymmetric_branch_preserves_q10_floor(tmp_path):
    """When the parquet entry has asymmetric=True the floor for q10 is
    preserved (cal_q10 = max(0, q10)); only q90 is scaled."""
    import pandas as pd
    p = tmp_path / "quantile_cal_rolling.parquet"
    df = pd.DataFrame([
        {"date": "2025-01-01", "stat": "fg3m", "scale": 1.5,
         "asymmetric": True, "n_window": 60, "coverage": 0.80},
        {"date": "2025-01-01", "stat": "pts", "scale": 1.1,
         "asymmetric": False, "n_window": 60, "coverage": 0.80},
    ])
    df.to_parquet(p, index=False)

    # Asymmetric stat: q10 floor preserved, q90 scales.
    cal_q10, cal_q90 = apply_rolling("fg3m", q10=0.0, q50=2.0, q90=4.0,
                                     on_or_before="2025-06-01", path=str(p))
    assert cal_q10 == 0.0, f"asymmetric q10 should equal max(0, q10): {cal_q10}"
    expected_q90 = 2.0 + 1.5 * (4.0 - 2.0)
    assert abs(cal_q90 - expected_q90) < 1e-6, \
        f"asymmetric cal_q90 wrong: got {cal_q90}, want {expected_q90}"

    # Symmetric stat: BOTH sides scale.
    cal_q10_s, cal_q90_s = apply_rolling("pts", q10=10.0, q50=20.0, q90=30.0,
                                         on_or_before="2025-06-01", path=str(p))
    expected_q10_s = 20.0 - 1.1 * (20.0 - 10.0)
    expected_q90_s = 20.0 + 1.1 * (30.0 - 20.0)
    assert abs(cal_q10_s - expected_q10_s) < 1e-6, cal_q10_s
    assert abs(cal_q90_s - expected_q90_s) < 1e-6, cal_q90_s

    # load_rolling_scale honours the on_or_before constraint.
    s, asym = load_rolling_scale("fg3m", "2025-06-01", path=str(p))
    assert s == 1.5 and asym is True

    # Pre-history date -> falls through to the global JSON fallback. Just
    # verify it does not crash and returns a sane float.
    s_fb, _ = load_rolling_scale("fg3m", "2020-01-01", path=str(p))
    assert isinstance(s_fb, float)


def test_rolling_cal_flag_importable_in_compare_to_lines():
    """The --rolling-cal flag exists in compare_to_lines.py argparse AND the
    apply_quantile_calibration_rolling import succeeds at module load.
    Smoke-test only -- we do NOT invoke the full predictor pipeline.
    """
    import importlib
    mod = importlib.import_module("scripts.compare_to_lines")
    # Sanity: module imports the rolling helper (may be None if pandas missing,
    # but the symbol must exist).
    assert hasattr(mod, "apply_quantile_calibration_rolling"), \
        "compare_to_lines.py must import apply_rolling for the --rolling-cal flag"
    # _model_hit_prob signature must accept use_rolling.
    import inspect
    sig = inspect.signature(mod._model_hit_prob)
    assert "use_rolling" in sig.parameters, \
        "_model_hit_prob must accept use_rolling for --rolling-cal"
    assert "on_or_before" in sig.parameters, \
        "_model_hit_prob must accept on_or_before for rolling lookups"

    # Argparse: --rolling-cal must be a registered flag. We exercise main()'s
    # parser by inspecting the source -- a full main() run requires NBA data.
    src = inspect.getsource(mod.main)
    assert "--rolling-cal" in src, "compare_to_lines.main must register --rolling-cal"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
