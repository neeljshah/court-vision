"""tests/test_live_adjustment.py — same-day projection adjustment layer."""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.live_adjustment import (  # noqa: E402
    adjust_projection,
    vacated_usage_share,
    is_enabled,
    load_coeffs,
    _MULT_LO,
    _MULT_HI,
    _VAC_BUMP_STRONG_GATE,
    _VAC_BUMP_STRONG_SCALE,
    _VAC_BUMP_STRONG_STATS,
)

_COEFFS = {
    "inactive_pts_k": 0.44, "inactive_reb_k": 0.25,
    "blowout_min_k": -0.0035, "blowout_slack": 12.0,
    "baseline_game_total": 228.0, "pace_damp": 0.5,
}


# ── vacated_usage_share ───────────────────────────────────────────────────────
def test_share_zero_when_no_one_out():
    assert vacated_usage_share([], 20.0) == 0.0


def test_share_increases_with_out_scoring():
    low = vacated_usage_share([10.0], 20.0)
    high = vacated_usage_share([25.0, 18.0], 20.0)
    assert 0.0 < low < high < 0.95


def test_share_bounded():
    # huge vacated usage, tiny player -> approaches but never reaches the cap
    s = vacated_usage_share([200.0], 0.0)
    assert 0.0 < s <= 0.95


# ── no-op behavior ────────────────────────────────────────────────────────────
def test_noop_when_no_context():
    base = {"pts": 20.0, "reb": 8.0, "ast": 5.0}
    out = adjust_projection(base, coeffs=_COEFFS)
    assert out == {"pts": 20.0, "reb": 8.0, "ast": 5.0}


def test_unknown_nonnumeric_passes_through():
    base = {"pts": 20.0, "label": "starter"}
    out = adjust_projection(base, vac_share=0.3, coeffs=_COEFFS)
    assert out["label"] == "starter"


# ── inactive bump ─────────────────────────────────────────────────────────────
def test_inactive_bump_raises_usage_stats_more_than_opportunity():
    base = {"pts": 20.0, "reb": 8.0}
    out = adjust_projection(base, vac_share=0.3, coeffs=_COEFFS)
    # pts uses k=0.44, reb uses k=0.25 -> pts lifts by a larger fraction
    pts_lift = out["pts"] / 20.0 - 1
    reb_lift = out["reb"] / 8.0 - 1
    assert pts_lift > reb_lift > 0


def test_inactive_bump_matches_calibrated_coefficient():
    base = {"pts": 20.0}
    out = adjust_projection(base, vac_share=0.5, coeffs=_COEFFS)
    assert out["pts"] == round(20.0 * (1 + 0.44 * 0.5), 3)


# ── pace ──────────────────────────────────────────────────────────────────────
def test_high_total_raises_counting_stats():
    base = {"pts": 20.0}
    hi = adjust_projection(base, game_total=250.0, coeffs=_COEFFS)["pts"]
    lo = adjust_projection(base, game_total=210.0, coeffs=_COEFFS)["pts"]
    assert hi > 20.0 > lo


def test_pace_is_damped():
    # total 12% over baseline -> only ~6% bump (pace_damp 0.5)
    base = {"pts": 100.0}
    out = adjust_projection(base, game_total=228.0 * 1.12, coeffs=_COEFFS)["pts"]
    assert abs(out - 106.0) < 0.5


# ── blowout ───────────────────────────────────────────────────────────────────
def test_blowout_cuts_when_spread_large():
    base = {"pts": 20.0}
    big = adjust_projection(base, game_spread=20.0, coeffs=_COEFFS)["pts"]
    assert big < 20.0


def test_no_blowout_inside_slack():
    base = {"pts": 20.0}
    out = adjust_projection(base, game_spread=8.0, coeffs=_COEFFS)["pts"]
    assert out == 20.0  # spread within slack -> no haircut, no other term


