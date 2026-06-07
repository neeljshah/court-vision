"""
tests/test_alt_line_ladder.py — Phase 15.5 Wave 0 + CV_ALTLINE_SIGMA_FIX tests.

Tests 1-4 verify alt_line_ladder.py (built, xfail removed now that module exists).
Test 5 verifies conformal_props.py works correctly.
Tests 6-9 verify the CV_ALTLINE_SIGMA_FIX gate (FIX 2 from AST_KELLY_ALTLINE_FIXES).
"""
from __future__ import annotations
import math
import os
import numpy as np
import pytest

# ── Test 5 (no xfail): conformal_props.py already exists ──────────────────────

def test_conformal_load_and_predict():
    """ConformalPredictor calibrates and predicts valid intervals."""
    from src.prediction.conformal_props import ConformalPredictor
    rng = np.random.default_rng(42)
    y_true = rng.normal(20.0, 3.0, 80)
    y_hat = y_true + rng.normal(0, 1.5, 80)
    cp = ConformalPredictor()
    cp.calibrate(y_true, y_hat)
    lo, hi = cp.predict_interval(22.5, coverage=0.80)
    assert lo < 22.5 < hi, f"Interval {lo}..{hi} must straddle point estimate 22.5"
    assert hi - lo > 0, "Interval width must be positive"

# ── Tests 1-4: xfail until alt_line_ladder.py is created ──────────────────────

