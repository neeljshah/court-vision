"""Per-file test for mlb_live_model -- in-game P(home win) for MLB.

Run ONLY this file (the full suite freezes the box):
    python -m pytest scripts/platformkit/ingame/test_mlb_live_model.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame.mlb_live_model import mlb_home_prob


def _state(p0=0.45, diff=0.0, frac=0.5, status="In Progress"):
    return {"p0": p0, "state_diff": diff, "frac_elapsed": frac, "status": status}


def test_early_game_near_pregame_prior():
    # frac=0.05 (top 1st, tied) -> blend should sit very close to the pregame prior.
    p = mlb_home_prob(_state(p0=0.40, diff=0.0, frac=0.05))
    assert p is not None
    assert abs(p - 0.40) < 0.12  # early -> mostly pregame


def test_late_lead_pulls_toward_win():
    # frac=0.92 (top 9th), home up 4 -> should be well above the pregame prior.
    p = mlb_home_prob(_state(p0=0.40, diff=4.0, frac=0.92))
    assert p is not None and p > 0.85


def test_late_deficit_pulls_toward_loss():
    p = mlb_home_prob(_state(p0=0.55, diff=-4.0, frac=0.92))
    assert p is not None and p < 0.15


def test_freshness_monotone_for_same_lead():
    # the SAME +2 lead is worth more (higher p_home) later in the game than earlier.
    early = mlb_home_prob(_state(p0=0.5, diff=2.0, frac=0.2))
    late = mlb_home_prob(_state(p0=0.5, diff=2.0, frac=0.85))
    assert early is not None and late is not None
    assert late > early


def test_final_game_is_skipped():
    assert mlb_home_prob(_state(diff=2.0, frac=1.0, status="Final")) is None
    assert mlb_home_prob(_state(diff=2.0, frac=0.99, status="Final")) is None


# --------------------------------------------------------------------------------------- #
# LANE 2 (wave-14 grade-write wedge fix): frac_elapsed==1.0 from a STILL-LIVE bottom-9th /
# extra-innings tick must NOT be treated as final. ingame_live_state's MLB frac formula
# saturates at exactly 1.0 from the bottom of the 9th onward (denom_half=18.0) and stays
# clamped there through every extra inning -- only the real ESPN status string decides
# finality (_is_final), never frac_elapsed reaching/exceeding 1.0.
# --------------------------------------------------------------------------------------- #
def test_bottom_ninth_saturated_frac_still_prices():
    # frac_elapsed==1.0 (bottom 9th math saturates), status is still live -> must price,
    # not skip. This was the root cause of the wave-14 grade-write wedge (MIL@ARI stall).
    p = mlb_home_prob(_state(p0=0.45, diff=1.0, frac=1.0, status="Bottom 9th"))
    assert p is not None and 0.0 <= p <= 1.0


def test_extra_innings_saturated_frac_still_prices():
    # Extras (e.g. "Top 11th") also read frac_elapsed==1.0 from the live feed -- must
    # still produce a number every tick, not permanently stall after the 9th.
    p = mlb_home_prob(_state(p0=0.50, diff=0.0, frac=1.0, status="Top 11th"))
    assert p is not None and 0.0 <= p <= 1.0
    # A big extra-innings lead should price decisively toward the leader (max freshness).
    p_lead = mlb_home_prob(_state(p0=0.50, diff=3.0, frac=1.0, status="Top 11th"))
    assert p_lead is not None and p_lead > 0.8


def test_frac_elapsed_over_one_also_still_prices():
    # Defensive: even if frac_elapsed somehow exceeds 1.0 (a future formula variant),
    # a live status must still be priced, never skipped -- only _is_final gates finality.
    p = mlb_home_prob(_state(p0=0.5, diff=1.0, frac=1.05, status="Top 12th"))
    assert p is not None and 0.0 <= p <= 1.0


def test_negative_frac_elapsed_is_honest_skip():
    # An unparseable/negative freshness lever is still a clean skip (never fabricated).
    assert mlb_home_prob(_state(p0=0.5, diff=1.0, frac=-0.1, status="Top 1st")) is None


def test_missing_fields_skip():
    assert mlb_home_prob({"state_diff": 1.0, "frac_elapsed": 0.5}) is None  # no p0
    assert mlb_home_prob({"p0": 0.5, "frac_elapsed": 0.5}) is None          # no diff
    assert mlb_home_prob({"p0": 0.5, "state_diff": 1.0}) is None            # no frac
    assert mlb_home_prob("not a dict") is None


def test_returns_probability_in_unit_interval():
    for diff in (-6, -2, 0, 2, 6):
        for frac in (0.05, 0.5, 0.95):
            p = mlb_home_prob(_state(diff=diff, frac=frac))
            assert p is not None and 0.0 <= p <= 1.0


def test_via_live_board_seam():
    # the live_board model_fn seam must route mlb through this model.
    from scripts.platformkit.frontend.live_board import live_model_home_prob
    p = live_model_home_prob("mlb", _state(p0=0.5, diff=3.0, frac=0.9))
    assert p is not None and p > 0.5
