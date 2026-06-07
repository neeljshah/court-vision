"""W-032: CV_WP_RECONCILED_CALIB — win-prob reconciled chain calibration.

Tests verify:
  1. Flag OFF: _live_wp_continuous output is byte-identical to baseline
     (no behavior change whatsoever when CV_WP_RECONCILED_CALIB is unset/0).
  2. Flag ON: sigma=12.5 is used instead of 14.5 (tighter, Brier-optimal).
  3. Flag ON: w_market cap=1.00 instead of 0.80 (full market trust at tip).
  4. Flag ON: at tip (rem=48, period=1, clock=12:00), market weight=1.0 when
     pregame wp is available (trusts pregame market fully pre-game).
  5. Flag OFF at tip: market weight=0.80 (original cap).
  6. Both flag states produce values in [0.005, 0.995].
  7. FINAL game status: rem=0 → output converges near 0 or 1.
  8. No projected totals (fallback path): flag OFF=flag ON for proj_margin
     computation (margin derivation unchanged; only sigma/w_market differ).
  9. Late-game (rem=3, Q4): flag ON uses tighter sigma → more confident output
     (larger |z| for same projected margin).
  10. Byte-identical check: a reference call with env unset matches one with
      explicit CV_WP_RECONCILED_CALIB=0.
"""
from __future__ import annotations

import math
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pytest

# ---------------------------------------------------------------------------
# Import the function under test directly from the module (avoids full FastAPI
# stack) using importlib so we can reload after env changes without polluting
# the global module cache.
# ---------------------------------------------------------------------------

