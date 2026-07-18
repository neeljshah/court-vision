"""Per-file test for shooter_isolated_v4_claims -- synthetic frames only.
Run: python -m pytest scripts/platformkit/intel_validation/test_shooter_isolated_v4_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import shooter_isolated_v4_claims as m


def _raw():
    # A and B shoot the same 40% from three -- but A is spoon-fed (95% assisted,
    # corner-heavy, no attention) while B self-creates under attention. The
    # context residual must rank B above A. C is a low-percentage creator.
    # 14 rows so the 4-parameter OLS is well-determined (6 rows overfit and
    # made the residual ordering arbitrary -- caught on first run). The filler
    # players encode the context gradient the fit must learn: higher assisted
    # share and corner diet -> higher expected fg3_pct.
    filler_assist = [.9, .85, .8, .75, .7, .65, .6, .55, .5, .45]
    filler_corner = [.45, .42, .4, .37, .35, .32, .3, .27, .25, .22]
    filler_pct = [.41, .405, .40, .395, .39, .385, .38, .375, .37, .365]
    return pd.DataFrame({
        "player_id": list(range(1, 15)),
        "player_name": ["A_fed", "B_creator", "C_low", "D"] + [f"F{i}" for i in range(10)],
        "games": [70] * 14,
        "fg3a_per_game": [6.0, 6.0, 5.0, 4.0] + [5.0] * 10,
        "fg3_pct": [.40, .40, .33, .36] + filler_pct,
        "ft_pct": [.85, .88, .80, .82] + [.83] * 10,
        "assisted_3_share": [.95, .30, .40, .70] + filler_assist,
        "corner_diet_share": [.50, .10, .20, .30] + filler_corner,
        "gravity": [.01, .06, .04, .03] + [.03] * 10,
        "self_created_volume": [6.0 * .05, 6.0 * .70, 5.0 * .60, 4.0 * .30]
                                + [5.0 * (1 - a) for a in filler_assist],
    })


def test_creator_outranks_spoonfed_at_equal_pct():
    snap = m.compute_snapshot(_raw())
    a = snap[snap["player_name"] == "A_fed"].iloc[0]
    b = snap[snap["player_name"] == "B_creator"].iloc[0]
    assert b["context_resid"] > a["context_resid"]
    assert b["shooter_isolated_v4"] > a["shooter_isolated_v4"]


def test_claim_contract_and_floor():
    snap = m.compute_snapshot(_raw())
    claim = m.build_claim(snap, "2025-26")
    assert claim["claim_id"] == "shooter_isolated_v4_full_season_2025_26"
    assert claim["edge_claimed"] is False
    assert claim["criteria"]["min_sample"] == {"n_present": 2}
    assert "DESCRIPTIVE" in claim["caveats"][0]
    assert claim["ranking"][0]["rank"] == 1