# ── clamp ─────────────────────────────────────────────────────────────────────
def test_net_multiplier_is_clamped():
    base = {"pts": 100.0}
    # absurd combined context should never exceed the clamp band
    out = adjust_projection(base, vac_share=0.95, game_total=400.0,
                            coeffs=_COEFFS, return_breakdown=True)
    proj, bd = out
    assert _MULT_LO <= bd["pts"]["net"] <= _MULT_HI
    assert proj["pts"] <= 100.0 * _MULT_HI + 1e-6


def test_breakdown_keys():
    base = {"pts": 20.0}
    _proj, bd = adjust_projection(base, vac_share=0.2, game_total=235.0,
                                  game_spread=15.0, coeffs=_COEFFS,
                                  return_breakdown=True)
    assert set(bd["pts"]) == {"inactive", "pace", "blowout", "net"}


# ── flag + coeff loading ──────────────────────────────────────────────────────
def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("CV_LIVE_ADJUST", raising=False)
    assert is_enabled() is False
    monkeypatch.setenv("CV_LIVE_ADJUST", "1")
    assert is_enabled() is True


def test_calibrated_coeffs_load():
    c = load_coeffs()
    # file exists from calibration; sanity-check the signs/ranges
    assert c["inactive_pts_k"] > 0
    assert c["blowout_min_k"] < 0
    assert 200 < c["baseline_game_total"] < 250


# ── CV_VAC_BUMP_GATED: gate the vacated-load bump to validated high-share pts/reb ──
# (VAC_BUMP_ACCURACY_VALIDATION.md: the FLAT bump hurts MAE +0.57%; it only helps at
#  high vac_share, and AST is mis-tuned). Default params = byte-identical flat bump.

def test_vac_gate_default_params_byte_identical():
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0, "fg3m": 2.0}
    flat = adjust_projection(base, vac_share=0.5)
    # AST IS bumped under the flat default (the mis-tuning the gate fixes)
    assert flat["ast"] > 5.0 and flat["pts"] > 20.0 and flat["reb"] > 6.0


def test_vac_gate_low_share_is_noop():
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0, "fg3m": 2.0}
    out = adjust_projection(base, vac_share=0.5, vac_min_share=0.60,
                            vac_stats=frozenset({"pts", "reb"}))
    assert out == base, "share below gate -> no vac bump (base already absorbs it)"


def test_vac_gate_high_share_pts_reb_only():
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0, "fg3m": 2.0}
    out = adjust_projection(base, vac_share=0.7, vac_min_share=0.60,
                            vac_stats=frozenset({"pts", "reb"}))
    assert out["pts"] > 20.0, "pts bumped at high share (validated win)"
    assert out["reb"] > 6.0, "reb bumped at high share (validated win)"
    assert abs(out["ast"] - 5.0) < 1e-9, "AST NOT bumped (mis-tuned coefficient)"
    assert abs(out["fg3m"] - 2.0) < 1e-9, "fg3m NOT bumped (not a validated vac stat)"


def test_vac_gate_pace_still_applies_below_gate():
    # pace/blowout terms are independent of the vac gate
    base = {"pts": 20.0}
    out = adjust_projection(base, vac_share=0.1, game_total=240.0,
                            vac_min_share=0.60, vac_stats=frozenset({"pts", "reb"}))
    assert out["pts"] != 20.0, "pace term still applies even when vac is gated off"


# ── CV_VAC_BUMP_STRONG: stronger gated coefficient (s=1.28, PTS/REB only >= 0.60) ──
# (VAC_BUMP_COEFFICIENT_TUNING.md: temporal held-out, two splits, MAE-optimal s=1.28
#  beats 1x on RMSE at both 70/30 and 65/35 splits for PTS and REB; AST excluded.)

def test_vac_bump_strong_default_off_is_byte_identical(monkeypatch):
    """Default (CV_VAC_BUMP_STRONG=0) produces EXACTLY the same result as 1x bump."""
    monkeypatch.delenv("CV_VAC_BUMP_STRONG", raising=False)
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0}
    # default call (env unset) and explicit vac_strong_scale=1.0 must be identical
    out_default = adjust_projection(base, vac_share=0.75, coeffs=_COEFFS)
    out_explicit = adjust_projection(base, vac_share=0.75, coeffs=_COEFFS,
                                     vac_strong_scale=1.0)
    assert out_default == out_explicit, "Default OFF must be byte-identical to scale=1.0"