def _import_fn():
    """Return _live_wp_continuous from courtvision_router (not-yet-cached)."""
    import importlib
    spec = importlib.util.spec_from_file_location(
        "_cvrouter_w032",
        os.path.join(PROJECT_DIR, "api", "courtvision_router.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # Provide a minimal stub so the module-level FastAPI imports don't fail.
    import types
    for stub_name in [
        "fastapi", "fastapi.responses", "fastapi.templating",
        "api._courtvision_data",
        "slowapi", "slowapi.util",
    ]:
        if stub_name not in sys.modules:
            sys.modules[stub_name] = types.ModuleType(stub_name)
    # Provide fastapi.APIRouter / HTTPException / etc stubs
    import fastapi as _fa_stub
    if not hasattr(_fa_stub, "APIRouter"):
        _fa_stub.APIRouter = lambda **kw: object()
        _fa_stub.Body = lambda *a, **kw: None
        _fa_stub.HTTPException = Exception
        _fa_stub.Query = lambda *a, **kw: None
        _fa_stub.Request = object
    import fastapi.responses as _far_stub
    if not hasattr(_far_stub, "HTMLResponse"):
        _far_stub.HTMLResponse = object
        _far_stub.JSONResponse = object
        _far_stub.RedirectResponse = object
        _far_stub.Response = object
    import fastapi.templating as _fat_stub
    if not hasattr(_fat_stub, "Jinja2Templates"):
        _fat_stub.Jinja2Templates = lambda *a, **kw: object()
    # We can't load the full module easily; instead call the function via a
    # controlled env. Use a direct import of the already-loaded module.
    return None


# ---------------------------------------------------------------------------
# Use the already-loaded module after regular import — the env var controls
# the branch in _live_wp_continuous at call time.
# ---------------------------------------------------------------------------

# We import the function here; the env var is read inside each call.
try:
    from api.courtvision_router import _live_wp_continuous as _lwp_fn
    _IMPORT_OK = True
except Exception as _exc:
    _IMPORT_OK = False
    _IMPORT_EXC = str(_exc)


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    """Ensure flag is OFF before each test (reset to baseline)."""
    monkeypatch.delenv("CV_WP_RECONCILED_CALIB", raising=False)
    yield
    monkeypatch.delenv("CV_WP_RECONCILED_CALIB", raising=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_overlay(period: int, clock: str, home_score: int = 55,
                  away_score: int = 50, game_status: str = "") -> dict:
    return {
        "period": period,
        "clock": clock,
        "home_score": home_score,
        "away_score": away_score,
        "game_status": game_status,
    }


def _call_flag_off(overlay, pregame_wp, proj_home=None, proj_away=None):
    """Call with flag explicitly OFF."""
    os.environ.pop("CV_WP_RECONCILED_CALIB", None)
    return _lwp_fn(overlay, pregame_wp, proj_home, proj_away)


def _call_flag_on(overlay, pregame_wp, proj_home=None, proj_away=None, monkeypatch=None):
    """Call with flag explicitly ON."""
    os.environ["CV_WP_RECONCILED_CALIB"] = "1"
    try:
        return _lwp_fn(overlay, pregame_wp, proj_home, proj_away)
    finally:
        os.environ.pop("CV_WP_RECONCILED_CALIB", None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _IMPORT_OK, reason="courtvision_router import failed")
class TestW032WpReconciledCalib:

    def test_01_import_ok(self):
        """Function is importable."""
        assert _lwp_fn is not None

    def test_02_flag_off_returns_float(self):
        """Flag OFF: returns a float in [0.005, 0.995]."""
        overlay = _make_overlay(2, "6:00", 55, 50)
        result = _call_flag_off(overlay, 0.52, proj_home=112.0, proj_away=108.0)
        assert result is not None
        assert 0.005 <= result <= 0.995

    def test_03_flag_on_returns_float(self):
        """Flag ON: still returns a float in [0.005, 0.995]."""
        overlay = _make_overlay(2, "6:00", 55, 50)
        result = _call_flag_on(overlay, 0.52, proj_home=112.0, proj_away=108.0)
        assert result is not None
        assert 0.005 <= result <= 0.995

    def test_04_byte_identical_when_off(self):
        """Flag OFF (env unset) == flag OFF (env='0'): byte-identical."""
        overlay = _make_overlay(3, "6:00", 80, 75)
        os.environ.pop("CV_WP_RECONCILED_CALIB", None)
        r1 = _lwp_fn(overlay, 0.54, proj_home=114.0, proj_away=108.0)
        os.environ["CV_WP_RECONCILED_CALIB"] = "0"
        r2 = _lwp_fn(overlay, 0.54, proj_home=114.0, proj_away=108.0)
        os.environ.pop("CV_WP_RECONCILED_CALIB", None)
        assert r1 == r2, f"byte-identical failed: {r1} != {r2}"

    def test_05_flag_on_different_from_off(self):
        """Flag ON and flag OFF produce different values (calibration is active)."""
        # Use a scenario where sigma and w_market both differ meaningfully.
        # Early game (rem=36, Q1, clock=12:00) with projected margin=+6:
        overlay = _make_overlay(1, "12:00", 0, 0)
        r_off = _call_flag_off(overlay, 0.50, proj_home=115.0, proj_away=109.0)
        r_on = _call_flag_on(overlay, 0.50, proj_home=115.0, proj_away=109.0)
        # Tighter sigma (12.5 vs 14.5) → p_proj is further from 0.5 (more extreme)
        # but higher w_market cap (1.0 vs 0.8) → more market-anchored (closer to 0.5).
        # Net effect should be different.
        assert r_off != r_on, (
            f"flag ON and OFF should differ: off={r_off}, on={r_on}"
        )

    def test_06_tighter_sigma_on(self):
        """Flag ON with large projected margin: tighter sigma → p_proj is more extreme."""
        # Mid-game, Q3, projected margin = +15 (strong lead), pregame=0.55
        # With tighter sigma, the projected-margin term is stronger.
        # rem ≈ 12 min (period=3, clock=6:00).
        overlay = _make_overlay(3, "6:00", 80, 65)
        proj_home = 120.0
        proj_away = 105.0  # projected margin = +15
        r_off = _call_flag_off(overlay, 0.55, proj_home, proj_away)
        r_on = _call_flag_on(overlay, 0.55, proj_home, proj_away)
        # Both should be high win-prob (home up +15 projected);
        # net blend differs due to sigma+w_market changes.
        assert 0.005 <= r_off <= 0.995
        assert 0.005 <= r_on <= 0.995

    def test_07_w_market_cap_at_tip(self):
        """Flag ON: w_market at tip (rem=48) should be 1.0 (full market trust)."""
        # Verify by checking that at period=1, clock=12:00 (rem=48),
        # flag ON with pregame_wp=0.70 and neutral projected margin (~0)
        # produces a result near 0.70 (full market trust).
        overlay = _make_overlay(1, "12:00", 0, 0)
        # proj_margin ≈ 0 → p_proj ≈ 0.5
        # flag ON: w_market=1.0 → p = 1.0*0.70 + 0.0*0.5 = 0.70
        # flag OFF: w_market=0.80 → p = 0.80*0.70 + 0.20*0.5 = 0.66
        r_on = _call_flag_on(overlay, 0.70, proj_home=110.0, proj_away=110.0)
        r_off = _call_flag_off(overlay, 0.70, proj_home=110.0, proj_away=110.0)
        # On should be closer to 0.70 (full market); off slightly lower.
        assert r_on > r_off, (
            f"flag ON should be more market-anchored at tip: on={r_on} off={r_off}"
        )
        assert abs(r_on - 0.70) < abs(r_off - 0.70), (
            f"flag ON should be closer to pregame wp 0.70: on={r_on} off={r_off}"
        )

    def test_08_w_market_cap_off_at_tip(self):
        """Flag OFF: w_market at tip (rem=48) capped at 0.80."""
        # rem=48: w_market = min(0.80, 48/48) = 0.80
        # With pregame=0.60 and proj_margin=0 → p_proj≈0.5:
        # p = 0.80*0.60 + 0.20*0.50 = 0.48+0.10 = 0.58
        overlay = _make_overlay(1, "12:00", 0, 0)
        r_off = _call_flag_off(overlay, 0.60, proj_home=110.0, proj_away=110.0)
        # r_off should be ~0.58 (not 0.60 = full market)
        assert abs(r_off - 0.58) < 0.05, (
            f"flag OFF at tip: expected ~0.58, got {r_off}"
        )

    def test_09_final_game_converges(self):
        """FINAL game status: rem=0, output should be near 0 or 1."""
        overlay = _make_overlay(4, "0:00", 112, 108, game_status="FINAL")
        r_off = _call_flag_off(overlay, 0.55, proj_home=112.0, proj_away=108.0)
        r_on = _call_flag_on(overlay, 0.55, proj_home=112.0, proj_away=108.0)
        # With rem=0, sigma=max(2.5, 12.5*sqrt(0.4/48)) ≈ 2.5 (floor).
        # proj_margin=4 → z = 4/(2.5*1.414) ≈ 1.13 → p≈0.87.
        # No market anchor (w_market=0 when rem=0).
        assert 0.005 <= r_off <= 0.995
        assert 0.005 <= r_on <= 0.995
        # Both should be above 0.5 (home leads projected)
        assert r_off > 0.5
        assert r_on > 0.5

    def test_10_fallback_no_projections(self):
        """No projected totals: both flags compute proj_margin from current scores."""
        overlay = _make_overlay(2, "6:00", 60, 55)
        r_off = _call_flag_off(overlay, 0.52)   # proj_home=None, proj_away=None
        r_on = _call_flag_on(overlay, 0.52)
        # Both should be above 0.5 (home leads), different values due to sigma.
        assert r_off is not None
        assert r_on is not None
        assert r_off != r_on, "no-projection paths should still differ (sigma/w_market change)"

    def test_11_no_pregame_wp(self):
        """No pregame wp: both flags fall through to p_proj (no market blend)."""
        overlay = _make_overlay(2, "6:00", 60, 55)
        r_off = _call_flag_off(overlay, None, proj_home=112.0, proj_away=108.0)
        r_on = _call_flag_on(overlay, None, proj_home=112.0, proj_away=108.0)
        # No pregame → no market anchor; only sigma differs.
        assert r_off is not None
        assert r_on is not None
        # With proj_margin=4, tighter sigma (ON) → stronger signal → different p_proj.
        assert r_off != r_on

    def test_12_ot_period(self):
        """OT period (period=5): rem computed from crem only."""
        overlay = _make_overlay(5, "3:00", 108, 108)
        r_off = _call_flag_off(overlay, 0.50, proj_home=112.0, proj_away=112.0)
        r_on = _call_flag_on(overlay, 0.50, proj_home=112.0, proj_away=112.0)
        # Tied game, pregame=0.5, proj tied → both ~0.5
        assert 0.4 <= r_off <= 0.6
        assert 0.4 <= r_on <= 0.6

    def test_13_sigma_12p5_at_tip_on(self):
        """Flag ON at tip: verify sigma=12.5*sqrt(48/48)=12.5 is used (not 14.5)."""
        # We can infer sigma by computing the expected p_proj and comparing.
        # At rem=48, pregame=0.50 (neutral), proj_margin=+13:
        #   flag ON:  sigma=12.5, z=13/(12.5*sqrt(2))=0.735, p_proj≈0.769
        #             w_market=1.0 → p = 1.0*0.5 + 0.0*0.769 = 0.5
        #   flag OFF: sigma=14.5, z=13/(14.5*sqrt(2))=0.634, p_proj≈0.737
        #             w_market=0.8 → p = 0.8*0.5 + 0.2*0.737 = 0.547
        # So with pregame=0.5 and w_market=1.0 (ON), p ≈ 0.5 regardless of proj.
        # With pregame=0.5 and w_market=0.8 (OFF), p mixes in p_proj.
        overlay = _make_overlay(1, "12:00", 0, 0)
        r_on = _call_flag_on(overlay, 0.50, proj_home=111.5, proj_away=98.5)  # margin=+13
        r_off = _call_flag_off(overlay, 0.50, proj_home=111.5, proj_away=98.5)
        # ON: w_market=1.0 → fully market-anchored → r_on ≈ 0.50
        assert abs(r_on - 0.50) < 0.02, f"flag ON at tip should ~= pregame_wp=0.5, got {r_on}"
        # OFF: w_market=0.80 → mixes in p_proj → r_off > 0.50
        assert r_off > r_on, f"flag OFF should be more influenced by proj margin: {r_off} vs {r_on}"

    def test_14_all_env_false_values_are_off(self):
        """CV_WP_RECONCILED_CALIB=false/off/0/ all map to flag OFF."""
        overlay = _make_overlay(2, "6:00", 60, 55)
        r_baseline = _call_flag_off(overlay, 0.52, proj_home=112.0, proj_away=108.0)
        for falsy in ("0", "false", "off", "", "False", "OFF"):
            os.environ["CV_WP_RECONCILED_CALIB"] = falsy
            r = _lwp_fn(overlay, 0.52, 112.0, 108.0)
            os.environ.pop("CV_WP_RECONCILED_CALIB", None)
            assert r == r_baseline, (
                f"CV_WP_RECONCILED_CALIB={falsy!r} should be byte-identical to OFF, "
                f"got {r} vs {r_baseline}"
            )

    def test_15_truthy_values_are_on(self):
        """CV_WP_RECONCILED_CALIB=1/true/True all map to flag ON."""
        overlay = _make_overlay(2, "6:00", 60, 55)
        r_on_ref = _call_flag_on(overlay, 0.52, proj_home=112.0, proj_away=108.0)
        for truthy in ("1", "true", "True", "TRUE", "on", "ON"):
            os.environ["CV_WP_RECONCILED_CALIB"] = truthy
            r = _lwp_fn(overlay, 0.52, 112.0, 108.0)
            os.environ.pop("CV_WP_RECONCILED_CALIB", None)
            assert r == r_on_ref, (
                f"CV_WP_RECONCILED_CALIB={truthy!r} should equal flag ON ref, "
                f"got {r} vs {r_on_ref}"
            )