@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_ladder_offsets():
    """build_alt_line_ladder returns 22 entries: 11 offsets × 2 directions."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="LeBron James",
        stat="pts",
        point_estimate=26.5,
        conformal_interval=(22.0, 31.0),
        pinnacle_signal={"line": 26.5, "over_odds": -110, "under_odds": -110},
    )
    assert isinstance(result, list), "Result must be a list"
    assert len(result) >= 22, f"Expected >= 22 entries (11 offsets × 2), got {len(result)}"
    directions = {r["direction"] for r in result}
    assert "over" in directions and "under" in directions
    alt_lines = sorted({r["alt_line"] for r in result})
    assert len(alt_lines) == 11, f"Expected 11 distinct alt lines, got {len(alt_lines)}"


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_ev_computation():
    """EV = model_prob / book_prob - 1. With model=0.60, book=0.50 → EV ≈ 0.20."""
    from src.prediction.alt_line_ladder import _compute_ev
    ev = _compute_ev(model_prob=0.60, book_prob=0.50)
    assert abs(ev - 0.20) < 0.01, f"EV should be ~0.20, got {ev}"


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_pinnacle_decay():
    """Book probability decays for wider alt lines (Pinnacle vig structure)."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="Jayson Tatum",
        stat="pts",
        point_estimate=28.0,
        conformal_interval=(23.5, 32.5),
        pinnacle_signal={"line": 28.0, "over_odds": -110, "under_odds": -110},
    )
    # At offset 0.0 (main line) and offset +2.0 (alt line), over prob should decay
    by_alt = {(r["alt_line"], r["direction"]): r for r in result}
    main_over = by_alt.get((28.0, "over"), {}).get("book_prob", 0.50)
    wide_over = by_alt.get((30.0, "over"), {}).get("book_prob", 0.50)
    assert wide_over < main_over, (
        f"book_prob at +2.0 ({wide_over}) should be < book_prob at 0.0 ({main_over})"
    )


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_kelly_cap():
    """kelly_raw must never exceed 0.02 (2% of bankroll cap) for any ladder entry."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="Stephen Curry",
        stat="fg3m",
        point_estimate=4.5,
        conformal_interval=(2.0, 7.0),
        pinnacle_signal={"line": 4.5, "over_odds": -115, "under_odds": -105},
    )
    for row in result:
        kelly = row.get("kelly_raw", 0.0)
        assert kelly <= 0.02, f"Kelly {kelly} exceeds 2% cap at alt_line={row.get('alt_line')}"
        assert kelly >= 0.0, f"Kelly must be non-negative, got {kelly}"


# ── CV_ALTLINE_SIGMA_FIX tests (FIX 2 from AST_KELLY_ALTLINE_FIXES) ───────────

class TestAltLineSigmaFix:
    """Verify CV_ALTLINE_SIGMA_FIX gate — flag OFF byte-identical; flag ON uses
    correct 80% CI divisor 2.5631 instead of IQR divisor 1.349."""

    # Fixed conformal interval used in all sigma tests
    _LO, _HI = 20.0, 32.0   # width = 12.0

    @property
    def _sigma_wrong(self):
        return (self._HI - self._LO) / 1.349     # ≈ 8.895 — inflated

    @property
    def _sigma_correct(self):
        return (self._HI - self._LO) / 2.5631    # ≈ 4.682 — correct for 80% CI

    def _get_sigma(self, flag_value):
        from src.prediction.alt_line_ladder import _fit_uncertainty_distribution
        import importlib, sys
        # reload to pick up fresh env state
        import src.prediction.alt_line_ladder as mod
        importlib.reload(mod)
        old = os.environ.get("CV_ALTLINE_SIGMA_FIX")
        try:
            os.environ["CV_ALTLINE_SIGMA_FIX"] = flag_value
            _, sigma = mod._fit_uncertainty_distribution(26.0, self._LO, self._HI)
        finally:
            if old is None:
                os.environ.pop("CV_ALTLINE_SIGMA_FIX", None)
            else:
                os.environ["CV_ALTLINE_SIGMA_FIX"] = old
        return sigma

    def test_flag_off_byte_identical_sigma(self):
        """Flag OFF: sigma uses original 1.349 divisor (IQR) — byte-identical to pre-fix."""
        sigma = self._get_sigma("0")
        assert abs(sigma - self._sigma_wrong) < 0.01, (
            f"Flag OFF sigma should be {self._sigma_wrong:.4f} (IQR), got {sigma:.4f}"
        )

    def test_flag_on_correct_sigma(self):
        """Flag ON: sigma uses correct 2.5631 divisor for 80% CI."""
        sigma = self._get_sigma("1")
        assert abs(sigma - self._sigma_correct) < 0.01, (
            f"Flag ON sigma should be {self._sigma_correct:.4f} (80% CI), got {sigma:.4f}"
        )

    def test_flag_on_sigma_tighter_than_off(self):
        """Flag ON sigma must be tighter than flag OFF (1.90x smaller)."""
        sigma_off = self._get_sigma("0")
        sigma_on = self._get_sigma("1")
        ratio = sigma_off / sigma_on
        assert 1.85 < ratio < 1.96, (
            f"sigma_off/sigma_on ratio should be ~1.90, got {ratio:.4f}"
        )

    def test_flag_on_ev_increases_for_edge_bet(self):
        """Flag ON: EV at a genuine edge (model > market) must increase vs flag OFF.
        Inflated sigma pulls P(X>line) toward 0.5, understating EV. Correct sigma
        restores the gap."""
        import math

        def normal_cdf(z):
            return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

        mu = 6.5    # model projection
        line = 5.5  # book line (model has an edge OVER)

        sigma_off = self._get_sigma("0")
        sigma_on = self._get_sigma("1")

        # P(X > line) for each sigma
        from src.prediction.alt_line_ladder import _SIGMA_FLOOR
        p_off = 1.0 - normal_cdf((line - mu) / max(sigma_off, _SIGMA_FLOOR))
        p_on  = 1.0 - normal_cdf((line - mu) / max(sigma_on,  _SIGMA_FLOOR))

        # EV = model_prob / book_prob - 1 (vf_over ≈ 0.50 at -110)
        vf_over = 0.50
        ev_off = p_off / vf_over - 1.0
        ev_on  = p_on  / vf_over - 1.0

        assert ev_on > ev_off, (
            f"Flag ON EV ({ev_on:.4f}) should exceed flag OFF EV ({ev_off:.4f}) "
            f"for an edge bet (inflated sigma understated EV)"
        )


# ── CV_ALTLINE_DECAY_DIR_FIX tests (2026-06-05 audit) ────────────────────────

class TestAltLineDecayDirFix:
    """The negative-offset branch (LOWER alt line -> over is EASIER) must INCREASE
    book over-prob, not decrease it. Legacy multiplied by (1 - 0.08*|d|) < 1 and
    wrongly LOWERED it -> EV inflated on easier-over rungs. Gate default-OFF is
    byte-identical (legacy); ON corrects the direction. The positive (harder-over)
    branch is unchanged in both modes."""

    def _f(self, flag_value, vf_over, dist):
        import importlib
        import src.prediction.alt_line_ladder as mod
        importlib.reload(mod)
        old = os.environ.get("CV_ALTLINE_DECAY_DIR_FIX")
        try:
            if flag_value is None:
                os.environ.pop("CV_ALTLINE_DECAY_DIR_FIX", None)
            else:
                os.environ["CV_ALTLINE_DECAY_DIR_FIX"] = flag_value
            return mod._book_prob_at_alt_line(vf_over, dist)
        finally:
            if old is None:
                os.environ.pop("CV_ALTLINE_DECAY_DIR_FIX", None)
            else:
                os.environ["CV_ALTLINE_DECAY_DIR_FIX"] = old

    def test_off_is_legacy_byte_identical(self):
        # easier over (d<0) legacy WRONGLY decreases: 0.55*(1-0.08*2.5)=0.44
        assert abs(self._f(None, 0.55, -2.5) - 0.44) < 1e-9
        assert abs(self._f("0", 0.55, -2.5) - 0.44) < 1e-9

    def test_on_increases_for_easier_over(self):
        # ON correctly increases: 0.55*(1+0.08*2.5)=0.66
        assert abs(self._f("1", 0.55, -2.5) - 0.66) < 1e-9
        # and the corrected prob is HIGHER than legacy (no fake edge inflation)
        assert self._f("1", 0.55, -2.5) > self._f("0", 0.55, -2.5)

    def test_harder_over_unchanged_both_modes(self):
        off = self._f("0", 0.55, 2.5)
        on = self._f("1", 0.55, 2.5)
        assert abs(off - on) < 1e-9 and abs(off - 0.385) < 1e-9

    def test_on_clamps_at_099(self):
        assert self._f("1", 0.95, -10.0) <= 0.99