def test_vac_bump_strong_on_increases_pts_reb_at_high_share(monkeypatch):
    """With CV_VAC_BUMP_STRONG=1, PTS and REB are bumped MORE at high vac_share.

    Use vac_share=0.60 (gate threshold) — at 1x the PTS multiplier is 1.264 (no clamp),
    while at 1.28x it is 1.338 (clamps to 1.30), so output still increases: 25.28 -> 26.0.
    """
    monkeypatch.delenv("CV_VAC_BUMP_STRONG", raising=False)
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0}
    vac = 0.60  # at the gate threshold — 1x does NOT clamp; 1.28x clamps but is larger
    out_1x = adjust_projection(base, vac_share=vac, coeffs=_COEFFS,
                                vac_strong_scale=1.0)
    out_strong = adjust_projection(base, vac_share=vac, coeffs=_COEFFS,
                                   vac_strong_scale=_VAC_BUMP_STRONG_SCALE)
    assert out_strong["pts"] > out_1x["pts"], "STRONG scale bumps PTS more than 1x"
    assert out_strong["reb"] > out_1x["reb"], "STRONG scale bumps REB more than 1x"
    assert out_strong["ast"] == out_1x["ast"], "AST NOT scaled (mis-tuned; excluded)"


def test_vac_bump_strong_no_effect_below_gate(monkeypatch):
    """CV_VAC_BUMP_STRONG has no effect when vac_share < 0.60."""
    monkeypatch.delenv("CV_VAC_BUMP_STRONG", raising=False)
    base = {"pts": 20.0, "reb": 6.0}
    vac = 0.50  # BELOW the gate threshold
    out_1x = adjust_projection(base, vac_share=vac, coeffs=_COEFFS,
                                vac_strong_scale=1.0)
    out_strong = adjust_projection(base, vac_share=vac, coeffs=_COEFFS,
                                   vac_strong_scale=_VAC_BUMP_STRONG_SCALE)
    assert out_strong == out_1x, (
        "Strong scale has no effect below the gate (vac_share < "
        f"{_VAC_BUMP_STRONG_GATE})"
    )


def test_vac_bump_strong_env_flag(monkeypatch):
    """CV_VAC_BUMP_STRONG=1 env var activates the stronger scale automatically.

    Use vac_share=0.60 so 1x doesn't clamp (mult=1.264) but 1.28x does (1.338->1.30),
    giving different outputs (25.28 vs 26.0 for PTS).
    """
    from src.prediction import live_adjustment as la
    base = {"pts": 20.0, "reb": 6.0, "ast": 5.0}
    vac = 0.60  # at gate threshold — 1x no clamp, 1.28x clamps to 1.30 but is larger

    # Force OFF
    monkeypatch.setenv("CV_VAC_BUMP_STRONG", "0")
    out_off = la.adjust_projection(base, vac_share=vac, coeffs=_COEFFS)

    # Force ON
    monkeypatch.setenv("CV_VAC_BUMP_STRONG", "1")
    out_on = la.adjust_projection(base, vac_share=vac, coeffs=_COEFFS)

    assert out_on["pts"] > out_off["pts"], "ENV=1 activates stronger PTS bump"
    assert out_on["reb"] > out_off["reb"], "ENV=1 activates stronger REB bump"
    assert out_on["ast"] == out_off["ast"], "AST unchanged regardless of flag"


def test_vac_bump_strong_stats_constants():
    """Sanity: the strong-bump constants have expected values."""
    assert _VAC_BUMP_STRONG_GATE == 0.60
    assert 1.2 <= _VAC_BUMP_STRONG_SCALE <= 1.5, "Scale should be in the fit range"
    assert "pts" in _VAC_BUMP_STRONG_STATS
    assert "reb" in _VAC_BUMP_STRONG_STATS
    assert "ast" not in _VAC_BUMP_STRONG_STATS
